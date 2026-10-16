"""Project-scoped persistent agent state, including the SQLite memory DB."""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
modpath = ROOT / "scripts/project-state.py"
spec = importlib.util.spec_from_file_location("project_state", modpath)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)

CLAIM = ROOT / "scripts/claim-state.sh"
KEY = "a" * 24
OTHER = "b" * 24


class ProjectStateTests(unittest.TestCase):
    def test_same_project_source_has_stable_identity(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work) / "app"
            folder.mkdir()
            key1 = state.project_key(str(folder), "agent-a")
            key2 = state.project_key(str(folder / ".." / "app"), "agent-a")
            self.assertEqual(key1, key2)
            self.assertEqual(len(key1), 24)
            self.assertEqual(state.volume_name("codex", key1),
                             f"isolated-agent-codex-{key1}")
            self.assertEqual(state.volume_name("serena", key1),
                             f"isolated-agent-serena-{key1}")

    def test_changed_project_dir_and_compose_identity_never_share(self):
        with tempfile.TemporaryDirectory() as work:
            a = pathlib.Path(work) / "app-a"
            b = pathlib.Path(work) / "app-b"
            a.mkdir()
            b.mkdir()
            self.assertNotEqual(state.project_key(str(a), "agent"),
                                state.project_key(str(b), "agent"))
            self.assertNotEqual(state.project_key(str(a), "agent"),
                                state.project_key(str(a), "other-agent"))

    def test_invalid_identity(self):
        with self.assertRaises(ValueError):
            state.project_key("./work", "../invalid")
        with self.assertRaises(ValueError):
            state.volume_name("evil", KEY)

    def claim(self, directory: pathlib.Path, key: str = KEY,
              allow: str = "false", component: str = "codex"):
        return subprocess.run(
            ["bash", str(CLAIM), str(directory), key, allow, component],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            check=False,
        )

    def test_fresh_volume_survives_and_rejects_different_project(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work) / "codex-home"
            first = self.claim(folder)
            self.assertEqual(first.returncode, 0, first.stderr)
            (folder / "memories").mkdir()
            (folder / "memories" / "MEMORY.md").write_text("important memory")
            (folder / "memories_1.sqlite").write_bytes(b"sqlite-placeholder")
            self.assertEqual(self.claim(folder).returncode, 0)
            self.assertNotEqual(self.claim(folder, OTHER).returncode, 0)
            self.assertEqual((folder / "memories" / "MEMORY.md").read_text(),
                             "important memory")
            self.assertEqual((folder / "memories_1.sqlite").read_bytes(),
                             b"sqlite-placeholder")

    def test_existing_legacy_volume_requires_explicit_claim(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work) / "codex-home"
            folder.mkdir()
            (folder / "auth.json").write_text("do-not-touch")
            rejected = self.claim(folder)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((folder / ".isolated-agent-project-key").exists())
            self.assertEqual(self.claim(folder, allow="true").returncode, 0)
            self.assertEqual((folder / "auth.json").read_text(), "do-not-touch")
            self.assertEqual(self.claim(folder, OTHER, allow="true").returncode, 1)

    def test_container_image_volume_copyup_first_mount(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work) / "codex-home"
            folder.mkdir()
            (folder / ".isolated-agent-volume-template").touch()
            (folder / "packages").mkdir()
            self.assertEqual(self.claim(folder).returncode, 0)
            self.assertFalse((folder / ".isolated-agent-volume-template").exists())
            (folder / ".isolated-agent-project-key").unlink()
            self.assertNotEqual(self.claim(folder).returncode, 0)

    def test_serena_global_state_volume_guard(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work) / "serena-home"
            folder.mkdir()
            (folder / ".isolated-agent-volume-template").touch()
            self.assertEqual(self.claim(folder, component="serena").returncode, 0)
            (folder / "memories").mkdir()
            self.assertNotEqual(self.claim(folder, OTHER, component="serena").returncode, 0)

    def test_guard_rejects_symlink_marker(self):
        with tempfile.TemporaryDirectory() as work:
            folder = pathlib.Path(work)
            (folder / ".isolated-agent-project-key").symlink_to("/etc/passwd")
            self.assertNotEqual(self.claim(folder).returncode, 0)

    def test_compose_and_makefile_volume_contract(self):
        mk = (ROOT / "Makefile").read_text()
        compose = (ROOT / "compose.yaml").read_text()
        serena = (ROOT / "compose.serena.yaml").read_text()
        image = (ROOT / "images/project/Containerfile").read_text()
        self.assertIn("CODEX_STATE_VOLUME ?= isolated-agent-codex-$(CODEX_PROJECT_KEY)", mk)
        self.assertIn("SERENA_STATE_VOLUME ?= isolated-agent-serena-$(CODEX_PROJECT_KEY)", mk)
        self.assertIn("CODEX_FEATURE_MEMORIES ?= true", mk)
        self.assertIn("name: ${CODEX_STATE_VOLUME:-", compose)
        self.assertIn("name: ${SERENA_STATE_VOLUME:-", serena)
        self.assertIn("CODEX_PROJECT_KEY: ${CODEX_PROJECT_KEY:-}", compose)
        self.assertIn("ARG CODEX_FEATURE_MEMORIES=true", image)
        self.assertIn("printf 'memories = %s", image)


if __name__ == "__main__":
    unittest.main()
