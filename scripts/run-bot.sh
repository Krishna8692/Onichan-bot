#!/usr/bin/env bash
# Start the Onichan bot on the workspace-local CPython 3.14.
# Used by the "Onichan Bot" workflow (with BOT_DISABLE_POLLING=1) and by the
# production run command in artifacts/onichan-web/.replit-artifact/artifact.toml.
set -euo pipefail

# shellcheck source=scripts/python314-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/python314-env.sh"
cd "$ROOT"

# Self-heal: missing toolchain, or a venv whose python no longer points at our
# 3.14 build (uv recreates the venv when the interpreter does not match).
if [ ! -x "$PY314_BIN" ] || [ ! -x "$PY314_VENV_PY" ] ||
   [ "$(readlink -f "$PY314_VENV_PY")" != "$(readlink -f "$PY314_BIN")" ]; then
  echo "[run-bot] Python 3.14 environment missing or broken - provisioning it first" >&2
  bash "$ROOT/scripts/setup-python314.sh" --no-compile >&2
fi

export PYTHONPATH="$ROOT/bot_src"
export PYTHONUNBUFFERED=1
exec "$PY314_VENV_PY" "$ROOT/bot_main.py" "$@"
