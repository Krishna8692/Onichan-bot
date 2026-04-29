"""
Chrome Pool — manages headless Chromium instances for "Pro Mode" tabs.

Architecture
------------
- One singleton background thread runs an asyncio event loop that owns the
  Playwright connection and one shared `Browser`.
- Each tab is a `Page` inside a `BrowserContext`. Normal Pro tabs share a
  single per-user persistent context (cookies survive across tabs). Incognito
  Pro tabs each get a fresh ephemeral context that is destroyed on close.
- Per-user concurrency cap: at most ``MAX_PRO_TABS_PER_USER`` simultaneous Pro
  tabs. Tabs hidden for more than ``IDLE_SUSPEND_SECONDS`` are suspended (page
  closed, last URL cached, recreated lazily on next focus).
- The active proxy from the existing browser_proxies table is honoured; the
  caller passes a ``proxy_url`` string when acquiring a tab.

If Chromium cannot be launched (binary missing or system libs missing),
``PRO_AVAILABLE`` becomes ``False`` and ``UNAVAILABLE_REASON`` is populated;
all public ``acquire`` calls raise :class:`ProUnavailable`.

This module is intentionally self-contained — no Flask imports — so it can be
unit-tested or invoked from any context.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

MAX_PRO_TABS_PER_USER = 2
IDLE_SUSPEND_SECONDS = 5 * 60  # 5 minutes — applied to *hidden* tabs only
# After this many seconds with no user input we drop the active-tab frame
# rate from ~25fps to ~1fps to keep bandwidth bounded per the task spec.
IDLE_FPS_AFTER_SECONDS = 10
IDLE_FPS_MIN_INTERVAL = 1.0  # seconds between frames in idle-fps mode
DEFAULT_VIEWPORT = (1280, 800)
SCREENCAST_QUALITY = 60
SCREENCAST_MAX_WIDTH = 1280
SCREENCAST_MAX_HEIGHT = 800
SCREENCAST_EVERY_NTH_FRAME = 1  # Active tab → ~all frames

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class ProUnavailable(RuntimeError):
    """Pro Mode cannot be served (Chromium missing, pool exhausted, etc.)."""


# ── Module-load capability check ──────────────────────────────────────────────
PRO_AVAILABLE: bool = False
UNAVAILABLE_REASON: str = ""

try:
    from playwright.async_api import async_playwright  # noqa: F401
    PRO_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    UNAVAILABLE_REASON = f"playwright import failed: {_e}"
    _log.warning("[ChromePool] %s", UNAVAILABLE_REASON)


def _proxy_to_playwright(proxy_url: str | None) -> dict | None:
    """Convert a proxy URL into Playwright's ``proxy`` launch option."""
    if not proxy_url:
        return None
    try:
        u = urlparse(proxy_url if "://" in proxy_url else f"http://{proxy_url}")
        if not u.hostname or not u.port:
            return None
        scheme = u.scheme.lower() or "http"
        # Playwright accepts "http://h:p", "https://h:p", "socks5://h:p"
        server = f"{scheme}://{u.hostname}:{u.port}"
        out: dict = {"server": server}
        if u.username:
            out["username"] = u.username
        if u.password:
            out["password"] = u.password
        return out
    except Exception:  # pragma: no cover
        return None


# ── Per-tab state ─────────────────────────────────────────────────────────────
@dataclass
class _TabRecord:
    uid: str
    tab_key: str
    incognito: bool
    proxy_url: str | None
    last_url: str = "about:blank"
    last_title: str = ""
    last_active: float = field(default_factory=time.time)
    # Last time the user actually sent input. Drives the active/idle frame
    # rate switch in the WS handler.
    last_input_at: float = field(default_factory=time.time)
    # Wall-clock time the client last reported the tab as hidden. ``None``
    # when the tab is visible. The idle reaper suspends tabs that have
    # been hidden longer than IDLE_SUSPEND_SECONDS.
    hidden_since: float | None = None
    viewport_w: int = DEFAULT_VIEWPORT[0]
    viewport_h: int = DEFAULT_VIEWPORT[1]
    # Runtime objects, populated when the tab is "live"
    context: Any | None = None
    page: Any | None = None
    cdp: Any | None = None
    screencasting: bool = False
    frame_cb: Optional[Callable[[bytes, dict], None]] = None
    meta_cb: Optional[Callable[[str, Any], None]] = None
    # Holds the Page.screencastFrame listener so stop_screencast can
    # detach it cleanly — otherwise reconnects accumulate handlers.
    frame_listener: Any | None = None
    navigated: bool = False  # has the page been navigated at least once
    # Suspended state — when True, ``page`` is None and ``last_url`` holds the
    # cached destination for re-creation on next focus.
    suspended: bool = False


