"""
Browser Routes — In-panel web browser with proxy support.
Registered via register_browser_routes(app, ...) called from keep_alive.py.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import threading
import time
from urllib.parse import urljoin, urlparse, quote, unquote

import requests as _req
from flask import request, jsonify, session, redirect, render_template_string, Response

_log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_SCHEMES = {"http", "https"}
_BINARY_CONTENT_TYPES = {
    "image/", "audio/", "video/", "font/",
    "application/octet-stream", "application/pdf",
    "application/zip", "application/x-zip",
    "application/wasm",
}
_PASSTHROUGH_TYPES = {
    "application/javascript", "text/javascript",
    "text/css", "text/plain",
    "application/json",
}

_sessions_lock = threading.Lock()
_user_http_sessions: dict[str, _req.Session] = {}

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


# ── per-user requests.Session (persists cookies per user) ─────────────────────
def _get_http_session(uid: str) -> _req.Session:
    with _sessions_lock:
        if uid not in _user_http_sessions:
            s = _req.Session()
            s.headers.update({"User-Agent": _BROWSER_UA})
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


# ── helpers ───────────────────────────────────────────────────────────────────
def _he(s) -> str:
    return _html.escape(str(s) if s is not None else "")


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
    if low.startswith("data:") or low.startswith("javascript:") or url.startswith("#") or url.startswith("mailto:"):
        return url
    return urljoin(base, url)


def _proxied(absolute_url: str) -> str:
    return "/user/browser/fetch?url=" + quote(absolute_url, safe="")


# ── HTML rewriting ────────────────────────────────────────────────────────────
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)\s'\"]*)(['\"]?)\s*\)")
_META_REFRESH_RE = re.compile(r"(\d+)\s*;\s*url\s*=\s*(.*)", re.IGNORECASE)


def _rewrite_css_text(css: str, base_url: str) -> str:
    def _rep(m):
        quote_char = m.group(1)
        raw_url = m.group(2).strip()
        if not raw_url or raw_url.startswith("data:"):
            return m.group(0)
        abs_url = _make_absolute(raw_url, base_url)
        parsed = urlparse(abs_url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return m.group(0)
        return "url(" + quote_char + _proxied(abs_url) + quote_char + ")"
    return _CSS_URL_RE.sub(_rep, css)


def _rewrite_html(raw: bytes, base_url: str, encoding: str = "utf-8") -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return raw.decode(encoding, errors="replace")

    try:
        soup = BeautifulSoup(raw, "html.parser")
    except Exception:
        return raw.decode(encoding, errors="replace")

    # Inject postMessage helper so iframe notifies parent of navigation
    _pm_js = (
        "try{"
        "function _bpm(u){try{window.top.postMessage({type:'browser_nav',url:u},'*');}catch(e){}}"
        "var _bcu=window.location.href;_bpm(_bcu);"
        "window.addEventListener('load',function(){_bpm(window.location.href);});"
        "var _bpo=history.pushState;"
        "history.pushState=function(){_bpo.apply(this,arguments);_bpm(window.location.href);};"
        "var _bpr=history.replaceState;"
        "history.replaceState=function(){_bpr.apply(this,arguments);_bpm(window.location.href);};"
        "}catch(e){}"
    )
    tag_pm = soup.new_tag("script")
    tag_pm.string = _pm_js
    head = soup.find("head")
    if head:
        head.insert(0, tag_pm)
    else:
        soup.insert(0, tag_pm)

    # Rewrite href on <a>, <link>, <area>, <base>
    for tag in soup.find_all(["a", "link", "area"]):
        href = tag.get("href") or ""
        low_href = href.lower().lstrip()
        if href and not low_href.startswith("#") and not low_href.startswith("javascript:") and not low_href.startswith("data:") and not low_href.startswith("mailto:"):
            abs_url = _make_absolute(href, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["href"] = _proxied(abs_url)

    for tag in soup.find_all("base"):
        tag.decompose()

    # Rewrite action on <form>
    for tag in soup.find_all("form"):
        action = tag.get("action") or ""
        if action and not action.lower().startswith("javascript:"):
            abs_url = _make_absolute(action, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["action"] = _proxied(abs_url)

    # Rewrite src / srcset
    for tag in soup.find_all(["img", "script", "iframe", "embed", "audio", "video", "source", "track", "input"]):
        src = tag.get("src") or ""
        if src and not src.lower().startswith("data:") and not src.lower().startswith("javascript:"):
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

    # Rewrite <meta http-equiv="refresh">
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

    # Rewrite inline style="url(...)"
    for tag in soup.find_all(style=True):
        tag["style"] = _rewrite_css_text(tag["style"], base_url)

    # Rewrite <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = _rewrite_css_text(style_tag.string, base_url)

    return str(soup)


def _is_binary(content_type: str) -> bool:
    ct = content_type.lower().split(";")[0].strip()
    for prefix in _BINARY_CONTENT_TYPES:
        if ct.startswith(prefix):
            return True
    return False


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

    # ── CSS ───────────────────────────────────────────────────────────────────
    BROWSER_CSS = """
