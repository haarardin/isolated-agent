# isolated-agent global instructions

These instructions describe the container runtime only. Project-specific
instructions belong to the mounted project under /workspace.

## Project context

Treat /workspace as the canonical project root.

Project-specific context should live in the target repository:

- /workspace/AGENTS.md for project instructions;
- /workspace/.codex/config.toml for project-level Codex overrides;
- /workspace/.serena/ for Serena project configuration and memories.

Do not create project-specific instructions or project configuration under
/root.

## Runtime state

The following paths are container/runtime state, not project source:

- /root/.codex for Codex authentication, sessions, history and user-level state;
- /root/.serena for Serena global settings and logs;
- /root/.cache for Go and tool caches.

Do not treat those directories as the primary source of project context.

## Workspace boundary

The agent may modify files under /workspace according to the target project's
own instructions.

Do not assume access to host files outside explicitly mounted paths.
Do not mount or request the host Podman/Docker socket.
