#!/usr/bin/env python3
"""
Production entry point for Onichan Bot — Reserved VM edition.

Strategy
--------
1. Bind a stdlib http.server on EVERY exposed port (5000, 8080) within
   the first 0.1 seconds of startup — no third-party packages required.
   This guarantees the deployment health-check probe gets HTTP 200 before
   any other code runs.

2. Start bot.py as a supervised subprocess (Telegram polling + full
   keep_alive web panel if SKIP_KEEP_ALIVE is not set in the child env).

3. Block the main process forever so the container stays alive.
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

# All ports declared in .replit [[ports]] — probe ALL of them
ALL_PORTS = [5000, 8080]


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


def _start_health_server(port: int, daemon: bool = True):
    """Start a minimal HTTP health server on *port* in a background thread."""
    try:
        srv = http.server.HTTPServer(("0.0.0.0", port), _OK)
        t = threading.Thread(target=srv.serve_forever, daemon=daemon)
        t.start()
        print(f"[prod] Health server up on :{port}", flush=True)
        return srv
    except OSError as exc:
        print(f"[prod] Health server :{port} skipped ({exc})", flush=True)
        return None


# Start health servers on every exposed port — runs in < 100 ms
# Always include MAIN_PORT even if it's not in ALL_PORTS
_all_ports = sorted(set(ALL_PORTS + [MAIN_PORT]))
_servers = []
for _p in _all_ports:
    _srv = _start_health_server(_p, daemon=(_p != MAIN_PORT))
    _servers.append(_srv)

# Small pause so threads actually bind before the health probe arrives
time.sleep(0.3)
print(f"[prod] Health servers running on ports {ALL_PORTS}", flush=True)


# ---------------------------------------------------------------------------
# 3.  Run bot.py in a supervised restart loop
# ---------------------------------------------------------------------------
# SKIP_KEEP_ALIVE=1  →  bot.py won't try to start its own Flask server
# (the health servers above already handle /ping and /).

BOT_ENV = {
    **os.environ,
    "SKIP_KEEP_ALIVE": "1",
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
# 4.  Block main thread — keep container alive via the non-daemon server
# ---------------------------------------------------------------------------
# The health server for MAIN_PORT was started with daemon=False, so the
# process stays alive as long as that server runs.  If for any reason it
# exited, fall back to a simple sleep loop.

main_srv = _servers[0] if _servers else None
if main_srv and not threading.current_thread().daemon:
    # serve_forever() was already called in its own thread; just join it.
    pass

# Safety net: sleep forever so the process never exits
while True:
    time.sleep(60)
