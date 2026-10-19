"""Disabled MCP sidecars are reconciled without touching other projects."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reconcile", ROOT / "scripts/reconcile-tool-sidecars.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
PROJECT = "demo"


def item(project, service, *, managed=True, image=None, running=True):
    labels = {"io.podman.compose.project": project, "io.podman.compose.service": service}
    if managed:
        labels["isolated-agent.managed-tool"] = "true"
    return {"Config": {"Labels": labels,
                       "Image": image if image is not None else f"localhost/isolated-agent-tool-{project}-{service[5:]}:dev"},
            "State": {"Status": "running" if running else "exited", "Running": running}}


class FakePodman:
    def __init__(self):
        self.items = {
            "a"*64: item(PROJECT, "tool-enabled"),
            "b"*64: item(PROJECT, "tool-removed", managed=False),
            "c"*64: item("other", "tool-other"),
            "d"*64: item(PROJECT, "postgres"),
            "e"*64: item(PROJECT, "tool-custom", managed=False, image="postgres:17")}
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        action = args[1]
        if action == "ps":
            out = "\n".join(self.items)
        elif action == "inspect":
            out = json.dumps([self.items[args[2]]])
        else:
            cid = args[-1]
            if action == "rm":
                del self.items[cid]
            elif action == "stop":
                self.items[cid]["State"] = {"Status": "exited", "Running": False}
            elif action == "unpause":
                pass
            else:
                raise AssertionError(args)
            out = ""
        return subprocess.CompletedProcess(args, 0, out, "")


class Tests(unittest.TestCase):
    def test_enable_disable_reconcile_and_isolation(self):
        fake = FakePodman()
        with mock.patch.object(mod.subprocess, "run", side_effect=fake.run):
            self.assertEqual(mod.reconcile(PROJECT, {"tool-enabled", "tool-removed"}, ["podman"]), [])
            self.assertEqual(mod.reconcile(PROJECT, {"tool-enabled"}, ["podman"]), ["tool-removed"])
            self.assertEqual(mod.reconcile(PROJECT, set(), ["podman"]), ["tool-enabled"])
            self.assertEqual(mod.reconcile(PROJECT, set(), ["podman"]), [])
        for char in "cde":
            self.assertIn(char*64, fake.items)
            self.assertNotIn(["podman", "rm", char*64], fake.calls)
        self.assertFalse(any("-v" in args for args in fake.calls))

    def test_stopped_sidecar_only_removed(self):
        fake = FakePodman()
        fake.items["a"*64] = item(PROJECT, "tool-enabled", running=False)
        with mock.patch.object(mod.subprocess, "run", side_effect=fake.run):
            self.assertEqual(mod.reconcile(PROJECT, {"tool-removed"}, ["podman"]), ["tool-enabled"])
        self.assertFalse(any(args[1] == "stop" and args[-1] == "a"*64 for args in fake.calls))
        self.assertIn(["podman", "rm", "a"*64], fake.calls)


if __name__ == "__main__":
    unittest.main()
