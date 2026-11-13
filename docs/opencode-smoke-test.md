# Manual acceptance: selectable coding agents / OpenCode V2 + ProxyAPI

Run on the **local Debian 13 rootless-Podman host**. These are manual
acceptance checks for the selectable coding-agent architecture, not a
substitute for testing the current image against a live provider.

**Important:** `AGENT_RUNTIME` in `.env` selects which installed coding
runtime starts, while `[[agents]].enabled` controls **installation**.
Both Codex and OpenCode may be enabled. `make build` installs **only**
enabled coding runtimes, with **no Node.js/npm for OpenCode itself**.
Node/npm can be requested separately for project or MCP requirements.

Use an **unimportant scratch workspace** for first-run tests.
Do not reset Codex state volumes or reveal credentials in logs/issues.

## A. Update the PR checkout and local environment

```bash
cd /path/to/isolated-agent
git status --short
git fetch origin
git switch main   # or remain on your intended feature branch
git pull --ff-only

test -f .env || cp .env.example .env
mkdir -p workspace
printf '# OpenCode smoke workspace\nThis repository is safe for test prompts.\n' > workspace/README.md
```

If `git status` shows important local modifications, save them before
switching. Do not change someone else's `.env` or `PROJECT_DIR`.

Edit **`.env`**:

```dotenv
AGENT_RUNTIME=opencode
PROJECT_DIR=./workspace
```

If you have an existing app you want to test, use its absolute path for
`PROJECT_DIR` instead.

## B. Enable only OpenCode (smallest test image)

Edit **`dependencies/dependencies.toml`** — these entries already exist,
so change just their `enabled` fields:

```toml
[[agents]]
id = "codex"
enabled = false
# Keep its [[agents.install]] and [agents.state] sections intact.

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

The actual `codex` entry with its install/state sections appears earlier
in the same TOML file; do not replace the whole document with this snippet.
OpenCode installs through its **official standalone shell installer** without
any version argument; the installer selects the latest release at build time.
The Debian Base does not install Node or npm.

Alternatively enable **both** agents by setting both `enabled = true`,
then switch only `AGENT_RUNTIME` to choose the CLI at launch.

## C. Create the gitignored provider configuration

```bash
umask 077
test -f config/opencode.jsonc || cp config/opencode.example.jsonc config/opencode.jsonc
python3 -m json.tool config/opencode.jsonc >/dev/null
git check-ignore config/opencode.jsonc
```

Expected: `git check-ignore` prints `config/opencode.jsonc`.
The provider settings live in **isolated-agent/config**, not in the
source-code `PROJECT_DIR`. The container mounts this **one file read-only**
at `/opt/isolated-agent/opencode-user.jsonc`; OpenCode uses
`OPENCODE_CONFIG` to read it. The system-level generated MCP config remains
at `/etc/opencode/opencode.json`.

The default `proxyapi` example maps `proxyapi/qwen-flash` to the upstream
identifier `qwen/qwen3.8-flash`. Confirm its availability at
https://proxyapi.ru/models/browse, and adjust the local `modelID`
if it is not offered. No API key belongs in this file, in `.env`,
the image, or Git. Enter it later via `/connect`.

The optional `config/opencode.proxyapi-multi.example.jsonc` shows
additional *illustrative* models through one proxy key. Because this
example contains JSONC comments, a strict `python3 -m json.tool` check
is only suitable for the **minimal** example above.

Project-level `opencode.json(c)` files may override provider settings.
For this first test, avoid conflicting project configs.

## D. Static preflight + real image build

```bash
make deps-validate
make deps-plan
python3 -m unittest discover -s tests -p 'test_dependencies.py' -v
python3 -m unittest discover -s tests -p 'test_agent_dispatch.py' -v
bash scripts/test-security-static.sh

