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
        r = self.s.post(f"{BASE}/user/browser/api/tab/close",
                        json={"tab_key": tab_key}, timeout=10)
        self.assertEqual(r.status_code, 200)
        # Allow the pool's release path to settle, then verify the tab is gone.
        time.sleep(0.5)
        d = self.s.get(f"{BASE}/user/browser/api/pro/state", timeout=10).json()
        for u in d.get("users", []):
            for t in u.get("tabs", []):
                self.assertNotEqual(t.get("tab_key"), tab_key,
                                    "pool still tracks closed tab")


if __name__ == "__main__":
    unittest.main(verbosity=2)
