#!/usr/bin/env bash
set -e
export PORT=5000
cd /home/runner/workspace/src
exec python bot.py
