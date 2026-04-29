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


# ── Privacy: UA pool, tracking-param stripper, tracker blocklist ──────────────
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
]

_TRACKING_PARAMS = frozenset({
    # UTM family
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_brand", "utm_creative", "utm_creative_format",
    "utm_marketing_tactic", "utm_source_platform", "utm_referrer", "utm_name",
    # Click identifiers
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "yclid", "wbraid", "gbraid",
    "twclid", "li_fat_id", "ttclid", "rb_clickid", "_openstat",
    # Analytics / referral
    "_ga", "_gl", "mc_cid", "mc_eid", "icid", "igshid",
    "ref_src", "ref_url", "vero_id", "vero_conv",
    "oly_anon_id", "oly_enc_id",
    # HubSpot
    "hsCtaTracking", "hsa_acc", "hsa_cam", "hsa_grp", "hsa_ad", "hsa_src",
    "hsa_tgt", "hsa_kw", "hsa_mt", "hsa_net", "hsa_ver", "_hsenc", "_hsmi",
    # Branch
    "_branch_match_id", "_branch_referrer",
    # Misc
    "ga_source", "ga_medium", "ga_term", "ga_content", "ga_campaign",
    "spm", "scm", "trk", "trkCampaign",
    "campaign_id", "ad_id", "adgroup_id", "creative_id",
    "ScCid", "irclickid", "irgwc",
    "mkt_tok", "pk_campaign", "pk_kwd",
    "piwik_campaign", "piwik_kwd",
    "yclid", "ymclid", "from_action", "from",
})


def _strip_tracking_params(url: str) -> str:
    """Remove well-known tracking parameters from the query string."""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        qs = parse_qs(parsed.query, keep_blank_values=True)
        clean = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
        if len(clean) == len(qs):
            return url
        new_qs = urlencode(clean, doseq=True)
        return urlunparse(parsed._replace(query=new_qs))
    except Exception:
        return url


# Curated default tracker / ad blocklist. Hostname suffix-matched.
_DEFAULT_BLOCKLIST = frozenset({
    # Google ads / analytics / trackers
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "google-analytics.com", "googletagmanager.com", "googletagservices.com",
    "adservice.google.com", "adservice.google.co.uk", "adservice.google.de",
    "pagead2.googlesyndication.com", "stats.g.doubleclick.net",
    "partner.googleadservices.com", "tpc.googlesyndication.com",
    "fundingchoicesmessages.google.com",
    # Facebook / Meta tracking pixels
    "connect.facebook.net", "an.facebook.com",
    # Twitter / X
    "ads-twitter.com", "static.ads-twitter.com", "analytics.twitter.com",
    "platform.twitter.com",
    # Adobe
    "demdex.net", "everesttech.net", "omtrdc.net", "2o7.net",
    "adobedtm.com", "adobetm.com",
    # Microsoft / Bing
    "bat.bing.com", "clarity.ms", "c.bing.com",
    # LinkedIn
    "ads.linkedin.com", "px.ads.linkedin.com",
    # Amazon ads
    "amazon-adsystem.com", "amazonclix.com",
    # TikTok
    "analytics.tiktok.com", "ads-api.tiktok.com",
    # Pinterest
    "ct.pinterest.com",
    # Snapchat
    "tr.snapchat.com", "sc-static.net",
    # Reddit
    "redditstatic.com", "events.redditmedia.com", "alb.reddit.com",
    # Quantserve
    "quantserve.com", "quantcount.com",
    # Outbrain / Taboola native ads
    "outbrain.com", "outbrainimg.com", "widgets.outbrain.com",
    "taboola.com", "trc.taboola.com", "cdn.taboola.com",
    # Criteo retargeting
    "criteo.com", "criteo.net", "static.criteo.net",
    # Yahoo / Verizon Media
    "yieldmanager.com", "advertising.com", "atwola.com",
    "analytics.yahoo.com", "ads.yahoo.com",
    # Comscore
    "scorecardresearch.com", "comscore.com",
    # Chartbeat / NewRelic / etc
    "chartbeat.com", "static.chartbeat.com",
    # Mixpanel / Amplitude / Heap / Segment
    "mixpanel.com", "api.mixpanel.com", "cdn.mxpnl.com",
    "amplitude.com", "api.amplitude.com",
    "heap.io", "heapanalytics.com",
    "segment.io", "segment.com", "cdn.segment.com",
    "api.segment.io",
    # Hotjar / FullStory / SessionStack / LogRocket
    "hotjar.com", "static.hotjar.com", "script.hotjar.com",
    "fullstory.com", "rs.fullstory.com",
    "logrocket.com", "cdn.lr-ingest.io",
    # Optimizely / VWO / Crazy Egg
    "optimizely.com", "cdn.optimizely.com",
    "visualwebsiteoptimizer.com", "vwo.com",
    "crazyegg.com", "script.crazyegg.com",
    # Intercom / Drift / Tawk (sometimes tracking)
    "intercom-cdn.com",
    # Ad networks
    "adsrvr.org", "adnxs.com", "rubiconproject.com", "openx.net",
    "pubmatic.com", "moatads.com", "adform.net", "adsafeprotected.com",
    "advertising.com", "casalemedia.com", "spotxchange.com",
    "rlcdn.com", "agkn.com", "bluekai.com", "krxd.net",
    "rfihub.com", "tapad.com", "adroll.com",
    "mathtag.com", "exelator.com", "turn.com",
    "yieldlab.net", "smartadserver.com", "indexww.com",
    "lijit.com", "sonobi.com", "33across.com",
    "deployads.com", "monetate.net",
    # Misc trackers
    "newrelic.com", "nr-data.net", "bam.nr-data.net",
    "clicktale.net",
    "branch.io", "app.link",
    "bugsnag.com", "rollbar.com",  # error reporting (informational)
    "trackjs.com", "loggly.com",
    # Push notification spam
    "onesignal.com", "cdn.onesignal.com",
    "notifio.io", "pushcrew.com", "sendpulse.com",
    # General known offenders
    "addthis.com", "sharethis.com", "addthisedge.com",
    "disqus.com", "disquscdn.com",  # social widgets, sometimes tracking
})


def _load_blocklist() -> frozenset:
    """Load default blocklist + optional user-extension file."""
    extras: set[str] = set()
    try:
        import os as _os
        path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "browser_blocklist.txt")
        if _os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    h = line.strip().lower()
                    if h and not h.startswith("#"):
                        extras.add(h)
    except Exception:
        pass
    return frozenset(_DEFAULT_BLOCKLIST | extras)


_BLOCKLIST: frozenset = _load_blocklist()


def _is_blocked_host(host: str) -> bool:
    """Suffix-match the hostname against the tracker blocklist."""
    if not host:
        return False
    h = host.lower().lstrip(".")
    parts = h.split(".")
    # Try each suffix from the full host down to the eTLD+1
    for i in range(len(parts) - 1):
        if ".".join(parts[i:]) in _BLOCKLIST:
            return True
    return False


# ── Per-tab session map (Incognito tabs each get a fresh ephemeral Session) ───
_tab_lock = threading.Lock()
# uid -> { tab_key: requests.Session }   — only populated for private tabs
_tab_sessions: dict[str, dict[str, _req.Session]] = {}
# uid -> { tab_key: {"ua":..,"private":..,"last_used":..,"blocked":..} }
_tab_meta: dict[str, dict[str, dict]] = {}
_TAB_IDLE_TTL = 60 * 60  # 1 hour idle → evict private tab session
_MAX_PRIVATE_TABS_PER_USER = 30  # hard cap; LRU eviction beyond this

