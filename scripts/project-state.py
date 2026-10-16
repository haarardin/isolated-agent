#!/usr/bin/env python3
"""Derive persistent per-source-project volume identities for Codex and Serena.

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
    if kind not in {"codex", "serena"} or not re.fullmatch(r"[0-9a-f]{24}", key):
        raise ValueError("Invalid volume kind or project key")
    return f"isolated-agent-{kind}-{key}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--field", choices=("key", "codex-volume", "serena-volume"), required=True)
    args = parser.parse_args()
    try:
        key = project_key(args.project_dir, args.compose_project)
        if args.field == "key":
            print(key)
        else:
            print(volume_name(args.field.removesuffix("-volume"), key))
    except ValueError as exc:
        print(f"ERROR: cannot derive isolated project state: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
