# OpenCode V2 + ProxyAPI: manual verification (PR #11)

This is a **manual** runbook for a **rootless Podman** host (Debian 13).
It tests the optional OpenCode runtime in the `feat/opencode-v2-optional-runtime`
branch. No API keys are checked in, put into `.env`, or baked into images.
`PROJECT_DIR` remains the only approved source-code bind.

**Prerequisites:** Podman rootless + podman-compose, Make, Python >=3.11,
a real project directory (or the included `./workspace` test directory),
working access to ProxyAPI with its API key and a supported model.
API calls can incur charges. Use a non-sensitive test repository.

## A. Select the branch and preserve local settings

```bash
cd /path/to/isolated-agent
git fetch origin
git switch feat/opencode-v2-optional-runtime
git pull --ff-only

# Only create .env when missing; do not overwrite an existing one.
test -f .env || cp .env.example .env
```

Edit `.env` and set `AGENT_RUNTIME=opencode`. Set `PROJECT_DIR` to your
approved host repository path. For an isolated scratch test, keep the default
`PROJECT_DIR=./workspace` and place a harmless `README.md` inside it.
Never point `PROJECT_DIR` at the isolated-agent checkout or your home
directory.

Enable the **existing** OpenCode Agent Tool in
`dependencies/dependencies.toml` by changing its `enabled = false` to
`enabled = true`. Keep its `install` and `state` entries intact.

## B. Prepare the isolated provider config

```bash
umask 077
test -e config/opencode.jsonc || cp config/opencode.example.jsonc config/opencode.jsonc
python3 -m json.tool config/opencode.jsonc >/dev/null
git check-ignore config/opencode.jsonc
```

Expected: JSON validation succeeds and `git check-ignore` prints
`config/opencode.jsonc`. This config is *outside* `PROJECT_DIR`, ignored
by Git, and mounted read-only at
`/opt/isolated-agent/opencode-user.jsonc` in the agent container.
The OpenCode wrapper sets `OPENCODE_CONFIG` to this path.

The example uses `proxyapi/qwen-flash` mapped to
`qwen/qwen3.8-flash`. Check the actual model ID in
https://proxyapi.ru/models/browse and edit `modelID` if necessary.
For other optional models, use
`config/opencode.proxyapi-multi.example.jsonc`; do not replace your
local config if you want to keep its settings.

**Do not paste your ProxyAPI key into `config/opencode.jsonc`.**
Connect it interactively in step D. An optional `env` declaration in the
example is for environments where the key is supplied securely; the default
container deliberately does not forward `PROXYAPI_API_KEY`.

OpenCode merges configuration sources. A higher-priority
`PROJECT_DIR/opencode.jsonc` or `PROJECT_DIR/opencode.json` could override
the external config; remove or inspect those project configs for this test.

## C. Static checks, build and container lifecycle

```bash
make deps-validate
python3 -m unittest discover -s tests -p 'test_agent_dispatch.py' -v
python3 -m unittest discover -s tests -p 'test_dependencies.py' -v
bash scripts/test-security-static.sh
make deps-plan
make build
make up
make recreate-agent
```

`make build` installs the pinned OpenCode binary when enabled. A
`make recreate-agent` is required when changing image contents or mounts,
not when only editing the host config file.

Check the binary, mount and runtime settings:

```bash
bash scripts/compose.sh exec agent /usr/local/bin/isolated-agent-opencode --version
bash scripts/compose.sh exec agent sh -c 'test -r /opt/isolated-agent/opencode-user.jsonc && test -d /root/.isolated-opencode'
```

Expected: V2 version and a successful file/state check. Custom model
availability should be checked after authentication in step D. To inspect mounted paths and options
without opening credentials:

```bash
podman inspect "$(bash scripts/service-id.sh agent)" --format '{{json .Mounts}}' | python3 -m json.tool
```

Confirm that `/opt/isolated-agent/opencode-user.jsonc` is a **read-only
bind** and `/workspace` is the intended source path. Never paste full
credential or environment dumps into issues.

## D. Authenticate and make a real request

```bash
make agent
```

