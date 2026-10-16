"""Regression tests for generic dependency and Agent Tool generation."""
import importlib.util
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("deps", ROOT / "scripts/dependencies.py")
deps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deps)


class DependencyTests(unittest.TestCase):
    def test_default_has_no_language_sdk(self):
        cfg = deps.parse()
        self.assertEqual(cfg["apt"]["packages"], [])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            manifest = deps.generate(cfg, out)
            image = (out / "Containerfile.dependencies").read_text()
            self.assertIn("ARG CODEX_IMAGE=", image)
            self.assertNotIn("go install", image)
            self.assertEqual(manifest["sidecars"], [])
            self.assertIn("services: {}", (out / "compose.tools.yaml").read_text())
            self.assertEqual(tomllib.loads((out / "codex-mcp.toml").read_text()), {})

    def test_optional_go_and_serena(self):
        cfg = deps.parse(ROOT / "dependencies/examples/go-serena.toml")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            deps.generate(cfg, out)
            img = (out / "Containerfile.dependencies").read_text()
            mcp = tomllib.loads((out / "codex-mcp.toml").read_text())
            self.assertIn("install-go.sh", img)
            self.assertIn("serena-agent==1.7.0", img)
            self.assertIn("gopls@", img)
            self.assertEqual(mcp["mcp_servers"]["serena"]["command"],
                             "/opt/agent-tools/serena/bin/serena")

    def test_generic_http_sidecar_and_external_tool(self):
        cfg = {"apt": {"packages": []},
               "agent_tools": [
                   {"id": "index", "placement": "sidecar", "kind": "mcp",
                    "runtime": {"command": ["/opt/indexer/server"], "port": 8787},
                    "integration": {"transport": "http", "path": "/mcp"}},
                   {"id": "remote", "placement": "external", "kind": "mcp",
                    "integration": {"transport": "http", "url": "https://example.org/mcp"}}]}
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "project-a"}):
            out = Path(td)
            manifest = deps.generate(cfg, out)
            mcp = tomllib.loads((out / "codex-mcp.toml").read_text())["mcp_servers"]
            compose = (out / "compose.tools.yaml").read_text()
            self.assertEqual(manifest["sidecars"], ["index"])
            self.assertEqual(mcp["index"]["url"], "http://project-a-tool-index:8787/mcp")
            self.assertEqual(mcp["remote"]["url"], "https://example.org/mcp")
            self.assertIn("project-a-tool-index", compose)
            self.assertIn("read_only: true", compose)
            self.assertNotIn("privileged:", compose)
            self.assertIn("BASE_IMAGE", (out / "Containerfile.tool-index").read_text())

    def test_generic_embedded_tool_state_is_persistent_and_scoped(self):
        tool = {"id": "helper", "placement": "embedded", "kind": "mcp",
                "integration": {"transport": "stdio", "command": "/usr/local/bin/helper"},
                "state": {"base": "./volumes/tools/helper", "target": "/root/.helper"}}
        cfg = {"apt": {"packages": []}, "agent_tools": [tool]}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(deps, "ROOT", Path(td)), mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "example"}):
                deps.prepare_tool_state(cfg)
                state = deps.state_dir(tool, "example")
                self.assertTrue(state.is_dir())
                (state / "memory.txt").write_text("preserved")
                deps.prepare_tool_state(cfg)
                self.assertEqual((state / "memory.txt").read_text(), "preserved")
                out = Path(td) / ".generated"
                deps.generate(cfg, out)
                compose = (out / "compose.tools.yaml").read_text()
                self.assertIn("agent:", compose)
                self.assertIn("/root/.helper:rw", compose)

    def test_reject_apt_shell_injection(self):
        with self.assertRaises(ValueError):
            deps.check_step({"type": "apt", "packages": ["curl;rm -rf /"]}, "apt")

    def test_reject_traversal(self):
        with self.assertRaises(ValueError):
            deps.check_step({"type": "script", "file": "../outside.sh"}, "script")

    def test_reject_plain_http_for_external(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.toml"
            path.write_text('''[[agent_tools]]
id="bad"
placement="external"
kind="mcp"
[agent_tools.integration]
transport="http"
url="http://unsafe.example/mcp"
''')
            with self.assertRaises(ValueError):
                deps.parse(path)

    def test_disabled_tools_still_validated(self):
        deps.parse(ROOT / "dependencies/examples/mcp-http.toml")

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = deps.generate(deps.parse(), Path(a))
            second = deps.generate(deps.parse(), Path(b))
            self.assertEqual(first, second)
            self.assertEqual((Path(a) / "Containerfile.dependencies").read_bytes(),
                             (Path(b) / "Containerfile.dependencies").read_bytes())


if __name__ == "__main__":
    unittest.main()
