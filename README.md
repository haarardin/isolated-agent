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
       │    │    ├── AGENTS.md              project instructions
       │    │    ├── .codex/config.toml     project Codex config
       │    │    └── .serena/               project Serena state
       │    ├── /root/.codex  volume        runtime/user state
       │    ├── /root/.serena volume        Serena global state (optional)
       │    └── /root/.cache  volume        build/tool cache
       │
       ├── postgres      optional
       ├── redis         optional
       └── other project services
```

The agent does **not** receive the host Podman/Docker socket. Service orchestration stays outside the agent sandbox.

## Image layers

The environment uses three baseline image layers plus an optional Serena layer:

1. `base` — OS, Go, Git, build/debug utilities.
2. `codex` — Codex CLI installation.
3. `project` — project dependencies, generic global Codex policy, and system defaults.
4. `serena` — optional Serena MCP + `gopls` layer built on top of `project`.

The image store belongs to the rootless Podman host user, not to a repository
clone or Compose project. Two different project-context clones can therefore
run containers from the same image ID as long as they use the same image tags.

This keeps expensive toolchain layers reusable while Compose isolates runtime
containers, networks, and persistent state.

## Project context root

`/workspace` is the canonical project root inside the agent.

Project-specific context should live with the mounted target project:

```text
/workspace/AGENTS.md
/workspace/.codex/config.toml
/workspace/.serena/
```

Use these paths for repository-specific instructions, Codex overrides and
Serena project state. Codex loads repository `AGENTS.md` files from the
project tree and loads project `.codex/config.toml` for trusted projects.

The `/root` paths serve a different purpose:

```text
/root/.codex   Codex authentication, sessions, history and user/runtime state
/root/.serena  Serena global settings/logs
/root/.cache   Go and tool caches
```

Do not use `/root/.codex/AGENTS.md` or `/root/.serena` as the primary source
of project-specific context. The image may provide a small generic global
policy under `/root/.codex/AGENTS.md`, but repository-specific instructions
belong in `/workspace/AGENTS.md` and take precedence at the project scope.

For local-only project context that should not be committed, prefer the target
repository's `.git/info/exclude`:

```text
AGENTS.md
.codex/
.serena/
```

This keeps the files available to Codex and Serena without changing the shared
repository `.gitignore`.

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

Ensure all image layers are available:

```bash
make ensure-images
```

This is the preferred bootstrap command when the repository is cloned more than
once on the same host. Rootless Podman image storage is shared for the current
host user, so images with the same configured tags are reused instead of being
built again.

Use `make build` and `make build-serena` when you intentionally want to
rebuild image layers.

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

## Recommended multi-project workflow

A practical setup is **one clone of `isolated-agent` per target project
context**. Each clone owns its Compose configuration and runtime state, while
the heavy Podman images are shared by the same rootless host user.

Example:

```text
~/agents/project-a/isolated-agent
  .env:
    COMPOSE_PROJECT_NAME=isolated-agent-project-a
    PROJECT_DIR=/home/user/projects/project-a

~/agents/project-b/isolated-agent
  .env:
    COMPOSE_PROJECT_NAME=isolated-agent-project-b
    PROJECT_DIR=/home/user/projects/project-b
```

Both contexts can use the same local image tags:

```text
localhost/isolated-agent-base:dev
localhost/isolated-agent-codex:dev
localhost/isolated-agent-project:dev
localhost/isolated-agent-serena:dev
```

The resulting runtime looks conceptually like this:

```text
project-a clone ── Compose project A ──┐
                                      ├── shared Podman images
project-b clone ── Compose project B ──┘

Compose project A:
  /workspace -> project-a
  own containers
  own network
  own Codex/cache/Serena state

Compose project B:
  /workspace -> project-b
  own containers
  own network
  own Codex/cache/Serena state
