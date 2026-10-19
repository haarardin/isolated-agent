"""Pure-Python Podman simulation for non-destructive project start/stop."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lifecycle", ROOT / "scripts/project-lifecycle.py")
life = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(life)

KEY = "4c9ea23249722423311dcc61"
PROJECT = "agent-go-c-smoke"
WORKSPACE = "/home/test/workspace"
STATE = "/home/test/codex-state"


def container(char, project, service, status="running", workspace=WORKSPACE):
    ident = char * 64
    return {
        "Id": ident,
        "Config": {"Labels": {"io.podman.compose.project": project,
                              "io.podman.compose.service": service}},
        "State": {"Status": status, "Running": status == "running",
                  "Paused": status == "paused"},
        "Mounts": [
            {"Destination": "/workspace", "Type": "bind", "Source": workspace},
            {"Destination": "/root/.codex", "Type": "bind", "Source": STATE},
        ] if service == "agent" else [],
    }


class FakePodman:
    def __init__(self):
        self.items = {
            c["Id"]: c for c in (
                container("a", PROJECT, "agent"),
                container("b", PROJECT, "squid"),
                container("c", PROJECT, "postgres"),
                container("d", PROJECT, "redis", "exited"),
                container("e", "another-project", "agent"),
            )
        }
        self.commands = []

    def run(self, argv, **kwargs):
        self.commands.append(argv[:])
        self_last = argv[1:]
        action = self_last[0]
        if action == "ps":
            result = "\n".join(self.items)
        elif action == "inspect":
            cid = self_last[1]
            obj = self.items.get(cid)
            if obj is None:
                raise subprocess.CalledProcessError(125, argv, stderr="not found")
            result = json.dumps([obj])
        else:
            cid = self_last[-1]
            if cid not in self.items:
                raise subprocess.CalledProcessError(125, argv, stderr="not found")
            item = self.items[cid]
            if action == "stop":
                item["State"].update(Status="exited", Running=False, Paused=False)
            elif action == "start":
                item["State"].update(Status="running", Running=True, Paused=False)
            elif action == "pause":
                item["State"].update(Status="paused", Running=False, Paused=True)
            elif action == "unpause":
                item["State"].update(Status="running", Running=True, Paused=False)
            else:
                raise AssertionError(f"Unexpected Podman operation {argv}")
            result = ""
        return subprocess.CompletedProcess(argv, 0, result, "")


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake = FakePodman()
        self.patch = mock.patch.object(life.subprocess, "run", side_effect=self.fake.run)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.env = mock.patch.dict(os.environ, {
            "PROJECT_DIR": WORKSPACE,
            "CODEX_STATE_MOUNT_TYPE": "bind",
            "CODEX_STATE_MOUNT_SOURCE": STATE,
            "CODEX_NAMED_VOLUME": "unused",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cli = life.Lifecycle(PROJECT, KEY, Path(self.tmp.name), ["podman"])

    def status(self, c):
        return life.status(self.fake.items[c * 64])

    def commands(self, name):
        return [x for x in self.fake.commands if len(x) > 1 and x[1] == name]

    def test_roundtrip_only_previously_running_containers(self):
        self.cli.stop()
        self.assertEqual(self.status("a"), "exited")
        self.assertEqual(self.status("b"), "exited")
        self.assertEqual(self.status("c"), "exited")
        self.assertEqual(self.status("d"), "exited")
        self.assertEqual(self.status("e"), "running")
        self.assertTrue(self.cli.file.is_file())
        checkpoint = json.loads(self.cli.file.read_text())
        self.assertEqual({r["service"] for r in checkpoint["containers"]},
                         {"agent", "squid", "postgres"})
        self.cli.start()
        self.assertEqual(self.status("a"), "running")
        self.assertEqual(self.status("b"), "running")
        self.assertEqual(self.status("c"), "running")
        self.assertEqual(self.status("d"), "exited")  # was stopped beforehand
        self.assertEqual(self.status("e"), "running")  # other project untouched
        self.assertFalse(self.cli.file.exists())
        self.assertEqual(self.commands("start")[-1][-1], "a" * 64)  # agent last
        self.assertFalse(any(x[1] in ("up", "rm", "create") for x in self.fake.commands))

    def test_paused_container_restored_as_paused(self):
        self.fake.items["b" * 64]["State"].update(Status="paused", Paused=True, Running=False)
        self.cli.stop()
        self.assertEqual(self.status("b"), "exited")
        self.cli.start()
        self.assertEqual(self.status("b"), "paused")
        self.assertTrue(self.commands("pause"))

    def test_second_stop_does_not_erase_recovery_checkpoint(self):
        self.cli.stop()
        original = self.cli.file.read_bytes()
        self.cli.stop()
        self.assertEqual(self.cli.file.read_bytes(), original)
        self.cli.start()
        self.assertFalse(self.cli.file.exists())

    def test_start_without_saved_set_does_not_guess_containers(self):
        with self.assertRaisesRegex(RuntimeError, "no saved running-container"):
            self.cli.start()
        self.assertFalse(self.commands("start"))

    def test_replaced_or_cross_project_container_blocks_start(self):
        self.cli.stop()
        self.fake.items.pop("b" * 64)
        with self.assertRaises(subprocess.CalledProcessError):
            self.cli.start()
        self.assertFalse(self.commands("start"))
        self.assertTrue(self.cli.file.exists())

    def test_mount_mismatch_prevents_any_stop(self):
        self.fake.items["a" * 64]["Mounts"][0]["Source"] = "/another/workspace"
        with self.assertRaisesRegex(RuntimeError, "another workspace"):
            self.cli.stop()
        self.assertEqual(self.status("b"), "running")
        self.assertFalse(self.cli.file.exists())

    def test_old_checkpoint_cannot_start_other_project_identity(self):
        self.cli.stop()
        other = life.Lifecycle("another-project", KEY, Path(self.tmp.name), ["podman"])
        with self.assertRaisesRegex(RuntimeError, "another project"):
            other.start()
        self.assertFalse(self.commands("start"))

    def test_no_existing_project_containers_is_noop(self):
        self.fake.items = {"e" * 64: self.fake.items["e" * 64]}
        self.cli.stop()
        self.assertFalse(self.cli.file.exists())
        self.assertEqual(self.commands("stop"), [])


if __name__ == "__main__":
    unittest.main()
