"""
Lucko.ai Wallet Bridge
- Maps bot telegram_id → Lucko user_id
- Handles deposit/withdraw with commission
- Caches guest session tokens for game URL generation
- Background idle-sweep returns stale balances
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

_SWEEP_INTERVAL   = 300    # seconds between idle-sweep runs
_IDLE_THRESHOLD   = 1800   # consider session idle after 30 min
_MIN_SWEEP        = 0.01   # ignore dust below this amount

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_lucko_tables():
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS lucko_members (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            lucko_user_id VARCHAR(100) NOT NULL,
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
            txn_id VARCHAR(150) UNIQUE,
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
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_lucko_tf_user   ON lucko_transfers(telegram_id, created_at DESC)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_lucko_tf_status ON lucko_transfers(status, created_at)")

    defaults = {
        'enabled':              'false',
        'default_commission_pct': '5.0',
        'min_buyin':            '1.00',
        'max_buyin':            '500.00',
        'default_buyin':        '10.00',
        'game_settings':        '{}',
    }
    for k, v in defaults.items():
        _execute_with_retry("""
            INSERT INTO lucko_settings (key, value, updated_at)
            VALUES (%s, %s, NOW()) ON CONFLICT (key) DO NOTHING
        """, (k, v))


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = '') -> str:
    row = _execute_with_retry(
        "SELECT value FROM lucko_settings WHERE key = %s", (key,), fetch_one=True
    )
    return (row['value'] if row else None) or default


def set_setting(key: str, value: str):
    _execute_with_retry("""
        INSERT INTO lucko_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, str(value)))


def is_enabled() -> bool:
    return get_setting('enabled', 'false').lower() == 'true'


def get_commission_pct(game_id: str = '') -> float:
    if game_id:
        try:
            gs = json.loads(get_setting('game_settings', '{}'))
            pct = gs.get(game_id, {}).get('commission_pct')
            if pct is not None:
                return float(pct)
        except Exception:
            pass
    return float(get_setting('default_commission_pct', '5.0'))


def set_game_setting(game_id: str, field: str, value):
    try:
        gs = json.loads(get_setting('game_settings', '{}'))
    except Exception:
        gs = {}
    gs.setdefault(game_id, {})[field] = value
    set_setting('game_settings', json.dumps(gs))


def is_game_enabled(game_id: str) -> bool:
    try:
        gs = json.loads(get_setting('game_settings', '{}'))
        return gs.get(game_id, {}).get('enabled', True)
    except Exception:
        return True


# ── Member management ─────────────────────────────────────────────────────────

def _lucko_uid(telegram_id: int) -> str:
    """Deterministic Lucko user_id for a Telegram user."""
    return f"onichan_{telegram_id}"


def ensure_member(telegram_id: int) -> Optional[str]:
    """Return Lucko user_id for this user, registering if necessary."""
    row = _execute_with_retry(
        "SELECT lucko_user_id FROM lucko_members WHERE telegram_id = %s",
        (telegram_id,), fetch_one=True
    )
    if row:
        return row['lucko_user_id']

    lucko_uid = _lucko_uid(telegram_id)
    res = _api.create_member(lucko_uid, str(telegram_id))
    # code 200 = created, 700102 = already exists — both are fine
    if res.get('code') not in (200, 700102):
        logger.warning(f"[lucko] create_member failed for {telegram_id}: {res}")
        return None

    _execute_with_retry("""
        INSERT INTO lucko_members (telegram_id, lucko_user_id)
        VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING
    """, (telegram_id, lucko_uid))
    return lucko_uid


# ── Token / game URL ──────────────────────────────────────────────────────────

# Short-lived in-memory token cache {lucko_uid: (token, expiry_ts)}
_token_cache: Dict[str, tuple] = {}
_token_lock = threading.Lock()
_TOKEN_TTL = 3000  # seconds (~50 min; tokens expire around 60 min)


