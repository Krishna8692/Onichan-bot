import secrets
import random
import hashlib
import time
import json
import threading
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from modules.database import _execute_with_retry

_secure_rng = random.SystemRandom()

# ── Settings cache ─────────────────────────────────────────────────────────────
# Bulk-loads ALL casino_settings rows in one query and caches for a short TTL.
# Eliminates the N×DB-roundtrip pattern caused by calling get_setting() per game.
_settings_cache: dict = {}
_settings_cache_ts: float = 0.0
_settings_cache_ttl: float = 5.0   # seconds
_settings_cache_lock = threading.Lock()


def _load_settings_bulk() -> dict:
    rows = _execute_with_retry("SELECT key, value FROM casino_settings", fetch=True) or []
    return {r['key']: r['value'] for r in rows}


def _get_settings_cache() -> dict:
    global _settings_cache, _settings_cache_ts
    now = time.monotonic()
    with _settings_cache_lock:
        if now - _settings_cache_ts < _settings_cache_ttl and _settings_cache:
            return _settings_cache
    fresh = _load_settings_bulk()
    with _settings_cache_lock:
        _settings_cache = fresh
        _settings_cache_ts = time.monotonic()
    return fresh


def _invalidate_settings_cache():
    global _settings_cache_ts
    with _settings_cache_lock:
        _settings_cache_ts = 0.0


GAMES = [
    'head_tail', 'rock_paper_scissors', 'spin_wheel', 'number_guess',
    'dice_rolling', 'card_finding', 'number_slot', 'number_pool',
    'roulette', 'casino_dice', 'keno', 'blackjack', 'mines',
    'poker', 'color_prediction', 'crazy_times', 'dream_catcher',
    'andar_bahar', 'pai_gow_poker', 'crash',
]

GAME_META = {
    'head_tail': {'name': 'Head & Tail', 'icon': '🪙', 'win': 95},
    'rock_paper_scissors': {'name': 'Rock Paper Scissors', 'icon': '✊', 'win': 90},
    'spin_wheel': {'name': 'Spin Wheel', 'icon': '🎡', 'win': 90},
    'number_guess': {'name': 'Number Guess', 'icon': '🔢', 'win': 85},
    'dice_rolling': {'name': 'Dice Rolling', 'icon': '🎲', 'win': 90},
    'card_finding': {'name': 'Card Finding', 'icon': '🃏', 'win': 85},
    'number_slot': {'name': 'Number Slot', 'icon': '🎰', 'win': 80},
    'number_pool': {'name': 'Number Pool', 'icon': '🎱', 'win': 85},
    'roulette': {'name': 'Roulette', 'icon': '🎡', 'win': 95},
    'casino_dice': {'name': 'Casino Dice', 'icon': '🎲', 'win': 90},
    'keno': {'name': 'Keno', 'icon': '🔢', 'win': 80},
    'blackjack': {'name': 'Blackjack', 'icon': '🃏', 'win': 90},
    'mines': {'name': 'Mines', 'icon': '💣', 'win': 85},
    'poker': {'name': 'Video Poker', 'icon': '♠️', 'win': 90},
    'color_prediction': {'name': 'Color Prediction', 'icon': '🎨', 'win': 85},
    'crazy_times': {'name': 'Crazy Times', 'icon': '🤪', 'win': 80},
    'dream_catcher': {'name': 'Dream Catcher', 'icon': '🌙', 'win': 85},
    'andar_bahar': {'name': 'Andar Bahar', 'icon': '🎴', 'win': 90},
    'pai_gow_poker': {'name': 'Pai Gow Poker', 'icon': '🀄', 'win': 85},
    'crash': {'name': 'Crash', 'icon': '🚀', 'win': 97},
}

DEFAULT_HOUSE_EDGES = {g: 100 - GAME_META[g]['win'] for g in GAMES}

DEFAULT_SETTINGS = {
    'enabled': True,
    'daily_free_amount': 5.00,
    'daily_free_enabled': True,
    'daily_free_max_win': 20.00,
    'min_bet': 0.10,
    'max_bet': 100.00,
}


