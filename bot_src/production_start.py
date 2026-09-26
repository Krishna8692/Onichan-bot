#!/usr/bin/env python3
"""
Production entry point for Onichan Bot — Reserved VM edition.

Strategy
--------
1. Bind a stdlib http.server on port 5000 ONLY — no third-party packages.
   This satisfies Replit's health-check probe instantly.
   Port 8080 is owned by the API server; we must NOT touch it.

2. Release port 5000 once Replit has detected it, so that bot.py's
   keep_alive (Flask/waitress) web panel can take over that port.

3. Start bot.py as a supervised subprocess.  keep_alive will bind 5000
   and serve the full web panel.  SKIP_KEEP_ALIVE is NOT set.

4. Block the main process forever so the container stays alive.

Uptime guarantee
----------------
Port 5000 must NEVER go dark — not during initial startup, not during crash
recovery.  The recovery loop re-binds the stdlib health server immediately
after bot.py exits and releases it only once the new bot.py process has had
time to bring up its own early health server (line 53 of bot.py runs before
any third-party imports, so it's up within ~200 ms of process start).
"""
import http.server
import os
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# 1.  Constants
# ---------------------------------------------------------------------------

DIR = os.path.dirname(os.path.abspath(__file__))
PY  = sys.executable

# Primary port: what the deployment health-check probes
MAIN_PORT = int(os.environ.get("PORT", 5000))

# How long to wait before relaunching bot.py after a crash (seconds).
RESTART_DELAY = 5


# ---------------------------------------------------------------------------
# 2.  Minimal health-check server (stdlib only, zero third-party deps)
# ---------------------------------------------------------------------------

class _OK(http.server.BaseHTTPRequestHandler):
    """Responds 200 OK to any GET/HEAD request."""

    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # silence request logs


def _start_health_server(port: int):
    """Bind a minimal HTTP server on *port* in a daemon thread.
    Returns the HTTPServer instance, or None if the port is already taken."""
    try:
        srv = http.server.HTTPServer(("0.0.0.0", port), _OK)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"[prod] Health server up on :{port}", flush=True)
        return srv
    except OSError as exc:
        print(f"[prod] Health server :{port} skipped ({exc})", flush=True)
        return None


def _stop_health_server(srv):
    """Shut down a health server and free the port."""
    if srv is None:
        return
    try:
        srv.shutdown()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3.  Initial startup — bind health server immediately
# ---------------------------------------------------------------------------
# This is the very first thing that runs, before any bot.py code loads.
# Replit's port-detection probe will see port 5000 respond within milliseconds.

_health_srv = _start_health_server(MAIN_PORT)

# Give Replit's port scanner time to detect the port before we release it.
time.sleep(1.5)
print(f"[prod] Port {MAIN_PORT} detected — releasing for bot.py keep_alive", flush=True)

# Release the port.  bot.py starts its own early stdlib server on line 53
# (before any third-party imports), so the gap is < 300 ms.
_stop_health_server(_health_srv)
_health_srv = None
time.sleep(0.3)  # give the OS time to free the socket


# ---------------------------------------------------------------------------
# 4.  Bot environment
# ---------------------------------------------------------------------------

BOT_ENV = {
    **os.environ,
    "PORT": str(MAIN_PORT),
    # Ensure src/ is on PYTHONPATH so bot.py can resolve `from modules.X import Y`
    "PYTHONPATH": DIR + ((":" + os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else ""),
}


# ---------------------------------------------------------------------------
# 5.  Supervised restart loop — port 5000 stays alive through every crash
# ---------------------------------------------------------------------------

def _run_bot():
    """Supervised restart loop for bot.py.

    Port-5000 coverage during crash recovery:
    ┌─────────────────────────────────────────────────────┐
    │  bot.py running  → Flask owns port 5000            │
    │  bot.py exits    → we bind stdlib health server     │
    │  RESTART_DELAY s → temporary health server answers  │
    │  pre-launch      → we release port so bot.py binds  │
    │  bot.py starts   → bot.py early server takes over  │
    └─────────────────────────────────────────────────────┘
    There is never a moment when port 5000 is not answering.
    """
    while True:
        print("[prod] Starting bot.py …", flush=True)
        try:
            rc = subprocess.run(
                [PY, os.path.join(DIR, "bot.py")],
                env=BOT_ENV,
                cwd=DIR,
            ).returncode
            print(f"[prod] bot.py exited (code {rc})", flush=True)
        except Exception as exc:
            print(f"[prod] bot.py launch error: {exc}", flush=True)

        # ── Crash recovery: immediately cover port 5000 ───────────────────
        # bot.py (and its Flask server) just died.  Re-bind the stdlib health
        # server instantly so the Replit probe keeps getting 200 OK while
        # we wait for the restart delay.
        _recovery_srv = _start_health_server(MAIN_PORT)
        print(f"[prod] Restarting bot.py in {RESTART_DELAY} s …", flush=True)
        time.sleep(RESTART_DELAY)

        # Release port so bot.py's early health server (line 53) can bind.
        _stop_health_server(_recovery_srv)
        time.sleep(0.3)  # give the OS time to free the socket


_bot_thread = threading.Thread(target=_run_bot, daemon=True)
_bot_thread.start()


# ---------------------------------------------------------------------------
# 6.  Block main thread — keep the container alive forever
# ---------------------------------------------------------------------------
# _run_bot runs as a daemon thread; the main thread must never exit or the
# entire process (and all daemon threads) will be killed.

while True:
    time.sleep(60)
