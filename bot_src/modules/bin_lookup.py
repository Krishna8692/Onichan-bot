"""
BIN Lookup Module - Get card info from BIN
Uses multiple APIs with caching for reliability
"""

import requests
import aiohttp

BIN_API_URL = "https://bindb.rythampkhandelwal.workers.dev/bin/{bin}"

_cache = {}

def _flag(code2: str) -> str:
    if not code2 or len(code2) != 2:
        return "🌍"
    try:
        return chr(0x1F1E6 + ord(code2[0].upper()) - 65) + chr(0x1F1E6 + ord(code2[1].upper()) - 65)
    except Exception:
        return "🌍"


def lookup_bin(bin_number: str) -> dict:
    """Lookup BIN info — tries fast API first, binlist fallback"""
    bin_6 = str(bin_number)[:6]
    if len(bin_6) < 6:
        return _unknown(bin_6)

    if bin_6 in _cache:
        return _cache[bin_6]

    try:
        res = requests.get(BIN_API_URL.format(bin=bin_6), timeout=6)
        if res.status_code == 200:
            data = res.json()
            result = {
                "success": True,
                "bin": bin_6,
                "brand": (data.get("Brand") or "Unknown").upper(),
                "type": (data.get("Type") or "Unknown").upper(),
                "level": (data.get("Category") or "").upper(),
                "bank": (data.get("Issuer") or "Unknown").upper(),
                "country": (data.get("CountryName") or "Unknown").upper(),
                "country_emoji": _flag(data.get("isoCode2", "")),
                "country_code": (data.get("isoCode2") or "XX").upper()
            }
            _cache[bin_6] = result
            return result
    except Exception:
        pass

    try:
        res = requests.get(f"https://lookup.binlist.net/{bin_6}", timeout=6, headers={
            "Accept-Version": "3"
        })
        if res.status_code == 200:
            data = res.json()
            country = data.get("country", {})
            result = {
                "success": True,
                "bin": bin_6,
                "brand": (data.get("scheme") or "Unknown").upper(),
                "type": (data.get("type") or "Unknown").upper(),
                "level": (data.get("brand") or "").upper(),
                "bank": (data.get("bank", {}) or {}).get("name", "Unknown"),
                "country": (country.get("name") or "Unknown").upper(),
                "country_emoji": country.get("emoji", "🌍"),
                "country_code": (country.get("alpha2") or "XX").upper()
            }
            _cache[bin_6] = result
            return result
    except Exception:
        pass

    return _unknown(bin_6)


