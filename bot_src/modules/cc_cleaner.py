"""
CC Cleaner - Extract, Clean, and Filter Credit Cards from Junk Text
Supports unlimited cards, BIN/country filtering, expired removal, and YYYY format.
"""

import re
from datetime import datetime


# ── Year normalization helpers ────────────────────────────────────────────────

def _normalize_year(raw: str) -> str:
    """Normalize raw year to 2-digit form.  '2031' → '31', '31' → '31'"""
    raw = raw.strip()
    if len(raw) == 4 and raw.isdigit():
        return raw[2:]
    return raw[-2:] if len(raw) >= 2 else raw.zfill(2)


def _year_to_full(raw: str) -> str:
    """Convert raw year to 4-digit form.  '31' → '2031', '2031' → '2031'"""
    raw = raw.strip()
    if len(raw) == 4 and raw.isdigit():
        return raw
    return f"20{raw[-2:]}" if len(raw) >= 2 else f"20{raw.zfill(2)}"


def _is_expired(mm: str, yy_raw: str) -> bool:
    """Return True if the card expiry date is in the past."""
    try:
        year4 = int(_year_to_full(yy_raw))
        month = int(mm)
        now = datetime.now()
        if year4 < now.year:
            return True
        if year4 == now.year and month < now.month:
            return True
        return False
    except Exception:
        return False


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_cards_from_junk(text: str, remove_expired: bool = True) -> list:
    """
    Extract valid credit card combos from any messy / junk text.

    Supported input formats:
      CC|MM|YY|CVV       CC|MM|YYYY|CVV
      CC:MM:YY:CVV       CC/MM/YY/CVV
      CC MM YY CVV       (space-separated)
      CC|MM|YY  (no CVV)

    Returns a list of dicts with keys: cc, mm, yy, yy4, cvv, card, brand, bin
    """
    cards = []
    seen = set()

    # Primary pattern: CC + sep + MM + sep + YY(YY) + sep + CVV(optional)
    pattern = re.compile(
        r'(\d{15,19})'
        r'[\s|:/\-,]+'
        r'(\d{1,2})'
        r'[\s|:/\-,]+'
        r'(\d{2,4})'
        r'(?:[\s|:/\-,]+(\d{3,4}))?'
    )

    for m in pattern.finditer(text):
        cc_raw  = m.group(1)
        mm_raw  = m.group(2).zfill(2)
        yy_raw  = m.group(3)
        cvv_raw = m.group(4) or "000"

        yy2  = _normalize_year(yy_raw)
        yy4  = _year_to_full(yy_raw)

        if not _validate_fields(cc_raw, mm_raw, yy2, cvv_raw):
            continue
        if remove_expired and _is_expired(mm_raw, yy_raw):
            continue

        brand    = get_card_brand(cc_raw)
        card_str = f"{cc_raw}|{mm_raw}|{yy4}|{cvv_raw}"

        if card_str in seen:
            continue
        seen.add(card_str)

        cards.append({
            "cc":    cc_raw,
            "mm":    mm_raw,
            "yy":    yy2,
            "yy4":   yy4,
            "cvv":   cvv_raw,
            "card":  card_str,
            "brand": brand,
            "bin":   cc_raw[:6],
        })

    return cards


def _validate_fields(cc: str, mm: str, yy: str, cvv: str) -> bool:
    """Validate individual card fields (Luhn, month range, digit-only)."""
    try:
        if not (cc.isdigit() and mm.isdigit() and yy.isdigit() and cvv.isdigit()):
            return False
        if not (15 <= len(cc) <= 19):
            return False
        if len(mm) != 2:
            return False
        if not (1 <= int(mm) <= 12):
            return False
        if not (3 <= len(cvv) <= 4):
            return False
        if not luhn_check(cc):
            return False
        return True
    except Exception:
        return False


# ── Luhn algorithm ────────────────────────────────────────────────────────────

def luhn_check(card_number: str) -> bool:
    """Validate card number using Luhn algorithm."""
    try:
        digits = [int(d) for d in str(card_number)]
        odd_digits  = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(int(x) for x in str(d * 2))
        return checksum % 10 == 0
    except Exception:
        return False


# ── Brand detection ───────────────────────────────────────────────────────────

