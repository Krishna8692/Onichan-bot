#!/usr/bin/env bash
# Launch only the pinned Hermes API gateway on PM's selected Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/scripts/hermes_runtime.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[run-hermes] python3 is required to query Hermes PM" >&2
  exit 1
fi

PROJECT_PYTHON="$(python3 "$RUNTIME" resolve-python --root "$ROOT" --home "$ROOT/.hermes-home")" || {
  echo "[run-hermes] could not resolve pm.environments.project_python" >&2
  exit 1
}
if [[ ! -x "$PROJECT_PYTHON" || "$PROJECT_PYTHON" == "$ROOT/.hermes-agent/venv/"* ]]; then
  echo "[run-hermes] PM-selected Python is missing or points at the obsolete checkout venv" >&2
  exit 1
fi

exec "$PROJECT_PYTHON" "$RUNTIME" gateway