make build
```

The dependency and runtime-dispatch tests are designed to run whether your
local `dependencies/dependencies.toml` enables Codex-only, OpenCode-only,
both, or neither: test cases explicitly set the agent combinations they
exercise, rather than assuming Codex is enabled in your edited manifest.
You do **not** need to enable Codex just to run the tests.

Expected: Base, Dependencies and Project images build successfully.
`make build` no longer needs the old standalone Codex image stage.
If `codex.enabled=false`, Codex is **not installed** in the new Dependencies
image. If `opencode.enabled=true`, the **native** CLI is installed;
Node.js/npm are not installed unless declared under `[apt]`, `[[install]]`,
or some enabled `[[agent_tools.install]]` (e.g. Node-based MCP).

Close any interactive sessions in the existing agent before recreating it.
After build:

```bash
make recreate-agent   # apply new image/mounts; replaces the old agent container
make up               # ensure filtered Squid internet egress is running
make doctor
```

Using `make recreate-agent` **before** `make up` is intentional when
switching installed agents: `make up` refuses to reuse an existing
container with stale agent-state mounts.

## E. Verify the active binaries and mounts

In the OpenCode-only container, `make doctor` invokes the **OpenCode
wrapper**, not the bare native executable. Even `opencode --version`
initializes its log file; direct invocation without XDG environment
overrides would try to write under `/root/.local/share/opencode/log/`
and fail on the intentionally read-only root filesystem. The wrapper
uses `/root/.isolated-opencode/{config,data,state}` in the existing
writable persistent volume, while `/root/.cache` remains the writable
cache. If updating only `scripts/doctor.sh`, run `git pull --ff-only`
and rerun `make doctor`; **no image rebuild or agent recreation is
needed** for this host-side doctor fix.


```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode --version

bash scripts/compose.sh exec agent sh -c \
  'test -r /opt/isolated-agent/opencode-user.jsonc &&
   test -w /root/.isolated-opencode'

make agent
```

Expected: a successfully reported OpenCode CLI version (whatever the current
upstream release is); state/config tests exit zero; `make agent` opens
OpenCode, **not Codex**. No version is pinned in the manifest.

For OpenCode-only (and no other Node dependencies), also check:

```bash
bash scripts/compose.sh exec agent sh -c \
  '! command -v codex && ! command -v node && ! command -v npm'
```

If you explicitly added Node-based MCP dependencies or SDKs, expect
`node`/`npm` to exist; that does not indicate OpenCode installed them.

To inspect mounts *without printing key values*:

```bash
podman inspect "$(bash scripts/service-id.sh agent)" --format '{{json .Mounts}}' | python3 -m json.tool
```

Check: `/workspace` points to the intended source directory; the
OpenCode user config mount is read-only; and with Codex disabled,
there is **no** `/root/.codex` persistent mount.

## F. Authenticate with the existing ProxyAPI key

In the OpenCode TUI:

1. `/connect` → custom/Other → `proxyapi`; enter your **existing** API key.
2. `/models` → `proxyapi/qwen-flash` (or the alias chosen in your config).
3. Ask: "Прочитай README.md и кратко объясни его содержимое по-русски.
   Ничего не изменяй."

Exact TUI labels may vary between V2 patch releases.

Exit the TUI and check without showing any token:

```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode auth list

bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode run --model proxyapi/qwen-flash \
  "Ответь одним предложением по-русски. Файлы не изменяй."
```

Expected: `proxyapi` appears as connected, a real model answer arrives,
and the ProxyAPI dashboard records activity. A 401/403 is an authentication
error; 404/model unavailable usually means the upstream model ID is wrong;
402 may mean insufficient balance. Tool calling must be tested separately
and depends on the specific model.

## G. Optional MCP + Go/Serena

You **do not** need Serena or Go to test the OpenCode CLI.
To enable the full Go example, merge only the needed entries from
`dependencies/examples/go-opencode-serena.toml` into your existing
`dependencies/dependencies.toml` (avoid losing other tools).

Then:

```bash
make deps-validate
make build
make recreate-agent
make up
make opencode-mcp
make lsp-doctor
```

`lsp-doctor` requires a workspace containing actual Go source files,
not the scratch README-only project. `make opencode-mcp` should show
Serena when enabled. A successful MCP list alone is not enough: ask
the agent to use a Serena tool and observe an actual Go symbol lookup.

If your MCP server needs Node, enable it separately in `[apt]` or that
tool's own `[[agent_tools.install]]` section — the OpenCode CLI never
forces this dependency.

## H. Session persistence, network checks and Codex switching

```bash
bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode auth list

