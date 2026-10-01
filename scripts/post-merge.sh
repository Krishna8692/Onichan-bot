#!/bin/bash
set -e
pnpm install --frozen-lockfile
pnpm --filter db push
# Bot: Python 3.14 interpreter + venv (.python/, .venv/) from uv.lock. Idempotent.
bash scripts/setup-python314.sh
# Separate, restricted general-purpose Hermes gateway.
bash scripts/setup-hermes.sh
