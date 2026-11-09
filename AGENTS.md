# AGENTS.md

This repository defines a reusable isolated development environment for AI coding agents.

## Design invariants

Preserve these unless the task explicitly changes the security model:

1. Do not mount the host Docker socket.
2. Do not mount the host Podman socket.
3. Do not mount the user's home directory.
4. Do not mount SSH credentials into the agent.
5. The only host source tree exposed by default is PROJECT_DIR -> /workspace.
6. Podman on the host must remain rootless. Root inside the rootless container is acceptable and must not be confused with host root.
7. Keep the runtime root filesystem read-only where practical.
8. Mount persistent state for enabled agents (Codex, OpenCode), Agent Tools (e.g. Serena), and build caches only through reviewed Compose volumes. Disabled agents must not retain state mounts.
9. Project services should run as sibling Compose services, not inside the agent process container.
10. Install coding agents through enabled `[[agents]]` and SDKs/MCP dependencies through `[[install]]`/`[[agent_tools]]` in `dependencies/dependencies.toml`. Keep image-owned runtime configuration in `images/project/Containerfile`.
11. The normal image chain is Base -> Dependencies -> Project. Codex is installed via `dependencies/scripts/install-codex.sh` only when enabled; OpenCode via `dependencies/scripts/install-opencode.sh` only when enabled, without Node/npm solely for OpenCode. `images/codex/Containerfile` is a legacy manual target.
12. Rootless Podman is the primary sandbox. Do not add privileged mode, host runtime sockets, or broad Linux capabilities to make Codex's nested Bubblewrap sandbox work.
13. The default Codex sandbox mode is `danger-full-access` inside the container; changing it to `workspace-write` requires verifying nested sandbox compatibility.

## Validation

Before completing infrastructure changes:

- review Compose mounts;
- verify no host runtime sockets were introduced;
- run shell syntax checks for scripts;
- validate YAML/Compose configuration when Podman is available;
- keep README and all docs usage examples synchronized with Makefile targets, runtime selection and generated MCP configurations;
- keep Codex config keys aligned with current OpenAI Codex documentation.

## Scope

The initial version intentionally keeps Podman service orchestration on the host.

If agent-controlled lifecycle management is added later, prefer a constrained service controller with a small allowlisted API rather than exposing the unrestricted host container-runtime socket.
