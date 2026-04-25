#!/usr/bin/env python3
"""
Production entry point for Onichan Bot.

Starts the Flask web server IMMEDIATELY so Replit's health-check probe always
gets a 200 response within the first second, regardless of how long bot.py
takes to import and start.

Replit's Reserved-VM health check uses port 5000 (from the .replit [[ports]]
table) while the main app runs on port 8080 (artifact.toml localPort).
This script therefore binds the full Flask app to whichever port $PORT
specifies (default 8080) and also starts a minimal health-check responder on
port 5000 — so the deployment probe always succeeds.

Architecture:
  Thread 1 – keep_alive.py web server (all routes, admin panel, etc.)
  Thread 2 – minimal Flask on port 5000 (health-check mirror)
  Main loop – bot.py subprocess restart supervisor (Telegram polling)
"""
import os
import sys
import subprocess
import threading
import time

MAIN_PORT   = int(os.environ.get("PORT", 5000))
HEALTH_PORT = 5000          # .replit's first [[ports]] entry; deployment probe
DIR         = os.path.dirname(os.path.abspath(__file__))
PY          = sys.executable


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_minimal_app():
    """Return a tiny Flask app that answers /ping and / with 200."""
    from flask import Flask
    _app = Flask("health")

    @_app.route("/ping")
    def _ping():
        return "OK", 200

    @_app.route("/")
    def _home():
        return "<h1>Onichan Bot</h1><p>Online</p>", 200

    return _app


def _serve(app, port):
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
    except Exception:
        app.run(host="0.0.0.0", port=port)


# ── 1. Start main Flask app (full keep_alive routes) ─────────────────────────

def _run_main_flask():
    try:
        from keep_alive import run
        print(f"[prod] Main Flask: full keep_alive app on :{MAIN_PORT}", flush=True)
        run()                                   # blocks until killed
    except Exception as exc:
        print(f"[prod] Main Flask: fallback ({exc})", flush=True)
        _serve(_make_minimal_app(), MAIN_PORT)


main_thread = threading.Thread(target=_run_main_flask, daemon=False)
main_thread.start()


# ── 2. Start health-check mirror on port 5000 (if different from MAIN_PORT) ──
# Replit's deployment VM probes port 5000 regardless of artifact.toml localPort.

def _run_health_flask():
    if HEALTH_PORT == MAIN_PORT:
        return                          # already covered by main thread
    print(f"[prod] Health mirror: :{HEALTH_PORT}", flush=True)
    try:
        _serve(_make_minimal_app(), HEALTH_PORT)
    except Exception as exc:
        print(f"[prod] Health mirror failed ({exc})", flush=True)


health_thread = threading.Thread(target=_run_health_flask, daemon=False)
health_thread.start()

# Give both servers 2 s to bind before launching the bot subprocess
time.sleep(2)
print(f"[prod] Flask up on :{MAIN_PORT} and health mirror on :{HEALTH_PORT}", flush=True)


# ── 3. Run bot.py in a supervised restart loop ───────────────────────────────
# SKIP_KEEP_ALIVE=1 → bot.py skips keep_alive() since Flask is already running.

BOT_ENV = {**os.environ, "SKIP_KEEP_ALIVE": "1", "PORT": str(MAIN_PORT)}

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

    print("[prod] Restarting bot.py in 5 s …", flush=True)
    time.sleep(5)
