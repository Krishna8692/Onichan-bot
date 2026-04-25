#!/usr/bin/env bash
set -e

# Absolute path to the Python binary managed by Replit/.pythonlibs
PYTHON="/home/runner/workspace/.pythonlibs/bin/python"

# Fall back to whatever python3/python is available if .pythonlibs is absent
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 || command -v python)"
fi

export PYTHONPATH="/home/runner/workspace/src:${PYTHONPATH}"
export PORT="${PORT:-5000}"
export FORCE_WEB_SERVER=1

echo "[start-bot] Using Python: $PYTHON"
echo "[start-bot] PORT: $PORT"

cd /home/runner/workspace/src

# production_start.py:
#   1. Starts Flask (keep_alive routes) immediately so health-check passes
#   2. Then runs bot.py as a supervised subprocess (auto-restarts on crash)
exec "$PYTHON" production_start.py
