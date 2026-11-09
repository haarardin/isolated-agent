"""Regression tests for configuration-selected container agent dispatch."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import tomllib
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_dispatch", ROOT / "scripts/agent.py")
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class AgentDispatchTests(unittest.TestCase):
    def test_known_runtimes_use_explicit_argv(self):
        self.assertEqual(agent.select_agent("codex"), ["codex"])
        self.assertEqual(agent.select_agent("opencode"),
                         ["/usr/local/bin/isolated-agent-opencode"])

    def test_unknown_or_unsafe_runtime_fails_closed(self):
        for runtime in ("", "claude", "CODEX", "../codex",
                        "codex;id", "codex $(id)", "opencode\nother"):
            with self.subTest(runtime=runtime), self.assertRaises(ValueError):
                agent.select_agent(runtime)

    def test_invalid_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "agents.json"
            for contents in ('[]', '{"codex": []}', '{"codex": "codex"}',
                             '{"codex": ["codex", 123]}',
                             '{"codex": ["codex", "bad\\u0000arg"]}',
                             '{"codex": [null]}'):
                registry.write_text(contents)
                with self.subTest(contents=contents), self.assertRaises(ValueError):
                    agent.select_agent("codex", registry)

    def test_wrapper_passes_exact_argv_without_shell_evaluation(self):
        for runtime, binary in (
            ("codex", "codex"),
            ("opencode", "/usr/local/bin/isolated-agent-opencode"),
        ):
            with self.subTest(runtime=runtime), \
                 mock.patch.dict(agent.os.environ, {"AGENT_RUNTIME": runtime}, clear=True), \
                 mock.patch.object(agent.os, "execvp") as execute, \
                 mock.patch.object(agent, "enabled_runtime", return_value=True):
                self.assertEqual(agent.main(["run", "message;touch /tmp/unsafe"]), 0)
                execute.assert_called_once_with(
                    "bash",
                    ["bash", str(ROOT / "scripts/compose.sh"), "exec", "agent",
                     binary, "run", "message;touch /tmp/unsafe"],
                )

    def test_invalid_selection_does_not_call_compose(self):
        with mock.patch.dict(agent.os.environ, {"AGENT_RUNTIME": "bad value"}, clear=True), \
             mock.patch.object(agent.os, "execvp") as execute, \
                 mock.patch.object(agent, "enabled_runtime", return_value=True):
            self.assertEqual(agent.main(), 2)
            execute.assert_not_called()

    def test_manifest_enabled_runtime_follows_enabled_flags(self):
        # Test both settings without assuming the developer's checked-out
        # dependencies.toml is still in the default Codex-only state.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dependencies = root / "dependencies"
            dependencies.mkdir()
            manifest = dependencies / "dependencies.toml"
            for codex_enabled, opencode_enabled in (
                (True, False), (False, True), (True, True), (False, False)
            ):
                with self.subTest(codex=codex_enabled, opencode=opencode_enabled):
                    manifest.write_text(
                        '[[agents]]\nid = "codex"\nenabled = ' +
                        str(codex_enabled).lower() +
                        '\n[[agents]]\nid = "opencode"\nenabled = ' +
                        str(opencode_enabled).lower() + '\n'
                    )
                    with mock.patch.object(agent, "ROOT", root):
                        self.assertEqual(agent.enabled_runtime("codex"), codex_enabled)
                        self.assertEqual(agent.enabled_runtime("opencode"), opencode_enabled)

    def test_make_agent_dispatches_each_runtime_without_podman(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "podman-compose"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            fake.chmod(0o755)
            env = {**os.environ,
                   "PATH": td + os.pathsep + os.environ.get("PATH", ""),
                   "COMPOSE_PROJECT_NAME": "agent-dispatch-test",
                   "AGENT_NETWORK_NAME": "agent-dispatch-test_net"}
            # Verify whichever agents are enabled in this checkout. The
            # developer may run the suite with Codex-only, OpenCode-only,
            # both, or both disabled; none should require editing tests.
            config = tomllib.loads(
                (ROOT / "dependencies/dependencies.toml").read_text()
            )
            enabled = {a["id"]: a["enabled"] for a in config["agents"]}
            expected = {
                "codex": "codex",
                "opencode": "/usr/local/bin/isolated-agent-opencode",
            }
            for runtime, executable in expected.items():
                with self.subTest(runtime=runtime, enabled=enabled[runtime]):
                    result = subprocess.run(
                        ["make", "--no-print-directory", "agent",
                         f"AGENT_RUNTIME={runtime}"],
                        cwd=ROOT, env=env, capture_output=True,
                        text=True, check=False,
                    )
                    if enabled[runtime]:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(
                            result.stdout.splitlines(),
                            ["exec", "agent", executable],
                        )
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("disabled in [[agents]]", result.stderr)
                        self.assertNotIn("exec", result.stdout)

            bad = subprocess.run(
                ["make", "--no-print-directory", "agent", "AGENT_RUNTIME=codex;id"],
                cwd=ROOT, env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("invalid AGENT_RUNTIME", bad.stderr)
            self.assertNotIn("exec", bad.stdout)


if __name__ == "__main__":
    unittest.main()