<style>
:root{--tb-h:54px;--stat-h:32px;}
body{overflow:hidden!important;height:100vh;display:flex;flex-direction:column;}
.main-content{padding:0!important;flex:1;display:flex;flex-direction:column;overflow:hidden;height:100%;}

/* Toolbar */
.br-toolbar{display:flex;align-items:center;gap:6px;padding:6px 10px;
  background:rgba(20,10,35,.97);border-bottom:1px solid rgba(255,105,180,.2);
  height:var(--tb-h);flex-shrink:0;z-index:50;}
.br-toolbar button{background:rgba(255,255,255,.08);border:1px solid rgba(255,105,180,.2);
  color:#fff;border-radius:7px;padding:5px 9px;cursor:pointer;font-size:.9rem;
  transition:background .15s;min-width:32px;}
.br-toolbar button:hover{background:rgba(255,105,180,.2);}
.br-toolbar button:disabled{opacity:.35;cursor:not-allowed;}
.br-addr{flex:1;background:rgba(255,255,255,.07);border:1px solid rgba(255,105,180,.25);
  color:#fff;border-radius:20px;padding:6px 16px;font-size:.88rem;outline:none;
  min-width:0;}
.br-addr:focus{border-color:#ff69b4;background:rgba(255,255,255,.1);}
.br-scheme{font-size:.8rem;padding:4px 8px;border-radius:6px;font-weight:700;margin-right:-4px;}
.br-scheme.https{background:rgba(74,222,128,.15);color:#4ade80;}
.br-scheme.http{background:rgba(255,190,0,.12);color:#fbbf24;}
.br-scheme.none{display:none;}

/* Status bar */
.br-status{display:flex;align-items:center;gap:10px;padding:2px 12px;
  background:rgba(15,5,25,.9);border-bottom:1px solid rgba(255,105,180,.12);
  height:var(--stat-h);flex-shrink:0;font-size:.72rem;color:#aaa;}
.br-proxy-badge{display:flex;align-items:center;gap:4px;background:rgba(255,105,180,.1);
  border:1px solid rgba(255,105,180,.25);border-radius:10px;padding:1px 8px;color:#ff99cc;}
.br-proxy-badge.off{background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.1);color:#666;}
.br-ip{color:#7ec8e3;font-family:monospace;}

/* Main area */
.br-main{flex:1;display:flex;overflow:hidden;}
.br-frame-wrap{flex:1;position:relative;background:#111;}
#br-frame{width:100%;height:100%;border:none;display:block;}
.br-loading-overlay{position:absolute;inset:0;background:rgba(10,5,20,.95);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  z-index:10;transition:opacity .3s;}
.br-spinner{width:44px;height:44px;border:3px solid rgba(255,105,180,.2);
  border-top-color:#ff69b4;border-radius:50%;animation:br-spin .8s linear infinite;margin-bottom:14px;}
@keyframes br-spin{to{transform:rotate(360deg);}}
.br-load-txt{color:#aaa;font-size:.82rem;}

/* Side panel */
.br-side{width:300px;background:rgba(15,5,25,.98);border-left:1px solid rgba(255,105,180,.15);
  display:flex;flex-direction:column;overflow:hidden;transition:width .25s;flex-shrink:0;}
.br-side.collapsed{width:0;}
.br-side-inner{min-width:300px;flex:1;display:flex;flex-direction:column;overflow:hidden;}
.br-side-tabs{display:flex;border-bottom:1px solid rgba(255,105,180,.15);flex-shrink:0;}
.br-side-tab{flex:1;padding:9px;text-align:center;cursor:pointer;font-size:.78rem;
  color:#aaa;transition:all .2s;border-bottom:2px solid transparent;}
.br-side-tab.active{color:#ff69b4;border-color:#ff69b4;background:rgba(255,105,180,.05);}
.br-side-body{flex:1;overflow-y:auto;padding:10px;}
.br-side-section{display:none;}
.br-side-section.active{display:block;}
.br-pitem{display:flex;align-items:center;gap:6px;padding:8px;border-radius:8px;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,105,180,.1);margin-bottom:6px;}
.br-pitem.active-proxy{border-color:#4ade80;background:rgba(74,222,128,.07);}
.br-pitem-name{flex:1;font-size:.82rem;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.br-pitem-type{font-size:.68rem;color:#aaa;padding:1px 5px;background:rgba(255,255,255,.07);border-radius:4px;}
.br-pill-btn{padding:3px 8px;font-size:.7rem;border-radius:5px;cursor:pointer;border:none;font-weight:700;}
.br-pill-activate{background:rgba(74,222,128,.2);color:#4ade80;}
.br-pill-deactivate{background:rgba(255,190,0,.2);color:#fbbf24;}
.br-pill-test{background:rgba(125,200,255,.15);color:#7ec8e3;}
.br-pill-del{background:rgba(239,68,68,.15);color:#f87171;}
.br-add-form label{display:block;font-size:.75rem;color:#aaa;margin-bottom:2px;margin-top:8px;}
.br-add-form input,.br-add-form select{width:100%;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,105,180,.2);color:#fff;border-radius:7px;padding:5px 10px;
  font-size:.82rem;font-family:inherit;box-sizing:border-box;}
.br-bm-item{display:flex;align-items:center;gap:6px;padding:6px;border-radius:7px;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);margin-bottom:5px;cursor:pointer;}
.br-bm-item:hover{background:rgba(255,105,180,.08);}
.br-bm-title{flex:1;font-size:.8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ddd;}
.br-bm-url{font-size:.68rem;color:#888;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:2;}
.br-hist-item{padding:5px 8px;border-radius:6px;cursor:pointer;font-size:.78rem;color:#ccc;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-bottom:1px solid rgba(255,255,255,.04);}
.br-hist-item:hover{background:rgba(255,105,180,.08);}
.br-toggle-side{background:rgba(255,255,255,.07)!important;padding:4px 8px!important;font-size:.8rem!important;}
.br-msg{font-size:.75rem;padding:5px 8px;border-radius:5px;margin-top:6px;}
.br-msg.ok{background:rgba(74,222,128,.12);color:#4ade80;}
.br-msg.err{background:rgba(239,68,68,.12);color:#f87171;}
</style>
"""

    def _uid():
        return str(session.get("user_id") or "")

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

        # Proxy list HTML
        def _proxy_item(p):
            pid = p["id"]
            pname = _he(p["name"])
            ptype = _he(p["proxy_type"])
            purl_safe = _he(p["proxy_url"])
            is_act = p["is_active"]
            active_cls = " active-proxy" if is_act else ""
            badge = "✓ Active" if is_act else "Inactive"
            badge_cls = "br-pitem.active-proxy" if is_act else ""
            act_btn_cls = "br-pill-deactivate" if is_act else "br-pill-activate"
            act_btn_label = "Deactivate" if is_act else "Activate"
            act_fn = "deactivateProxy()" if is_act else ("activateProxy(" + str(pid) + ")")
            return (
                f'<div class="br-pitem{active_cls}" id="pitem-{pid}">'
                f'<div style="flex:1;min-width:0">'
                f'<div class="br-pitem-name" title="{purl_safe}">{pname}</div>'
                f'<div style="font-size:.68rem;color:#888;margin-top:1px">{purl_safe[:40]}</div>'
                f'</div>'
                f'<span class="br-pitem-type">{ptype}</span>'
                f'<button class="br-pill-btn {act_btn_cls}" onclick="{act_fn}">{act_btn_label}</button>'
                f'<button class="br-pill-btn br-pill-test" onclick="testProxy({pid})">Test</button>'
                f'<button class="br-pill-btn br-pill-del" onclick="delProxy({pid})">✕</button>'
                f'</div>'
            )

        proxies_html = "".join(_proxy_item(p) for p in proxies)
        if not proxies_html:
            proxies_html = '<div style="color:#666;font-size:.8rem;text-align:center;padding:20px">No proxies saved yet.</div>'

        # Bookmark list HTML
        def _bm_item(b):
            bid = b["id"]
            btitle = _he(b["title"])
            burl = _he(b["url"])
            burl_raw = b["url"].replace("'", "\\'")
            return (
                f'<div class="br-bm-item" onclick="navigateTo(\'{burl_raw}\')">'
                f'<div style="flex:0 0 16px;font-size:.75rem">🔖</div>'
                f'<div style="flex:1;min-width:0">'
                f'<div class="br-bm-title">{btitle}</div>'
                f'<div class="br-bm-url">{burl}</div>'
                f'</div>'
                f'<button class="br-pill-btn br-pill-del" onclick="event.stopPropagation();delBookmark({bid})">✕</button>'
                f'</div>'
            )

        bm_html = "".join(_bm_item(b) for b in bookmarks)
        if not bm_html:
            bm_html = '<div style="color:#666;font-size:.8rem;text-align:center;padding:20px">No bookmarks saved yet.</div>'

        proxy_status_badge = ""
        if active_proxy:
            proxy_status_badge = (
                f'<span class="br-proxy-badge">🛡 {proxy_name_safe} ({proxy_type_safe})</span>'
                f'<span id="br-ip" class="br-ip">checking...</span>'
            )
        else:
            proxy_status_badge = (
                '<span class="br-proxy-badge off">🔓 No proxy (direct)</span>'
                '<span id="br-ip" class="br-ip"></span>'
            )

        sidebar = get_user_sidebar("browser", "Browser")

        return render_template_string("""<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Browser — Onichan</title>
""" + USER_CSS + BROWSER_CSS + """
</head><body>
""" + sidebar + """
<div class="main-content">

<!-- Toolbar -->
<div class="br-toolbar">
  <button id="btn-back" onclick="goBack()" title="Back" disabled>&#8592;</button>
  <button id="btn-fwd" onclick="goForward()" title="Forward" disabled>&#8594;</button>
  <button id="btn-reload" onclick="doReload()" title="Reload">&#10227;</button>
  <button id="btn-stop" onclick="doStop()" title="Stop" style="display:none">&#10005;</button>
  <span id="br-scheme" class="br-scheme none">https</span>
  <input id="br-addr" class="br-addr" type="text" placeholder="Enter URL and press Enter..."
    onkeydown="if(event.key==='Enter'){navigateTo(this.value)}"
    onfocus="this.select()">
  <button onclick="navigateTo(document.getElementById('br-addr').value)" title="Go" style="padding:5px 14px;font-weight:700">Go</button>
  <button onclick="addBookmark()" title="Bookmark" style="font-size:1rem">🔖</button>
  <button class="br-toggle-side" onclick="toggleSide()" title="Panel">☰</button>
</div>

<!-- Status bar -->
<div class="br-status">
  """ + proxy_status_badge + """
  <span id="br-stat-txt" style="margin-left:auto;font-size:.7rem;color:#555">Ready</span>
</div>

<!-- Main: frame + side panel -->
<div class="br-main">
  <div class="br-frame-wrap">
    <div id="br-loading" class="br-loading-overlay" style="display:none">
      <div class="br-spinner"></div>
      <div class="br-load-txt" id="br-load-txt">Loading...</div>
    </div>
    <iframe id="br-frame" sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>
  </div>

  <!-- Side panel -->
  <div class="br-side" id="br-side">
    <div class="br-side-inner">
      <div class="br-side-tabs">
        <div class="br-side-tab active" id="tab-proxy" onclick="switchTab('proxy')">🛡 Proxy</div>
        <div class="br-side-tab" id="tab-bm" onclick="switchTab('bm')">🔖 Bookmarks</div>
        <div class="br-side-tab" id="tab-hist" onclick="switchTab('hist')">🕐 History</div>
      </div>
      <div class="br-side-body">

        <!-- Proxy tab -->
        <div id="sec-proxy" class="br-side-section active">
          <div id="proxy-list">""" + proxies_html + """</div>
          <div id="proxy-test-result" style="margin-top:8px"></div>
          <hr style="border-color:rgba(255,105,180,.15);margin:10px 0">
          <div style="font-size:.78rem;font-weight:700;color:#ff99cc;margin-bottom:6px">Add Proxy</div>
          <div class="br-add-form">
            <label>Name</label>
            <input id="add-name" placeholder="My Proxy" type="text">
            <label>Proxy URL / Format</label>
            <input id="add-url" placeholder="ip:port or ip:port:user:pass or socks5://...">
            <button onclick="addProxy()" style="margin-top:10px;width:100%;background:linear-gradient(135deg,#e94560,#9b2e9b);color:#fff;border:none;border-radius:8px;padding:7px;cursor:pointer;font-weight:700;">Add Proxy</button>
            <div id="add-result" style="margin-top:4px"></div>
          </div>
        </div>

        <!-- Bookmarks tab -->
        <div id="sec-bm" class="br-side-section">
          <div id="bm-list">""" + bm_html + """</div>
        </div>

        <!-- History tab -->
        <div id="sec-hist" class="br-side-section">
          <div id="hist-list"><div style="color:#666;font-size:.8rem;text-align:center;padding:20px">Navigate somewhere to build history.</div></div>
        </div>

      </div>
    </div>
  </div>
</div><!-- .br-main -->
</div><!-- .main-content -->

<script>
// ── navigation history ───────────────────────────────────────────────────────
var _hist = [];
var _histIdx = -1;

function _updateNavBtns() {
  document.getElementById('btn-back').disabled = (_histIdx <= 0);
  document.getElementById('btn-fwd').disabled = (_histIdx >= _hist.length - 1);
}

function _setSchemeIndicator(url) {
  var el = document.getElementById('br-scheme');
  if (!url) { el.className = 'br-scheme none'; return; }
  if (url.startsWith('https')) {
    el.textContent = '🔒';
    el.className = 'br-scheme https';
  } else {
    el.textContent = '⚠️';
    el.className = 'br-scheme http';
  }
}

function navigateTo(url) {
  if (!url || !url.trim()) return;
  url = url.trim();
  // Auto-add https:// if missing
  if (!/^https?:\/\//i.test(url) && !url.startsWith('//')) {
    url = 'https://' + url;
  }
  document.getElementById('br-addr').value = url;
  _setSchemeIndicator(url);
  _showLoading(url);
  var fetchUrl = '/user/browser/fetch?url=' + encodeURIComponent(url);
  // Truncate forward history
  if (_histIdx < _hist.length - 1) {
    _hist = _hist.slice(0, _histIdx + 1);
  }
  _hist.push(url);
  _histIdx = _hist.length - 1;
  _updateNavBtns();
  _addHistItem(url);
  document.getElementById('br-frame').src = fetchUrl;
}

function goBack() {
  if (_histIdx <= 0) return;
  _histIdx--;
  var url = _hist[_histIdx];
  document.getElementById('br-addr').value = url;
  _setSchemeIndicator(url);
  _showLoading(url);
  document.getElementById('br-frame').src = '/user/browser/fetch?url=' + encodeURIComponent(url);
  _updateNavBtns();
}

function goForward() {
  if (_histIdx >= _hist.length - 1) return;
  _histIdx++;
  var url = _hist[_histIdx];
  document.getElementById('br-addr').value = url;
  _setSchemeIndicator(url);
  _showLoading(url);
  document.getElementById('br-frame').src = '/user/browser/fetch?url=' + encodeURIComponent(url);
  _updateNavBtns();
}

function doReload() {
  var frame = document.getElementById('br-frame');
  var src = frame.src;
  if (src) {
    _showLoading('');
    frame.src = src;
  }
}

function doStop() {
  document.getElementById('br-frame').src = 'about:blank';
  _hideLoading();
}

function _showLoading(url) {
  var lo = document.getElementById('br-loading');
  var lt = document.getElementById('br-load-txt');
  lo.style.display = 'flex';
  lt.textContent = url ? ('Loading: ' + url.substring(0, 60) + (url.length > 60 ? '...' : '')) : 'Loading...';
  document.getElementById('btn-stop').style.display = '';
  document.getElementById('btn-reload').style.display = 'none';
  document.getElementById('br-stat-txt').textContent = 'Loading...';
}

function _hideLoading() {
  document.getElementById('br-loading').style.display = 'none';
  document.getElementById('btn-stop').style.display = 'none';
  document.getElementById('btn-reload').style.display = '';
  document.getElementById('br-stat-txt').textContent = 'Done';
}

// Listen for postMessage from proxied pages
window.addEventListener('message', function(e) {
  if (e.data && e.data.type === 'browser_nav') {
    var url = e.data.url || '';
    // Decode if it's the proxied URL
    var m = url.match(/[?&]url=([^&]+)/);
    if (m) {
      try { url = decodeURIComponent(m[1]); } catch(ex) {}
    }
    if (url && url !== 'about:blank') {
      document.getElementById('br-addr').value = url;
      _setSchemeIndicator(url);
    }
  }
});

// iframe load/error
document.getElementById('br-frame').addEventListener('load', function() {
  _hideLoading();
});

document.getElementById('br-frame').addEventListener('error', function() {
  _hideLoading();
  document.getElementById('br-stat-txt').textContent = 'Error loading page';
});

// ── history panel ─────────────────────────────────────────────────────────────
var _histDisplayed = [];
function _addHistItem(url) {
  _histDisplayed.push(url);
  if (_histDisplayed.length > 50) _histDisplayed = _histDisplayed.slice(-50);
  _renderHist();
}
function _renderHist() {
  var list = document.getElementById('hist-list');
  if (!list) return;
  var items = _histDisplayed.slice().reverse().slice(0, 20);
  list.innerHTML = items.map(function(u) {
    var uSafe = u.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    var uJs = u.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    return '<div class="br-hist-item" onclick="navigateTo(\'' + uJs + '\')">' + uSafe + '</div>';
  }).join('');
}

// ── tab switching ─────────────────────────────────────────────────────────────
function switchTab(name) {
  ['proxy','bm','hist'].forEach(function(n) {
    var t = document.getElementById('tab-' + n);
    var s = document.getElementById('sec-' + n);
    if (t) t.className = 'br-side-tab' + (n === name ? ' active' : '');
    if (s) s.className = 'br-side-section' + (n === name ? ' active' : '');
  });
}

// ── side panel toggle ─────────────────────────────────────────────────────────
function toggleSide() {
  var el = document.getElementById('br-side');
  el.classList.toggle('collapsed');
}

// ── proxy management ──────────────────────────────────────────────────────────
function activateProxy(id) {
  fetch('/user/browser/api/proxy/activate', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({proxy_id:id})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) location.reload();
    else alert(d.error || 'Error');
  }).catch(()=>alert('Request failed'));
}

function deactivateProxy() {
  fetch('/user/browser/api/proxy/deactivate', {method:'POST'})
  .then(r=>r.json()).then(d=>{
    if(d.ok) location.reload();
    else alert(d.error || 'Error');
  }).catch(()=>alert('Request failed'));
}

function delProxy(id) {
  if (!confirm('Delete this proxy?')) return;
  fetch('/user/browser/api/proxy/delete', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({proxy_id:id})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) { var el=document.getElementById('pitem-'+id); if(el) el.remove(); }
    else alert(d.error || 'Error');
  }).catch(()=>alert('Request failed'));
}

function testProxy(id) {
  var res = document.getElementById('proxy-test-result');
  res.innerHTML = '<div class="br-msg ok">Testing proxy...</div>';
  fetch('/user/browser/api/proxy/test', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({proxy_id:id})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) {
      var flag = d.country_code ? ' ' + String.fromCodePoint(...[...d.country_code].map(c=>c.charCodeAt(0)+127397)) : '';
      res.innerHTML = '<div class="br-msg ok">✅ Alive &mdash; IP: ' + (d.ip||'?') + flag + ' | ' + (d.country||'?') + ' | ' + (d.ms||'?') + 'ms</div>';
    } else {
      res.innerHTML = '<div class="br-msg err">❌ ' + (d.error||'Failed') + '</div>';
    }
  }).catch(()=>{ res.innerHTML='<div class="br-msg err">Request failed</div>'; });
}

function addProxy() {
  var name = document.getElementById('add-name').value.trim();
  var url = document.getElementById('add-url').value.trim();
  var res = document.getElementById('add-result');
  if (!url) { res.innerHTML='<div class="br-msg err">Proxy URL is required</div>'; return; }
  fetch('/user/browser/api/proxy/add', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name||'Proxy',proxy_url:url})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) {
      res.innerHTML='<div class="br-msg ok">Proxy added! Reloading...</div>';
      setTimeout(()=>location.reload(), 700);
    } else {
      res.innerHTML='<div class="br-msg err">❌ '+(d.error||'Error')+'</div>';
    }
  }).catch(()=>{ res.innerHTML='<div class="br-msg err">Request failed</div>'; });
}

// ── bookmarks ─────────────────────────────────────────────────────────────────
function addBookmark() {
  var url = document.getElementById('br-addr').value.trim();
  if (!url) return;
  var title = prompt('Bookmark title:', url.replace(/https?:\/\//,'').split('/')[0]) || url;
  fetch('/user/browser/api/bookmark/add', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:title, url:url})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) {
      var list=document.getElementById('bm-list');
      var uSafe=url.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      var tSafe=title.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      var uJs=url.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
      var newHtml='<div class="br-bm-item" onclick="navigateTo(\''+uJs+'\')">'
        +'<div style="flex:0 0 16px;font-size:.75rem">🔖</div>'
        +'<div style="flex:1;min-width:0">'
        +'<div class="br-bm-title">'+tSafe+'</div>'
        +'<div class="br-bm-url">'+uSafe+'</div>'
        +'</div>'
        +'<button class="br-pill-btn br-pill-del" onclick="event.stopPropagation();delBookmark('+d.id+')">✕</button>'
        +'</div>';
      if(list.querySelector('div[style]')) list.innerHTML='';
      list.insertAdjacentHTML('afterbegin', newHtml);
    }
  }).catch(()=>{});
}

function delBookmark(id) {
  fetch('/user/browser/api/bookmark/delete', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({bookmark_id:id})})
  .then(r=>r.json()).then(d=>{
    if(d.ok) { location.reload(); }
  }).catch(()=>{});
}

// ── IP check on load ──────────────────────────────────────────────────────────
(function() {
  var ipEl = document.getElementById('br-ip');
  if (!ipEl) return;
  fetch('/user/browser/api/ip')
    .then(r=>r.json())
    .then(d=>{
      if(d.ip) {
        var flag='';
        if(d.country_code && d.country_code.length===2){
          try{ flag=' '+String.fromCodePoint(...[...d.country_code].map(c=>c.charCodeAt(0)+127397)); }catch(e){}
        }
        ipEl.textContent = d.ip + flag + (d.country ? ' (' + d.country + ')' : '');
      }
    }).catch(()=>{});
})();
</script>
</body></html>""")

    # ── fetch endpoint ─────────────────────────────────────────────────────────
    @app.route("/user/browser/fetch")
    @user_required
    def browser_fetch():
        uid = _uid()
        raw_url = request.args.get("url", "").strip()

        # Auto-add scheme
        if raw_url and "://" not in raw_url and not raw_url.startswith("//"):
            raw_url = "https://" + raw_url

        ok, err = _validate_url(raw_url)
        if not ok:
            error_html = (
                "<html><body style='background:#0a0515;color:#fff;font-family:sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column'>"
                "<div style='font-size:3rem'>⚠️</div>"
                "<h2 style='color:#f87171;margin:10px 0'>Cannot load page</h2>"
                "<p style='color:#aaa;font-size:.9rem'>" + _he(err) + "</p>"
                "<p style='color:#666;font-size:.8rem'>URL: " + _he(raw_url[:200]) + "</p>"
                "</body></html>"
            )
            return Response(error_html, status=400, content_type="text/html; charset=utf-8")

        active_proxy = _get_active_proxy_row(uid)
        proxies_dict = None
        if active_proxy:
            proxy_url = _parse_proxy_url(active_proxy["proxy_url"])
            if proxy_url:
                proxies_dict = {"http": proxy_url, "https": proxy_url}

        http_session = _get_http_session(uid)

        try:
            resp = http_session.get(
                raw_url,
                timeout=_FETCH_TIMEOUT,
                proxies=proxies_dict,
                stream=True,
                allow_redirects=True,
                headers={"Accept-Encoding": "identity"},
            )
        except _req.exceptions.ProxyError as e:
            err_msg = "Proxy error — check your proxy settings."
            _log.warning("browser proxy error uid=%s url=%s: %s", uid, raw_url[:100], e)
        except _req.exceptions.ConnectionError as e:
            err_msg = "Connection error — could not reach the server."
        except _req.exceptions.Timeout:
            err_msg = "Request timed out after 15 seconds."
        except Exception as e:
            err_msg = "Fetch failed: " + str(e)[:120]
        else:
            err_msg = None

        if err_msg:
            error_html = (
                "<html><body style='background:#0a0515;color:#fff;font-family:sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column'>"
                "<div style='font-size:3rem'>🚫</div>"
                "<h2 style='color:#f87171;margin:10px 0'>Page load failed</h2>"
                "<p style='color:#aaa;font-size:.9rem'>" + _he(err_msg) + "</p>"
                "<p style='color:#666;font-size:.8rem'>URL: " + _he(raw_url[:200]) + "</p>"
                "<p style='margin-top:20px'><a href='javascript:history.back()' "
                "style='color:#ff69b4;font-size:.85rem'>Go Back</a></p>"
                "</body></html>"
            )
            return Response(error_html, status=502, content_type="text/html; charset=utf-8")

        ct = resp.headers.get("Content-Type", "text/html")
        final_url = resp.url or raw_url

        # Stream binary / passthrough content directly
        if _is_binary(ct) or _is_passthrough(ct):
            content = resp.raw.read(amt=_MAX_RESPONSE_BYTES)
            r = Response(content, status=resp.status_code, content_type=ct)
            for hdr in ("Cache-Control", "ETag", "Last-Modified"):
                if hdr in resp.headers:
                    r.headers[hdr] = resp.headers[hdr]
            return r

        # HTML — read and rewrite
        raw_bytes = resp.raw.read(amt=_MAX_RESPONSE_BYTES)
        encoding = resp.encoding or "utf-8"
        rewritten = _rewrite_html(raw_bytes, final_url, encoding)
        flask_resp = Response(rewritten, status=resp.status_code, content_type="text/html; charset=utf-8")
        # Strip headers that would prevent iframe embedding
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
            r1 = _req.get(
                "https://api.ipify.org?format=json",
                timeout=8,
                proxies=proxies_dict,
            )
            ip = r1.json().get("ip", "")
        except Exception:
            return jsonify({"ip": None})
        if not ip:
            return jsonify({"ip": None})
        try:
            r2 = _req.get(
                f"http://ip-api.com/json/{ip}?fields=query,country,countryCode,isp",
                timeout=6,
            )
            geo = r2.json()
            return jsonify({
                "ip": ip,
                "country": geo.get("country"),
                "country_code": geo.get("countryCode"),
                "isp": geo.get("isp"),
            })
        except Exception:
            return jsonify({"ip": ip})

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

    # ── proxy: delete ──────────────────────────────────────────────────────────
    @app.route("/user/browser/api/proxy/delete", methods=["POST"])
    @user_required
    def browser_proxy_delete():
        uid = _uid()
        data = request.get_json(silent=True) or {}
        pid = int(data.get("proxy_id", 0))
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
        pid = int(data.get("proxy_id", 0))
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
        pid = int(data.get("proxy_id", 0))
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
            r1 = _req.get(
                "https://api.ipify.org?format=json",
                timeout=12,
                proxies=proxies_dict,
            )
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
            r2 = _req.get(
                f"http://ip-api.com/json/{ip}?fields=query,country,countryCode,isp",
                timeout=6,
            )
            geo = r2.json()
            return jsonify({
                "ok": True, "ip": ip, "ms": ms,
                "country": geo.get("country"),
                "country_code": geo.get("countryCode"),
                "isp": geo.get("isp"),
            })
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
        bid = int(data.get("bookmark_id", 0))
        if not bid:
            return jsonify({"ok": False, "error": "bookmark_id required"})
        _delete_bookmark(uid, bid)
        return jsonify({"ok": True})

    print("[Browser] Routes registered ✓")
