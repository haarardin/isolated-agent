#!/usr/bin/env python3
"""Fail safely when pre-unification Serena .env settings would be ignored.

Legacy volumes are NEVER deleted or modified here. This guard only blocks
new container provisioning until the user has chosen a migration strategy.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

LEGACY_KEYS = frozenset({
    "SERENA_STATE_VOLUME", "SERENA_BIND_EXISTING_STATE",
    "SERENA_CREATE_NAMED_VOLUME", "SERENA_STATE_MOUNT_TYPE",
    "SERENA_STATE_MOUNT_SOURCE", "SERENA_NAMED_VOLUME",
    "SERENA_IMAGE", "SERENA_VERSION", "SERENA_GOPLS_VERSION",
    "SERENA_PROJECT_KEY",
})
SETTING = re.compile(r"^\s*(?:export\s+)?(SERENA_[A-Z0-9_]+)\s*=")


def obsolete_keys(path: Path, environ: dict[str, str]) -> set[str]:
    existing = {name for name in LEGACY_KEYS if name in environ}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = SETTING.match(line)
            if match and match.group(1) in LEGACY_KEYS:
                existing.add(match.group(1))
    return existing


def main() -> int:
    keys = obsolete_keys(Path(".env"), os.environ)
    if not keys:
        return 0
    print("ERROR: obsolete built-in Serena settings: " + ", ".join(sorted(keys)), file=sys.stderr)
    print(
        "These variables no longer mount/install Serena and cannot be silently "
        "ignored. Stop active sessions, back up the prior Serena global state, "
        "migrate any named Serena volume, declare Serena through [[agent_tools]] "
        "in dependencies/dependencies.toml, and remove the obsolete .env "
        "entries. See docs/serena.md (Migration). No state was removed.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
