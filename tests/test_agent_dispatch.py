"""Regression tests for configuration-selected container agent dispatch."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
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
                 mock.patch.object(agent.os, "execvp") as execute:
                self.assertEqual(agent.main(["run", "message;touch /tmp/unsafe"]), 0)
                execute.assert_called_once_with(
                    "bash",
                    ["bash", str(ROOT / "scripts/compose.sh"), "exec", "agent",
                     binary, "run", "message;touch /tmp/unsafe"],
                )

    def test_invalid_selection_does_not_call_compose(self):
        with mock.patch.dict(agent.os.environ, {"AGENT_RUNTIME": "bad value"}, clear=True), \
             mock.patch.object(agent.os, "execvp") as execute:
            self.assertEqual(agent.main(), 2)
            execute.assert_not_called()

    def test_make_agent_dispatches_each_runtime_without_podman(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "podman-compose"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            fake.chmod(0o755)
            env = {**os.environ,
                   "PATH": td + os.pathsep + os.environ.get("PATH", ""),
                   "COMPOSE_PROJECT_NAME": "agent-dispatch-test",
                   "AGENT_NETWORK_NAME": "agent-dispatch-test_net"}
            for runtime, cmd in (("codex", "codex"),
                                 ("opencode", "/usr/local/bin/isolated-agent-opencode")):
                with self.subTest(runtime=runtime):
                    run = subprocess.run(
                        ["make", "--no-print-directory", "agent",
                         "AGENT_RUNTIME=" + runtime],
                        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(run.stdout.splitlines(), ["exec", "agent", cmd])

            bad = subprocess.run(
                ["make", "--no-print-directory", "agent", "AGENT_RUNTIME=codex;id"],
                cwd=ROOT, env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("invalid AGENT_RUNTIME", bad.stderr)
            self.assertNotIn("exec", bad.stdout)


if __name__ == "__main__":
    unittest.main()
