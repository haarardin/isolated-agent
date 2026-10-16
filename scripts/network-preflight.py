#!/usr/bin/env python3
"""Plan/create/reuse a rootless-Podman internal network by explicit name.

No network is ever removed here. Network creation is an explicit --ensure;
ordinary preflight only checks and reports the proposed/existing subnet.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib

POOL = ipaddress.ip_network("10.203.0.0/16")
SUBNETS = tuple(POOL.subnets(new_prefix=24))
MANAGED_LABEL = "io.isolated-agent.project"
NETWORK_LABEL = "io.isolated-agent.network"
PROJECT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}$")


def validate_project(project: str) -> str:
    if not PROJECT_PATTERN.fullmatch(project):
        raise ValueError("COMPOSE_PROJECT_NAME must be 1-81 safe characters: letters, digits, underscore, dot, dash")
    return project


def network_name(project: str, chosen: str | None = None) -> str:
    """Independent network identity; legacy default follows Compose project."""
    validate_project(project)
    name = chosen or project + "_isolated-dev"
    if not PROJECT_PATTERN.fullmatch(name):
        raise ValueError("AGENT_NETWORK_NAME must be a safe Podman network name")
    return name


def read_subnets(network: dict) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = network.get("subnets", network.get("Subnets", [])) or []
    parsed = []
    for entry in raw:
        cidr = entry.get("subnet", entry.get("Subnet", "")) if isinstance(entry, dict) else str(entry)
        if cidr:
            parsed.append(ipaddress.ip_network(cidr, strict=False))
    return parsed


def network_info(networks: list[dict], name: str) -> dict | None:
    matches = [n for n in networks if n.get("name", n.get("Name")) == name]
    if len(matches) > 1:
        raise ValueError(f"multiple networks named {name!r}; refusing to guess")
    return matches[0] if matches else None


def find_collisions(networks: list[dict], target: str, expected_name: str) -> list[str]:
    """Compatibility helper for static regression tests and explicit subnet validation."""
    wanted = ipaddress.ip_network(target, strict=True)
    errors = []
    for network in networks:
        name = network.get("name", network.get("Name", "<unknown>"))
        try:
            subnets = read_subnets(network)
        except ValueError as exc:
            errors.append(f"Invalid subnet on Podman network {name}: {exc}")
            continue
        for existing in subnets:
            if wanted.overlaps(existing):
                if name != expected_name:
                    errors.append(f"Podman network {name!r} already uses {existing}, overlapping {wanted}")
                elif existing != wanted:
                    errors.append(f"Existing Compose network {name!r} uses {existing}, expected {wanted}")
        if name == expected_name:
            if not network.get("internal", network.get("Internal", False)):
                errors.append(f"Existing Compose network {name!r} is NOT internal")
            if wanted not in subnets:
                errors.append(f"Existing Compose network {name!r} lacks required subnet {wanted}")
    return errors


def verify_existing(network: dict, project: str, requested: str, chosen: str | None = None) -> str:
    name = network_name(project, chosen)
    if not network.get("internal", network.get("Internal", False)):
        raise ValueError(f"Existing Compose network {name!r} is NOT internal; manual migration required")
    driver = network.get("driver", network.get("Driver", ""))
    if driver != "bridge":
        raise ValueError(f"Existing network {name!r} has unsupported driver {driver!r}; expected bridge")
    if network.get("ipv6_enabled", network.get("IPv6Enabled", False)):
        raise ValueError(f"Existing network {name!r} has IPv6 enabled; refusing to join")
    labels = network.get("labels", network.get("Labels", {})) or {}
    if NETWORK_LABEL in labels and labels[NETWORK_LABEL] != name:
        raise ValueError(f"Network {name!r} has mismatched managed network label")
    # Old project-owned networks carry owner labels. A DIFFERENT Compose
    # project may join only when it explicitly sets AGENT_NETWORK_NAME.
    # Implicit project-derived names still reject foreign ownership.
    if chosen is None:
        for label in (MANAGED_LABEL, "io.podman.compose.project", "com.docker.compose.project"):
            if label in labels and labels[label] != project:
                raise ValueError(f"Existing network {name!r} belongs to {labels[label]!r}, not {project!r}")
    subnets = read_subnets(network)
    if len(subnets) != 1 or subnets[0].version != 4:
        raise ValueError(f"Existing network {name!r} must have exactly one IPv4 subnet (found {subnets})")
    actual = str(subnets[0])
    if requested != "auto" and actual != requested:
        raise ValueError(f"Existing network {name!r} subnet {actual} differs from AGENT_SUBNET={requested}")
    return actual


def choose_subnet(networks: list[dict], project: str, requested: str, previous: str | None = None, chosen: str | None = None) -> str:
    if requested != "auto":
        candidate = ipaddress.ip_network(requested, strict=True)
        if candidate.version != 4:
            raise ValueError("AGENT_SUBNET must be IPv4")
        if find_collisions(networks, str(candidate), network_name(project, chosen)):
            raise ValueError("; ".join(find_collisions(networks, str(candidate), network_name(project))))
        return str(candidate)
    # Prefer the last assigned subnet when the network was intentionally
    # removed. Otherwise select a stable hash start, avoiding all existing
    # Podman subnets (including those used by other projects and VPNs).
    if previous:
        prior = ipaddress.ip_network(previous, strict=True)
        if prior.version != 4:
            raise ValueError(f"Invalid persisted project subnet {previous}")
        if not find_collisions(networks, str(prior), network_name(project, chosen)):
            return str(prior)
        raise ValueError(f"Last project subnet {prior} is now occupied; set AGENT_SUBNET explicitly after review")
    index = zlib.crc32(network_name(project, chosen).encode("utf-8")) % len(SUBNETS)
    for offset in range(len(SUBNETS)):
        candidate = SUBNETS[(index + offset) % len(SUBNETS)]
        if not find_collisions(networks, str(candidate), network_name(project)):
            return str(candidate)
    raise ValueError(f"No unused /24 subnet in {POOL}; set an unused AGENT_SUBNET explicitly")


def inspect_networks() -> list[dict]:
    names = subprocess.check_output(
        ["podman", "network", "ls", "--format", "{{.Name}}"],
        text=True, stderr=subprocess.PIPE,
    ).splitlines()
    networks = []
    for name in names:
        if not name.strip():
            continue
        obj = json.loads(subprocess.check_output(
            ["podman", "network", "inspect", name],
            text=True, stderr=subprocess.PIPE,
        ))
        if isinstance(obj, dict):
            networks.append(obj)
        elif isinstance(obj, list):
            networks.extend(obj)
        else:
            raise ValueError(f"Unexpected network inspect JSON for {name!r}")
    return networks


def load_state(path: Path, project: str, chosen: str | None = None) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("project") != project:
        raise ValueError("Persisted network state belongs to a different Compose project")
    if data.get("name") != network_name(project, chosen):
        # Explicit switch from project-owned to shared network: retain the
        # old external Podman network, but choose/validate the NEW name.
        return None
    return str(ipaddress.ip_network(data["subnet"], strict=True))


def save_state(path: Path, project: str, subnet: str, chosen: str | None = None) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    # Do not follow a symlink when replacing the state file.
    if path.is_symlink():
        raise ValueError("Refusing symlinked .state/network.json")
    data = {"project": project, "name": network_name(project, chosen), "subnet": subnet}
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".network-", text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def resolve(networks: list[dict], project: str, requested: str, previous: str | None,
            chosen: str | None = None) -> tuple[str, bool]:
    name = network_name(project, chosen)
    existing = network_info(networks, name)
    if existing:
        actual = verify_existing(existing, project, requested, chosen)
        if previous and previous != actual:
            raise ValueError(f"Saved subnet {previous} differs from existing network {name}: {actual}")
        # Check for conflicting other subnet definitions, not just exact-name validation.
        conflicts = find_collisions([n for n in networks if n is not existing], actual, name)
        if conflicts:
            raise ValueError("; ".join(conflicts))
        return actual, True
    return choose_subnet(networks, project, requested, previous, chosen), False


def run(project: str, requested: str, state: Path, ensure: bool, chosen: str | None = None) -> tuple[str, str]:
    validate_project(project)
    if requested != "auto":
        wanted = ipaddress.ip_network(requested, strict=True)
        if wanted.version != 4:
            raise ValueError("AGENT_SUBNET must be IPv4")
        requested = str(wanted)
    previous = load_state(state, project, chosen)
    networks = inspect_networks()
    subnet, exists = resolve(networks, project, requested, previous, chosen)
    name = network_name(project, chosen)
    if ensure and not exists:
        command = [
            "podman", "network", "create", "--driver", "bridge", "--internal",
            "--subnet", subnet, "--label", f"{NETWORK_LABEL}={name}", name,
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode:
            # A competing initializer may have created the exact same network.
            again = network_info(inspect_networks(), name)
            if again is None:
                raise ValueError(f"Failed to create network {name}: {result.stderr.strip()}")
            resolved, exists_now = resolve(inspect_networks(), project, requested, previous, chosen)
            if not exists_now or resolved != subnet:
                raise ValueError(f"Concurrent creation of network {name} changed its subnet")
        # Fail closed if runtime silently ignored --internal or chose other CIDR.
        now = network_info(inspect_networks(), name)
        if now is None or verify_existing(now, project, requested, chosen) != subnet:
            raise ValueError(f"Podman did not create the expected isolated network {name}")
        exists = True
        action = "created"
    else:
        action = "reused" if exists else "planned"
    if ensure:
        save_state(state, project, subnet, chosen)
    return subnet, action


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="isolated-agent-demo")
    parser.add_argument("--network-name", default=None,
                        help="explicit shared network name (default: <project>_isolated-dev)")
    parser.add_argument("--subnet", default="auto",
                        help="auto (stable free /24) or explicit private IPv4 CIDR")
    parser.add_argument("--state", type=Path, default=Path(".state/network.json"))
    parser.add_argument("--ensure", action="store_true", help="create missing network after validation")
    args = parser.parse_args()
    try:
        subnet, action = run(args.project, args.subnet, args.state, args.ensure, args.network_name)
        print(f"Project network {action}: {network_name(args.project, args.network_name)} ({subnet}, internal IPv4)")
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: unsafe/unavailable project network: {exc}", file=sys.stderr)
        print("Inspect: podman network ls; podman network inspect <AGENT_NETWORK_NAME>", file=sys.stderr)
        print("Do not remove someone else's network or bypass the internal restriction.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
