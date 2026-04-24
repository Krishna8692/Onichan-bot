#!/usr/bin/env bash
export PATH="/home/runner/workspace/.pythonlibs/bin:$PATH"
export PORT=5000
cd /home/runner/workspace/src
exec python bot.py