In the TUI use `/connect` -> custom/Other -> `proxyapi` and enter the
existing ProxyAPI key. Use `/models` to select `proxyapi/qwen-flash`.
Exact menu wording depends on the CLI version.

A quick non-interactive auth check (do **not** show token data):

```bash
bash scripts/compose.sh exec agent /usr/local/bin/isolated-agent-opencode auth list
bash scripts/compose.sh exec agent /usr/local/bin/isolated-agent-opencode models proxyapi
```

Expected: authenticated provider `proxyapi` and your model alias listed.
If `models proxyapi` shows no models before connecting, that is not by
itself a failure; retry after `/connect`.

Test a **real** model request (charges a small number of tokens):

```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode run --model proxyapi/qwen-flash \
  "Respond with a short greeting in Russian; do not edit files."
```

Expected: a valid response and a corresponding usage entry in your
ProxyAPI dashboard. If there is a 401/403 check that `proxyapi`, not
`openai`, was authenticated. 404/model errors usually mean wrong model
ID or unavailable model in the ProxyAPI account; 402 may mean insufficient
balance. If the model answers but cannot use tools, use a model with
verified tool-calling support.

Next, test the agent reading only the approved workspace:

> Read README.md in this workspace and summarize it in Russian.
> Do not change any files.

If the scratch workspace has no README.md, create a harmless one on the host
before this request.

## E. MCP and Go checks (optional, only if installed)

The OpenCode CLI works without Serena. With the default dependencies
manifest, `make opencode-mcp` may show no MCP servers: **this is expected**.
To test Serena, merge the Go SDK and Serena entries from
`dependencies/examples/go-opencode-serena.toml` into your existing
`dependencies/dependencies.toml`, **without** removing other project tools.
Then repeat the `make deps-validate`, `make build`, `make recreate-agent`
commands.

```bash
make opencode-mcp
make lsp-doctor
```

Expected: Serena is listed as connected and the actual LSP probe
works **when the workspace contains a supported source project**. A
successful `mcp list` alone does not prove tool-call compatibility.
Ask OpenCode to locate a Go function through Serena and run a non-destructive
read-only analysis.

## F. State persistence and network boundary

Exit the OpenCode TUI and run:

```bash
bash scripts/compose.sh exec agent /usr/local/bin/isolated-agent-opencode auth list
make recreate-agent
bash scripts/compose.sh exec agent /usr/local/bin/isolated-agent-opencode auth list
make network-check
```

Expected: `proxyapi` remains authenticated after recreation and
`make network-check` passes in filtered-Web mode. For extra confidence,
resume an actual saved OpenCode session using `make agent` and
the CLI's continue/resume feature. Do not delete `volumes/` or run
`make reset-state`.

Editing `config/opencode.jsonc` later requires **only a new OpenCode CLI
process** to reload the provider settings; no container rebuild/recreation
is necessary. Adding/removing agent tools or altering mounts *does* require
a rebuild/recreate.

## Troubleshooting / merge gate

- `make agent` runs Codex: check `AGENT_RUNTIME=opencode` in `.env`.
- `OpenCode is not installed`: enable the tool in `dependencies.toml`,
  rebuild, and recreate. `make ensure-images` does not rebuild existing images.
- Missing config / symlink rejected: create a **regular file** by copying the
  example; do not symlink secrets from arbitrary host paths.
- `models proxyapi` shows nothing: check `OPENCODE_CONFIG`, custom provider
  schema, the selected model, and `auth list`.
- ProxyAPI requests fail: check `api.proxyapi.ru:443` via the configured
  Squid egress. `make network-check` validates general network isolation,
  not that this particular provider is reachable.
- Project configuration unexpectedly overrides ProxyAPI: OpenCode project
  config takes precedence over `OPENCODE_CONFIG`. Keep testing with a
  project that does not provide conflicting OpenCode settings.
- MCP fails: check whether Serena is enabled, whether its process starts,
  the configured `--context=codex`, and the Go project/LSP prerequisites.

**Do not merge this draft PR solely on the basis of static CI success.**
The Debian host must confirm: OpenCode build, ProxyAPI real response,
correct config mount, persistent auth/session, optional Serena MCP
if enabled, and unchanged rootless network protections.