def _get_session_token(lucko_uid: str) -> Optional[str]:
    """
    Get a valid session token for this user.
    Flow: guest/login → token → member/login → personalised token.
    """
    with _token_lock:
        cached = _token_cache.get(lucko_uid)
        if cached and time.time() < cached[1]:
            return cached[0]

    # 1. Acquire a guest token
    g = _api.guest_login('web')
    if g.get('code') != 200:
        logger.warning(f"[lucko] guest_login failed: {g}")
        return None
    guest_token = (g.get('data') or {}).get('token', '')
    if not guest_token:
        return None

    # 2. Exchange for a member-specific token (no inst_id = lobby URL)
    uid_part = lucko_uid  # e.g. onichan_12345
    m = _api.member_login(uid_part, guest_token, 'web')
    if m.get('code') != 200:
        logger.warning(f"[lucko] member_login failed for {lucko_uid}: {m}")
        return None
    member_token = (m.get('data') or {}).get('token', '')
    if not member_token:
        return None

    with _token_lock:
        _token_cache[lucko_uid] = (member_token, time.time() + _TOKEN_TTL)
    return member_token


def get_lobby_url(telegram_id: int, inst_id: str = '') -> Dict[str, Any]:
    """
    Return the playable game URL for this user.
    inst_id is appended as a query param to deep-link into a specific room.
    """
    lucko_uid = ensure_member(telegram_id)
    if not lucko_uid:
        return {'ok': False, 'error': 'Failed to register Lucko account'}

    token = _get_session_token(lucko_uid)
    if not token:
        return {'ok': False, 'error': 'Could not obtain session token'}

    # member/login returns a lobby URL — append inst_id to open specific room
    res = _api.member_login(lucko_uid, token, 'web')
    if res.get('code') != 200:
        # Token may have expired — invalidate and retry once
        with _token_lock:
            _token_cache.pop(lucko_uid, None)
        token = _get_session_token(lucko_uid)
        if not token:
            return {'ok': False, 'error': 'Session token refresh failed'}
        res = _api.member_login(lucko_uid, token, 'web')

    if res.get('code') != 200:
        return {'ok': False, 'error': res.get('message', 'Login failed')}

    url = (res.get('data') or {}).get('url', '')
    new_token = (res.get('data') or {}).get('token', token)
    with _token_lock:
        _token_cache[lucko_uid] = (new_token, time.time() + _TOKEN_TTL)

    # Append inst_id to deep-link into a specific game room
    if inst_id and url:
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}inst_id={inst_id}"

    return {'ok': True, 'url': url}


# ── Wallet operations ─────────────────────────────────────────────────────────

# ── Active session tracking ───────────────────────────────────────────────────
# Maps telegram_id → {'inst_id': str, 'buyin_txn_id': str, 'ts': float}
# Written at buy-in; read/cleared at cashout.  Never trust client-supplied
# inst_id for commission lookups — always pull from this server-side record.

_active_sessions: Dict[int, Dict[str, Any]] = {}
_session_lock = threading.Lock()


def _set_active_session(telegram_id: int, inst_id: str, buyin_txn_id: str):
    with _session_lock:
        _active_sessions[telegram_id] = {
            'inst_id':      inst_id,
            'buyin_txn_id': buyin_txn_id,
            'ts':           time.time(),
        }


def _get_active_session(telegram_id: int) -> Optional[Dict[str, Any]]:
    with _session_lock:
        return _active_sessions.get(telegram_id)


def _clear_active_session(telegram_id: int):
    with _session_lock:
        _active_sessions.pop(telegram_id, None)


