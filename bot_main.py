import os
import platform
import runpy
import sys

os.environ.setdefault("PORT", "8080")

# The bot targets the workspace-local CPython 3.14 (see scripts/run-bot.sh).
print(f"[bot] Python {platform.python_version()} ({sys.executable})", flush=True)
if sys.version_info < (3, 14):
    print(
        "[bot] WARNING: expected Python 3.14+. Start the bot with scripts/run-bot.sh "
        "(or run scripts/setup-python314.sh first).",
        flush=True,
    )

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_src")
runpy.run_path(os.path.join(src_dir, "bot.py"), run_name="__main__")
