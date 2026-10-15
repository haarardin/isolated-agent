#!/usr/bin/env python3
"""Check fixed Compose subnet against existing rootless Podman networks.

Never delete networks automatically: another repository or service may own them.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
import sys


def find_collisions(networks: list[dict], target: str, expected_name: str) -> list[str]:
    """Return diagnostics for overlapping subnets or invalid owned network."""
    wanted = ipaddress.ip_network(target, strict=True)
    errors: list[str] = []
    for network in networks:
        name = network.get("name", network.get("Name", "<unknown>"))
        internal = network.get("internal", network.get("Internal", False))
        subnets = network.get("subnets", network.get("Subnets", [])) or []
        parsed: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for entry in subnets:
            value = entry.get("subnet", entry.get("Subnet", "")) if isinstance(entry, dict) else str(entry)
            if not value:
                continue
            try:
                existing = ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                errors.append(f"Invalid subnet {value!r} on Podman network {name}: {exc}")
                continue
            parsed.append(existing)
            if wanted.overlaps(existing):
                if name != expected_name:
                    errors.append(
                        f"Podman network {name!r} already uses {existing}, "
                        f"which overlaps required {wanted}"
                    )
                elif wanted != existing:
                    errors.append(
                        f"Existing Compose network {name!r} uses {existing}, "
                        f"but project expects {wanted}"
                    )
        if name == expected_name:
            if not internal:
                errors.append(f"Existing Compose network {name!r} is NOT internal")
            if wanted not in parsed:
                errors.append(f"Existing Compose network {name!r} lacks required subnet {wanted}")
    return errors


def inspect_networks() -> list[dict]:
    names = subprocess.check_output(
        ["podman", "network", "ls", "--format", "{{.Name}}"],
        text=True,
        stderr=subprocess.PIPE,
    ).splitlines()
    all_networks: list[dict] = []
    for name in names:
        if not name.strip():
            continue
        output = subprocess.check_output(
            ["podman", "network", "inspect", name],
            text=True,
            stderr=subprocess.PIPE,
        )
        info = json.loads(output)
        if isinstance(info, dict):
            all_networks.append(info)
        elif isinstance(info, list):
            all_networks.extend(info)
        else:
            raise ValueError(f"Unexpected Podman network inspect format for {name}")
    return all_networks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subnet", default="10.89.71.0/24")
    parser.add_argument("--project", default="isolated-agent-demo")
    args = parser.parse_args()

    try:
        ipaddress.ip_network(args.subnet, strict=True)
        existing = inspect_networks()
        expected = args.project + "_isolated-dev"
        conflicts = find_collisions(existing, args.subnet, expected)
    except (ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: Unable to inspect Podman networks: {exc}", file=sys.stderr)
        return 1

    if not conflicts:
        print(f"Network preflight OK: {args.subnet} is available for {expected}")
        return 0

    print("ERROR: Cannot create isolated Compose network:", file=sys.stderr)
    for issue in conflicts:
        print(f"  - {issue}", file=sys.stderr)
    print(
        "\nInspect the affected network with: podman network inspect <name>\n"
        "Check attached containers: podman ps -a --filter network=<name>\n"
        "Only if unused, remove the old network: podman network rm <name>\n"
        "Do not delete networks owned by other projects. "
        "Set AGENT_SUBNET and ensure no CIDR overlaps; do not remove foreign networks.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
