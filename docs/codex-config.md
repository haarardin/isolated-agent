# Codex configuration

This project intentionally separates three types of Codex state.

## 1. Image defaults

Generated in the final image at:

```text
/etc/codex/config.toml
```

These are controlled by build arguments from `.env`.

They define safe/reproducible project defaults such as model reasoning effort, approval policy, sandbox mode, network access, and web-search behavior.

## 2. Persistent Codex home

Mounted by Compose at:

```text
/root/.codex
```

It contains authentication and Codex-managed persistent state.

Rebuilding an image must not erase it. By default, `CODEX_HOME` is bind-mounted from `./volumes/codex/<project-key>` in the root of the isolated-agent checkout; the directory is created automatically before container startup. A bare Podman volume name remains supported for legacy projects.

The startup script only refreshes the image-owned global `AGENTS.md`; it does not clear or recreate the rest of the directory.

## 3. Repository configuration

The target repository is mounted at:

```text
/workspace
```

It can provide:

```text
AGENTS.md
AGENTS.override.md
.codex/config.toml
```

Codex applies configuration/instructions by scope and precedence. Project configuration should contain settings that genuinely belong to the source repository, while image defaults should describe the isolated execution environment.

## Native Codex memory and persisted state

`CODEX_FEATURE_MEMORIES=true` enables native memory in new builds.
Codex may store `memories/`, SQLite database files, sessions, credentials
and other metadata directly in `CODEX_HOME`. For this reason we bind the
**entire** `/root/.codex` directory rather than only `memories/`.

### Default directories (next to the project's images/ and Makefile)

```text
isolated-agent/
  images/...
  Makefile
  .env
  volumes/
    codex/<project-key>/        -> /root/.codex
    serena/<project-key>/       -> /root/.serena
```

In `.env` (the defaults are also in `.env.example`):

```dotenv
COMPOSE_PROJECT_NAME=codex-backend
PROJECT_DIR=/home/user/projects/backend
CODEX_FEATURE_MEMORIES=true

CODEX_STATE_VOLUME=./volumes/codex
SERENA_STATE_VOLUME=./volumes/serena
```

These two variables identify **host base directories**, not named
volumes. The system automatically appends `<project-key>`, derived
from canonical `PROJECT_DIR` and `COMPOSE_PROJECT_NAME`; multiple
projects in one isolated-agent checkout therefore get independent
subdirectories and volume identity markers.

```bash
make memory-info     # print exact resolved paths (no credentials)
make up              # creates both missing directories before starting
make recreate-agent  # deploy updated mount if agent already existed
make remote-start    # only for Remote Control
```

`make offline` and `make up-serena` also prepare the directories.
The `volumes/` tree is gitignored. **Do not commit or share it**:
it includes Codex authentication and session history.

Named volumes are **still supported for compatibility**. When
`CODEX_STATE_VOLUME` is a bare name without a slash or leading
`.` (for example `isolated-agent-demo_codex-state`), that exact
existing Podman named volume is used; the equivalent behavior applies
to `SERENA_STATE_VOLUME`. An explicit host path uses a bind mount.

The startup identity marker refuses accidental reuse of memory belonging
to another project, including when the user explicitly supplies the
same host base directory to different projects. Files are never
automatically deleted. Switching `PROJECT_DIR` selects a new child
folder; the previous folder remains on disk.

Container deletion, image rebuilding and ordinary Compose `down`
do not delete these directories. They **are not automatic backups**:
for valuable state, stop Codex before copying the entire directory
(including SQLite database and WAL files), and store encrypted backups
outside the source checkout.

## Upgrading an existing Codex volume

**Do not run `make reset-state`.** Existing setups used a Podman
named volume such as `<COMPOSE_PROJECT_NAME>_codex-state`. Switching
straight to the new default local directory will start with an empty
Codex home: **the old auth and memories are not deleted**, but they
are not automatically copied either.

To preserve the previous Codex sessions and login with zero migration
risk, explicitly keep the old volume name in `.env`:

