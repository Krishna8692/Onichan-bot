"""
Browser Routes — In-panel web browser with proxy support.
Registered via register_browser_routes(app, ...) called from keep_alive.py.
"""
from __future__ import annotations

import html as _html
import ipaddress
import json
import logging
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlparse, quote, unquote, urlencode, parse_qs, urlunparse

import requests as _req
from flask import request, jsonify, session, redirect, render_template_string, Response

_log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_SCHEMES = {"http", "https"}
_HISTORY_LIMIT = 50
_BINARY_CONTENT_TYPES = (
    "image/", "audio/", "video/", "font/",
    "application/octet-stream", "application/pdf",
    "application/zip", "application/x-zip", "application/wasm",
)
_PASSTHROUGH_TYPES = {
    "application/javascript", "text/javascript",
    "text/plain", "application/json",
}

# ── SSRF protection ───────────────────────────────────────────────────────────
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local & AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),          # multicast
]
_BLOCKED_EXACT_IPS = frozenset({
    "169.254.169.254",   # AWS / GCP / Azure IMDS
    "100.100.100.200",   # Alibaba Cloud metadata
    "fd00:ec2::254",     # AWS IPv6 metadata
})
_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost",
})


def _is_ssrf_safe(url: str) -> tuple[bool, str]:
    """Resolve the target host and ensure it is not a private/internal address."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().strip("[]")
        if not hostname:
            return False, "No hostname in URL"
        if hostname in _BLOCKED_HOSTNAMES:
            return False, "Access to localhost is not allowed"
        try:
            addrs = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            return False, f"DNS resolution failed: {e}"
        for _family, _type, _proto, _canon, sockaddr in addrs:
            ip_str = sockaddr[0].split("%")[0]  # strip IPv6 zone id
            if ip_str in _BLOCKED_EXACT_IPS:
                return False, "Access to cloud metadata service is not allowed"
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
                    return False, "Access to reserved/internal addresses is not allowed"
                for net in _PRIVATE_NETS:
                    if ip_obj in net:
                        return False, "Access to private network addresses is not allowed"
            except ValueError:
                pass
        return True, ""
    except Exception as e:
        return False, f"SSRF check error: {e}"


# ── per-user requests.Session (persists cookies per user) ────────────────────
_sessions_lock = threading.Lock()
_user_http_sessions: dict[str, _req.Session] = {}

_history_lock = threading.Lock()
_user_history: dict[str, list] = {}   # uid -> list[str] (most recent last)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _get_http_session(uid: str) -> _req.Session:
    with _sessions_lock:
        if uid not in _user_http_sessions:
            s = _req.Session()
            s.headers.update({
                "User-Agent": _BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                # Let the upstream gzip/br/deflate-encode — requests transparently
                # decompresses on iter_content (decode_content=True by default).
                "Accept-Encoding": "gzip, deflate, br",
            })
            # Bigger connection pool so parallel subresource fetches don't queue.
            try:
                from requests.adapters import HTTPAdapter
                adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=0)
                s.mount("http://", adapter)
                s.mount("https://", adapter)
            except Exception:
                pass
            _user_http_sessions[uid] = s
        return _user_http_sessions[uid]


def _reset_http_session(uid: str) -> None:
    with _sessions_lock:
        if uid in _user_http_sessions:
            try:
                _user_http_sessions[uid].close()
            except Exception:
                pass
            del _user_http_sessions[uid]


def _add_history(uid: str, url: str) -> None:
    with _history_lock:
        hist = _user_history.setdefault(uid, [])
        if hist and hist[-1] == url:
            return
        hist.append(url)
        if len(hist) > _HISTORY_LIMIT:
            _user_history[uid] = hist[-_HISTORY_LIMIT:]


def _get_history(uid: str) -> list:
    with _history_lock:
        hist = _user_history.get(uid, [])
        return list(reversed(hist[-20:]))


# ── helpers ───────────────────────────────────────────────────────────────────
def _he(s) -> str:
    return _html.escape(str(s) if s is not None else "")


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_proxy_url(proxy_str: str) -> str | None:
    if not proxy_str or not proxy_str.strip():
        return None
    p = proxy_str.strip()
    if "://" in p:
        return p
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f"http://{user}:{passwd}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return None


def _detect_proxy_type(proxy_url: str) -> str:
    if not proxy_url:
        return "HTTP"
    low = proxy_url.lower()
    if low.startswith("socks5"):
        return "SOCKS5"
    if low.startswith("socks4"):
        return "SOCKS4"
    if low.startswith("https"):
        return "HTTPS"
    return "HTTP"


def _validate_url(url: str) -> tuple[bool, str]:
    if not url:
        return False, "No URL provided"
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            return False, f"Scheme '{scheme}' not allowed. Only http/https are supported."
        if not parsed.netloc:
            return False, "Invalid URL — missing host"
        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {e}"


def _ensure_scheme(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if "://" not in url and not url.startswith("//"):
        return "https://" + url
    return url


def _make_absolute(url: str, base: str) -> str:
    if not url:
        return url
    low = url.lower().lstrip()
    if low.startswith(("data:", "javascript:", "mailto:", "tel:")):
        return url
    if url.startswith("#"):
        return url
    return urljoin(base, url)


def _proxied(absolute_url: str) -> str:
    return "/user/browser/fetch?url=" + quote(absolute_url, safe="")


# ── HTML rewriting ────────────────────────────────────────────────────────────
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)\s'\"]*)(['\"]?)\s*\)")
_META_REFRESH_RE = re.compile(r"(\d+)\s*;\s*url\s*=\s*(.*)", re.IGNORECASE)

# Injected JS: postMessage navigation sync + GET-form interceptor
_INJECT_JS = """
(function(){
try{
// Report current URL to parent frame
function _bpm(u){try{window.top.postMessage({type:'browser_nav',url:u},'*');}catch(e){}}
_bpm(window.location.href);
window.addEventListener('load',function(){_bpm(window.location.href);});
var _bpo=history.pushState;
history.pushState=function(){_bpo.apply(this,arguments);_bpm(window.location.href);};
var _bpr=history.replaceState;
history.replaceState=function(){_bpr.apply(this,arguments);_bpm(window.location.href);};

// Intercept GET form submissions so form fields are appended to the target URL
// (HTML spec: GET form submit replaces the query string of the action URL entirely)
function _interceptForms(){
  var forms=document.querySelectorAll('form:not([method]),form[method="get"],form[method="GET"]');
  forms.forEach(function(f){
    if(f._brIntercepted) return;
    f._brIntercepted=true;
    f.addEventListener('submit',function(e){
      var action=f.getAttribute('action')||'';
      // Only handle if action is our proxy fetch URL
      var m=action.match(/[?&]url=([^&]*)/);
      if(!m) return;
      e.preventDefault();
      var targetUrl;
      try{ targetUrl=decodeURIComponent(m[1]); }catch(ex){ return; }
      // Build target URL with form fields appended
      var parsed;
      try{ parsed=new URL(targetUrl); }catch(ex){ return; }
      var fd=new FormData(f);
      // Merge fields (don't override existing query params; append)
      fd.forEach(function(v,k){ parsed.searchParams.append(k,v); });
      var finalUrl=parsed.toString();
      window.location.href='/user/browser/fetch?url='+encodeURIComponent(finalUrl);
    });
  });
}
document.addEventListener('DOMContentLoaded',_interceptForms);
if(document.readyState!=='loading') _interceptForms();
}catch(e){}
})();
"""


def _rewrite_css_text(css: str, base_url: str) -> str:
    def _rep(m):
        quote_char = m.group(1)
        raw_url = m.group(2).strip()
        if not raw_url or raw_url.startswith("data:"):
            return m.group(0)
        abs_url = _make_absolute(raw_url, base_url)
        if urlparse(abs_url).scheme not in _ALLOWED_SCHEMES:
            return m.group(0)
        return "url(" + quote_char + _proxied(abs_url) + quote_char + ")"
    return _CSS_URL_RE.sub(_rep, css)


def _rewrite_html(raw: bytes, base_url: str, encoding: str = "utf-8") -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return raw.decode(encoding, errors="replace")
    # Try the much faster lxml parser first; fall back to stdlib html.parser.
    soup = None
    for parser_name in ("lxml", "html.parser"):
        try:
            soup = BeautifulSoup(raw, parser_name)
            break
        except Exception:
            continue
    if soup is None:
        return raw.decode(encoding, errors="replace")

    # Inject helper JS
    tag_pm = soup.new_tag("script")
    tag_pm.string = _INJECT_JS
    head = soup.find("head")
    if head:
        head.insert(0, tag_pm)
    else:
        soup.insert(0, tag_pm)

    # <a>, <link>, <area>
    for tag in soup.find_all(["a", "link", "area"]):
        href = tag.get("href") or ""
        low = href.lower().lstrip()
        if href and not low.startswith(("#", "javascript:", "data:", "mailto:", "tel:")):
            abs_url = _make_absolute(href, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["href"] = _proxied(abs_url)

    # Remove <base> tags to prevent relative URL confusion
    for tag in soup.find_all("base"):
        tag.decompose()

    # <form> — rewrite action; GET forms also handled by injected JS
    for tag in soup.find_all("form"):
        action = tag.get("action") or ""
        if action and not action.lower().startswith("javascript:"):
            abs_url = _make_absolute(action, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["action"] = _proxied(abs_url)

    # Elements with src / srcset
    for tag in soup.find_all(["img", "script", "iframe", "embed", "audio", "video", "source", "track", "input"]):
        src = tag.get("src") or ""
        if src and not src.lower().startswith(("data:", "javascript:")):
            abs_url = _make_absolute(src, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["src"] = _proxied(abs_url)
        srcset = tag.get("srcset") or ""
        if srcset:
            parts = []
            for seg in srcset.split(","):
                seg = seg.strip()
                if not seg:
                    continue
                tokens = seg.split(None, 1)
                img_url = tokens[0]
                descriptor = (" " + tokens[1]) if len(tokens) > 1 else ""
                abs_url = _make_absolute(img_url, base_url)
                if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                    parts.append(_proxied(abs_url) + descriptor)
                else:
                    parts.append(seg)
            tag["srcset"] = ", ".join(parts)

    # <meta http-equiv="refresh">
    for tag in soup.find_all("meta"):
        if str(tag.get("http-equiv", "")).lower() == "refresh":
            content = tag.get("content", "")
            m = _META_REFRESH_RE.match(content)
            if m:
                delay = m.group(1)
                rurl = m.group(2).strip().strip("'\"")
                abs_url = _make_absolute(rurl, base_url)
                if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                    tag["content"] = delay + ";url=" + _proxied(abs_url)

    # Inline style= and <style> blocks
    for tag in soup.find_all(style=True):
        tag["style"] = _rewrite_css_text(tag["style"], base_url)
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = _rewrite_css_text(style_tag.string, base_url)

    return str(soup)


def _is_binary(content_type: str) -> bool:
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(p) for p in _BINARY_CONTENT_TYPES)


def _is_passthrough(content_type: str) -> bool:
    ct = content_type.lower().split(";")[0].strip()
    return ct in _PASSTHROUGH_TYPES


# ── DB helpers ────────────────────────────────────────────────────────────────
def _init_browser_tables() -> None:
    from modules.database import _execute_with_retry as _db

    def _migrate(conn):
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS browser_proxies (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT 'Proxy',
                    proxy_url TEXT NOT NULL,
                    proxy_type TEXT DEFAULT 'http',
                    is_active BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS browser_bookmarks (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT 'Untitled',
                    url TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bp_user ON browser_proxies(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bb_user ON browser_bookmarks(user_id)")

    try:
        _db(_migrate)
        print("[Browser] Tables initialised ✓")
    except Exception as e:
        print(f"[Browser] Table init error: {e}")


def _get_active_proxy_row(uid: str) -> dict | None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, proxy_url, proxy_type FROM browser_proxies "
                "WHERE user_id=%s AND is_active=TRUE LIMIT 1",
                (uid,),
            )
            row = cur.fetchone()
            if row:
                return {"id": row[0], "name": row[1], "proxy_url": row[2], "proxy_type": row[3]}
            return None

    try:
        return _db(_q)
    except Exception:
        return None


def _list_proxies(uid: str) -> list:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, proxy_url, proxy_type, is_active, created_at "
                "FROM browser_proxies WHERE user_id=%s ORDER BY created_at DESC",
                (uid,),
            )
            rows = cur.fetchall()
            return [
                {"id": r[0], "name": r[1], "proxy_url": r[2], "proxy_type": r[3],
                 "is_active": r[4], "created_at": r[5]}
                for r in rows
            ]

    try:
        return _db(_q)
    except Exception:
        return []


def _add_proxy(uid: str, name: str, proxy_url: str, proxy_type: str) -> int:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO browser_proxies (user_id, name, proxy_url, proxy_type) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (uid, name, proxy_url, proxy_type),
            )
            return cur.fetchone()[0]

    return _db(_q)


def _delete_proxy(uid: str, proxy_id: int) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM browser_proxies WHERE id=%s AND user_id=%s", (proxy_id, uid))

    _db(_q)


def _edit_proxy(uid: str, proxy_id: int, name: str, proxy_url: str, proxy_type: str) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE browser_proxies SET name=%s, proxy_url=%s, proxy_type=%s "
                "WHERE id=%s AND user_id=%s",
                (name, proxy_url, proxy_type, proxy_id, uid),
            )

    _db(_q)


def _activate_proxy(uid: str, proxy_id: int) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE browser_proxies SET is_active=FALSE WHERE user_id=%s", (uid,))
            cur.execute("UPDATE browser_proxies SET is_active=TRUE WHERE id=%s AND user_id=%s", (proxy_id, uid))

    _db(_q)


def _deactivate_all_proxies(uid: str) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE browser_proxies SET is_active=FALSE WHERE user_id=%s", (uid,))

    _db(_q)


def _list_bookmarks(uid: str) -> list:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, url, created_at FROM browser_bookmarks "
                "WHERE user_id=%s ORDER BY created_at DESC LIMIT 100",
                (uid,),
            )
            rows = cur.fetchall()
            return [{"id": r[0], "title": r[1], "url": r[2], "created_at": r[3]} for r in rows]

    try:
        return _db(_q)
    except Exception:
        return []


def _add_bookmark(uid: str, title: str, url: str) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO browser_bookmarks (user_id, title, url) VALUES (%s, %s, %s)",
                (uid, title[:200], url[:2000]),
            )

    _db(_q)


def _delete_bookmark(uid: str, bm_id: int) -> None:
    from modules.database import _execute_with_retry as _db

    def _q(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM browser_bookmarks WHERE id=%s AND user_id=%s", (bm_id, uid))

    _db(_q)


# ── registration ──────────────────────────────────────────────────────────────
def register_browser_routes(app, user_required, get_user_sidebar, USER_CSS):
    _init_browser_tables()

    BROWSER_CSS = """
