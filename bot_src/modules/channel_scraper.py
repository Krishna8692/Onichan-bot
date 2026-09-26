"""
Telegram Channel Scraper
Monitors configured public channels for card dumps and forwards valid cards
to the bot owner's DM automatically.
"""

import os
import sys
import re
import asyncio
import threading
from datetime import datetime
from typing import List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import _execute_with_retry, get_connection_with_retry

_bot_ref = None
_owner_id: Optional[int] = None
_running = False
_monitor_channels: List[str] = []

CC_PATTERN = re.compile(
    r'\b([3-9]\d{11,18})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b'
)
LUHN_RE = re.compile(r'\b\d{13,19}\b')


def _luhn_check(number: str) -> bool:
    try:
        digits = [int(d) for d in number]
        odd = digits[-1::-2]
        even = [sum(divmod(d * 2, 10)) for d in digits[-2::-2]]
        return (sum(odd) + sum(even)) % 10 == 0
    except Exception:
        return False


def extract_cards_from_text(text: str) -> List[dict]:
    """Extract card numbers in CC|MM|YY|CVV format from raw text."""
    cards = []
    seen: Set[str] = set()
    for m in CC_PATTERN.finditer(text):
        cc, mm, yy, cvv = m.group(1), m.group(2), m.group(3), m.group(4)
        if not _luhn_check(cc):
            continue
        key = f"{cc}|{mm}|{yy}|{cvv}"
        if key not in seen:
            seen.add(key)
            cards.append({"cc": cc, "mm": mm, "yy": yy, "cvv": cvv, "raw": key})
    return cards


def init_scraper_tables() -> bool:
    conn = get_connection_with_retry()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scraper_channels (
                    id SERIAL PRIMARY KEY,
                    channel_username VARCHAR(255) UNIQUE NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    cards_found INTEGER DEFAULT 0,
                    added_by BIGINT,
                    added_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scraped_cards (
                    id SERIAL PRIMARY KEY,
                    channel VARCHAR(255),
                    card_raw VARCHAR(100) NOT NULL,
                    cc VARCHAR(20),
                    mm VARCHAR(4),
                    yy VARCHAR(6),
                    cvv VARCHAR(5),
                    found_at TIMESTAMP DEFAULT NOW()
                )
            """)
        return True
    except Exception as e:
        print(f"[ChannelScraper] Table init error: {e}")
        return False


def add_channel(channel: str, added_by: int) -> bool:
    channel = channel.lstrip("@").strip()
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scraper_channels (channel_username, added_by)
                VALUES (%s, %s) ON CONFLICT (channel_username) DO UPDATE SET is_active=TRUE
            """, (channel, added_by))
        return True
    return bool(_execute_with_retry(_op))


def remove_channel(channel: str) -> bool:
    channel = channel.lstrip("@").strip()
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scraper_channels SET is_active=FALSE WHERE channel_username=%s",
                (channel,))
        return True
    return bool(_execute_with_retry(_op))


def get_active_channels() -> List[str]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT channel_username FROM scraper_channels WHERE is_active=TRUE
            """)
            return [r[0] for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


def _store_cards(channel: str, cards: List[dict]) -> None:
    def _op(conn):
        with conn.cursor() as cur:
            for c in cards:
                cur.execute("""
                    INSERT INTO scraped_cards (channel, card_raw, cc, mm, yy, cvv)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (channel, c["raw"], c["cc"], c["mm"], c["yy"], c["cvv"]))
            cur.execute("""
                UPDATE scraper_channels SET cards_found = cards_found + %s
                WHERE channel_username=%s
            """, (len(cards), channel))
    _execute_with_retry(_op)


def get_scraper_stats() -> List[dict]:
    def _op(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT channel_username, is_active, cards_found, added_at
                FROM scraper_channels ORDER BY cards_found DESC
            """)
            return [{"channel": r[0], "active": r[1], "found": r[2], "added": r[3]}
                    for r in cur.fetchall()]
    return _execute_with_retry(_op) or []


async def scrape_once(bot, owner_id: int) -> int:
    """
    Scrape all active channels once using the bot's get_updates mechanism.
    Returns number of cards found.
    Note: Telegram bots cannot read channel history directly.
    This monitors channels the bot has been added to as admin.
    """
    channels = get_active_channels()
    total_found = 0
    for channel in channels:
        try:
            updates = await bot.get_chat(f"@{channel}")
            _ = updates
        except Exception:
            pass
    return total_found


def process_channel_message(channel: str, text: str, bot=None, owner_id: int = None) -> int:
    """
    Call this from a message handler when a message arrives from a monitored channel.
    Returns number of cards extracted.
    """
    if not text:
        return 0
    cards = extract_cards_from_text(text)
    if not cards:
        return 0
    _store_cards(channel, cards)
    if bot and owner_id and cards:
        lines = "\n".join(f"<code>{c['raw']}</code>" for c in cards[:20])
        msg = (f"🃏 <b>Channel Scraper Hit</b>\n"
               f"📢 <b>Channel:</b> @{channel}\n"
               f"💳 <b>Cards ({len(cards)}):</b>\n{lines}")
        asyncio.create_task(
            bot.send_message(chat_id=owner_id, text=msg, parse_mode="HTML")
        )
    return len(cards)
