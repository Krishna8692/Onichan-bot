import re
import os
import asyncio
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from typing import List, Tuple, Optional, Dict

# ── BIN lookup adapter using Onichan's gate_checker module ──────────────────
import random
from modules.cc_cleaner import extract_cards_from_junk, remove_duplicates
from modules.bin_lookup import lookup_bin

async def _lookup_bin_async(bin6: str) -> dict:
    try:
        from modules.gate_checker import get_bin_info
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_bin_info, bin6)
        return info or {}
    except Exception:
        return {}


# Card Brand Detector
def detect_card_brand(card_num: str) -> str:
    if card_num.startswith(('300', '305', '36', '38')):
        return 'Diners Club'
    elif card_num.startswith('4'):
        return 'Visa'
    elif any(card_num.startswith(p) for p in ('51', '52', '53', '54', '55')) or (len(card_num) >= 4 and 2221 <= int(card_num[:4]) <= 2720):
        return 'Mastercard'
    elif card_num.startswith(('34', '37')):
        return 'Amex'
    elif card_num.startswith(('6011', '65', '644', '645')):
        return 'Discover'
    elif card_num.startswith(('3528', '3589')) or (len(card_num) >= 4 and 3528 <= int(card_num[:4]) <= 3589):
        return 'JCB'
    return 'Other'

BRAND_ORDER = {'Visa': 1, 'Mastercard': 2, 'Amex': 3, 'Discover': 4, 'JCB': 5, 'Diners Club': 6, 'Other': 7}

# Card Validator
def is_valid_card(card: str, month: str, year: str, cvv: str) -> bool:
    if not (13 <= len(card) <= 19 and card.isdigit()):
        return False
    if not month.isdigit() or not (1 <= int(month) <= 12):
        return False

    curr_year = datetime.now().year
    curr_month = datetime.now().month
    exp_year = int(year) + 2000 if len(year) == 2 else int(year)

    if exp_year < curr_year:
        return False
    if exp_year == curr_year and int(month) < curr_month:
        return False

    if not (3 <= len(cvv) <= 4 and cvv.isdigit()):
        return False

    return True

# 1. Clean & Sort
def clean_and_sort_cards_text(raw_text: str, delimiter: str = '|', sort_by: str = 'brand') -> Tuple[str, Dict]:
    """
    Full clean+sort pipeline supporting multi-delimiter input.
    Returns (output_text, stats_dict).
    """
    lines = raw_text.split('\n')
    seen = set()

    brand_counts = {'Visa': 0, 'Mastercard': 0, 'Amex': 0, 'Discover': 0, 'JCB': 0, 'Diners Club': 0, 'Other': 0}
    invalid_count = 0
    duplicate_count = 0

    card_entries = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        matches = re.findall(r'(\d{13,19})[|/:\s;]+(\d{1,2})[|/:\s;]+(\d{2,4})[|/:\s;]+(\d{3,4})', line_str)
        if not matches:
            invalid_count += 1
            continue

        card, month, year, cvv = matches[0]
        month = month.zfill(2)
        year_str = year[-2:] if len(year) >= 2 else year.zfill(2)

        formatted = f"{card}|{month}|{year_str}|{cvv}"

        if not is_valid_card(card, month, year_str, cvv):
            invalid_count += 1
            continue

        if formatted in seen:
            duplicate_count += 1
            continue

        seen.add(formatted)
        brand = detect_card_brand(card)
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
        card_entries.append((brand, formatted))

    card_entries.sort(key=lambda x: (BRAND_ORDER.get(x[0], 99), x[1]))

    sorted_lines = [entry[1] for entry in card_entries]
    output_text = "\n".join(sorted_lines)

    stats = {
        'total_input': len(lines),
        'valid_total': len(sorted_lines),
        'invalid_count': invalid_count,
        'duplicate_count': duplicate_count,
        'brand_counts': brand_counts
    }
    return output_text, stats

def estimate_bin_country(bin_prefix: str) -> Optional[Dict]:
    """Quick BIN country lookup."""
    try:
        padded = bin_prefix + "0" * max(0, 16 - len(bin_prefix))
        return lookup_bin(padded)
    except Exception:
        return None

# 2. Split (Lines per file)
def split_text_lines_per_file(text: str, lines_per_file: int) -> List[str]:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return []
    lines_per_file = max(1, lines_per_file)

    parts = []
    for i in range(0, len(lines), lines_per_file):
        chunk = lines[i:i + lines_per_file]
        if chunk:
            parts.append("\n".join(chunk))
    return parts

def split_text_n_parts(text: str, n_parts: int) -> List[str]:
    return split_text_lines_per_file(text, n_parts)

