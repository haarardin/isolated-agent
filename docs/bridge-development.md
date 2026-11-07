# Agentic Bridge — four-repository local development on Debian 13

Status: infrastructure and mock fixture only. The current Go Bridge CLI
does not dispatch real commands to agents; the Bridge Server has no WSS
listener yet. This profile does NOT implement the missing applications.

## 1. Host prerequisites

Use a non-root user with functioning **rootless** Podman, podman-compose,
git, make, Python 3.11+ and network access to Go/Node/PyPI/npm/OCI registries.
Do not install Docker or expose podman.sock. On Debian 13:

```bash
sudo apt update
sudo apt install -y podman podman-compose git make python3 curl uidmap slirp4netns
podman info --format '{{.Host.Security.Rootless}}' # must print true
ip -4 addr show | grep -F '192.168.88.240'
```

The last command MUST find a host interface address if you intend to bind
ports directly to 192.168.88.240. This configuration does NOT assign that
address to a container. If it belongs to another machine/interface, use
an address actually owned by this host, or 127.0.0.1 for local-only tests.
Do not publish these unauthenticated dev services onto the public Internet.
Allow TCP 5173 and 8080 only from trusted LAN clients, if required.

## 2. Clone the four projects on the Debian HOST

Clone outside the isolated-agent checkout. Private GitHub repositories need
host-side Git authentication (prefer an SSH agent or a credential helper).
Never copy Git credentials, SSH keys, or host HOME into the Codex container.

```bash
mkdir -p "$HOME/dev/agentic-bridge-workspace"
cd "$HOME/dev/agentic-bridge-workspace"
git clone https://github.com/haarardin/agentic-bridge-cli.git
git clone https://github.com/haarardin/agentic-bridge-architecture.git
git clone https://github.com/haarardin/agentic-bridge-server.git
git clone https://github.com/haarardin/agentic-bridge-ui.git

# Separate checkout for isolated-agent runtime/configuration:
cd "$HOME/dev"
git clone -b setup/agentic-bridge-dev \
  https://github.com/haarardin/isolated-agent.git
cd isolated-agent
cp templates/AGENTS.bridge-workspace.md "$HOME/dev/agentic-bridge-workspace/AGENTS.md"
```

The four repositories stay independent (each owns its own .git, go.mod or
package.json), while the **parent** directory becomes one /workspace mount.
The architecture repository is essential shared context.

## 3. Select the dependency profile and bind IP

```bash
cd "$HOME/dev/isolated-agent"
cp .env.example .env
cp dependencies/examples/agentic-bridge-dev.toml dependencies/dependencies.toml

# Append overrides. PROJECT_DIR must be absolute and existing:
cat >>.env <<EOF
COMPOSE_PROJECT_NAME=agentic-bridge-dev
PROJECT_DIR=$HOME/dev/agentic-bridge-workspace
BRIDGE_BIND_IP=192.168.88.240
BRIDGE_UI_PORT=5173
BRIDGE_SERVER_PORT=8080
EOF
```

If .env.example already declares COMPOSE_PROJECT_NAME or PROJECT_DIR,
edit those lines IN PLACE instead of appending duplicates (Make reads both
through includes and the duplicate last assignment wins; minimize confusion).
Use `BRIDGE_BIND_IP=127.0.0.1` when LAN exposure is not needed.
If the host uses SELinux, check bind-mount labeling separately; do not
disable SELinux or broaden mounts without review.

## 4. Build and start

```bash
make deps-validate
make deps-plan
make preflight
make build
make bridge-up
make bridge-ps
make doctor
make network-check
```

The opt-in build adds Go 1.27.3, Node 24.11.1/npm, Python venv, gopls,
TypeScript LSP, Serena 1.7.0 (one MCP registration per checkout),
Playwright MCP 0.0.84 with bundled headless Chromium, PostgreSQL 18 and
Redis 8. Browser downloads can be large. Image builds fetch remote packages
on the host-side Podman builder; Codex remains on a single internal network
and reaches public websites only through filtered Squid.

`make bridge-up` publishes **only** the Codex container's dev ports
5173 and 8080 on BRIDGE_BIND_IP. Mock, PostgreSQL, Redis and Squid are
NOT published to the LAN. Mock is on the same internal network as Codex
and responds at http://mock-agent:8090. The Go CLI currently has no
adapter connecting to this mock; treat this as a fixture for integration work.

If the agent was already created without published ports, save active Codex
sessions first, then run `make remove-agent` and `make bridge-up`.
Do not use `make reset-state`: it deletes persistent data.

## 5. Authenticate Codex and check toolchain

```bash
make login               # device flow; auth stays in project-scoped CODEX_HOME
make shell
```

Inside the container:

```bash
go version
gopls version
node --version
npm --version
codex mcp list
curl --noproxy '*' -fsS http://mock-agent:8090/healthz
```

