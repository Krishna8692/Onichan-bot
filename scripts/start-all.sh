#!/usr/bin/env bash

DIST="/home/runner/workspace/artifacts/api-server/dist/index.mjs"

if ss -tlnp 2>/dev/null | grep -q ':8080 '; then
  echo "[Deploy] Port 8080 already in use — dev workflow is running, skipping."
  exit 0
fi

if [ ! -f "$DIST" ]; then
  echo "[Deploy] Building API server..."
  cd /home/runner/workspace
  pnpm --filter @workspace/api-server run build
fi

echo "[Deploy] Starting API server on port 8080..."
export PORT=8080
export NODE_ENV=production
exec node --enable-source-maps "$DIST"
