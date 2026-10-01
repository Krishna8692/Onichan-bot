# Onichan Bot

Telegram bot (`bot_src/bot.py`, ~120 modules) with a Flask web panel, plus a pnpm workspace (API server, React web panel shell, canvas sandbox).

## Run & Operate

### Bot (Python 3.14)
- `bash scripts/run-bot.sh` — start the bot on the workspace-local CPython 3.14 (this is what the `Onichan Bot` workflow and the production run command execute). The first log line prints the interpreter version.
- `bash scripts/setup-python314.sh` — (re)provision the toolchain: downloads the pinned python-build-standalone CPython 3.14 into `.python/`, syncs `.venv/` from `uv.lock`, precompiles bytecode. Idempotent (~1 s when nothing changed). Runs automatically from `scripts/post-merge.sh` and as the production build step.
- `scripts/uv314.sh add <pkg>` / `remove <pkg>` / `lock` — manage Python dependencies. **Do not use the Replit Packages pane or plain `uv add`/`pip install` for the bot**: they target Replit's 3.11 environment (`.pythonlibs`), which the bot does not use.
- `scripts/uv314.sh run python -c "..."` — run anything inside the 3.14 venv.
- Dev workflow runs with `BOT_DISABLE_POLLING=1` (the published bot owns Telegram polling on the live token) and `PORT=3000` for the panel.
- Required env: `BOT_TOKEN`, `OWNER_ID`, `SESSION_SECRET`; optional per-feature keys (see `bot_src/modules/*`).

### Node workspace
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)

## Stack

- Bot: CPython 3.14.7 (python-build-standalone, pinned in `scripts/python314-env.sh`), python-telegram-bot 22, Flask + waitress panel, uv-managed deps (`pyproject.toml` + `uv.lock`)
- pnpm workspaces, Node.js 24, TypeScript 5.9; API: Express 5; DB: PostgreSQL + Drizzle ORM

## Where things live

- `bot_main.py` → entrypoint; runs `bot_src/bot.py`. `bot_src/keep_alive.py` is the Flask panel; `bot_src/modules/` holds features.
- `scripts/python314-env.sh` — single source of truth for the 3.14 toolchain (version pin, sha256, paths, env sanitising). `setup-python314.sh`, `run-bot.sh`, `uv314.sh` all source it.
- `artifacts/onichan-web/.replit-artifact/artifact.toml` — production build (`scripts/setup-python314.sh`) and run (`scripts/run-bot.sh`) commands for the bot. `.replit` `[deployment]` holds no run command.
- `scripts/post-merge.sh` — pnpm install, db push, then the Python setup script (post-merge timeout is 10 min to allow a cold toolchain rebuild).

## Architecture decisions

- Replit has no Python 3.14 module, so the interpreter lives inside the workspace (`.python/`, gitignored, ~110 MB) and ships with the Reserved VM snapshot. The `python-3.11` module stays in `.replit` because it provides `uv`, gcc and the shared C libraries.
- The venv is `.venv`, not `.pythonlibs`: Replit's python module rewrites `.pythonlibs/bin/python*` and script shebangs back to 3.11 on boot / `.replit` changes, which silently downgraded a 3.14 venv placed there.
- `coincurve` is a direct dependency pinned to a git commit (`[tool.uv.sources]`) because 21.0.0 on PyPI does not build on 3.14; drop the pin once 22.0.0 is released.
- `scripts/python314-env.sh` exports `CC=gcc`: the standalone interpreter advertises `clang`, which Replit does not ship, and several deps (tgcrypto, crc16, coincurve) build from source.

## Gotchas

- Never start 3.14 with Replit's 3.11 env intact (`PYTHONPATH`, `PYTHONUSERBASE`, `REPLIT_PYTHONPATH`, `UV_PROJECT_ENVIRONMENT`); always go through the scripts.
- `import pyrogram` must stay lazy inside a running event loop (it raises "no current event loop" at import on 3.14); `modules/pyro_uploader.py` already does this.
- On 3.14 `asyncio.get_event_loop()` raises outside a running loop; use `get_running_loop()` in coroutines and pass the bot loop explicitly to threads (see `gate_monitor.py` / `hibp_watcher.py`).
- `bot_src/modules/freaky/*` has 10 modules with pre-existing broken imports (`get_bypass_headers`, `curl_compat` no longer exist); they are only imported lazily, unrelated to the 3.14 move.
- Changing `pyproject.toml` by hand requires `scripts/uv314.sh lock`; the setup script uses `uv sync --locked` and fails loudly on a stale lock.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
