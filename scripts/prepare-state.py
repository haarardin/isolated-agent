#!/usr/bin/env python3
"""Create selected persistent Codex / Serena bind directories on the host.

Called by Make targets BEFORE Podman Compose container creation; does not
alter existing content, delete volumes or rewrite Codex auth/session data.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def ensure_path(storage_type: str, source: str, label: str) -> None:
    if storage_type == "volume":
        if not source.endswith("-state"):
            raise ValueError(f"{label}: unexpected named-volume mount source")
        print(f"{label}: Podman named volume ({source}), no directory needed")
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
    parser.add_argument("--serena-type", required=True)
    parser.add_argument("--serena-source", required=True)
    args = parser.parse_args()
    try:
        previous = os.umask(0o077)
        try:
            ensure_path(args.codex_type, args.codex_source, "Codex")
            ensure_path(args.serena_type, args.serena_source, "Serena")
        finally:
            os.umask(previous)
    except (OSError, ValueError) as exc:
        print(f"ERROR: persistent state cannot be prepared: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
