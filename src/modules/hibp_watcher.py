"""
HaveIBeenPwned Leaked Credentials Watcher
Users register emails to watch; background thread checks HIBP API.
"""

import os
import sys
import time
import threading
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import _execute_with_retry, get_connection_with_retry

HIBP_API_KEY = os.environ.get("HIBP_API_KEY", "")
HIBP_BASE = "https://haveibeenpwned.com/api/v3"
CHECK_INTERVAL = 3600 * 6

_bot_ref = None
_watcher_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def init_hibp_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hibp_watchlist (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    last_checked TIMESTAMP,
                    known_breaches TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT TRUE,
                    added_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, email)
                )
            """)
        return True
    except Exception as e:
        print(f"[HIBP] Table init error: {e}")
        return False


def add_watch(user_id: int, email: str) -> tuple:
    email = email.strip().lower()
    if "@" not in email:
        return False, "Invalid email address."
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM hibp_watchlist WHERE user_id=%s AND is_active=TRUE
            """, (user_id,))
            count = cur.fetchone()[0]
            if count >= 5:
                return "limit"
            cur.execute("""
                INSERT INTO hibp_watchlist (user_id, email)
                VALUES (%s, %s) ON CONFLICT (user_id, email) DO UPDATE SET is_active=TRUE
            """, (user_id, email))
            return "ok"
    result = _execute_with_retry(_op)
    if result == "limit":
        return False, "You can watch up to 5 emails."
    return (True, f"Watching {email} for breaches.") if result == "ok" else (False, "DB error.")


def remove_watch(user_id: int, email: str) -> bool:
    email = email.strip().lower()
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE hibp_watchlist SET is_active=FALSE
                WHERE user_id=%s AND email=%s
            """, (user_id, email))
        return True
    return bool(_execute_with_retry(_op))


def get_user_watches(user_id: int) -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT email, last_checked, known_breaches, is_active
                FROM hibp_watchlist WHERE user_id=%s AND is_active=TRUE
                ORDER BY added_at DESC
            """, (user_id,))
            return [{"email": r[0], "checked": r[1],
                     "breaches": r[2] or "", "active": r[3]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def _check_email(email: str) -> List[str]:
    if not HIBP_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{HIBP_BASE}/breachedaccount/{email}",
            headers={"hibp-api-key": HIBP_API_KEY,
                     "User-Agent": "OnichanBot/1.0"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return [b.get("Name", "") for b in data]
        elif resp.status_code == 404:
            return []
        else:
            return []
    except Exception:
        return []


def _watcher_loop() -> None:
    print("[HIBP] Watcher loop started")
    import asyncio

    while not _stop_event.is_set():
        try:
            conn = get_connection_with_retry()
            if conn:
                with conn.cursor() as cur:
                    cutoff = datetime.utcnow() - timedelta(seconds=CHECK_INTERVAL)
                    cur.execute("""
                        SELECT id, user_id, email, known_breaches
                        FROM hibp_watchlist
                        WHERE is_active=TRUE AND (last_checked IS NULL OR last_checked < %s)
                        ORDER BY last_checked ASC NULLS FIRST LIMIT 20
                    """, (cutoff,))
                    rows = cur.fetchall()

                for wid, user_id, email, known_str in rows:
                    if _stop_event.is_set():
                        break
                    known = set(b for b in (known_str or "").split(",") if b)
                    new_breaches = _check_email(email)
                    new_set = set(new_breaches)
                    newly_found = new_set - known

                    def _update(conn, wid=wid, all_breaches=new_set):
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE hibp_watchlist SET last_checked=NOW(), known_breaches=%s
                                WHERE id=%s
                            """, (",".join(all_breaches), wid))
                    _execute_with_retry(_update)

                    if newly_found and _bot_ref:
                        breach_list = "\n".join(f"• {b}" for b in list(newly_found)[:10])
                        msg = (f"🚨 <b>New Data Breach Alert!</b>\n\n"
                               f"📧 <b>Email:</b> <code>{email}</code>\n"
                               f"💀 <b>Found in {len(newly_found)} new breach(es):</b>\n"
                               f"{breach_list}\n\n"
                               f"⚠️ Change your passwords immediately!")
                        try:
                            asyncio.run_coroutine_threadsafe(
                                _bot_ref.send_message(
                                    chat_id=user_id, text=msg, parse_mode="HTML"),
                                asyncio.get_event_loop()
                            )
                        except Exception as e:
                            print(f"[HIBP] Notify error for {user_id}: {e}")
                    time.sleep(1.5)

        except Exception as e:
            print(f"[HIBP] Watcher error: {e}")

        _stop_event.wait(300)


def start_watcher(bot=None) -> None:
    global _bot_ref, _watcher_thread
    _bot_ref = bot
    _stop_event.clear()
    _watcher_thread = threading.Thread(target=_watcher_loop, daemon=True, name="HIBPWatcher")
    _watcher_thread.start()
    print("[HIBP] Watcher started")
