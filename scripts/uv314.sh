#!/usr/bin/env bash
# Run uv against the bot's Python 3.14 venv (.venv) instead of Replit's 3.11 defaults.
#
#   scripts/uv314.sh add <package>        add a dependency + update uv.lock + install
#   scripts/uv314.sh remove <package>
#   scripts/uv314.sh lock                 re-resolve uv.lock after editing pyproject.toml
#   scripts/uv314.sh run python -c ...    run anything inside the 3.14 venv
set -euo pipefail

# shellcheck source=scripts/python314-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/python314-env.sh"
cd "$ROOT"

if [ ! -x "$PY314_BIN" ]; then
  echo "[uv314] CPython $PY314_VERSION is not installed yet - run scripts/setup-python314.sh first" >&2
  exit 1
fi

exec uv "$@"
