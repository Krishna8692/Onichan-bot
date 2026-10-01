#!/usr/bin/env bash
# Independently supervise the bot poller and the isolated Hermes gateway.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/scripts/hermes_supervisor.py"