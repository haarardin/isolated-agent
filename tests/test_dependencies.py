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
            self.assertEqual(json.loads((out / "opencode-mcp.json").read_text()),
                             {"$schema": "https://opencode.ai/config.json", "mcp": {"servers": {}}})

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
            oc = json.loads((out / "opencode-mcp.json").read_text())
            self.assertEqual(oc["mcp"]["servers"]["serena"]["type"], "local")
            self.assertEqual(oc["mcp"]["servers"]["serena"]["command"][0],
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
            oc = json.loads((out / "opencode-mcp.json").read_text())["mcp"]["servers"]
            self.assertEqual(oc["index"], {"type": "remote", "url": "http://project-a-tool-index:8787/mcp"})
            self.assertEqual(oc["remote"], {"type": "remote", "url": "https://example.org/mcp"})
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

    def test_reject_state_targets_overlapping_protected_mounts(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "bad.toml"
            for target in ("/root/.codex", "/root", "/root/.codex/memories",
                           "/workspace", "/workspace/tools", "/tmp", "/run/cache",
                           "/root/.cache", "/root/.cache/go"):
                file.write_text(f"""
[[agent_tools]]
id = "helper"
kind = "mcp"
placement = "embedded"
[agent_tools.state]
base = "./volumes/helper"
target = "{target}"
[agent_tools.integration]
transport = "stdio"
command = "/usr/local/bin/helper"
""")
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "protected mount"):
                    deps.parse(file)

    def test_reject_state_targets_overlapping_other_tool_state(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "bad.toml"
            for target in ("/opt/state", "/opt/state/nested"):
                file.write_text(f"""
[[agent_tools]]
id = "first"
kind = "cli"
placement = "embedded"
[agent_tools.state]
base = "./volumes/first"
target = "/opt/state"
[[agent_tools]]
id = "second"
kind = "cli"
placement = "embedded"
[agent_tools.state]
base = "./volumes/second"
target = "{target}"
""")
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "overlaps tool first"):
                    deps.parse(file)

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

    def test_optional_opencode_cli_and_scoped_state(self):
        cfg = deps.parse()
        self.assertEqual([x["id"] for x in deps.enabled(cfg)], [])
        tool = next(x for x in cfg["agent_tools"] if x["id"] == "opencode")
        self.assertFalse(tool["enabled"])
        self.assertEqual(tool["state"]["target"], "/root/.isolated-opencode")
        tool["enabled"] = True
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "test-project"}):
            out = Path(td)
            deps.generate(cfg, out)
            self.assertIn("@opencode/cli@2.0.0", (out / "Containerfile.dependencies").read_text())
            compose = (out / "compose.tools.yaml").read_text()
            self.assertIn("/root/.isolated-opencode:rw", compose)
            readonly = str(ROOT / "config" / "opencode.jsonc") + ":/opt/isolated-agent/opencode-user.jsonc:ro"
            self.assertIn(readonly, compose)
            self.assertNotIn("opencode-user.jsonc:rw", compose)
            self.assertNotIn("privileged:", compose)
            self.assertNotIn("podman.sock", compose)
            self.assertNotIn("docker.sock", compose)

    def test_opencode_config_preflight_missing_symlink_and_valid(self):
        cfg = deps.parse()
        next(x for x in cfg["agent_tools"] if x["id"] == "opencode")["enabled"] = True
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_dir = root / "config"
            config_dir.mkdir()
            local = config_dir / "opencode.jsonc"
            with mock.patch.object(deps, "ROOT", root), \
                 mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "test-project"}):
                with self.assertRaisesRegex(ValueError, "config/opencode.example.jsonc"):
                    deps.prepare_tool_state(cfg)
                local.symlink_to("/etc/passwd")
                with self.assertRaisesRegex(ValueError, "config/opencode.example.jsonc"):
                    deps.prepare_tool_state(cfg)
                local.unlink()
                local.write_text('{"model": "proxyapi/qwen-flash"}')
                deps.prepare_tool_state(cfg)
                path = deps.state_dir(cfg["agent_tools"][0], "test-project")
                self.assertTrue(path.is_dir())
                # Local config remains on the host, outside generated state.
                self.assertFalse((path / "opencode.jsonc").exists())

    def test_opencode_config_is_not_baked_or_in_workspace(self):
        example = ROOT / "config" / "opencode.example.jsonc"
        data = json.loads(example.read_text())
        self.assertEqual(data["providers"]["proxyapi"]["settings"]["baseURL"],
                         "https://api.proxyapi.ru/v1")
        self.assertNotIn("apiKey", example.read_text())
        wrapper = (ROOT / "scripts/opencode.sh").read_text()
        self.assertIn('export OPENCODE_CONFIG="$config"', wrapper)
        self.assertIn("/opt/isolated-agent/opencode-user.jsonc", wrapper)
        image = (ROOT / "images/project/Containerfile").read_text()
        self.assertNotIn("config/opencode.jsonc", image)
        self.assertIn("/config/opencode.jsonc", (ROOT / ".gitignore").read_text())

    def test_documented_opencode_go_serena_example(self):
        cfg = deps.parse(ROOT / "dependencies/examples/go-opencode-serena.toml")
        self.assertEqual([x["id"] for x in deps.enabled(cfg)], ["opencode", "serena"])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            deps.generate(cfg, out)
            img = (out / "Containerfile.dependencies").read_text()
            self.assertIn("@opencode/cli@2.0.0", img)
            self.assertIn("gopls@v0.20.0", img)
            compose = (out / "compose.tools.yaml").read_text()
            self.assertIn("/root/.isolated-opencode:rw", compose)
            self.assertIn("/root/.serena:rw", compose)
            self.assertIn("/opt/isolated-agent/opencode-user.jsonc:ro", compose)
            mcp = json.loads((out / "opencode-mcp.json").read_text())
            self.assertIn("serena", mcp["mcp"]["servers"])
            self.assertEqual(mcp["mcp"]["servers"]["serena"]["type"], "local")

    def test_documented_proxyapi_config_examples(self):
        for name in ("opencode.example.jsonc", "opencode.proxyapi-multi.example.jsonc"):
            path = ROOT / "config" / name
            example = path.read_text()
            self.assertIn('"providers"', example)
            self.assertIn('"baseURL": "https://api.proxyapi.ru/v1"', example)
            self.assertIn('"env": ["PROXYAPI_API_KEY"]', example)
            self.assertNotIn("sk-", example)
            self.assertNotIn('"apiKey"', example)
            self.assertIn('"modelID"', example)
        # The default template is plain JSON; copy+edit with json.tool is valid.
        data = json.loads((ROOT / "config/opencode.example.jsonc").read_text())
        self.assertEqual(data["model"], "proxyapi/qwen-flash")

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = deps.generate(deps.parse(), Path(a))
            second = deps.generate(deps.parse(), Path(b))
            self.assertEqual(first, second)
            self.assertEqual((Path(a) / "Containerfile.dependencies").read_bytes(),
                             (Path(b) / "Containerfile.dependencies").read_bytes())
            self.assertEqual((Path(a) / "opencode-mcp.json").read_bytes(),
                             (Path(b) / "opencode-mcp.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
