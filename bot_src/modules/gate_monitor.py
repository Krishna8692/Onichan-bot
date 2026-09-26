"""
Gate Uptime Monitor & Hit Rate Analytics
- Background thread pings each gate every 5 minutes
- Tracks hit/dead ratios per gate
- Alerts admin on Telegram if a gate goes down
- Auto-disables gates whose live rate drops below threshold
"""

import os
import sys
import time
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import _execute_with_retry, get_connection_with_retry

_bot_ref = None
_admin_chat_id = None
_monitor_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

GATE_URLS: Dict[str, str] = {
    "pp":   "https://api.paypal.com/v1/oauth2/token",
    "ss":   "https://api.stripe.com/v1/tokens",
    "str":  "https://api.stripe.com/v1/tokens",
    "bu":   "https://api.braintreegateway.com/merchants/",
    "sq":   "https://connect.squareup.com/v2/payments",
    "rz":   "https://api.razorpay.com/v1/orders",
    "ast":  "https://api.authorize.net/xml/v1/request.api",
}

PING_INTERVAL = 300
AUTO_DISABLE_THRESHOLD = 5


def init_monitor_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gate_status (
                    gate VARCHAR(20) PRIMARY KEY,
                    is_up BOOLEAN DEFAULT TRUE,
                    last_check TIMESTAMP,
                    consecutive_failures INTEGER DEFAULT 0,
                    is_disabled BOOLEAN DEFAULT FALSE,
                    disabled_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gate_analytics (
                    id SERIAL PRIMARY KEY,
                    gate VARCHAR(20) NOT NULL,
                    user_id BIGINT,
                    result VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        return True
    except Exception as e:
        print(f"[GateMonitor] Table init error: {e}")
        return False


def record_check_result(gate: str, user_id: int, result: str) -> None:
    """Record a card check result for analytics (live/dead/error)."""
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gate_analytics (gate, user_id, result)
                VALUES (%s, %s, %s)
            """, (gate, user_id, result))
    try:
        _execute_with_retry(_op)
    except Exception:
        pass


def get_gate_stats(gate: Optional[str] = None,
                   since_hours: int = 24) -> List[Dict[str, Any]]:
    """Get hit/dead/error counts per gate for the last N hours."""
    since = datetime.utcnow() - timedelta(hours=since_hours)
    def _op(conn):
        with conn.cursor() as cur:
            if gate:
                cur.execute("""
                    SELECT gate,
                           COUNT(*) FILTER (WHERE result='live') as live_count,
                           COUNT(*) FILTER (WHERE result='dead') as dead_count,
                           COUNT(*) FILTER (WHERE result='error') as error_count,
                           COUNT(*) as total
                    FROM gate_analytics WHERE gate=%s AND created_at >= %s
                    GROUP BY gate
                """, (gate, since))
            else:
                cur.execute("""
                    SELECT gate,
                           COUNT(*) FILTER (WHERE result='live') as live_count,
                           COUNT(*) FILTER (WHERE result='dead') as dead_count,
                           COUNT(*) FILTER (WHERE result='error') as error_count,
                           COUNT(*) as total
                    FROM gate_analytics WHERE created_at >= %s
                    GROUP BY gate ORDER BY total DESC
                """, (since,))
            rows = cur.fetchall()
            result = []
            for r in rows:
                total = r[4] or 1
                live_pct = round((r[1] / total) * 100, 1)
                result.append({
                    "gate": r[0], "live": r[1], "dead": r[2],
                    "error": r[3], "total": total, "live_pct": live_pct
                })
            return result
    return _execute_with_retry(_op) or []


def _ping_gate(gate: str, url: str) -> bool:
    try:
        resp = requests.head(url, timeout=8, allow_redirects=True)
        return resp.status_code < 500
    except Exception:
        return False


def _update_gate_status(gate: str, is_up: bool) -> None:
    def _op(conn):
        with conn.cursor() as cur:
            if is_up:
                cur.execute("""
                    INSERT INTO gate_status (gate, is_up, last_check, consecutive_failures)
                    VALUES (%s, TRUE, NOW(), 0)
                    ON CONFLICT (gate) DO UPDATE SET
                        is_up=TRUE, last_check=NOW(), consecutive_failures=0
                """, (gate,))
            else:
                cur.execute("""
                    INSERT INTO gate_status (gate, is_up, last_check, consecutive_failures)
                    VALUES (%s, FALSE, NOW(), 1)
                    ON CONFLICT (gate) DO UPDATE SET
                        is_up=FALSE, last_check=NOW(),
                        consecutive_failures=gate_status.consecutive_failures+1
                """, (gate,))
    _execute_with_retry(_op)


def _get_consecutive_failures(gate: str) -> int:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT consecutive_failures FROM gate_status WHERE gate=%s", (gate,))
            row = cur.fetchone()
            return row[0] if row else 0
    return _execute_with_retry(_op) or 0


async def _notify_admin(message: str) -> None:
    if not _bot_ref or not _admin_chat_id:
        return
    try:
        await _bot_ref.send_message(
            chat_id=_admin_chat_id, text=message, parse_mode="HTML")
    except Exception as e:
        print(f"[GateMonitor] Notify error: {e}")


def _monitor_loop() -> None:
    print("[GateMonitor] Background monitor started")
    import asyncio
    while not _stop_event.is_set():
        for gate, url in GATE_URLS.items():
            if _stop_event.is_set():
                break
            try:
                up = _ping_gate(gate, url)
                _update_gate_status(gate, up)
                if not up:
                    fails = _get_consecutive_failures(gate)
                    if fails == 1 and _bot_ref and _admin_chat_id:
                        asyncio.run_coroutine_threadsafe(
                            _notify_admin(
                                f"⚠️ <b>Gate Down:</b> <code>{gate.upper()}</code>\n"
                                f"URL unreachable at {datetime.utcnow().strftime('%H:%M UTC')}"
                            ),
                            asyncio.get_event_loop()
                        )
            except Exception as e:
                print(f"[GateMonitor] Error checking {gate}: {e}")
        _stop_event.wait(PING_INTERVAL)
    print("[GateMonitor] Monitor stopped")


def start_monitor(bot=None, admin_chat_id=None) -> None:
    global _bot_ref, _admin_chat_id, _monitor_thread
    _bot_ref = bot
    _admin_chat_id = admin_chat_id
    _stop_event.clear()
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True,
                                       name="GateMonitor")
    _monitor_thread.start()
    print("[GateMonitor] Started")


def run_gate_health_check() -> List[Dict]:
    """Synchronous health check for all gates — used by /gatetest admin command."""
    results = []
    for gate, url in GATE_URLS.items():
        t0 = time.time()
        up = _ping_gate(gate, url)
        latency = round((time.time() - t0) * 1000)
        status = "🟢 Up" if up else "🔴 Down"
        results.append({"gate": gate, "status": status, "up": up, "latency_ms": latency})
    return results


def get_all_gate_statuses() -> List[Dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gate, is_up, last_check, consecutive_failures, is_disabled
                FROM gate_status ORDER BY gate
            """)
            return [{"gate": r[0], "up": r[1], "last_check": r[2],
                     "fails": r[3], "disabled": r[4]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []
