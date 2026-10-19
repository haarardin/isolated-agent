#!/usr/bin/env python3
"""Derive persistent per-source-project volume identity for Codex.

The identity binds a Compose deployment and the canonical host PROJECT_DIR.
Changing PROJECT_DIR therefore selects different persistent volumes by default.
The matching fingerprint is checked again INSIDE each volume at container start.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys

VALID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def project_key(project_dir: str, compose_project: str) -> str:
    if not compose_project or not VALID.fullmatch(compose_project):
        raise ValueError("Invalid COMPOSE_PROJECT_NAME")
    if not project_dir:
        raise ValueError("PROJECT_DIR cannot be empty")
    # resolve() works on a not-yet-mounted path. Use the actual canonical
    # location so ./foo, ../x/foo and absolute paths resolve identically.
    path = Path(project_dir).expanduser().resolve(strict=False)
    if not path.is_absolute():
        raise ValueError("PROJECT_DIR must resolve to an absolute path")
    payload = (compose_project + "\0" + str(path)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def volume_name(kind: str, key: str) -> str:
    if kind != "codex" or not re.fullmatch(r"[0-9a-f]{24}", key):
        raise ValueError("Invalid volume kind or project key")
    return f"isolated-agent-{kind}-{key}"



def storage_spec(setting: str, kind: str, key: str) -> tuple[str, str, str]:
    """Resolve a host directory BASE or backward-compatible Podman volume name.

    Host storage base e.g. ./volumes/codex -> ./volumes/codex/<project-key>.
    Explicit legacy named volumes (no slash) keep their original name.
    The returned third field is the Compose top-level named-volume name.
    """
    if kind != "codex":
        raise ValueError("Invalid storage kind")
    if not setting:
        raise ValueError(f"Empty {kind} storage setting")
    if setting.startswith((".", "~", "/")) or "/" in setting:
        root = Path(setting).expanduser().resolve(strict=False)
        if not root.is_absolute():
            raise ValueError(f"{kind} state path must be absolute after resolution")
        # Deliberately keep all project memory outside the image in a host
        # directory, one subdirectory per unique source-project identity.
        return ("bind", str(root / key), volume_name(kind, key))
    if not VALID.fullmatch(setting):
        raise ValueError(f"Invalid {kind} named volume {setting!r}")
    return ("volume", f"{kind}-state", setting)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--field", choices=("key", "codex-volume",
                                          "mount-type", "mount-source", "named-volume"), required=True)
    parser.add_argument("--kind", choices=("codex",))
    parser.add_argument("--storage")
    args = parser.parse_args()
    try:
        key = project_key(args.project_dir, args.compose_project)
        if args.field == "key":
            print(key)
        elif args.field.endswith("-volume") and args.field != "named-volume":
            print(volume_name(args.field.removesuffix("-volume"), key))
        else:
            if not args.kind or not args.storage:
                raise ValueError("--kind and --storage are required for mount fields")
            mount_type, mount_source, named = storage_spec(args.storage, args.kind, key)
            print({"mount-type": mount_type, "mount-source": mount_source,
                   "named-volume": named}[args.field])
    except ValueError as exc:
        print(f"ERROR: cannot derive isolated project state: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