<style>
*{box-sizing:border-box;}
/* Position the browser content area precisely to avoid fixed header/nav overlap */
.main-content{
  position:fixed!important;
  top:0!important; left:0!important; right:0!important; bottom:0!important;
  padding:0!important; margin:0!important;
  display:flex!important; flex-direction:column!important;
  overflow:hidden!important;
}
/* Desktop: sidebar is 260px wide */
@media(min-width:769px){
  .main-content{left:260px!important;}
}
/* Mobile: account for fixed header (55px) and fixed bottom nav (62px) */
@media(max-width:768px){
  .main-content{
    top:calc(55px + env(safe-area-inset-top))!important;
    bottom:calc(62px + env(safe-area-inset-bottom))!important;
  }
}

/* ── Toolbar ── */
.br-toolbar{display:flex;align-items:center;gap:5px;padding:5px 8px;
  background:rgba(20,10,35,.98);border-bottom:1px solid rgba(255,105,180,.2);
  flex-shrink:0;z-index:50;}
.br-tb-btn{background:rgba(255,255,255,.08);border:1px solid rgba(255,105,180,.18);
  color:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:.9rem;
  transition:background .15s;min-width:34px;flex-shrink:0;}
.br-tb-btn:hover{background:rgba(255,105,180,.2);}
.br-tb-btn:disabled{opacity:.3;cursor:not-allowed;}
.br-addr-wrap{flex:1;display:flex;align-items:center;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,105,180,.22);border-radius:22px;padding:0 4px 0 12px;
  min-width:0;transition:border-color .15s;}