```dotenv
CODEX_STATE_VOLUME=isolated-agent-demo_codex-state
CODEX_BIND_EXISTING_STATE=true
# Optional if you also use an old Serena named volume:
# SERENA_STATE_VOLUME=isolated-agent-demo_serena-state
# SERENA_BIND_EXISTING_STATE=true
```

Explicitly selected named volumes are now checked before Compose startup.
A typo does not silently create a new blank home. To intentionally create a
NEW named volume, temporarily set `CODEX_CREATE_NAMED_VOLUME=true`
(or `SERENA_CREATE_NAMED_VOLUME=true`) in .env and turn it off after
startup. This is separate from `CODEX_BIND_EXISTING_STATE`, which opts
in to claiming an already-populated legacy volume.

Before the first start, confirm the real name with `podman volume ls`,
stop Codex and Remote Control, and export a backup using
`podman volume export <volume-name> --output backup.tar`.

Run `make build-project && make recreate-agent` (or rebuild
the Serena image and use `make up-serena`). Once the identity marker
has been written, change `CODEX_BIND_EXISTING_STATE` back to
`false`. Your old named volume and its entire contents are retained.

To **move** old memory into the new repository-local bind directory
instead, stop the Codex container, back up/export the old volume,
copy its entire contents into the `make memory-info` Codex directory
while preserving permissions, and use
`CODEX_BIND_EXISTING_STATE=true` **once** to claim the pre-populated
directory. Do not extract an untrusted archive or move only the
`memories/` folder: the related SQLite state may live elsewhere.
Verify authentication, sessions and native memories before deleting
any old volume.

`SERENA_STATE_VOLUME` only concerns **global** Serena state:
project-level Serena memories remain in
`PROJECT_DIR/.serena/memories/` and are preserved with that workspace.

## Default autonomous profile

The initial skeleton uses:

```toml
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "high"
approval_policy = "never"
sandbox_mode = "danger-full-access"
file_opener = "none"
web_search = "cached"
project_doc_max_bytes = 65536

[shell_environment_policy]
ignore_default_excludes = false

[features]
memories = true
```

Rationale:

- the outer rootless Podman container is the primary host security boundary;
- `approval_policy = "never"` allows unattended/non-interactive tasks;
- `danger-full-access` disables Codex's nested Linux sandbox inside the already-isolated Podman container;
- rootless Podman remains the effective filesystem/process/network boundary;
- this avoids Bubblewrap failures caused by nested user/network namespace restrictions;
- cached web search is the safer default for routine development and can be changed to `live` per project;
- common secret-bearing environment variable names remain filtered from spawned shell commands;
- Native Codex memories are enabled by default and may be disabled per project via CODEX_FEATURE_MEMORIES=false (requires image rebuild).

Do not add Podman privileges or capabilities merely to make nested Bubblewrap work. If you intentionally switch to `workspace-write`, do so only on a runtime where the Codex Linux sandbox can initialize successfully.

## Reference

Current Codex configuration schema:

```text
https://developers.openai.com/codex/config-schema.json
```

When adding new build arguments, verify the exact key and allowed values against the current Codex documentation/schema before committing them.


## Secrets

Never pass credentials through Containerfile `ARG` values.

Build arguments can be retained in image/build metadata and are not designed for secrets. Keep ChatGPT/Codex authentication in the persistent `CODEX_HOME` volume and use runtime secret mechanisms for project credentials.


## Why the default is danger-full-access

On Linux, Codex's restricted sandbox uses a Bubblewrap-backed execution path. Inside rootless Podman, an additional user namespace can fail before the requested command starts, for example:

```text
bwrap: setting up uid map: Operation not permitted
```

This template already provides the outer isolation layer, so the default disables the redundant nested sandbox instead of weakening Podman with extra privileges.

The setting is intentionally scoped to the Codex process **inside this container**. It does not bypass Podman's mount, capability, read-only-rootfs, or network restrictions.
