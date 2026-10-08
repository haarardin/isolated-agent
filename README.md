# isolated-agent

Reusable Podman-based development sandbox for local AI coding agents such as OpenAI Codex CLI.

The goal is simple: give an agent enough freedom to edit code and run unit/integration tests, while exposing only the project workspace and explicitly declared project services.

## Architecture

```text
Host Linux
│
├── Podman + podman compose
│
├── project source directory
│      │
│      └──── bind mount ───────────────┐
│                                      │
└── isolated compose network           │
       │                               │
       ├── agent                       │
       │    ├── Codex CLI              │
       │    ├── Go toolchain           │
       │    ├── project dependencies   │
       │    ├── /workspace  ◄──────────┘
       │    └── persistent Codex state
       │
       ├── postgres      optional
       ├── redis         optional
       └── other project services
```

The agent does **not** receive the host Podman/Docker socket. Service orchestration stays outside the agent sandbox.

## Image layers

The environment is built in three layers:

1. `base` — OS, Go, Git, build/debug utilities.
2. `codex` — Codex CLI installed on top of the base image.
3. `project` — project-specific native libraries and tooling.

That keeps Codex upgrades separate from slower project/runtime dependencies.

## Requirements

- Linux
- rootless Podman
- `podman-compose` available as the Compose provider

`podman compose` is a wrapper around an external provider. This template defaults to `podman-compose` so Podman-specific features such as `keep-id` and `x-podman.in_pod` behave consistently. Override `PODMAN_COMPOSE_PROVIDER` only if the replacement provider supports the same semantics.

## Quick start

Copy the environment file:

```bash
cp .env.example .env
```

Set `PROJECT_DIR` in `.env` to the source directory the agent may access.

Build the three image layers:

```bash
make build
```

Start the agent:

```bash
make up
```

Authenticate Codex once:

```bash
make login
```

Open Codex inside the sandbox:

```bash
make codex
```

Open a regular shell inside the sandbox:

```bash
make shell
```

Stop the environment:

```bash
make down
```

## Example integration services

The repository includes an optional PostgreSQL + Redis example:

```bash
make up-example
```

Inside the agent container they are reachable through Compose DNS:

```text
postgres:5432
redis:6379
```

They are intentionally not exposed on host ports.

A normal Compose network does not share a loopback namespace, so sibling services are reached by service name rather than `127.0.0.1`. If a future project requires shared loopback semantics, add a Pod-specific runtime profile instead of weakening the base sandbox.

## Project-specific dependencies

Edit:

```text
images/project/Containerfile
```

Only this layer should contain dependencies unique to a target project.

For example:

```Dockerfile
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq-dev \
       gstreamer1.0-tools \
    && rm -rf /var/lib/apt/lists/*

USER agent
```

Then rebuild:

```bash
make build-project
```

## Persistent state

Two named volumes are kept outside the disposable agent container:

- `codex-state` → `/home/agent/.codex`
- `agent-cache` → `/home/agent/.cache`

This keeps Codex authentication/session state and build caches persistent between container recreations while remaining isolated from other project environments through the Compose project name.

Set a unique `COMPOSE_PROJECT_NAME` per project.

## Security model

The default agent container:

- requires rootless Podman;
- runs as a non-root user;
- uses Podman's `keep-id` user namespace mapping so the container user can edit the bind-mounted project without changing host ownership;
- drops Linux capabilities;
- enables `no-new-privileges`;
- uses a read-only root filesystem;
- receives only the configured project directory;
- does not mount `$HOME`, `.ssh`, Docker socket, Podman socket, or arbitrary host directories;
- gets writable storage only for `/workspace`, Codex state, cache, and temporary files.

This is a development sandbox, not a formal security boundary against kernel exploits. For stronger isolation, run the whole environment inside a VM.

## Useful commands

```bash
make preflight
make build
make up
make up-example
make login
make codex
make shell
make test
make race
make integration
make logs
make down
```

## Project instructions for the agent

Use `templates/AGENTS.project.md` as a starting point for the target repository's own `AGENTS.md`.

That file should document:

- architecture;
- test commands;
- integration-test commands;
- service endpoints;
- constraints on generated code;
- actions the agent must perform before declaring a task complete.

## Current scope

This first skeleton deliberately keeps service lifecycle control outside Codex.

A future optional layer may add a constrained orchestration API so the agent can restart/log selected project services without receiving the unrestricted host Podman socket.
