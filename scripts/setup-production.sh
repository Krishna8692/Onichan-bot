#!/usr/bin/env bash
# Provision the two independent Python runtimes used by the published processes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$ROOT/scripts/setup-python314.sh"
bash "$ROOT/scripts/setup-hermes.sh"