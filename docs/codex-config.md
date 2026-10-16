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

Rebuilding an image must not erase it. The named volume is configurable as `CODEX_STATE_VOLUME`; by default it is automatically derived from the canonical source `PROJECT_DIR` and `COMPOSE_PROJECT_NAME`.

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

Native `[features] memories = true` is the default in newly built project
images. Codex may persist `memories/`, `memories_1.sqlite`, sessions,
other SQLite databases, authentication and its CLI installation under
`/root/.codex`. File names can change between Codex versions; do **not**
mount just `memories/`. The entire `CODEX_HOME` is a single persistent
volume, selected by `CODEX_STATE_VOLUME`.

```dotenv
COMPOSE_PROJECT_NAME=codex-backend
PROJECT_DIR=/home/user/projects/backend
CODEX_FEATURE_MEMORIES=true
# Optional explicit choice of durable volume:
# CODEX_STATE_VOLUME=codex-backend-memory
# Optional Serena global-state volume (not project Serena memories):
# SERENA_STATE_VOLUME=serena-backend-state
```

```bash
make memory-info
make build-project      # required when changing CODEX_FEATURE_MEMORIES
make recreate-agent     # or make build-serena && make up-serena
make remote-start       # only if Remote Control is needed
```

The selected Codex state volume is uniquely derived from
`COMPOSE_PROJECT_NAME` and the **real absolute path of PROJECT_DIR** when
no explicit override is set. Changing PROJECT_DIR chooses a different
volume; using the same `CODEX_STATE_VOLUME` with two different
projects causes an explicit startup error. The identity marker lives
*inside* the persistent volume, so deleting a local `.state` directory
does not bypass the guard.

**A named volume survives container deletion and image rebuilding**,
but is not a backup: disk loss or `make reset-state` can delete it.
For valuable memories, regularly back up the volume while Codex is
fully stopped (do not copy live SQLite files while the daemon writes).

## Upgrading an existing Codex volume

**Do not run `make reset-state`.** The old default volume usually has
the name `<COMPOSE_PROJECT_NAME>_codex-state`. The new automatic
per-project name is different. We deliberately **do not** automatically
copy its auth/history/memories to arbitrary new repositories.

To keep the existing Codex state for the *same* repository:

1. Finish all active Codex sessions and stop Remote Control.
2. Inspect existing volumes with `podman volume ls` and identify the
   old Codex volume name for the correct project. Save a backup using
   `podman volume export <old-volume> --output backup.tar` while Codex
   is stopped.
3. In `.env`, set `CODEX_STATE_VOLUME=<old-volume>`. If using Serena,
   optionally set `SERENA_STATE_VOLUME=<old-serena-volume>`.
4. For the **first** container start only, set
   `CODEX_BIND_EXISTING_STATE=true` (and
   `SERENA_BIND_EXISTING_STATE=true` if a pre-populated Serena volume
   is being adopted). This explicitly claims the old volume for the
   currently selected PROJECT_DIR. It refuses to overwrite any data.
5. Run `make build-project && make recreate-agent` for the baseline,
   or `make build-project && make build-serena && make up-serena` for
   Serena. After successful startup, reset the
   `*_BIND_EXISTING_STATE` variables to `false` / comment them
   out. The volume's identity marker now prevents other PROJECT_DIR
   values from reusing that memory.
6. Verify `make doctor` and inspect the state without printing auth:

   ```bash
   make memory-info
   bash scripts/compose.sh exec agent sh -c 'test -w "$CODEX_HOME" && echo writable'
   ```

If you want a **fresh, separate** project instead, leave
`CODEX_STATE_VOLUME` unset and the new project receives its own volume.
The old volume is retained; nothing is deleted. If you change the
repository path but intend to migrate its memories, export/import the
volume after reviewing the provenance. Never point multiple
concurrently running agents at one Codex SQLite volume.

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