# 3. Find BIN
def filter_by_bin_prefix(text: str, bin_prefix: str) -> Tuple[str, int]:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    matched = []
    clean_bin = re.sub(r'\D', '', bin_prefix)

    for line in lines:
        card_matches = re.findall(r'(\d{13,19})', line)
        if card_matches:
            target_bin = card_matches[0]
            if target_bin.startswith(clean_bin):
                matched.append(line)

    return "\n".join(matched), len(matched)

# 4. Group by Country
async def group_text_by_country(text: str) -> Tuple[Dict[str, List[str]], Dict[str, Dict]]:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    country_groups: Dict[str, List[str]] = {}
    country_meta: Dict[str, Dict] = {}

    unique_bins = set()
    line_bin_map = []

    for line in lines:
        matches = re.findall(r'(\d{6,19})', line)
        if matches:
            bin6 = matches[0][:6]
            unique_bins.add(bin6)
            line_bin_map.append((bin6, line))

    # Perform async BIN lookups concurrently
    bin_results = {}
    tasks = {b6: _lookup_bin_async(b6) for b6 in list(unique_bins)[:150]}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for b6, result in zip(tasks.keys(), results):
        bin_results[b6] = result if isinstance(result, dict) else {}

    for bin6, line in line_bin_map:
        info = bin_results.get(bin6, {})
        country_name = info.get('country') or info.get('country_name') or 'Unknown'
        flag = info.get('emoji') or info.get('flag') or '🌐'
        code = info.get('country_code') or info.get('code') or 'UNK'

        if country_name not in country_groups:
            country_groups[country_name] = []
            country_meta[country_name] = {'flag': flag, 'code': code}

        country_groups[country_name].append(line)

    return country_groups, country_meta

def pick_random_cards(cards: List[str], n: int) -> List[str]:
    """Pick N random cards from a list without replacement."""
    if n >= len(cards):
        return cards[:]
    return random.sample(cards, n)

def get_country_stats(cards: List[str]) -> Dict[str, int]:
    """Get country distribution of cards via BIN lookup."""
    stats: Dict[str, int] = {}
    for card in cards:
        parts = re.split(r'[|/\s]', card.strip())
        if not parts:
            continue
        cc_num = parts[0]
        if len(cc_num) < 6:
            stats["Unknown"] = stats.get("Unknown", 0) + 1
            continue
        try:
            info = lookup_bin(cc_num + "0" * max(0, 16 - len(cc_num)))
            if info:
                country = info.get("country", "Unknown")
                flag = info.get("emoji", "")
                key = f"{flag} {country}".strip() if flag else country
                stats[key] = stats.get(key, 0) + 1
            else:
                stats["Unknown"] = stats.get("Unknown", 0) + 1
        except Exception:
            stats["Unknown"] = stats.get("Unknown", 0) + 1
    return dict(sorted(stats.items(), key=lambda x: -x[1]))

def split_cards(cards: List[str], n: int) -> List[List[str]]:
    """Split card list into N roughly equal chunks."""
    if n <= 0:
        return [cards]
    chunk_size = max(1, len(cards) // n)
    chunks = []
    for i in range(0, len(cards), chunk_size):
        chunk = cards[i:i + chunk_size]
        if chunk:
            chunks.append(chunk)
    # Merge last chunk if too small
    if len(chunks) > n:
        last = chunks.pop()
        chunks[-1].extend(last)
    return chunks

def get_brand_stats(cards: List[str]) -> Dict[str, int]:
    """Get brand distribution of cards."""
    from modules.cc_generator import get_card_brand
    stats: Dict[str, int] = {}
    for card in cards:
        parts = re.split(r'[|/\s]', card.strip())
        if parts:
            brand = get_card_brand(parts[0])
            stats[brand] = stats.get(brand, 0) + 1
    return dict(sorted(stats.items(), key=lambda x: -x[1]))

def filter_by_country_lookup(cards: List[str], country_codes: List[str]) -> List[str]:
    """Filter cards by country using BIN lookup."""
    codes_upper = [c.upper() for c in country_codes]
    result = []
    for card in cards:
        parts = re.split(r'[|/\s]', card.strip())
        if not parts:
            continue
        cc_num = parts[0]
        if len(cc_num) < 6:
            continue
        try:
            info = lookup_bin(cc_num + "0" * max(0, 16 - len(cc_num)))
            if info and info.get("country_code", "").upper() in codes_upper:
                result.append(card)
        except Exception:
            pass
    return result

def format_cards_as_text(cards: List[str]) -> str:
    """Format card list as a clean newline-separated text."""
    return '\n'.join(cards)

def parse_cards_from_text(text: str) -> List[str]:
    """Parse cards from raw text content."""
    cards = extract_cards_from_junk(text, remove_expired=True)
    return remove_duplicates(cards)
