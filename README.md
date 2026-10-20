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
└── isolated Compose network           │
       │                               │
       ├── agent                       │
       │    ├── Codex CLI              │
       │    ├── Optional SDKs         │
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

Filtered Web mode: agent -> Squid on internal network -> separate outbound network -> public Internet.
Offline mode: internal network only; Squid absent.
```

The agent does **not** receive the host Podman/Docker socket. Service orchestration stays outside the agent sandbox.

## Image layers

The environment uses four reusable image layers:

1. `base` — neutral Debian 13 with common utilities; no Go SDK or Serena.
2. `codex` — official Codex CLI and Remote Control.
3. `dependencies` — explicit SDKs, packages and embedded Agent Tools.
4. `project` — Codex configuration, global policy and generated MCP entries.

Serena is **not** an intrinsic image layer or Compose service. To install it,
enable `[[agent_tools]]` in `dependencies/dependencies.toml`.

## Persistent Codex and optional Agent Tool state

The default Codex home, including auth, SQLite memories and session
history, is bind-mounted from the gitignored host directory
`./volumes/codex/<project-key>`. `make up`, `make offline` and
`make recreate-agent` prepare this state. A per-project identity
marker prevents accidental cross-project Codex state reuse.

Additional tools opt into persistence through `[agent_tools.state]`,
which mounts a separate `./volumes/.../<project-key>` directory into
the appropriate container. No tool state directories are provisioned
when tools are disabled or absent.

For example, optional Serena uses
`base = "./volumes/serena"` and `target = "/root/.serena"`
in its TOML configuration. Serena's project memories remain under
`PROJECT_DIR/.serena/memories/` in the workspace bind mount.
Unlike Codex, Serena's old `SERENA_STATE_VOLUME` .env setting is no
longer supported; use the [migration guide](docs/serena.md) for
preserving existing named-volume state.

```dotenv
CODEX_STATE_VOLUME=./volumes/codex
CODEX_FEATURE_MEMORIES=true
```

`make memory-info` displays the resolved Codex state path. A bare
Codex state volume name remains supported for migration if that named
volume exists. Intentional creation of a new Codex named volume
requires `CODEX_CREATE_NAMED_VOLUME=true` for the first startup.
Neither standard container recreation nor Compose down deletes the
default bind state. Back it up separately.

## Universal toolchains and Agent Tools

Go is no longer required by the Base image or runtime doctor. SDKs,
Debian packages, local `.deb` / archives, installer scripts and arbitrary
trusted commands are configured in `dependencies/dependencies.toml`.
MCP and CLI tools share one generic `[[agent_tools]]` manifest with
`embedded`, `sidecar`, and `external` placements.

```bash
make deps-validate
make deps-plan       # preview generated image and MCP definitions
make build           # build Base, Codex, Dependencies, Project
make up              # agent + filtered Squid + enabled sidecars
make doctor
```

Change to TOML requires an explicit `make build-project` (or `make build`)
before restarting the agent. The Makefile maintains separate
project-scoped Project image tags so MCP endpoint configuration from one
checkout does not contaminate another checkout on the same host.
Legacy named images set explicitly in `.env` remain an operator choice.

Project tasks such as `make test`, `make race`, and `make integration`
now follow `[project]` recipes instead of assuming Go is installed.
See [Dependencies/Agent Tools design, examples and security](docs/dependencies.md).

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
For direct `scripts/compose.sh` invocations the wrapper resolves `COMPOSE_PROJECT_NAME`
and `AGENT_NETWORK_NAME` from this checkout's `.env`, unless explicitly set in
its environment. For full container provisioning use Make, which additionally
computes project-specific paths, volumes and image identities.

## Quick start

For **Android Remote Control**, follow the complete
[Remote Control launch guide](docs/REMOTE-START.md) rather than
only the generic CLI instructions below.

Copy the environment file:

```bash
cp .env.example .env
```

Set `PROJECT_DIR` in `.env` to the source directory the agent may access.

Build the generic agent (Base + Codex + Dependencies + Project):

```bash
make deps-validate
make deps-plan
make build
```

On an existing host, `make ensure-project-image` can reuse current tags
and build only missing layers. It does **not** detect changed dependencies
or configuration: use `make build-project` to apply those changes.
`make ensure-images` is an alias for ensuring the Project image
(and its Base/Codex prerequisites); it never builds Serena unless
Serena is explicitly enabled as an Agent Tool and the dependencies
are deliberately rebuilt.

Start the agent with **filtered web egress** (internal network + Squid):

```bash
make up
```

Use `make offline` for a network-isolated agent **without Internet**.
Existing contexts with the old `internal: false` Podman network must migrate
explicitly; see [network isolation](docs/network-isolation.md).

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

Stop the **existing containers without removing or recreating them**:

```bash
make stop
# Later, resume exactly the containers that were running:
make start
```

For first-time creation or after image/Compose changes, use `make up`
(or `make up-example` for PostgreSQL + Redis). Use `make down` only
when you explicitly want the Compose containers removed. Volumes are
preserved by normal `down`, but the container IDs and writable layers
are not.

## Independent network name and shared networks

Two independent Compose projects can intentionally join **one existing
internal Podman network** without sharing their Codex sessions or named volumes:

```dotenv
# Project A
COMPOSE_PROJECT_NAME=codex-api
AGENT_NETWORK_NAME=ai-development
AGENT_SUBNET=auto

