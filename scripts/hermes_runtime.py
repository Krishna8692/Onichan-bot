#!/usr/bin/env python3
"""Fail-closed runtime support for the isolated Hermes API gateway."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from typing import Any, Mapping


PINNED_COMMIT = "e8c97320ac8691d4de92af49f98459f9ef9ddb08"
HERMES_HMAC_CONTEXT = b"onichan-hermes-api-v1"
NPM_TARBALL_PATH = "/npm/-/npm-12.0.2.tgz"
NPM_TARBALL_SHA256 = "5dbb86c71d07a1957f2e90734092dd6a58bdcd9ebc2d8d41ca1c6e6a21d364e1"
NPM_FIREWALL_URL = (
    "http://package-firewall.replit.internal/npm/npm/-/npm-12.0.2.tgz"
)

MESSAGE_ADAPTERS = (
    "telegram",
    "discord",
    "whatsapp",
    "slack",
    "signal",
    "homeassistant",
    "qqbot",
    "yuanbao",
    "teams",
    "google_chat",
    "mattermost",
    "matrix",
    "irc",
    "webhook",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def derive_api_server_key(session_secret: str) -> str:
    """Derive the API key shared with the bot bridge; never persist the source secret."""
    if not isinstance(session_secret, str) or not session_secret:
        raise RuntimeError("SESSION_SECRET is required to configure the Hermes API server")
    return hmac.new(
        session_secret.encode("utf-8"), HERMES_HMAC_CONTEXT, hashlib.sha256
    ).hexdigest()


def _managed_value(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"required managed environment variable {name} is missing")
    return value


def approved_library_path(
    env: Mapping[str, str], *, gcc_output: str | None = None
) -> str:
    """Return only Replit's approved Python libraries and gcc's libatomic directory."""
    managed = env.get("REPLIT_PYTHON_LD_LIBRARY_PATH", "").strip()
    if gcc_output is None:
        gcc = shutil.which("gcc")
        if not gcc:
            raise RuntimeError("gcc is required to locate the approved libatomic runtime")
        try:
            result = subprocess.run(
                [gcc, "-print-file-name=libatomic.so.1"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("could not locate gcc's libatomic.so.1") from exc
        gcc_output = result.stdout.strip()
    atomic = Path(gcc_output)
    if not atomic.is_absolute() or atomic.name != "libatomic.so.1":
        raise RuntimeError("gcc did not return an absolute libatomic.so.1 path")
    paths: list[str] = []
    if managed:
        paths.extend(item for item in managed.split(os.pathsep) if item)
    paths.append(str(atomic.parent))
    # Preserve order but avoid duplicate search directories.
    return os.pathsep.join(dict.fromkeys(paths))


def build_gateway_env(
    source_env: Mapping[str, str],
    *,
    home: Path,
    python_bin: Path,
    gcc_output: str | None = None,
) -> dict[str, str]:
    """Build a strict, allowlisted environment for Hermes (not for the bot)."""
    anthropic_key = _managed_value(
        source_env, "AI_INTEGRATIONS_ANTHROPIC_API_KEY"
    )
    anthropic_base = _managed_value(
        source_env, "AI_INTEGRATIONS_ANTHROPIC_BASE_URL"
    )
    api_key = derive_api_server_key(_managed_value(source_env, "SESSION_SECRET"))

    isolated_home = home / "home"
    isolated_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path_entries = [str(home / "bin"), str(python_bin.parent), "/usr/bin", "/bin"]
    minimal_path = os.pathsep.join(dict.fromkeys(path_entries))
    lang = source_env.get("LANG", "C.UTF-8")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", lang):
        lang = "C.UTF-8"

    return {
        "HOME": str(isolated_home),
        "HERMES_HOME": str(home),
        "PATH": minimal_path,
        "LANG": lang,
        "LD_LIBRARY_PATH": approved_library_path(source_env, gcc_output=gcc_output),
        "ANTHROPIC_API_KEY": anthropic_key,
        "ANTHROPIC_BASE_URL": anthropic_base,
        "API_SERVER_KEY": api_key,
    }


def _yaml_load(path: Path) -> dict[str, Any]:
    try:
        from ruamel.yaml import YAML

        parsed = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except ImportError:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "the PM-selected Hermes environment must provide a YAML parser"
            ) from exc
        with path.open(encoding="utf-8") as stream:
            parsed = yaml.safe_load(stream)
    except Exception as exc:
        raise RuntimeError(f"cannot parse Hermes runtime config {path}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Hermes runtime config must be a YAML mapping: {path}")
    return parsed


def _known_builtin_toolsets() -> set[str]:
    """Resolve toolsets from the pinned source so newly added capabilities fail closed."""
    agent_root = project_root() / ".hermes-agent"
    if not agent_root.is_dir():
        raise RuntimeError("the pinned Hermes source is required to validate toolsets")
    source_path = str(agent_root)
    sys.path.insert(0, source_path)
    try:
        import toolsets

        loaded_from = Path(toolsets.__file__).resolve()
        if not loaded_from.is_relative_to(agent_root.resolve()):
            raise RuntimeError("Hermes toolset registry did not load from the pinned checkout")
        return set(toolsets.TOOLSETS)
    except (ImportError, AttributeError, OSError) as exc:
        raise RuntimeError("cannot inspect built-in Hermes toolsets") from exc
    finally:
        try:
            sys.path.remove(source_path)
        except ValueError:
            pass


def validate_tool_config(config: Mapping[str, Any]) -> None:
    """Reject config drift that could expose tools, adapters, or approval paths."""
    if config.get("tools") != {"tool_search": {"enabled": False}}:
        raise RuntimeError("Hermes automatic tool discovery must remain disabled")
    if config.get("providers") != {"anthropic": {"request_timeout_seconds": 90}}:
        raise RuntimeError("Hermes provider timeout must remain bounded at 90 seconds")
    model = config.get("model")
    if not isinstance(model, dict) or any(
        model.get(key) != value
        for key, value in {
            "provider": "anthropic",
            "default": "claude-sonnet-5",
            "max_tokens": 8192,
        }.items()
    ):
        raise RuntimeError("Hermes model configuration differs from the approved policy")

    agent = config.get("agent")
    if not isinstance(agent, dict) or agent.get("max_turns") != 25:
        raise RuntimeError("Hermes max_turns must remain 25")
    allowed_toolsets = {"todo", "memory"}
    disabled_toolsets = agent.get("disabled_toolsets")
    required_disabled = _known_builtin_toolsets() - allowed_toolsets
    if (
        not isinstance(disabled_toolsets, list)
        or disabled_toolsets != sorted(required_disabled)
    ):
        raise RuntimeError(
            "Hermes agent.disabled_toolsets must globally suppress every built-in "
            "toolset except todo and memory"
        )

    expected_tools = {"api_server": ["todo", "memory"], "cli": ["todo", "memory"]}
    if config.get("platform_toolsets") != expected_tools:
        raise RuntimeError(
            "Hermes toolsets are not the strict api_server/cli todo+memory allowlist"
        )

    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        raise RuntimeError("Hermes platform configuration is missing")
    api = platforms.get("api_server")
    if not isinstance(api, dict) or api.get("enabled") is not True:
        raise RuntimeError("Hermes API server must be the only enabled platform")
    extra = api.get("extra")
    if extra != {
        "host": "127.0.0.1",
        "port": 8642,
        "direct_model_requests": True,
    }:
        raise RuntimeError("Hermes API server must remain loopback-only on port 8642")
    for name in MESSAGE_ADAPTERS:
        adapter = platforms.get(name)
        if not isinstance(adapter, dict) or adapter.get("enabled") is not False:
            raise RuntimeError(f"Hermes messaging adapter {name} must remain disabled")
    if set(platforms) != {"api_server", *MESSAGE_ADAPTERS}:
        raise RuntimeError("Hermes platform list changed; refusing an unreviewed adapter")

    terminal = config.get("terminal")
    if not isinstance(terminal, dict) or any(
        terminal.get(key) != value
        for key, value in {
            "backend": "local",
            "cwd": ".hermes-home/sandbox",
            "home_mode": "profile",
        }.items()
    ):
        raise RuntimeError("Hermes terminal policy changed; refusing to start")

    approvals = config.get("approvals")
    if not isinstance(approvals, dict) or any(
        approvals.get(key) != "deny"
        for key in ("cron_mode", "single_query_mode", "unattended_mode")
    ):
        raise RuntimeError("Hermes unattended approval policy must remain deny")
    if approvals.get("mode") != "manual":
        raise RuntimeError("Hermes dangerous-command approvals must remain manual")

    cron = config.get("cron")
    if not isinstance(cron, dict) or cron.get("allow_agent_scheduling") is not False:
        raise RuntimeError("Hermes cron scheduling must remain disabled")
    skills = config.get("skills")
    if not isinstance(skills, dict) or skills.get("creation_nudge_interval") != 0:
        raise RuntimeError("Hermes skill nudges must remain disabled")
    curator = config.get("curator")
    if not isinstance(curator, dict) or curator.get("enabled") is not False:
        raise RuntimeError("Hermes skill curator must remain disabled")
    plugins = config.get("plugins")
    if not isinstance(plugins, dict) or plugins.get("enabled") != []:
        raise RuntimeError("Hermes plugins must remain disabled")
    if config.get("mcp_servers") != {}:
        raise RuntimeError("Hermes MCP servers must remain disabled")


def _active_dotenv_assignments(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"cannot inspect dotenv file {path}") from exc
    return [
        f"{path}:{number}"
        for number, line in enumerate(lines, 1)
        if re.match(r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=", line)
    ]


def reject_dotenv_overrides(root: Path, home: Path) -> None:
    """Hermes may load only empty/comment-only dotenv files in this deployment."""
    home_env = home / ".env"
    if home_env.is_file() and _active_dotenv_assignments(home_env):
        template = root / ".hermes-agent" / ".env.example"
        try:
            is_installer_template = (
                template.is_file() and home_env.read_bytes() == template.read_bytes()
            )
        except OSError as exc:
            raise RuntimeError(f"cannot inspect Hermes dotenv file {home_env}") from exc
        if is_installer_template:
            # The official installer seeds a sample .env with active, non-secret
            # defaults. This private home accepts no dotenv values, so remove
            # only that byte-for-byte installer template; preserve and reject
            # any custom dotenv file instead of silently clobbering it.
            _atomic_write(home_env, b"", 0o600)

    files = (
        home / ".op.env",
        root / ".hermes-agent" / ".env",
        root / ".hermes-agent" / ".op.env",
        home_env,
    )
    assignments = [
        assignment for path in files for assignment in _active_dotenv_assignments(path)
    ]
    if assignments:
        raise RuntimeError(
            "Hermes dotenv overrides are disabled; remove assignments from "
            + ", ".join(assignments)
        )


def ensure_home_config(root: Path, home: Path) -> Path:
    source = root / "hermes" / "config.yaml"
    target = home / "config.yaml"
    if not source.is_file():
        raise RuntimeError(f"required Hermes policy config is missing: {source}")
    policy = _yaml_load(source)
    validate_tool_config(policy)

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    (home / "sandbox").mkdir(mode=0o700, exist_ok=True)
    (home / "bin").mkdir(mode=0o700, exist_ok=True)
    if not target.exists():
        _atomic_write(target, source.read_bytes(), 0o600)
    else:
        installed = _yaml_load(target)
        try:
            validate_tool_config(installed)
        except RuntimeError:
            installed = None
        if installed != policy:
            # First installation leaves Hermes's stock example in its home.
            # It is safe to replace only an untouched copy of that upstream
            # template; all other drift is an explicit fail-closed error.
            template = root / ".hermes-agent" / "cli-config.yaml.example"
            if not (
                template.is_file()
                and target.read_bytes() == template.read_bytes()
            ):
                raise RuntimeError(
                    f"Hermes runtime config drifted from the reviewed policy: {target}"
                )
            _atomic_write(target, source.read_bytes(), 0o600)
    installed = _yaml_load(target)
    validate_tool_config(installed)
    if installed != policy:
        raise RuntimeError(
            f"Hermes runtime config drifted from the reviewed policy: {target}"
        )
    reject_dotenv_overrides(root, home)
    return target


def _atomic_write(path: Path, contents: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def resolve_project_python(root: Path, home: Path) -> Path:
    """Ask the pinned PM selector for the project environment, never the legacy venv."""
    _verify_checkout(root)
    agent_root = root / ".hermes-agent"
    previous_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(home)
    sys.path.insert(0, str(agent_root))
    try:
        from pm.environments import project_python

        # Preserve the venv pathname: resolving its executable symlink selects
        # the base interpreter and drops the venv's installed packages.
        selected = Path(project_python(agent_root)).absolute()
    except Exception as exc:
        raise RuntimeError("PM could not select Hermes's project Python environment") from exc
    finally:
        try:
            sys.path.remove(str(agent_root))
        except ValueError:
            pass
        if previous_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous_home

    obsolete = (agent_root / "venv" / "bin" / "python").absolute()
    if selected == obsolete:
        raise RuntimeError("PM selected the obsolete .hermes-agent/venv interpreter")
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise RuntimeError(f"PM-selected Hermes Python is unavailable: {selected}")
    return selected


def _verify_selected_environment(python_bin: Path, env: Mapping[str, str], cwd: Path) -> None:
    try:
        result = subprocess.run(
            [
                str(python_bin),
                "-c",
                "import sys, anthropic, hermes_cli.main, gateway.run; "
                "assert sys.version_info[:3] == (3, 14, 7), sys.version",
            ],
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("PM-selected Hermes environment failed its import check") from exc
    if result.returncode != 0:
        raise RuntimeError(
            "PM-selected Hermes environment cannot import the pinned gateway "
            f"(exit {result.returncode})"
        )


def _verify_checkout(root: Path) -> None:
    agent_root = root / ".hermes-agent"
    if not agent_root.is_dir():
        raise RuntimeError(f"Hermes checkout is missing: {agent_root}")
    try:
        commit = subprocess.run(
            ["git", "-C", str(agent_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("cannot verify the Hermes source checkout") from exc
    if commit != PINNED_COMMIT:
        raise RuntimeError(
            f"Hermes checkout must remain pinned at {PINNED_COMMIT}; found {commit}"
        )
    try:
        status = subprocess.run(
            ["git", "-C", str(agent_root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("cannot verify Hermes source checkout cleanliness") from exc
    if status.strip():
        raise RuntimeError("Hermes source checkout has local changes; refusing unreviewed code")


def check_install(root: Path | None = None) -> Path:
    """Validate the checkout, policy config and PM-selected runtime without secrets."""
    root = (root or project_root()).resolve()
    _verify_checkout(root)
    home = root / ".hermes-home"
    ensure_home_config(root, home)
    python_bin = resolve_project_python(root, home)
    sandbox = home / "sandbox"
    import_env = {
        "HOME": str(home / "home"),
        "HERMES_HOME": str(home),
        "PATH": os.pathsep.join(
            [str(home / "bin"), str(python_bin.parent), "/usr/bin", "/bin"]
        ),
        "LANG": "C.UTF-8",
        "LD_LIBRARY_PATH": approved_library_path(os.environ),
    }
    _verify_selected_environment(python_bin, import_env, sandbox)
    return python_bin


def write_ready_marker(root: Path | None = None) -> Path:
    root = (root or project_root()).resolve()
    python_bin = check_install(root)
    home = root / ".hermes-home"
    config_hash = hashlib.sha256((root / "hermes" / "config.yaml").read_bytes()).hexdigest()
    marker = {
        "schema": 1,
        "commit": PINNED_COMMIT,
        "project_python": str(python_bin),
        "config_sha256": config_hash,
    }
    marker_path = home / "runtime-ready.json"
    encoded = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if not marker_path.exists() or marker_path.read_bytes() != encoded:
        _atomic_write(marker_path, encoded, 0o600)
    return python_bin


def launch_gateway(root: Path | None = None) -> None:
    root = (root or project_root()).resolve()
    agent_root = root / ".hermes-agent"
    home = root / ".hermes-home"
    _verify_checkout(root)
    ensure_home_config(root, home)
    python_bin = resolve_project_python(root, home)
    sandbox = home / "sandbox"
    source_env = os.environ
    runtime_env = build_gateway_env(
        source_env, home=home, python_bin=python_bin
    )
    _verify_selected_environment(python_bin, runtime_env, sandbox)
    argv = [
        str(python_bin),
        "-u",
        "-m",
        "hermes_cli.main",
        "gateway",
        "run",
    ]
    os.chdir(sandbox)
    os.execve(str(python_bin), argv, runtime_env)


class _NpmRelayHandler(http.server.BaseHTTPRequestHandler):
    archive: bytes = b""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != NPM_TARBALL_PATH:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.archive)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(self.archive)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != NPM_TARBALL_PATH:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.archive)))
        self.end_headers()

    def log_message(self, _format: str, *args: Any) -> None:
        return


def serve_npm_archive(archive_path: Path, port_file: Path) -> None:
    archive = archive_path.read_bytes()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != NPM_TARBALL_SHA256:
        raise RuntimeError("cached npm-12.0.2 tarball failed SHA256 verification")
    handler = type("CachedNpmRelayHandler", (_NpmRelayHandler,), {"archive": archive})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port_file.write_text(str(server.server_address[1]), encoding="ascii")

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        port_file.unlink(missing_ok=True)


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("gateway")
    subparsers.add_parser("check")
    subparsers.add_parser("prepare")
    relay = subparsers.add_parser("npm-relay")
    relay.add_argument("--archive", type=Path, required=True)
    relay.add_argument("--port-file", type=Path, required=True)
    resolve = subparsers.add_parser("resolve-python")
    resolve.add_argument("--root", type=Path, default=project_root())
    resolve.add_argument("--home", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "gateway":
            launch_gateway()
        elif args.command == "npm-relay":
            serve_npm_archive(args.archive, args.port_file)
        elif args.command == "check":
            print(check_install())
        elif args.command == "prepare":
            print(write_ready_marker())
        else:
            root = args.root.resolve()
            home = (args.home or root / ".hermes-home").resolve()
            print(resolve_project_python(root, home))
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"[hermes-runtime] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())