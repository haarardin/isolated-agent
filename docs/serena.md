# Serena as a universal embedded MCP Agent Tool

Serena is **optional**. The agent's Debian Base, Codex and Project images
contain no dedicated Serena installation. Install it exactly like any other
embedded MCP tool by adding a `[[agent_tools]]` entry to
`dependencies/dependencies.toml`. The example is
[`dependencies/examples/go-serena.toml`](../dependencies/examples/go-serena.toml).

## Configure and start

The example explicitly opts into Python, Serena 1.7, Go, gopls and clangd.
For non-Go projects, include only the language SDKs and language servers
that the target project requires. Copy the relevant `[[agent_tools]]`
entry, installation steps and state/LSP settings into your active TOML.
The optional Go-specific `[project]` recipes are examples, not defaults.

```toml
[[agent_tools]]
id = "serena"
kind = "mcp"
placement = "embedded"
enabled = true

[[agent_tools.install]]
type = "command"
run = "python3 -m venv /opt/agent-tools/serena && /opt/agent-tools/serena/bin/pip install --no-cache-dir 'serena-agent==1.7.0'"

[agent_tools.state]
base = "./volumes/serena"
target = "/root/.serena"

[agent_tools.lsp]
adapter = "serena"
servers = { cpp = "/usr/bin/clangd" }

[agent_tools.integration]
transport = "stdio"
command = "/opt/agent-tools/serena/bin/serena"
args = ["start-mcp-server", "--project=/workspace", "--context=codex", "--transport=stdio", "--enable-web-dashboard=false", "--open-web-dashboard=false", "--enable-gui-log-window=false"]
```

This is an illustrative module configuration; install `python3`,
`python3-venv` and `clangd` in `[apt].packages` as necessary.
The `[agent_tools.lsp]` binding is optional for non-C/C++ usage but
recommended for offline C/C++ with local clangd; declaring it requires
an installed executable at `/usr/bin/clangd`. Serena's LSP adapter
currently assumes Python beside the declared Serena executable.

```bash
make deps-validate
make deps-plan
make build-project       # regenerate dependencies and the Project image
make up                  # first startup; starts only enabled Agent Tools
make doctor
make lsp-doctor          # deep Serena LSP check when source files exist
make codex               # use /mcp to inspect registration
```

For an already-running container, **save/close Codex turns** and run
`make recreate-agent` after rebuilding the image. Use
`make up-example` only if you also require example PostgreSQL/Redis.
There is no special `build-serena`, `up-serena` or Serena Compose profile.

The generated MCP stanza appears in the Project image's
`/etc/codex/config.toml`; no MCP port, host runtime socket or
privileged container is required. Agent Tool state gets a project-scoped
persistent host path and is mounted at `/root/.serena`. The source
project's `/workspace/.serena` files live in the workspace bind mount.
Serena is not installed or started if the TOML module is absent/disabled.

## Migration from the removed legacy Serena layer

PR #7 and older revisions exposed a dedicated
`images/serena/Containerfile`, `compose.serena.yaml`, `make up-serena`,
and `SERENA_STATE_VOLUME`. These interfaces have been **removed**.

Before updating an existing deployment:

1. Stop active Codex/Remote Control work and back up the **entire**
   Codex state, Serena global state and workspace (including SQLite WAL
   files). Do not run `make reset-state` or delete Podman volumes.
2. Remove legacy `SERENA_IMAGE`, `SERENA_STATE_VOLUME`,
   `SERENA_BIND_EXISTING_STATE`, `SERENA_CREATE_NAMED_VOLUME`,
   `SERENA_VERSION` and `SERENA_GOPLS_VERSION` from `.env`
   after recording their previous values.
3. Add the generic Serena `[[agent_tools]]` configuration to
   `dependencies/dependencies.toml`, including
   `[agent_tools.state]` with `base = "./volumes/serena"` and
   `target = "/root/.serena"`.

If the old installation used the default local Serena bind directory
`./volumes/serena/<project-key>`, the generic module resolves the
**same host directory** when `COMPOSE_PROJECT_NAME` and canonical
`PROJECT_DIR` are unchanged. Existing global settings survive. The
generator never clears the directory on startup.

**If the old installation selected a named Serena Podman volume**, the
generic Agent Tool format does **not** accept named volumes for tool
state. Do not assume the existing state will be mounted or copied
automatically. First identify and back up the volume with
`podman volume ls` and `podman volume export NAME --output backup.tar`;
then, with the agent stopped, restore its complete contents to the
correct project-scoped bind directory under `./volumes/serena/`
while preserving permissions/ownership. Inspect the
`.isolated-agent-project-key` marker and verify it matches the expected
project before switching; never overwrite another project's state.
Do not remove the old Podman volume until configuration, projects and
Serena indexing are verified. Project-level memories under
`PROJECT_DIR/.serena/memories/` remain with the source checkout.

Build and switch only after migration:

```bash
make deps-validate
make build-project
make recreate-agent
make doctor
```

`make start` merely resumes previously stopped containers and **cannot
switch an existing legacy Serena image** to the generic Project image.

## Diagnostics, limitations and safety

Run `make doctor` for runtime validation and `make lsp-doctor` when
analyzable source exists. Serena 1.7 may skip files of 1000 bytes or
less during health checks. In Codex, `/mcp` lists registered modules.
For Go work, install gopls explicitly as in the example.

The current LSP adapter only supports known Serena bindings and does
not automatically remove previously written `ls_path` values from
persistent `serena_config.yml` when a TOML LSP mapping is removed.
Back up the file before manually cleaning obsolete values and preserve
user-owned settings. Details: [LSP configuration](dependencies.md).

Serena executes with the same access as the Codex agent inside rootless
Podman; it is **not** an additional security boundary. Review source
changes and avoid sharing the same persistent state across unrelated
projects. Indexing can be resource-intensive. Token savings remain
a hypothesis to benchmark, not a guarantee.
