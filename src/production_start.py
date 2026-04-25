#!/usr/bin/env python3
"""
Production entry point for Onichan Bot.

Starts the Flask web server IMMEDIATELY so Replit's health-check probe always
gets a 200 response within the first second, regardless of how long bot.py
takes to import and start.

Architecture:
  Thread 1 (Flask)  — keep_alive.py web server (all routes, admin panel, etc.)
  Main thread       — bot.py subprocess restart loop (Telegram polling)
"""
import os
import sys
import subprocess
import threading
import time

PORT  = int(os.environ.get("PORT", 8080))
DIR   = os.path.dirname(os.path.abspath(__file__))
PY    = sys.executable


# ── 1. Start Flask web server immediately ────────────────────────────────────

def _run_flask():
    try:
        # Import the real Flask app — all /admin, /user, /api, /ping routes
        from keep_alive import run
        print(f"[prod] Flask: full app on :{PORT}", flush=True)
        run()                                   # blocks until killed
    except Exception as exc:
        print(f"[prod] Flask: keep_alive failed ({exc}), using minimal server",
              flush=True)
        # Minimal fallback so at least /ping and / return 200
        from flask import Flask
        _app = Flask("health")

        @_app.route("/ping")
        def _ping():
            return "OK", 200

        @_app.route("/")
        def _home():
            return "<h1>Onichan Bot</h1><p>Online</p>", 200

        try:
            from waitress import serve
            serve(_app, host="0.0.0.0", port=PORT)
        except Exception:
            _app.run(host="0.0.0.0", port=PORT)


flask_thread = threading.Thread(target=_run_flask, daemon=False)
flask_thread.start()

# Give Flask 2 s to bind before continuing (not strictly required, but avoids
# a tiny window where health check could hit before the socket is ready)
time.sleep(2)
print(f"[prod] Flask up on :{PORT} — starting bot.py", flush=True)


# ── 2. Run bot.py in a supervised restart loop ───────────────────────────────
# SKIP_KEEP_ALIVE=1 tells bot.py not to start a second Flask server on the
# same port (it would fail to bind anyway, but this is cleaner).

BOT_ENV = {**os.environ, "SKIP_KEEP_ALIVE": "1", "PORT": str(PORT)}

while True:
    print("[prod] Starting bot.py …", flush=True)
    try:
        rc = subprocess.run(
            [PY, "bot.py"],
            env=BOT_ENV,
            cwd=DIR,
        ).returncode
        print(f"[prod] bot.py exited with code {rc}", flush=True)
    except Exception as exc:
        print(f"[prod] bot.py launch error: {exc}", flush=True)

    # Don't spin too fast if bot.py keeps crashing immediately
    print("[prod] Restarting bot.py in 5 s …", flush=True)
    time.sleep(5)
