"""Integration tests for Pro Mode (real headless Chromium tabs) — Task #75.

Exercises the new ``/user/browser/api/pro/*`` REST endpoints AND a real
end-to-end CDP screencast over the ``/user/browser/pro/ws`` WebSocket
against a running bot instance.

Run with::

    BROWSER_TEST_BASE=http://localhost:5000 pytest tests/test_browser_pro.py

The test user ``999900001 / testpass123`` is registered on the fly via
``/user/register`` if it does not already exist. If Pro Mode reports
``available=false`` (Chromium missing or flask-sock missing) the
end-to-end frame test is skipped so CI remains green on environments
without the heavy dependencies.
"""
from __future__ import annotations

import json
import os
import struct
import time
import unittest

import requests

try:
    import websocket  # websocket-client
    HAS_WS = True
except Exception:
    HAS_WS = False

BASE = os.environ.get("BROWSER_TEST_BASE", "http://localhost:5000")
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")
TG_ID = os.environ.get("BROWSER_TEST_USER", "999900001")
PASS = os.environ.get("BROWSER_TEST_PASS", "testpass123")


def _login():
    """Log in (registering on the fly), return a Session or None."""
    s = requests.Session()
    r = s.post(f"{BASE}/user/login",
               data={"user_id": TG_ID, "password": PASS},
               allow_redirects=False, timeout=10)
    if r.status_code in (302, 303):
        return s
    try:
        s.post(f"{BASE}/user/register",
               data={"user_id": TG_ID, "password": PASS,
                     "confirm_password": PASS},
               allow_redirects=False, timeout=10)
        r = s.post(f"{BASE}/user/login",
                   data={"user_id": TG_ID, "password": PASS},
                   allow_redirects=False, timeout=10)
    except Exception:
        return None
    return s if r.status_code in (302, 303) else None


def _server_alive() -> bool:
    try:
        return requests.get(f"{BASE}/healthz", timeout=2).status_code < 500
    except Exception:
        try:
            return requests.get(f"{BASE}/", timeout=2).status_code < 500
        except Exception:
            return False


def tearDownModule():  # noqa: N802 — required name for unittest hooks
    """Scrub the throwaway test user from the tracked credentials file.

    The bot persists registered users to ``data/user_credentials.json``,
    which is git-tracked. Without this hook, every CI run would leave
    a known test login behind and surface in code review as a leak.
    Only the synthetic test ID is removed; real users are untouched.
    """
    try:
        import json as _json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "data" / "user_credentials.json"
        if not p.exists():
            return
        data = _json.loads(p.read_text() or "{}")
        if TG_ID in data:
            data.pop(TG_ID, None)
            p.write_text(_json.dumps(data))
    except Exception:
        pass


class SSRFGateUnitTests(unittest.TestCase):
    """Pure unit tests for the SSRF gate that protects every request the
    headless Chromium makes (top-level nav, redirects, subresources,
    fetch/XHR, websockets). These do not need the bot running."""

    @classmethod
    def setUpClass(cls):
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
            from browser_chrome_pool import _ssrf_block  # type: ignore
            cls._ssrf_block = staticmethod(_ssrf_block)
        except Exception as e:
            raise unittest.SkipTest(f"could not import _ssrf_block: {e}")

    def test_blocks_metadata_ip(self):
        self.assertTrue(self._ssrf_block("http://169.254.169.254/latest"))

    def test_blocks_private_v4_ranges(self):
        for u in (
            "http://10.0.0.1/", "http://10.255.255.1/",
            "http://172.16.0.1/", "http://172.31.255.1/",
            "http://192.168.0.1/", "http://192.168.255.1/",
            "http://100.64.0.1/",
        ):
            self.assertTrue(self._ssrf_block(u), f"should block {u}")

    def test_blocks_loopback_and_link_local(self):
        for u in (
            "http://127.0.0.1/", "http://127.255.255.1/",
            "http://localhost/", "http://169.254.0.1/",
        ):
            self.assertTrue(self._ssrf_block(u), f"should block {u}")

    def test_blocks_disallowed_schemes(self):
        for u in (
            "file:///etc/passwd", "gopher://attacker/",
            "ftp://example.com/", "javascript:alert(1)",
        ):
            # data:, blob:, about:, javascript: are evaluated in the renderer
            # — the gate intentionally only blocks navigation/network ones.
            if u.startswith("javascript:"):
                self.assertFalse(self._ssrf_block(u), u)
            else:
                self.assertTrue(self._ssrf_block(u), f"should block {u}")

    def test_allows_public_host(self):
        # If the test sandbox can't reach DNS at all we skip — the cache
        # would otherwise pin a fail-closed result for example.com.
        try:
            import socket as _s
            _s.getaddrinfo("example.com", None)
        except Exception:
            self.skipTest("no DNS available")
        self.assertFalse(self._ssrf_block("https://example.com/"))


