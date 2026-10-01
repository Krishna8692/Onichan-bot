# Onichan Bot

Onichan is a Telegram bot with a Flask-based web panel. This repository also
contains the API server and component-preview workspace used by the project.

## Project components

- **Telegram bot:** Python application in `bot_src/`, started through
  `bot_main.py`.
- **Web panel:** Flask application in `bot_src/keep_alive.py`.
- **API server:** TypeScript/Express service in `artifacts/api-server/`.
- **Component preview:** Vite-based UI sandbox in `artifacts/mockup-sandbox/`.

## Requirements

The bot setup scripts currently target **64-bit Linux**. They use:

- CPython 3.14, provisioned by the setup script
- `uv`, `curl`, `tar`, `sha256sum`, and a C compiler (`gcc`/`g++`)
- Node.js 24 and pnpm for the JavaScript workspace

On Replit, the configured Python module supplies `uv` and the native build
tools required by the bot dependencies.

## Getting started

Clone the repository, then provision the bot's Python runtime and dependencies:

```bash
bash scripts/setup-python314.sh
```

Configure the required runtime variables through your environment or the
platform's secret manager:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token |
| `OWNER_ID` | Telegram user ID of the bot owner |
| `SESSION_SECRET` | Secret used by web-panel sessions |

Some optional features may require additional environment variables. Configure
those through a secret manager; do not commit credentials or `.env` files.

Start the bot and web panel:

```bash
bash scripts/run-bot.sh
```

The startup log prints the Python version. Set `PORT` to choose the web-panel
port. For development with the configured Replit workflow, keep
`BOT_DISABLE_POLLING=1` so the development instance does not compete with the
published bot for Telegram updates.

## Python dependencies

The Python dependencies are declared in `pyproject.toml` and locked in
`uv.lock`. Use the wrapper so commands target the project's Python 3.14
environment:

```bash
scripts/uv314.sh add <package>
scripts/uv314.sh remove <package>
scripts/uv314.sh run python -c "import sys; print(sys.version)"
```

After changing dependency declarations, update the lockfile with:

```bash
scripts/uv314.sh lock
```

The runtime and virtual environment are created locally under `.python/` and
`.venv/`; they are not committed to Git.

## JavaScript workspace

Install workspace dependencies:

```bash
pnpm install --frozen-lockfile
```

Useful checks:

```bash
pnpm run typecheck
pnpm run build
```

Start an individual service:

```bash
pnpm --filter @workspace/api-server run dev
pnpm --filter @workspace/onichan-web run dev
pnpm --filter @workspace/mockup-sandbox run dev
```

## Repository layout

```text
artifacts/
  api-server/       Express API
  mockup-sandbox/   Component preview workspace
  onichan-web/      Web-panel artifact configuration
bot_src/            Telegram bot, web panel, and bot modules
scripts/            Python setup, launch, and dependency helpers
pyproject.toml      Python dependency declarations
uv.lock             Locked Python dependency graph
```

## Security and deployment

Never commit bot tokens, session secrets, API keys, private keys, or user data.
Use your hosting platform's secret-management feature to configure runtime
credentials. Keep a development bot instance's Telegram polling disabled when
the published instance uses the same bot token.

Deployment commands and service settings are defined in the artifact
configuration under `artifacts/`.

## License

This repository does not currently include a `LICENSE` file. Add one before
redistributing the project or relying on a specific open-source license.