#!/usr/bin/env bash
# Provision the bot's Python 3.14 toolchain:  .python/ (interpreter) + .venv/ (venv).
#
# Idempotent and fast when nothing changed, so it is safe to run from:
#   - a fresh checkout                      bash scripts/setup-python314.sh
#   - the post-merge script                 (scripts/post-merge.sh)
#   - the production build step             (artifacts/onichan-web artifact.toml)
#
# Flags:  --no-compile   skip bytecode precompilation (faster, slower first start)
set -euo pipefail

# shellcheck source=scripts/python314-env.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/python314-env.sh"
cd "$ROOT"

COMPILE_FLAG="--compile-bytecode"
for arg in "$@"; do
  case "$arg" in
    --no-compile) COMPILE_FLAG="" ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '[setup-python314] %s\n' "$*"; }

# -----------------------------------------------------------------------------
# 1. Interpreter: python-build-standalone CPython ${PY314_VERSION}
# -----------------------------------------------------------------------------
interpreter_ok() {
  [ -x "$PY314_BIN" ] &&
    [ "$("$PY314_BIN" -c 'import platform; print(platform.python_version())' 2>/dev/null)" = "$PY314_VERSION" ]
}

if interpreter_ok; then
  log "CPython $PY314_VERSION already installed at $PY314_HOME"
else
  asset="cpython-${PY314_VERSION}+${PY314_PBS_TAG}-${PY314_PBS_TRIPLE}-install_only_stripped.tar.gz"
  url="https://github.com/astral-sh/python-build-standalone/releases/download/${PY314_PBS_TAG}/${asset/+/%2B}"
  tmp="$ROOT/.python/.temp"
  mkdir -p "$tmp"
  log "downloading $asset"
  curl -fL --retry 3 --retry-delay 2 -o "$tmp/$asset" "$url"
  log "verifying sha256"
  echo "$PY314_PBS_SHA256  $tmp/$asset" | sha256sum -c - >/dev/null
  rm -rf "$PY314_HOME"
  mkdir -p "$PY314_HOME"
  # archive layout: python/{bin,lib,include,share}
  tar -xzf "$tmp/$asset" -C "$PY314_HOME" --strip-components=1
  rm -f "$tmp/$asset"
  interpreter_ok || { log "ERROR: extracted interpreter does not run"; exit 1; }
  log "installed CPython $PY314_VERSION at $PY314_HOME"
fi

# -----------------------------------------------------------------------------
# 2. Project venv: .venv, synced from uv.lock
#    uv recreates the venv automatically when its interpreter is not 3.14.
# -----------------------------------------------------------------------------
log "syncing $PY314_VENV from uv.lock"
uv sync --locked --no-dev --python "$PY314_BIN" $COMPILE_FLAG

# -----------------------------------------------------------------------------
# 3. Sanity check
# -----------------------------------------------------------------------------
"$PY314_VENV_PY" - <<'EOF'
import platform, sys
assert platform.python_version().startswith("3.14."), sys.version
import telegram, flask, pandas, cryptography, coincurve, tgcrypto  # noqa: F401
print(f"[setup-python314] OK  python {platform.python_version()}  ({sys.executable})")
EOF