# Project B (separate checkout and .env)
COMPOSE_PROJECT_NAME=codex-sip
AGENT_NETWORK_NAME=ai-development
AGENT_SUBNET=auto
```

`COMPOSE_PROJECT_NAME` scopes containers, sessions, cache and DB
volumes. **`AGENT_NETWORK_NAME` selects the network independently.**
If omitted, the previous default remains:
`<COMPOSE_PROJECT_NAME>_isolated-dev`.

`make network-info` checks the configured network, and
`make network-ensure` creates it if missing or validates and reuses
a same-named internal network. `make up` invokes that automatically.
Compose `down` does not delete the external internal network.

Each project's Squid receives a unique DNS alias such as
`codex-api-egress` or `codex-sip-egress`. A **shared network grants
reachability between its member containers** and is suitable only
for mutually trusted projects.

See [network identity and sharing](docs/network-isolation.md).

## Start Codex Remote Control from Android

For a complete step-by-step setup, **start here**:
**[REMOTE-START.md — first install, existing agent upgrade, Android pairing,
validation and troubleshooting](docs/REMOTE-START.md)**.

The quick operational sequence, **after the correct images are built and
the agent is initialized**, is:

```bash
make up                # agent + Squid; online filtered-egress mode
make login             # only if not already signed in to Codex
make remote-start      # detached managed Codex daemon
make remote-status
make remote-doctor
make remote-pair       # only when pairing a new Android device
```

**Do not skip the image build and recreation steps in the linked guide**
when updating an older container. Remote Android tasks may initialize
`/root/Documents`, which the updated **project image** maps to
`/workspace` using an image-baked symlink. Applying this requires
`make build-project && make recreate-agent` (or rebuilding and starting
the Serena image). No host port needs to be opened; rootless Podman isolation
and the selected persistent Codex/Serena bind directories (or
explicit legacy named volumes) are retained.

The Android host/pairing flow has been observed on an actual device,
but successful execution of a whole remote turn must still be verified
on the Debian host. The official manual-code flow remains experimental
and may differ across Android versions.

Detailed background:
[Remote Control implementation](docs/remote-control.md) ·
[network isolation](docs/network-isolation.md) ·
[security model](docs/security.md).

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

The reusable host-level images share these default tags:

```text
localhost/isolated-agent-base:dev
localhost/isolated-agent-codex:dev
localhost/isolated-agent-dependencies:dev
```

The **Project** image is project-scoped by default, keyed by the
canonical `PROJECT_DIR` and `COMPOSE_PROJECT_NAME`:

```text
localhost/isolated-agent-project-<project-key>:dev
```

The Dependencies image tag remains host-global. Running
`make build-project` regenerates its recipe, builds Dependencies,
and builds the project-scoped Project image with current MCP settings.
Explicit image-tag overrides in older `.env` files bypass the
project-scoped defaults and must be reviewed before reuse.

### Bootstrap a new project context

Copy `.env.example` to `.env` and assign a distinct `COMPOSE_PROJECT_NAME`
and an absolute `PROJECT_DIR` for the target source directory:

```bash
make deps-validate
make deps-plan
make build              # on a fresh host: Base, Codex, Dependencies, Project
make up
make ps
```

On a host where Base and Codex already exist, run `make build-project`
instead of `make build`. `make ensure-project-image` reuses existing
image tags and builds only missing layers; it does not detect changed
dependencies, build arguments or generated MCP configuration.
`make ensure-images` now ensures only Base, Codex and Project images,
without an extra dedicated Serena image.

### What is shared and what stays isolated

The Base and Codex image tags, and by default the Dependencies image tag,
are reusable. Workspace files, containers, Codex and Serena state,
Project image tags, and runtime lifecycle checkpoints are scoped per project.
Internal networks are separate by default; sharing `AGENT_NETWORK_NAME`
with another *trusted* project grants mutual service reachability.

### Shared tags are host-global

Any explicitly shared `DEPENDENCIES_IMAGE` or `PROJECT_IMAGE`
tag can be overwritten by a build from another checkout.
Already-running containers retain their image ID, but a recreated container
may use the newer image. Prefer project-scoped defaults for project-specific
settings.

### Migration after upgrading existing project contexts

If you already have an `isolated-agent` project context created before the
workspace-context change, two existing local artifacts can preserve the old
behavior even after pulling the updated repository.

First, check the local `.env`. Older contexts may still contain:

```dotenv
CODEX_AGENTS_FILE=templates/AGENTS.project.md
```

That explicit value overrides the new Makefile/default configuration. Remove
the line entirely to use the repository default, or change it to:

```dotenv
CODEX_AGENTS_FILE=templates/AGENTS.global.md
```

Second, existing Podman images are intentionally reused by
`make ensure-images`. An already-built `PROJECT_IMAGE` may still
contain the previous image-global `AGENTS.project.md`.

After updating an existing context, inspect old `.env` image overrides
and legacy state volumes. After saving active Codex work:

```bash
make build-project
make recreate-agent
```

For previous legacy Serena users, follow
[the Serena state migration guide](docs/serena.md) before switching
to the normal Project image with declarative Serena enabled.

### Rebuild rules

Use `make ensure-images` to reuse current Base/Codex/Project image tags
without checking whether their build inputs changed.

Use `make build-project` when project settings, SDKs, dependencies or
`[[agent_tools]]` configuration changes. After saving active work,
run `make recreate-agent` to deploy the rebuilt Project image.
Use `make build` to rebuild all four layers from Base upwards.

The Project image inherits generated Dependencies and MCP configuration.
A rebuild does not hot-reload active Codex sessions.

## Persistent Codex state

`/root/.codex` is the **complete** persistent CODEX_HOME, including
authentication, sessions, history, native memories, and associated SQLite
files. By default its source is a gitignored host directory:
`./volumes/codex/<project-key>` (bind-mounted). Serena global state
defaults to `./volumes/serena/<project-key>` at `/root/.serena`;
Serena project memories remain under `PROJECT_DIR/.serena/memories/`.
The `agent-cache` named volume is mounted at `/root/.cache`.

These are not backups. `make memory-info` displays effective paths.
Legacy Podman named volumes work when explicitly selected in `.env`,
but must exist unless a separate named-volume creation opt-in is enabled.
See [migration and backups](docs/codex-config.md#upgrading-an-existing-codex-volume).

The image-owned generic `AGENTS.md` is synchronized into
`/root/.codex/AGENTS.md` on startup without erasing authentication,
memories or Codex-managed state. Repository instructions belong in
`/workspace/AGENTS.md`.

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
| `CODEX_FEATURE_MEMORIES` | `true` | Enable Codex native memories in new builds; an existing `.env` may override |
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

Use `dependencies/dependencies.toml` for language SDKs, system packages,
installation scripts, and Agent Tools. For example, add packages under
`[apt]` and run `make deps-validate && make build-project`, followed by
`make recreate-agent`. The older `PROJECT_APT_PACKAGES` argument remains
available for small Project-layer additions; avoid putting new language
toolchains in the Base image.

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

`make test`, `make race`, `make integration`, and `make deps-lint`
run the recipes declared in the active
`dependencies/dependencies.toml` `[project]` table. The default TOML
installs **no Go SDK** and contains no project test recipes: these Make
targets fail with an explanation until configured. For a Go example,
see `dependencies/examples/go-serena.toml`.

## Security model

The default environment:

- requires rootless Podman;
- exposes only `PROJECT_DIR` from the host;
- bind-mounts project-scoped Codex state by default (or an explicitly selected legacy named volume), and uses a named build-cache volume;
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
make memory-info
make deps-validate
make deps-plan
make ensure-project-image
make ensure-images
make test-image-reuse-static
make test-project-context-static
make build
make build-project
make up
make up-example
make offline
make stop
make start
make deps-reconcile
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

To delete this Compose project's **named** volumes (including
cache/database and any legacy Codex named volume):

```bash
make reset-state
```

Both commands scope container and labeled network/volume removal
to `COMPOSE_PROJECT_NAME`. They do **not** remove repository-local
`volumes/codex/<project-key>` and `volumes/serena/<project-key>`
bind directories. Back them up and manage their deletion separately.


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


## Project-wide lifecycle: `make stop` / `make start`

These two commands operate on **all existing containers belonging to the
current `COMPOSE_PROJECT_NAME`**, identified by Compose's Podman-native or
Docker-compatible project labels. This includes the agent, Squid, optional
PostgreSQL/Redis, and any enabled Agent Tool sidecars that have already been
created. Containers of other Compose projects are never selected, even
when they share `AGENT_NETWORK_NAME`.

```bash
make up-example            # create agent + squid + postgres + redis (once)
make stop                  # stop the currently running containers
make start                 # restart the same containers, no Compose 'up'
make ps-example
make doctor
```

`make stop` saves only containers that were **running (or paused)**
into an atomic `.state/lifecycle-<project-key>.json` checkpoint, then
stops them with a graceful 30-second timeout. Already stopped services
remain stopped; a paused service is restored to paused state. Stopping
twice without an intervening `make start` does not erase the checkpoint.
`make start` uses those exact saved container IDs, starting dependency
services before the agent, and then clears the checkpoint after success.

The operations do not create/remove containers, build images, change
Compose profiles, networks or volumes. They verify the project labels
and agent's workspace/Codex mounts before acting. If a saved container
was removed/recreated externally or the project configuration now
points to a different workspace, `make start` **fails rather than
silently switching containers**. Inspect/resolve the stale checkpoint
before a fresh `make up` or `make stop` cycle.

`make start` is **not a substitute for initial `make up`** and is not
an image-update command. Without a prior `make stop`, it will explain
that there is no saved running set. For image/config changes, use
`make build-project` and `make recreate-agent` as usual.

**Persistence:** bind-mounted Codex/Serena state, workspace files,
PostgreSQL's persistent named volume, and each existing container's
writable layer survive `make stop`/`make start`. Processes are
terminated/restarted, not frozen: interactive Codex sessions end, and
the example Redis uses no snapshot/AOF persistence, so **its in-memory
keys are lost when stopped**. Close/commit active work before stopping.
Do not confuse `make stop` with `make down` (Compose removes service
containers) or `make clean` (removes project containers/networks).

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

Serena is an **ordinary embedded MCP Agent Tool** configured through
`dependencies/dependencies.toml`. No custom image, Compose profile,
Make commands or mandatory Serena installation remain.

The example `dependencies/examples/go-serena.toml` opts into Python,
Serena, Go/gopls and clangd. Add the required entries to the active
TOML and use the standard tool lifecycle:

```bash
make deps-validate
make deps-plan
make build-project
make recreate-agent    # when an agent already exists; save work first
make doctor
make lsp-doctor         # deep Serena check after analyzable source exists
```

See [generic MCP/Agent Tools](docs/dependencies.md) and the
[Serena module setup and migration guide](docs/serena.md).
Existing Serena host bind state can be reused when the project identity
is unchanged; old Serena named volumes require manual migration.

## Network security change (migration required)

The former `isolated-dev` network was `internal: false`.
It is now `internal: true` with configurable `AGENT_SUBNET`
(default `auto`, which chooses an available /24 from the configured
network allocation pool). An existing unrestricted network **must not**
be silently reused. Run `make preflight` to
identify it, then explicitly run
`CONFIRM=YES make migrate-network` (after saving work).
That stops project containers using Compose `down` **without `-v`**,
preserving both default project-scoped Codex/Serena host bind directories
and existing PostgreSQL, cache or legacy Codex/Serena named volumes.

`make up` starts Squid separately dual-homed between internal and
outbound networks; Codex itself has no direct Internet route.
`make offline` removes Squid and leaves native intra-project DB access
available. Set additional denied CIDRs in `BLOCK_CIDRS` for host
public IPs, VPN and other sensitive networks.

`make remote-start` requires filtered Internet and the managed Codex
CLI. It must be rerun after agent container recreation; the daemon
is detached **inside** that container, not a host daemon.
See [docs/network-isolation.md](docs/network-isolation.md) for
remaining limitations and the Debian verification steps.