@unittest.skipUnless(_server_alive(), f"bot server not reachable at {BASE}")
class ProModeRestTests(unittest.TestCase):
    """REST surface — runs even when Chromium is unavailable."""

    @classmethod
    def setUpClass(cls):
        cls.s = _login()
        if cls.s is None:
            raise unittest.SkipTest("could not log in test user")

    def test_status_endpoint_shape(self):
        r = self.s.get(f"{BASE}/user/browser/api/pro/status", timeout=10)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("available", d)
        self.assertIsInstance(d["available"], bool)
        if not d["available"]:
            self.assertIn("reason", d)
            self.assertTrue(d["reason"], "unavailable but no reason given")

    def test_state_endpoint_shape_and_isolation(self):
        r = self.s.get(f"{BASE}/user/browser/api/pro/state", timeout=10)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("available", d)
        self.assertIn("users", d)
        # Every user record (if any) must belong to the calling user.
        for u in d.get("users", []):
            self.assertEqual(u.get("user_id"), TG_ID,
                             "pool/state leaked another user's tabs")

    def test_browser_page_contains_pro_toggle(self):
        """The /user/browser shell must expose the Pro toggle markup."""
        r = self.s.get(f"{BASE}/user/browser", timeout=10)
        self.assertEqual(r.status_code, 200)
        html = r.text
        for needle in (
            'id="btn-pro"',
            'id="br-pro-pill"',
            'TM.togglePro()',
            'ProRenderer',
            '/user/browser/pro/ws',
            '_refreshProStatus',
            'br-pro-canvas',
        ):
            self.assertIn(needle, html, f"page missing Pro Mode marker: {needle}")

    def test_unauthenticated_status_redirects(self):
        anon = requests.Session()
        r = anon.get(f"{BASE}/user/browser/api/pro/status",
                     allow_redirects=False, timeout=10)
        # The decorator either bounces to /user/login or returns 401/403;
        # any of those are acceptable proof of auth gating.
        self.assertIn(r.status_code, (302, 303, 401, 403))


@unittest.skipUnless(_server_alive() and HAS_WS,
                     "needs running bot + websocket-client installed")
