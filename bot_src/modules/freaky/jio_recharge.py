"""
Jio recharge payment flow.
Handles the Jio-specific recharge API with card payment.
"""
import re
import json
import time
import random
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urlencode

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
]

JIO_RECHARGE_URL = "https://www.jio.com/api/v1/recharge"
JIO_PAY_URL = "https://www.jio.com/api/v1/payment"
JIO_ORDER_URL = "https://www.jio.com/api/v1/order"


def _jio_headers(referer: str = "https://www.jio.com") -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.jio.com",
        "Referer": referer,
        "X-Request-Source": "jio_web",
        "X-App-Version": "3.0.0",
    }


async def do_jio_recharge(
    session: aiohttp.ClientSession,
    mobile: str,
    cc: str,
    mm: str,
    yy: str,
    cvv: str,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Jio mobile recharge using a card.
    Returns status dict without gateway/time_taken (caller adds those).
    """
    exp_year = int("20" + yy) if len(yy) == 2 else int(yy)

    # Step 1: Get recharge plans to pick the smallest one
    plan_id = None
    amount = None
    try:
        async with session.get(
            f"https://www.jio.com/api/v1/plans?mobile={mobile}&type=prepaid",
            headers=_jio_headers(),
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            plans_data = await resp.json(content_type=None)
            plans = plans_data.get("plans", plans_data.get("data", {}).get("plans", []))
            if plans:
                # Pick cheapest plan
                sorted_plans = sorted(plans, key=lambda p: float(p.get("price", p.get("amount", 999999))))
                plan = sorted_plans[0]
                plan_id = plan.get("id") or plan.get("planId")
                amount = plan.get("price") or plan.get("amount")
    except Exception:
        pass

    if not plan_id:
        plan_id = "599"
        amount = "599"

    # Step 2: Create recharge order
    order_id = None
    try:
        order_payload = {
            "mobile": mobile,
            "planId": str(plan_id),
            "amount": str(amount),
            "paymentType": "CC",
        }
        async with session.post(
            JIO_ORDER_URL,
            json=order_payload,
            headers=_jio_headers(),
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            order_data = await resp.json(content_type=None)
            order_id = order_data.get("orderId") or order_data.get("data", {}).get("orderId")
    except Exception:
        pass

    # Step 3: Pay with card
    pay_payload = {
        "orderId": order_id or f"JIO{int(time.time())}",
        "mobile": mobile,
        "cardNumber": cc,
        "expiryMonth": mm.zfill(2),
        "expiryYear": str(exp_year),
        "cvv": cvv,
        "cardHolderName": "John Doe",
        "saveCard": False,
        "amount": str(amount),
    }

    try:
        async with session.post(
            JIO_PAY_URL,
            json=pay_payload,
            headers=_jio_headers(f"https://www.jio.com/recharge/{mobile}"),
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            text = await resp.text(errors="ignore")
            status_code = resp.status
            try:
                pay_data = json.loads(text)
            except Exception:
                pay_data = {}

        return _classify_jio_response(pay_data, text, status_code)

    except asyncio.TimeoutError:
        return {"status": "error", "message": "Request timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


def _classify_jio_response(data: dict, text: str, status_code: int) -> Dict[str, str]:
    lower = text.lower()

    result = data.get("result", data.get("status", "")).lower()
    msg = data.get("message", data.get("msg", "")).lower()

    if result in ("success", "approved", "paid") or "success" in msg:
        return {"status": "live", "message": "Recharge Successful ✅"}
    if result in ("failed", "declined", "rejected") or "declined" in msg:
        return {"status": "decline", "message": data.get("message", "Payment Declined") + " ❌"}
    if "otp" in lower or "authentication" in lower or "3d" in lower or "verify" in lower:
        return {"status": "3ds", "message": "OTP/Verification Required 🔐"}
    if any(k in lower for k in ["successful", "recharge done", "activated"]):
        return {"status": "live", "message": "Recharge Successful ✅"}
    if any(k in lower for k in ["declined", "failed", "invalid", "insufficient"]):
        return {"status": "decline", "message": "Payment Declined ❌"}

    if status_code == 200:
        return {"status": "live", "message": "Processed ✅"}

    return {"status": "decline", "message": f"Unknown Response ⚠️"}
