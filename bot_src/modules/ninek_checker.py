"""
9kboss.com account checker module.
Handles login (with CAPTCHA), balance, VIP level, and withdrawal records.
"""

import hashlib
import hmac
import secrets
import time
import base64
import html
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_OK = True
except ImportError:
    CURL_CFFI_OK = False

BASE = "https://9kboss.com"
ST_VAL = "-5.5"  # India timezone: UTC+5:30 → getTimezoneOffset()/60 = -5.5

# --- Pending login sessions: (user_id, email) → {session, proxy, password} ---
_PENDING: Dict[Tuple[int, str], Dict] = {}

# --- Cached auth tokens: (user_id, email) → {token, expiry, salt, password_hash} ---
# A cached session must only be used for the credentials that created it.
_TOKEN_CACHE: Dict[Tuple[int, str], Dict] = {}


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.sha256(salt + password.encode("utf-8")).digest()


# ── Signature helpers ────────────────────────────────────────────────────────

def _compute_stt(url_path: str, st: str = ST_VAL) -> str:
    """Compute the STT request signature required by 9kboss API."""
    # Secret embedded in RPX JS bundle (chunk 6639); combined with path + ST offset.
    raw = f"#kfdjksgjdksajgkdsjkdjfkda#{url_path}#{st}"
    return hashlib.md5(raw.encode()).hexdigest()


def _build_headers(url_path: str, token: Optional[str] = None) -> dict:
    """Return the minimal required headers for a 9kboss API request."""
    h = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Origin": BASE,
        "Referer": f"{BASE}/login",
        "COUNTRY": "IN",
        "LANG": "en",
        "ST": ST_VAL,
        "STT": _compute_stt(url_path, ST_VAL),
    }
    if token:
        h["Auth"] = token
    return h


def _post_headers(url_path: str, token: Optional[str] = None) -> dict:
    h = _build_headers(url_path, token)
    h["Content-Type"] = "application/json;charset=UTF-8"
    return h


# ── Proxy helpers ────────────────────────────────────────────────────────────

_FALLBACK_PROXIES = [
    "http://34.131.37.209:40001",
    "http://45.195.90.142:8080",
    "http://45.195.90.228:8080",
    "http://45.194.3.132:8080",
]
_BAD_ROUTES: Dict[str, float] = {}


def _route_id(proxy) -> str:
    return proxy["https"] if proxy else "direct"


def _mark_route_failed(proxy) -> None:
    _BAD_ROUTES[_route_id(proxy)] = time.monotonic() + 90


def _proxy_candidates():
    """Try fresh Indian routes first, then fallbacks, then direct access."""
    urls = []
    try:
        from modules.database import _execute_with_retry
        rows = _execute_with_retry(
            """SELECT host, port, proxy_type FROM proxy_pool
               WHERE alive = TRUE AND country_code = 'IN'
               ORDER BY last_checked DESC NULLS LAST LIMIT 8""",
            fetch=True,
        )
        for row in rows or []:
            if str(row["proxy_type"]).lower() in ("http", "https"):
                urls.append(f"http://{row['host']}:{row['port']}")
    except Exception:
        pass
    for url in _FALLBACK_PROXIES:
        if url not in urls:
            urls.append(url)
    candidates = [{"http": url, "https": url} for url in urls] + [None]
    now = time.monotonic()
    return [p for p in candidates if _BAD_ROUTES.get(_route_id(p), 0) <= now] or [None]


def _get_proxy() -> Optional[Dict[str, str]]:
    """Preferred route for authenticated lookups."""
    return _proxy_candidates()[0]


def _new_session() -> "cffi_requests.Session":
    return cffi_requests.Session(impersonate="chrome120")


# ── Public API ───────────────────────────────────────────────────────────────

