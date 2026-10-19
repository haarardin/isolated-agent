#!/usr/bin/env python3
"""Reconcile disabled managed sidecars by Compose ownership and image namespace."""
from __future__ import annotations
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SERVICE = re.compile(r"^tool-[a-z][a-z0-9-]{0,40}$")


def compose_label(item, podman_key, docker_key):
    labels = (item.get("Config") or {}).get("Labels") or {}
    a, b = labels.get(podman_key), labels.get(docker_key)
    if a and b and a != b:
        raise ValueError("Conflicting Compose labels")
    return a or b or ""


def reconcile(project, enabled, engine):
    if not PROJECT.fullmatch(project) or not engine or any(not SERVICE.fullmatch(x) for x in enabled):
        raise ValueError("Invalid project or enabled services")

    def run(*args):
        return subprocess.run([*engine, *args], capture_output=True, text=True,
                              check=True).stdout

    obsolete = []
    for cid in run("ps", "-a", "-q").splitlines():
        data = json.loads(run("inspect", cid))
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("Invalid Podman inspect data")
        item = data[0]
        project_label = compose_label(item, "io.podman.compose.project", "com.docker.compose.project")
        service = compose_label(item, "io.podman.compose.service", "com.docker.compose.service")
        if project_label != project or not SERVICE.fullmatch(service) or service in enabled:
            continue
        tags = (item.get("Config") or {}).get("Labels") or {}
        image = item.get("ImageName") or (item.get("Config") or {}).get("Image") or ""
        legacy_image = f"localhost/isolated-agent-tool-{project}-{service[5:]}:"
        if tags.get("isolated-agent.managed-tool") != "true" and not image.startswith(legacy_image):
            print(f"Skipping unmanaged tool-like service: {service}")
            continue
        if not re.fullmatch(r"[0-9a-f]{12,64}", cid):
            raise ValueError("Invalid container ID")
        state = item.get("State") or {}
        paused = bool(state.get("Paused") or state.get("Status") == "paused")
        running = bool(paused or state.get("Running") or state.get("Status") == "running")
        obsolete.append((cid, service, paused, running))
    # Inspect all candidates before removing any containers.
    for cid, service, paused, running in obsolete:
        if paused:
            run("unpause", cid)
        if running:
            run("stop", "--time", "30", cid)
        run("rm", cid)  # never pass -v or remove the state directory
        print(f"Removed disabled managed sidecar {service}: {cid[:12]}")
    return [service for _, service, _, _ in obsolete]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--enabled", default="")
    args = parser.parse_args()
    try:
        reconcile(args.project, set(args.enabled.split()),
                  shlex.split(os.environ.get("PODMAN", "podman")))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: sidecar reconciliation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
