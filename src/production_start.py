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


# ---------------------------------------------------------------------------
# 2.  Instant health-check server (stdlib only, no Flask needed)
# ---------------------------------------------------------------------------

class _OK(http.server.BaseHTTPRequestHandler):
    """Responds 200 OK to any GET request."""

    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silence request logs


def _start_health_server(port: int):
    """Start a minimal HTTP health server on *port* in a background thread."""
    try:
        srv = http.server.HTTPServer(("0.0.0.0", port), _OK)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"[prod] Health server up on :{port}", flush=True)
        return srv
    except OSError as exc:
        print(f"[prod] Health server :{port} skipped ({exc})", flush=True)
        return None


# Start health server on MAIN_PORT (5000) only.
# Port 8080 belongs to the API server — never bind it here.
_health_srv = _start_health_server(MAIN_PORT)

# Wait so Replit's port-detection probe sees the port come up
time.sleep(1.5)
print(f"[prod] Health server running on port {MAIN_PORT}", flush=True)

# Release port 5000 so bot.py's keep_alive (Flask/waitress) can bind it.
if _health_srv:
    _health_srv.shutdown()
    _health_srv = None
time.sleep(0.5)  # give the OS time to free the socket
print(f"[prod] Released port {MAIN_PORT} — handing off to keep_alive", flush=True)


# ---------------------------------------------------------------------------
# 3.  Run bot.py in a supervised restart loop
# ---------------------------------------------------------------------------
# keep_alive.py will bind PORT (5000) and serve the full web panel.
# Do NOT set SKIP_KEEP_ALIVE here.

BOT_ENV = {
    **os.environ,
    "PORT": str(MAIN_PORT),
    # Ensure src/ is on PYTHONPATH so bot.py can resolve `from modules.X import Y`
    "PYTHONPATH": DIR + ((":" + os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else ""),
}


def _run_bot():
    """Supervised restart loop for bot.py."""
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
        print("[prod] Restarting bot.py in 5 s …", flush=True)
        time.sleep(5)


_bot_thread = threading.Thread(target=_run_bot, daemon=True)
_bot_thread.start()


# ---------------------------------------------------------------------------
# 4.  Block main thread — keep the container alive forever
# ---------------------------------------------------------------------------
# bot.py runs as a daemon thread; the main thread must not exit or the
# entire process (and all daemon threads) will be killed.

while True:
    time.sleep(60)
