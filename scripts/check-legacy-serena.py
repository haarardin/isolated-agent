#!/usr/bin/env python3
"""Fail closed when old Serena configuration OR a legacy agent image is present.

No containers, images, named volumes, bind state or user files are modified.
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

LEGACY_KEYS = frozenset({
    "SERENA_STATE_VOLUME", "SERENA_BIND_EXISTING_STATE",
    "SERENA_CREATE_NAMED_VOLUME", "SERENA_STATE_MOUNT_TYPE",
    "SERENA_STATE_MOUNT_SOURCE", "SERENA_NAMED_VOLUME",
    "SERENA_IMAGE", "SERENA_VERSION", "SERENA_GOPLS_VERSION",
    "SERENA_PROJECT_KEY",
})
SETTING = re.compile(r"^\s*(?:export\s+)?(SERENA_[A-Z0-9_]+)\s*=")
PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
CID = re.compile(r"^[0-9a-f]{12,64}$")
LEGACY_IMAGE = re.compile(r"(?:^|/)isolated-agent-serena(?:[-:]|$)")
GENERIC_IMAGE = re.compile(r"(?:^|/)isolated-agent-project(?:[-:]|$)")


def obsolete_keys(path: Path, environ: dict[str, str]) -> set[str]:
    existing = {name for name in LEGACY_KEYS if name in environ}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = SETTING.match(line)
            if match and match.group(1) in LEGACY_KEYS:
                existing.add(match.group(1))
    return existing


def read_label(record: dict, suffix: str) -> str:
    labels = (record.get("Config") or {}).get("Labels") or {}
    a = labels.get("io.podman.compose." + suffix)
    b = labels.get("com.docker.compose." + suffix)
    if a and b and a != b:
        raise ValueError("conflicting Compose ownership labels; refusing to proceed")
    return a or b or ""


def legacy_agent(record: dict, expected_project_image: str) -> str | None:
    """Classify only same-project agent records; caller verifies Compose labels."""
    config = record.get("Config") or {}
    raw_env = config.get("Env") or []
    if not isinstance(raw_env, list):
        raise ValueError("unexpected Podman Config.Env")
    entries = [v.split("=", 1)[0] for v in raw_env if isinstance(v, str)]
    image = record.get("ImageName") or config.get("Image") or ""
    mounts = record.get("Mounts") or []
    if not isinstance(mounts, list):
        raise ValueError("unexpected Podman Mounts")
    serena_mount = any(isinstance(m, dict) and
                       (m.get("Destination") or m.get("Target")) == "/root/.serena"
                       for m in mounts)
    # Old compose.serena.yaml always injects SERENA_PROJECT_KEY into Config.Env.
    # Detect it even if the image has a custom name or the value is empty.
    if "SERENA_PROJECT_KEY" in entries or "SERENA_BIND_EXISTING_STATE" in entries:
        return "legacy Serena container environment"
    if LEGACY_IMAGE.search(image):
        return "legacy Serena agent image " + image
    # A regular generated Agent Tools overlay can ALSO mount /root/.serena.
    # Its Project image has no legacy environment; this case is allowed.
    if serena_mount and not (image == expected_project_image or GENERIC_IMAGE.search(image)):
        return "unrecognized agent image with Serena mount: " + (image or "<unknown>")
    return None


def find_legacy_agent(project: str, podman: str, expected_project_image: str = "") -> list[str]:
    if not PROJECT.fullmatch(project):
        raise ValueError("invalid COMPOSE_PROJECT_NAME")
    command = shlex.split(podman)
    if not command:
        raise ValueError("empty Podman executable")

    def call(*args: str) -> str:
        return subprocess.run([*command, *args], check=True,
                              capture_output=True, text=True).stdout

    found = []
    for cid in call("ps", "-a", "-q").splitlines():
        if not CID.fullmatch(cid):
            raise ValueError("invalid Podman container ID: " + cid)
        inspected = json.loads(call("inspect", cid))
        if not isinstance(inspected, list) or len(inspected) != 1:
            raise ValueError("unexpected Podman inspect response")
        record = inspected[0]
        if read_label(record, "project") != project or read_label(record, "service") != "agent":
            continue
        reason = legacy_agent(record, expected_project_image)
        if reason:
            found.append(f"{cid[:12]} ({reason})")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("COMPOSE_PROJECT_NAME", "isolated-agent-demo"))
    parser.add_argument("--podman", default=os.environ.get("PODMAN", "podman"))
    parser.add_argument("--project-image", default=os.environ.get("PROJECT_IMAGE", ""))
    args = parser.parse_args()
    try:
        keys = obsolete_keys(Path(".env"), os.environ)
        if keys:
            raise ValueError("obsolete built-in Serena settings: " + ", ".join(sorted(keys)))
        old_agents = find_legacy_agent(args.project, args.podman, args.project_image)
        if old_agents:
            raise ValueError("existing legacy Serena agent container(s): " +
                             "; ".join(old_agents))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            json.JSONDecodeError) as exc:
        print("ERROR: Serena legacy migration check: " + str(exc), file=sys.stderr)
        print(
            "Provisioning stopped BEFORE any agent replacement or network changes. "
            "Save sessions and back up Codex/Serena state; enable the generic "
            "[[agent_tools]] Serena module and migrate legacy named state if needed. "
            "Then explicitly remove only the old agent container with "
            "'make remove-agent' (does not remove volumes) and retry 'make up'. "
            "See docs/serena.md. No state was deleted by this check.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