async def lookup_bin_async(bin_number: str) -> dict:
    """Async BIN lookup with aiohttp"""
    bin_6 = str(bin_number)[:6]
    if len(bin_6) < 6:
        return _unknown(bin_6)

    if bin_6 in _cache:
        return _cache[bin_6]

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
            async with session.get(BIN_API_URL.format(bin=bin_6)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    result = {
                        "success": True,
                        "bin": bin_6,
                        "brand": (data.get("Brand") or "Unknown").upper(),
                        "type": (data.get("Type") or "Unknown").upper(),
                        "level": (data.get("Category") or "").upper(),
                        "bank": (data.get("Issuer") or "Unknown").upper(),
                        "country": (data.get("CountryName") or "Unknown").upper(),
                        "country_emoji": _flag(data.get("isoCode2", "")),
                        "country_code": (data.get("isoCode2") or "XX").upper()
                    }
                    _cache[bin_6] = result
                    return result
    except Exception:
        pass

    return _unknown(bin_6)


def _unknown(bin_6: str = "") -> dict:
    brand = "VISA" if bin_6.startswith("4") else "MASTERCARD" if bin_6.startswith("5") else "AMEX" if bin_6.startswith("3") else "UNKNOWN"
    return {
        "success": False,
        "bin": bin_6,
        "brand": brand,
        "type": "UNKNOWN",
        "level": "",
        "bank": "Unknown",
        "country": "Unknown",
        "country_emoji": "🌍",
        "country_code": "XX"
    }


def format_bin_block(b: dict) -> str:
    """Format BIN info into a compact display block"""
    flag = b.get("country_emoji", "🌍")
    cc = b.get("country_code", "")
    country = f"{flag} {b.get('country', 'Unknown')} ({cc})" if cc else b.get("country", "Unknown")
    return (
        f"BIN → {b.get('bin', '?')} — {b.get('brand', '?')} — {b.get('type', '?')}\n"
        f"Product → {b.get('level', '?')}\n"
        f"Bank → {b.get('bank', '?')}\n"
        f"Country → {country}"
    )


def _build_network_line(bin_info):
    """Build network line without duplicates"""
    brand = bin_info.get('brand', 'Unknown')
    card_type = bin_info.get('type', '')
    level = bin_info.get('level', '')
    seen = {brand.upper()}
    parts = [brand]
    if card_type and card_type.upper() not in ('UNKNOWN', '') and card_type.upper() not in seen:
        seen.add(card_type.upper())
        parts.append(card_type)
    if level and level.upper() not in ('UNKNOWN', '') and level.upper() not in seen:
        parts.append(level)
    return " • ".join(parts)


def format_mass_card_result(
    card_str: str,
    status: str,
    response: str,
    gate_name: str = "Auth",
    time_taken: float = 0,
    username: str = None
) -> str:
    """Format individual card result for mass checking — compact"""
    from config import SUPPORT_USERNAME

    cc = card_str.split("|")[0] if "|" in card_str else card_str[:16]
    bin_info = lookup_bin(cc)

    if status.upper() in ["CHARGED", "APPROVED", "LIVE", "SUCCESS", "CVV"]:
        status_line = "Approved ✅"
    elif status.upper() in ["DECLINED", "DEAD"]:
        status_line = "Declined ❌"
    else:
        status_line = "Error ⚠️"

    if len(response) > 60:
        response = response[:57] + "..."

    sep = "━━━━━━━━━━━━━━━━━━━━"

    result = f"""💜 <b>ONICHAN • {gate_name.upper()}</b>
{sep}
💳 <code>{card_str}</code>
{sep}
📉 <b>Status</b>   : {status_line}
💬 <b>Response</b> : {response}
{sep}
🔢 <b>BIN</b>      : {bin_info.get('bin', cc[:6])}
💠 <b>Network</b>  : {_build_network_line(bin_info)}
🏦 <b>Bank</b>     : {bin_info.get('bank', 'Unknown')}
🌍 <b>Country</b>  : {bin_info.get('country', 'Unknown')}
{sep}
⏱ <b>Time</b>     : {time_taken:.2f}s"""

    if username:
        result += f"\n👤 <b>User</b>     : @{username}"
    result += f"\n⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"
    return result


def format_mass_header(total: int, approved: int, declined: int, errors: int, gate_name: str = "") -> str:
    """Format mass check header — compact"""
    sep = "━━━━━━━━━━━━━━━━━━━━"
    gate_label = f" • {gate_name.upper()}" if gate_name else ""
    return f"""💜 <b>ONICHAN{gate_label} • MASS DONE</b>
{sep}
📊 <b>Total</b> : {total} | ✅ {approved} | ❌ {declined} | ⚠️ {errors}
{sep}"""


def format_enhanced_response(
    cc: str,
    status: str,
    response: str,
    gate_name: str,
    time_taken: float = 0,
    username: str = None,
    proxy_status: str = "Live ☁️"
) -> str:
    """Format enhanced response — compact"""
    from config import SUPPORT_USERNAME

    parts = cc.split("|")
    cc_num = parts[0] if parts else cc[:16]
    bin_info = lookup_bin(cc_num)

    if status.upper() in ["CHARGED", "APPROVED", "LIVE", "SUCCESS"]:
        status_line = "Approved ✅"
    elif status.upper() in ["DECLINED", "DEAD"]:
        status_line = "Declined ❌"
    else:
        status_line = "Error ⚠️"

    if len(response) > 60:
        response = response[:57] + "..."

    sep = "━━━━━━━━━━━━━━━━━━━━"

    msg = f"""💜 <b>ONICHAN • {gate_name.upper()}</b>
{sep}
💳 <code>{cc}</code>
{sep}
📉 <b>Status</b>   : {status_line}
💬 <b>Response</b> : {response}
{sep}
🔢 <b>BIN</b>      : {bin_info.get('bin', cc_num[:6])}
💠 <b>Network</b>  : {_build_network_line(bin_info)}
🏦 <b>Bank</b>     : {bin_info.get('bank', 'Unknown')}
🌍 <b>Country</b>  : {bin_info.get('country', 'Unknown')}
{sep}
⏱ <b>Time</b>     : {time_taken:.2f}s"""

    if username:
        msg += f"\n👤 <b>User</b>     : @{username}"
    msg += f"\n⚡ <b>Powered</b>  : @{SUPPORT_USERNAME}"
    return msg
