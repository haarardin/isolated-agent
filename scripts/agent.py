#!/usr/bin/env python3
"""Select an installed container agent from a trusted runtime registry.

AGENT_RUNTIME chooses a named CLI, never a shell command. The registry is
explicit and extendable; unrecognized names fail closed. The host retains
control of Podman Compose, which is never exposed inside the agent.
"""
from __future__ import annotations

import json
import os
import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/agent-runtimes.json"
NAME = re.compile(r"[a-z][a-z0-9-]{0,40}\Z")


def select_agent(runtime: str, registry: Path = REGISTRY) -> list[str]:
    """Return an argv vector for a configured runtime; never execute a shell."""
    if not NAME.fullmatch(runtime):
        raise ValueError(f"invalid AGENT_RUNTIME: {runtime!r}")
    raw = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("agent runtime registry must be a JSON object")
    command = raw.get(runtime)
    if command is None:
        supported = ", ".join(sorted(raw))
        raise ValueError(f"unsupported AGENT_RUNTIME {runtime!r}; available: {supported}")
    if (not isinstance(command, list) or not command
            or not all(isinstance(arg, str) and arg and "\x00" not in arg for arg in command)):
        raise ValueError(f"invalid argv for configured agent {runtime!r}")
    return command


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    runtime = os.environ.get("AGENT_RUNTIME", "codex")
    try:
        command = select_agent(runtime)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    # Runtime registration is not installation. Reject disabled agents before
    # asking Podman to execute any command (even if a stale CLI still exists).
    spec = importlib.util.spec_from_file_location("agent_dependencies", ROOT / "scripts/dependencies.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        config = module.parse()
        if not module.agent_enabled(config, runtime):
            raise ValueError(f"agent {runtime!r} is disabled in [[agents]]; enable and rebuild")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    # execvp replaces this process and preserves terminal signal handling.
    # This wrapper never evaluates AGENT_RUNTIME as shell source.
    os.execvp("bash", ["bash", str(ROOT / "scripts/compose.sh"), "exec",
                       "agent", *command, *argv])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
