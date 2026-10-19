#!/usr/bin/env python3
"""Stop/restart exactly the existing containers of one Compose project.

Never use Compose 'up', create/remove containers, or touch networks/volumes.
The scoped checkpoint records only previously running/paused containers, so
services intentionally stopped beforehand remain stopped after 'make start'.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

PROJECT_LABELS = ("io.podman.compose.project", "com.docker.compose.project")
SERVICE_LABELS = ("io.podman.compose.service", "com.docker.compose.service")
PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
KEY_RE = re.compile(r"^[0-9a-f]{24}$")


def fail(message: str) -> None:
    raise RuntimeError(message)


def label(container: dict, keys: tuple[str, ...]) -> str | None:
    values = (container.get("Config") or {}).get("Labels") or {}
    for key in keys:
        if values.get(key):
            return values[key]
    return None


def status(container: dict) -> str:
    state = container.get("State") or {}
    value = str(state.get("Status") or "").lower()
    if state.get("Paused") or value == "paused":
        return "paused"
    if state.get("Running") or value == "running":
        return "running"
    return value


def identifier(container: dict) -> str:
    value = container.get("Id") or container.get("ID")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{12,64}", value):
        fail("Podman inspect returned an invalid container ID")
    return value


def order_key(record: dict) -> tuple[int, str, str]:
    # Dependencies/proxy first, agent last. Unrecognized sidecars are middle.
    priority = {"postgres": 0, "redis": 1, "squid": 2, "agent": 99}
    return (priority.get(record["service"], 10), record["service"], record["id"])


class Lifecycle:
    def __init__(self, project: str, key: str, state_root: Path, podman: list[str]):
        if not PROJECT_RE.fullmatch(project):
            fail("invalid COMPOSE_PROJECT_NAME")
        if not KEY_RE.fullmatch(key):
            fail("missing or invalid CODEX_PROJECT_KEY: use make targets")
        if not podman:
            fail("Podman executable not configured")
        self.project = project
        self.key = key
        self.state_root = state_root
        self.file = state_root / f"lifecycle-{key}.json"
        self.podman = podman

    def call(self, *args: str) -> str:
        result = subprocess.run([*self.podman, *args], check=True,
                                text=True, capture_output=True)
        return result.stdout

    def inspect(self, container_id: str) -> dict:
        info = json.loads(self.call("inspect", container_id))
        if not isinstance(info, list) or len(info) != 1:
            fail(f"Unexpected inspect output for {container_id}")
        return info[0]

    def project_containers(self) -> list[dict]:
        ids = self.call("ps", "-a", "-q").splitlines()
        items = []
        for item in ids:
            details = self.inspect(item)
            if label(details, PROJECT_LABELS) == self.project:
                # Ignore unrelated containers even if their names look similar.
                identifier(details)
                items.append(details)
        return items

    def validate_agent(self, container: dict) -> None:
        if label(container, SERVICE_LABELS) != "agent":
            return
        expected_workspace = os.environ.get("PROJECT_DIR")
        expected_codex_type = os.environ.get("CODEX_STATE_MOUNT_TYPE")
        expected_codex_source = os.environ.get("CODEX_STATE_MOUNT_SOURCE")
        expected_codex_named = os.environ.get("CODEX_NAMED_VOLUME")
        if not expected_workspace or not expected_codex_type:
            fail("PROJECT_DIR or CODEX_STATE_MOUNT_TYPE missing; use make start/stop")
        mounts = {m.get("Destination"): m for m in (container.get("Mounts") or [])}
        workspace = mounts.get("/workspace") or {}
        codex = mounts.get("/root/.codex") or {}
        same_workspace = (
            workspace.get("Type", "").lower() == "bind" and
            os.path.realpath(workspace.get("Source") or "") == os.path.realpath(expected_workspace)
        )
        if expected_codex_type == "bind":
            same_codex = (
                codex.get("Type", "").lower() == "bind" and
                os.path.realpath(codex.get("Source") or "") == os.path.realpath(expected_codex_source or "")
            )
        elif expected_codex_type == "volume":
            same_codex = (
                codex.get("Type", "").lower() == "volume" and
                codex.get("Name") == expected_codex_named
            )
        else:
            fail("unexpected CODEX_STATE_MOUNT_TYPE")
        if not (same_workspace and same_codex):
            fail("existing agent belongs to another workspace/Codex state; refusing lifecycle operation")

    def save(self, rows: list[dict]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = {"project": self.project, "key": self.key, "containers": rows}
        fd, name = tempfile.mkstemp(prefix=".lifecycle-", dir=self.state_root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.file)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def load(self) -> list[dict]:
        if self.file.is_symlink():
            fail("refusing symlinked lifecycle checkpoint")
        if not self.file.is_file():
            fail("no saved running-container set; first use make up or make up-example, then make stop")
        info = json.loads(self.file.read_text(encoding="utf-8"))
        if info.get("project") != self.project or info.get("key") != self.key:
            fail("lifecycle checkpoint belongs to another project")
        rows = info.get("containers")
        if not isinstance(rows, list) or not rows:
            fail("lifecycle checkpoint has no containers")
        known = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"id", "service", "status"}:
                fail("invalid lifecycle checkpoint entry")
            if not re.fullmatch(r"[0-9a-f]{12,64}", str(row["id"])) or row["id"] in known:
                fail("invalid or duplicate container in lifecycle checkpoint")
            if row["status"] not in ("running", "paused") or not isinstance(row["service"], str):
                fail("invalid saved container state")
            known.add(row["id"])
        return rows

    def stop(self) -> None:
        containers = self.project_containers()
        for item in containers:
            self.validate_agent(item)  # validate before stopping any container
        selected = []
        for item in containers:
            st = status(item)
            if st in ("running", "paused"):
                selected.append({"id": identifier(item),
                                 "service": label(item, SERVICE_LABELS) or "",
                                 "status": st})
        if not selected:
            print(f"No running containers for {self.project}; no changes")
            # Do not replace a checkpoint from an earlier stop with an empty set.
            return
        if self.file.exists():
            fail("existing lifecycle checkpoint found; run make start or remove stale checkpoint manually after inspection")
        selected.sort(key=order_key)
        self.save(selected)  # keep recovery set even if Podman stop partially fails
        for record in reversed(selected):
            cid = record["id"]
            if record["status"] == "paused":
                self.call("unpause", cid)
            print(f"Stopping {record['service'] or 'service'}: {cid[:12]}", flush=True)
            self.call("stop", "--time", "30", cid)
        print(f"Stopped {len(selected)} existing container(s) for {self.project}; no containers removed")

    def start(self) -> None:
        rows = self.load()
        # Validate the *entire* checkpoint before starting anything.
        details = []
        for row in rows:
            item = self.inspect(row["id"])
            if identifier(item) != row["id"] or label(item, PROJECT_LABELS) != self.project:
                fail("saved container ID was replaced or moved to another project: " + row["id"])
            if (label(item, SERVICE_LABELS) or "") != row["service"]:
                fail("saved container service label changed: " + row["id"])
            self.validate_agent(item)
            st = status(item)
            if st not in ("running", "paused", "exited", "stopped", "created", "configured"):
                fail(f"cannot start container {row['id']}: unexpected status {st}")
            details.append(st)
        for row, current in zip(rows, details):
            cid = row["id"]
            if current not in ("running", "paused"):
                print(f"Starting {row['service'] or 'service'}: {cid[:12]}", flush=True)
                self.call("start", cid)
            if row["status"] == "paused" and current != "paused":
                self.call("pause", cid)
            elif row["status"] == "running" and current == "paused":
                self.call("unpause", cid)
        self.file.unlink()
        print(f"Restored {len(rows)} existing container(s) for {self.project}; no containers recreated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop"))
    args = parser.parse_args()
    try:
        item = Lifecycle(
            project=os.environ.get("COMPOSE_PROJECT_NAME", ""),
            key=os.environ.get("CODEX_PROJECT_KEY", ""),
            state_root=Path(__file__).resolve().parents[1] / ".state",
            podman=shlex.split(os.environ.get("PODMAN", "podman")),
        )
        getattr(item, args.action)()
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"ERROR: project lifecycle: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
