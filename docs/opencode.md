# OpenCode V2 alongside Codex (initial integration)

The existing Codex CLI remains the default and works unchanged. Selection
is controlled by `AGENT_RUNTIME` in `.env`, with `make agent` as the shared
entrypoint. Registered runtimes live in `config/agent-runtimes.json`. OpenCode V2
is an optional **embedded Agent Tool** running in the **same rootless Podman
agent** with the same /workspace and installed MCP toolchain.

## Enable

In `dependencies/dependencies.toml`, change `enabled = false` to `true`
**only** for `id = "opencode"`. Set `AGENT_RUNTIME=opencode` in `.env`.
Keep provider/model settings OUTSIDE the source workspace: they belong to
this `isolated-agent` checkout, not the Go/CAD/etc project.

```bash
umask 077
cp config/opencode.example.jsonc config/opencode.jsonc
# edit config/opencode.jsonc to select your models / provider
```

`config/opencode.jsonc` is gitignored and is mounted read-only at
`/opt/isolated-agent/opencode-user.jsonc` inside the container. The launcher
sets `OPENCODE_CONFIG` to that path. **The file is not baked into any image,
not copied into the workspace, and not exposed to the Codex CLI.**
Neither the optional CLI nor this config requires a project-level
`PROJECT_DIR/opencode.jsonc`; do not create one. The project itself can
still supply a higher-precedence project config, so inspect that if behavior
seems overridden.

This selects the OpenCode CLI when running `make agent`. This installs pinned
`@opencode/cli@2.0.0` via npm in the Dependencies image. It does NOT remove
Codex or convert its auth. An image rebuild/recreate is necessary:

```bash
make deps-validate
make deps-plan
make build
make up
make agent
make opencode-mcp
```

The checked-in example uses **ProxyAPI** as an OpenAI-compatible custom
provider; it only declares the endpoint and an illustrative model ID.
Confirm the exact model ID supported by your ProxyAPI account and adjust it.
After `make agent`, use `/connect` → `Other` → `proxyapi` to enter the
existing ProxyAPI key, then `/models` to select the model. The example also
allows `PROXYAPI_API_KEY` as an optional environment variable, but does not
put any secret in the JSON file. Avoid storing keys in `.env`, image build
args or the checked-in example. ChatGPT/Codex credentials are not reusable
implicitly.

To change provider/model configuration, edit the local file and start a
**new OpenCode process** (`make agent`); no image rebuild or Compose
recreation is required. Switching between projects reuses the local config
while each project's OpenCode state remains independently scoped.

Changing `AGENT_RUNTIME` only changes which existing CLI is launched.
It does not install an agent. To add a new runtime later, install its CLI
via the dependencies mechanism and add its executable argv to
`config/agent-runtimes.json`. Unknown runtime names fail before Podman is
invoked. The existing `make codex` and `make opencode` commands are retained
as direct-launch compatibility aliases.

For headless execution after authentication:

```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode run "Explain this Go repository"
```

For a **foreground API** on the container's loopback, with no published host
port:

```bash
make opencode-serve
```

This initial PR does not implement Go Agentic Bridge HTTP/SSE/API access,
remote approvals, or a long-lived service supervisor. API security and
session/event mapping are separate follow-ups.

## Isolation / persistence

- An opt-in, project-scoped state bind is generated automatically:
  `./volumes/opencode/<project-key>:/root/.isolated-opencode:rw`. The key
  is based on `COMPOSE_PROJECT_NAME` and canonical `PROJECT_DIR`.
- The `isolated-agent-opencode` wrapper redirects XDG config/data/state
  to the above mount. Its cache uses existing `/root/.cache`.
- The only extra agent bind for the provider configuration is the single
  read-only `config/opencode.jsonc` file from the isolated-agent checkout.
  `make up`/state-preparation fail with a helpful message if this file is
  missing or a symlink. It is deliberately not a bind to the repository
  directory. Credentials entered via `/connect` go into persistent XDG
  state, not the config example.
- `.generated/opencode-mcp.json` is generated from the **same** enabled
  `agent_tools` MCP entries as Codex and copied to the V2 system path
  `/etc/opencode/opencode.json`. V2 requires `mcp.servers`; V1's
  `mcp.<name>` layout is intentionally not supported.
- Local stdio MCP servers remain processes inside the agent. Sidecar HTTP
  uses the existing internal DNS alias; external MCP requires HTTPS.
- Current rootless Podman containment, limited /workspace, read-only rootfs,
  dropped capabilities, Squid egress isolation and no host Podman/Docker
  socket remain intact.

Serena's current `--context=codex` declaration is reused verbatim.
Verify its tool availability and behavior with OpenCode before depending on
it. OpenCode models and authentication are independent of Codex.

## Verify

```bash
python3 -m unittest discover -s tests -p 'test_dependencies.py' -v
bash scripts/test-security-static.sh
make deps-generate
make deps-validate
```

On the target Debian 13 / rootless Podman host, additionally verify
`opencode --version`, provider authentication, `make opencode-mcp`, a
real headless task, and session recovery after recreate. Live Podman and LLM
smoke tests are **not** part of the static CI checks.

References:
- https://opencode.ai/v2/docs
- https://opencode.ai/v2/docs/mcp-servers
- https://opencode.ai/v2/docs/cli
- https://opencode.ai/v2/docs/cli/web/
- https://opencode.ai/v2/docs/api