def buy_in(telegram_id: int, credits: float, game_id: str = '') -> Dict[str, Any]:
    """
    Deduct credits from bot wallet → transfer to Lucko wallet.
    Records inst_id in the server-side active session so cashout always
    uses the correct commission — never trusting client-supplied inst_id.
    Returns {'ok': True, 'txn_id': ..., 'lucko_balance': ...}
    """
    credits = round(float(credits), 2)
    min_b = float(get_setting('min_buyin', '1.00'))
    max_b = float(get_setting('max_buyin', '500.00'))

    if credits < min_b:
        return {'ok': False, 'error': f'Minimum buy-in is ${min_b:.2f}'}
    if credits > max_b:
        return {'ok': False, 'error': f'Maximum buy-in is ${max_b:.2f}'}

    bot_balance = get_user_balance(telegram_id)
    if bot_balance < credits:
        return {'ok': False, 'error': f'Insufficient balance (have ${bot_balance:.2f})'}

    lucko_uid = ensure_member(telegram_id)
    if not lucko_uid:
        return {'ok': False, 'error': 'Failed to register Lucko account'}

    txn_id = f"bi_{telegram_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

    # Deduct first (optimistic)
    add_user_balance(telegram_id, -credits)

    # Log pending
    _execute_with_retry("""
        INSERT INTO lucko_transfers (telegram_id, direction, credits_bot, credits_lucko, game_id, txn_id, status)
        VALUES (%s, 'in', %s, %s, %s, %s, 'pending')
    """, (telegram_id, credits, credits, game_id, txn_id))

    res = _api.deposit(lucko_uid, credits, txn_id)
    if res.get('code') == 200:
        _execute_with_retry("UPDATE lucko_transfers SET status='completed' WHERE txn_id=%s", (txn_id,))
        lucko_bal = _api.get_balance(lucko_uid) or credits
        # Record server-side session AFTER successful deposit so commission
        # policy is bound to this specific inst_id and cannot be overridden.
        _set_active_session(telegram_id, game_id, txn_id)
        return {'ok': True, 'txn_id': txn_id, 'lucko_balance': lucko_bal}
    else:
        # Refund
        add_user_balance(telegram_id, credits)
        _execute_with_retry("""
            UPDATE lucko_transfers SET status='failed', error_msg=%s WHERE txn_id=%s
        """, (res.get('message', 'API error'), txn_id))
        return {'ok': False, 'error': res.get('message', 'Deposit failed')}


def rollback_buy_in(telegram_id: int) -> Dict[str, Any]:
    """
    Zero-commission reversal used when a game URL could not be obtained
    immediately after a successful buy-in.  Withdraws the full Lucko balance
    back to the bot wallet WITHOUT charging any commission.
    Clears the active session on success.
    """
    lucko_uid = ensure_member(telegram_id)
    if not lucko_uid:
        return {'ok': False, 'error': 'No Lucko account found'}

    lucko_bal = _api.get_balance(lucko_uid)
    if lucko_bal is None:
        return {'ok': False, 'error': 'Could not fetch Lucko balance for rollback'}

    if lucko_bal < _MIN_SWEEP:
        _clear_active_session(telegram_id)
        return {'ok': True, 'credits_back': 0.0, 'commission': 0.0}

    txn_id = f"rb_{telegram_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

    _execute_with_retry("""
        INSERT INTO lucko_transfers
            (telegram_id, direction, credits_bot, credits_lucko,
             commission_pct, commission_amount, game_id, txn_id, status)
        VALUES (%s, 'out', %s, %s, 0, 0, 'ROLLBACK', %s, 'pending')
    """, (telegram_id, float(lucko_bal), float(lucko_bal), txn_id))

    res = _api.withdraw(lucko_uid, float(lucko_bal), txn_id)
    if res.get('code') == 200:
        add_user_balance(telegram_id, float(lucko_bal))
        _execute_with_retry("UPDATE lucko_transfers SET status='completed' WHERE txn_id=%s", (txn_id,))
        _clear_active_session(telegram_id)
        logger.info(f"[lucko] rollback_buy_in: refunded {lucko_bal} to {telegram_id} (no commission)")
        return {'ok': True, 'credits_back': float(lucko_bal), 'commission': 0.0}
    else:
        _execute_with_retry("""
            UPDATE lucko_transfers SET status='failed', error_msg=%s WHERE txn_id=%s
        """, (res.get('message', 'API error'), txn_id))
        return {'ok': False, 'error': res.get('message', 'Rollback withdraw failed')}