Serena repositories may need first-time project indexing/health checks;
from `make shell` run, for example:

```bash
/opt/agent-tools/serena/bin/serena project health-check /workspace/agentic-bridge-cli
/opt/agent-tools/serena/bin/serena project health-check /workspace/agentic-bridge-ui
```

Use project-specific Serena MCP registrations to avoid mixing LSP
workspaces; the default `make lsp-doctor` checks only /workspace as a
single project and is not the right deep check for this multi-repo layout.
For Go repos, gopls uses its own module. No root go.work is required.

## 6. Validate all codebases

Inside `make shell`:

```bash
for r in agentic-bridge-cli agentic-bridge-server; do
  (cd "/workspace/$r" && go test ./... && go vet ./...)
done
(cd /workspace/agentic-bridge-ui && npm ci && npm run typecheck && npm run lint && npm test && npm run build)
(cd /workspace/agentic-bridge-ui && npx playwright install chromium)
```

The architecture repository contains contracts/specs, not a Go module.
For browser tests, run `npm run test:e2e` from the UI directory after
installing its Playwright browser revision (different from the MCP
package's own pinned browser).

## 7. Run web/UI development servers (Codex can do this too)

From `make shell` (tmux processes persist while the agent is running):

```bash
tmux new-session -d -s bridge-server 'cd /workspace/agentic-bridge-server && go run ./cmd/agentic-bridge-server -listen 0.0.0.0:8080'
tmux new-session -d -s bridge-ui 'cd /workspace/agentic-bridge-ui && npm run dev -- --host 0.0.0.0 --port 5173'
tmux list-sessions
```

On another trusted LAN device:

- UI (currently using its own mock data): http://192.168.88.240:5173
- Go Server skeleton: http://192.168.88.240:8080/healthz

Check: `curl -fsS http://192.168.88.240:8080/healthz`.
Do not misread a working UI or healthz as completed Bridge integration.
Stop an individual dev server with `tmux kill-session -t bridge-ui`
(or `bridge-server`).

## 8. Private mock agent smoke test

From the Codex container, query the private service. It accepts a
minimal **Bridge-style envelope carried over HTTP POST**, not actual
Bridge Server WebSockets, and returns deterministic in-memory replies.
The mock deliberately does not run shell commands or execute code.

```bash
curl --noproxy '*' -sS http://mock-agent:8090/healthz

curl --noproxy '*' -sS -X POST http://mock-agent:8090/rpc \
  -H 'Content-Type: application/json' \
  -d '{"version":0,"id":"10e16d2d-d10f-4f49-80e1-d80bde5c3aac","method":"server:session.create","error":"","params":{"agent_id":"mock","workspace_key":"agentic-bridge-cli","command_id":"285895e5-1a8c-45fd-9f2e-0e11b03e2211"}}'

curl --noproxy '*' -sS -X POST http://mock-agent:8090/rpc \
  -H 'Content-Type: application/json' \
  -d '{"version":0,"id":"8ef37f3e-7c5c-4a23-ad6e-16a8983a2c3d","method":"server:turn.start","error":"","params":{"agent_id":"mock","workspace_key":"agentic-bridge-cli","session_id":"mock-session-285895e5-1a8c-45fd-9f2e-0e11b03e2211","command_id":"4698a3cc-5170-4d30-bf17-759402900762","input":[{"type":"text","text":"Implement a sample task"}]}}'

curl --noproxy '*' -sS http://mock-agent:8090/v1/turns/mock-turn-4698a3cc-5170-4d30-bf17-759402900762
```

Expected: an accepted reply and a completed turn with a simple mock
message, not real agent execution. No network, credential, or shell
control is granted by this mock. Current CLI does not send to it;
adding the adapter/dispatcher is a separate application task.

## 9. Lifecycle

```bash
make bridge-ps
make bridge-logs
make bridge-down     # stops/removes this dev stack, preserves volumes
make bridge-up       # start again with current images
make codex           # start interactive agent
```

For edits to the dependency TOML, rebuild: `make build-project`,
then save active Codex turns and `make recreate-agent`. The latter
recreates with the BASE compose set, which can drop overlay-published
ports; for Bridge, use `make remove-agent` followed by
`make bridge-up` instead after the backup. Do not use the generic
`make up` when you specifically need the Bridge overlay.

## Known blockers (not solved by this infrastructure commit)

1. CLI advertises no actual agent/workspace and returns
   UNSUPPORTED_CAPABILITY; no running native Codex adapter or mock adapter.
2. Go Server has only GET /healthz, no CLI WSS endpoint/auth/task routing.
3. UI is mocked and not yet integrated with an authenticated Go Server.
4. The mock's GET /v1/turns is test-only HTTP polling; production must
   map terminal events to the accepted Bridge RPC contract and enforce
   Node/workspace admission. Do not expose the fixture on an external port.