make recreate-agent
make up

bash scripts/compose.sh exec agent \
  /usr/local/bin/isolated-agent-opencode auth list

make network-check
```

Expected: ProxyAPI authorization persists. Also confirm that the previous
OpenCode session can be resumed. Never run `make reset-state` during
smoke testing.

### Existing-container stop/start round trip

After leaving the OpenCode TUI and saving any in-progress work:

```bash
make stop
podman ps                  # this Compose project's agent/Squid should be stopped
make start
make doctor
make opencode-mcp
```

`make stop` records only already-running/paused Compose-managed services
of the selected `COMPOSE_PROJECT_NAME`, and `make start` restarts those
same container IDs, preserving previously stopped services. These commands
**do not verify PROJECT_DIR or Codex/OpenCode state mounts**, rebuild images,
or reconcile new dependencies; use `make build` / `make recreate-agent`
/ `make up` for configuration changes. The saved checkpoint is keyed by
the project identity, so run `make start` with the same project settings.
For this OpenCode-only test, neither command should require a
`/root/.codex` mount.

For the **dual-agent** configuration, set `codex.enabled=true` and
`opencode.enabled=true`, then rebuild/recreate once. From then on you can
switch without rebuilding:

```bash
make agent codex           # override .env just for this invocation
make agent opencode        # override .env just for this invocation
make agent                 # still uses AGENT_RUNTIME in .env
```

If Codex is enabled and not yet authenticated, use `make login`.
Codex Remote Control is Codex-specific and requires a running, installed
Codex runtime; it is not an OpenCode server.

## Acceptance and common errors

- Plain `make agent` starts the wrong CLI: inspect `AGENT_RUNTIME` in `.env`.
  To bypass the default for one invocation, use `make agent codex` or
  `make agent opencode`; no `.env` edit, rebuild or recreation is needed
  when both agents are already enabled.
- `make agent <runtime>` rejects the runtime: confirm its ID exists in
  `config/agent-runtimes.json` and is enabled under `[[agents]]` in
  `dependencies/dependencies.toml`. Only one positional runtime goal is
  allowed after `agent`.
- `disabled in [[agents]]`: enable that runtime; run `make build`,
  `make recreate-agent`, `make up`.
- `make doctor` fails with `EROFS` writing
  `/root/.local/share/opencode/log/opencode.log`: update the branch
  and rerun `make doctor`. The doctor must execute
  `/usr/local/bin/isolated-agent-opencode --version`, not the bare CLI;
  preserve `read_only: true` and the persistent XDG state mount.
- `opencode not found`: verify build logs for native installer,
  `install-opencode.sh` and selected agent flags. No Node/npm needed.
- The CLI may print a version with an arbitrary prefix or release number.
  Installation succeeds whenever the binary is executable and
  `opencode --version` exits successfully. There is **no** strict version
  pattern or comparison. A repeat `make build` may reuse the previous
  Podman image layer instead of downloading the latest upstream release;
  for a deliberate refresh see `docs/opencode.md` → Updating OpenCode.
- Missing local provider config: copy the example to
  `config/opencode.jsonc`; symlinks are rejected.
- Stale agent mounts error: stop active tasks and run `make recreate-agent`.
- ProxyAPI unreachable: confirm Squid filtered egress allows
  `https://api.proxyapi.ru/v1`; `make network-check` does not guarantee
  that a specific provider endpoint works.
- MCP missing: enable Serena separately under `[[agent_tools]]`, rebuild,
  and verify the `mcp list` and actual tool calls.
- Migrated Codex data must stay under the existing `CODEX_STATE_VOLUME`;
  disabling Codex does **not** delete its data.

Do **not** merge PR #11 based on static checks alone. Confirm the
native installer, selected runtime, ProxyAPI response, persistent state,
MCP when enabled, and the existing rootless network boundary locally.
