#!/usr/bin/env bash
# Provision the pinned Hermes source checkout and its PM-owned Python runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="$ROOT/.hermes-agent"
HERMES_HOME_DIR="$ROOT/.hermes-home"
BOOTSTRAP_HOME="$ROOT/.hermes-bootstrap-home"
RUNTIME="$ROOT/scripts/hermes_runtime.py"
PIN="e8c97320ac8691d4de92af49f98459f9ef9ddb08"
NPM_HASH="5dbb86c71d07a1957f2e90734092dd6a58bdcd9ebc2d8d41ca1c6e6a21d364e1"
NPM_FIREWALL_URL="http://package-firewall.replit.internal/npm/npm/-/npm-12.0.2.tgz"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[setup-hermes] python3 is required to query Hermes PM" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "[setup-hermes] curl is required to access the Replit package firewall" >&2
  exit 1
fi
if ! command -v gcc >/dev/null 2>&1; then
  echo "[setup-hermes] gcc is required to locate libatomic.so.1" >&2
  exit 1
fi

atomic_so="$(gcc -print-file-name=libatomic.so.1)"
if [[ "$atomic_so" != /*/libatomic.so.1 ]]; then
  echo "[setup-hermes] gcc did not locate an absolute libatomic.so.1 path" >&2
  exit 1
fi
LD_LIBRARY_PATH="${REPLIT_PYTHON_LD_LIBRARY_PATH:-}"
atomic_dir="$(dirname "$atomic_so")"
case ":$LD_LIBRARY_PATH:" in
  *":$atomic_dir:"*) ;;
  *) LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$atomic_dir" ;;
esac
export LD_LIBRARY_PATH

ORIGINAL_NPM_REGISTRY="${npm_config_registry:-${NPM_CONFIG_REGISTRY:-}}"
if [[ -z "$ORIGINAL_NPM_REGISTRY" ]]; then
  echo "[setup-hermes] npm_config_registry/NPM_CONFIG_REGISTRY must contain the configured package mirror" >&2
  exit 1
fi

mkdir -p "$HERMES_HOME_DIR" "$BOOTSTRAP_HOME"

pm_python=""
if [[ -d "$AGENT_DIR" ]]; then
  pm_python="$(python3 "$RUNTIME" resolve-python --root "$ROOT" --home "$HERMES_HOME_DIR" 2>/dev/null || true)"
fi
runtime_ready=false
if [[ -n "$pm_python" && -x "$pm_python" ]] &&
   "$pm_python" "$RUNTIME" check >/dev/null 2>&1; then
  runtime_ready=true
fi
products_ready=false
if [[ -f "$AGENT_DIR/install-stamp.json" ]] &&
   grep -Fq "\"commit\": \"$PIN\"" "$AGENT_DIR/install-stamp.json"; then
  products_ready=true
fi

if [[ "$runtime_ready" != true || "$products_ready" != true ]]; then
  installer="$AGENT_DIR/scripts/install.sh"
  installer_tmp=""
  current_commit=""
  checkout_status="unavailable"
  if [[ -d "$AGENT_DIR/.git" ]]; then
    current_commit="$(git -C "$AGENT_DIR" rev-parse HEAD 2>/dev/null || true)"
    checkout_status="$(git -C "$AGENT_DIR" status --porcelain --untracked-files=all 2>/dev/null || true)"
  fi
  if [[ "$current_commit" != "$PIN" || -n "$checkout_status" || ! -f "$installer" ]]; then
    installer_tmp="$(mktemp --suffix=.sh "$ROOT/.hermes-installer.XXXXXX")"
    trap 'rm -f "${installer_tmp:-}"' EXIT
    curl --fail --location --silent --show-error \
      "https://raw.githubusercontent.com/NousResearch/hermes-agent/$PIN/scripts/install.sh" \
      --output "$installer_tmp"
    installer="$installer_tmp"
  fi

  installer_args=(
    --non-interactive
    --skip-browser
    --skip-computer-use
    --dir "$AGENT_DIR"
    --hermes-home "$HERMES_HOME_DIR"
    --commit "$PIN"
  )
  run_installer_stage() {
    local stage="$1"
    if [[ "$stage" == "python-deps" ]]; then
      env -u NPM_CONFIG_REGISTRY \
        HOME="$BOOTSTRAP_HOME" HERMES_HOME="$HERMES_HOME_DIR" \
        HERMES_INSTALL_DIR="$AGENT_DIR" \
        npm_config_registry="$npm_relay_registry" \
        bash "$installer" "${installer_args[@]}" --stage "$stage"
    else
      env HOME="$BOOTSTRAP_HOME" HERMES_HOME="$HERMES_HOME_DIR" \
        HERMES_INSTALL_DIR="$AGENT_DIR" \
        npm_config_registry="$ORIGINAL_NPM_REGISTRY" \
        NPM_CONFIG_REGISTRY="$ORIGINAL_NPM_REGISTRY" \
        bash "$installer" "${installer_args[@]}" --stage "$stage"
    fi
  }

  if [[ "$runtime_ready" != true ]]; then
    run_installer_stage prerequisites
    run_installer_stage repository
    run_installer_stage venv

    archive="$(mktemp --suffix=.tgz "$HERMES_HOME_DIR/npm-12.0.2.XXXXXX")"
    port_file="$(mktemp "$HERMES_HOME_DIR/npm-relay-port.XXXXXX")"
    rm -f "$port_file"
    relay_pid=""
    stop_relay() {
      if [[ -n "$relay_pid" ]]; then
        kill "$relay_pid" 2>/dev/null || true
        wait "$relay_pid" 2>/dev/null || true
        relay_pid=""
      fi
      rm -f "$archive" "$port_file"
    }
    trap stop_relay EXIT
    trap 'stop_relay; exit 130' INT
    trap 'stop_relay; exit 143' TERM
    curl --fail --location --silent --show-error --retry 3 \
      "$NPM_FIREWALL_URL" --output "$archive"
    if ! printf '%s  %s\n' "$NPM_HASH" "$archive" | sha256sum --check --status; then
      echo "[setup-hermes] npm-12.0.2 tarball failed SHA256 verification" >&2
      exit 1
    fi

    python3 "$RUNTIME" npm-relay --archive "$archive" --port-file "$port_file" \
      >/dev/null 2>&1 &
    relay_pid=$!
    for _attempt in $(seq 1 100); do
      [[ -s "$port_file" ]] && break
      if ! kill -0 "$relay_pid" 2>/dev/null; then
        echo "[setup-hermes] local npm relay exited before becoming ready" >&2
        exit 1
      fi
      sleep 0.1
    done
    if [[ ! -s "$port_file" ]]; then
      echo "[setup-hermes] timed out starting the loopback npm relay" >&2
      exit 1
    fi
    relay_port="$(cat "$port_file")"
    npm_relay_registry="http://127.0.0.1:${relay_port}/"
    run_installer_stage python-deps
    stop_relay
    trap - INT TERM
    trap 'rm -f "${installer_tmp:-}"' EXIT
  else
    # The PM-owned Python environment is already healthy; preserve the user's
    # configured npm mirror for config/product maintenance stages.
    npm_relay_registry="$ORIGINAL_NPM_REGISTRY"
  fi

  if [[ "$products_ready" != true ]]; then
    run_installer_stage config
    pm_python="$(python3 "$RUNTIME" resolve-python --root "$ROOT" --home "$HERMES_HOME_DIR")"
    # This is the installer's supported product-completion entrypoint. Calling
    # it directly avoids mutating the host user's .bashrc/.profile.
    env HOME="$BOOTSTRAP_HOME" HERMES_HOME="$HERMES_HOME_DIR" \
      npm_config_registry="$ORIGINAL_NPM_REGISTRY" \
      NPM_CONFIG_REGISTRY="$ORIGINAL_NPM_REGISTRY" \
      "$pm_python" -I -B -X utf8 \
      "$AGENT_DIR/hermes_cli/source_completion.py" \
      --source "$AGENT_DIR" --prepared
  fi
  if [[ -n "$installer_tmp" ]]; then
    rm -f "$installer_tmp"
    installer_tmp=""
    trap - EXIT
  fi
fi

if [[ -z "$pm_python" || ! -x "$pm_python" ]]; then
  pm_python="$(python3 "$RUNTIME" resolve-python --root "$ROOT" --home "$HERMES_HOME_DIR")"
fi
if ! "$pm_python" -c 'import anthropic' >/dev/null 2>&1; then
  # Current upstream separates provider SDKs from its core dependency set.
  # PM records this extra and retains it across subsequent environment rebuilds.
  (
    cd "$AGENT_DIR"
    HOME="$BOOTSTRAP_HOME" HERMES_HOME="$HERMES_HOME_DIR" \
      npm_config_registry="$ORIGINAL_NPM_REGISTRY" \
      "$pm_python" -m pm.cli install --extra anthropic
  )
  pm_python="$(python3 "$RUNTIME" resolve-python --root "$ROOT" --home "$HERMES_HOME_DIR")"
fi
ready_python="$("$pm_python" "$RUNTIME" prepare)"
echo "[setup-hermes] ready with PM-selected Python: $ready_python"