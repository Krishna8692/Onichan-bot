"""
Device Fingerprint Spoofer
Generates randomized HTTP headers and browser fingerprint data per request
to make each card check appear from a different browser/device.
"""

import random
from typing import Dict, Optional


DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Samsung Galaxy S23) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.0.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 Samsung/5.0",
]

LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.8,en-US;q=0.7",
    "fr-FR,fr;q=0.9,en;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en;q=0.8",
    "it-IT,it;q=0.9,en;q=0.8",
    "pt-BR,pt;q=0.9,en;q=0.8",
    "ja-JP,ja;q=0.9,en;q=0.8",
]

SCREEN_SIZES = [
    (1920, 1080), (1366, 768), (1440, 900), (2560, 1440),
    (1280, 800), (1600, 900), (1920, 1200), (1024, 768),
    (2560, 1600), (3840, 2160),
]

TIMEZONES = [
    "America/New_York", "America/Los_Angeles", "America/Chicago",
    "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid",
    "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney",
    "America/Toronto", "America/Sao_Paulo",
]

PLATFORMS = ["Win32", "MacIntel", "Linux x86_64", "Linux aarch64"]


def get_spoofed_headers(mobile: bool = False) -> Dict[str, str]:
    """Generate a full set of randomized browser HTTP headers."""
    ua = random.choice(MOBILE_UAS if mobile else DESKTOP_UAS)
    lang = random.choice(LANGUAGES)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": lang,
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": str(random.randint(0, 1)),
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin"]),
        "Cache-Control": random.choice(["max-age=0", "no-cache"]),
    }
    if "Chrome" in ua or "Edg" in ua:
        ch_ua_ver = random.randint(120, 124)
        headers["Sec-Ch-Ua"] = (
            f'"Chromium";v="{ch_ua_ver}", "Google Chrome";v="{ch_ua_ver}", "Not-A.Brand";v="99"'
        )
        headers["Sec-Ch-Ua-Mobile"] = "?1" if mobile else "?0"
        headers["Sec-Ch-Ua-Platform"] = (
            '"Android"' if mobile else f'"{random.choice(["Windows", "macOS", "Linux"])}"'
        )
    return headers


def get_js_fingerprint() -> Dict[str, str]:
    """Return a dict of JS-side fingerprint values to inject."""
    w, h = random.choice(SCREEN_SIZES)
    return {
        "screenWidth": str(w),
        "screenHeight": str(h),
        "colorDepth": str(random.choice([24, 30, 32])),
        "pixelRatio": str(random.choice([1, 1.5, 2, 2.5, 3])),
        "timezone": random.choice(TIMEZONES),
        "platform": random.choice(PLATFORMS),
        "cookiesEnabled": "true",
        "doNotTrack": str(random.randint(0, 1)),
        "hardwareConcurrency": str(random.choice([2, 4, 6, 8, 12, 16])),
        "deviceMemory": str(random.choice([2, 4, 8, 16])),
    }


def get_random_proxy(proxy_type: str = "http") -> Optional[str]:
    """
    Pull one live residential proxy from the DB proxy_pool.
    Returns a proxy string like 'http://user:pass@host:port' or None.
    """
    try:
        from modules.database import _execute_with_retry
        def _op(conn):
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT host, port, username, password, proxy_type
                    FROM proxy_pool
                    WHERE alive = TRUE
                      AND (classification = 'residential' OR classification IS NULL)
                    ORDER BY RANDOM() LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    cur.execute("""
                        SELECT host, port, username, password, proxy_type
                        FROM proxy_pool WHERE alive = TRUE
                        ORDER BY RANDOM() LIMIT 1
                    """)
                    row = cur.fetchone()
                return row
        row = _execute_with_retry(_op)
        if not row:
            return None
        host, port, user, pwd, proto = row
        proto = (proto or proxy_type).lower()
        if user and pwd:
            return f"{proto}://{user}:{pwd}@{host}:{port}"
        return f"{proto}://{host}:{port}"
    except Exception:
        return None


def build_requests_kwargs(use_proxy: bool = True, mobile: bool = False,
                          timeout: int = 30) -> Dict:
    """Build a kwargs dict ready to pass to requests.get/post."""
    kwargs: Dict = {
        "headers": get_spoofed_headers(mobile=mobile),
        "timeout": timeout,
        "verify": True,
    }
    if use_proxy:
        proxy = get_random_proxy()
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
    return kwargs
