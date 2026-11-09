# Serena as a shared embedded MCP Agent Tool

Serena is **optional** and is declared **once** under `[[agent_tools]]` in
`dependencies/dependencies.toml`. Codex and OpenCode are separate, optional
coding runtimes declared under `[[agents]]`. Enabling Serena installs **one
Serena executable and Python environment** in the Dependencies image,
regardless of which coding runtimes are enabled. The generated MCP registry
adds the same tool to both clients:

- Codex: `/etc/codex/config.toml` (from `.generated/codex-mcp.toml`).
- OpenCode: `/etc/opencode/opencode.json` (from `.generated/opencode-mcp.json`).

With **stdio** transport, each active MCP client starts its *own Serena
process* from that one installed executable. This is not a persistent
shared Serena daemon, and concurrent sessions can use additional memory and
language-server resources. The Serena home state is separately mounted at
`/root/.serena`; project configuration/memories may also reside under
`/workspace/.serena`. Those are not extra mounts outside the approved project
and tool-state directories.

## Enable Serena

Keep the existing `[[agents]]` settings unchanged. OpenCode-only
(`codex.enabled=false`, `opencode.enabled=true`) is supported; no need
to install Codex to use Serena. For a basic connection test, make sure
`[apt].packages` includes `python3`, `python3-venv`, and
`python3-pip` (merge with existing packages). Add the following to the
active `dependencies/dependencies.toml`, **above** `[project]`:

```toml
[[agent_tools]]
id = "serena"
kind = "mcp"
placement = "embedded"
enabled = true

[[agent_tools.install]]
type = "command"
run = "python3 -m venv /opt/agent-tools/serena && /opt/agent-tools/serena/bin/pip install --no-cache-dir 'serena-agent==1.7.0'"
verify = ["/opt/agent-tools/serena/bin/serena --help >/dev/null"]

[agent_tools.state]
base = "./volumes/serena"
target = "/root/.serena"

[agent_tools.integration]
transport = "stdio"
command = "/opt/agent-tools/serena/bin/serena"
args = ["start-mcp-server", "--project=/workspace", "--context=codex", "--transport=stdio", "--enable-web-dashboard=false", "--open-web-dashboard=false", "--enable-gui-log-window=false"]
```

This reproduces the existing Serena 1.7 example. The shared
`--context=codex` value is passed even when OpenCode connects: the
generated MCP integration currently has **one set of launch arguments**
for both clients. MCP registration can work with that setting, but the
Serena context can influence the tools it exposes. Separate per-client
contexts would require another feature, not another installation.

The minimal setup does **not** require Go, `gopls`, `clangd`, Node.js or
npm. Install them only when the workspace needs them:

- Go + `gopls`: merge the Go SDK and gopls installation steps from
  [OpenCode + Go + Serena](../dependencies/examples/go-opencode-serena.toml),
  or [Codex + Go + Serena](../dependencies/examples/go-serena.toml).
  These examples intentionally include additional C++ dependencies.
- C/C++ with `clangd`: add `clangd` to `[apt].packages` and use
  `[agent_tools.lsp]` with `adapter = "serena"` and
  `servers = { cpp = "/usr/bin/clangd" }`. This explicit binding configures
  Serena's persistent global state without trusting a project-specific
  override. See [LSP configuration](dependencies.md#explicit-agent-tool-lsp-bindings-serena-adapter).

Only keep one `[[agent_tools]] id = "serena"` entry. Do not duplicate it
to "make Serena for Codex" and "make Serena for OpenCode."

## Build, start and verify

```bash
make deps-validate
make deps-plan
make build-project     # rebuild Dependencies + Project image; Base already built
make recreate-agent    # for an already-running agent; close sessions first
make up                # ensure filtered Squid egress is running
make doctor

# Verify installed Serena CLI independently of any MCP client:
bash scripts/compose.sh exec agent /opt/agent-tools/serena/bin/serena --help

# Verify OpenCode MCP registration/connection when OpenCode is enabled:
make opencode-mcp
make agent             # with AGENT_RUNTIME=opencode
```

In OpenCode, ask the model to call a **Serena tool** against the current
workspace, without modifying files. Check the actual tool invocation, not
just that a server name appears in a list. When Codex is also enabled, its
MCP registration comes from the same `[[agent_tools]]` entry. For a
Codex-only session use `make agent AGENT_RUNTIME=codex` and inspect
the registered tools there; `make opencode-mcp` requires OpenCode enabled.

For real Go/C++ symbol analysis, use a workspace with source files and
the appropriate language server installed. If `[agent_tools.lsp]` is
configured, `make lsp-doctor` runs the language-server health probe.
A README-only scratch workspace is not a suitable semantic-analysis test.
There is no special `build-serena`, `up-serena` or dedicated Serena
Compose profile.

## Migration from the removed legacy Serena layer

PR #7 and older revisions exposed a dedicated
`images/serena/Containerfile`, `compose.serena.yaml`, `make up-serena`,
and `SERENA_STATE_VOLUME`. These interfaces have been **removed**.

Before updating an existing deployment:

1. Stop active Codex/OpenCode/Remote Control work and back up the **entire**
   Codex state, Serena global state and workspace (including SQLite WAL
   files). Do not run `make reset-state` or delete Podman volumes.
2. Remove legacy `SERENA_IMAGE`, `SERENA_STATE_VOLUME`,
   `SERENA_BIND_EXISTING_STATE`, `SERENA_CREATE_NAMED_VOLUME`,
   `SERENA_VERSION` and `SERENA_GOPLS_VERSION` from `.env`
   after recording their previous values.
3. Add the generic Serena `[[agent_tools]]` configuration to
   `dependencies/dependencies.toml`, including
   `[agent_tools.state]` with `base = "./volumes/serena"` and
   `target = "/root/.serena"`. If the old agent used the dedicated
   Serena image (even with no `SERENA_*` entries in `.env`), the
   migration guard will refuse provisioning until you explicitly
   remove that old agent container after backing up the state.

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

Build and switch only after migration, with the old container intentionally
removed **after** you have backed up its state and verified the generic
Serena persistent mount is the same intended directory:

```bash
make deps-validate
make build-project
make remove-agent      # explicit migration step; preserves named/bind volumes
make up                # creates the Project image-based agent
make doctor
```

For already migrated Project image agents, use `make recreate-agent`
instead. The migration guard checks both legacy `.env` keys and the
actual existing Podman Compose agent's image/environment, so a legacy
default-config installation cannot silently lose its active Serena MCP.
An existing generic Project image with a `/root/.serena` Agent Tool mount
continues to be supported.

`make start` merely resumes previously stopped containers and **cannot
switch an existing legacy Serena image** to the generic Project image.

## Diagnostics, limitations and safety

Run `make doctor` for runtime checks, `make opencode-mcp` when OpenCode is
enabled, and `make lsp-doctor` for enabled LSP bindings after creating
analyzable source. Serena 1.7 may skip files of 1000 bytes or less
during health checks. In Codex use its MCP tools view; Go symbol
analysis requires the Go SDK and gopls, as shown in the examples.

The current LSP adapter only supports known Serena bindings and does
not automatically remove previously written `ls_path` values from
persistent `serena_config.yml` when a TOML LSP mapping is removed.
Back up the file before manually cleaning obsolete values and preserve
user-owned settings. Details: [LSP configuration](dependencies.md).

Serena executes with the same container access as the active Codex or
OpenCode client inside rootless Podman; it is **not** an additional security
boundary. Review source
changes and avoid sharing the same persistent state across unrelated
projects. Indexing can be resource-intensive. Token savings remain
a hypothesis to benchmark, not a guarantee.
