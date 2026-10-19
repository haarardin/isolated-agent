#!/usr/bin/env python3
"""Apply and verify declared local LSP bindings for supported tool adapters.

Runs inside the agent, with the tool's own Python environment. Never executes
untrusted project configuration or modifies Serena's project trust allowlist.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from ruamel.yaml import YAML


def configure(spec: dict, check: bool) -> None:
    if spec.get("adapter") != "serena":
        raise ValueError("Unsupported LSP consumer adapter")
    if spec.get("state") != "/root/.serena":
        raise ValueError("Serena adapter requires a persistent /root/.serena mount")
    servers = spec.get("servers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError("No declared language servers")

    root = Path(spec["state"])
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Serena state directory is unavailable or unsafe")
    path = root / "serena_config.yml"
    if path.is_symlink():
        raise ValueError("Refusing symlinked Serena global configuration")

    # Serena generates its full default configuration; do not synthesize an
    # incomplete YAML document that could drop Serena-specific defaults.
    if not path.exists() and not check:
        from serena.config.serena_config import SerenaConfig
        SerenaConfig.from_config_file()
    if not path.is_file():
        raise ValueError("Serena global configuration missing: " + str(path))

    yaml = YAML(typ="rt")  # preserve comments, project registry and all settings
    with path.open(encoding="utf-8") as stream:
        settings = yaml.load(stream)
    if not isinstance(settings, dict):
        raise ValueError("Serena global config must be a mapping")
    configured = settings.get("ls_specific_settings")
    if configured is None:
        if check:
            raise ValueError("Global Serena config lacks ls_specific_settings")
        settings["ls_specific_settings"] = {}
        configured = settings["ls_specific_settings"]
    if not isinstance(configured, dict):
        raise ValueError("Serena ls_specific_settings must be a mapping")

    changed = False
    for language, executable in servers.items():
        binary = Path(executable)
        if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(f"{language}: configured LSP executable missing: {executable}")
        options = configured.get(language)
        if options is None:
            if check:
                raise ValueError(f"{language}: no global LSP binding in Serena")
            configured[language] = {}
            options = configured[language]
            changed = True
        if not isinstance(options, dict):
            raise ValueError(f"{language}: Serena LS options must be a mapping")
        existing = options.get("ls_path")
        if existing is not None and existing != executable:
            raise ValueError(
                f"{language}: existing user ls_path={existing!r} conflicts with "
                f"the declarative executable {executable!r}; refusing to overwrite"
            )
        if existing is None:
            if check:
                raise ValueError(f"{language}: Serena missing global ls_path")
            options["ls_path"] = executable
            changed = True

    if changed:
        backup = path.with_name("serena_config.yml.before-isolated-agent-lsp")
        if not backup.exists():
            shutil.copy2(path, backup)
            backup.chmod(0o600)
        fd, name = tempfile.mkstemp(prefix=".serena-lsp-", dir=root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                yaml.dump(settings, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    print("LSP bindings verified:", ", ".join(f"{k}={v}" for k, v in sorted(servers.items())))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("spec", help="JSON tool LSP binding generated from dependencies.toml")
    args = parser.parse_args()
    try:
        configure(json.loads(args.spec), args.check)
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print("ERROR: Agent Tool LSP configuration:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
