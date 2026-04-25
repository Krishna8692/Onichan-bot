#!/usr/bin/env bash
set -e
export PATH="/home/runner/workspace/.pythonlibs/bin:/usr/local/bin:$PATH"
export PYTHONPATH="/home/runner/workspace/src:$PYTHONPATH"
# Replit Reserved VM routes external traffic to port 8080
export PORT="${PORT:-8080}"
cd /home/runner/workspace/src
exec python bot.py
