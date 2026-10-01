#!/usr/bin/env bash
# Shared environment for everything that touches the bot's Python 3.14 toolchain.
#
# Replit has no Python 3.14 module, so the bot runs on a python-build-standalone
# CPython 3.14 that lives INSIDE the workspace (.python/) with its project venv at
# .venv/.  Replit's python-3.11 module injects 3.11-specific paths into the
# environment; they must never leak into the 3.14 interpreter.
#
# The venv is deliberately NOT .pythonlibs: Replit's python module "repairs" that
# directory on every boot / .replit change by re-pointing bin/python* and script
# shebangs at the 3.11 interpreter, which silently downgrades a 3.14 venv there.
#
# Usage:  source "$(dirname "$0")/python314-env.sh"
# Exports: ROOT, PY314_VERSION, PY314_HOME, PY314_BIN, PY314_VENV, PY314_VENV_PY

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT

# --- pinned interpreter (python-build-standalone release) ---------------------
# Bump all four values together; scripts/setup-python314.sh verifies the hash.
export PY314_VERSION="3.14.7"
export PY314_PBS_TAG="20260929"
export PY314_PBS_TRIPLE="x86_64-unknown-linux-gnu"
export PY314_PBS_SHA256="da5357f47b1d9c8d4c439004d463d893ef688a44c27438a62b47073d26d1377e"

export PY314_HOME="$ROOT/.python/cpython-${PY314_VERSION}-linux-x86_64-gnu"
export PY314_BIN="$PY314_HOME/bin/python3.14"
export PY314_VENV="$ROOT/.venv"
export PY314_VENV_PY="$PY314_VENV/bin/python"

# --- strip the python-3.11 module's environment ------------------------------
# PYTHONPATH        -> 3.11 sitecustomize + 3.11 pip
# PYTHONUSERBASE    -> .pythonlibs as a 3.11 *user* site
# REPLIT_PYTHONPATH -> .pythonlibs/lib/python3.11/site-packages + 3.11 setuptools
# PIP_CONFIG_FILE   -> forces `pip --user`, which is invalid inside a venv
unset PYTHONPATH PYTHONUSERBASE PYTHONHOME PYTHONSTARTUP REPLIT_PYTHONPATH \
      VIRTUAL_ENV PIP_CONFIG_FILE PIP_USER

# Replit's wrapped 3.11 exports these shared libraries (libstdc++, zlib, glib,
# X11 ...) before starting Python; manylinux wheels rely on the same set.
if [ -n "${REPLIT_PYTHON_LD_LIBRARY_PATH:-}" ]; then
  export LD_LIBRARY_PATH="${REPLIT_PYTHON_LD_LIBRARY_PATH}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# python-build-standalone was compiled with clang, so sysconfig advertises
# CC=clang; Replit only ships gcc. Source builds (tgcrypto, crc16, coincurve ...)
# need these overrides. setuptools derives LDSHARED from CC automatically.
export CC="${CC:-gcc}"
export CXX="${CXX:-g++}"

# --- uv: always target the 3.14 interpreter and the workspace venv -----------
export UV_PROJECT_ENVIRONMENT="$PY314_VENV"
export UV_PYTHON="$PY314_BIN"
export UV_PYTHON_PREFERENCE="system"
export UV_PYTHON_DOWNLOADS="never"