```

### Bootstrap a new project context

After cloning the repository for another project:

```bash
cp .env.example .env
```

At minimum, set:

```dotenv
COMPOSE_PROJECT_NAME=isolated-agent-my-project
PROJECT_DIR=/absolute/path/to/my-project
```

`COMPOSE_PROJECT_NAME` must be unique for each context. Use an absolute
`PROJECT_DIR` for real projects so it is obvious which host repository is
mounted at `/workspace`.

Then run:

```bash
make ensure-images
make up
make ps
```

`make ensure-images` checks each configured image with
`podman image exists`. Existing images are reused and only missing layers are
built.

A simple verification is:

```bash
podman ps
```

Different contexts should have different container names, while the IMAGE
column may intentionally show the same image, for example:

```text
isolated-agent-project-a_agent_1   localhost/isolated-agent-project:dev
isolated-agent-project-b_agent_1   localhost/isolated-agent-project:dev
```

### What is shared and what stays isolated

Normally safe to share across project contexts:

- `BASE_IMAGE` — common OS/toolchain layer;
- `CODEX_IMAGE` — common Codex CLI layer;
- `PROJECT_IMAGE` — when all project-context build-time settings are the same;
- `SERENA_IMAGE` — when its parent project image and Serena/gopls versions are the same.

Keep separate per project context:

- `COMPOSE_PROJECT_NAME`;
- `PROJECT_DIR`;
- containers and Compose networks;
- Codex sessions/history/memories when using per-project volumes or bind mounts;
- build caches when configured per project;
- Serena runtime/project state;
- project-local `AGENTS.md` and source code.

### Important: shared tags are host-global

Image tags such as:

```text
localhost/isolated-agent-project:dev
```

belong to the rootless Podman image store for the current host user. They are
not namespaced by `COMPOSE_PROJECT_NAME`.

Therefore, running:

```bash
make build-project
make build-serena
```

in one clone updates those shared tags for every other clone that uses the same
tag names.

Already-running containers continue using the image ID they were created with.
A newly created or recreated container resolves the current image tag and may
therefore pick up the newly rebuilt image.

This is useful when all contexts intentionally share the same toolchain and
agent configuration, but it matters when project-specific build inputs differ.

### Project-specific image configuration

`make ensure-images` deliberately checks only whether an image tag exists. It
does **not** compare the current clone's build arguments with the image that is
already present.

The `project` image is affected by settings such as:

- `CODEX_AGENTS_FILE`;
- `PROJECT_APT_PACKAGES`;
- Codex model/default configuration;
- memory feature flags and other generated Codex defaults.

The Serena image additionally depends on:

- the selected `PROJECT_IMAGE`;
- `SERENA_VERSION`;
- `SERENA_GOPLS_VERSION`.

For maximum image reuse, keep image-level configuration generic and put
project-specific context directly in the mounted/source project:
`AGENTS.md`, `.codex/config.toml`, and `.serena/`.

If two projects genuinely need different image-level dependencies or Codex
defaults, give them different image tags in their respective `.env` files,
for example:

```dotenv
PROJECT_IMAGE=localhost/isolated-agent-project:sip-server
SERENA_IMAGE=localhost/isolated-agent-serena:sip-server
```

Then build only that project's specialized layers:

```bash
make build-project
make build-serena
```

### Rebuild rules

Use:

```bash
make ensure-images
```

when you want to reuse already available images and build only missing ones.

Use:

```bash
make build-project
make build-serena
```

when project-level build arguments changed.

Use:

```bash
make build
make build-serena
```

when you intentionally want a full rebuild of all layers.

This separation lets multiple project contexts share expensive base/toolchain
images without accidentally forcing a rebuild every time the repository is
cloned.

## Persistent Codex state

All writable Codex state is mounted by Compose:

```text
codex-state  -> /root/.codex
agent-cache  -> /root/.cache
```

This preserves login credentials, sessions/history, Codex-managed state, and Go/build caches when the image or container is rebuilt.

Named volumes are scoped by `COMPOSE_PROJECT_NAME`, so each project should use its own value.

A small image-owned global policy is synchronized into
`/root/.codex/AGENTS.md` on container startup. It describes only the generic
container/runtime rules. Repository-specific instructions belong in
`/workspace/AGENTS.md`.

Other state in `CODEX_HOME` is left intact.

## Codex configuration

The final project layer generates:

```text
/etc/codex/config.toml
```

from build arguments. This provides image-level defaults without mixing them with the persistent user/session state under `/root/.codex`.

Available values in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODEX_AGENTS_FILE` | `templates/AGENTS.global.md` | Generic global image-provided `AGENTS.md` source |
| `CODEX_MODEL` | empty | Explicit model override; empty uses Codex/account default |
| `CODEX_MODEL_REASONING_EFFORT` | `high` | Default reasoning effort |
| `CODEX_PLAN_REASONING_EFFORT` | `high` | Plan-mode reasoning effort |
| `CODEX_MODEL_VERBOSITY` | empty | Optional model verbosity override |
| `CODEX_PERSONALITY` | empty | Optional communication personality |
| `CODEX_REVIEW_MODEL` | empty | Optional model override for `/review` |
| `CODEX_SERVICE_TIER` | empty | Optional service tier such as `fast` when supported |
| `CODEX_FILE_OPENER` | `none` | Disable desktop-editor URI integration inside the container |
| `CODEX_APPROVAL_POLICY` | `never` | Non-interactive/autonomous approval behavior |
| `CODEX_SANDBOX_MODE` | `danger-full-access` | Disable nested Codex sandbox; rootless Podman is the isolation boundary |
| `CODEX_NETWORK_ACCESS` | `true` | Network access from workspace-write sandbox |
| `CODEX_WEB_SEARCH` | `cached` | Web-search mode; use `live` only when freshness is required |
| `CODEX_PROJECT_DOC_MAX_BYTES` | `65536` | Maximum project-instruction bytes loaded |
| `CODEX_SHELL_IGNORE_DEFAULT_EXCLUDES` | `false` | Keep Codex's default secret-name environment filtering active |
| `CODEX_FEATURE_MEMORIES` | `false` | Optional experimental Codex memory feature |
| `PROJECT_APT_PACKAGES` | empty | Extra Debian packages for this project layer |

