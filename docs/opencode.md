# Coding agents: Codex and OpenCode V2

Both coding runtimes are **optional, independently installed** in the same
rootless Podman environment. The `[[agents]]` entries in
`dependencies/dependencies.toml` decide **what is installed**. The
`AGENT_RUNTIME` setting in the checkout's gitignored `.env` decides
**which installed CLI `make agent` launches**.

The default remains **Codex enabled / OpenCode disabled** for backwards
compatibility. This PR does not implicitly remove existing Codex
authentication, sessions, or project data.

## Architecture and installation

```text
Debian 13 Base (no Node.js/npm, no coding CLI)
  └── Dependencies image
        ├── enabled [[agents]]          Codex and/or OpenCode CLI
        ├── [[install]]                 Go/Python/other project SDKs
        └── [[agent_tools]]             MCP, LSP and other tools
      └── Project image                generated MCP + runtime defaults
          └── agent container          /workspace + only enabled agent states
```

The **normal** `make build` path is Base → Dependencies → Project;
`images/codex/Containerfile` and `make build-codex` remain only as legacy
manual tooling, not as a required image dependency.

`[[agents]]` schema:

```toml
[[agents]]
id = "codex"
enabled = true

[[agents.install]]
type = "script"
file = "install-codex.sh"
verify = ["codex --version"]

[agents.state]
base = "./volumes/codex"
target = "/root/.codex"

[[agents]]
id = "opencode"
enabled = true

[[agents.install]]
type = "script"
file = "install-opencode.sh"
verify = ["opencode --version"]

[agents.state]
base = "./volumes/opencode"
target = "/root/.isolated-opencode"
```

- `install-codex.sh` installs the **complete** official Codex standalone
  runtime, including the managed Remote Control app-server components.
- `install-opencode.sh` downloads **only the native V2 CLI** using
  `https://opencode.ai/v2/install` with `--no-modify-path` and **without
  a version argument**. It selects the latest available upstream release
  when that build step actually runs. **Node.js and npm are not installed
  for OpenCode.** The `verify = ["opencode --version"]` step only checks
  that the CLI starts; it never compares version numbers.
  They can be installed independently under `[apt].packages`/`[[install]]`
  or an MCP's `[[agent_tools.install]]` if a tool or application needs them.
- `agents.state` controls per-project persistent OpenCode state. For Codex,
  the existing host `CODEX_STATE_VOLUME` and legacy named-volume migration
  flags still override the directory selection to preserve prior state.
- `[[agent_tools]]` remains **only** for MCP/supporting tools (for example
  Serena). Do not put coding runtimes there. The generic tool `kind = "cli"`
  remains supported for non-agent helper executables.
- Do not set `AGENT_RUNTIME` to a disabled CLI. `make agent` fails before
  launching Compose. Changing which agents are **installed** requires
  `make build` and container recreation. Simply switching
  `AGENT_RUNTIME` between two already-installed agents requires neither.

Examples: Codex only (default): `codex=true`, `opencode=false`;
OpenCode only: `codex=false`, `opencode=true`;
both: `codex=true`, `opencode=true`.

### Updating OpenCode

There is no OpenCode version setting, version comparison, or background
updater in this PR. On a fresh image build, the official installer resolves
the latest release. **Podman layer caching can reuse a previously installed
binary** on later `make build` runs, so a repeated build is not guaranteed
to upgrade OpenCode. To force retrieval of the latest release explicitly:

```bash
make build DEPS_NO_CACHE=true
make recreate-agent
make up
```

`DEPS_NO_CACHE=true` passes `--no-cache` to the Dependencies image build
and fetches a fresh upstream OpenCode CLI. It also rebuilds other enabled
dependencies, potentially downloading or installing them again. Ordinary
`make build` can reuse cache and is recommended for the first installation
and most configuration changes. Close active agent sessions before
recreating the container.

## Provider configuration outside /workspace

OpenCode provider/model settings do **not** belong in `PROJECT_DIR`.
From the `isolated-agent` checkout:

```bash
umask 077
test -f config/opencode.jsonc || cp config/opencode.example.jsonc config/opencode.jsonc
```

The local `config/opencode.jsonc` is gitignored and **read-only** mounted
inside the container at `/opt/isolated-agent/opencode-user.jsonc`; the
OpenCode wrapper sets `OPENCODE_CONFIG` to that path. The immutable
`/etc/opencode/opencode.json` provides the centrally generated MCP
configuration. OpenCode merges configuration sources. Project-level
`opencode.json(c)` can override settings, so inspect those if model/MCP
behavior differs from expectations.

The default example defines `proxyapi` with
`https://api.proxyapi.ru/v1` and an **illustrative** model ID
`qwen/qwen3.8-flash`. Verify that the model and tool calling are available
in your ProxyAPI account. A multi-model example is in
`config/opencode.proxyapi-multi.example.jsonc`.

Do **not** store a ProxyAPI key in a JSON file, `.env`, image build args or
Git. Enter the existing key using OpenCode TUI `/connect` → custom/Other →
`proxyapi`, then select the configured model via `/models`. Credentials
and sessions are stored under the per-project
`./volumes/opencode/<project-key>` bind.

Changing only `config/opencode.jsonc` requires restarting OpenCode, **not**
rebuilding images. A local project config can override it. The same
container user can access both CLIs when both are enabled; the separate
config file is not a cross-agent secrecy boundary.

## Launch

After editing the manifest (OpenCode enabled), `.env`, and creating the
local provider config:

```bash
make deps-validate
make deps-plan
make build
make recreate-agent  # stop old sessions first; updates image and mounts
make up              # start/confirm Squid filtered egress
make doctor
make agent           # dispatches selected AGENT_RUNTIME
```

`make login` and Codex Remote Control only apply to **installed Codex**;
`make opencode`, `make opencode-mcp` and `make opencode-serve` only apply
to **installed OpenCode**. Direct commands remain available for
compatibility; `make agent` is the default entry point.

Headless read-only model test:

```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode run --model proxyapi/qwen-flash \
  "Привет. Ответь одним предложением."
```

## Serena MCP / Go

MCP entries remain in `[[agent_tools]]`, not `[[agents]]`. The generated
`.generated/codex-mcp.toml` and `.generated/opencode-mcp.json` read the
same enabled MCP entries. Use the reference manifest
`dependencies/examples/go-opencode-serena.toml` to install Go, Serena and
gopls. Merge the pieces into your own `dependencies.toml` and rebuild.

The current Serena example uses `--context=codex` even when paired with
OpenCode; verify the MCP handshake, tools and LSP with real Go sources.
OpenCode does not require Serena to run. Node/npm are independent tools:
an npm-based MCP server may still need them if explicitly configured.

## Verification and cautions

Follow **[OpenCode + ProxyAPI smoke test](opencode-smoke-test.md)** for
precise instructions and expected outcomes. Important checks:

- `make doctor` checks installed runtimes and container isolation.
- `make opencode-mcp` checks optional MCP connectivity.
- `make network-check` verifies rootless network boundary (not ProxyAPI
  API availability).
- After `make recreate-agent`, `opencode auth list` must still show
  the connected provider and session continuation should work.

Codex Remote Control and Go Agentic Bridge integrations are Codex-specific
or future work. This PR does not add a Go Agentic Bridge adapter for OpenCode
nor publish OpenCode API ports. Do not merge solely because static CI passes:
a real rootless Podman and ProxyAPI smoke test is required.

Official sources:
- https://opencode.ai/v2/docs
- https://opencode.ai/v2/install
- https://opencode.ai/docs/providers
- https://opencode.ai/docs/mcp-servers
