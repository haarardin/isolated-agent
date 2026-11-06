# OpenCode V2 alongside Codex (initial integration)

The existing Codex CLI remains the default and works unchanged. OpenCode V2
is an optional **embedded Agent Tool** running in the **same rootless Podman
agent** with the same /workspace and installed MCP toolchain.

## Enable

In `dependencies/dependencies.toml`, change `enabled = false` to `true`
**only** for `id = "opencode"`. This installs pinned
`@opencode/cli@2.0.0` via npm in the Dependencies image. It does NOT remove
Codex or convert its auth. An image rebuild/recreate is necessary:

```bash
make deps-validate
make deps-plan
make build
make up
make opencode
make opencode-mcp
```

Configure an OpenCode LLM provider using its own supported authentication
mechanism. ChatGPT/Codex credentials are not implicitly reusable; never
commit provider secrets to the source repository or bake them into images.

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
