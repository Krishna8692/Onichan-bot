"""
TON Wallet Monitor
Polls the TON Center API every 30 seconds for new incoming transactions.
When a matching payment is found (amount + comment = user's Telegram ID),
premium is activated automatically.
"""

import asyncio
import time
import aiohttp
from datetime import datetime, timedelta

TON_NANOTONS = 1_000_000_000
POLL_INTERVAL = 30          # seconds between polls
AMOUNT_TOLERANCE = 0.05     # accept up to 5% less (covers TX fees)
PENDING_EXPIRY = 3600       # 1 hour to complete payment

# Shared pending payments: user_id (int) -> {plan_key, name, duration_days, nanotons, created_at}
_pending: dict = {}

# Last processed transaction lt (logical time) — avoids double-processing
_last_lt: int = 0


def add_pending(user_id: int, plan_key: str, name: str, duration_days: int, ton_amount: str):
    nanotons = int(float(ton_amount) * TON_NANOTONS)
    _pending[user_id] = {
        "plan_key": plan_key,
        "name": name,
        "duration_days": duration_days,
        "nanotons": nanotons,
        "ton": ton_amount,
        "created_at": time.time(),
    }


def remove_pending(user_id: int):
    _pending.pop(user_id, None)


def get_pending(user_id: int):
    return _pending.get(user_id)


def _expired_ids():
    now = time.time()
    return [uid for uid, p in _pending.items() if now - p["created_at"] > PENDING_EXPIRY]


async def _fetch_transactions(wallet: str, limit: int = 50):
    """Fetch recent incoming transactions from TON Center API."""
    url = "https://toncenter.com/api/v2/getTransactions"
    params = {"address": wallet, "limit": limit, "archival": "false"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", [])
    except Exception as e:
        print(f"[TON Monitor] Fetch error: {e}")
    return []


def _parse_comment(tx: dict) -> str:
    """Extract the text comment from a transaction."""
    try:
        msg = tx.get("in_msg", {})
        # Plain text comment
        message = msg.get("message", "") or ""
        if message:
            return message.strip()
        # Encoded message body fallback
        msg_data = msg.get("msg_data", {})
        if isinstance(msg_data, dict):
            text = msg_data.get("text", "") or ""
            if text:
                import base64
                try:
                    return base64.b64decode(text).decode("utf-8", errors="ignore").strip()
                except Exception:
                    return text.strip()
    except Exception:
        pass
    return ""


async def _run_monitor(wallet: str, bot, set_premium_fn):
    global _last_lt
    print(f"[TON Monitor] Started — watching {wallet[:8]}...{wallet[-6:]}")

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        # Clean up expired pending payments
        for uid in _expired_ids():
            _pending.pop(uid, None)

        if not _pending:
            continue

        txs = await _fetch_transactions(wallet)
        if not txs:
            continue

        for tx in txs:
            lt = int(tx.get("transaction_id", {}).get("lt", 0))
            if lt <= _last_lt:
                continue  # already processed

            in_msg = tx.get("in_msg", {})
            value = int(in_msg.get("value", 0))
            if value <= 0:
                continue  # outgoing or empty

            comment = _parse_comment(tx)
            print(f"[TON Monitor] TX lt={lt} value={value} comment='{comment}'")

            # Try to match against a pending payment
            matched_uid = None
            for uid, pending in list(_pending.items()):
                expected = pending["nanotons"]
                tolerance = int(expected * AMOUNT_TOLERANCE)
                uid_str = str(uid)

                if comment == uid_str and value >= expected - tolerance:
                    matched_uid = uid
                    matched_pending = pending
                    break

            if matched_uid:
                _pending.pop(matched_uid, None)
                plan = matched_pending
                expiry = datetime.now() + timedelta(days=plan["duration_days"])
                set_premium_fn(matched_uid, expiry)

                ton_actual = value / TON_NANOTONS
                print(f"[TON Monitor] ✅ Activated {matched_uid} — {plan['name']} ({ton_actual:.4f} TON)")

                try:
                    await bot.send_message(
                        chat_id=matched_uid,
                        text=(
                            f"✅ <b>TON Payment Confirmed!</b>\n\n"
                            f"📦 <b>Plan:</b> {plan['name']}\n"
                            f"💎 <b>Paid:</b> {ton_actual:.4f} TON\n"
                            f"📅 <b>Expires:</b> {expiry.strftime('%Y-%m-%d')}\n\n"
                            f"🎉 Your premium is now <b>active</b>!\n"
                            f"Enjoy all features. Thank you!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"[TON Monitor] Notify error: {e}")

            # Update last processed lt (keep the highest we've seen)
            if lt > _last_lt:
                _last_lt = lt


async def start_monitor(wallet: str, bot, set_premium_fn):
    """Launch the monitor as a background asyncio task."""
    if not wallet:
        print("[TON Monitor] No wallet configured — skipping.")
        return
    asyncio.create_task(_run_monitor(wallet, bot, set_premium_fn))