class ProModeScreencastTests(unittest.TestCase):
    """End-to-end CDP screencast — skipped when Pro Mode is unavailable."""

    @classmethod
    def setUpClass(cls):
        cls.s = _login()
        if cls.s is None:
            raise unittest.SkipTest("could not log in test user")
        d = cls.s.get(f"{BASE}/user/browser/api/pro/status", timeout=10).json()
        if not d.get("available"):
            raise unittest.SkipTest(
                f"Pro Mode unavailable: {d.get('reason') or 'unknown'}")
        cls._tab_keys = []

    @classmethod
    def tearDownClass(cls):
        # Best-effort cleanup so the pool doesn't hold a tab between runs.
        if cls.s is None:
            return
        for tk in getattr(cls, "_tab_keys", []):
            try:
                cls.s.post(f"{BASE}/user/browser/api/tab/close",
                           json={"tab_key": tk}, timeout=10)
            except Exception:
                pass

    def _open_ws(self, tab_key, url, incognito=True):
        cookie = "; ".join(f"{k}={v}" for k, v in self.s.cookies.items())
        ws_url = (f"{WS_BASE}/user/browser/pro/ws?tabKey={tab_key}"
                  f"&incognito={'1' if incognito else '0'}"
                  f"&url={requests.utils.quote(url, safe='')}")
        return websocket.create_connection(
            ws_url, header=[f"Cookie: {cookie}"], timeout=15)

    def _drain(self, ws, *, max_frames=2, timeout=25):
        frames, metas, errors = [], [], []
        ws.settimeout(2.0)
        deadline = time.time() + timeout
        while time.time() < deadline and len(frames) < max_frames:
            try:
                opcode, data = ws.recv_data()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                errors.append(str(e))
                break
            if opcode == 1:
                try:
                    metas.append(json.loads(data.decode("utf-8")))
                except Exception:
                    pass
            elif opcode == 2:
                if len(data) < 8:
                    continue
                w = struct.unpack("<I", data[:4])[0]
                h = struct.unpack("<I", data[4:8])[0]
                magic = data[8:12].hex()
                frames.append((w, h, len(data) - 8, magic))
        return frames, metas, errors

    def test_first_frame_arrives_and_is_jpeg(self):
        tab_key = f"pytest-{int(time.time() * 1000)}"
        self.__class__._tab_keys.append(tab_key)
        ws = self._open_ws(tab_key, "https://example.com/", incognito=True)
        try:
            frames, metas, errors = self._drain(ws, max_frames=1, timeout=25)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        self.assertFalse(errors, f"WS errors: {errors}")
        self.assertTrue(any(m.get("type") == "ready" for m in metas),
                        f"no 'ready' meta: {metas[:3]}")
        self.assertTrue(frames, "no JPEG frame received")
        w, h, sz, magic = frames[0]
        self.assertGreater(w, 0); self.assertGreater(h, 0)
        self.assertGreater(sz, 500, f"degenerate frame size {sz}")
        self.assertTrue(magic.startswith("ffd8"),
                        f"first frame is not a JPEG: {magic}")

    def test_pool_state_reflects_open_tab(self):
        tab_key = f"pytest-state-{int(time.time() * 1000)}"
        self.__class__._tab_keys.append(tab_key)
        ws = self._open_ws(tab_key, "https://example.com/", incognito=True)
        try:
            self._drain(ws, max_frames=1, timeout=20)
            d = self.s.get(f"{BASE}/user/browser/api/pro/state", timeout=10).json()
            tabs = []
            for u in d.get("users", []):
                tabs.extend(u.get("tabs", []))
            self.assertTrue(any(t.get("tab_key") == tab_key for t in tabs),
                            f"open Pro tab missing from pool/state: {tabs}")
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def test_initial_url_ssrf_rejected(self):
        """A bad scheme on the initial URL must surface a JSON error
        envelope and must NOT trigger a navigation. The WS still opens
        (so the client can recover) and a 'ready' meta is still sent."""
        tab_key = f"pytest-bad-{int(time.time() * 1000)}"
        self.__class__._tab_keys.append(tab_key)
        # file:// scheme is rejected by _validate_url; if the gate is
        # bypassed Chromium would happily try to open it.
        ws = self._open_ws(tab_key, "file:///etc/passwd", incognito=True)
        try:
            _frames, metas, _errors = self._drain(ws, max_frames=1, timeout=10)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        errs = [m for m in metas if m.get("type") == "error"]
        self.assertTrue(errs, f"expected an error meta, got: {metas[:5]}")
        readies = [m for m in metas if m.get("type") == "ready"]
        self.assertTrue(readies, "ready meta should still be sent")

    def test_close_endpoint_releases_pool_slot(self):
        tab_key = f"pytest-close-{int(time.time() * 1000)}"
        ws = self._open_ws(tab_key, "https://example.com/", incognito=True)
        try:
            self._drain(ws, max_frames=1, timeout=20)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        # Explicit release through the existing tab/close endpoint.
        t0 = time.time()
        r = self.s.post(f"{BASE}/user/browser/api/tab/close",
                        json={"tab_key": tab_key}, timeout=10)
        self.assertEqual(r.status_code, 200)
        # Spec: upstream Chromium page must be torn down within ~2s of
        # the close beacon. Poll pool/state and assert the tab is gone.
        deadline = t0 + 2.0
        gone = False
        while time.time() < deadline:
            d = self.s.get(f"{BASE}/user/browser/api/pro/state", timeout=5).json()
            still_there = any(
                t.get("tab_key") == tab_key
                for u in d.get("users", [])
                for t in u.get("tabs", [])
            )
            if not still_there:
                gone = True
                break
            time.sleep(0.1)
        self.assertTrue(gone, "pool still tracks closed tab after 2s")

    def test_interaction_keeps_frames_flowing(self):
        """Sending an input event must (a) not break the WS and (b) keep
        frames coming. This is the closest deterministic assertion we can
        make for ‘canvas focus → keystroke → rendered frame update’ —
        comparing JPEG bytes for visual change is non-deterministic.
        """
        tab_key = f"pytest-input-{int(time.time() * 1000)}"
        self.__class__._tab_keys.append(tab_key)
        ws = self._open_ws(tab_key, "https://example.com/", incognito=True)
        try:
            first, _metas, errs = self._drain(ws, max_frames=1, timeout=25)
            self.assertFalse(errs, f"ws errors before input: {errs}")
            self.assertTrue(first, "no first frame before input")
            # Synthetic keystroke + click — the server forwards them to
            # CDP via dispatch_input, which also bumps last_input_at.
            ws.send(json.dumps({"type": "key",
                                "action": "down", "code": "KeyA"}))
            ws.send(json.dumps({"type": "key",
                                "action": "up", "code": "KeyA"}))
            ws.send(json.dumps({"type": "mouse",
                                "action": "down", "x": 50, "y": 50,
                                "button": "left"}))
            ws.send(json.dumps({"type": "mouse",
                                "action": "up", "x": 50, "y": 50,
                                "button": "left"}))
            after, _m2, errs2 = self._drain(ws, max_frames=2, timeout=10)
            self.assertFalse(errs2, f"ws errors after input: {errs2}")
            self.assertTrue(after, "no frames received after input")
        finally:
            try:
                ws.close()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
