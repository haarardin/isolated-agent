# AGENTS.md

This repository defines a reusable isolated development environment for AI coding agents.

## Design invariants

Preserve these unless the task explicitly changes the security model:

1. Do not mount the host Docker socket.
2. Do not mount the host Podman socket.
3. Do not mount the user's home directory.
4. Do not mount SSH credentials into the agent.
5. The only host source tree exposed by default is PROJECT_DIR -> /workspace.
6. The agent container must remain non-root at runtime.
7. Keep the runtime root filesystem read-only where practical.
8. Project services should run as sibling Compose services, not inside the agent process container.
9. Project-specific native dependencies belong in images/project/Containerfile.
10. Codex installation belongs only in images/codex/Containerfile.

## Validation

Before completing infrastructure changes:

- review compose mounts;
- verify no host runtime sockets were introduced;
- run shell syntax checks for scripts;
- validate YAML/Compose configuration when Podman is available;
- keep README usage examples synchronized with Makefile targets.

## Scope

The initial version intentionally keeps Podman service orchestration on the host.

If agent-controlled lifecycle management is added later, prefer a constrained service controller with a small allowlisted API rather than exposing the unrestricted host container-runtime socket.