def cash_out(telegram_id: int) -> Dict[str, Any]:
    """
    Sweep Lucko wallet → bot wallet minus commission.
    The commission rate is determined by the inst_id recorded server-side at
    buy-in time (_active_sessions).  The client cannot influence the commission
    by supplying a different inst_id — that parameter is intentionally removed.
    Returns {'ok': True, 'credits_back': ..., 'commission': ..., 'commission_pct': ...}
    """
    lucko_uid = ensure_member(telegram_id)
    if not lucko_uid:
        return {'ok': False, 'error': 'No Lucko account found'}

    lucko_bal = _api.get_balance(lucko_uid)
    if lucko_bal is None:
        return {'ok': False, 'error': 'Could not fetch Lucko balance'}

    if lucko_bal < _MIN_SWEEP:
        _clear_active_session(telegram_id)
        return {'ok': True, 'credits_back': 0.0, 'commission': 0.0, 'commission_pct': 0.0, 'lucko_gross': 0.0}

    # Pull inst_id from the server-side session — never from client input.
    session_info = _get_active_session(telegram_id)
    game_id = session_info['inst_id'] if session_info else ''

    commission_pct = get_commission_pct(game_id)
    gross = Decimal(str(lucko_bal))
    commission_amt = (gross * Decimal(str(commission_pct)) / Decimal('100')).quantize(
        Decimal('0.01'), rounding=ROUND_DOWN
    )
    net = (gross - commission_amt).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    net_f   = float(net)
    comm_f  = float(commission_amt)

    txn_id = f"bo_{telegram_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

    _execute_with_retry("""
        INSERT INTO lucko_transfers
            (telegram_id, direction, credits_bot, credits_lucko, commission_pct, commission_amount, game_id, txn_id, status)
        VALUES (%s, 'out', %s, %s, %s, %s, %s, %s, 'pending')
    """, (telegram_id, net_f, float(lucko_bal), commission_pct, comm_f, game_id, txn_id))

    res = _api.withdraw(lucko_uid, float(lucko_bal), txn_id)
    if res.get('code') == 200:
        add_user_balance(telegram_id, net_f)
        _execute_with_retry("UPDATE lucko_transfers SET status='completed' WHERE txn_id=%s", (txn_id,))
        _clear_active_session(telegram_id)
        return {
            'ok': True,
            'credits_back':   net_f,
            'commission':     comm_f,
            'commission_pct': commission_pct,
            'lucko_gross':    float(lucko_bal),
        }
    else:
        _execute_with_retry("""
            UPDATE lucko_transfers SET status='failed', error_msg=%s WHERE txn_id=%s
        """, (res.get('message', 'API error'), txn_id))
        return {'ok': False, 'error': res.get('message', 'Withdraw failed')}


# ── Admin helpers ─────────────────────────────────────────────────────────────

def get_recent_transfers(limit: int = 50):
    return _execute_with_retry("""
        SELECT lt.*, lm.lucko_user_id
        FROM lucko_transfers lt
        LEFT JOIN lucko_members lm ON lm.telegram_id = lt.telegram_id
        ORDER BY lt.created_at DESC LIMIT %s
    """, (limit,), fetch=True) or []


def sweep_all_members() -> Dict[str, Any]:
    members = _execute_with_retry(
        "SELECT telegram_id, lucko_user_id FROM lucko_members", fetch=True
    ) or []
    swept = errors = 0
    total_back = 0.0
    for m in members:
        tid = m['telegram_id']
        bal = _api.get_balance(m['lucko_user_id'])
        if bal and bal >= _MIN_SWEEP:
            res = cash_out(tid)
            if res.get('ok'):
                swept += 1
                total_back += res.get('credits_back', 0)
            else:
                errors += 1
    return {'swept': swept, 'errors': errors, 'total_back': round(total_back, 2)}


# ── Game list cache ───────────────────────────────────────────────────────────

_game_cache: Dict = {'rooms': [], 'fetched_at': 0}
_CACHE_TTL = 3600

