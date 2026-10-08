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

Rebuilding an image must not erase it.

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
memories = false
```

Rationale:

- the outer rootless Podman container is the primary host security boundary;
- `approval_policy = "never"` allows unattended/non-interactive tasks;
- `danger-full-access` disables Codex's nested Linux sandbox inside the already-isolated Podman container;
- rootless Podman remains the effective filesystem/process/network boundary;
- this avoids Bubblewrap failures caused by nested user/network namespace restrictions;
- cached web search is the safer default for routine development and can be changed to `live` per project;
- common secret-bearing environment variable names remain filtered from spawned shell commands;
- Codex memories remain opt-in while the feature is experimental.

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
