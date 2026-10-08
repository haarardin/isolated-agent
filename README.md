# isolated-agent

Reusable rootless-Podman development sandbox for local AI coding agents such as OpenAI Codex CLI.

The goal is to give an agent enough freedom to edit code, use project services, and run unit/integration tests while exposing only the project workspace and explicitly declared Compose resources.

## Architecture

```text
Host Linux
│
├── rootless Podman + pinned podman-compose wrapper
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
       │    ├── /root/.codex  volume
       │    └── /root/.cache  volume
       │
       ├── postgres      optional
       ├── redis         optional
       └── other project services
```

The agent does **not** receive the host Podman/Docker socket. Service orchestration stays outside the agent sandbox.

## Image layers

The environment is built in three layers:

1. `base` — OS, Go, Git, build/debug utilities.
2. `codex` — Codex CLI installation.
3. `project` — project dependencies, global `AGENTS.md`, and Codex production defaults.

This keeps Codex upgrades separate from both the slower base toolchain and project-specific configuration.

## Why root inside the container

The host runtime is required to be **rootless Podman**.

The final container itself runs as container root. In rootless Podman that identity is mapped into the host user's user namespace; it is not host root. This removes unnecessary UID/GID plumbing and lets the agent edit the bind-mounted workspace naturally.

We still keep the outer controls:

- rootless Podman;
- read-only container root filesystem at runtime;
- all Linux capabilities dropped;
- `no-new-privileges`;
- no host runtime socket;
- no host `$HOME`, `.ssh`, or arbitrary filesystem mounts.

## Requirements

- Linux
- rootless Podman
- `podman-compose` available as the Compose provider

`podman compose` is itself only a provider wrapper and prefers `docker-compose` when both providers are installed. This project therefore does not rely on provider auto-selection: all project commands go through `scripts/compose.sh`, which invokes `podman-compose` directly. This avoids requiring a Podman API service socket for ordinary local orchestration.

## Quick start

Copy the environment file:

```bash
cp .env.example .env
```

Set `PROJECT_DIR` in `.env` to the source directory the agent may access.

Build all image layers:

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

Open Codex:

```bash
make codex
```

Open a regular shell:

```bash
make shell
```

Stop the environment:

```bash
make down
```

## Persistent Codex state

All writable Codex state is mounted by Compose:

```text
codex-state  -> /root/.codex
agent-cache  -> /root/.cache
```

This preserves login credentials, sessions/history, Codex-managed state, and Go/build caches when the image or container is rebuilt.

Named volumes are scoped by `COMPOSE_PROJECT_NAME`, so each project should use its own value.

The image-owned global instructions file is synchronized into:

```text
/root/.codex/AGENTS.md
```

on container startup. Other state in `CODEX_HOME` is left intact.

## Codex configuration

The final project layer generates:

```text
/etc/codex/config.toml
```

from build arguments. This provides image-level defaults without mixing them with the persistent user/session state under `/root/.codex`.

