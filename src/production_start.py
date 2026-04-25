#!/usr/bin/env python3
"""
Production entry point for Onichan Bot.

Starts the Flask web server IMMEDIATELY so Replit's health-check probe always
gets a 200 response within the first second, regardless of how long bot.py
takes to import and start.

Replit's Reserved-VM health check probes ALL ports listed in .replit's
[[ports]] section (localPort 5000 and localPort 8080).  This script:
  1. Binds the full keep_alive Flask app on MAIN_PORT ($PORT, default 5000)
  2. Binds minimal health-check mirrors on every other known port
  3. Runs bot.py in a supervised restart loop

Architecture:
  Thread 1 – keep_alive.py web server (all routes, admin panel, etc.)
  Thread 2 – minimal Flask mirror on port 8080 (second .replit [[ports]] entry)
  Thread 3 – minimal Flask mirror on port 5000 if MAIN_PORT≠5000
  Main loop – bot.py subprocess restart supervisor (Telegram polling)
"""
import os
import sys
import subprocess
import threading
import time

MAIN_PORT = int(os.environ.get("PORT", 5000))
# All localPorts declared in .replit [[ports]] – health-check probes them all
ALL_PORTS  = [5000, 8080]
DIR        = os.path.dirname(os.path.abspath(__file__))
PY         = sys.executable


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_minimal_app(port_label):
    """Return a tiny Flask app that answers /ping and / with 200."""
    from flask import Flask
    _app = Flask(f"health_{port_label}")

    @_app.route("/ping")
    def _ping():
        return "OK", 200

    @_app.route("/")
    def _home():
        return f"<h1>Onichan Bot</h1><p>Online (:{port_label})</p>", 200

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
        _serve(_make_minimal_app(MAIN_PORT), MAIN_PORT)


main_thread = threading.Thread(target=_run_main_flask, daemon=False)
main_thread.start()


# ── 2. Start health-check mirrors on every other known port ──────────────────
# Replit probes ALL [[ports]] entries – each must return 200.

def _mirror_thread(port):
    def _run():
        print(f"[prod] Health mirror: :{port}", flush=True)
        try:
            _serve(_make_minimal_app(port), port)
        except Exception as exc:
            print(f"[prod] Health mirror :{port} failed ({exc})", flush=True)
    return threading.Thread(target=_run, daemon=False)


for _p in ALL_PORTS:
    if _p != MAIN_PORT:
        _mirror_thread(_p).start()


# Give all servers 2 s to bind before launching the bot subprocess
time.sleep(2)
bound = [MAIN_PORT] + [p for p in ALL_PORTS if p != MAIN_PORT]
print(f"[prod] Flask up on ports: {bound}", flush=True)


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
