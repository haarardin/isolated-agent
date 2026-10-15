#!/usr/bin/env python3
"""Validate CIDRs and atomically produce Squid's destination-deny ACL file.

The generated file is NOT a firewall rule. Squid is a trusted application
enforcing the policy; see docs/NETWORK.md for limitations.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import tempfile


def parse_networks(default: str, extra: str) -> list[str]:
    values = [
        line.partition("#")[0].strip()
        for line in default.splitlines()
    ]
    values = [value for value in values if value]
    values.extend(part.strip() for part in extra.split(",") if part.strip())
    if not values:
        raise ValueError("empty denylist is not allowed")
    networks = []
    for value in values:
        # Force CIDR or address input, no domain strings or Squid directives.
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid BLOCK_CIDRS/destination entry {value!r}") from exc
        canonical = str(network)
        if canonical not in networks:
            networks.append(canonical)
    return networks


def render(base: Path, output: Path, extra: str) -> None:
    networks = parse_networks(base.read_text(encoding="utf-8"), extra)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=".blocked-cidrs-", delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            for cidr in networks:
                handle.write(cidr + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o644)  # only public network prefixes, no secrets
        os.replace(tmp_path, output)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--extra", default="")
    args = parser.parse_args()
    try:
        render(args.base, args.output, args.extra)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