.br-addr-wrap:focus-within{border-color:#ff69b4;background:rgba(255,255,255,.1);}
.br-scheme{font-size:.72rem;font-weight:700;flex-shrink:0;margin-right:4px;}
.br-scheme.https{color:#4ade80;}
.br-scheme.http{color:#fbbf24;}
.br-scheme.none{display:none;}
.br-addr{flex:1;background:transparent;border:none;color:#fff;
  font-size:.85rem;outline:none;padding:7px 0;min-width:0;}
.br-go-btn{background:linear-gradient(135deg,#e94560,#9b2e9b);border:none;
  color:#fff;border-radius:18px;padding:8px 18px;cursor:pointer;font-weight:700;
  font-size:.85rem;flex-shrink:0;min-height:32px;-webkit-tap-highlight-color:rgba(255,105,180,.3);}
.br-go-btn:active{transform:scale(.96);}

/* ── Status bar ── */
.br-status{display:flex;align-items:center;gap:8px;padding:3px 10px;
  background:rgba(12,4,22,.95);border-bottom:1px solid rgba(255,105,180,.1);
  flex-shrink:0;font-size:.7rem;color:#aaa;min-height:26px;}
.br-proxy-badge{display:inline-flex;align-items:center;gap:3px;
  background:rgba(255,105,180,.1);border:1px solid rgba(255,105,180,.22);
  border-radius:10px;padding:1px 8px;color:#ff99cc;cursor:pointer;white-space:nowrap;}
.br-proxy-badge:hover{background:rgba(255,105,180,.18);}
.br-proxy-badge.off{background:rgba(255,255,255,.04);border-color:rgba(255,255,255,.08);color:#666;}
.br-ip{color:#7ec8e3;font-family:monospace;font-size:.68rem;}

/* ── Frame area ── */
.br-frame-wrap{flex:1;position:relative;background:#0d0520;overflow:hidden;}
#br-frame{width:100%;height:100%;border:none;display:block;}
.br-loading-overlay{position:absolute;inset:0;background:rgba(8,3,18,.97);
  display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:10;}
.br-spinner{width:42px;height:42px;border:3px solid rgba(255,105,180,.15);
  border-top-color:#ff69b4;border-radius:50%;animation:br-spin .75s linear infinite;margin-bottom:12px;}
@keyframes br-spin{to{transform:rotate(360deg);}}
.br-load-txt{color:#888;font-size:.8rem;}
.br-welcome{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:14px;padding:20px;}
.br-welcome-icon{font-size:3.5rem;opacity:.3;}
.br-welcome-txt{color:rgba(255,255,255,.35);font-size:.9rem;text-align:center;}
.br-welcome-quick{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:360px;margin-top:8px;}
.br-welcome-quick button{background:rgba(255,105,180,.12);border:1px solid rgba(255,105,180,.3);
  color:#ffb3d1;border-radius:18px;padding:8px 14px;font-size:.82rem;cursor:pointer;
  -webkit-tap-highlight-color:rgba(255,105,180,.3);transition:background .15s;}
.br-welcome-quick button:hover,.br-welcome-quick button:active{background:rgba(255,105,180,.25);}

/* ── Settings modal (bottom sheet) ── */
.br-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;
  opacity:0;pointer-events:none;transition:opacity .25s;}
.br-backdrop.open{opacity:1;pointer-events:all;}
.br-modal{position:fixed;bottom:0;left:0;right:0;z-index:201;
  background:rgba(14,5,28,.99);border-top:1px solid rgba(255,105,180,.25);
  border-radius:18px 18px 0 0;transform:translateY(100%);
  transition:transform .3s cubic-bezier(.32,.72,0,1);
  display:flex;flex-direction:column;max-height:82vh;}
.br-modal.open{transform:translateY(0);}
.br-modal-drag{width:40px;height:4px;background:rgba(255,255,255,.15);
  border-radius:2px;margin:10px auto 4px;}
.br-modal-tabs{display:flex;border-bottom:1px solid rgba(255,105,180,.15);flex-shrink:0;padding:0 4px;}
.br-modal-tab{flex:1;padding:10px 4px;text-align:center;cursor:pointer;font-size:.8rem;
  color:#888;border-bottom:2px solid transparent;transition:all .2s;}
.br-modal-tab.active{color:#ff69b4;border-color:#ff69b4;}
.br-modal-body{flex:1;overflow-y:auto;padding:12px 14px 24px;}
.br-modal-sec{display:none;}
.br-modal-sec.active{display:block;}

/* ── Proxy items ── */
.br-pitem{display:flex;align-items:center;gap:6px;padding:10px;border-radius:10px;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,105,180,.1);margin-bottom:8px;flex-wrap:wrap;}
.br-pitem.active-proxy{border-color:#4ade80;background:rgba(74,222,128,.06);}
.br-pitem-name{font-size:.84rem;font-weight:700;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;flex:1;min-width:0;}
.br-pitem-type{font-size:.67rem;color:#aaa;padding:1px 6px;background:rgba(255,255,255,.07);
  border-radius:4px;flex-shrink:0;}
.br-pill-btn{padding:4px 9px;font-size:.7rem;border-radius:6px;cursor:pointer;
  border:none;font-weight:700;white-space:nowrap;flex-shrink:0;}
.br-pill-activate{background:rgba(74,222,128,.2);color:#4ade80;}
.br-pill-deactivate{background:rgba(255,190,0,.2);color:#fbbf24;}
.br-pill-test{background:rgba(125,200,255,.15);color:#7ec8e3;}
.br-pill-edit{background:rgba(255,165,0,.15);color:#ffa500;}
.br-pill-del{background:rgba(239,68,68,.15);color:#f87171;}
.br-edit-row{display:none;padding:6px 0 2px;flex-direction:column;gap:5px;width:100%;}
.br-edit-row.open{display:flex;}
.br-edit-row input{background:rgba(255,255,255,.07);border:1px solid rgba(255,105,180,.2);
  color:#fff;border-radius:7px;padding:6px 10px;font-size:.8rem;font-family:inherit;width:100%;}

/* ── Add proxy form ── */
.br-add-form label{display:block;font-size:.74rem;color:#aaa;margin:8px 0 3px;}
.br-add-form input{width:100%;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,105,180,.2);color:#fff;border-radius:8px;
  padding:8px 12px;font-size:.84rem;font-family:inherit;}
.br-add-form input:focus{outline:none;border-color:#ff69b4;}
.br-submit-btn{width:100%;margin-top:12px;background:linear-gradient(135deg,#e94560,#9b2e9b);
  color:#fff;border:none;border-radius:10px;padding:10px;cursor:pointer;
  font-weight:700;font-size:.9rem;}

/* ── Bookmarks / History ── */
.br-bm-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);
  margin-bottom:6px;cursor:pointer;}
.br-bm-item:hover{background:rgba(255,105,180,.08);}
.br-bm-title{flex:1;font-size:.82rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ddd;}
.br-bm-url{font-size:.68rem;color:#777;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.br-hist-item{padding:8px 10px;border-radius:7px;cursor:pointer;font-size:.8rem;color:#ccc;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  border-bottom:1px solid rgba(255,255,255,.05);}
.br-hist-item:hover{background:rgba(255,105,180,.08);}

/* ── Misc ── */
.br-msg{font-size:.75rem;padding:6px 10px;border-radius:7px;margin-top:6px;}
.br-msg.ok{background:rgba(74,222,128,.12);color:#4ade80;}
.br-msg.err{background:rgba(239,68,68,.12);color:#f87171;}
.br-section-title{font-size:.75rem;font-weight:700;color:#ff99cc;margin:10px 0 6px;
  text-transform:uppercase;letter-spacing:.04em;}
.br-divider{border:none;border-top:1px solid rgba(255,105,180,.12);margin:12px 0;}
</style>
"""

    def _uid():
        return str(session.get("user_id") or "")

    # ── helper: error page ────────────────────────────────────────────────────
    def _error_page(title: str, msg: str, url: str = "", status: int = 502) -> Response:
        body = (
            "<html><body style='background:#0a0515;color:#fff;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;"
            "height:100vh;flex-direction:column'>"
            "<div style='font-size:3rem'>🚫</div>"
            "<h2 style='color:#f87171;margin:10px 0'>" + _he(title) + "</h2>"
            "<p style='color:#aaa;font-size:.9rem'>" + _he(msg) + "</p>"
        )
        if url:
            body += "<p style='color:#666;font-size:.78rem'>URL: " + _he(url[:200]) + "</p>"
        body += (
            "<p style='margin-top:20px'>"
            "<a href='javascript:history.back()' style='color:#ff69b4;font-size:.85rem'>&#8592; Go Back</a>"
            "</p></body></html>"
        )
        return Response(body, status=status, content_type="text/html; charset=utf-8")

    # ── main browser page ─────────────────────────────────────────────────────
    @app.route("/user/browser")
    @user_required
    def browser_home():
        uid = _uid()
        active_proxy = _get_active_proxy_row(uid)
        proxies = _list_proxies(uid)
        bookmarks = _list_bookmarks(uid)

        proxy_name_safe = _he(active_proxy["name"]) if active_proxy else ""
        proxy_type_safe = _he(active_proxy["proxy_type"]) if active_proxy else ""

        def _proxy_item(p):
            pid = p["id"]
            pname = _he(p["name"])
            ptype = _he(p["proxy_type"])
            purl_safe = _he(p["proxy_url"])
            is_act = p["is_active"]
            active_cls = " active-proxy" if is_act else ""
            act_btn_cls = "br-pill-deactivate" if is_act else "br-pill-activate"
            act_btn_label = "Deactivate" if is_act else "Activate"
            act_fn = "deactivateProxy()" if is_act else ("activateProxy(" + str(pid) + ")")
            return (
                f'<div class="br-pitem{active_cls}" id="pitem-{pid}">'
                f'<span class="br-pitem-name" title="{purl_safe}">'
                f'{"✓ " if is_act else ""}{pname}</span>'
                f'<span class="br-pitem-type">{ptype}</span>'
                f'<button class="br-pill-btn {act_btn_cls}" onclick="{act_fn}">{act_btn_label}</button>'
                f'<button class="br-pill-btn br-pill-test" onclick="testProxy({pid})">Test</button>'
                f'<button class="br-pill-btn br-pill-edit" onclick="toggleEdit({pid})">Edit</button>'
                f'<button class="br-pill-btn br-pill-del" onclick="delProxy({pid})">✕</button>'
                f'<div class="br-edit-row" id="edit-row-{pid}">'
                f'<input id="edit-name-{pid}" placeholder="Name" value="{pname}">'
                f'<input id="edit-url-{pid}" placeholder="Proxy URL" value="{purl_safe}">'
                f'<button class="br-pill-btn br-pill-activate" '
                f'onclick="saveEdit({pid})" style="align-self:flex-start">Save</button>'
                f'</div>'
                f'</div>'
            )

        proxies_html = "".join(_proxy_item(p) for p in proxies)
        if not proxies_html:
            proxies_html = '<div style="color:#666;font-size:.8rem;text-align:center;padding:20px">No proxies saved yet.</div>'

        def _bm_item(b):
            bid = b["id"]
            btitle = _he(b["title"])
            burl = _he(b["url"])
            # Safe JS string literal (escapes backslash, quote, newlines, </script>, etc.)
            # then HTML-escape for use inside an HTML attribute.
            burl_js_attr = _he(json.dumps(b["url"]))
            return (
                f'<div class="br-bm-item" onclick="navigateTo({burl_js_attr})">'
                f'<span style="flex:0 0 14px;font-size:.75rem">🔖</span>'
                f'<div style="flex:1;min-width:0">'
                f'<div class="br-bm-title">{btitle}</div>'
                f'<div class="br-bm-url">{burl}</div>'
                f'</div>'
                f'<button class="br-pill-btn br-pill-del" '
                f'onclick="event.stopPropagation();delBookmark({bid})">✕</button>'
                f'</div>'
            )

        bm_html = "".join(_bm_item(b) for b in bookmarks)
        if not bm_html:
            bm_html = '<div style="color:#666;font-size:.8rem;text-align:center;padding:20px">No bookmarks yet.</div>'

        if active_proxy:
            proxy_status_html = (
                f'<span class="br-proxy-badge">🛡 {proxy_name_safe} ({proxy_type_safe})</span>'
                f'<span id="br-ip" class="br-ip">checking...</span>'
            )
        else:
            proxy_status_html = (
                '<span class="br-proxy-badge off">🔓 No proxy (direct)</span>'
                '<span id="br-ip" class="br-ip"></span>'
            )

        sidebar = get_user_sidebar("browser", "Browser")

        page = """<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Browser — Onichan</title>
""" + USER_CSS + BROWSER_CSS + """
</head><body>
""" + sidebar + """
<div class="main-content">

<!-- Toolbar -->
<div class="br-toolbar">
  <button class="br-tb-btn" id="btn-back" onclick="goBack()" title="Back" disabled>&#8592;</button>
  <button class="br-tb-btn" id="btn-fwd" onclick="goForward()" title="Forward" disabled>&#8594;</button>
  <button class="br-tb-btn" id="btn-reload" onclick="doReload()" title="Reload">&#10227;</button>
  <button class="br-tb-btn" id="btn-stop" onclick="doStop()" title="Stop" style="display:none">&#10005;</button>
  <form class="br-addr-wrap" id="br-addr-form" novalidate onsubmit="navigateTo(document.getElementById('br-addr').value);return false;" action="javascript:void(0)">
    <span id="br-scheme" class="br-scheme none"></span>
    <input id="br-addr" class="br-addr" type="text" inputmode="url"
      enterkeyhint="go" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false"
      placeholder="URL or search..." onfocus="this.select()">
    <button type="submit" class="br-go-btn">Go</button>
  </form>
  <button class="br-tb-btn" onclick="addBookmark()" title="Bookmark">🔖</button>
  <button class="br-tb-btn" onclick="openSettings('proxy')" title="Settings">⚙️</button>
</div>

<!-- Status bar -->
<div class="br-status">
  <span class="br-proxy-badge """ + ("" if active_proxy else "off") + """" onclick="openSettings('proxy')">
    """ + ("🛡 " + proxy_name_safe + " (" + proxy_type_safe + ")" if active_proxy else "🔓 No proxy (direct)") + """
  </span>
  <span id="br-ip" class="br-ip"></span>
  <span id="br-stat-txt" style="margin-left:auto;color:#444">Ready</span>
</div>

<!-- Browser frame -->
<div class="br-frame-wrap">
  <div id="br-loading" class="br-loading-overlay" style="display:none">
    <div class="br-spinner"></div>
    <div class="br-load-txt" id="br-load-txt">Loading...</div>
  </div>
  <div class="br-welcome" id="br-welcome">
    <div class="br-welcome-icon">🌐</div>
    <div class="br-welcome-txt">Enter a URL above to start browsing</div>
    <div class="br-welcome-quick">
      <button onclick="navigateTo('https://duckduckgo.com')">🦆 DuckDuckGo</button>
      <button onclick="navigateTo('https://en.wikipedia.org')">📖 Wikipedia</button>
      <button onclick="navigateTo('https://news.ycombinator.com')">🟠 HN</button>
      <button onclick="navigateTo('https://example.com')">🧪 Test</button>
    </div>
  </div>
  <iframe id="br-frame"
    sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
    loading="eager" fetchpriority="high" referrerpolicy="no-referrer"
    style="display:none"
  ></iframe>
</div>

<!-- Settings backdrop -->
<div class="br-backdrop" id="br-backdrop" onclick="closeSettings()"></div>

<!-- Settings bottom sheet -->
<div class="br-modal" id="br-modal">
  <div class="br-modal-drag"></div>
  <div class="br-modal-tabs">
    <div class="br-modal-tab active" id="mtab-proxy" onclick="switchTab('proxy')">🛡 Proxy</div>
    <div class="br-modal-tab" id="mtab-bm" onclick="switchTab('bm')">🔖 Bookmarks</div>
    <div class="br-modal-tab" id="mtab-hist" onclick="switchTab('hist')">🕐 History</div>
  </div>
  <div class="br-modal-body">

    <!-- Proxy tab -->
    <div id="msec-proxy" class="br-modal-sec active">
      <div class="br-section-title">Saved Proxies</div>
      <div id="proxy-list">""" + proxies_html + """</div>
      <div id="proxy-test-result"></div>
      <hr class="br-divider">
      <div class="br-section-title">Add Proxy</div>
      <div class="br-add-form">
        <label>Name</label>
        <input id="add-name" placeholder="My Proxy" type="text">
        <label>Proxy URL &nbsp;<span style="color:#666;font-weight:400">(ip:port &nbsp;·&nbsp; ip:port:user:pass &nbsp;·&nbsp; socks5://...)</span></label>
        <input id="add-url" placeholder="192.168.1.1:8080">
        <button class="br-submit-btn" onclick="addProxy()">Add Proxy</button>
        <div id="add-result"></div>
      </div>
    </div>

    <!-- Bookmarks tab -->
    <div id="msec-bm" class="br-modal-sec">
      <div class="br-section-title">Bookmarks</div>
      <div id="bm-list">""" + bm_html + """</div>
    </div>

    <!-- History tab -->
    <div id="msec-hist" class="br-modal-sec">
      <div class="br-section-title">Recent History</div>
      <div id="hist-list"><div style="color:#555;font-size:.8rem;text-align:center;padding:20px">Navigate somewhere to build history.</div></div>
    </div>

  </div>
</div>

</div><!-- .main-content -->
<script>
// ── Navigation ────────────────────────────────────────────────────────────────
var _hist=[], _histIdx=-1;
function _updateNavBtns(){
  document.getElementById('btn-back').disabled=(_histIdx<=0);
  document.getElementById('btn-fwd').disabled=(_histIdx>=_hist.length-1);
}
function _setScheme(url){
  var el=document.getElementById('br-scheme');
  if(!url){el.className='br-scheme none';return;}
  if(/^https/i.test(url)){el.textContent='🔒';el.className='br-scheme https';}
  else{el.textContent='⚠️';el.className='br-scheme http';}
}
function _normalizeUrl(input){
  if(!input)return '';
  var s=input.trim();
  if(!s)return '';
  // Already has a scheme (http/https/about/data/etc.)
  if(/^[a-z][a-z0-9+.-]*:\\/\\//i.test(s))return s;
  if(s.startsWith('//'))return 'https:'+s;
  // about: pages
  if(/^about:/i.test(s))return s;
  // Looks like a domain or IP if it has a dot, OR is localhost-ish (which we'll let the server reject)
  // Heuristic: contains a dot or colon (port), no spaces, first segment is alphanumeric/dash/dot
  var firstSpace=s.indexOf(' ');
  var hasDotOrPort=/^[^\\s\\/]+\\.[^\\s\\/]+/.test(s)||/^[^\\s\\/]+:[0-9]+(\\/|$)/.test(s);
  if(firstSpace===-1&&hasDotOrPort){return 'https://'+s;}
  // Otherwise treat as a search query → DuckDuckGo
  return 'https://duckduckgo.com/?q='+encodeURIComponent(s);
}
function navigateTo(url){
  url=_normalizeUrl(url);
  if(!url)return;
  document.getElementById('br-addr').value=url;
  _setScheme(url);
  _showLoading(url);
  closeSettings();
  document.getElementById('br-welcome').style.display='none';
  document.getElementById('br-frame').style.display='block';
  if(_histIdx<_hist.length-1){_hist=_hist.slice(0,_histIdx+1);}
  _hist.push(url);_histIdx=_hist.length-1;_updateNavBtns();
  _pushServerHistory(url);
  document.getElementById('br-frame').src='/user/browser/fetch?url='+encodeURIComponent(url);
}
function goBack(){
  if(_histIdx<=0)return;
  _histIdx--;
  var url=_hist[_histIdx];
  document.getElementById('br-addr').value=url;_setScheme(url);_showLoading(url);
  document.getElementById('br-frame').src='/user/browser/fetch?url='+encodeURIComponent(url);
  _updateNavBtns();
}
function goForward(){
  if(_histIdx>=_hist.length-1)return;
  _histIdx++;
  var url=_hist[_histIdx];
  document.getElementById('br-addr').value=url;_setScheme(url);_showLoading(url);
  document.getElementById('br-frame').src='/user/browser/fetch?url='+encodeURIComponent(url);
  _updateNavBtns();
}
function doReload(){
  var f=document.getElementById('br-frame');
  if(f.src&&f.src!=='about:blank'){_showLoading('');f.src=f.src;}
}
function doStop(){
  document.getElementById('br-frame').src='about:blank';
  document.getElementById('br-frame').style.display='none';
  document.getElementById('br-welcome').style.display='flex';
  _hideLoading();
}
function _showLoading(url){
  document.getElementById('br-loading').style.display='flex';
  document.getElementById('br-load-txt').textContent=
    url?('Loading '+url.replace(/^https?:\\/\\//,'').substring(0,50)+'...'):'Loading...';
  document.getElementById('btn-stop').style.display='';
  document.getElementById('btn-reload').style.display='none';
  document.getElementById('br-stat-txt').textContent='Loading...';
}
function _hideLoading(){
  document.getElementById('br-loading').style.display='none';
  document.getElementById('btn-stop').style.display='none';
  document.getElementById('btn-reload').style.display='';
  document.getElementById('br-stat-txt').textContent='Done';
}
document.getElementById('br-frame').addEventListener('load',_hideLoading);
document.getElementById('br-frame').addEventListener('error',function(){
  _hideLoading();document.getElementById('br-stat-txt').textContent='Error';
});
window.addEventListener('message',function(e){
  if(!e.data||e.data.type!=='browser_nav')return;
  var url=e.data.url||'';
  var m=url.match(/[?&]url=([^&]+)/);
  if(m){try{url=decodeURIComponent(m[1]);}catch(ex){}}
  if(url&&url!=='about:blank'&&!/^\\/user\\/browser\\/fetch/.test(url)){
    document.getElementById('br-addr').value=url;_setScheme(url);
  }
});

// ── Settings modal ────────────────────────────────────────────────────────────
function openSettings(tab){
  document.getElementById('br-backdrop').classList.add('open');
  document.getElementById('br-modal').classList.add('open');
  if(tab)switchTab(tab);
}
function closeSettings(){
  document.getElementById('br-backdrop').classList.remove('open');
  document.getElementById('br-modal').classList.remove('open');
}
function switchTab(n){
  ['proxy','bm','hist'].forEach(function(k){
    var t=document.getElementById('mtab-'+k),s=document.getElementById('msec-'+k);
    if(t)t.className='br-modal-tab'+(k===n?' active':'');
    if(s)s.className='br-modal-sec'+(k===n?' active':'');
  });
  if(n==='hist')_loadServerHistory();
}

// ── Proxy actions ─────────────────────────────────────────────────────────────
function activateProxy(id){
  _post('/user/browser/api/proxy/activate',{proxy_id:id},function(d){
    if(d.ok)location.reload();else alert(d.error||'Error');
  });
}
function deactivateProxy(){
  _post('/user/browser/api/proxy/deactivate',{},function(d){
    if(d.ok)location.reload();else alert(d.error||'Error');
  });
}
function delProxy(id){
  if(!confirm('Delete this proxy?'))return;
  _post('/user/browser/api/proxy/delete',{proxy_id:id},function(d){
    if(d.ok){var el=document.getElementById('pitem-'+id);if(el)el.remove();}
    else alert(d.error||'Error');
  });
}
function toggleEdit(id){
  var row=document.getElementById('edit-row-'+id);
  if(row)row.classList.toggle('open');
}
function saveEdit(id){
  var name=document.getElementById('edit-name-'+id).value.trim();
  var url=document.getElementById('edit-url-'+id).value.trim();
  if(!url){alert('Proxy URL required');return;}
  _post('/user/browser/api/proxy/edit',{proxy_id:id,name:name||'Proxy',proxy_url:url},function(d){
    if(d.ok)location.reload();else alert(d.error||'Error');
  });
}
function testProxy(id){
  var res=document.getElementById('proxy-test-result');
  res.innerHTML='<div class="br-msg ok" style="margin-bottom:6px">Testing proxy...</div>';
  _post('/user/browser/api/proxy/test',{proxy_id:id},function(d){
    if(d.ok){
      var flag='';
      if(d.country_code&&d.country_code.length===2){
        try{flag=' '+String.fromCodePoint(...[...d.country_code].map(c=>c.charCodeAt(0)+127397));}catch(e){}
      }
      res.innerHTML='<div class="br-msg ok" style="margin-bottom:6px">✅ '+
        (d.ip||'?')+flag+' &nbsp;·&nbsp; '+(d.country||'?')+' &nbsp;·&nbsp; '+(d.ms||'?')+'ms</div>';
    }else{
      res.innerHTML='<div class="br-msg err" style="margin-bottom:6px">❌ '+(d.error||'Failed')+'</div>';
    }
  });
}
function addProxy(){
  var name=document.getElementById('add-name').value.trim();
  var url=document.getElementById('add-url').value.trim();
  var res=document.getElementById('add-result');
  if(!url){res.innerHTML='<div class="br-msg err">Proxy URL required</div>';return;}
  _post('/user/browser/api/proxy/add',{name:name||'Proxy',proxy_url:url},function(d){
    if(d.ok){
      res.innerHTML='<div class="br-msg ok">Added!</div>';
      document.getElementById('add-name').value='';
      document.getElementById('add-url').value='';
      setTimeout(()=>location.reload(),600);
    }else{
      res.innerHTML='<div class="br-msg err">❌ '+(d.error||'Error')+'</div>';
    }
  });
}

// ── Bookmarks ─────────────────────────────────────────────────────────────────
function addBookmark(){
  var url=document.getElementById('br-addr').value.trim();
  if(!url||!/^https?:\\/\\//i.test(url)){alert('Navigate to a page first');return;}
  var host='';try{host=new URL(url).hostname;}catch(e){host=url;}
  var title=prompt('Bookmark title:',host);
  if(!title)return;
  _post('/user/browser/api/bookmark/add',{title:title,url:url},function(d){
    if(!d.ok){alert(d.error||'Error');return;}
    var list=document.getElementById('bm-list');
    var div=document.createElement('div');
    div.className='br-bm-item';
    div.dataset.url=url;
    div.addEventListener('click',function(){navigateTo(this.dataset.url);});
    div.innerHTML='<span style="flex-shrink:0">🔖</span>'+
      '<div style="flex:1;min-width:0"><div class="br-bm-title"></div>'+
      '<div class="br-bm-url"></div></div>'+
      '<button class="br-pill-btn br-pill-del" data-id="'+d.id+'">✕</button>';
    div.querySelector('.br-bm-title').textContent=title;
    div.querySelector('.br-bm-url').textContent=url;
    div.querySelector('.br-pill-del').addEventListener('click',function(e){
      e.stopPropagation();delBookmark(parseInt(this.dataset.id,10));
    });
    list.insertBefore(div,list.firstChild);
  });
}
function delBookmark(id){
  _post('/user/browser/api/bookmark/delete',{bookmark_id:id},function(d){
    if(d.ok)location.reload();
  });
}

// ── History ───────────────────────────────────────────────────────────────────
function _pushServerHistory(url){
  fetch('/user/browser/api/history/add',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url})}).catch(()=>{});
}
function _loadServerHistory(){
  fetch('/user/browser/api/history').then(r=>r.json()).then(d=>{
    var list=document.getElementById('hist-list');if(!list)return;
    if(!d.history||!d.history.length){
      list.innerHTML='<div style="color:#555;font-size:.8rem;text-align:center;padding:20px">No history yet.</div>';
      return;
    }
    list.innerHTML='';
    d.history.forEach(function(u){
      var item=document.createElement('div');
      item.className='br-hist-item';
      item.dataset.url=u;
      item.textContent=u;
      item.addEventListener('click',function(){navigateTo(this.dataset.url);});
      list.appendChild(item);
    });
  }).catch(()=>{});
}

// ── Generic POST ──────────────────────────────────────────────────────────────
function _post(url,data,cb){
  fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data)}).then(r=>r.json()).then(cb)
    .catch(function(){cb({ok:false,error:'Request failed'});});
}

// ── IP check on load ──────────────────────────────────────────────────────────
(function(){
  var ipEl=document.getElementById('br-ip');if(!ipEl)return;
  fetch('/user/browser/api/ip').then(r=>r.json()).then(d=>{
    if(!d.ip)return;
    var flag='';
    if(d.country_code&&d.country_code.length===2){
      try{flag=' '+String.fromCodePoint(...[...d.country_code].map(c=>c.charCodeAt(0)+127397));}catch(e){}
    }
    ipEl.textContent=d.ip+flag;
  }).catch(()=>{});
})();
</script>
</body></html>"""

        return render_template_string(page)

    # ── /user/browser/proxies — redirect to main browser page ─────────────────
    @app.route("/user/browser/proxies")
    @user_required
    def browser_proxies_page():
        return redirect("/user/browser")

    # ── fetch endpoint — GET and POST ─────────────────────────────────────────
    @app.route("/user/browser/fetch", methods=["GET", "POST"])
    @user_required
    def browser_fetch():
        uid = _uid()

        # Build target URL from 'url' param; for GET forms, other query params
        # are already merged into the target URL by the injected JS interceptor.
        # For direct navigation, pick up any extra params and forward them.
        raw_url = request.args.get("url", "").strip()
        if not raw_url:
            return _error_page("No URL", "No URL was specified.", status=400)

        # Auto-add scheme
        if "://" not in raw_url and not raw_url.startswith("//"):
            raw_url = "https://" + raw_url

        # If extra query params exist (besides 'url'), merge them into target URL
        extra_params = {k: v for k, v in request.args.items() if k != "url"}
        if extra_params:
            parsed_target = urlparse(raw_url)
            existing_qs = parse_qs(parsed_target.query, keep_blank_values=True)
            for k, v in extra_params.items():
                existing_qs.setdefault(k, []).append(v)
            merged_qs = urlencode({k: v[0] for k, v in existing_qs.items()}, doseq=False)
            raw_url = urlunparse(parsed_target._replace(query=merged_qs))

        ok, err = _validate_url(raw_url)
        if not ok:
            return _error_page("Invalid URL", err, raw_url, 400)

        # SSRF protection
        ssrf_ok, ssrf_err = _is_ssrf_safe(raw_url)
        if not ssrf_ok:
            return _error_page("Access Denied", ssrf_err, raw_url, 403)

        active_proxy = _get_active_proxy_row(uid)
        proxies_dict = None
        if active_proxy:
            purl = _parse_proxy_url(active_proxy["proxy_url"])
            if purl:
                proxies_dict = {"http": purl, "https": purl}

        http_session = _get_http_session(uid)

        # Determine HTTP method and body
        method = request.method
        post_data = None
        post_files = None
        if method == "POST":
            ct = request.content_type or ""
            if "application/x-www-form-urlencoded" in ct:
                post_data = request.form.to_dict(flat=False)
            elif "multipart/form-data" in ct:
                post_data = request.form.to_dict(flat=False)
                post_files = request.files.to_dict(flat=False)
            elif request.data:
                post_data = request.data

        # ── fetch with manual redirect following (SSRF check per hop) ─────────
        current_url = raw_url
        resp = None
        err_msg = None
        _MAX_HOPS = 10
        try:
            for _hop in range(_MAX_HOPS + 1):
                if _hop == _MAX_HOPS:
                    err_msg = "Too many redirects (max 10)"
                    break
                fetch_kwargs = dict(
                    timeout=_FETCH_TIMEOUT,
                    proxies=proxies_dict,
                    stream=True,
                    allow_redirects=False,
                )
                if _hop == 0 and method == "POST":
                    resp = http_session.post(
                        current_url,
                        data=post_data,
                        files=post_files,
                        **fetch_kwargs,
                    )
                else:
                    resp = http_session.get(current_url, **fetch_kwargs)
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "").strip()
                    if not location:
                        break  # no Location header — treat as final response
                    next_url = urljoin(current_url, location)
                    ok_url, url_err = _validate_url(next_url)
                    if not ok_url:
                        err_msg = "Redirect target invalid: " + url_err
                        break
                    ssrf_ok, ssrf_err = _is_ssrf_safe(next_url)
                    if not ssrf_ok:
                        err_msg = "Redirect blocked (SSRF): " + ssrf_err
                        break
                    current_url = next_url
                    resp.close()
                    continue
                # Non-redirect — we have our final response
                break
        except _req.exceptions.ProxyError:
            err_msg = "Proxy error — check your proxy settings."
        except _req.exceptions.ConnectionError:
            err_msg = "Connection error — could not reach the server."
        except _req.exceptions.Timeout:
            err_msg = "Request timed out (15 s)."
        except Exception as e:
            err_msg = "Fetch failed: " + str(e)[:120]

        if err_msg:
            return _error_page("Page load failed", err_msg, raw_url)

        # Track in server-side history
        _add_history(uid, current_url)

        ct = resp.headers.get("Content-Type", "text/html")
        final_url = current_url

        # ── Streaming body read with hard size cap ──────────────────────────
        def _read_stream(max_bytes: int) -> tuple[bytes, bool]:
            """Read up to max_bytes from resp, return (data, truncated)."""
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return b"".join(chunks), True
                chunks.append(chunk)
            return b"".join(chunks), False

        # Binary / passthrough — stream through unchanged
        if _is_binary(ct) or _is_passthrough(ct):
            content, over = _read_stream(_MAX_RESPONSE_BYTES)
            if over:
                return _error_page("Response Too Large",
                                   "The server response exceeds the 10 MB limit.",
                                   final_url, 413)
            r = Response(content, status=resp.status_code, content_type=ct)
            for hdr in ("Cache-Control", "ETag", "Last-Modified"):
                if hdr in resp.headers:
                    r.headers[hdr] = resp.headers[hdr]
            return r

        # CSS — rewrite url() references
        if ct.lower().split(";")[0].strip() == "text/css":
            raw_bytes, over = _read_stream(_MAX_RESPONSE_BYTES)
            if over:
                return _error_page("Response Too Large",
                                   "The CSS file exceeds the 10 MB limit.",
                                   final_url, 413)
            encoding = resp.encoding or "utf-8"
            css_text = raw_bytes.decode(encoding, errors="replace")
            rewritten_css = _rewrite_css_text(css_text, final_url)
            r = Response(rewritten_css, status=resp.status_code,
                         content_type="text/css; charset=utf-8")
            for hdr in ("Cache-Control", "ETag", "Last-Modified"):
                if hdr in resp.headers:
                    r.headers[hdr] = resp.headers[hdr]
            return r

        # HTML — rewrite links
        raw_bytes, over = _read_stream(_MAX_RESPONSE_BYTES)
        if over:
            return _error_page("Response Too Large",
                               "The page exceeds the 10 MB limit.",
                               final_url, 413)
        encoding = resp.encoding or "utf-8"
        rewritten = _rewrite_html(raw_bytes, final_url, encoding)
        flask_resp = Response(rewritten, status=resp.status_code,
                              content_type="text/html; charset=utf-8")
        # Pass through caching hints so the browser can revalidate / serve from cache.
        for hdr in ("Cache-Control", "ETag", "Last-Modified", "Expires", "Vary"):
            if hdr in resp.headers:
                flask_resp.headers[hdr] = resp.headers[hdr]
        # Strip headers that would block embedding the iframe.
        for h in ("X-Frame-Options", "Content-Security-Policy",
                  "X-Content-Type-Options", "Cross-Origin-Opener-Policy",
                  "Cross-Origin-Embedder-Policy"):
            flask_resp.headers.pop(h, None)
        return flask_resp

    # ── IP info ────────────────────────────────────────────────────────────────
    @app.route("/user/browser/api/ip")
    @user_required
    def browser_api_ip():
        uid = _uid()
        active_proxy = _get_active_proxy_row(uid)
        proxies_dict = None
        if active_proxy:
            purl = _parse_proxy_url(active_proxy["proxy_url"])
            if purl:
                proxies_dict = {"http": purl, "https": purl}
        try:
            r1 = _req.get("https://api.ipify.org?format=json", timeout=8, proxies=proxies_dict)
            ip = r1.json().get("ip", "")
        except Exception:
            return jsonify({"ip": None})
        if not ip:
            return jsonify({"ip": None})
        try:
            r2 = _req.get(f"http://ip-api.com/json/{ip}?fields=query,country,countryCode,isp", timeout=6)
            geo = r2.json()
            return jsonify({"ip": ip, "country": geo.get("country"),
                            "country_code": geo.get("countryCode"), "isp": geo.get("isp")})
        except Exception:
            return jsonify({"ip": ip})

    # ── history API ────────────────────────────────────────────────────────────
    @app.route("/user/browser/api/history")
    @user_required
    def browser_api_history():
        uid = _uid()
        return jsonify({"history": _get_history(uid)})

    @app.route("/user/browser/api/history/add", methods=["POST"])
    @user_required
    def browser_api_history_add():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        if url:
            ok, _ = _validate_url(url)
            if ok:
                _add_history(uid, url)
        return jsonify({"ok": True})

    # ── proxy: add ─────────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/add", methods=["POST"])
    @user_required
    def browser_proxy_add():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        raw = str(data.get("proxy_url", "")).strip()
        name = str(data.get("name", "Proxy")).strip()[:80]
        if not raw:
            return jsonify({"ok": False, "error": "Proxy URL is required"})
        proxy_url = _parse_proxy_url(raw)
        if not proxy_url:
            return jsonify({"ok": False, "error": "Could not parse proxy format"})
        proxy_type = _detect_proxy_type(proxy_url)
        try:
            pid = _add_proxy(uid, name or "Proxy", proxy_url, proxy_type)
            return jsonify({"ok": True, "id": pid})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:120]})

    # ── proxy: edit ────────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/edit", methods=["POST"])
    @user_required
    def browser_proxy_edit():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        pid = _safe_int(data.get("proxy_id"))
        raw = str(data.get("proxy_url", "")).strip()
        name = str(data.get("name", "Proxy")).strip()[:80]
        if not pid:
            return jsonify({"ok": False, "error": "proxy_id required"})
        if not raw:
            return jsonify({"ok": False, "error": "Proxy URL required"})
        proxy_url = _parse_proxy_url(raw)
        if not proxy_url:
            return jsonify({"ok": False, "error": "Could not parse proxy format"})
        proxy_type = _detect_proxy_type(proxy_url)
        try:
            _edit_proxy(uid, pid, name or "Proxy", proxy_url, proxy_type)
            _reset_http_session(uid)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:120]})

    # ── proxy: delete ──────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/delete", methods=["POST"])
    @user_required
    def browser_proxy_delete():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        pid = _safe_int(data.get("proxy_id"))
        if not pid:
            return jsonify({"ok": False, "error": "proxy_id required"})
        _delete_proxy(uid, pid)
        return jsonify({"ok": True})

    # ── proxy: activate ────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/activate", methods=["POST"])
    @user_required
    def browser_proxy_activate():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        pid = _safe_int(data.get("proxy_id"))
        if not pid:
            return jsonify({"ok": False, "error": "proxy_id required"})
        _activate_proxy(uid, pid)
        _reset_http_session(uid)
        return jsonify({"ok": True})

    # ── proxy: deactivate ──────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/deactivate", methods=["POST"])
    @user_required
    def browser_proxy_deactivate():
        uid = _uid()
        _deactivate_all_proxies(uid)
        _reset_http_session(uid)
        return jsonify({"ok": True})

    # ── proxy: test ────────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/test", methods=["POST"])
    @user_required
    def browser_proxy_test():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        pid = _safe_int(data.get("proxy_id"))
        proxies_list = _list_proxies(uid)
        target = next((p for p in proxies_list if p["id"] == pid), None)
        if not target:
            return jsonify({"ok": False, "error": "Proxy not found"})
        proxy_url = _parse_proxy_url(target["proxy_url"])
        if not proxy_url:
            return jsonify({"ok": False, "error": "Invalid proxy URL"})
        proxies_dict = {"http": proxy_url, "https": proxy_url}
        t0 = time.time()
        try:
            r1 = _req.get("https://api.ipify.org?format=json", timeout=12, proxies=proxies_dict)
            ip = r1.json().get("ip", "")
            ms = int((time.time() - t0) * 1000)
        except _req.exceptions.ProxyError:
            return jsonify({"ok": False, "error": "Proxy connection refused"})
        except _req.exceptions.ConnectTimeout:
            return jsonify({"ok": False, "error": "Proxy timed out"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:80]})
        if not ip:
            return jsonify({"ok": False, "error": "No IP returned from proxy"})
        try:
            r2 = _req.get(f"http://ip-api.com/json/{ip}?fields=query,country,countryCode,isp", timeout=6)
            geo = r2.json()
            return jsonify({"ok": True, "ip": ip, "ms": ms,
                            "country": geo.get("country"), "country_code": geo.get("countryCode"),
                            "isp": geo.get("isp")})
        except Exception:
            return jsonify({"ok": True, "ip": ip, "ms": ms})

    # ── bookmark: add ──────────────────────────────────────────────────────────
    @app.route("/user/browser/api/bookmark/add", methods=["POST"])
    @user_required
    def browser_bm_add():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        title = str(data.get("title", "")).strip() or url[:60]
        ok_url, err = _validate_url(url)
        if not ok_url:
            return jsonify({"ok": False, "error": err})
        try:
            _add_bookmark(uid, title, url)
            bms = _list_bookmarks(uid)
            new_id = bms[0]["id"] if bms else 0
            return jsonify({"ok": True, "id": new_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:100]})

    # ── bookmark: delete ───────────────────────────────────────────────────────
    @app.route("/user/browser/api/bookmark/delete", methods=["POST"])
    @user_required
    def browser_bm_delete():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        bid = _safe_int(data.get("bookmark_id"))
        if not bid:
            return jsonify({"ok": False, "error": "bookmark_id required"})
        _delete_bookmark(uid, bid)
        return jsonify({"ok": True})

    print("[Browser] Routes registered ✓")