class _ChromePool:
    """Singleton Chrome pool. Use :func:`get_pool` to access."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pw = None
        self._browser = None
        self._lock = threading.Lock()
        # uid -> {tab_key -> _TabRecord}
        self._tabs: dict[str, dict[str, _TabRecord]] = {}
        # uid -> persistent context (shared by all *normal* Pro tabs of that user)
        self._user_contexts: dict[str, Any] = {}
        # uid -> proxy_url currently bound to the user's persistent context.
        # If this changes, we recreate the context.
        self._user_context_proxy: dict[str, str | None] = {}
        self._started = False
        self._start_failure: str | None = None
        self._idle_task_started = False

    # ── Bootstrapping ────────────────────────────────────────────────────────
    def _ensure_started(self) -> None:
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            if not PRO_AVAILABLE:
                raise ProUnavailable(UNAVAILABLE_REASON or "playwright not installed")
            if self._start_failure:
                raise ProUnavailable(self._start_failure)
            try:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop_runner, name="chrome-pool-loop", daemon=True
                )
                self._thread.start()
                fut = asyncio.run_coroutine_threadsafe(self._async_startup(), self._loop)
                fut.result(timeout=30)
                self._started = True
                _log.info("[ChromePool] started")
            except Exception as e:
                self._start_failure = str(e)[:200]
                _log.warning("[ChromePool] startup failed: %s", e)
                raise ProUnavailable(self._start_failure) from e

    def _loop_runner(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:  # pragma: no cover
            try:
                self._loop.close()
            except Exception:
                pass

    async def _async_startup(self) -> None:
        from playwright.async_api import async_playwright as _ap
        self._pw = await _ap().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--mute-audio",
            ],
        )
        # Fire-and-forget idle reaper
        if not self._idle_task_started:
            self._idle_task_started = True
            asyncio.ensure_future(self._idle_reaper())

    def _run_async(self, coro):
        """Schedule ``coro`` on the pool loop and block for the result."""
        assert self._loop is not None
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=30)

    # ── Capability ───────────────────────────────────────────────────────────
    def status(self) -> dict:
        """Return a JSON-friendly status object suitable for /api/pro/status."""
        if not PRO_AVAILABLE:
            return {"available": False, "reason": UNAVAILABLE_REASON or "missing"}
        if self._start_failure:
            return {"available": False, "reason": self._start_failure}
        # Try a lazy bring-up just to surface launch errors early. If that
        # fails, ``_ensure_started`` will set ``_start_failure`` for us.
        try:
            self._ensure_started()
        except ProUnavailable as e:
            return {"available": False, "reason": str(e)}
        return {"available": True, "reason": ""}

    def pool_state(self) -> dict:
        """Debug snapshot of the pool — used by /api/pro/state."""
        out_users: list[dict] = []
        with self._lock:
            for uid, tabs in self._tabs.items():
                out_users.append({
                    "user_id": uid,
                    "has_persistent_ctx": uid in self._user_contexts,
                    "tabs": [
                        {
                            "tab_key": t.tab_key,
                            "incognito": t.incognito,
                            "url": t.last_url,
                            "title": t.last_title,
                            "suspended": t.suspended,
                            "screencasting": t.screencasting,
                            "viewport": [t.viewport_w, t.viewport_h],
                            "idle_secs": int(time.time() - t.last_active),
                        }
                        for t in tabs.values()
                    ],
                })
        return {
            "available": PRO_AVAILABLE and not self._start_failure,
            "max_per_user": MAX_PRO_TABS_PER_USER,
            "idle_suspend_secs": IDLE_SUSPEND_SECONDS,
            "users": out_users,
        }

    # ── Public API: tab acquisition ──────────────────────────────────────────
    def acquire(
        self,
        uid: str,
        tab_key: str,
        *,
        incognito: bool = False,
        url: str = "about:blank",
        proxy_url: str | None = None,
        viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    ) -> _TabRecord:
        """Idempotently create or return the per-tab record. Does not navigate."""
        self._ensure_started()
        with self._lock:
            user_tabs = self._tabs.setdefault(uid, {})
            if tab_key in user_tabs:
                rec = user_tabs[tab_key]
                rec.last_active = time.time()
                return rec
            # Enforce per-user cap. Evict the oldest *suspended* tab first.
            if len(user_tabs) >= MAX_PRO_TABS_PER_USER:
                victim = self._pick_eviction_victim(user_tabs)
                if victim is None:
                    raise ProUnavailable(
                        f"Pro tab limit reached ({MAX_PRO_TABS_PER_USER})."
                    )
                self._teardown_tab_locked(uid, victim.tab_key)
            rec = _TabRecord(
                uid=uid,
                tab_key=tab_key,
                incognito=bool(incognito),
                proxy_url=proxy_url,
                last_url=url or "about:blank",
                viewport_w=viewport[0],
                viewport_h=viewport[1],
            )
            user_tabs[tab_key] = rec
        return rec

    def _pick_eviction_victim(self, user_tabs: dict[str, _TabRecord]) -> _TabRecord | None:
        # Prefer suspended → otherwise least-recently-active not currently streaming
        suspended = [t for t in user_tabs.values() if t.suspended]
        if suspended:
            return min(suspended, key=lambda t: t.last_active)
        idle = [t for t in user_tabs.values() if not t.screencasting]
        if idle:
            return min(idle, key=lambda t: t.last_active)
        return None

    # ── Page bring-up / suspend ──────────────────────────────────────────────
    async def _ensure_page(self, rec: _TabRecord) -> None:
        if rec.page is not None:
            return
        # Build/reuse the right context.
        if rec.incognito:
            ctx = await self._new_incognito_context(rec)
        else:
            ctx = await self._get_persistent_context(rec.uid, rec.proxy_url)
        rec.context = ctx
        rec.page = await ctx.new_page()
        await rec.page.set_viewport_size(
            {"width": rec.viewport_w, "height": rec.viewport_h}
        )
        rec.cdp = await ctx.new_cdp_session(rec.page)
        rec.suspended = False
        rec.last_active = time.time()

        # Wire up Page → meta callbacks
        def _on_framenav(frame):
            try:
                if frame == rec.page.main_frame:  # type: ignore[union-attr]
                    rec.last_url = frame.url
                    self._emit_meta(rec, "url", frame.url)
            except Exception:
                pass
        rec.page.on("framenavigated", _on_framenav)
        rec.page.on("load", lambda *_: self._emit_meta(rec, "loading", False))
        rec.page.on("close", lambda *_: self._emit_meta(rec, "closed", True))

        async def _on_title():
            try:
                t = await rec.page.title()  # type: ignore[union-attr]
                rec.last_title = t or ""
                self._emit_meta(rec, "title", rec.last_title)
            except Exception:
                pass
        rec.page.on("domcontentloaded", lambda *_: asyncio.ensure_future(_on_title()))

    async def _get_persistent_context(self, uid: str, proxy_url: str | None):
        # If user already has a persistent context but the proxy has changed,
        # tear it down and recreate. Cookies are intentionally discarded —
        # a different proxy means a different egress IP, so the previous
        # session is no longer trustworthy.
        existing = self._user_contexts.get(uid)
        if existing is not None:
            if self._user_context_proxy.get(uid) != proxy_url:
                try:
                    await existing.close()
                except Exception:
                    pass
                self._user_contexts.pop(uid, None)
                self._user_context_proxy.pop(uid, None)
                # Invalidate every non-incognito tab record that pointed at
                # the now-closed context — otherwise _ensure_page() would
                # see ``rec.page is not None`` and skip recreation, leaving
                # the tab pointing at a dead Page.
                for r in list(self._tabs.get(uid, {}).values()):
                    if r.incognito:
                        continue
                    r.page = None
                    r.context = None
                    r.cdp = None
                    r.screencasting = False
                    r.frame_listener = None
            else:
                return existing
        opts: dict = {
            "viewport": {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            "user_agent": USER_AGENT,
        }
        proxy = _proxy_to_playwright(proxy_url)
        if proxy:
            opts["proxy"] = proxy
        ctx = await self._browser.new_context(**opts)  # type: ignore[union-attr]
        self._user_contexts[uid] = ctx
        self._user_context_proxy[uid] = proxy_url
        return ctx

    async def _new_incognito_context(self, rec: _TabRecord):
        opts: dict = {
            "viewport": {"width": rec.viewport_w, "height": rec.viewport_h},
            "user_agent": USER_AGENT,
        }
        proxy = _proxy_to_playwright(rec.proxy_url)
        if proxy:
            opts["proxy"] = proxy
        return await self._browser.new_context(**opts)  # type: ignore[union-attr]

    # ── Public API: navigation ───────────────────────────────────────────────
    def navigate(self, uid: str, tab_key: str, url: str) -> None:
        rec = self._require_rec(uid, tab_key)

        async def _do():
            await self._ensure_page(rec)
            rec.last_url = url
            rec.navigated = True
            self._emit_meta(rec, "loading", True)
            try:
                await rec.page.goto(url, timeout=20000, wait_until="domcontentloaded")  # type: ignore[union-attr]
            except Exception as e:
                self._emit_meta(rec, "error", str(e)[:200])
        self._run_async(_do())

    def go_back(self, uid: str, tab_key: str) -> None:
        rec = self._require_rec(uid, tab_key)

        async def _do():
            await self._ensure_page(rec)
            try:
                await rec.page.go_back(timeout=10000)  # type: ignore[union-attr]
            except Exception as e:
                self._emit_meta(rec, "error", str(e)[:200])
        self._run_async(_do())

    def go_forward(self, uid: str, tab_key: str) -> None:
        rec = self._require_rec(uid, tab_key)

        async def _do():
            await self._ensure_page(rec)
            try:
                await rec.page.go_forward(timeout=10000)  # type: ignore[union-attr]
            except Exception as e:
                self._emit_meta(rec, "error", str(e)[:200])
        self._run_async(_do())

    def reload(self, uid: str, tab_key: str) -> None:
        rec = self._require_rec(uid, tab_key)

        async def _do():
            await self._ensure_page(rec)
            try:
                await rec.page.reload(timeout=15000)  # type: ignore[union-attr]
            except Exception as e:
                self._emit_meta(rec, "error", str(e)[:200])
        self._run_async(_do())

    def stop(self, uid: str, tab_key: str) -> None:
        rec = self._require_rec(uid, tab_key)

        async def _do():
            await self._ensure_page(rec)
            try:
                # Playwright doesn't expose Page.stopLoading, but CDP does.
                await rec.cdp.send("Page.stopLoading")  # type: ignore[union-attr]
            except Exception:
                pass
        self._run_async(_do())

    def mark_visibility(self, uid: str, tab_key: str, hidden: bool) -> None:
        """Record whether the client currently has the tab hidden.

        Called by the WS handler on inbound ``pause``/``resume`` messages
        and once on disconnect (treated as "hidden") so the idle reaper
        can suspend tabs whose owner has gone away without a tab-close.
        """
        rec = self._tabs.get(uid, {}).get(tab_key)
        if rec is None:
            return
        rec.hidden_since = time.time() if hidden else None

    def set_viewport(self, uid: str, tab_key: str, w: int, h: int) -> None:
        w = max(320, min(2400, int(w)))
        h = max(240, min(1800, int(h)))
        rec = self._require_rec(uid, tab_key)
        rec.viewport_w = w
        rec.viewport_h = h

        async def _do():
            await self._ensure_page(rec)
            try:
                await rec.page.set_viewport_size({"width": w, "height": h})  # type: ignore[union-attr]
            except Exception:
                pass
        self._run_async(_do())

    # ── Input forwarding ─────────────────────────────────────────────────────
    def dispatch_input(self, uid: str, tab_key: str, evt: dict) -> None:
        """Forward a single input event from the client.

        Supported types: ``mouse`` (with ``action`` move|down|up), ``wheel``,
        ``key`` (with ``action`` down|up|press, ``key`` and optional ``text``).
        """
        rec = self._require_rec(uid, tab_key)
        now = time.time()
        rec.last_active = now
        rec.last_input_at = now
        t = evt.get("type")

        async def _do():
            await self._ensure_page(rec)
            try:
                if t == "mouse":
                    await self._mouse(rec, evt)
                elif t == "wheel":
                    dx = float(evt.get("dx") or 0)
                    dy = float(evt.get("dy") or 0)
                    x, y = self._scale_xy(rec, evt.get("x"), evt.get("y"))
                    await rec.page.mouse.move(x, y)  # type: ignore[union-attr]
                    await rec.page.mouse.wheel(dx, dy)  # type: ignore[union-attr]
                elif t == "key":
                    await self._key(rec, evt)
            except Exception as e:  # pragma: no cover
                _log.debug("dispatch_input %s failed: %s", t, e)
        self._run_async(_do())

    def _scale_xy(self, rec: _TabRecord, x: Any, y: Any) -> tuple[float, float]:
        """Translate canvas-space coords into upstream viewport coords.

        The client sends ``x`` / ``y`` already as fractions in 0..1 of the
        canvas size, so we just multiply by the upstream viewport.
        """
        try:
            fx = float(x) if x is not None else 0.0
            fy = float(y) if y is not None else 0.0
        except Exception:
            fx = fy = 0.0
        fx = max(0.0, min(1.0, fx))
        fy = max(0.0, min(1.0, fy))
        return fx * rec.viewport_w, fy * rec.viewport_h

    async def _mouse(self, rec: _TabRecord, evt: dict) -> None:
        action = evt.get("action") or "move"
        button = evt.get("button") or "left"
        click_count = int(evt.get("clickCount") or 1)
        x, y = self._scale_xy(rec, evt.get("x"), evt.get("y"))
        m = rec.page.mouse  # type: ignore[union-attr]
        if action == "move":
            await m.move(x, y)
        elif action == "down":
            await m.move(x, y)
            await m.down(button=button, click_count=click_count)
        elif action == "up":
            await m.move(x, y)
            await m.up(button=button, click_count=click_count)
        elif action == "click":
            await m.click(x, y, button=button, click_count=click_count)

    async def _key(self, rec: _TabRecord, evt: dict) -> None:
        action = evt.get("action") or "press"
        key = evt.get("key") or ""
        text = evt.get("text")
        kb = rec.page.keyboard  # type: ignore[union-attr]
        if not key and text:
            await kb.insert_text(text)
            return
        if action == "down":
            await kb.down(key)
        elif action == "up":
            await kb.up(key)
        else:
            await kb.press(key)

    # ── Screencast plumbing ──────────────────────────────────────────────────
    def start_screencast(
        self,
        uid: str,
        tab_key: str,
        *,
        on_frame: Callable[[bytes, dict], None],
        on_meta: Callable[[str, Any], None] | None = None,
    ) -> None:
        rec = self._require_rec(uid, tab_key)
        rec.frame_cb = on_frame
        rec.meta_cb = on_meta

        async def _do():
            await self._ensure_page(rec)
            if rec.screencasting:
                return
            cdp = rec.cdp
            assert cdp is not None

            def _on_frame(payload):
                try:
                    data = base64.b64decode(payload["data"])
                    md = payload.get("metadata") or {}
                    if rec.frame_cb is not None:
                        rec.frame_cb(data, md)
                    sess = payload.get("sessionId")
                    if sess is not None:
                        asyncio.ensure_future(
                            cdp.send("Page.screencastFrameAck", {"sessionId": sess})
                        )
                except Exception as e:  # pragma: no cover
                    _log.debug("screencast frame error: %s", e)

            cdp.on("Page.screencastFrame", _on_frame)
            rec.frame_listener = _on_frame
            await cdp.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": SCREENCAST_QUALITY,
                "maxWidth": SCREENCAST_MAX_WIDTH,
                "maxHeight": SCREENCAST_MAX_HEIGHT,
                "everyNthFrame": SCREENCAST_EVERY_NTH_FRAME,
            })
            rec.screencasting = True
        self._run_async(_do())

    def stop_screencast(self, uid: str, tab_key: str) -> None:
        rec = self._tabs.get(uid, {}).get(tab_key)
        if rec is None or not rec.screencasting:
            return

        async def _do():
            try:
                if rec.cdp is not None:
                    await rec.cdp.send("Page.stopScreencast")
            except Exception:
                pass
            # Detach the screencastFrame listener so a subsequent
            # start_screencast does not stack multiple callbacks.
            try:
                if rec.cdp is not None and rec.frame_listener is not None:
                    rec.cdp.remove_listener(
                        "Page.screencastFrame", rec.frame_listener
                    )
            except Exception:
                pass
            rec.frame_listener = None
            rec.screencasting = False
            rec.frame_cb = None
            rec.meta_cb = None
        try:
            self._run_async(_do())
        except Exception:
            pass

    def _emit_meta(self, rec: _TabRecord, kind: str, value: Any) -> None:
        cb = rec.meta_cb
        if cb is None:
            return
        try:
            cb(kind, value)
        except Exception:
            pass

    # ── Teardown ─────────────────────────────────────────────────────────────
    def release(self, uid: str, tab_key: str) -> None:
        with self._lock:
            self._teardown_tab_locked(uid, tab_key)

    def _teardown_tab_locked(self, uid: str, tab_key: str) -> None:
        user_tabs = self._tabs.get(uid)
        if not user_tabs or tab_key not in user_tabs:
            return
        rec = user_tabs.pop(tab_key)
        if not user_tabs:
            self._tabs.pop(uid, None)

        async def _do():
            try:
                if rec.screencasting and rec.cdp is not None:
                    try:
                        await rec.cdp.send("Page.stopScreencast")
                    except Exception:
                        pass
                if rec.page is not None:
                    try:
                        await rec.page.close()
                    except Exception:
                        pass
                # Incognito context is per-tab → close it too.
                if rec.incognito and rec.context is not None:
                    try:
                        await rec.context.close()
                    except Exception:
                        pass
            finally:
                rec.page = None
                rec.cdp = None
                rec.context = None
                rec.screencasting = False
        try:
            if self._loop is not None:
                self._run_async(_do())
        except Exception:
            pass

    def release_user(self, uid: str) -> None:
        """Tear down everything owned by ``uid`` (used on logout / wipe)."""
        with self._lock:
            keys = list(self._tabs.get(uid, {}).keys())
        for k in keys:
            self.release(uid, k)
        ctx = self._user_contexts.pop(uid, None)
        self._user_context_proxy.pop(uid, None)
        if ctx is not None and self._loop is not None:
            async def _do():
                try:
                    await ctx.close()
                except Exception:
                    pass
            try:
                self._run_async(_do())
            except Exception:
                pass

    # ── Idle reaper ──────────────────────────────────────────────────────────
    async def _idle_reaper(self) -> None:
        while True:
            try:
                await asyncio.sleep(30)
                now = time.time()
                victims: list[tuple[str, str]] = []
                with self._lock:
                    for uid, tabs in self._tabs.items():
                        for k, rec in tabs.items():
                            if rec.suspended:
                                continue
                            if rec.page is None:
                                continue
                            # Per spec: only *hidden* tabs that have been
                            # hidden for longer than IDLE_SUSPEND_SECONDS
                            # are suspended. A visible tab is never
                            # suspended regardless of input idleness.
                            if rec.hidden_since is None:
                                continue
                            if (now - rec.hidden_since) > IDLE_SUSPEND_SECONDS:
                                victims.append((uid, k))
                for uid, k in victims:
                    await self._suspend(uid, k)
            except Exception as e:  # pragma: no cover
                _log.debug("idle reaper: %s", e)

    async def _suspend(self, uid: str, tab_key: str) -> None:
        rec = self._tabs.get(uid, {}).get(tab_key)
        if rec is None or rec.page is None:
            return
        try:
            if rec.cdp is not None and rec.screencasting:
                try:
                    await rec.cdp.send("Page.stopScreencast")
                except Exception:
                    pass
                try:
                    if rec.frame_listener is not None:
                        rec.cdp.remove_listener(
                            "Page.screencastFrame", rec.frame_listener
                        )
                except Exception:
                    pass
            try:
                await rec.page.close()
            except Exception:
                pass
            if rec.incognito and rec.context is not None:
                try:
                    await rec.context.close()
                except Exception:
                    pass
        finally:
            rec.page = None
            rec.cdp = None
            rec.context = None
            rec.frame_listener = None
            rec.screencasting = False
            rec.suspended = True
            # Notify the WS layer so the client can choose to reconnect.
            try:
                self._emit_meta(rec, "suspended", True)
            except Exception:
                pass
            _log.info("[ChromePool] suspended idle tab uid=%s key=%s", uid, tab_key)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _require_rec(self, uid: str, tab_key: str) -> _TabRecord:
        rec = self._tabs.get(uid, {}).get(tab_key)
        if rec is None:
            raise ProUnavailable(f"unknown pro tab '{tab_key}'")
        return rec


_pool_singleton: _ChromePool | None = None
_pool_lock = threading.Lock()


def get_pool() -> _ChromePool:
    global _pool_singleton
    if _pool_singleton is None:
        with _pool_lock:
            if _pool_singleton is None:
                _pool_singleton = _ChromePool()
    return _pool_singleton


def is_user_data_dir_empty(path: str) -> bool:
    """Helper for incognito verification — true if ``path`` doesn't exist or is empty."""
    if not os.path.isdir(path):
        return True
    try:
        return not any(os.scandir(path))
    except Exception:
        return True


__all__ = [
    "PRO_AVAILABLE",
    "UNAVAILABLE_REASON",
    "MAX_PRO_TABS_PER_USER",
    "IDLE_SUSPEND_SECONDS",
    "ProUnavailable",
    "get_pool",
    "is_user_data_dir_empty",
]
