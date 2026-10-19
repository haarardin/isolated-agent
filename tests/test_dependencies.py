"""Regression tests for generic dependency and Agent Tool generation."""
import importlib.util
import json
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
            bindings = json.loads((out / "tool-lsp.json").read_text())
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0]["adapter"], "serena")
            self.assertEqual(bindings[0]["servers"], {"cpp": "/usr/bin/clangd"})
            self.assertEqual(bindings[0]["python"], "/opt/agent-tools/serena/bin/python")
            self.assertEqual(bindings[0]["state"], "/root/.serena")

    def test_warn_when_serena_cannot_find_locally_installed_clangd(self):
        cfg = deps.parse(ROOT / "dependencies/examples/go-serena.toml")
        self.assertEqual(deps.lsp_configuration_warnings(cfg), [])
        cfg["agent_tools"][0].pop("lsp")
        warnings = deps.lsp_configuration_warnings(cfg)
        self.assertEqual(len(warnings), 1)
        self.assertIn("[agent_tools.lsp]", warnings[0])
        self.assertIn("Error extracting archive", warnings[0])
        # No false warning when another project does not install clangd.
        cfg["apt"]["packages"].remove("clangd")
        self.assertEqual(deps.lsp_configuration_warnings(cfg), [])
        # A disabled Serena tool needs no runtime LSP mapping.
        cfg["apt"]["packages"].append("clangd")
        cfg["agent_tools"][0]["enabled"] = False
        self.assertEqual(deps.lsp_configuration_warnings(cfg), [])

    def test_invalid_lsp_bindings_are_rejected(self):
        good = {"id": "serena", "placement": "embedded", "kind": "mcp",
                "integration": {"transport": "stdio", "command": "/opt/serena/bin/serena"},
                "state": {"base": "./volumes/serena", "target": "/root/.serena"},
                "lsp": {"adapter": "serena", "servers": {"cpp": "/usr/bin/clangd"}}}
        for update in (
            {"lsp": {"adapter": "unknown", "servers": {"cpp": "/usr/bin/clangd"}}},
            {"lsp": {"adapter": "serena", "servers": {"cpp": "clangd"}}},
            {"lsp": {"adapter": "serena", "servers": {"cpp": "/usr/bin/../clangd"}}},
            {"lsp": {"adapter": "serena", "servers": {"cpp": "/usr/bin/clangd; bad"}}},
            {"state": {"base": "./volumes/serena", "target": "/tmp/serena"}},
            {"placement": "external"},
        ):
            cfg = {"apt": {"packages": []}, "agent_tools": [{**good, **update}]}
            with tempfile.TemporaryDirectory() as td:
                file = Path(td) / "invalid.toml"
                # Test parse validation against temporary TOML through
                # python's installed tomli-writer-free deterministic fixture.
                fixture = """
[[agent_tools]]
id = "serena"
placement = "%s"
kind = "mcp"
[agent_tools.state]
base = "%s"
target = "%s"
[agent_tools.lsp]
adapter = "%s"
servers = { cpp = "%s" }
[agent_tools.integration]
transport = "stdio"
command = "/opt/serena/bin/serena"
""" % (
                    cfg["agent_tools"][0]["placement"],
                    cfg["agent_tools"][0]["state"]["base"],
                    cfg["agent_tools"][0]["state"]["target"],
                    cfg["agent_tools"][0]["lsp"]["adapter"],
                    cfg["agent_tools"][0]["lsp"]["servers"]["cpp"],
                )
                file.write_text(fixture)
                with self.assertRaises(ValueError):
                    deps.parse(file)

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
                # Regression: no sidecars + embedded persistent state used to
                # append "{}" to the last volume entry, producing invalid YAML.
                self.assertNotIn(":rw\" {}", compose)
                self.assertTrue(compose.endswith(":rw\"\n"))
                self.assertNotIn("services: {}", compose)

    def test_serena_with_state_but_no_sidecar_ends_in_valid_volume(self):
        cfg = deps.parse(ROOT / "dependencies/examples/go-serena.toml")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            deps.generate(cfg, out)
            compose = (out / "compose.tools.yaml").read_text()
            self.assertIn("services:\n  agent:\n    volumes:\n", compose)
            self.assertIn("/root/.serena:rw", compose)
            self.assertEqual(len(compose.splitlines()), 5)
            self.assertNotIn("{} ", compose)
            self.assertTrue(compose.endswith(":rw\"\n"))

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
