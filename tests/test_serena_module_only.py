"""Regression: Serena is an opt-in Agent Tool, not a dedicated agent profile."""
import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dependencies", ROOT / "scripts/dependencies.py")
deps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deps)


class SerenaAsModuleTests(unittest.TestCase):
    def test_no_legacy_serena_image_compose_or_commands(self):
        for path in (
            "images/serena/Containerfile", "compose.serena.yaml",
            "scripts/serena-doctor.sh", "scripts/test-serena-static.sh",
            ".github/workflows/serena-static.yml",
        ):
            self.assertFalse((ROOT / path).exists(), path)
        mk = (ROOT / "Makefile").read_text()
        for goal in ("build-serena", "up-serena", "up-serena-example",
                     "codex-serena", "offline-serena", "serena-doctor",
                     "ensure-serena-image", "ps-serena"):
            self.assertNotIn("\n" + goal + ":", mk)
        self.assertNotIn("SERENA_STATE_VOLUME", mk)
        self.assertNotIn("SERENA_PROJECT_KEY", (ROOT / "images/project/entrypoint.sh").read_text())
        self.assertIn("ensure-images: ensure-project-image", mk)

    def test_serena_optional_generic_mcp_and_persistent_state(self):
        base = deps.parse(ROOT / "dependencies/dependencies.toml")
        self.assertFalse(any(x["id"] == "serena" for x in base.get("agent_tools", [])))
        example = deps.parse(ROOT / "dependencies/examples/go-serena.toml")
        tool = next(t for t in example["agent_tools"] if t["id"] == "serena")
        self.assertEqual(tool["kind"], "mcp")
        self.assertEqual(tool["placement"], "embedded")
        self.assertEqual(tool["state"]["target"], "/root/.serena")
        self.assertEqual(tool["integration"]["transport"], "stdio")
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch)
            deps.generate(base, output)
            no_tool = tomllib.loads((output / "codex-mcp.toml").read_text())
            self.assertNotIn("serena", no_tool.get("mcp_servers", {}))
            deps.generate(example, output)
            mcp = tomllib.loads((output / "codex-mcp.toml").read_text())
            self.assertIn("serena", mcp["mcp_servers"])
            compose = (output / "compose.tools.yaml").read_text()
            self.assertIn("/root/.serena:rw", compose)
            self.assertIn("agent:", compose)
            self.assertNotIn("tool-serena:", compose)


if __name__ == "__main__":
    unittest.main()