# Tab key format: alphanumerics, dash, underscore. Frontend generates
# "n-<id>" or "inc-<id>-<hex>", so a permissive but bounded charset is enough.
_TAB_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _valid_tab_key(tab_key: str) -> bool:
    return bool(tab_key) and bool(_TAB_KEY_RE.match(tab_key))


def _make_private_session(ua: str) -> _req.Session:
    s = _req.Session()
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Sec-GPC": "1",
    })
    try:
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=0)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
    except Exception:
        pass
    return s


def _ensure_tab_meta(uid: str, tab_key: str, private: bool) -> dict:
    """Create-or-touch a tab's metadata entry. Also evicts idle private tabs."""
    import random as _random
    with _tab_lock:
        meta_map = _tab_meta.setdefault(uid, {})
        if tab_key not in meta_map:
            ua = _random.choice(_UA_POOL) if private else _BROWSER_UA
            meta_map[tab_key] = {
                "ua": ua, "private": bool(private),
                "last_used": time.time(), "blocked": 0,
            }
        else:
            meta_map[tab_key]["last_used"] = time.time()
        # Evict idle private tabs
        cutoff = time.time() - _TAB_IDLE_TTL
        sess_map = _tab_sessions.setdefault(uid, {})
        stale = [k for k, m in meta_map.items()
                 if m.get("private") and m.get("last_used", 0) < cutoff
                 and k != tab_key]
        for k in stale:
            sess = sess_map.pop(k, None)
            if sess:
                try:
                    sess.close()
                except Exception:
                    pass
            meta_map.pop(k, None)
        # Hard cap: if the user is hoarding private tabs (intentionally or via
        # buggy/abusive client), LRU-evict until we're back under the cap.
        priv_keys = [k for k, m in meta_map.items() if m.get("private")]
        if len(priv_keys) > _MAX_PRIVATE_TABS_PER_USER:
            priv_keys.sort(key=lambda k: meta_map[k].get("last_used", 0))
            # Never evict the tab we just touched.
            victims = [k for k in priv_keys if k != tab_key][
                : len(priv_keys) - _MAX_PRIVATE_TABS_PER_USER
            ]
            for k in victims:
                sess = sess_map.pop(k, None)
                if sess:
                    try:
                        sess.close()
                    except Exception:
                        pass
                meta_map.pop(k, None)
        return meta_map[tab_key]


def _get_session_for_tab(uid: str, tab_key: str, meta: dict) -> _req.Session:
    """Return the requests.Session backing this tab.

    Normal tabs share the user's primary cookie jar; Incognito tabs each
    get their own ephemeral Session with a randomised UA.
    """
    if not meta.get("private"):
        return _get_http_session(uid)
    with _tab_lock:
        sess_map = _tab_sessions.setdefault(uid, {})
        if tab_key not in sess_map:
            sess_map[tab_key] = _make_private_session(meta["ua"])
        return sess_map[tab_key]


def _close_tab(uid: str, tab_key: str) -> None:
    """Evict a tab's session and metadata (called on browser tab close)."""
    if not tab_key:
        return
    with _tab_lock:
        sess_map = _tab_sessions.get(uid, {})
        sess = sess_map.pop(tab_key, None)
        _tab_meta.get(uid, {}).pop(tab_key, None)
        if sess:
            try:
                sess.close()
            except Exception:
                pass


def _bump_blocked(uid: str, tab_key: str) -> int:
    with _tab_lock:
        meta = _tab_meta.get(uid, {}).get(tab_key)
        if meta is None:
            return 0
        meta["blocked"] = meta.get("blocked", 0) + 1
        return meta["blocked"]


def _wipe_user_browser(uid: str) -> None:
    """Wipe everything: tab sessions, primary cookies, history, and bookmarks.

    The Privacy panel UI advertises that this clears bookmarks too, so we
    delete them here. Best-effort: a DB failure shouldn't break the wipe of
    in-memory state.
    """
    with _tab_lock:
        sess_map = _tab_sessions.pop(uid, {})
        _tab_meta.pop(uid, None)
        for s in sess_map.values():
            try:
                s.close()
            except Exception:
                pass
    _reset_http_session(uid)
    with _history_lock:
        _user_history.pop(uid, None)
    try:
        from modules.database import _execute_with_retry as _db
        def _q(conn):
            with conn.cursor() as cur:
                cur.execute("DELETE FROM browser_bookmarks WHERE user_id=%s", (uid,))
        _db(_q)
    except Exception:
        pass


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


def _proxied(absolute_url: str, tab_key: str = "", private: bool = False) -> str:
    out = "/user/browser/fetch?url=" + quote(absolute_url, safe="")
    if tab_key:
        out += "&t=" + quote(tab_key, safe="")
    if private:
        out += "&p=1"
    return out


# ── HTML rewriting ────────────────────────────────────────────────────────────
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)\s'\"]*)(['\"]?)\s*\)")
_META_REFRESH_RE = re.compile(r"(\d+)\s*;\s*url\s*=\s*(.*)", re.IGNORECASE)

# Injected JS: postMessage navigation sync + GET-form interceptor
_INJECT_JS = """
(function(){
try{
// Report current URL + page title to parent frame so the tab strip
// can render a real Chrome-style title.
function _bpm(u){
  try{
    window.top.postMessage({
      type:'browser_nav',
      url:u,
      title:(document.title||'').slice(0,200)
    },'*');
  }catch(e){}
}
_bpm(window.location.href);
window.addEventListener('load',function(){_bpm(window.location.href);});
// Re-emit when the page title changes (SPAs).
try{
  var _ttEl=document.querySelector('title');
  if(_ttEl&&window.MutationObserver){
    new MutationObserver(function(){_bpm(window.location.href);})
      .observe(_ttEl,{childList:true,characterData:true,subtree:true});
  }
}catch(e){}
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
      // Preserve tab affinity (t) and incognito flag (p) from the action URL
      // so form GET navigations don't drop out of the current tab/private context.
      var tm=action.match(/[?&]t=([^&]*)/);
      var pm=action.match(/[?&]p=([^&]*)/);
      var dest='/user/browser/fetch?url='+encodeURIComponent(finalUrl);
      if(tm) dest+='&t='+encodeURIComponent(tm[1]);
      if(pm) dest+='&p='+encodeURIComponent(pm[1]);
      window.location.href=dest;
    });
  });
}
document.addEventListener('DOMContentLoaded',_interceptForms);
if(document.readyState!=='loading') _interceptForms();
}catch(e){}
})();
"""


def _rewrite_css_text(css: str, base_url: str, tab_key: str = "", private: bool = False) -> str:
    def _rep(m):
        quote_char = m.group(1)
        raw_url = m.group(2).strip()
        if not raw_url or raw_url.startswith("data:"):
            return m.group(0)
        abs_url = _make_absolute(raw_url, base_url)
        if urlparse(abs_url).scheme not in _ALLOWED_SCHEMES:
            return m.group(0)
        return "url(" + quote_char + _proxied(abs_url, tab_key, private) + quote_char + ")"
    return _CSS_URL_RE.sub(_rep, css)