def _init_casino_tables():
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_bets (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            game VARCHAR(20) NOT NULL,
            bet_amount DECIMAL(10,2) NOT NULL,
            win_amount DECIMAL(10,2) DEFAULT 0,
            profit DECIMAL(10,2) DEFAULT 0,
            result TEXT DEFAULT '',
            details JSONB DEFAULT '{}',
            is_free_play BOOLEAN DEFAULT FALSE,
            server_seed VARCHAR(64) DEFAULT '',
            seed_hash VARCHAR(64) DEFAULT '',
            client_nonce INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_settings (
            key VARCHAR(50) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_daily_claims (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            claimed_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_sessions (
            session_id VARCHAR(24) PRIMARY KEY,
            user_id BIGINT NOT NULL,
            game VARCHAR(20) NOT NULL,
            bet DECIMAL(10,2) NOT NULL,
            is_free BOOLEAN DEFAULT FALSE,
            state JSONB NOT NULL DEFAULT '{}',
            server_seed VARCHAR(64) DEFAULT '',
            seed_hash VARCHAR(64) DEFAULT '',
            client_nonce INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("ALTER TABLE casino_bets ADD COLUMN IF NOT EXISTS server_seed VARCHAR(64) DEFAULT ''")
    _execute_with_retry("ALTER TABLE casino_bets ADD COLUMN IF NOT EXISTS seed_hash VARCHAR(64) DEFAULT ''")
    _execute_with_retry("ALTER TABLE casino_bets ADD COLUMN IF NOT EXISTS client_nonce INTEGER DEFAULT 0")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_bets_user ON casino_bets(user_id)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_bets_game ON casino_bets(game)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_daily_user ON casino_daily_claims(user_id, claimed_at)")
    _execute_with_retry("CREATE UNIQUE INDEX IF NOT EXISTS idx_casino_daily_unique ON casino_daily_claims(user_id, (claimed_at::date))")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_sessions_user ON casino_sessions(user_id)")

    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_achievements (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            achievement_id VARCHAR(50) NOT NULL,
            unlocked_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, achievement_id)
        )
    """)
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_achievements_user ON casino_achievements(user_id)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_bets_created ON casino_bets(created_at)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_bets_user_result ON casino_bets(user_id, result)")

    _execute_with_retry("""
        CREATE TABLE IF NOT EXISTS casino_leaderboard_rewards (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            period VARCHAR(10) NOT NULL,
            period_label VARCHAR(50) NOT NULL,
            rank INTEGER NOT NULL,
            reward_amount DECIMAL(10,2) NOT NULL,
            paid_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_lb_rewards_user ON casino_leaderboard_rewards(user_id)")
    _execute_with_retry("CREATE INDEX IF NOT EXISTS idx_casino_lb_rewards_period ON casino_leaderboard_rewards(period, period_label)")


ACHIEVEMENT_DEFS = {
    'first_win': {
        'name': 'First Win',
        'icon': '🏆',
        'description': 'Win your first casino bet',
    },
    'high_roller': {
        'name': 'High Roller',
        'icon': '💸',
        'description': 'Place a bet of $50 or more',
    },
    'jackpot_winner': {
        'name': 'Jackpot Winner',
        'icon': '💎',
        'description': 'Win 10x or more on a single bet',
    },
    'bet_100': {
        'name': 'Centurion',
        'icon': '🎖️',
        'description': 'Place 100 total bets',
    },
    'bet_500': {
        'name': 'Veteran Gambler',
        'icon': '🎗️',
        'description': 'Place 500 total bets',
    },
    'bet_1000': {
        'name': 'Casino Legend',
        'icon': '👑',
        'description': 'Place 1,000 total bets',
    },
    'win_streak_5': {
        'name': 'Hot Streak',
        'icon': '🔥',
        'description': 'Win 5 bets in a row',
    },
    'win_streak_10': {
        'name': 'Unstoppable',
        'icon': '⚡',
        'description': 'Win 10 bets in a row',
    },
    'big_winner_100': {
        'name': 'Big Winner',
        'icon': '💰',
        'description': 'Win $100 or more in a single bet',
    },
    'big_winner_500': {
        'name': 'Mega Winner',
        'icon': '🤑',
        'description': 'Win $500 or more in a single bet',
    },
    'all_games': {
        'name': 'Jack of All Trades',
        'icon': '🎮',
        'description': 'Play all 19 casino games',
    },
    'daily_collector': {
        'name': 'Daily Collector',
        'icon': '📅',
        'description': 'Claim daily free credits 7 times',
    },
    'profit_100': {
        'name': 'In the Green',
        'icon': '📈',
        'description': 'Reach $100 in total net winnings',
    },
    'slots_master': {
        'name': 'Slots Master',
        'icon': '🎰',
        'description': 'Win 50 times on Number Slot',
    },
    'blackjack_pro': {
        'name': 'Blackjack Pro',
        'icon': '🃏',
        'description': 'Get a natural blackjack 5 times',
    },
    'weekly_champion': {
        'name': 'Weekly Champion',
        'icon': '🏅',
        'description': 'Reach #1 on the weekly leaderboard',
    },
    'monthly_champion': {
        'name': 'Monthly Champion',
        'icon': '🏆',
        'description': 'Reach #1 on the monthly leaderboard',
    },
}


def get_user_achievements(user_id):
    rows = _execute_with_retry(
        "SELECT achievement_id, unlocked_at FROM casino_achievements WHERE user_id = %s ORDER BY unlocked_at DESC",
        (user_id,), fetch=True
    ) or []
    result = []
    for r in rows:
        aid = r['achievement_id']
        defn = ACHIEVEMENT_DEFS.get(aid, {})
        result.append({
            'id': aid,
            'name': defn.get('name', aid),
            'icon': defn.get('icon', '🏅'),
            'description': defn.get('description', ''),
            'unlocked_at': r['unlocked_at'].strftime('%Y-%m-%d %H:%M') if r.get('unlocked_at') else '',
        })
    return result


def _award_achievement(user_id, achievement_id):
    result = _execute_with_retry("""
        INSERT INTO casino_achievements (user_id, achievement_id, unlocked_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id, achievement_id) DO NOTHING
    """, (user_id, achievement_id), return_rowcount=True)
    return result and result > 0


def check_achievements(user_id, game, bet_amount, win_amount, result_str):
    newly_unlocked = []

    existing = _execute_with_retry(
        "SELECT achievement_id FROM casino_achievements WHERE user_id = %s",
        (user_id,), fetch=True
    ) or []
    existing_ids = {r['achievement_id'] for r in existing}

    def _try_award(aid):
        if aid not in existing_ids:
            if _award_achievement(user_id, aid):
                defn = ACHIEVEMENT_DEFS.get(aid, {})
                newly_unlocked.append({
                    'id': aid,
                    'name': defn.get('name', aid),
                    'icon': defn.get('icon', '🏅'),
                    'description': defn.get('description', ''),
                })

    if result_str in ('win', 'blackjack') and 'first_win' not in existing_ids:
        _try_award('first_win')

    if bet_amount >= 50 and 'high_roller' not in existing_ids:
        _try_award('high_roller')

    if win_amount > 0 and bet_amount > 0:
        multiplier = win_amount / bet_amount
        if multiplier >= 10 and 'jackpot_winner' not in existing_ids:
            _try_award('jackpot_winner')

    if win_amount >= 100 and 'big_winner_100' not in existing_ids:
        _try_award('big_winner_100')
    if win_amount >= 500 and 'big_winner_500' not in existing_ids:
        _try_award('big_winner_500')

    stats = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM casino_bets WHERE user_id = %s AND is_free_play = FALSE",
        (user_id,), fetch_one=True
    ) or {}
    total_bets = int(stats.get('cnt', 0))
    if total_bets >= 100:
        _try_award('bet_100')
    if total_bets >= 500:
        _try_award('bet_500')
    if total_bets >= 1000:
        _try_award('bet_1000')

    if result_str in ('win', 'blackjack'):
        recent = _execute_with_retry(
            "SELECT result FROM casino_bets WHERE user_id = %s AND is_free_play = FALSE ORDER BY created_at DESC LIMIT 10",
            (user_id,), fetch=True
        ) or []
        streak = 0
        for r in recent:
            if r['result'] in ('win', 'blackjack'):
                streak += 1
            else:
                break
        if streak >= 5:
            _try_award('win_streak_5')
        if streak >= 10:
            _try_award('win_streak_10')

    if 'all_games' not in existing_ids:
        games_played = _execute_with_retry(
            "SELECT DISTINCT game FROM casino_bets WHERE user_id = %s",
            (user_id,), fetch=True
        ) or []
        if len(games_played) >= len(GAMES):
            _try_award('all_games')

    if 'profit_100' not in existing_ids:
        net_row = _execute_with_retry(
            "SELECT COALESCE(SUM(win_amount - bet_amount), 0) as net FROM casino_bets WHERE user_id = %s AND is_free_play = FALSE",
            (user_id,), fetch_one=True
        ) or {}
        if float(net_row.get('net', 0)) >= 100:
            _try_award('profit_100')

    if game == 'number_slot' and result_str == 'win' and 'slots_master' not in existing_ids:
        slot_wins = _execute_with_retry(
            "SELECT COUNT(*) as cnt FROM casino_bets WHERE user_id = %s AND game = 'number_slot' AND result = 'win'",
            (user_id,), fetch_one=True
        ) or {}
        if int(slot_wins.get('cnt', 0)) >= 50:
            _try_award('slots_master')

    if result_str == 'blackjack' and 'blackjack_pro' not in existing_ids:
        bj_count = _execute_with_retry(
            "SELECT COUNT(*) as cnt FROM casino_bets WHERE user_id = %s AND game = 'blackjack' AND result = 'blackjack'",
            (user_id,), fetch_one=True
        ) or {}
        if int(bj_count.get('cnt', 0)) >= 5:
            _try_award('blackjack_pro')

    return newly_unlocked


def check_daily_collector_achievement(user_id):
    existing = _execute_with_retry(
        "SELECT 1 FROM casino_achievements WHERE user_id = %s AND achievement_id = 'daily_collector'",
        (user_id,), fetch_one=True
    )
    if existing:
        return None
    claim_count = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM casino_daily_claims WHERE user_id = %s",
        (user_id,), fetch_one=True
    ) or {}
    if int(claim_count.get('cnt', 0)) >= 7:
        if _award_achievement(user_id, 'daily_collector'):
            defn = ACHIEVEMENT_DEFS['daily_collector']
            return {
                'id': 'daily_collector',
                'name': defn['name'],
                'icon': defn['icon'],
                'description': defn['description'],
            }
    return None


def get_achievement_stats():
    rows = _execute_with_retry("""
        SELECT ca.achievement_id, COUNT(*) as unlock_count,
               ARRAY_AGG(DISTINCT CAST(ca.user_id AS TEXT) || ':' || COALESCE(u.username, '')) as unlocked_users
        FROM casino_achievements ca
        LEFT JOIN users u ON ca.user_id = u.user_id
        GROUP BY ca.achievement_id
        ORDER BY unlock_count DESC
    """, fetch=True) or []
    result = []
    for r in rows:
        aid = r['achievement_id']
        defn = ACHIEVEMENT_DEFS.get(aid, {})
        users_list = []
        for entry in (r.get('unlocked_users') or []):
            if entry:
                parts = str(entry).split(':', 1)
                uid = parts[0]
                uname = parts[1] if len(parts) > 1 and parts[1] else None
                users_list.append({'user_id': uid, 'username': uname})
        result.append({
            'id': aid,
            'name': defn.get('name', aid),
            'icon': defn.get('icon', '🏅'),
            'description': defn.get('description', ''),
            'unlock_count': int(r['unlock_count']),
            'unlocked_users': users_list,
        })
    for aid, defn in ACHIEVEMENT_DEFS.items():
        if not any(r['id'] == aid for r in result):
            result.append({
                'id': aid,
                'name': defn.get('name', aid),
                'icon': defn.get('icon', '🏅'),
                'description': defn.get('description', ''),
                'unlock_count': 0,
                'unlocked_users': [],
            })
    return result


def get_username(user_id):
    row = _execute_with_retry(
        "SELECT username FROM users WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    return row['username'] if row and row.get('username') else None


def search_users(query, limit=10):
    if not query or len(query) < 1:
        return []
    rows = _execute_with_retry(
        "SELECT user_id, username FROM users WHERE username ILIKE %s ORDER BY username LIMIT %s",
        (f'%{query}%', limit), fetch=True
    ) or []
    return [{'user_id': str(r['user_id']), 'username': r['username']} for r in rows if r.get('username')]


def get_username_map(user_ids):
    if not user_ids:
        return {}
    placeholders = ','.join(['%s'] * len(user_ids))
    rows = _execute_with_retry(
        f"SELECT user_id, username FROM users WHERE user_id IN ({placeholders})",
        tuple(user_ids), fetch=True
    ) or []
    return {str(r['user_id']): r.get('username') for r in rows}


def get_achievement_unlock_timeline():
    rows = _execute_with_retry("""
        SELECT DATE(unlocked_at) as unlock_date, COUNT(*) as unlock_count
        FROM casino_achievements
        WHERE unlocked_at IS NOT NULL
        GROUP BY DATE(unlocked_at)
        ORDER BY unlock_date ASC
    """, fetch=True) or []
    return [{'date': r['unlock_date'].strftime('%Y-%m-%d'), 'count': int(r['unlock_count'])} for r in rows]


def get_all_bets_for_export():
    rows = _execute_with_retry("""
        SELECT id, user_id, game, bet_amount, win_amount, profit, result,
               is_free_play, created_at
        FROM casino_bets
        ORDER BY created_at DESC
    """, fetch=True) or []
    return rows


def revoke_achievement(user_id, achievement_id):
    if achievement_id not in ACHIEVEMENT_DEFS:
        return False
    result = _execute_with_retry(
        "DELETE FROM casino_achievements WHERE user_id = %s AND achievement_id = %s",
        (user_id, achievement_id), return_rowcount=True
    )
    return result and result > 0


def grant_achievement(user_id, achievement_id):
    if achievement_id not in ACHIEVEMENT_DEFS:
        return False
    return _award_achievement(user_id, achievement_id)


def get_leaderboard(period='all'):
    if period == 'weekly':
        time_filter = "AND cb.created_at >= NOW() - INTERVAL '7 days'"
    elif period == 'monthly':
        time_filter = "AND cb.created_at >= NOW() - INTERVAL '30 days'"
    else:
        time_filter = ""

    rows = _execute_with_retry(f"""
        SELECT cb.user_id,
               COALESCE(u.username, 'User ' || cb.user_id) as username,
               COUNT(*) as total_bets,
               COALESCE(SUM(cb.bet_amount), 0) as total_wagered,
               COALESCE(SUM(cb.win_amount), 0) as total_won,
               COALESCE(SUM(cb.win_amount - cb.bet_amount), 0) as net_profit,
               COUNT(CASE WHEN cb.result IN ('win', 'blackjack') THEN 1 END) as wins
        FROM casino_bets cb
        LEFT JOIN users u ON cb.user_id = u.user_id
        WHERE cb.is_free_play = FALSE {time_filter}
        GROUP BY cb.user_id, u.username
        ORDER BY total_won DESC
        LIMIT 50
    """, fetch=True) or []

    return [{
        'rank': i + 1,
        'user_id': r['user_id'],
        'username': r['username'] or f"User {r['user_id']}",
        'total_bets': int(r['total_bets']),
        'total_wagered': float(r['total_wagered']),
        'total_won': float(r['total_won']),
        'net_profit': float(r['net_profit']),
        'wins': int(r['wins']),
        'win_rate': round(int(r['wins']) / max(int(r['total_bets']), 1) * 100, 1),
    } for i, r in enumerate(rows)]


def get_setting(key, default=None):
    return _get_settings_cache().get(key, default)


def set_setting(key, value):
    _execute_with_retry("""
        INSERT INTO casino_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, (key, str(value)))
    _invalidate_settings_cache()


def get_house_edge(game):
    val = get_setting(f'house_edge_{game}')
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return DEFAULT_HOUSE_EDGES.get(game, 5.0)


def set_house_edge(game, edge):
    set_setting(f'house_edge_{game}', str(float(edge)))


def is_game_enabled(game):
    val = get_setting(f'game_enabled_{game}')
    if val is not None:
        return val.lower() in ('true', '1', 'yes')
    return True


def set_game_enabled(game, enabled):
    set_setting(f'game_enabled_{game}', 'true' if enabled else 'false')


def is_casino_enabled():
    val = get_setting('enabled')
    if val is not None:
        return val.lower() in ('true', '1', 'yes')
    return True


def get_min_bet():
    val = get_setting('min_bet')
    try:
        return float(val) if val else 0.10
    except (ValueError, TypeError):
        return 0.10


def get_max_bet():
    val = get_setting('max_bet')
    try:
        return float(val) if val else 100.00
    except (ValueError, TypeError):
        return 100.00


def get_daily_free_amount():
    val = get_setting('daily_free_amount')
    try:
        return float(val) if val else 5.00
    except (ValueError, TypeError):
        return 5.00


def is_daily_free_enabled():
    val = get_setting('daily_free_enabled')
    if val is not None:
        return val.lower() in ('true', '1', 'yes')
    return True


def get_daily_free_max_win():
    val = get_setting('daily_free_max_win')
    try:
        return float(val) if val else 20.00
    except (ValueError, TypeError):
        return 20.00


DEFAULT_REWARD_SETTINGS = {
    'lb_rewards_enabled': True,
    'lb_weekly_1st': 50.00,
    'lb_weekly_2nd': 25.00,
    'lb_weekly_3rd': 10.00,
    'lb_monthly_1st': 200.00,
    'lb_monthly_2nd': 100.00,
    'lb_monthly_3rd': 50.00,
    'lb_auto_payout': False,
}


def get_lb_reward_setting(key):
    val = get_setting(key)
    if val is not None:
        if key == 'lb_rewards_enabled' or key == 'lb_auto_payout':
            return val.lower() in ('true', '1', 'yes')
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return DEFAULT_REWARD_SETTINGS.get(key)


def set_lb_reward_setting(key, value):
    if key in ('lb_rewards_enabled', 'lb_auto_payout'):
        set_setting(key, 'true' if value else 'false')
    else:
        set_setting(key, str(float(value)))


def get_lb_reward_config():
    return {
        'enabled': get_lb_reward_setting('lb_rewards_enabled'),
        'auto_payout': get_lb_reward_setting('lb_auto_payout'),
        'weekly': {
            1: get_lb_reward_setting('lb_weekly_1st'),
            2: get_lb_reward_setting('lb_weekly_2nd'),
            3: get_lb_reward_setting('lb_weekly_3rd'),
        },
        'monthly': {
            1: get_lb_reward_setting('lb_monthly_1st'),
            2: get_lb_reward_setting('lb_monthly_2nd'),
            3: get_lb_reward_setting('lb_monthly_3rd'),
        },
    }


def _get_period_label(period):
    now = datetime.utcnow()
    if period == 'weekly':
        start = now - timedelta(days=now.weekday())
        return f"week_{start.strftime('%Y_%m_%d')}"
    elif period == 'monthly':
        return f"month_{now.strftime('%Y_%m')}"
    return ''


def _already_paid(period, period_label):
    row = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM casino_leaderboard_rewards WHERE period = %s AND period_label = %s",
        (period, period_label), fetch_one=True
    )
    return (row or {}).get('cnt', 0) > 0


def process_leaderboard_rewards(period):
    config = get_lb_reward_config()
    if not config['enabled']:
        return {'error': 'Leaderboard rewards are disabled'}

    if period not in ('weekly', 'monthly'):
        return {'error': 'Invalid period, must be weekly or monthly'}

    period_label = _get_period_label(period)
    if _already_paid(period, period_label):
        return {'error': f'Rewards already paid for {period} period ({period_label})'}

    leaderboard = get_leaderboard(period)
    if not leaderboard:
        return {'error': 'No leaderboard data for this period'}

    rewards_map = config[period]
    payouts = []

    from modules.cc_shop import add_user_balance

    for entry in leaderboard[:3]:
        rank = entry['rank']
        reward_amount = rewards_map.get(rank, 0)
        if reward_amount <= 0:
            continue

        user_id = entry['user_id']
        add_user_balance(user_id, reward_amount)

        _execute_with_retry("""
            INSERT INTO casino_leaderboard_rewards (user_id, period, period_label, rank, reward_amount, paid_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (user_id, period, period_label, rank, reward_amount))

        if rank == 1:
            ach_id = 'weekly_champion' if period == 'weekly' else 'monthly_champion'
            _award_achievement(user_id, ach_id)

        payouts.append({
            'user_id': user_id,
            'username': entry['username'],
            'rank': rank,
            'reward': reward_amount,
        })

    return {'success': True, 'period': period, 'period_label': period_label, 'payouts': payouts}


def get_reward_history(limit=50):
    rows = _execute_with_retry("""
        SELECT lr.*, COALESCE(u.username, 'User ' || lr.user_id) as username
        FROM casino_leaderboard_rewards lr
        LEFT JOIN users u ON lr.user_id = u.user_id
        ORDER BY lr.paid_at DESC
        LIMIT %s
    """, (limit,), fetch=True) or []
    return [{
        'id': r['id'],
        'user_id': r['user_id'],
        'username': r.get('username', f"User {r['user_id']}"),
        'period': r['period'],
        'period_label': r['period_label'],
        'rank': r['rank'],
        'reward_amount': float(r['reward_amount']),
        'paid_at': r['paid_at'].strftime('%Y-%m-%d %H:%M') if r.get('paid_at') else '',
    } for r in rows]


_user_nonces = {}

def _generate_provably_fair():
    server_seed = secrets.token_hex(32)
    seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()
    return server_seed, seed_hash

def _fair_random(server_seed, client_nonce, index=0):
    combined = f"{server_seed}:{client_nonce}:{index}"
    h = hashlib.sha256(combined.encode()).digest()
    return int.from_bytes(h[:4], 'big') / 0xFFFFFFFF

def _fair_randint(server_seed, client_nonce, low, high, index=0):
    r = _fair_random(server_seed, client_nonce, index)
    return low + int(r * (high - low + 1)) % (high - low + 1)

def _fair_choice(server_seed, client_nonce, lst, index=0):
    idx = _fair_randint(server_seed, client_nonce, 0, len(lst)-1, index)
    return lst[idx]

def _fair_shuffle(server_seed, client_nonce, lst):
    result = lst[:]
    for i in range(len(result)-1, 0, -1):
        j = _fair_randint(server_seed, client_nonce, 0, i, i)
        result[i], result[j] = result[j], result[i]
    return result

def _fair_sample(server_seed, client_nonce, population, k):
    pool = list(population)
    result = []
    for i in range(k):
        idx = _fair_randint(server_seed, client_nonce, 0, len(pool)-1, 1000+i)
        result.append(pool.pop(idx))
    return result

def _get_nonce(user_id):
    uid = str(user_id)
    _user_nonces[uid] = _user_nonces.get(uid, 0) + 1
    return _user_nonces[uid]

def _apply_house_edge(win_multiplier, house_edge_pct, server_seed, client_nonce, edge_index=999):
    if win_multiplier <= 0:
        return win_multiplier
    edge = house_edge_pct / 100.0
    roll = _fair_random(server_seed, client_nonce, edge_index)
    if roll < edge:
        return 0
    return win_multiplier


def can_claim_daily(user_id):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    row = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM casino_daily_claims WHERE user_id = %s AND claimed_at >= %s",
        (user_id, today_start), fetch_one=True
    )
    return (row or {}).get('cnt', 0) == 0


def get_free_balance(user_id):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    claim = _execute_with_retry(
        "SELECT amount FROM casino_daily_claims WHERE user_id = %s AND claimed_at >= %s ORDER BY claimed_at DESC LIMIT 1",
        (user_id, today_start), fetch_one=True
    )
    if not claim:
        return 0.0
    claimed_amount = float(claim['amount'])
    spent = _execute_with_retry(
        "SELECT COALESCE(SUM(bet_amount), 0) as total FROM casino_bets WHERE user_id = %s AND is_free_play = TRUE AND created_at >= %s",
        (user_id, today_start), fetch_one=True
    )
    total_spent = float((spent or {}).get('total', 0))
    reserved = _execute_with_retry(
        "SELECT COALESCE(SUM(bet), 0) as total FROM casino_sessions WHERE user_id = %s AND is_free = TRUE AND created_at >= %s",
        (user_id, today_start), fetch_one=True
    )
    total_reserved = float((reserved or {}).get('total', 0))
    return max(0, claimed_amount - total_spent - total_reserved)


def get_daily_free_winnings(user_id):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    row = _execute_with_retry(
        "SELECT COALESCE(SUM(win_amount), 0) as total FROM casino_bets WHERE user_id = %s AND is_free_play = TRUE AND created_at >= %s",
        (user_id, today_start), fetch_one=True
    )
    return float((row or {}).get('total', 0))


def claim_daily_free(user_id):
    if not is_daily_free_enabled():
        return {'error': 'Daily free play is disabled'}
    if not can_claim_daily(user_id):
        return {'error': 'Already claimed today'}
    amount = get_daily_free_amount()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = _execute_with_retry("""
        INSERT INTO casino_daily_claims (user_id, amount, claimed_at)
        SELECT %s, %s, NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM casino_daily_claims WHERE user_id = %s AND claimed_at >= %s
        )
    """, (user_id, amount, user_id, today_start), return_rowcount=True)
    if not result or result == 0:
        return {'error': 'Already claimed today'}
    resp = {'success': True, 'amount': amount}
    try:
        ach = check_daily_collector_achievement(user_id)
        if ach:
            resp['new_achievements'] = [ach]
    except Exception as e:
        print(f"[Casino] Daily collector achievement check failed for user {user_id}: {e}")
    return resp


def get_next_claim_time():
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    diff = (tomorrow - now).total_seconds()
    hours = int(diff // 3600)
    minutes = int((diff % 3600) // 60)
    return f"{hours}h {minutes}m"


def _log_bet(user_id, game, bet_amount, win_amount, result, details=None, is_free=False, server_seed='', seed_hash='', client_nonce=0):
    profit = bet_amount - win_amount
    _execute_with_retry("""
        INSERT INTO casino_bets (user_id, game, bet_amount, win_amount, profit, result, details, is_free_play, server_seed, seed_hash, client_nonce)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, game, bet_amount, win_amount, profit, result, json.dumps(details or {}), is_free, server_seed, seed_hash, client_nonce))


def place_bet(user_id, game, bet_amount, is_free=False):
    if not is_casino_enabled():
        return {'error': 'Casino is currently disabled'}
    if game not in GAMES:
        return {'error': 'Invalid game'}
    if not is_game_enabled(game):
        return {'error': f'{game.title()} is currently disabled'}

    bet_amount = round(float(bet_amount), 2)
    min_b = get_min_bet()
    max_b = get_max_bet()

    if bet_amount < min_b:
        return {'error': f'Minimum bet is ${min_b:.2f}'}
    if bet_amount > max_b:
        return {'error': f'Maximum bet is ${max_b:.2f}'}

    if is_free:
        free_bal = get_free_balance(user_id)
        if bet_amount > free_bal:
            return {'error': f'Not enough free credits (${free_bal:.2f} remaining)'}
    else:
        result = _execute_with_retry("""
            UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW()
            WHERE user_id = %s AND COALESCE(shop_balance, 0) >= %s
        """, (bet_amount, user_id, bet_amount), return_rowcount=True)
        if not result or result == 0:
            from modules.cc_shop import get_user_balance
            balance = get_user_balance(user_id)
            return {'error': f'Not enough balance (${balance:.2f})'}

    return {'ok': True, 'bet': bet_amount}


def settle_bet(user_id, game, bet_amount, win_amount, result, details=None, is_free=False, server_seed='', seed_hash='', client_nonce=0):
    win_amount = round(float(win_amount), 2)

    if is_free:
        net_profit = win_amount - bet_amount
        if net_profit > 0:
            max_win = get_daily_free_max_win()
            today_wins = get_daily_free_winnings(user_id)
            remaining_cap = max(0, max_win - today_wins)
            actual_credit = min(net_profit, remaining_cap)
            if actual_credit > 0:
                from modules.cc_shop import add_user_balance
                add_user_balance(user_id, actual_credit)
            win_amount = actual_credit + bet_amount
        else:
            win_amount = max(win_amount, 0)
    else:
        if win_amount > 0:
            from modules.cc_shop import add_user_balance
            add_user_balance(user_id, win_amount)

    _log_bet(user_id, game, bet_amount, win_amount, result, details, is_free, server_seed, seed_hash, client_nonce)

    new_achievements = []
    if not is_free and result != 'timeout':
        try:
            new_achievements = check_achievements(user_id, game, bet_amount, win_amount, result)
        except Exception as e:
            print(f"[Casino] Achievement check failed for user {user_id}: {e}")

    resp = {'win_amount': win_amount, 'result': result, 'seed_hash': seed_hash, 'server_seed': server_seed}
    if new_achievements:
        resp['new_achievements'] = new_achievements
    return resp


CARD_SUITS = ['♠', '♥', '♦', '♣']
CARD_RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

def _make_deck():
    return [{'rank': r, 'suit': s} for s in CARD_SUITS for r in CARD_RANKS]

def _card_value(card):
    r = card['rank']
    if r in ('J', 'Q', 'K'):
        return 10
    if r == 'A':
        return 11
    return int(r)

def _hand_value(hand):
    total = sum(_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c['rank'] == 'A')
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def _card_str(card):
    return f"{card['rank']}{card['suit']}"

def _save_session(session_id, user_id, game, bet, is_free, state, server_seed, seed_hash, nonce):
    _execute_with_retry("""
        INSERT INTO casino_sessions (session_id, user_id, game, bet, is_free, state, server_seed, seed_hash, client_nonce)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (session_id) DO UPDATE SET state = %s, bet = %s
    """, (session_id, user_id, game, bet, is_free, json.dumps(state), server_seed, seed_hash, nonce, json.dumps(state), bet))

def _load_session(session_id, user_id, game):
    row = _execute_with_retry(
        "SELECT * FROM casino_sessions WHERE session_id = %s AND user_id = %s AND game = %s",
        (session_id, user_id, game), fetch_one=True
    )
    if not row:
        return None
    state = row['state'] if isinstance(row['state'], dict) else json.loads(row['state'])
    return {
        'user_id': row['user_id'], 'bet': float(row['bet']),
        'is_free': row['is_free'], 'server_seed': row['server_seed'],
        'seed_hash': row['seed_hash'], 'nonce': row['client_nonce'],
        **state
    }

def _delete_session(session_id):
    _execute_with_retry("DELETE FROM casino_sessions WHERE session_id = %s", (session_id,))


def play_blackjack_deal(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'blackjack', bet_amount, is_free)
    if 'error' in check:
        return check

    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    deck = _fair_shuffle(server_seed, nonce, _make_deck())

    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    session_id = secrets.token_hex(6)

    pv = _hand_value(player)
    dv = _hand_value(dealer)

    if pv == 21:
        if dv == 21:
            win = bet
            result = 'push'
        else:
            multiplier = _apply_house_edge(2.5, get_house_edge('blackjack'), server_seed, nonce)
            win = round(bet * multiplier, 2)
            result = 'blackjack' if multiplier > 0 else 'lose'
        settled = settle_bet(user_id, 'blackjack', bet, win, result,
                           {'player': [_card_str(c) for c in player],
                            'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'player': [_card_str(c) for c in player],
                'dealer': [_card_str(c) for c in dealer],
                'player_value': pv, 'dealer_value': dv,
                'bet': bet, 'game': 'blackjack', 'done': True}

    state = {
        'deck': [{'rank': c['rank'], 'suit': c['suit']} for c in deck],
        'player': [{'rank': c['rank'], 'suit': c['suit']} for c in player],
        'dealer': [{'rank': c['rank'], 'suit': c['suit']} for c in dealer],
        'doubled': False,
    }
    _save_session(session_id, user_id, 'blackjack', bet, is_free, state, server_seed, seed_hash, nonce)

    return {
        'session_id': session_id, 'seed_hash': seed_hash,
        'player': [_card_str(c) for c in player],
        'dealer': [_card_str(dealer[0]), '??'],
        'player_value': pv, 'dealer_value': _card_value(dealer[0]),
        'bet': bet, 'game': 'blackjack', 'done': False,
        'can_double': len(player) == 2,
    }

def play_blackjack_action(user_id, session_id, action):
    if action not in ('hit', 'stand', 'double'):
        return {'error': 'Invalid action'}
    sess = _load_session(session_id, user_id, 'blackjack')
    if not sess:
        return {'error': 'Invalid session'}

    deck = sess['deck']
    player = sess['player']
    dealer = sess['dealer']
    bet = sess['bet']
    is_free = sess['is_free']
    server_seed = sess['server_seed']
    seed_hash = sess['seed_hash']
    nonce = sess['nonce']
    house_edge = get_house_edge('blackjack')

    if action == 'double':
        if len(player) != 2 or sess.get('doubled'):
            return {'error': 'Cannot double now'}
        extra = bet
        if not is_free:
            result_rows = _execute_with_retry("""
                UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW()
                WHERE user_id = %s AND COALESCE(shop_balance, 0) >= %s
            """, (extra, user_id, extra), return_rowcount=True)
            if not result_rows or result_rows == 0:
                return {'error': 'Not enough balance to double'}
        else:
            free_bal = get_free_balance(user_id)
            if free_bal < extra:
                return {'error': 'Not enough free credits to double'}
        bet = round(bet * 2, 2)
        sess['doubled'] = True
        player.append(deck.pop())
        action = 'stand'

    if action == 'hit':
        player.append(deck.pop())
        pv = _hand_value(player)
        if pv > 21:
            _delete_session(session_id)
            settled = settle_bet(user_id, 'blackjack', bet, 0, 'bust',
                               {'player': [_card_str(c) for c in player],
                                'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
            return {**settled, 'player': [_card_str(c) for c in player],
                    'dealer': [_card_str(c) for c in dealer],
                    'player_value': pv, 'dealer_value': _hand_value(dealer),
                    'bet': bet, 'game': 'blackjack', 'done': True}
        if pv == 21:
            action = 'stand'
        else:
            state = {
                'deck': deck, 'player': player, 'dealer': dealer,
                'doubled': sess.get('doubled', False),
            }
            _save_session(session_id, user_id, 'blackjack', bet, is_free, state, server_seed, seed_hash, nonce)
            return {
                'session_id': session_id, 'seed_hash': seed_hash,
                'player': [_card_str(c) for c in player],
                'dealer': [_card_str(dealer[0]), '??'],
                'player_value': pv, 'bet': bet, 'game': 'blackjack', 'done': False,
                'can_double': False,
            }

    if action == 'stand':
        pv = _hand_value(player)
        while _hand_value(dealer) < 17:
            dealer.append(deck.pop())
        dv = _hand_value(dealer)

        if dv > 21 or pv > dv:
            multiplier = 2
            multiplier = _apply_house_edge(multiplier, house_edge, server_seed, nonce)
            win = round(bet * multiplier, 2)
            result = 'win' if multiplier > 0 else 'lose'
        elif pv == dv:
            win = bet
            result = 'push'
        else:
            win = 0
            result = 'lose'

        _delete_session(session_id)
        settled = settle_bet(user_id, 'blackjack', bet, win, result,
                           {'player': [_card_str(c) for c in player],
                            'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'player': [_card_str(c) for c in player],
                'dealer': [_card_str(c) for c in dealer],
                'player_value': pv, 'dealer_value': dv,
                'bet': bet, 'game': 'blackjack', 'done': True}

    return {'error': 'Invalid action'}


def _prob_win(game, server_seed, nonce):
    edge = get_house_edge(game)
    prob = max(0, min(100, 100 - edge))
    r = _fair_random(server_seed, nonce, 999) * 100
    return r <= prob


def play_head_tail(user_id, bet_amount, choose='head', is_free=False):
    if choose not in ('head', 'tail'):
        return {'error': 'Choose head or tail'}
    check = place_bet(user_id, 'head_tail', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    win_pct = 100 - get_house_edge('head_tail')
    multiplier = 0
    if _prob_win('head_tail', server_seed, nonce):
        coin_result = choose
        multiplier = 1.95
    else:
        coin_result = 'tail' if choose == 'head' else 'head'
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'coin_result': coin_result}
    settled = settle_bet(user_id, 'head_tail', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'head_tail'}


def play_rock_paper_scissors(user_id, bet_amount, choose='rock', is_free=False):
    if choose not in ('rock', 'paper', 'scissors'):
        return {'error': 'Choose rock, paper, or scissors'}
    check = place_bet(user_id, 'rock_paper_scissors', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    beats = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'}
    loses_to = {'rock': 'paper', 'paper': 'scissors', 'scissors': 'rock'}
    multiplier = 0
    if _prob_win('rock_paper_scissors', server_seed, nonce):
        bot_choice = beats[choose]
        multiplier = 1.95
    else:
        bot_choice = loses_to[choose]
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'bot_choice': bot_choice}
    settled = settle_bet(user_id, 'rock_paper_scissors', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'rock_paper_scissors'}


SPIN_SEGMENTS = [
    {'label': '2x', 'multiplier': 2, 'color': '#e74c3c'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
    {'label': '1.5x', 'multiplier': 1.5, 'color': '#3498db'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
    {'label': '3x', 'multiplier': 3, 'color': '#e67e22'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
    {'label': '1.5x', 'multiplier': 1.5, 'color': '#9b59b6'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
    {'label': '5x', 'multiplier': 5, 'color': '#f1c40f'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
    {'label': '1.2x', 'multiplier': 1.2, 'color': '#1abc9c'},
    {'label': '0x', 'multiplier': 0, 'color': '#2c3e50'},
]

def play_spin_wheel(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'spin_wheel', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    if _prob_win('spin_wheel', server_seed, nonce):
        win_segs = [i for i, s in enumerate(SPIN_SEGMENTS) if s['multiplier'] > 0]
        seg_idx = _fair_choice(server_seed, nonce, win_segs, 1)
    else:
        lose_segs = [i for i, s in enumerate(SPIN_SEGMENTS) if s['multiplier'] == 0]
        seg_idx = _fair_choice(server_seed, nonce, lose_segs, 1)
    seg = SPIN_SEGMENTS[seg_idx]
    multiplier = seg['multiplier']
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'segment': seg_idx, 'segment_label': seg['label']}
    settled = settle_bet(user_id, 'spin_wheel', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'segments': SPIN_SEGMENTS, 'multiplier': multiplier, 'bet': bet, 'game': 'spin_wheel'}


def play_number_guess(user_id, bet_amount, guess_number=None, is_free=False):
    try:
        guess_number = int(guess_number)
        if guess_number < 1 or guess_number > 99:
            return {'error': 'Guess a number between 1-99'}
    except (ValueError, TypeError):
        return {'error': 'Enter a valid number (1-99)'}
    check = place_bet(user_id, 'number_guess', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    secret_number = _fair_randint(server_seed, nonce, 1, 99, 0)
    diff = abs(secret_number - guess_number)
    multiplier = 0
    if diff == 0:
        multiplier = 9.5
    elif diff <= 5:
        multiplier = 3.0
    elif diff <= 10:
        multiplier = 2.0
    elif diff <= 20:
        multiplier = 1.2
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('number_guess'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    hint = 'higher' if secret_number > guess_number else ('lower' if secret_number < guess_number else 'exact')
    details = {'guess': guess_number, 'secret': secret_number, 'diff': diff, 'hint': hint}
    settled = settle_bet(user_id, 'number_guess', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'number_guess'}


def play_dice_rolling(user_id, bet_amount, choose='high', is_free=False):
    if choose not in ('high', 'low', 'seven'):
        return {'error': 'Choose high, low, or seven'}
    check = place_bet(user_id, 'dice_rolling', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    die1 = _fair_randint(server_seed, nonce, 1, 6, 0)
    die2 = _fair_randint(server_seed, nonce, 1, 6, 1)
    total = die1 + die2
    multiplier = 0
    if choose == 'high' and total > 7:
        multiplier = 1.95
    elif choose == 'low' and total < 7:
        multiplier = 1.95
    elif choose == 'seven' and total == 7:
        multiplier = 4.5
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('dice_rolling'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'dice': [die1, die2], 'total': total, 'choose': choose}
    settled = settle_bet(user_id, 'dice_rolling', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'dice_rolling'}


def play_card_finding(user_id, bet_amount, chosen_position=0, is_free=False):
    try:
        chosen_position = int(chosen_position)
        if chosen_position < 0 or chosen_position > 2:
            chosen_position = 0
    except (ValueError, TypeError):
        chosen_position = 0
    check = place_bet(user_id, 'card_finding', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    cards = ['🂡', '🂢', '🂣']
    positions = _fair_shuffle(server_seed, nonce, [0, 1, 2])
    winning_position = positions[0]
    multiplier = 0
    if chosen_position == winning_position:
        multiplier = 2.5
        multiplier = _apply_house_edge(multiplier, get_house_edge('card_finding'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'chosen': chosen_position, 'winning': winning_position, 'positions': positions}
    settled = settle_bet(user_id, 'card_finding', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'card_finding'}


SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🔔', '⭐', '💎', '7️⃣']
SLOT_PAYOUTS = {'🍒🍒🍒': 5, '🍋🍋🍋': 8, '🍊🍊🍊': 10, '🍇🍇🍇': 15, '🔔🔔🔔': 25, '⭐⭐⭐': 50, '💎💎💎': 100, '7️⃣7️⃣7️⃣': 250}
SLOT_PARTIAL = {'🍒🍒': 2, '🍋🍋': 2, '🍊🍊': 3, '🔔🔔': 5}

def play_number_slot(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'number_slot', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    reels = [_fair_choice(server_seed, nonce, SLOT_SYMBOLS, i) for i in range(3)]
    combo = ''.join(reels)
    multiplier = 0
    if combo in SLOT_PAYOUTS:
        multiplier = SLOT_PAYOUTS[combo]
    else:
        partial = reels[0] + reels[1]
        if partial in SLOT_PARTIAL and reels[0] == reels[1]:
            multiplier = SLOT_PARTIAL[partial]
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('number_slot'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'reels': reels, 'multiplier': multiplier}
    settled = settle_bet(user_id, 'number_slot', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, 'reels': reels, 'multiplier': multiplier, 'bet': bet, 'game': 'number_slot'}


def play_number_pool(user_id, bet_amount, choose='odd', is_free=False):
    if choose not in ('odd', 'even'):
        return {'error': 'Choose odd or even'}
    check = place_bet(user_id, 'number_pool', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    ball_number = _fair_randint(server_seed, nonce, 1, 49, 0)
    ball_is_odd = ball_number % 2 == 1
    multiplier = 0
    if (choose == 'odd' and ball_is_odd) or (choose == 'even' and not ball_is_odd):
        multiplier = 1.9
        multiplier = _apply_house_edge(multiplier, get_house_edge('number_pool'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'ball': ball_number}
    settled = settle_bet(user_id, 'number_pool', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'number_pool'}


ROULETTE_REDS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
ROULETTE_BLACKS = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}

def play_roulette(user_id, bet_amount, bet_type, bet_value=None, is_free=False):
    check = place_bet(user_id, 'roulette', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    number = _fair_randint(server_seed, nonce, 0, 36)
    color = 'green' if number == 0 else ('red' if number in ROULETTE_REDS else 'black')
    multiplier = 0
    if bet_type == 'number':
        try:
            if int(bet_value) == number:
                multiplier = 36
        except (ValueError, TypeError):
            pass
    elif bet_type == 'red' and color == 'red':
        multiplier = 2
    elif bet_type == 'black' and color == 'black':
        multiplier = 2
    elif bet_type == 'odd' and number > 0 and number % 2 == 1:
        multiplier = 2
    elif bet_type == 'even' and number > 0 and number % 2 == 0:
        multiplier = 2
    elif bet_type == 'low' and 1 <= number <= 18:
        multiplier = 2
    elif bet_type == 'high' and 19 <= number <= 36:
        multiplier = 2
    elif bet_type == 'dozen1' and 1 <= number <= 12:
        multiplier = 3
    elif bet_type == 'dozen2' and 13 <= number <= 24:
        multiplier = 3
    elif bet_type == 'dozen3' and 25 <= number <= 36:
        multiplier = 3
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('roulette'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'number': number, 'color': color, 'bet_type': bet_type, 'bet_value': bet_value}
    settled = settle_bet(user_id, 'roulette', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, 'number': number, 'color': color, 'multiplier': multiplier, 'bet': bet, 'game': 'roulette'}


def play_casino_dice(user_id, bet_amount, percent=50, choose='low', is_free=False):
    try:
        percent = float(percent)
        if percent < 1 or percent > 95:
            return {'error': 'Win chance must be 1-95%'}
    except (ValueError, TypeError):
        return {'error': 'Invalid win chance'}
    if choose not in ('low', 'high'):
        return {'error': 'Choose low or high'}
    check = place_bet(user_id, 'casino_dice', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    payout = round(99 / percent, 4)
    roll = _fair_randint(server_seed, nonce, 100, 9999, 0)
    target = int(percent * 100)
    multiplier = 0
    if choose == 'low' and roll <= target:
        multiplier = payout
    elif choose == 'high' and roll >= (9900 - target + 99):
        multiplier = payout
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('casino_dice'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    roll_display = f"{roll / 100:.2f}"
    details = {'roll': roll_display, 'target': f"{percent:.2f}", 'choose': choose, 'payout': f"{payout:.4f}x"}
    settled = settle_bet(user_id, 'casino_dice', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'casino_dice'}


KENO_PAYOUTS = {
    1: {1: 3}, 2: {2: 9}, 3: {2: 2, 3: 25}, 4: {2: 1, 3: 5, 4: 75},
    5: {3: 3, 4: 15, 5: 250}, 6: {3: 2, 4: 8, 5: 50, 6: 500},
    7: {3: 1, 4: 4, 5: 20, 6: 100, 7: 1000}, 8: {4: 3, 5: 10, 6: 50, 7: 300, 8: 2000},
    10: {5: 5, 6: 25, 7: 150, 8: 500, 9: 2500, 10: 10000},
}

def play_keno(user_id, bet_amount, picks, is_free=False):
    if not picks or not isinstance(picks, list):
        return {'error': 'Pick 1-10 numbers between 1-80'}
    try:
        picks = [int(p) for p in picks if 1 <= int(p) <= 80][:10]
    except (ValueError, TypeError):
        return {'error': 'Invalid picks'}
    if len(picks) < 1:
        return {'error': 'Pick at least 1 number'}
    check = place_bet(user_id, 'keno', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    drawn = sorted(_fair_sample(server_seed, nonce, range(1, 81), 20))
    hits = sorted([p for p in picks if p in drawn])
    num_hits = len(hits)
    payout_table = KENO_PAYOUTS.get(len(picks), {})
    multiplier = payout_table.get(num_hits, 0)
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('keno'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'picks': picks, 'drawn': drawn, 'hits': hits, 'num_hits': num_hits}
    settled = settle_bet(user_id, 'keno', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'keno'}


POKER_HANDS = {
    'royal_flush': 250, 'straight_flush': 50, 'four_kind': 25,
    'full_house': 9, 'flush': 6, 'straight': 4,
    'three_kind': 3, 'two_pair': 2, 'jacks_or_better': 1,
}

def _rank_num(rank):
    order = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}
    return order.get(rank, 0)

def _evaluate_poker(hand):
    ranks = sorted([_rank_num(c['rank']) for c in hand], reverse=True)
    suits = [c['suit'] for c in hand]
    is_flush = len(set(suits)) == 1
    is_straight = (ranks == list(range(ranks[0], ranks[0]-5, -1))) or ranks == [14,5,4,3,2]
    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts = sorted(rank_counts.values(), reverse=True)
    if is_flush and is_straight and ranks[0] == 14 and ranks[1] == 13:
        return 'royal_flush'
    if is_flush and is_straight:
        return 'straight_flush'
    if counts == [4, 1]:
        return 'four_kind'
    if counts == [3, 2]:
        return 'full_house'
    if is_flush:
        return 'flush'
    if is_straight:
        return 'straight'
    if counts == [3, 1, 1]:
        return 'three_kind'
    if counts == [2, 2, 1]:
        return 'two_pair'
    if counts[0] == 2:
        pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
        if pair_rank >= 11:
            return 'jacks_or_better'
    return 'nothing'

def play_poker_deal(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'poker', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    deck = _fair_shuffle(server_seed, nonce, _make_deck())
    hand = [deck.pop() for _ in range(5)]
    session_id = secrets.token_hex(6)
    state = {'deck': [{'rank': c['rank'], 'suit': c['suit']} for c in deck], 'hand': [{'rank': c['rank'], 'suit': c['suit']} for c in hand]}
    _save_session(session_id, user_id, 'poker', bet, is_free, state, server_seed, seed_hash, nonce)
    return {'session_id': session_id, 'seed_hash': seed_hash, 'hand': [_card_str(c) for c in hand], 'hand_name': _evaluate_poker(hand).replace('_', ' ').title(), 'bet': bet, 'game': 'poker', 'done': False}

def play_poker_draw(user_id, session_id, hold_indices):
    if not isinstance(hold_indices, (list, tuple)):
        hold_indices = []
    try:
        hold_indices = [int(i) for i in hold_indices if isinstance(i, (int, float, str)) and 0 <= int(i) <= 4]
    except (ValueError, TypeError):
        hold_indices = []
    sess = _load_session(session_id, user_id, 'poker')
    if not sess:
        return {'error': 'Invalid session'}
    deck, hand, bet = sess['deck'], sess['hand'], sess['bet']
    is_free, server_seed, seed_hash, nonce = sess['is_free'], sess['server_seed'], sess['seed_hash'], sess['nonce']
    for i in range(5):
        if i not in hold_indices:
            hand[i] = deck.pop()
    hand_type = _evaluate_poker(hand)
    multiplier = POKER_HANDS.get(hand_type, 0)
    if multiplier > 0:
        multiplier = _apply_house_edge(multiplier, get_house_edge('poker'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    _delete_session(session_id)
    details = {'hand': [_card_str(c) for c in hand], 'hand_type': hand_type}
    settled = settle_bet(user_id, 'poker', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, 'hand': [_card_str(c) for c in hand], 'hand_name': hand_type.replace('_', ' ').title(), 'multiplier': multiplier, 'bet': bet, 'game': 'poker', 'done': True}


def play_blackjack_deal(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'blackjack', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    deck = _fair_shuffle(server_seed, nonce, _make_deck())
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    session_id = secrets.token_hex(6)
    pv, dv = _hand_value(player), _hand_value(dealer)
    if pv == 21:
        if dv == 21:
            win, result = bet, 'push'
        else:
            m = _apply_house_edge(2.5, get_house_edge('blackjack'), server_seed, nonce)
            win = round(bet * m, 2)
            result = 'blackjack' if m > 0 else 'lose'
        settled = settle_bet(user_id, 'blackjack', bet, win, result, {'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer], 'player_value': pv, 'dealer_value': dv, 'bet': bet, 'game': 'blackjack', 'done': True}
    state = {'deck': [{'rank': c['rank'], 'suit': c['suit']} for c in deck], 'player': [{'rank': c['rank'], 'suit': c['suit']} for c in player], 'dealer': [{'rank': c['rank'], 'suit': c['suit']} for c in dealer], 'doubled': False}
    _save_session(session_id, user_id, 'blackjack', bet, is_free, state, server_seed, seed_hash, nonce)
    return {'session_id': session_id, 'seed_hash': seed_hash, 'player': [_card_str(c) for c in player], 'dealer': [_card_str(dealer[0]), '??'], 'player_value': pv, 'dealer_value': _card_value(dealer[0]), 'bet': bet, 'game': 'blackjack', 'done': False, 'can_double': len(player) == 2}

def play_blackjack_action(user_id, session_id, action):
    if action not in ('hit', 'stand', 'double'):
        return {'error': 'Invalid action'}
    sess = _load_session(session_id, user_id, 'blackjack')
    if not sess:
        return {'error': 'Invalid session'}
    deck, player, dealer = sess['deck'], sess['player'], sess['dealer']
    bet, is_free = sess['bet'], sess['is_free']
    server_seed, seed_hash, nonce = sess['server_seed'], sess['seed_hash'], sess['nonce']
    if action == 'double':
        if len(player) != 2 or sess.get('doubled'):
            return {'error': 'Cannot double now'}
        extra = bet
        if not is_free:
            r = _execute_with_retry("UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW() WHERE user_id = %s AND COALESCE(shop_balance, 0) >= %s", (extra, user_id, extra), return_rowcount=True)
            if not r or r == 0:
                return {'error': 'Not enough balance to double'}
        else:
            if get_free_balance(user_id) < extra:
                return {'error': 'Not enough free credits to double'}
        bet = round(bet * 2, 2)
        sess['doubled'] = True
        player.append(deck.pop())
        action = 'stand'
    if action == 'hit':
        player.append(deck.pop())
        pv = _hand_value(player)
        if pv > 21:
            _delete_session(session_id)
            settled = settle_bet(user_id, 'blackjack', bet, 0, 'bust', {'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
            return {**settled, 'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer], 'player_value': pv, 'dealer_value': _hand_value(dealer), 'bet': bet, 'game': 'blackjack', 'done': True}
        if pv == 21:
            action = 'stand'
        else:
            state = {'deck': deck, 'player': player, 'dealer': dealer, 'doubled': sess.get('doubled', False)}
            _save_session(session_id, user_id, 'blackjack', bet, is_free, state, server_seed, seed_hash, nonce)
            return {'session_id': session_id, 'seed_hash': seed_hash, 'player': [_card_str(c) for c in player], 'dealer': [_card_str(dealer[0]), '??'], 'player_value': pv, 'bet': bet, 'game': 'blackjack', 'done': False, 'can_double': False}
    if action == 'stand':
        pv = _hand_value(player)
        while _hand_value(dealer) < 17:
            dealer.append(deck.pop())
        dv = _hand_value(dealer)
        if dv > 21 or pv > dv:
            m = _apply_house_edge(2, get_house_edge('blackjack'), server_seed, nonce)
            win = round(bet * m, 2)
            result = 'win' if m > 0 else 'lose'
        elif pv == dv:
            win, result = bet, 'push'
        else:
            win, result = 0, 'lose'
        _delete_session(session_id)
        settled = settle_bet(user_id, 'blackjack', bet, win, result, {'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer]}, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'player': [_card_str(c) for c in player], 'dealer': [_card_str(c) for c in dealer], 'player_value': pv, 'dealer_value': dv, 'bet': bet, 'game': 'blackjack', 'done': True}
    return {'error': 'Invalid action'}


def play_mines_start(user_id, bet_amount, num_mines=3, is_free=False):
    try:
        num_mines = int(num_mines)
        if num_mines < 1 or num_mines > 24:
            return {'error': 'Mines must be 1-24'}
    except (ValueError, TypeError):
        return {'error': 'Invalid mine count'}
    check = place_bet(user_id, 'mines', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    positions = list(range(25))
    mine_positions = _fair_sample(server_seed, nonce, positions, num_mines)
    session_id = secrets.token_hex(6)
    state = {'mines': mine_positions, 'num_mines': num_mines, 'revealed': [], 'gems_found': 0, 'cashed_out': False}
    _save_session(session_id, user_id, 'mines', bet, is_free, state, server_seed, seed_hash, nonce)
    return {'session_id': session_id, 'seed_hash': seed_hash, 'num_mines': num_mines, 'bet': bet, 'game': 'mines', 'done': False, 'gems_found': 0, 'grid_size': 25}

def play_mines_reveal(user_id, session_id, position):
    try:
        position = int(position)
        if position < 0 or position > 24:
            return {'error': 'Invalid position'}
    except (ValueError, TypeError):
        return {'error': 'Invalid position'}
    sess = _load_session(session_id, user_id, 'mines')
    if not sess:
        return {'error': 'Invalid session'}
    if sess.get('cashed_out'):
        return {'error': 'Already cashed out'}
    if position in sess.get('revealed', []):
        return {'error': 'Already revealed'}
    bet, is_free = sess['bet'], sess['is_free']
    server_seed, seed_hash, nonce = sess['server_seed'], sess['seed_hash'], sess['nonce']
    mines = sess['mines']
    revealed = sess.get('revealed', [])
    if position in mines:
        revealed.append(position)
        _delete_session(session_id)
        settled = settle_bet(user_id, 'mines', bet, 0, 'lose', {'mines': mines, 'revealed': revealed, 'hit_mine': position}, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'hit_mine': True, 'mine_position': position, 'mines': mines, 'revealed': revealed, 'bet': bet, 'game': 'mines', 'done': True}
    revealed.append(position)
    gems = len([r for r in revealed if r not in mines])
    safe_total = 25 - sess['num_mines']
    multiplier = round(1 + (gems * sess['num_mines'] / safe_total) * 1.5, 4)
    state = {**sess, 'revealed': revealed, 'gems_found': gems}
    del state['bet'], state['is_free'], state['server_seed'], state['seed_hash'], state['nonce'], state['user_id']
    _save_session(session_id, user_id, 'mines', bet, is_free, state, server_seed, seed_hash, nonce)
    return {'session_id': session_id, 'hit_mine': False, 'position': position, 'gems_found': gems, 'current_multiplier': multiplier, 'potential_win': round(bet * multiplier, 2), 'revealed': revealed, 'bet': bet, 'game': 'mines', 'done': False}

def play_mines_cashout(user_id, session_id):
    sess = _load_session(session_id, user_id, 'mines')
    if not sess:
        return {'error': 'Invalid session'}
    if sess.get('cashed_out'):
        return {'error': 'Already cashed out'}
    bet, is_free = sess['bet'], sess['is_free']
    server_seed, seed_hash, nonce = sess['server_seed'], sess['seed_hash'], sess['nonce']
    mines, revealed = sess['mines'], sess.get('revealed', [])
    gems = len([r for r in revealed if r not in mines])
    if gems == 0:
        return {'error': 'Reveal at least one gem first'}
    safe_total = 25 - sess['num_mines']
    multiplier = round(1 + (gems * sess['num_mines'] / safe_total) * 1.5, 4)
    multiplier = _apply_house_edge(multiplier, get_house_edge('mines'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    _delete_session(session_id)
    details = {'mines': mines, 'revealed': revealed, 'gems': gems, 'multiplier': multiplier}
    settled = settle_bet(user_id, 'mines', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, 'mines': mines, 'revealed': revealed, 'gems_found': gems, 'multiplier': multiplier, 'bet': bet, 'game': 'mines', 'done': True}


COLOR_OPTIONS = ['red', 'green', 'blue']

def play_color_prediction(user_id, bet_amount, choose='red', is_free=False):
    if choose not in COLOR_OPTIONS:
        return {'error': f'Choose from: {", ".join(COLOR_OPTIONS)}'}
    check = place_bet(user_id, 'color_prediction', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    if _prob_win('color_prediction', server_seed, nonce):
        winning_color = choose
        multiplier = 2.8
    else:
        others = [c for c in COLOR_OPTIONS if c != choose]
        winning_color = _fair_choice(server_seed, nonce, others, 1)
        multiplier = 0
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'winning_color': winning_color}
    settled = settle_bet(user_id, 'color_prediction', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'color_prediction'}


CRAZY_SEGMENTS = ['1', '2', '5', '10', 'coin_flip', 'pachinko', 'cash_hunt', 'crazy_times']
CRAZY_MULTIPLIERS = {'1': 1, '2': 2, '5': 5, '10': 10, 'coin_flip': 8, 'pachinko': 12, 'cash_hunt': 15, 'crazy_times': 20}

def play_crazy_times(user_id, bet_amount, choose='1', is_free=False):
    if choose not in CRAZY_SEGMENTS:
        return {'error': 'Invalid choice'}
    check = place_bet(user_id, 'crazy_times', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    if _prob_win('crazy_times', server_seed, nonce):
        spin_result = choose
        multiplier = CRAZY_MULTIPLIERS.get(choose, 1)
    else:
        others = [s for s in CRAZY_SEGMENTS if s != choose]
        spin_result = _fair_choice(server_seed, nonce, others, 1)
        multiplier = 0
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'spin_result': spin_result}
    settled = settle_bet(user_id, 'crazy_times', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'crazy_times'}


DREAM_SEGMENTS = ['1', '2', '5', '10', '20', '40']
DREAM_MULTIPLIERS = {'1': 1, '2': 2, '5': 5, '10': 10, '20': 20, '40': 40}

def play_dream_catcher(user_id, bet_amount, choose='1', is_free=False):
    if choose not in DREAM_SEGMENTS:
        return {'error': 'Invalid choice'}
    check = place_bet(user_id, 'dream_catcher', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    if _prob_win('dream_catcher', server_seed, nonce):
        spin_result = choose
        multiplier = DREAM_MULTIPLIERS.get(choose, 1)
    else:
        others = [s for s in DREAM_SEGMENTS if s != choose]
        spin_result = _fair_choice(server_seed, nonce, others, 1)
        multiplier = 0
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'choose': choose, 'spin_result': spin_result}
    settled = settle_bet(user_id, 'dream_catcher', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'dream_catcher'}


def play_andar_bahar(user_id, bet_amount, choose='andar', is_free=False):
    if choose not in ('andar', 'bahar'):
        return {'error': 'Choose andar or bahar'}
    check = place_bet(user_id, 'andar_bahar', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    deck = _fair_shuffle(server_seed, nonce, _make_deck())
    joker = deck.pop()
    joker_rank = joker['rank']
    andar_cards, bahar_cards = [], []
    winner = None
    deal_to_andar = True
    for i in range(40):
        card = deck.pop()
        if deal_to_andar:
            andar_cards.append(card)
            if card['rank'] == joker_rank:
                winner = 'andar'
                break
        else:
            bahar_cards.append(card)
            if card['rank'] == joker_rank:
                winner = 'bahar'
                break
        deal_to_andar = not deal_to_andar
    if not winner:
        winner = 'andar' if _fair_randint(server_seed, nonce, 0, 1, 50) == 0 else 'bahar'
    multiplier = 0
    if choose == winner:
        multiplier = 1.9 if winner == 'andar' else 2.0
        multiplier = _apply_house_edge(multiplier, get_house_edge('andar_bahar'), server_seed, nonce)
    win = round(bet * multiplier, 2)
    result = 'win' if win > 0 else 'lose'
    details = {'joker': _card_str(joker), 'andar': [_card_str(c) for c in andar_cards], 'bahar': [_card_str(c) for c in bahar_cards], 'winner': winner, 'choose': choose}
    settled = settle_bet(user_id, 'andar_bahar', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'andar_bahar'}


def _pai_gow_hand_value(hand):
    ranks = sorted([_rank_num(c['rank']) for c in hand], reverse=True)
    suits = [c['suit'] for c in hand]
    is_flush = len(set(suits)) == 1
    unique = sorted(set(ranks), reverse=True)
    is_straight = False
    if len(unique) == len(ranks):
        if ranks == list(range(ranks[0], ranks[0]-len(ranks), -1)):
            is_straight = True
        if set(ranks) == {14, 5, 4, 3, 2}:
            is_straight = True
    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    counts = sorted(rank_counts.values(), reverse=True)
    score = 0
    if is_flush and is_straight:
        score = 800
    elif counts == [4, 1]:
        score = 700
    elif counts == [3, 2]:
        score = 600
    elif is_flush:
        score = 500
    elif is_straight:
        score = 400
    elif counts == [3, 1, 1]:
        score = 300
    elif counts == [2, 2, 1]:
        score = 200
    elif counts[0] == 2:
        score = 100
    return score + sum(ranks)

def play_pai_gow_poker(user_id, bet_amount, is_free=False):
    check = place_bet(user_id, 'pai_gow_poker', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    deck = _fair_shuffle(server_seed, nonce, _make_deck())
    player_cards = [deck.pop() for _ in range(7)]
    dealer_cards = [deck.pop() for _ in range(7)]
    p_sorted = sorted(player_cards, key=lambda c: _rank_num(c['rank']), reverse=True)
    p_high = p_sorted[:5]
    p_low = p_sorted[5:]
    d_sorted = sorted(dealer_cards, key=lambda c: _rank_num(c['rank']), reverse=True)
    d_high = d_sorted[:5]
    d_low = d_sorted[5:]
    p_high_val = _pai_gow_hand_value(p_high)
    p_low_val = sum(_rank_num(c['rank']) for c in p_low)
    d_high_val = _pai_gow_hand_value(d_high)
    d_low_val = sum(_rank_num(c['rank']) for c in d_low)
    p_wins = 0
    if p_high_val > d_high_val:
        p_wins += 1
    if p_low_val > d_low_val:
        p_wins += 1
    multiplier = 0
    if p_wins == 2:
        multiplier = 1.95
        multiplier = _apply_house_edge(multiplier, get_house_edge('pai_gow_poker'), server_seed, nonce)
        result = 'win'
    elif p_wins == 1:
        multiplier = 1
        result = 'push'
    else:
        result = 'lose'
    win = round(bet * multiplier, 2)
    details = {'player_high': [_card_str(c) for c in p_high], 'player_low': [_card_str(c) for c in p_low], 'dealer_high': [_card_str(c) for c in d_high], 'dealer_low': [_card_str(c) for c in d_low]}
    settled = settle_bet(user_id, 'pai_gow_poker', bet, win, result, details, is_free, server_seed, seed_hash, nonce)
    return {**settled, **details, 'multiplier': multiplier, 'bet': bet, 'game': 'pai_gow_poker'}


# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════

def get_casino_stats():
    total = _execute_with_retry("""
        SELECT COUNT(*) as bets, COALESCE(SUM(bet_amount),0) as wagered,
               COALESCE(SUM(win_amount),0) as paid, COALESCE(SUM(profit),0) as profit
        FROM casino_bets WHERE is_free_play = FALSE
    """, fetch_one=True) or {}

    free = _execute_with_retry("""
        SELECT COUNT(*) as bets, COALESCE(SUM(bet_amount),0) as wagered,
               COALESCE(SUM(win_amount),0) as paid
        FROM casino_bets WHERE is_free_play = TRUE
    """, fetch_one=True) or {}

    by_game = _execute_with_retry("""
        SELECT game, COUNT(*) as bets, COALESCE(SUM(bet_amount),0) as wagered,
               COALESCE(SUM(win_amount),0) as paid, COALESCE(SUM(profit),0) as profit
        FROM casino_bets WHERE is_free_play = FALSE
        GROUP BY game ORDER BY wagered DESC
    """, fetch=True) or []

    return {
        'total_bets': int(total.get('bets', 0)),
        'total_wagered': float(total.get('wagered', 0)),
        'total_paid': float(total.get('paid', 0)),
        'house_profit': float(total.get('profit', 0)),
        'free_bets': int(free.get('bets', 0)),
        'free_wagered': float(free.get('wagered', 0)),
        'free_paid': float(free.get('paid', 0)),
        'by_game': [{
            'game': g['game'], 'bets': int(g['bets']),
            'wagered': float(g['wagered']), 'paid': float(g['paid']),
            'profit': float(g['profit']),
        } for g in by_game],
    }


def get_user_casino_stats(user_id):
    row = _execute_with_retry("""
        SELECT COUNT(*) as bets, COALESCE(SUM(bet_amount),0) as wagered,
               COALESCE(SUM(win_amount),0) as won, COALESCE(SUM(profit),0) as lost
        FROM casino_bets WHERE user_id = %s AND is_free_play = FALSE
    """, (user_id,), fetch_one=True) or {}
    return {
        'bets': int(row.get('bets', 0)),
        'wagered': float(row.get('wagered', 0)),
        'won': float(row.get('won', 0)),
        'net': float(row.get('wagered', 0)) - float(row.get('won', 0)),
    }


def get_recent_bets(limit=50, user_id=None):
    if user_id:
        return _execute_with_retry("""
            SELECT * FROM casino_bets WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
        """, (user_id, limit), fetch=True) or []
    return _execute_with_retry("""
        SELECT * FROM casino_bets ORDER BY created_at DESC LIMIT %s
    """, (limit,), fetch=True) or []


def cleanup_sessions():
    expired = _execute_with_retry(
        "SELECT * FROM casino_sessions WHERE created_at < NOW() - INTERVAL '10 minutes'",
        fetch=True
    ) or []
    for row in expired:
        sid = row['session_id']
        settle_bet(
            row['user_id'], row['game'], float(row['bet']), 0, 'timeout', {},
            row['is_free'], row.get('server_seed', ''), row.get('seed_hash', ''), row.get('client_nonce', 0)
        )
        _delete_session(sid)


_cleanup_started = False

def start_cleanup_scheduler():
    global _cleanup_started
    if _cleanup_started:
        return
    _cleanup_started = True
    import threading
    def _cleanup_loop():
        while True:
            try:
                cleanup_sessions()
            except Exception:
                pass
            time.sleep(60)
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()


# ============================================================================
# CRASH (Aviator-style)
# ============================================================================
import math as _math_crash

CRASH_GROWTH = 0.06  # multiplier exponent per second (~1.82x at 10s)
CRASH_MAX_MULT = 100.0

def _generate_crash_point(server_seed, nonce, edge_pct):
    """Provably-fair crash multiplier with house edge.
    edge_pct chance of instant 1.00x crash; otherwise distribution m = 0.99/(1-r)."""
    h = hashlib.sha256(f"{server_seed}:{nonce}:crash".encode()).hexdigest()
    r_int = int(h[:13], 16)
    r = r_int / float(1 << 52)
    edge_threshold = max(0.01, edge_pct / 100.0)
    if r < edge_threshold:
        return 1.00
    r2 = (r - edge_threshold) / (1 - edge_threshold)
    if r2 >= 0.999999:
        return CRASH_MAX_MULT
    m = 0.99 / (1.0 - r2)
    return round(min(max(m, 1.01), CRASH_MAX_MULT), 2)

def play_crash_start(user_id, bet_amount, is_free=False, auto_cashout=None):
    check = place_bet(user_id, 'crash', bet_amount, is_free)
    if 'error' in check:
        return check
    bet = check['bet']
    server_seed, seed_hash = _generate_provably_fair()
    nonce = _get_nonce(user_id)
    edge = get_house_edge('crash')
    crash_point = _generate_crash_point(server_seed, nonce, edge)
    start_ts = time.time()
    auto = None
    if auto_cashout is not None:
        try:
            a = float(auto_cashout)
            if 1.01 <= a <= CRASH_MAX_MULT:
                auto = round(a, 2)
        except (ValueError, TypeError):
            pass
    state = {'crash_point': crash_point, 'start_ts': start_ts, 'auto_cashout': auto, 'cashed_out': False}
    session_id = secrets.token_hex(6)
    _save_session(session_id, user_id, 'crash', bet, is_free, state, server_seed, seed_hash, nonce)
    return {'session_id': session_id, 'seed_hash': seed_hash, 'bet': bet,
            'game': 'crash', 'done': False, 'growth_rate': CRASH_GROWTH,
            'auto_cashout': auto, 'start_ts': start_ts}

def _crash_multiplier_at(start_ts, now_ts):
    elapsed = max(0.0, now_ts - start_ts)
    m = _math_crash.exp(CRASH_GROWTH * elapsed)
    return round(min(m, CRASH_MAX_MULT), 2)

def play_crash_cashout(user_id, session_id):
    sess = _load_session(session_id, user_id, 'crash')
    if not sess:
        return {'error': 'Invalid session'}
    if sess.get('cashed_out'):
        return {'error': 'Already cashed out'}
    bet, is_free = sess['bet'], sess['is_free']
    server_seed, seed_hash, nonce = sess['server_seed'], sess['seed_hash'], sess['nonce']
    crash_point = float(sess['crash_point'])
    start_ts = float(sess['start_ts'])
    now = time.time()
    current = _crash_multiplier_at(start_ts, now)
    if current >= crash_point:
        # Already crashed before cashout
        _delete_session(session_id)
        details = {'crash_point': crash_point, 'cashout_at': None}
        settled = settle_bet(user_id, 'crash', bet, 0, 'lose', details, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'crashed': True, 'crash_point': crash_point, 'multiplier': 0,
                'bet': bet, 'game': 'crash', 'done': True}
    cashout_mult = current
    win = round(bet * cashout_mult, 2)
    _delete_session(session_id)
    details = {'crash_point': crash_point, 'cashout_at': cashout_mult}
    settled = settle_bet(user_id, 'crash', bet, win, 'win', details, is_free, server_seed, seed_hash, nonce)
    return {**settled, 'crashed': False, 'crash_point': crash_point, 'multiplier': cashout_mult,
            'bet': bet, 'game': 'crash', 'done': True}

def play_crash_status(user_id, session_id):
    """Polled by the client to check if auto-cashout fired or crash hit."""
    sess = _load_session(session_id, user_id, 'crash')
    if not sess:
        return {'error': 'Invalid session'}
    bet, is_free = sess['bet'], sess['is_free']
    server_seed, seed_hash, nonce = sess['server_seed'], sess['seed_hash'], sess['nonce']
    crash_point = float(sess['crash_point'])
    start_ts = float(sess['start_ts'])
    auto = sess.get('auto_cashout')
    now = time.time()
    current = _crash_multiplier_at(start_ts, now)
    if auto and current >= float(auto) and float(auto) < crash_point:
        cashout_mult = round(float(auto), 2)
        win = round(bet * cashout_mult, 2)
        _delete_session(session_id)
        details = {'crash_point': crash_point, 'cashout_at': cashout_mult, 'auto': True}
        settled = settle_bet(user_id, 'crash', bet, win, 'win', details, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'crashed': False, 'crash_point': crash_point, 'multiplier': cashout_mult,
                'bet': bet, 'game': 'crash', 'done': True, 'auto': True}
    if current >= crash_point:
        _delete_session(session_id)
        details = {'crash_point': crash_point, 'cashout_at': None}
        settled = settle_bet(user_id, 'crash', bet, 0, 'lose', details, is_free, server_seed, seed_hash, nonce)
        return {**settled, 'crashed': True, 'crash_point': crash_point, 'multiplier': 0,
                'bet': bet, 'game': 'crash', 'done': True}
    return {'session_id': session_id, 'current_multiplier': current,
            'bet': bet, 'game': 'crash', 'done': False}
