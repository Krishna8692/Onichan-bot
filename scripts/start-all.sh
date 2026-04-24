#!/usr/bin/env bash
set -e

DIST="/home/runner/workspace/artifacts/api-server/dist/index.mjs"

if [ ! -f "$DIST" ]; then
  echo "[Deploy] Building API server..."
  cd /home/runner/workspace
  pnpm --filter @workspace/api-server run build
fi

echo "[Deploy] Starting API server on port 8080..."
export PORT=8080
export NODE_ENV=production
exec node --enable-source-maps "$DIST"