def start_captcha_flow(
    user_id: int, email: str, password: str
) -> Tuple[bool, Optional[bytes], str]:
    """
    Begin the login flow for (user_id, email).
    Downloads a CAPTCHA image and stores the session so complete_login can reuse it.
    Returns (ok, captcha_image_bytes, message).
    """
    if not CURL_CFFI_OK:
        return False, None, "curl_cffi not installed"

    # The homepage request is not required to obtain an image and can fail
    # with a proxy CONNECT 500 even when the CAPTCHA endpoint is reachable.
    for proxy in _proxy_candidates():
        try:
            s = _new_session()
            r = s.get(
                f"{BASE}/api/auth/image_code?t={int(time.time() * 1000)}",
                headers={"COUNTRY": "IN", "LANG": "en", "Accept": "image/png,image/*,*/*"},
                proxies=proxy,
                timeout=6,
            )
            if r.status_code != 200 or not r.content.startswith(b"\x89PNG\r\n\x1a\n"):
                _mark_route_failed(proxy)
                continue
            _PENDING[(user_id, email)] = {
                "session": s,
                "proxy": proxy,
                "password": password,
                "created": time.monotonic(),
            }
            return True, bytes(r.content), "ok"
        except Exception:
            _mark_route_failed(proxy)
            continue
    return False, None, "9kBoss CAPTCHA is unreachable through all available routes."


