#!/usr/bin/env python3
"""Create selected persistent Codex / Serena bind directories on the host.

Called by Make targets BEFORE Podman Compose container creation; does not
alter existing content, delete volumes or rewrite Codex auth/session data.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from pathlib import Path
import sys


def ensure_path(storage_type: str, source: str, label: str, *,
                named_volume: str = "", create_named_volume: bool = False,
                podman: str = "podman") -> None:
    if storage_type == "volume":
        if source != label.lower() + "-state" or not named_volume:
            raise ValueError(f"{label}: invalid named-volume configuration")
        executable = shlex.split(podman)
        if not executable:
            raise ValueError("Missing Podman executable")
        result = subprocess.run([*executable, "volume", "exists", named_volume],
                                check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"{label}: existing Podman named volume verified ({named_volume})")
            return
        if result.returncode != 1:
            raise RuntimeError(f"{label}: cannot inspect named volume {named_volume}: {result.stderr.strip()}")
        if not create_named_volume:
            raise ValueError(f"{label}: named volume {named_volume!r} does not exist; verify "
                             "podman volume ls or explicitly opt in to creation")
        print(f"{label}: creation of new named volume {named_volume} explicitly allowed")
        return
    if storage_type != "bind":
        raise ValueError(f"{label}: unsupported storage type {storage_type!r}")
    if not source or not Path(source).is_absolute():
        raise ValueError(f"{label}: bind mount source must be an absolute path")
    dest = Path(source)
    if dest.is_symlink():
        raise ValueError(f"{label}: refusing symlinked state directory {dest}")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not dest.is_dir():
        raise ValueError(f"{label}: state destination is not a directory")
    if not os.access(dest, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError(f"{label}: state directory not accessible")
    print(f"{label}: persistent local directory ready: {dest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-type", required=True)
    parser.add_argument("--codex-source", required=True)
    parser.add_argument("--codex-named-volume", default="")
    parser.add_argument("--codex-create-named-volume", default="false")
    parser.add_argument("--serena-type", required=True)
    parser.add_argument("--serena-source", required=True)
    parser.add_argument("--serena-named-volume", default="")
    parser.add_argument("--serena-create-named-volume", default="false")
    parser.add_argument("--podman", default="podman")
    args = parser.parse_args()
    try:
        previous = os.umask(0o077)
        try:
            if args.codex_create_named_volume not in ("true", "false") or args.serena_create_named_volume not in ("true", "false"):
                raise ValueError("named-volume creation flags must be true/false")
            ensure_path(args.codex_type, args.codex_source, "Codex",
                        named_volume=args.codex_named_volume,
                        create_named_volume=args.codex_create_named_volume == "true", podman=args.podman)
            ensure_path(args.serena_type, args.serena_source, "Serena",
                        named_volume=args.serena_named_volume,
                        create_named_volume=args.serena_create_named_volume == "true", podman=args.podman)
        finally:
            os.umask(previous)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: persistent state cannot be prepared: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