def _rewrite_html(raw: bytes, base_url: str, encoding: str = "utf-8",
                  tab_key: str = "", private: bool = False) -> str:
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
                tag["href"] = _proxied(abs_url, tab_key, private)

    # Remove <base> tags to prevent relative URL confusion
    for tag in soup.find_all("base"):
        tag.decompose()

    # <form> — rewrite action; GET forms also handled by injected JS
    for tag in soup.find_all("form"):
        action = tag.get("action") or ""
        if action and not action.lower().startswith("javascript:"):
            abs_url = _make_absolute(action, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["action"] = _proxied(abs_url, tab_key, private)

    # Elements with src / srcset
    for tag in soup.find_all(["img", "script", "iframe", "embed", "audio", "video", "source", "track", "input"]):
        src = tag.get("src") or ""
        if src and not src.lower().startswith(("data:", "javascript:")):
            abs_url = _make_absolute(src, base_url)
            if urlparse(abs_url).scheme in _ALLOWED_SCHEMES:
                tag["src"] = _proxied(abs_url, tab_key, private)
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
                    parts.append(_proxied(abs_url, tab_key, private) + descriptor)
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
                    tag["content"] = delay + ";url=" + _proxied(abs_url, tab_key, private)

    # Inline style= and <style> blocks
    for tag in soup.find_all(style=True):
        tag["style"] = _rewrite_css_text(tag["style"], base_url, tab_key, private)
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = _rewrite_css_text(style_tag.string, base_url, tab_key, private)

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

/* ── Multi-tab strip + Incognito theming ── */
.br-shell{flex:1;display:flex;flex-direction:column;min-height:0;overflow:hidden;}
.br-tabstrip{display:flex;align-items:flex-end;background:rgba(8,3,18,.98);
  padding:6px 4px 0 6px;gap:2px;overflow-x:auto;overflow-y:hidden;
  scrollbar-width:thin;scrollbar-color:rgba(255,105,180,.4) transparent;
  flex-shrink:0;border-bottom:1px solid rgba(255,105,180,.18);
  -webkit-overflow-scrolling:touch;}
.br-tabstrip::-webkit-scrollbar{height:4px;}
.br-tabstrip::-webkit-scrollbar-thumb{background:rgba(255,105,180,.4);border-radius:2px;}
.br-tab{position:relative;display:flex;align-items:center;gap:6px;height:30px;
  min-width:90px;max-width:200px;flex-shrink:1;padding:0 6px 0 12px;
  background:rgba(255,255,255,.04);border-radius:8px 8px 0 0;
  color:#aaa;cursor:pointer;font-size:.78rem;font-weight:500;
  border:1px solid transparent;border-bottom:none;user-select:none;
  white-space:nowrap;transition:background .12s,color .12s;}
.br-tab:hover{background:rgba(255,105,180,.08);color:#ddd;}
.br-tab.active{background:rgba(20,10,35,.98);
  border-color:rgba(255,105,180,.25);color:#fff;z-index:2;
  box-shadow:0 -1px 0 rgba(255,105,180,.15);}
.br-tab.incognito::before{content:'';position:absolute;top:0;left:0;right:0;
  height:2px;background:linear-gradient(90deg,#9b2e9b,#c084fc);
  border-radius:8px 8px 0 0;}
.br-tab-icon{flex-shrink:0;font-size:.78rem;opacity:.85;}
.br-tab-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.br-tab-close{flex-shrink:0;width:18px;height:18px;border-radius:50%;
  background:transparent;border:none;color:inherit;font-size:.85rem;line-height:1;
  cursor:pointer;opacity:0;display:flex;align-items:center;justify-content:center;
  padding:0;-webkit-tap-highlight-color:rgba(255,255,255,.2);
  transition:opacity .12s ease;}
/* Chrome behaviour: × shows on tab hover OR when the tab is active. */
.br-tab:hover .br-tab-close{opacity:.7;}
.br-tab.active .br-tab-close{opacity:.85;}
.br-tab-close:hover{background:rgba(255,255,255,.16);opacity:1;}
.br-tab-favicon{flex-shrink:0;width:14px;height:14px;border-radius:2px;
  object-fit:contain;background:rgba(255,255,255,.06);}
/* Disabled bookmark button (active tab is Incognito) */
.br-tb-btn.disabled{opacity:.35;cursor:not-allowed;
  background:rgba(192,132,252,.06)!important;}
.br-tb-btn.disabled:hover{background:rgba(192,132,252,.06)!important;}
.br-newtab-wrap{position:relative;flex-shrink:0;display:flex;align-items:flex-end;}
.br-newtab-btn{height:26px;width:34px;margin:0 2px 2px 4px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,105,180,.18);
  color:#fff;border-radius:6px;cursor:pointer;font-size:1.05rem;line-height:1;
  display:flex;align-items:center;justify-content:center;padding:0;}
.br-newtab-btn:hover{background:rgba(255,105,180,.18);}
.br-newtab-menu{position:absolute;top:30px;left:4px;
  background:rgba(20,10,35,.99);border:1px solid rgba(255,105,180,.3);
  border-radius:10px;min-width:220px;padding:4px;
  box-shadow:0 6px 18px rgba(0,0,0,.6);z-index:120;display:none;}
.br-newtab-menu.open{display:block;}
.br-newtab-menu-item{display:flex;align-items:center;gap:10px;
  padding:8px 10px;cursor:pointer;border-radius:6px;
  font-size:.82rem;color:#ddd;}
.br-newtab-menu-item:hover{background:rgba(255,105,180,.15);color:#fff;}
.br-newtab-menu-item .ico{font-size:1rem;width:20px;text-align:center;}
.br-newtab-menu-item .kbd{margin-left:auto;font-size:.62rem;color:#888;
  background:rgba(255,255,255,.08);padding:1px 6px;border-radius:4px;
  font-family:ui-monospace,monospace;}

/* Incognito accent on toolbar/tabstrip when active tab is private */
.br-shell.incognito .br-tabstrip{
  background:linear-gradient(180deg,rgba(40,15,60,.98) 0%,rgba(20,10,35,.98) 100%);
  border-bottom-color:rgba(192,132,252,.32);}
.br-shell.incognito .br-toolbar{
  background:linear-gradient(180deg,rgba(50,20,80,.98) 0%,rgba(20,10,35,.98) 100%);
  border-bottom-color:rgba(192,132,252,.35);}
.br-shell.incognito .br-tab.active{background:rgba(40,18,68,.98);
  border-color:rgba(192,132,252,.35);}

/* Per-tab iframe container (TabManager injects iframes inside) */
.br-frames{position:absolute;inset:0;width:100%;height:100%;}
.br-frame{position:absolute;inset:0;width:100%;height:100%;border:none;
  background:#0d0520;}

/* Blocked tracker badge */
.br-blocked-badge{display:none;align-items:center;gap:3px;
  background:rgba(74,222,128,.12);border:1px solid rgba(74,222,128,.32);
  border-radius:10px;padding:1px 7px;color:#4ade80;font-size:.68rem;
  font-weight:700;cursor:help;white-space:nowrap;}

/* Wipe button + Privacy section */
.br-wipe-btn{width:100%;margin-top:10px;background:rgba(239,68,68,.14);
  color:#f87171;border:1px solid rgba(239,68,68,.38);border-radius:10px;
  padding:11px;font-weight:700;font-size:.86rem;cursor:pointer;
  -webkit-tap-highlight-color:rgba(239,68,68,.3);}
.br-wipe-btn:hover{background:rgba(239,68,68,.22);}
.br-priv-list{font-size:.76rem;color:#bbb;line-height:1.7;
  background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);
  border-radius:10px;padding:10px 14px;}
.br-priv-list .ok{color:#4ade80;}

/* Incognito splash welcome */
.br-welcome.incognito-splash{background:rgba(8,3,18,.55);}
.br-welcome.incognito-splash .br-welcome-icon{font-size:4rem;opacity:.55;
  filter:drop-shadow(0 0 18px rgba(192,132,252,.4));}
.br-welcome-title{color:#c084fc;font-size:1.1rem;
  font-weight:700;margin-top:2px;}
.br-welcome-bullets{color:rgba(255,255,255,.65);font-size:.78rem;
  text-align:left;line-height:1.7;max-width:380px;
  background:rgba(192,132,252,.06);border:1px solid rgba(192,132,252,.18);
  border-radius:10px;padding:10px 16px;margin-top:6px;}
.br-welcome-bullets div{display:flex;gap:8px;align-items:baseline;}
.br-welcome-bullets .yes{color:#4ade80;flex-shrink:0;width:14px;}
.br-welcome-bullets .no{color:#f87171;flex-shrink:0;width:14px;}

/* Mobile tab strip tweaks */
@media(max-width:768px){
  .br-tab{min-width:60px;max-width:140px;padding:0 4px 0 10px;
    font-size:.72rem;height:30px;}
  .br-tab-icon{display:none;}
  /* On touch the close × is shown only on the active tab — there is no
     hover state on touch screens, so always-on for inactive would be too
     noisy. Active tab gets the × so it's still closeable with one tap. */
  .br-tab.active .br-tab-close{opacity:.9;}
  .br-tabstrip{padding:5px 4px 0 4px;}
  .br-newtab-btn{width:30px;}
  .br-newtab-menu{min-width:200px;}
}
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

<div class="br-shell" id="br-shell">

<!-- Tab strip -->
<div class="br-tabstrip" id="br-tabstrip">
  <div class="br-newtab-wrap" id="br-newtab-wrap">
    <button class="br-newtab-btn" onclick="toggleNewTabMenu(event)" title="New tab" aria-haspopup="true">+</button>
    <div class="br-newtab-menu" id="br-newtab-menu" role="menu">
      <div class="br-newtab-menu-item" onclick="newTabFromMenu('normal')" role="menuitem">
        <span class="ico">🌐</span><span>New tab</span><span class="kbd">Ctrl+T</span>
      </div>
      <div class="br-newtab-menu-item" onclick="newTabFromMenu('incognito')" role="menuitem">
        <span class="ico">🕶</span><span>New Incognito tab</span><span class="kbd">Ctrl+Shift+N</span>
      </div>
      <div class="br-newtab-menu-item" onclick="reopenLastClosedFromMenu()" role="menuitem">
        <span class="ico">↺</span><span>Reopen last closed tab</span><span class="kbd">Ctrl+Shift+T</span>
      </div>
    </div>
  </div>
</div>

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
  <button class="br-tb-btn" id="btn-bookmark" onclick="addBookmark()" title="Bookmark">🔖</button>
  <button class="br-tb-btn" onclick="openSettings('proxy')" title="Settings">⚙️</button>
</div>

<!-- Status bar -->
<div class="br-status">
  <span class="br-proxy-badge """ + ("" if active_proxy else "off") + """" onclick="openSettings('proxy')">
    """ + ("🛡 " + proxy_name_safe + " (" + proxy_type_safe + ")" if active_proxy else "🔓 No proxy (direct)") + """
  </span>
  <span id="br-ip" class="br-ip"></span>
  <span id="br-blocked" class="br-blocked-badge" title="Trackers blocked on this tab">🛡 0</span>
  <span id="br-stat-txt" style="margin-left:auto;color:#444">Ready</span>
</div>

<!-- Browser frame -->
<div class="br-frame-wrap">
  <div id="br-loading" class="br-loading-overlay" style="display:none">
    <div class="br-spinner"></div>
    <div class="br-load-txt" id="br-load-txt">Loading...</div>
  </div>
  <div id="br-frames" class="br-frames"></div>
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
  <div class="br-welcome incognito-splash" id="br-welcome-incognito" style="display:none">
    <div class="br-welcome-icon">🕶</div>
    <div class="br-welcome-title">You've gone Incognito</div>
    <div class="br-welcome-txt">Pages you view in this tab won't be saved.</div>
    <div class="br-welcome-bullets">
      <div><span class="yes">✓</span><span>No browsing history is recorded</span></div>
      <div><span class="yes">✓</span><span>Cookies are wiped when this tab closes</span></div>
      <div><span class="yes">✓</span><span>Random User-Agent per tab</span></div>
      <div><span class="yes">✓</span><span>Referer dropped, DNT &amp; Sec-GPC sent</span></div>
      <div><span class="yes">✓</span><span>Tracking parameters stripped from URLs</span></div>
      <div><span class="yes">✓</span><span>Tracker / ad hosts are blocked</span></div>
      <div><span class="no">✗</span><span>Bookmarks are disabled in Incognito</span></div>
    </div>
    <div class="br-welcome-quick">
      <button onclick="navigateTo('https://duckduckgo.com')">🦆 DuckDuckGo</button>
      <button onclick="navigateTo('https://startpage.com')">🌟 Startpage</button>
    </div>
  </div>
</div>

</div><!-- .br-shell -->

<!-- Settings backdrop -->
<div class="br-backdrop" id="br-backdrop" onclick="closeSettings()"></div>

<!-- Settings bottom sheet -->
<div class="br-modal" id="br-modal">
  <div class="br-modal-drag"></div>
  <div class="br-modal-tabs">
    <div class="br-modal-tab active" id="mtab-proxy" onclick="switchTab('proxy')">🛡 Proxy</div>
    <div class="br-modal-tab" id="mtab-bm" onclick="switchTab('bm')">🔖 Bookmarks</div>
    <div class="br-modal-tab" id="mtab-hist" onclick="switchTab('hist')">🕐 History</div>
    <div class="br-modal-tab" id="mtab-priv" onclick="switchTab('priv')">🔒 Privacy</div>
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

    <!-- Privacy tab -->
    <div id="msec-priv" class="br-modal-sec">
      <div class="br-section-title">What Incognito does</div>
      <div class="br-priv-list">
        <div><span class="ok">✓</span> Each Incognito tab uses a fresh, isolated cookie jar</div>
        <div><span class="ok">✓</span> A random User-Agent is picked per tab</div>
        <div><span class="ok">✓</span> Referer is dropped, DNT &amp; Sec-GPC are sent</div>
        <div><span class="ok">✓</span> Tracking parameters (utm_*, fbclid, gclid, …) are stripped</div>
        <div><span class="ok">✓</span> Tracker / ad hosts are blocked entirely</div>
        <div><span class="ok">✓</span> No browsing history is recorded</div>
        <div><span class="ok">✓</span> Tab cookies are wiped when the tab closes</div>
      </div>
      <hr class="br-divider">
      <div class="br-section-title">Wipe everything</div>
      <div style="font-size:.78rem;color:#aaa;line-height:1.5">
        Delete every tab's session, all stored cookies, in-memory history, and bookmarks for your account. This cannot be undone.
      </div>
      <button class="br-wipe-btn" onclick="wipeBrowser()">🗑 Wipe all browser data</button>
      <div id="wipe-result"></div>
    </div>

  </div>
</div>

</div><!-- .main-content -->
<script>
// ── Helpers ───────────────────────────────────────────────────────────────────
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
  if(/^[a-z][a-z0-9+.-]*:\\/\\//i.test(s))return s;
  if(s.startsWith('//'))return 'https:'+s;
  if(/^about:/i.test(s))return s;
  var firstSpace=s.indexOf(' ');
  var hasDotOrPort=/^[^\\s\\/]+\\.[^\\s\\/]+/.test(s)||/^[^\\s\\/]+:[0-9]+(\\/|$)/.test(s);
  if(firstSpace===-1&&hasDotOrPort){return 'https://'+s;}
  return 'https://duckduckgo.com/?q='+encodeURIComponent(s);
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

// ── TabManager ────────────────────────────────────────────────────────────────
function TabManager(){
  this.tabs=[];
  this.activeId=null;
  this.lastClosed=[];
  this.nextId=1;
}
TabManager.prototype._gen=function(){return String(this.nextId++);};
TabManager.prototype._find=function(id){
  for(var i=0;i<this.tabs.length;i++)if(this.tabs[i].id===id)return this.tabs[i];
  return null;
};
TabManager.prototype.active=function(){return this._find(this.activeId);};
TabManager.prototype.newTab=function(mode,url,opts){
  opts=opts||{};
  mode=(mode==='incognito')?'incognito':'normal';
  var id=this._gen();
  var rand='';
  try{
    var arr=new Uint8Array(8);crypto.getRandomValues(arr);
    rand=Array.prototype.map.call(arr,function(b){return ('0'+b.toString(16)).slice(-2);}).join('');
  }catch(e){rand=Math.random().toString(36).slice(2,12);}
  var tabKey=(mode==='incognito')?('inc-'+id+'-'+rand):('n-'+id);
  var tab={id:id,tabKey:tabKey,mode:mode,url:'',hist:[],histIdx:-1,
    blocked:0,iframe:null,loaded:false,suppressNextLoad:false};
  this.tabs.push(tab);
  this._createIframe(tab);
  this._render();
  if(!opts.background)this.activate(id);
  if(url)this.navigate(id,url);
  return tab;
};
TabManager.prototype._createIframe=function(tab){
  var wrap=document.getElementById('br-frames');
  var f=document.createElement('iframe');
  f.className='br-frame';
  f.dataset.tabId=tab.id;
  f.setAttribute('sandbox','allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox');
  f.setAttribute('referrerpolicy','no-referrer');
  f.setAttribute('loading','eager');
  f.setAttribute('fetchpriority','high');
  f.style.display='none';
  var self=this;
  f.addEventListener('load',function(){self._onIframeLoad(tab);});
  f.addEventListener('error',function(){self._onIframeError(tab);});
  wrap.appendChild(f);
  tab.iframe=f;
};
TabManager.prototype.activate=function(id){
  var tab=this._find(id);if(!tab)return;
  this.activeId=id;
  for(var i=0;i<this.tabs.length;i++){
    var t=this.tabs[i];
    if(t.iframe)t.iframe.style.display=(t.id===id)?'block':'none';
  }
  document.getElementById('br-addr').value=tab.url||'';
  _setScheme(tab.url||'');
  this._updateNavBtns();
  this._updateBlockedBadge();
  this._updateShellMode();
  this._updateWelcome();
  if(tab.loaded||!tab.url)_hideLoading();
  this._render();
};
TabManager.prototype.navigate=function(id,url){
  url=_normalizeUrl(url);
  if(!url)return;
  var tab=this._find(id);if(!tab)return;
  tab.url=url;
  if(tab.histIdx<tab.hist.length-1){tab.hist=tab.hist.slice(0,tab.histIdx+1);}
  tab.hist.push(url);
  tab.histIdx=tab.hist.length-1;
  if(tab.id===this.activeId){
    document.getElementById('br-addr').value=url;
    _setScheme(url);
    this._updateNavBtns();
  }
  if(tab.mode!=='incognito')_pushServerHistory(url);
  this._loadIframe(tab,url);
  this._render();
  this._updateWelcome();
};
TabManager.prototype._loadIframe=function(tab,url){
  var qs='?url='+encodeURIComponent(url)+
         '&t='+encodeURIComponent(tab.tabKey)+
         (tab.mode==='incognito'?'&p=1':'');
  if(tab.id===this.activeId)_showLoading(url);
  tab.loaded=false;
  tab.iframe.src='/user/browser/fetch'+qs;
};
TabManager.prototype.goBack=function(){
  var tab=this.active();if(!tab||tab.histIdx<=0)return;
  tab.histIdx--;
  var url=tab.hist[tab.histIdx];tab.url=url;
  document.getElementById('br-addr').value=url;_setScheme(url);
  this._loadIframe(tab,url);
  this._updateNavBtns();
  this._render();
};
TabManager.prototype.goForward=function(){
  var tab=this.active();if(!tab||tab.histIdx>=tab.hist.length-1)return;
  tab.histIdx++;
  var url=tab.hist[tab.histIdx];tab.url=url;
  document.getElementById('br-addr').value=url;_setScheme(url);
  this._loadIframe(tab,url);
  this._updateNavBtns();
  this._render();
};
TabManager.prototype.reload=function(){
  var tab=this.active();if(!tab||!tab.url)return;
  this._loadIframe(tab,tab.url);
};
TabManager.prototype.stop=function(){
  var tab=this.active();if(!tab)return;
  try{tab.iframe.contentWindow.stop();}catch(e){}
  try{tab.iframe.src='about:blank';}catch(e){}
  tab.url='';tab.hist=[];tab.histIdx=-1;
  document.getElementById('br-addr').value='';
  _setScheme('');_hideLoading();
  this._updateNavBtns();
  this._updateWelcome();
  this._render();
};
TabManager.prototype.closeTab=function(id){
  var idx=-1;
  for(var i=0;i<this.tabs.length;i++)if(this.tabs[i].id===id){idx=i;break;}
  if(idx<0)return;
  var tab=this.tabs[idx];
  if(tab.url){
    this.lastClosed.push({url:tab.url,mode:tab.mode});
    if(this.lastClosed.length>10)this.lastClosed.shift();
  }
  // Server eviction (beacon-friendly)
  var payload=JSON.stringify({tab_key:tab.tabKey});
  var sent=false;
  try{
    if(navigator.sendBeacon){
      var blob=new Blob([payload],{type:'application/json'});
      sent=navigator.sendBeacon('/user/browser/api/tab/close',blob);
    }
  }catch(e){}
  if(!sent){
    try{
      fetch('/user/browser/api/tab/close',{method:'POST',
        headers:{'Content-Type':'application/json'},body:payload,keepalive:true}).catch(function(){});
    }catch(e){}
  }
  // Detach iframe
  if(tab.iframe&&tab.iframe.parentNode)tab.iframe.parentNode.removeChild(tab.iframe);
  this.tabs.splice(idx,1);
  if(this.tabs.length===0){
    this.newTab('normal');
  }else if(this.activeId===id){
    var nxt=this.tabs[Math.min(idx,this.tabs.length-1)];
    this.activate(nxt.id);
  }else{
    this._render();
  }
};
TabManager.prototype.reopenLastClosed=function(){
  var item=this.lastClosed.pop();
  if(item)this.newTab(item.mode,item.url);
};
TabManager.prototype.switchByOffset=function(off){
  if(this.tabs.length<=1)return;
  var idx=-1;
  for(var i=0;i<this.tabs.length;i++)if(this.tabs[i].id===this.activeId){idx=i;break;}
  if(idx<0)return;
  var n=(idx+off+this.tabs.length)%this.tabs.length;
  this.activate(this.tabs[n].id);
};
TabManager.prototype.activateByIndex=function(n){
  if(n<0||n>=this.tabs.length)return;
  this.activate(this.tabs[n].id);
};
TabManager.prototype.findTabBySource=function(src){
  for(var i=0;i<this.tabs.length;i++){
    if(this.tabs[i].iframe&&this.tabs[i].iframe.contentWindow===src)return this.tabs[i];
  }
  return null;
};
TabManager.prototype.updateUrlFromIframe=function(tabId,newUrl){
  var tab=this._find(tabId);if(!tab)return;
  if(tab.hist[tab.histIdx]!==newUrl){
    if(tab.histIdx<tab.hist.length-1)tab.hist=tab.hist.slice(0,tab.histIdx+1);
    tab.hist.push(newUrl);
    tab.histIdx=tab.hist.length-1;
  }
  tab.url=newUrl;
  if(tab.id===this.activeId){
    document.getElementById('br-addr').value=newUrl;
    _setScheme(newUrl);
    this._updateNavBtns();
  }
  if(tab.mode!=='incognito')_pushServerHistory(newUrl);
  this._render();
};
TabManager.prototype._onIframeLoad=function(tab){
  tab.loaded=true;
  if(tab.id===this.activeId)_hideLoading();
  this._refreshBlocked(tab);
};
TabManager.prototype._onIframeError=function(tab){
  tab.loaded=true;
  if(tab.id===this.activeId){
    _hideLoading();
    document.getElementById('br-stat-txt').textContent='Error';
  }
};
TabManager.prototype._refreshBlocked=function(tab){
  var self=this;
  fetch('/user/browser/api/tab/state?t='+encodeURIComponent(tab.tabKey))
    .then(function(r){return r.json();})
    .then(function(d){
      if(d&&typeof d.blocked==='number'){
        tab.blocked=d.blocked;
        if(tab.id===self.activeId)self._updateBlockedBadge();
      }
    }).catch(function(){});
};
TabManager.prototype._tabTitle=function(t){
  if(t&&t.title)return t.title;
  if(!t||!t.url)return (t&&t.mode==='incognito')?'Incognito':'New Tab';
  try{
    var u=new URL(t.url);
    return u.hostname.replace(/^www\\./,'')||t.url;
  }catch(e){return t.url.substring(0,30);}
};
TabManager.prototype._faviconUrl=function(t){
  // Incognito tabs show NO favicon — fetching one would leak the visited
  // hostname to the favicon provider, defeating the privacy guarantee.
  if(!t||!t.url||t.mode==='incognito')return '';
  try{
    var u=new URL(t.url);
    if(!/^https?:$/.test(u.protocol))return '';
    // Use Google's favicon service via our own proxy so the user's
    // browser never directly contacts a third party.
    var fav='https://www.google.com/s2/favicons?domain='+
            encodeURIComponent(u.hostname)+'&sz=32';
    return '/user/browser/fetch?url='+encodeURIComponent(fav)+
           '&t='+encodeURIComponent(t.tabKey||'');
  }catch(e){return '';}
};
TabManager.prototype._render=function(){
  var strip=document.getElementById('br-tabstrip');if(!strip)return;
  var existing=strip.querySelectorAll('.br-tab');
  for(var i=0;i<existing.length;i++)existing[i].remove();
  var newtabWrap=document.getElementById('br-newtab-wrap');
  var self=this;
  for(var j=0;j<this.tabs.length;j++){
    (function(t){
      var el=document.createElement('div');
      el.className='br-tab'+(t.id===self.activeId?' active':'')+
                   (t.mode==='incognito'?' incognito':'');
      el.dataset.tabId=t.id;
      el.title=t.url||(t.mode==='incognito'?'Incognito tab':'New Tab');
      // Real favicon for normal tabs (proxied through our backend so the
      // user's browser never speaks directly to the favicon provider);
      // emoji glyph for Incognito and pre-navigation tabs.
      var iconNode;
      var favUrl=self._faviconUrl(t);
      if(favUrl){
        iconNode=document.createElement('img');
        iconNode.className='br-tab-favicon';
        iconNode.alt='';
        iconNode.referrerPolicy='no-referrer';
        iconNode.src=favUrl;
        iconNode.addEventListener('error',function(){
          // Replace broken favicon with a generic glyph.
          var span=document.createElement('span');
          span.className='br-tab-icon';
          span.textContent='🌐';
          if(iconNode.parentNode)iconNode.parentNode.replaceChild(span,iconNode);
        });
      }else{
        iconNode=document.createElement('span');
        iconNode.className='br-tab-icon';
        iconNode.textContent=(t.mode==='incognito')?'🕶':'🌐';
      }
      var titleSpan=document.createElement('span');
      titleSpan.className='br-tab-title';
      titleSpan.textContent=self._tabTitle(t);
      var closeBtn=document.createElement('button');
      closeBtn.className='br-tab-close';
      closeBtn.textContent='\u00d7';
      closeBtn.title='Close tab';
      closeBtn.addEventListener('mousedown',function(e){e.stopPropagation();});
      closeBtn.addEventListener('click',function(e){
        e.stopPropagation();
        self.closeTab(t.id);
      });
      el.appendChild(iconNode);
      el.appendChild(titleSpan);
      el.appendChild(closeBtn);
      el.addEventListener('click',function(){self.activate(t.id);});
      el.addEventListener('auxclick',function(e){
        if(e.button===1){e.preventDefault();self.closeTab(t.id);}
      });
      strip.insertBefore(el,newtabWrap);
    })(this.tabs[j]);
  }
};
TabManager.prototype._updateNavBtns=function(){
  var t=this.active();
  var b=document.getElementById('btn-back');
  var f=document.getElementById('btn-fwd');
  if(!t){if(b)b.disabled=true;if(f)f.disabled=true;return;}
  if(b)b.disabled=(t.histIdx<=0);
  if(f)f.disabled=(t.histIdx>=t.hist.length-1);
};
TabManager.prototype._updateBlockedBadge=function(){
  var el=document.getElementById('br-blocked');
  var t=this.active();
  if(!el)return;
  if(t&&t.blocked>0){
    el.style.display='inline-flex';
    el.textContent='🛡 '+t.blocked;
    el.title=t.blocked+' tracker requests blocked on this tab';
  }else{
    el.style.display='none';
  }
};
TabManager.prototype._updateShellMode=function(){
  var sh=document.getElementById('br-shell');
  var t=this.active();
  if(!sh)return;
  if(t&&t.mode==='incognito')sh.classList.add('incognito');
  else sh.classList.remove('incognito');
  this._updateBookmarkBtn();
};
TabManager.prototype._updateBookmarkBtn=function(){
  // Required by task spec: bookmark icon is replaced with a disabled
  // lock icon (tooltip explains why) when the active tab is Incognito.
  var btn=document.getElementById('btn-bookmark');
  if(!btn)return;
  var t=this.active();
  if(t&&t.mode==='incognito'){
    btn.classList.add('disabled');
    btn.setAttribute('aria-disabled','true');
    btn.dataset.priv='1';
    btn.textContent='🔒';
    btn.title='Bookmarks are disabled in Incognito tabs';
  }else{
    btn.classList.remove('disabled');
    btn.removeAttribute('aria-disabled');
    delete btn.dataset.priv;
    btn.textContent='🔖';
    btn.title='Bookmark';
  }
};
TabManager.prototype._updateWelcome=function(){
  var w=document.getElementById('br-welcome');
  var wi=document.getElementById('br-welcome-incognito');
  var t=this.active();
  if(!w||!wi)return;
  if(t&&!t.url){
    if(t.mode==='incognito'){w.style.display='none';wi.style.display='flex';}
    else{w.style.display='flex';wi.style.display='none';}
  }else{
    w.style.display='none';wi.style.display='none';
  }
};

var TM=new TabManager();

// ── Global wrappers (called from inline onclick=) ────────────────────────────
function navigateTo(url){
  var t=TM.active();if(!t)t=TM.newTab('normal');
  closeSettings();
  TM.navigate(t.id,url);
}
function goBack(){TM.goBack();}
function goForward(){TM.goForward();}
function doReload(){TM.reload();}
function doStop(){TM.stop();}
function newTab(mode){
  TM.newTab(mode||'normal');
  var addr=document.getElementById('br-addr');
  if(addr){addr.focus();addr.select();}
}
function closeActiveTab(){var t=TM.active();if(t)TM.closeTab(t.id);}
function toggleNewTabMenu(e){
  if(e&&e.stopPropagation)e.stopPropagation();
  var m=document.getElementById('br-newtab-menu');
  if(m)m.classList.toggle('open');
}
function _closeNewTabMenu(){
  var m=document.getElementById('br-newtab-menu');
  if(m)m.classList.remove('open');
}
function newTabFromMenu(mode){_closeNewTabMenu();newTab(mode);}
function reopenLastClosedFromMenu(){_closeNewTabMenu();TM.reopenLastClosed();}
document.addEventListener('click',function(e){
  var m=document.getElementById('br-newtab-menu');
  var w=document.getElementById('br-newtab-wrap');
  if(m&&m.classList.contains('open')&&w&&!w.contains(e.target)){
    m.classList.remove('open');
  }
});

// ── postMessage from rewritten pages ─────────────────────────────────────────
window.addEventListener('message',function(e){
  if(!e.data||e.data.type!=='browser_nav')return;
  var tab=TM.findTabBySource(e.source);
  if(!tab)return;
  var url=e.data.url||'';
  var m=url.match(/[?&]url=([^&]+)/);
  if(m){try{url=decodeURIComponent(m[1]);}catch(ex){}}
  // Real page title from the loaded document (Chrome-style tabs).
  if(typeof e.data.title==='string'){
    tab.title=e.data.title.replace(/\\s+/g,' ').trim().slice(0,120);
  }
  if(url&&url!=='about:blank'&&!/^\\/user\\/browser\\/fetch/.test(url)){
    TM.updateUrlFromIframe(tab.id,url);
  }else{
    // URL didn't change but title may have — re-render the strip.
    TM._render();
  }
});

// ── Tab close on page unload ─────────────────────────────────────────────────
window.addEventListener('pagehide',function(){
  for(var i=0;i<TM.tabs.length;i++){
    var t=TM.tabs[i];
    try{
      var blob=new Blob([JSON.stringify({tab_key:t.tabKey})],{type:'application/json'});
      navigator.sendBeacon&&navigator.sendBeacon('/user/browser/api/tab/close',blob);
    }catch(e){}
  }
});

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
document.addEventListener('keydown',function(e){
  var isCtrl=e.ctrlKey||e.metaKey;
  if(!isCtrl)return;
  var k=e.key;
  // Ctrl+L → focus address bar
  if(k==='l'||k==='L'){
    e.preventDefault();
    var addr=document.getElementById('br-addr');
    if(addr){addr.focus();addr.select();}
    return;
  }
  // Ctrl+T → new tab; Ctrl+Shift+T → reopen
  if(k==='t'||k==='T'){
    e.preventDefault();
    if(e.shiftKey)TM.reopenLastClosed();
    else newTab('normal');
    return;
  }
  // Ctrl+W → close active tab
  if(k==='w'||k==='W'){
    e.preventDefault();
    closeActiveTab();
    return;
  }
  // Ctrl+Shift+N → new incognito tab
  if((k==='n'||k==='N')&&e.shiftKey){
    e.preventDefault();
    newTab('incognito');
    return;
  }
  // Ctrl+Tab / Ctrl+Shift+Tab → switch tab
  if(k==='Tab'){
    e.preventDefault();
    TM.switchByOffset(e.shiftKey?-1:1);
    return;
  }
  // Ctrl+1..9 → jump to tab
  if(/^[1-9]$/.test(k)){
    e.preventDefault();
    TM.activateByIndex(parseInt(k,10)-1);
    return;
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
  ['proxy','bm','hist','priv'].forEach(function(k){
    var t=document.getElementById('mtab-'+k),s=document.getElementById('msec-'+k);
    if(t)t.className='br-modal-tab'+(k===n?' active':'');
    if(s)s.className='br-modal-sec'+(k===n?' active':'');
  });
  if(n==='hist')_loadServerHistory();
}

// ── Wipe ─────────────────────────────────────────────────────────────────────
function wipeBrowser(){
  if(!confirm('Wipe ALL browser data: every tab session, cookies, history, and bookmarks? This cannot be undone.'))return;
  var res=document.getElementById('wipe-result');
  if(res)res.innerHTML='<div class="br-msg ok" style="margin-top:8px">Wiping...</div>';
  _post('/user/browser/api/wipe',{},function(d){
    if(d&&d.ok){
      if(res)res.innerHTML='<div class="br-msg ok" style="margin-top:8px">✅ All browser data wiped. Reloading…</div>';
      setTimeout(function(){location.reload();},700);
    }else{
      if(res)res.innerHTML='<div class="br-msg err" style="margin-top:8px">❌ '+((d&&d.error)||'Failed')+'</div>';
    }
  });
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
  var t=TM.active();
  // Hard guard FIRST: in Incognito the bookmark button is rendered as a
  // disabled lock; the click handler still fires though, so block it here.
  if(t&&t.mode==='incognito'){
    alert('Bookmarks are disabled in Incognito tabs.');
    return;
  }
  var url=t&&t.url?t.url:document.getElementById('br-addr').value.trim();
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

// ── Init: open first tab on load ─────────────────────────────────────────────
(function(){
  function _init(){if(TM.tabs.length===0)TM.newTab('normal');}
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',_init);
  }else{_init();}
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

        # Tab routing — `t` is the per-tab key, `p=1` marks Incognito.
        # These are server-internal params; they MUST NOT be merged into the
        # outgoing target URL.
        tab_key = (request.args.get("t") or "").strip()[:64]
        if tab_key and not _valid_tab_key(tab_key):
            tab_key = ""  # silently ignore malformed keys
        private = request.args.get("p") == "1"

        # Build target URL from 'url' param; for GET forms, other query params
        # are already merged into the target URL by the injected JS interceptor.
        # For direct navigation, pick up any extra params and forward them.
        raw_url = request.args.get("url", "").strip()
        if not raw_url:
            return _error_page("No URL", "No URL was specified.", status=400)

        # Auto-add scheme
        if "://" not in raw_url and not raw_url.startswith("//"):
            raw_url = "https://" + raw_url

        # If extra query params exist (besides 'url', 't', 'p'), merge them.
        _RESERVED = {"url", "t", "p"}
        extra_params = {k: v for k, v in request.args.items() if k not in _RESERVED}
        if extra_params:
            parsed_target = urlparse(raw_url)
            existing_qs = parse_qs(parsed_target.query, keep_blank_values=True)
            for k, v in extra_params.items():
                existing_qs.setdefault(k, []).append(v)
            merged_qs = urlencode({k: v[0] for k, v in existing_qs.items()}, doseq=False)
            raw_url = urlunparse(parsed_target._replace(query=merged_qs))

        # Strip tracking params for Incognito tabs
        if private:
            raw_url = _strip_tracking_params(raw_url)

        ok, err = _validate_url(raw_url)
        if not ok:
            return _error_page("Invalid URL", err, raw_url, 400)

        # SSRF protection
        ssrf_ok, ssrf_err = _is_ssrf_safe(raw_url)
        if not ssrf_ok:
            return _error_page("Access Denied", ssrf_err, raw_url, 403)

        # Tracker / ad blocklist — return 204 for subresources, friendly page
        # for top-level navigation (so the iframe doesn't get stuck blank).
        try:
            blk_host = urlparse(raw_url).hostname or ""
        except Exception:
            blk_host = ""
        # Tracker blocking is an Incognito-only feature per the task spec —
        # normal tabs keep their existing behaviour (no blocklist enforcement)
        # so users don't see surprising blocks outside Incognito.
        if private and _is_blocked_host(blk_host):
            new_count = 0
            if tab_key:
                _ensure_tab_meta(uid, tab_key, private)
                new_count = _bump_blocked(uid, tab_key)
            sec_dest = (request.headers.get("Sec-Fetch-Dest") or "").lower()
            # "iframe" / "frame" are also top-level navigations from the user's
            # perspective inside our embedded browser; show the friendly page
            # so the frame doesn't get stuck on a blank 204.
            if sec_dest in ("", "document", "iframe", "frame"):
                body = (
                    "<html><body style='background:#0a0515;color:#fff;font-family:sans-serif;"
                    "display:flex;align-items:center;justify-content:center;height:100vh;"
                    "flex-direction:column;text-align:center;padding:20px'>"
                    "<div style='font-size:3.5rem'>🛡</div>"
                    "<h2 style='color:#4ade80;margin:14px 0 6px'>Tracker blocked</h2>"
                    "<p style='color:#bbb;font-size:.9rem;max-width:440px'>"
                    "<code style='color:#ff99cc'>" + _he(blk_host[:120]) + "</code>"
                    " is on the built-in tracker / ad blocklist. The request "
                    "was not sent."
                    "</p>"
                    "<p style='color:#666;font-size:.78rem;margin-top:10px'>"
                    "Open a new tab to navigate elsewhere."
                    "</p></body></html>"
                )
                r = Response(body, status=200, content_type="text/html; charset=utf-8")
            else:
                r = Response("", status=204)
            r.headers["X-Browser-Blocked"] = str(new_count)
            r.headers["X-Browser-Blocked-Host"] = blk_host[:120]
            return r

        # Pick session (per-tab Session for private; primary for normal)
        if tab_key:
            meta = _ensure_tab_meta(uid, tab_key, private)
            http_session = _get_session_for_tab(uid, tab_key, meta)
        else:
            http_session = _get_http_session(uid)

        active_proxy = _get_active_proxy_row(uid)
        proxies_dict = None
        if active_proxy:
            purl = _parse_proxy_url(active_proxy["proxy_url"])
            if purl:
                proxies_dict = {"http": purl, "https": purl}

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

        # Per-request header overrides for Incognito.
        # `Referer: None` causes requests to drop the header entirely.
        per_req_headers = None
        if private:
            per_req_headers = {
                "Referer": None,
                "DNT": "1",
                "Sec-GPC": "1",
            }

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
                if per_req_headers:
                    fetch_kwargs["headers"] = per_req_headers
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
                    # Block redirects to tracker hosts too — Incognito only.
                    try:
                        nh = urlparse(next_url).hostname or ""
                    except Exception:
                        nh = ""
                    if private and _is_blocked_host(nh):
                        if tab_key:
                            _ensure_tab_meta(uid, tab_key, private)
                            _bump_blocked(uid, tab_key)
                        resp.close()
                        r = Response("", status=204)
                        r.headers["X-Browser-Blocked"] = str(
                            _tab_meta.get(uid, {}).get(tab_key, {}).get("blocked", 0)
                        )
                        return r
                    if private:
                        next_url = _strip_tracking_params(next_url)
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

        # Server-side history is *only* recorded for non-private navigations.
        if not private:
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

        def _attach_blocked_header(r: Response) -> Response:
            if tab_key:
                cnt = _tab_meta.get(uid, {}).get(tab_key, {}).get("blocked", 0)
                r.headers["X-Browser-Blocked"] = str(cnt)
            return r

        def _apply_cache_policy(r: Response) -> None:
            """In Incognito, never let upstream cache hints linger anywhere
            in the user's UA — applies to HTML, CSS, AND binary subresources
            so an image/script/font fetched in Incognito isn't cached locally
            and replayed in a non-private session."""
            if private:
                r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                r.headers["Pragma"] = "no-cache"
                r.headers.pop("ETag", None)
                r.headers.pop("Last-Modified", None)
                r.headers.pop("Expires", None)
            else:
                for hdr in ("Cache-Control", "ETag", "Last-Modified"):
                    if hdr in resp.headers:
                        r.headers[hdr] = resp.headers[hdr]

        # Binary / passthrough — stream through unchanged
        if _is_binary(ct) or _is_passthrough(ct):
            content, over = _read_stream(_MAX_RESPONSE_BYTES)
            if over:
                return _error_page("Response Too Large",
                                   "The server response exceeds the 10 MB limit.",
                                   final_url, 413)
            r = Response(content, status=resp.status_code, content_type=ct)
            _apply_cache_policy(r)
            return _attach_blocked_header(r)

        # CSS — rewrite url() references
        if ct.lower().split(";")[0].strip() == "text/css":
            raw_bytes, over = _read_stream(_MAX_RESPONSE_BYTES)
            if over:
                return _error_page("Response Too Large",
                                   "The CSS file exceeds the 10 MB limit.",
                                   final_url, 413)
            encoding = resp.encoding or "utf-8"
            css_text = raw_bytes.decode(encoding, errors="replace")
            rewritten_css = _rewrite_css_text(css_text, final_url, tab_key, private)
            r = Response(rewritten_css, status=resp.status_code,
                         content_type="text/css; charset=utf-8")
            _apply_cache_policy(r)
            return _attach_blocked_header(r)

        # HTML — rewrite links
        raw_bytes, over = _read_stream(_MAX_RESPONSE_BYTES)
        if over:
            return _error_page("Response Too Large",
                               "The page exceeds the 10 MB limit.",
                               final_url, 413)
        encoding = resp.encoding or "utf-8"
        rewritten = _rewrite_html(raw_bytes, final_url, encoding, tab_key, private)
        flask_resp = Response(rewritten, status=resp.status_code,
                              content_type="text/html; charset=utf-8")
        _apply_cache_policy(flask_resp)
        # `Vary` is only relevant for non-private; pass through if not Incognito.
        if not private and "Vary" in resp.headers:
            flask_resp.headers["Vary"] = resp.headers["Vary"]
        # Strip headers that would block embedding the iframe.
        for h in ("X-Frame-Options", "Content-Security-Policy",
                  "X-Content-Type-Options", "Cross-Origin-Opener-Policy",
                  "Cross-Origin-Embedder-Policy"):
            flask_resp.headers.pop(h, None)
        return _attach_blocked_header(flask_resp)

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
        # Incognito navigations MUST NOT be recorded.
        if data.get("private") is True:
            return jsonify({"ok": True, "skipped": "private"})
        url = str(data.get("url", "")).strip()
        if url:
            ok, _ = _validate_url(url)
            if ok:
                _add_history(uid, url)
        return jsonify({"ok": True})

    # ── Tab lifecycle / privacy controls ───────────────────────────────────────
    @app.route("/user/browser/api/tab/close", methods=["POST"])
    @user_required
    def browser_api_tab_close():
        """Evict a closed tab's per-tab Session and metadata.

        POST-only (sendBeacon uses POST). Restricted to POST so an attacker
        can't use a hidden <img> or link with a guessed normal-tab key
        ("n-<id>") to nuke the user's active tab session via CSRF.
        """
        uid = _uid()
        data = request.get_json(silent=True) or {}
        if not data:
            # sendBeacon may use text/plain — try parsing raw body as JSON.
            try:
                data = json.loads(request.data.decode("utf-8")) if request.data else {}
            except Exception:
                data = {}
        tab_key = str(data.get("tab_key", "")).strip()[:64]
        if not _valid_tab_key(tab_key):
            return jsonify({"ok": False, "error": "invalid tab_key"}), 400
        _close_tab(uid, tab_key)
        return jsonify({"ok": True})

    @app.route("/user/browser/api/tab/state", methods=["GET"])
    @user_required
    def browser_api_tab_state():
        """Return the per-tab blocked-tracker count (drives the 🛡 badge)."""
        uid = _uid()
        tab_key = (request.args.get("t") or "").strip()[:64]
        if not _valid_tab_key(tab_key):
            return jsonify({"blocked": 0, "private": False})
        with _tab_lock:
            meta = _tab_meta.get(uid, {}).get(tab_key) or {}
        return jsonify({
            "blocked": meta.get("blocked", 0),
            "private": bool(meta.get("private")),
        })

    @app.route("/user/browser/api/wipe", methods=["POST"])
    @user_required
    def browser_api_wipe():
        """Wipe everything: cookies, history, every tab session."""
        uid = _uid()
        _wipe_user_browser(uid)
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
        # Bookmarks are disabled in Incognito tabs.
        if data.get("private") is True:
            return jsonify({"ok": False, "error": "Bookmarks are disabled in Incognito tabs"})
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