Available values in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODEX_AGENTS_FILE` | `templates/AGENTS.project.md` | Global image-provided `AGENTS.md` source |
| `CODEX_MODEL` | empty | Explicit model override; empty uses Codex/account default |
| `CODEX_MODEL_REASONING_EFFORT` | `high` | Default reasoning effort |
| `CODEX_PLAN_REASONING_EFFORT` | `high` | Plan-mode reasoning effort |
| `CODEX_MODEL_VERBOSITY` | empty | Optional model verbosity override |
| `CODEX_PERSONALITY` | empty | Optional communication personality |
| `CODEX_REVIEW_MODEL` | empty | Optional model override for `/review` |
| `CODEX_SERVICE_TIER` | empty | Optional service tier such as `fast` when supported |
| `CODEX_FILE_OPENER` | `none` | Disable desktop-editor URI integration inside the container |
| `CODEX_APPROVAL_POLICY` | `never` | Non-interactive/autonomous approval behavior |
| `CODEX_SANDBOX_MODE` | `workspace-write` | Codex's inner sandbox policy |
| `CODEX_NETWORK_ACCESS` | `true` | Network access from workspace-write sandbox |
| `CODEX_WEB_SEARCH` | `cached` | Web-search mode; use `live` only when freshness is required |
| `CODEX_PROJECT_DOC_MAX_BYTES` | `65536` | Maximum project-instruction bytes loaded |
| `CODEX_SHELL_IGNORE_DEFAULT_EXCLUDES` | `false` | Keep Codex's default secret-name environment filtering active |
| `CODEX_FEATURE_MEMORIES` | `false` | Optional experimental Codex memory feature |
| `PROJECT_APT_PACKAGES` | empty | Extra Debian packages for this project layer |

The outer Podman container is the primary isolation boundary. Codex's own `workspace-write` sandbox remains enabled as defense in depth.

The generated config also adds `/root/.cache` as a Codex writable root so Go/module/build caches remain usable with the inner sandbox. It explicitly keeps shell environment secret filtering enabled and defaults web search to cached mode to reduce unnecessary exposure to live untrusted web content.

Do not put API keys, tokens, passwords, or other credentials into build arguments: build arguments are image-build metadata, not a secrets mechanism. Authentication belongs in the persistent Codex state volume or in runtime secret injection.

### AGENTS.md precedence

`CODEX_AGENTS_FILE` supplies global instructions for the environment.

A target repository can still contain its own:

```text
/workspace/AGENTS.md
```

and deeper directories can contain additional `AGENTS.md` or `AGENTS.override.md` files. Codex loads these from global to local scope, so project-local instructions can specialize the generic image policy.

## Project-specific packages

For straightforward native dependencies you usually do not need to edit a Containerfile:

```dotenv
PROJECT_APT_PACKAGES=libpq-dev gstreamer1.0-tools
```

Then:

```bash
make build-project
```

For more complex installation logic, edit `images/project/Containerfile`.

## Example integration services

The repository includes optional PostgreSQL + Redis services:

```bash
make up-example
make ps-example
```

Inside the agent they are reachable through Compose DNS:

```text
postgres:5432
redis:6379
```

No database/cache ports are exposed on the host.

A normal Compose network does not share a loopback namespace, so sibling services are reached by service name rather than `127.0.0.1`.

## Testing workflow

The target project's own `AGENTS.md` should tell Codex which checks are mandatory before it reports completion.

The included template expects a flow such as:

```bash
go test ./...
go test -race ./...
make integration
```

Useful host commands:

```bash
make test
make race
make integration
```

## Security model

The default environment:

- requires rootless Podman;
- exposes only `PROJECT_DIR` from the host;
- mounts Codex state and build cache only as named Compose volumes;
- does not mount host `$HOME`;
- does not mount host `.ssh`;
- does not expose Docker/Podman sockets;
- drops all Linux capabilities;
- enables `no-new-privileges`;
- uses a read-only container root filesystem at runtime;
- leaves project services as sibling Compose services.

This is a strong development sandbox, not a formal VM-grade boundary against kernel exploits. For hostile/untrusted code, place the complete environment inside a VM as an additional layer.

## Useful commands

```bash
make preflight
make build
make build-project
make up
make up-example
make login
make codex
make shell
make test
make race
make integration
make logs
make logs-example
make ps
make ps-example
make down
make down-example
make reset-state
```

## Project instructions template

Use:

```text
templates/AGENTS.project.md
```

as the starting point for project instructions.

Keep stable development rules in `AGENTS.md` rather than relying on remembered chat context alone.

## Current scope

The first version intentionally keeps Podman service lifecycle control outside Codex.

A future optional layer can expose a constrained orchestration API for selected project services without giving the agent unrestricted access to the host container-runtime socket.


## Compose provider

For this repository, prefer the Make targets or the pinned wrapper:

```bash
make ps-example
```

or, when you need a raw Compose command:

```bash
bash scripts/compose.sh \
  -f compose.yaml \
  -f compose.example-services.yaml \
  ps
```

Do not use an unqualified `podman compose ...` command as a project instruction. On hosts that also have Docker Compose installed, Podman may choose `docker-compose` first, which then expects the Podman API socket.
