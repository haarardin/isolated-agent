# Optional Serena MCP integration

This is an opt-in fourth image layer for large, production-scale codebases.
PR #1 remains the baseline; this layer must **not** change baseline Codex
behavior when `compose.serena.yaml` is not selected.

## Why this integration

Serena provides semantic symbol lookup, references and targeted edits via MCP.
For Go it uses `gopls`. Instead of repeatedly reading large source files, Codex
can use Serena's symbol tools to load the relevant interfaces/implementations.
**Token savings are a hypothesis, not a guarantee**: benchmark on a real repo.

Serena is a local subprocess of Codex with MCP over **stdio**. It is not a
network service; no port, container runtime socket or additional capability
is needed.

## Architecture

```text
rootless Podman (same baseline restrictions)
  agent: isolated-agent-serena:dev (optional)
    Codex CLI
       |
       +-- MCP stdio -> Serena 1.7.0 -> gopls v0.20.0
       |
       +-- Go tests/build tools
    /workspace          host PROJECT_DIR bind mount (RW)
    /root/.codex        codex-state named volume (persisted)
    /root/.cache        agent-cache named volume (persisted)
    /root/.serena       serena-state named volume (persisted)
    /etc/codex/config.toml   image-provided config (read-only)
```

The Serena image inherits the project image and its entrypoint, so
`/root/.codex/AGENTS.md` refresh and login preservation continue working.
The MCP stanza is **not** written into `/root/.codex/config.toml`; it is
appended to the image's `/etc/codex/config.toml`. This keeps authorization
state and image policy separate.

`SERENA_VERSION=1.7.0` and `SERENA_GOPLS_VERSION=v0.20.0` are pinned,
not `latest`. The pinned Serena **v1.7.0** source release is MIT licensed;
later upstream revisions may have different licensing. Review licenses
before updating the pin or distributing images.

## Install and first run

From this child branch (or after its parent PR is merged and rebased):

```bash
git fetch origin
git switch feat/serena-mcp-integration
# Set PROJECT_DIR and COMPOSE_PROJECT_NAME in your local .env
make build-project   # only when project image is not yet built/changed
make build-serena
make up-example        # one-time bootstrap only on an empty Compose project
make up-serena-example # recreate only agent with Serena image
make serena-doctor
make codex-serena
```

`make up-serena` starts only the agent. `make up-serena-example`
uses the Compose overlay with PostgreSQL/Redis endpoints, but **only
recreates the agent**. This is intentional: some `podman-compose`
versions attempt to create the already-running PostgreSQL and Redis
containers a second time if invoked as `up -d` without a service name,
raising a "container name ... already in use" error.

**On a fresh/empty stack**, run `make up-example` once to bootstrap the
example service containers, then `make up-serena-example` to switch
only the agent to Serena. **On an already running stack**, run
`make up-serena-example` directly; it keeps the existing PostgreSQL
and Redis containers intact. The latter target does not start missing
example services itself.

Both Serena targets use our Podman service-label helper to
remove/recreate the agent container and prevent silently reusing the
non-Serena image. Do **not** run them during an active Codex session.
Neither deletes `/workspace` nor persistent volumes.

To check MCP registration within Codex use `/mcp`. For the first
semantic smoke test, try:

> Use Serena to activate /workspace, list Go symbols in the health package,
> find references to a selected function and describe its callers without
> opening every file. Do not modify source files.

On a real Go repository with a `.git` directory, Serena can also discover
the project from cwd, but this layer uses explicit `--project=/workspace`
so bind-mounted smoke projects without `.git` work too.

## Writes and project-state hygiene

Serena uses writable state:

- `/root/.serena`: Serena global settings/logs (named volume)
- `/root/.cache`: Python/LSP and Go build caches (existing named volume)
- `/workspace/.serena/`: project configuration and optional Serena memories.
  This directory is in your **source bind mount**, so it persists on the host.
  It may appear during project activation/indexing.

Do not accidentally commit generated `.serena/` artifacts into a production
repository. Review contents first. If they should be local-only, add
`.serena/` to **that repository's** `.gitignore`. For shared project
configuration, selectively commit only deliberate settings, not logs or
generated memory content. Serena is explicitly allowed to edit
`/workspace`, so always review changes on production branches.

Dashboard and GUI are disabled in the MCP launch arguments so Serena will
not open a browser or start a dashboard listener inside the container.

## Diagnostics

```bash
make ps-serena-example
make serena-doctor
bash scripts/compose.sh exec agent codex mcp list
bash scripts/compose.sh exec agent gopls version
bash scripts/compose.sh exec agent ls -la /root/.serena
make test
make race
```

The doctor verifies inherited runtime restrictions, Serena executable,
`gopls`, writable Serena state and the MCP entry in Codex. It does **not**
prove the MCP handshake, index correctness or token reduction; verify
those interactively with `/mcp` and the semantic smoke prompt.

If the agent image was switched from a non-Serena image but was not
recreated, run `make up-serena` again. Never fix Serena startup problems
by enabling privileged mode or mounting the host Podman socket.

To return to the baseline **without deleting credentials or caches**:

```bash
make recreate-agent
```

This invokes `up -d agent` using the baseline Compose files, so the
standard project image is restored without attempting to recreate
already-running PostgreSQL/Redis containers. Do **not** use
`make remove-agent && make up-example` on a running example stack:
that can trigger the same duplicate container-name error.
The Serena state volume remains until the explicit destructive
`make reset-state` cleanup.

## Limitations and security

- Python venv increases image size; there is no Python runtime requirement
  on the Debian host.
- Language servers can be CPU/memory intensive when indexing huge repos;
  expect a heavier first-run and record memory consumption.
- `gopls` must be installed in a path that will not be hidden by
  `agent-cache` (we use `/usr/local/bin`).
- Local Serena MCP runs with the same container-level access as Codex.
  With `sandbox_mode = "danger-full-access"`, do not assume the MCP server
  is a separate trust boundary. Do not mount host home, SSH keys or socket.
- For confidential production source code, review dependencies, security
  policy and data flow before using model-powered MCP operations.
- The baseline `make test`/`make race` remain unchanged.

## Benchmark before merging into the mainline

Compare baseline Codex and Codex+Serena on the same real Go revision.
Suggested tasks: locate all implementations of an interface, change a shared
method across packages, update call-sites/tests, and explain the impact of a
cross-package refactor.

Capture:

1. task success and passing tests;
2. token counters (including cached and reasoning tokens) from Codex runs;
3. wall-clock time, MCP calls and repeated command calls;
4. indexing cost, memory use and additional image size.

Evaluate several runs for each task. Do not infer savings solely from the
size of individual Serena results. A startup/indexing overhead could
outweigh reduced source reads for simpler tasks.
