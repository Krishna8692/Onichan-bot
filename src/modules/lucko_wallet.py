"""
Lucko.ai Wallet Bridge
Maps bot users to Lucko members, handles credit transfers, and runs a background
idle-sweep so credits are never permanently stranded in Lucko wallets.
"""
import threading
import time
import uuid
import json
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any

from modules.database import _execute_with_retry
from modules.cc_shop import get_user_balance, add_user_balance
import modules.lucko_client as _api

logger = logging.getLogger(__name__)

_SWEEP_INTERVAL = 300      # seconds between idle-sweep runs
_IDLE_THRESHOLD = 1800     # mark session idle after 30 min with no exit call
_MIN_BALANCE_TO_SWEEP = 0.01  # don't bother sweeping dust amounts


def init_lucko_tables():
    """Create lucko DB tables — called from _create_tables() in database.py."""
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS lucko_members (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            lucko_member_id VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS lucko_transfers (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            direction VARCHAR(10) NOT NULL,
            credits_bot DECIMAL(10,2) NOT NULL DEFAULT 0,
            credits_lucko DECIMAL(10,2) NOT NULL DEFAULT 0,
            commission_pct DECIMAL(5,2) DEFAULT 0,
            commission_amount DECIMAL(10,2) DEFAULT 0,
            game_id VARCHAR(200) DEFAULT '',
            order_id VARCHAR(150) UNIQUE,
            status VARCHAR(20) DEFAULT 'pending',
            error_msg TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS lucko_settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_lucko_tf_user ON lucko_transfers(telegram_id, created_at DESC)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_lucko_tf_status ON lucko_transfers(status, created_at)")

    # Seed defaults (won't overwrite existing values)
    defaults = {
        'enabled': 'false',
        'default_commission_pct': '5.0',
        'min_buyin': '1.00',
        'max_buyin': '500.00',
        'default_buyin': '10.00',
        'game_settings': '{}',
    }
    for k, v in defaults.items():
        _execute_with_retry("""
            INSERT INTO lucko_settings (key, value, updated_at)
            VALUES (%s, %s, NOW()) ON CONFLICT (key) DO NOTHING
        """, (k, v))


# ── Settings helpers ─────────────────────────────────────────────────────────

def get_lucko_setting(key: str, default: str = '') -> str:
    row = _execute_with_retry(
        "SELECT value FROM lucko_settings WHERE key = %s", (key,), fetch_one=True
    )
    return (row['value'] if row else None) or default


def set_lucko_setting(key: str, value: str):
    _execute_with_retry("""
        INSERT INTO lucko_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (key, str(value)))


def is_enabled() -> bool:
    return get_lucko_setting('enabled', 'false').lower() == 'true'


def get_commission_pct(game_id: str = '') -> float:
    if game_id:
        try:
            game_settings = json.loads(get_lucko_setting('game_settings', '{}'))
            g = game_settings.get(game_id, {})
            if 'commission_pct' in g:
                return float(g['commission_pct'])
        except Exception:
            pass
    return float(get_lucko_setting('default_commission_pct', '5.0'))


def set_game_setting(game_id: str, field: str, value):
    try:
        gs = json.loads(get_lucko_setting('game_settings', '{}'))
    except Exception:
        gs = {}
    if game_id not in gs:
        gs[game_id] = {}
    gs[game_id][field] = value
    set_lucko_setting('game_settings', json.dumps(gs))


def is_game_enabled(game_id: str) -> bool:
    try:
        gs = json.loads(get_lucko_setting('game_settings', '{}'))
        return gs.get(game_id, {}).get('enabled', True)
    except Exception:
        return True


# ── Member management ─────────────────────────────────────────────────────────

def ensure_member(telegram_id: int) -> Optional[str]:
    """Return Lucko member ID for this user, registering if necessary."""
    row = _execute_with_retry(
        "SELECT lucko_member_id FROM lucko_members WHERE telegram_id = %s",
        (telegram_id,), fetch_one=True
    )
    if row:
        return row['lucko_member_id']

    lucko_id = f"onichan_{telegram_id}"
    res = _api.create_member(lucko_id, str(telegram_id))
    if res.get('code') not in (0, None):
        code = res.get('code')
        # Code for "already exists" varies — treat non-fatal codes as success
        if code not in (-1, -2, -3):
            pass  # likely already created — still store it
        else:
            logger.warning(f"[lucko] create_member failed for {telegram_id}: {res}")
            return None

    _execute_with_retry("""
        INSERT INTO lucko_members (telegram_id, lucko_member_id)
        VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING
    """, (telegram_id, lucko_id))
    return lucko_id


# ── Transfer operations ───────────────────────────────────────────────────────

def buy_in(telegram_id: int, credits: float, game_id: str = '') -> Dict[str, Any]:
    """
    Deduct credits from bot wallet, transfer to Lucko wallet.
    Returns {'ok': True, 'order_id': ..., 'lucko_balance': ...}
    or      {'ok': False, 'error': '...'}
    """
    credits = round(float(credits), 2)
    min_b = float(get_lucko_setting('min_buyin', '1.00'))
    max_b = float(get_lucko_setting('max_buyin', '500.00'))

    if credits < min_b:
        return {'ok': False, 'error': f'Minimum buy-in is ${min_b:.2f}'}
    if credits > max_b:
        return {'ok': False, 'error': f'Maximum buy-in is ${max_b:.2f}'}

    bot_balance = get_user_balance(telegram_id)
    if bot_balance < credits:
        return {'ok': False, 'error': f'Insufficient balance (have ${bot_balance:.2f}, need ${credits:.2f})'}

    lucko_id = ensure_member(telegram_id)
    if not lucko_id:
        return {'ok': False, 'error': 'Failed to register Lucko account'}

    order_id = f"bi_{telegram_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

    # Deduct from bot wallet first (optimistic)
    add_user_balance(telegram_id, -credits)

    # Record pending transfer
    _execute_with_retry("""
        INSERT INTO lucko_transfers
            (telegram_id, direction, credits_bot, credits_lucko, game_id, order_id, status)
        VALUES (%s, 'in', %s, %s, %s, %s, 'pending')
    """, (telegram_id, credits, credits, game_id, order_id))

    # Call Lucko API
    res = _api.transfer_in(lucko_id, credits, order_id)
    if res.get('code') == 0:
        _execute_with_retry(
            "UPDATE lucko_transfers SET status='completed' WHERE order_id=%s", (order_id,)
        )
        lucko_bal = _api.get_member_balance(lucko_id) or credits
        return {'ok': True, 'order_id': order_id, 'lucko_balance': lucko_bal}
    else:
        # Refund on failure
        add_user_balance(telegram_id, credits)
        _execute_with_retry("""
            UPDATE lucko_transfers SET status='failed', error_msg=%s WHERE order_id=%s
        """, (res.get('msg', 'API error'), order_id))
        return {'ok': False, 'error': res.get('msg', 'Transfer failed')}


def cash_out(telegram_id: int, game_id: str = '') -> Dict[str, Any]:
    """
    Sweep Lucko balance back to bot wallet, applying commission on winnings.
    Returns {'ok': True, 'credits_back': ..., 'commission': ..., 'commission_pct': ...}
    or      {'ok': False, 'error': '...'}
    """
    lucko_id = ensure_member(telegram_id)
    if not lucko_id:
        return {'ok': False, 'error': 'No Lucko account found'}

    lucko_bal = _api.get_member_balance(lucko_id)
    if lucko_bal is None:
        return {'ok': False, 'error': 'Could not fetch Lucko balance'}

    if lucko_bal < _MIN_BALANCE_TO_SWEEP:
        return {'ok': True, 'credits_back': 0.0, 'commission': 0.0, 'commission_pct': 0.0}

    commission_pct = get_commission_pct(game_id)
    gross = Decimal(str(lucko_bal))
    commission_amt = (gross * Decimal(str(commission_pct)) / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_DOWN
    )
    net = (gross - commission_amt).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    net_f = float(net)
    comm_f = float(commission_amt)

    order_id = f"bo_{telegram_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

    _execute_with_retry("""
        INSERT INTO lucko_transfers
            (telegram_id, direction, credits_bot, credits_lucko, commission_pct,
             commission_amount, game_id, order_id, status)
        VALUES (%s, 'out', %s, %s, %s, %s, %s, %s, 'pending')
    """, (telegram_id, net_f, float(lucko_bal), commission_pct, comm_f, game_id, order_id))

    res = _api.transfer_out_all(lucko_id, order_id)
    if res.get('code') == 0:
        add_user_balance(telegram_id, net_f)
        _execute_with_retry(
            "UPDATE lucko_transfers SET status='completed' WHERE order_id=%s", (order_id,)
        )
        return {
            'ok': True,
            'credits_back': net_f,
            'commission': comm_f,
            'commission_pct': commission_pct,
            'lucko_gross': float(lucko_bal),
        }
    else:
        _execute_with_retry("""
            UPDATE lucko_transfers SET status='failed', error_msg=%s WHERE order_id=%s
        """, (res.get('msg', 'API error'), order_id))
        return {'ok': False, 'error': res.get('msg', 'Transfer out failed')}


# ── Game URL helper ───────────────────────────────────────────────────────────

def get_game_url(telegram_id: int, game_id: str, return_url: str = '') -> Dict[str, Any]:
    """Ensure member exists and return the playable launch URL."""
    lucko_id = ensure_member(telegram_id)
    if not lucko_id:
        return {'ok': False, 'error': 'Failed to create Lucko account'}
    res = _api.get_game_url(game_id, lucko_id, return_url=return_url)
    if res.get('code') == 0:
        url = (res.get('data') or {}).get('url', '')
        return {'ok': True, 'url': url}
    return {'ok': False, 'error': res.get('msg', 'Could not get game URL')}


# ── Admin helpers ─────────────────────────────────────────────────────────────

def get_recent_transfers(limit: int = 50):
    return _execute_with_retry("""
        SELECT lt.*, lm.lucko_member_id
        FROM lucko_transfers lt
        LEFT JOIN lucko_members lm ON lm.telegram_id = lt.telegram_id
        ORDER BY lt.created_at DESC LIMIT %s
    """, (limit,), fetch=True) or []


def get_total_lucko_credits() -> float:
    """Sum of all pending bot-side debits (credits still in play)."""
    row = _execute_with_retry("""
        SELECT COALESCE(SUM(credits_lucko), 0) as total
        FROM lucko_transfers
        WHERE direction='in' AND status='completed'
          AND id NOT IN (
              SELECT t2.id FROM lucko_transfers t2
              WHERE t2.telegram_id = lucko_transfers.telegram_id
                AND t2.direction='out' AND t2.status='completed'
                AND t2.created_at > lucko_transfers.created_at
          )
    """, fetch_one=True)
    if row:
        try:
            return float(row['total'])
        except Exception:
            return 0.0
    return 0.0


def sweep_all_members() -> Dict[str, Any]:
    """Force cash-out for every member that has a Lucko balance > 0."""
    members = _execute_with_retry(
        "SELECT telegram_id, lucko_member_id FROM lucko_members", fetch=True
    ) or []
    swept = 0
    errors = 0
    total_back = 0.0
    for m in members:
        tid = m['telegram_id']
        bal = _api.get_member_balance(m['lucko_member_id'])
        if bal and bal >= _MIN_BALANCE_TO_SWEEP:
            res = cash_out(tid)
            if res.get('ok'):
                swept += 1
                total_back += res.get('credits_back', 0)
            else:
                errors += 1
    return {'swept': swept, 'errors': errors, 'total_back': round(total_back, 2)}


# ── Idle-sweep background thread ──────────────────────────────────────────────

def _idle_sweep_loop():
    while True:
        try:
            time.sleep(_SWEEP_INTERVAL)
            if not is_enabled() or not _api.is_configured():
                continue
            # Find members with unclosed sessions older than idle threshold
            rows = _execute_with_retry("""
                SELECT DISTINCT telegram_id FROM lucko_transfers
                WHERE direction='in' AND status='completed'
                  AND created_at < NOW() - INTERVAL '%s seconds'
                  AND telegram_id NOT IN (
                      SELECT telegram_id FROM lucko_transfers
                      WHERE direction='out' AND status='completed'
                        AND created_at > NOW() - INTERVAL '%s seconds'
                  )
            """, (_IDLE_THRESHOLD, _IDLE_THRESHOLD), fetch=True) or []
            for r in rows:
                tid = r['telegram_id']
                lucko_id = ensure_member(tid)
                if not lucko_id:
                    continue
                bal = _api.get_member_balance(lucko_id)
                if bal and bal >= _MIN_BALANCE_TO_SWEEP:
                    cash_out(tid)
        except Exception as e:
            logger.warning(f"[lucko_sweep] {e}")


def start_idle_sweep():
    t = threading.Thread(target=_idle_sweep_loop, name='lucko-idle-sweep', daemon=True)
    t.start()