def get_card_brand(cc: str) -> str:
    """Detect card network brand from BIN prefix."""
    if not cc:
        return "Unknown"
    try:
        d1  = cc[0]
        d2  = cc[:2]
        d4  = cc[:4]
        d6  = cc[:6]
        n4  = int(d4) if len(d4) == 4 and d4.isdigit() else 0

        if d1 == "4":
            return "VISA"
        if d2 in ("51", "52", "53", "54", "55") or (2221 <= n4 <= 2720):
            return "MASTERCARD"
        if d2 in ("34", "37"):
            return "AMEX"
        if d2 == "65" or d4 == "6011" or (
            d4[:3].isdigit() and 644 <= int(d4[:3]) <= 649
        ):
            return "DISCOVER"
        if d2 in ("36", "38") or (d4[:3].isdigit() and 300 <= int(d4[:3]) <= 305):
            return "DINERS"
        if d2 == "35":
            return "JCB"
        if d6.startswith("636"):
            return "ELO"
        if d2 in ("62", "81"):
            return "UNIONPAY"
    except Exception:
        pass
    return "Unknown"


# ── Filtering & cleaning ──────────────────────────────────────────────────────

def clean_and_format_cards(cards_input, remove_expired: bool = True) -> list:
    """
    Accept either a raw text string or a list of card dicts.
    Returns cleaned, de-duplicated list of card dicts.
    """
    if isinstance(cards_input, str):
        cards = extract_cards_from_junk(cards_input, remove_expired=remove_expired)
    else:
        cards = list(cards_input)
    return remove_duplicates(cards)


def remove_duplicates(cards: list) -> list:
    """Remove duplicate cards keeping the first occurrence."""
    seen  = set()
    unique = []
    for card in cards:
        key = card.get("card", "")
        if key not in seen:
            unique.append(card)
            seen.add(key)
    return unique


def remove_expired_cards(cards: list) -> list:
    """Remove expired cards from a list of card dicts."""
    return [c for c in cards if not _is_expired(c["mm"], c.get("yy4") or c["yy"])]


def filter_by_bin(cards: list, bin_prefixes: list) -> list:
    """
    Filter cards to only those whose number starts with any of the given prefixes.
    bin_prefixes: list of BIN strings, e.g. ['414740', '37', '5276']
    """
    if not bin_prefixes:
        return cards
    prefixes = [p.strip() for p in bin_prefixes if p.strip()]
    if not prefixes:
        return cards
    return [c for c in cards if any(c["cc"].startswith(p) for p in prefixes)]


def filter_by_country(cards: list, country_codes: list) -> list:
    """
    Filter cards by issuing country using BIN lookup.
    country_codes: list of 2-letter ISO codes, e.g. ['US', 'GB', 'IN']
    Falls back to returning all cards if lookup is unavailable.
    """
    if not country_codes:
        return cards
    codes_upper = {c.strip().upper() for c in country_codes if c.strip()}
    if not codes_upper:
        return cards

    try:
        from modules.gate_checker import get_bin_info
    except ImportError:
        return cards

    result = []
    for card in cards:
        try:
            info    = get_bin_info(card["cc"])
            country = info.get("country", {})
            if isinstance(country, dict):
                iso = (country.get("alpha2") or country.get("name") or "").upper()
            else:
                iso = str(country or "").upper()
            if iso in codes_upper:
                result.append(card)
        except Exception:
            pass
    return result


def filter_by_brand(cards: list, brands: list) -> list:
    """Filter cards to only those matching the given brands (VISA, MASTERCARD…)."""
    if not brands:
        return cards
    brands_upper = {b.strip().upper() for b in brands if b.strip()}
    return [c for c in cards if c.get("brand", "").upper() in brands_upper]


def sort_cards(cards: list, by: str = "brand") -> list:
    """Sort cards by 'brand', 'bin', or 'cc'."""
    return sorted(cards, key=lambda x: x.get(by if by in ("brand", "bin", "cc") else "brand", ""))


def get_statistics(cards) -> dict:
    """
    Return statistics for a card list or raw text string.
    """
    if isinstance(cards, str):
        cards = extract_cards_from_junk(cards)

    if not cards:
        return {"total": 0, "by_brand": {}, "unique_bins": 0}

    brands: dict = {}
    bins:   set  = set()

    for card in cards:
        brand = card.get("brand", "Unknown")
        brands[brand] = brands.get(brand, 0) + 1
        bins.add(card.get("bin", ""))

    return {
        "total":       len(cards),
        "by_brand":    brands,
        "unique_bins": len(bins),
    }


def cards_to_text(cards: list, use_4digit_year: bool = True) -> str:
    """
    Serialize card dicts to newline-delimited CC|MM|YYYY|CVV (or YY) text.
    """
    lines = []
    for c in cards:
        yy = c.get("yy4", c.get("yy", "")) if use_4digit_year else c.get("yy", "")
        lines.append(f"{c['cc']}|{c['mm']}|{yy}|{c['cvv']}")
    return "\n".join(lines)