The outer rootless Podman container is the primary isolation boundary. The default intentionally uses `danger-full-access` **inside the container** so Codex does not try to create a nested Bubblewrap/user-namespace sandbox that rootless Podman commonly blocks. This does not grant host full access: Podman still enforces the filesystem mounts, read-only root filesystem, dropped capabilities, `no-new-privileges`, and network boundary.

If you explicitly switch `CODEX_SANDBOX_MODE=workspace-write` on a host/container configuration that supports nested user namespaces, the generated config also adds `/root/.cache` as a Codex writable root. It explicitly keeps shell environment secret filtering enabled and defaults web search to cached mode to reduce unnecessary exposure to live untrusted web content.

Do not put API keys, tokens, passwords, or other credentials into build arguments: build arguments are image-build metadata, not a secrets mechanism. Authentication belongs in the persistent Codex state volume or in runtime secret injection.

### AGENTS.md precedence

`CODEX_AGENTS_FILE` supplies only generic global instructions for the
container environment. The default is `templates/AGENTS.global.md`.

A target repository should keep its project-specific instructions in:

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

The repository includes optional PostgreSQL 18 + Redis services:

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

The PostgreSQL 18 image stores version-specific data below `/var/lib/postgresql`, so the example mounts the named volume at that directory rather than the pre-18 `/var/lib/postgresql/data` location.

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
make ensure-images
make test-image-reuse-static
make test-project-context-static
make build
make build-project
make build-serena
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
make clean
make reset-example-db
make reset-state
```

## Project instructions template

Use:

```text
templates/AGENTS.project.md
```

as the starting point for `PROJECT_DIR/AGENTS.md`. The template is not used as
the default global image policy.

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


## Recovering a partially removed stack

If a Compose `down` was run with a different set of compose files than the corresponding `up`, some project containers can remain attached to the project network.

Use:

```bash
make clean
```

This does not rely on the Compose model. It finds containers and networks carrying the current project's `io.podman.compose.project` label and removes only those resources.

Persistent volumes are deliberately kept.

To also delete the project's Codex state/cache/database volumes:

```bash
make reset-state
```

Both commands are scoped by `COMPOSE_PROJECT_NAME`.


### Resetting only the example PostgreSQL data

If the PostgreSQL example volume was initialized with an incompatible image/layout, reset only that database without deleting Codex state:

```bash
make reset-example-db
make up-example
make ps-example
```

This removes the PostgreSQL container and the Compose-labeled `postgres-data` volume for the current `COMPOSE_PROJECT_NAME`. Codex authentication/state and caches are preserved.


## Runtime toolchain check

After starting the agent, run:

```bash
make doctor
```

This verifies the effective runtime environment inside the agent container:

- Go is present in `PATH`;
- Codex is present in `PATH`;
- `/workspace`, `CODEX_HOME`, and the build cache are writable;
- the container root filesystem remains read-only.

Scripted test commands intentionally use a non-login shell. A login shell (`bash -l`) can replace the image-provided `PATH` via `/etc/profile` and hide toolchain paths such as `/usr/local/go/bin`.


## Codex sandbox inside Podman

Codex's Linux `workspace-write` mode uses the Linux sandbox backend (currently Bubblewrap by default). A rootless Podman container commonly cannot create the additional user/network namespaces Bubblewrap needs, producing errors such as:

```text
bwrap: setting up uid map: Operation not permitted
```

The default profile therefore uses:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

Here, "full access" means full access **to the already-isolated container**, not to the host.

Do not solve nested Bubblewrap failures by adding privileged mode, host runtime sockets, broad capabilities, or host filesystem mounts. Those changes would weaken the actual security boundary.

### Credential caveat

With Codex's inner sandbox disabled, commands run by the agent share the container security domain with Codex itself. Treat the container as a trusted development sandbox, avoid mounting unrelated secrets, keep host credentials out of it, and prefer narrowly scoped credentials when this project moves to remote/self-hosted execution.


## Agent-only lifecycle

`podman-compose` does not implement Docker Compose's `rm` subcommand. For agent persistence/recreation tests, use the project targets instead:

```bash
make stop-agent
make remove-agent
make ps-example
make up-example
```

Or recreate only the agent in one command:

```bash
make recreate-agent
```

`remove-agent` resolves the container by the current project's Compose labels:

```text
io.podman.compose.project=<COMPOSE_PROJECT_NAME>
io.podman.compose.service=agent
```

so it does not depend on generated container names and does not remove PostgreSQL, Redis, networks, or volumes.


### podman-compose label compatibility

Different podman-compose versions may use either the Podman-native label namespace:

```text
io.podman.compose.project
io.podman.compose.service
```

or the Docker Compose compatibility namespace:

```text
com.docker.compose.project
com.docker.compose.service
```

Lifecycle helper scripts inspect both forms so they work with older and newer podman-compose releases.

## Optional Serena MCP integration

Large Go repositories can opt into a separate `Serena + gopls` image layer.
Serena exposes symbol-aware code search and editing to Codex through MCP
over local stdio. The baseline three-layer image remains unchanged.

```bash
make build-serena
make test-serena-static
make up-serena-example
make serena-doctor
make codex-serena
```

For the first Serena start on an **empty** Compose project, bootstrap
the PostgreSQL/Redis examples once with `make up-example`.
Subsequent `make up-serena-example` invocations recreate **only the agent
container**. This avoids duplicate PostgreSQL/Redis container-name
errors seen with `podman-compose up -d` on some versions.
Do not switch while a Codex session is active. Existing source files
and Codex state volumes persist. The optional Compose overlay adds a separate
`serena-state` volume at `/root/.serena`.

To switch back to the plain project image without touching running example
services or persistent volumes, use `make recreate-agent`.

See [docs/serena.md](docs/serena.md) for architecture, permissions, project
`.serena/` artifacts, benchmark design, and rollback steps.
