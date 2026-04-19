#!/usr/bin/env bash
set -e

echo "[Deploy] Building API server..."
cd /home/runner/workspace
pnpm --filter @workspace/api-server run build

echo "[Deploy] Starting API server on port 8080..."
PORT=8080 NODE_ENV=production node --enable-source-maps \
  /home/runner/workspace/artifacts/api-server/dist/index.mjs &

echo "[Deploy] Starting bot on port 5000..."
cd /home/runner/workspace/src
exec python bot.py