def solve_text_captcha(image: bytes, api_key: str) -> str:
    """Submit a PNG to Nopecha's textcaptcha recognition API; poll for text."""
    url = "https://api.nopecha.com/v1/recognition/textcaptcha"
    headers = {"Authorization": f"Basic {api_key}"}
    s = _new_session()
    try:
        response = s.post(
            url,
            json={"image_data": ["data:image/png;base64," + base64.b64encode(image).decode("ascii")]},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        job_id = data.get("data")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("Nopecha did not accept the CAPTCHA image")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(2)
            result = s.get(url, params={"id": job_id}, headers=headers, timeout=8)
            result.raise_for_status()
            body = result.json()
            answer = body.get("data")
            if isinstance(answer, list) and answer and isinstance(answer[0], str):
                code = answer[0].strip()
                if code:
                    return code
            if body.get("error") not in (9, 14) and "incomplete" not in str(
                body.get("message", "")
            ).lower():
                raise ValueError("Nopecha could not solve this CAPTCHA")
    except Exception as exc:
        # Never include Authorization headers or API key in bot responses.
        raise ValueError("Nopecha solver unavailable") from exc
    raise TimeoutError("Nopecha solver timed out")


def check_account_auto(user_id: int, email: str, password: str):
    """Solve in a worker thread; return (ok, result, error, manual_image)."""
    api_key = os.environ.get("NOPECHA_API_KEY")
    if not api_key:
        return False, {}, "Nopecha is not configured", None
    for attempt in range(2):
        fetched, image, error = start_captcha_flow(user_id, email, password)
        if not fetched:
            return False, {}, error, None
        try:
            code = solve_text_captcha(image, api_key)
        except (ValueError, TimeoutError):
            # The pending session still holds the original CAPTCHA.
            return False, {}, "Automatic CAPTCHA solving unavailable", image
        ok, result, error = complete_login(user_id, email, password, code)
        if ok:
            return True, result, "", None
        if "connection to 9kboss failed" in error.lower():
            # The failing route was put on cooldown; a new attempt fetches
            # a new challenge through another route.
            if attempt == 0:
                continue
            return False, {}, error, None
        if not any(word in error.lower() for word in ("captcha", "image code")):
            return False, {}, error, None
    # A failed challenge cannot be reused: send a fresh one for manual entry.
    fetched, image, error = start_captcha_flow(user_id, email, password)
    return False, {}, "Automatic CAPTCHA answer was rejected", image if fetched else None


def complete_login(
    user_id: int,
    email: str,
    password: str,
    captcha_code: str,
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Complete the login for (user_id, email) using the stored session + captcha code.
    Only succeeds when the provided password matches what was used in start_captcha_flow,
    so a different user cannot hijack another's pending session.
    Returns (ok, result_dict, error_message).
    result_dict keys: token, user_info, last_withdraw
    """
    if not CURL_CFFI_OK:
        return False, {}, "curl_cffi not installed"

    # Retrieve stored session (keyed to this user_id + email)
    pending = _PENDING.pop((user_id, email), None)
    if (pending and pending.get("password") == password
            and time.monotonic() - pending["created"] < 180):
        s = pending["session"]
        proxy = pending["proxy"]
    else:
        return False, {}, "CAPTCHA session expired. Send /9k email:password again."

    # ── 1. Login ─────────────────────────────────────────────────────────────
    login_path = "/api/auth/login"
    try:
        r = s.post(
            BASE + login_path,
            json={"username": email, "password": password, "imageCode": captcha_code.strip()},
            headers=_post_headers(login_path),
            proxies=proxy,
            timeout=15,
        )
    except Exception:
        _mark_route_failed(proxy)
        return False, {}, "Connection to 9kBoss failed. Please retry the command."

    if r.status_code != 200:
        _mark_route_failed(proxy)
        return False, {}, f"Login HTTP error {r.status_code}"

    try:
        data = r.json()
    except Exception:
        return False, {}, "Invalid JSON from login endpoint"

    status = data.get("status")
    if status != 0:
        msg = data.get("message") or data.get("msg") or "Login failed"
        return False, {}, str(msg)

    # Token: check response headers first, then body
    token = (
        r.headers.get("Auth")
        or r.headers.get("auth")
        or _deep_get(data, "data", "token")
        or _deep_get(data, "data", "userInfo", "token")
        or _deep_get(data, "token")
    )
    if not token:
        return False, {}, "Login succeeded but no auth token in response"

    # ── 2. User detail info ──────────────────────────────────────────────────
    user_info = _fetch_user_info(s, token, proxy)
    if not user_info:
        return False, {}, "Login succeeded, but account details could not be retrieved. Please try again."

    # Cache only after both login and account-detail fetch succeed.
    salt = secrets.token_bytes(16)
    _TOKEN_CACHE[(user_id, email)] = {
        "token": token,
        "expiry": time.time() + 18000,
        "salt": salt,
        "password_hash": _password_hash(password, salt),
        "proxy": proxy,
    }

    # Withdrawal history endpoint has not been confirmed. Do not run a
    # series of speculative requests during an account check.
    last_withdraw = None

    return True, {
        "token": token,
        "user_info": user_info,
        "last_withdraw": last_withdraw,
    }, ""


def check_with_token(
    user_id: int, email: str, password: str
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Try to check account (user_id, email) using the caller's own cached auth token.
    A token cached for user A is never returned to user B.
    Returns (ok, result_dict, error_message).
    """
    cached = _TOKEN_CACHE.get((user_id, email))
    if not cached or time.time() >= cached["expiry"]:
        return False, {}, "No valid cached token"
    if not hmac.compare_digest(
        cached["password_hash"], _password_hash(password, cached["salt"])
    ):
        return False, {}, "Credentials do not match the verified session"

    token = cached["token"]
    user_info = {}
    preferred = cached.get("proxy")
    routes = [preferred] + [p for p in _proxy_candidates() if p != preferred]
    for proxy in routes[:4]:
        s = _new_session()
        user_info = _fetch_user_info(s, token, proxy)
        if user_info:
            cached["proxy"] = proxy
            break
    if not user_info:
        # A network error is not evidence that the token expired.
        return False, {}, "Account details temporarily unavailable"

    last_withdraw = None
    return True, {"token": token, "user_info": user_info, "last_withdraw": last_withdraw}, ""


# ── Internal fetch helpers ───────────────────────────────────────────────────

def _fetch_user_info(s, token: str, proxy: dict) -> dict:
    """Fetch /api/user/user_detail_info and return the raw data dict."""
    path = "/api/user/user_detail_info"
    try:
        r = s.get(
            BASE + path,
            headers=_build_headers(path, token),
            proxies=proxy,
            timeout=12,
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == 0:
                return d.get("data") or {}
    except Exception:
        pass
    return {}


def _fetch_last_withdraw(s, token: str, proxy: dict) -> Optional[dict]:
    """
    Try several known withdrawal record endpoints.
    Returns the most-recent withdrawal entry as a dict, or None.
    """
    endpoints = [
        ("/api/pay/withdraw_record_page", "GET"),
        ("/api/finance/withdraw_record", "GET"),
        ("/api/pay/withdraw_list", "GET"),
        ("/api/pay/withdraw_record", "GET"),
        ("/api/user/order_list", "GET"),
        ("/api/finance/record_page", "GET"),
        ("/api/user/withdraw_list", "GET"),
    ]
    for path, method in endpoints:
        try:
            h = _build_headers(path, token)
            if method == "GET":
                r = s.get(BASE + path, headers=h, proxies=proxy, timeout=8)
            else:
                r = s.post(
                    BASE + path,
                    json={"pageNo": 1, "pageSize": 10},
                    headers={**h, "Content-Type": "application/json;charset=UTF-8"},
                    proxies=proxy,
                    timeout=8,
                )
            if r.status_code != 200:
                continue
            d = r.json()
            if d.get("status") != 0:
                continue
            records = (
                _deep_get(d, "data", "list")
                or _deep_get(d, "data", "records")
                or d.get("data")
                or []
            )
            if isinstance(records, list) and records:
                return _parse_withdraw_record(records[0])
        except Exception:
            continue
    return None


def _parse_withdraw_record(rec: dict) -> dict:
    """Normalise a withdrawal record into a standard dict."""
    status_raw = rec.get("status") or rec.get("orderStatus") or rec.get("state") or ""
    if isinstance(status_raw, int):
        status_map = {0: "PENDING", 1: "PAID", 2: "FAILED", 3: "REJECTED", 4: "PROCESSING"}
        status_str = status_map.get(status_raw, str(status_raw))
    else:
        status_str = str(status_raw).upper()

    amount = (
        rec.get("actualAmount")
        or rec.get("actual_amount")
        or rec.get("amount")
        or rec.get("withdrawAmount")
        or 0
    )

    created_raw = (
        rec.get("createdAt")
        or rec.get("created_at")
        or rec.get("createTime")
        or rec.get("create_time")
        or ""
    )
    if isinstance(created_raw, (int, float)) and created_raw > 1e9:
        ts = created_raw / 1000 if created_raw > 1e12 else created_raw
        try:
            created_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_str = str(created_raw)
    else:
        created_str = str(created_raw)[:16] if created_raw else "N/A"

    return {"amount": amount, "status": status_str, "created_at": created_str}


# ── Formatting helpers ────────────────────────────────────────────────────────

def format_result(result: dict, email: str) -> Tuple[str, float]:
    """
    Format the check result into an HTML Telegram message.
    Returns (html_text, balance_float).
    """
    ui = result.get("user_info") or {}
    lw = result.get("last_withdraw")

    bal_raw = (
        ui.get("balance")
        or ui.get("wallet")
        or ui.get("walletBalance")
        or ui.get("amount")
        or ui.get("coin")
        or 0
    )
    try:
        bal = float(bal_raw)
    except Exception:
        bal = 0.0

    vip = (
        ui.get("vipLevel")
        or ui.get("vip_level")
        or ui.get("vip")
        or ui.get("level")
        or ui.get("vipGrade")
        or "0"
    )

    name = (
        ui.get("nickname")
        or ui.get("username")
        or ui.get("name")
        or ui.get("userName")
        or email.split("@")[0]
    )

    bal_icon = "💰" if bal > 0 else "💸"

    lines = [
        "<b>9kBoss Account Check ✅</b>",
        "━━━━━━━━━━━━━━",
        f"📧 <b>Email:</b> <code>{html.escape(str(email))}</code>",
        f"👤 <b>Name:</b> {html.escape(str(name))}",
        f"👑 <b>VIP Level:</b> {html.escape(str(vip))}",
        f"{bal_icon} <b>Balance:</b> ₹{bal:.2f}",
        "━━━━━━━━━━━━━━",
    ]

    if lw:
        lw_status = lw.get("status", "N/A")
        lw_icon = "✅" if "PAID" in lw_status else "⏳" if "PENDING" in lw_status else "❌"
        lines += [
            "<b>Last Withdrawal:</b>",
            f"   {lw_icon} Status: <b>{html.escape(str(lw_status))}</b>",
            f"   💵 Amount: ₹{html.escape(str(lw.get('amount', 0)))}",
            f"   🕐 Date: {html.escape(str(lw.get('created_at', 'N/A')))}",
            "━━━━━━━━━━━━━━",
        ]
    else:
        lines.append("📋 <b>Withdrawal history unavailable</b>")
        lines.append("━━━━━━━━━━━━━━")

    return "\n".join(lines), bal


# ── Utility ───────────────────────────────────────────────────────────────────

def _deep_get(d: dict, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, {})
    return d or default