_GAME_ID_NAMES = {
    '101': 'Baccarat', '102': 'Dragon Tiger', '103': 'Roulette',
    '104': 'Live Baccarat', '105': 'Blackjack', '109': 'Lottery',
    '112': 'Lucky Lace', '113': 'Lightning Baccarat', '114': 'Matching Lace',
    '115': 'Sic Bo', '116': 'Goal', '117': 'Football Goddess',
    '118': 'Football Goddess Lite', '20102': 'Space Crash', '20103': 'Surf Crash',
}

_GAME_ID_TYPES = {
    '101': 'live', '102': 'live', '103': 'live', '104': 'live',
    '105': 'live', '112': 'live', '113': 'live', '114': 'live',
    '115': 'live', '116': 'live', '117': 'live', '118': 'live',
    '109': 'lottery', '20102': 'crash', '20103': 'crash',
}


def get_cached_rooms(force: bool = False):
    """Return flat list of all game rooms from API, cached for 1 hour."""
    now = time.time()
    if not force and _game_cache['rooms'] and (now - _game_cache['fetched_at']) < _CACHE_TTL:
        return _game_cache['rooms']
    return refresh_game_cache()


def refresh_game_cache():
    res = _api.get_game_list()
    if res.get('code') != 200:
        return _game_cache['rooms']

    raw = (res.get('data') or {}).get('list', [])
    rooms = []
    try:
        gs = json.loads(get_setting('game_settings', '{}'))
    except Exception:
        gs = {}

    for category in raw:
        gid     = str(category.get('game_id', ''))
        gnames  = category.get('game_name', {})
        gname   = gnames.get('en-US') or gnames.get('zh-CN') or _GAME_ID_NAMES.get(gid, f'Game {gid}')
        gtype   = _GAME_ID_TYPES.get(gid, 'live')

        for room in category.get('rooms', []):
            inst_id = room.get('inst_id', '')
            if not inst_id:
                continue
            rnames  = room.get('inst_name', {})
            rname   = rnames.get('en-US') or rnames.get('zh-CN') or gname
            cover   = room.get('cover') or room.get('cover_thumbnail') or ''

            gsettings = gs.get(inst_id, {})
            rooms.append({
                'inst_id':      inst_id,
                'game_id':      gid,
                'name':         f"{gname} — {rname}" if rname != gname else gname,
                'game_name':    gname,
                'room_name':    rname,
                'game_type':    gtype,
                'cover':        cover,
                'enabled':      gsettings.get('enabled', True),
                'commission_pct': gsettings.get('commission_pct', float(get_setting('default_commission_pct', '5.0'))),
            })

    _game_cache['rooms']      = rooms
    _game_cache['fetched_at'] = time.time()
    return rooms


# ── Idle-sweep background thread ──────────────────────────────────────────────

def _idle_sweep_loop():
    while True:
        try:
            time.sleep(_SWEEP_INTERVAL)
            if not is_enabled() or not _api.is_configured():
                continue
            rows = _execute_with_retry("""
                SELECT DISTINCT t.telegram_id FROM lucko_transfers t
                WHERE t.direction='in' AND t.status='completed'
                  AND t.created_at < NOW() - INTERVAL '1800 seconds'
                  AND NOT EXISTS (
                      SELECT 1 FROM lucko_transfers t2
                      WHERE t2.telegram_id = t.telegram_id
                        AND t2.direction = 'out' AND t2.status = 'completed'
                        AND t2.created_at > t.created_at
                  )
            """, fetch=True) or []
            for r in rows:
                tid = r['telegram_id']
                lucko_uid = ensure_member(tid)
                if not lucko_uid:
                    continue
                bal = _api.get_balance(lucko_uid)
                if bal and bal >= _MIN_SWEEP:
                    cash_out(tid)
        except Exception as e:
            logger.warning(f"[lucko_sweep] {e}")


def start_idle_sweep():
    t = threading.Thread(target=_idle_sweep_loop, name='lucko-idle-sweep', daemon=True)
    t.start()
