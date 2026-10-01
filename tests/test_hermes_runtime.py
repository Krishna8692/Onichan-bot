import copy
import hashlib
import hmac
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from scripts import hermes_runtime
from scripts.hermes_supervisor import HermesSupervisor, production_services


ROOT = Path(__file__).resolve().parents[1]


class HermesRuntimeTests(unittest.TestCase):
    def test_api_server_key_matches_bot_hmac_context(self):
        secret = "unit-test-session-secret"
        expected = hmac.new(
            secret.encode(),
            b"onichan-hermes-api-v1",
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(hermes_runtime.derive_api_server_key(secret), expected)
        self.assertNotEqual(hermes_runtime.derive_api_server_key("another-secret"), expected)

    def test_gateway_environment_is_a_strict_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / ".hermes-home"
            python_bin = Path(temporary) / "venv" / "bin" / "python"
            source = {
                "AI_INTEGRATIONS_ANTHROPIC_API_KEY": "managed-key",
                "AI_INTEGRATIONS_ANTHROPIC_BASE_URL": "https://managed.example/v1",
                "SESSION_SECRET": "session-value",
                "BOT_TOKEN": "bot-token",
                "OWNER_ID": "784321",
                "REPLIT_TOKEN": "replit-token",
                "REPLIT_PYTHON_LD_LIBRARY_PATH": "/nix/python/lib",
                "LD_LIBRARY_PATH": "/unapproved/from-parent",
                "PATH": "/unapproved/parent-path",
                "LANG": "en_US.UTF-8",
                "RANDOM_SECRET": "must-not-leak",
            }
            env = hermes_runtime.build_gateway_env(
                source,
                home=home,
                python_bin=python_bin,
                gcc_output="/nix/gcc/lib/libatomic.so.1",
            )
        self.assertEqual(
            set(env),
            {
                "HOME",
                "HERMES_HOME",
                "PATH",
                "LANG",
                "LD_LIBRARY_PATH",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_BASE_URL",
                "API_SERVER_KEY",
            },
        )
        self.assertEqual(env["ANTHROPIC_API_KEY"], "managed-key")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://managed.example/v1")
        self.assertEqual(
            env["LD_LIBRARY_PATH"],
            os.pathsep.join(["/nix/python/lib", "/nix/gcc/lib"]),
        )
        self.assertNotIn("unapproved/from-parent", env["LD_LIBRARY_PATH"])
        self.assertNotIn("BOT_TOKEN", env)
        self.assertNotIn("OWNER_ID", env)
        self.assertNotIn("SESSION_SECRET", env)
        self.assertNotIn("REPLIT_TOKEN", env)
        self.assertNotIn("RANDOM_SECRET", env)
        self.assertNotIn("managed-key", repr(env["API_SERVER_KEY"]))

    def test_gateway_environment_fails_explicitly_on_missing_managed_values(self):
        required = {
            "AI_INTEGRATIONS_ANTHROPIC_API_KEY": "key",
            "AI_INTEGRATIONS_ANTHROPIC_BASE_URL": "https://managed.example",
            "SESSION_SECRET": "secret",
        }
        for missing in required:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                values = dict(required)
                del values[missing]
                with self.assertRaisesRegex(RuntimeError, missing):
                    hermes_runtime.build_gateway_env(
                        values,
                        home=Path(temporary) / "home",
                        python_bin=Path(temporary) / "python",
                        gcc_output="/nix/gcc/lib/libatomic.so.1",
                    )

    def test_checked_in_tool_policy_is_strict_and_fails_closed(self):
        config = hermes_runtime._yaml_load(ROOT / "hermes" / "config.yaml")
        hermes_runtime.validate_tool_config(config)
        self.assertEqual(
            config["platform_toolsets"],
            {"api_server": ["todo", "memory"], "cli": ["todo", "memory"]},
        )

        source_root = str(ROOT / ".hermes-agent")
        sys.path.insert(0, source_root)
        try:
            import model_tools

            for platform, toolsets in config["platform_toolsets"].items():
                with self.subTest(platform=platform):
                    effective = model_tools._select_tool_names(
                        toolsets,
                        config["agent"]["disabled_toolsets"],
                        quiet_mode=True,
                    )
                    self.assertEqual(effective, {"todo_list", "memory"})
                    with patch.dict(
                        os.environ, {"HERMES_HOME": str(ROOT / ".hermes-home")}
                    ):
                        definitions = model_tools.get_tool_definitions(
                            enabled_toolsets=toolsets,
                            disabled_toolsets=config["agent"]["disabled_toolsets"],
                            quiet_mode=True,
                        )
                    function_names = {
                        definition["function"]["name"] for definition in definitions
                    }
                    self.assertEqual(function_names, {"todo_list", "memory"})
        finally:
            sys.path.remove(source_root)

        altered_tools = copy.deepcopy(config)
        altered_tools["platform_toolsets"]["api_server"].append("terminal")
        with self.assertRaisesRegex(RuntimeError, "toolsets"):
            hermes_runtime.validate_tool_config(altered_tools)

        altered_global_denylist = copy.deepcopy(config)
        altered_global_denylist["agent"]["disabled_toolsets"].remove("terminal")
        with self.assertRaisesRegex(RuntimeError, "disabled_toolsets"):
            hermes_runtime.validate_tool_config(altered_global_denylist)

        altered_adapter = copy.deepcopy(config)
        altered_adapter["platforms"]["telegram"]["enabled"] = True
        with self.assertRaisesRegex(RuntimeError, "telegram"):
            hermes_runtime.validate_tool_config(altered_adapter)

        altered_terminal = copy.deepcopy(config)
        altered_terminal["terminal"]["cwd"] = "."
        with self.assertRaisesRegex(RuntimeError, "terminal policy"):
            hermes_runtime.validate_tool_config(altered_terminal)

    def test_project_python_keeps_the_pm_venv_symlink_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agent_root = root / ".hermes-agent"
            selected = root / ".hermes-home" / "installs" / "env" / "venv" / "bin" / "python"
            selected.parent.mkdir(parents=True)
            selected.symlink_to(sys.executable)
            fake_pm = ModuleType("pm")
            fake_pm.__path__ = []
            fake_environments = ModuleType("pm.environments")
            fake_environments.project_python = lambda _root: selected
            fake_pm.environments = fake_environments

            with patch.dict(
                sys.modules,
                {"pm": fake_pm, "pm.environments": fake_environments},
            ), patch.object(hermes_runtime, "_verify_checkout"):
                resolved = hermes_runtime.resolve_project_python(root, root / ".hermes-home")

            self.assertEqual(resolved, selected.absolute())
            self.assertNotEqual(resolved, selected.resolve())
            self.assertTrue(resolved.is_file())


class FakeProcess:
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None
        self.signals = []
        self.waited = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waited = True
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = -sig


class HermesSupervisorTests(unittest.TestCase):
    def test_services_restart_independently_with_backoff(self):
        processes = []
        spawn_options = []

        def popen(command, **kwargs):
            process = FakeProcess(len(processes) + 100)
            processes.append((command, process))
            spawn_options.append(kwargs)
            return process

        supervisor = HermesSupervisor(
            [("bot", ["bash", "run-bot.sh"]), ("hermes", ["bash", "run-hermes.sh"])],
            popen=popen,
            poll_interval=0.1,
            backoff_initial=1,
            backoff_max=8,
        )
        supervisor.tick(now=0)
        bot, hermes = processes[0][1], processes[1][1]
        self.assertTrue(all(item == {"start_new_session": True} for item in spawn_options))

        bot.returncode = 7
        supervisor.tick(now=0.5)
        self.assertIsNone(supervisor.services[0].process)
        self.assertIs(supervisor.services[1].process, hermes)
        self.assertEqual(supervisor.services[0].restart_at, 1.5)

        supervisor.tick(now=1.49)
        self.assertEqual(len(processes), 2)
        supervisor.tick(now=1.5)
        self.assertEqual(len(processes), 3)
        self.assertIs(supervisor.services[1].process, hermes)

    def test_shutdown_signals_complete_process_groups_gracefully(self):
        processes = []
        sent = []

        def popen(_command, **_kwargs):
            process = FakeProcess(len(processes) + 10)
            processes.append(process)
            return process

        def killpg(pid, sig):
            sent.append((pid, sig))
            for process in processes:
                if process.pid == pid and sig == signal.SIGTERM:
                    process.returncode = -sig

        supervisor = HermesSupervisor(
            [("bot", ["run-bot.sh"]), ("hermes", ["run-hermes.sh"])],
            popen=popen,
            killpg=killpg,
            shutdown_grace=1,
        )
        supervisor.tick(now=0)
        supervisor.stop_all()
        self.assertEqual(
            sent,
            [(10, signal.SIGTERM), (11, signal.SIGTERM)],
        )
        self.assertTrue(all(process.waited is False for process in processes))
        self.assertTrue(all(service.process is None for service in supervisor.services))

    def test_production_children_are_not_recursive_supervisors(self):
        services = production_services(ROOT)
        self.assertEqual({name for name, _ in services}, {"bot", "hermes"})
        self.assertIn("run-bot.sh", services[0][1][-1])
        self.assertIn("run-hermes.sh", services[1][1][-1])
        self.assertNotIn("hermes_supervisor.py", " ".join(arg for _, cmd in services for arg in cmd))


if __name__ == "__main__":
    unittest.main()