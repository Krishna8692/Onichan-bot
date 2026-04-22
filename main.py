import os
import runpy

os.environ.setdefault("PORT", "8080")

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
runpy.run_path(os.path.join(src_dir, "bot.py"), run_name="__main__")
