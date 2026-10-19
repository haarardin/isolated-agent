# Universal dependencies and Agent Tools

This repository builds a language-neutral Debian 13 base, then Codex,
then a configurable Dependencies layer, then Project. Go is NOT installed
in the base. Serena is optional and never requires Go unless the configured
language/toolchain actually uses it.

All installation steps live in dependencies/dependencies.toml.
The host generator is Python 3.11+ standard library (tomllib); all
installations happen as root during Podman image builds, never on the host.

## Files

dependencies/
  dependencies.toml    # Only file loaded by default
  scripts/             # Local shell installers, opt-in by TOML reference
  packages/            # Local .deb, .tar.gz, .tar.xz, .tar, .tgz, .zip
  files/               # Explicit supporting files for installer steps
  examples/            # Opt-in example configurations, not loaded

Generated files are under ignored .generated/:
  Containerfile.dependencies
  Containerfile.tool-<id>
  compose.tools.yaml
  codex-mcp.toml
  project-commands.json
  manifest.json

## Install steps

Use apt.packages to specify common Debian system libraries and one or
more [[install]] entries for strictly ordered operations:

- apt: packages = ["python3", "python3-venv"] (Debian apt names)
- deb: file = "custom_amd64.deb" (local dependencies/packages/)
- script: file = "install-go.sh", args = ["1.27.0"] (dependencies/scripts/)
- archive: file = "sdk.tar.gz", destination = "/opt/sdk"
- command: run = "some trusted shell command"

Optional verify = ["tool --version"] causes the image build to stop on
nonzero exit. Any step may set files = ["settings.json"] to copy that
explicit dependency from dependencies/files/ into the build image at
/opt/isolated-install/files/settings.json before running. The generator
rejects file traversal, and local resource contents contribute to the
configuration fingerprint. Changes to TOML/files change the Podman build cache layers.
Only referenced files are copied. Unknown types/paths fail validation.
Archive members are inspected to reject traversal, symlinks and special
files; always use trusted distribution packages and verify their checksums.

Installing arbitrary scripts, apt post-install scripts and .deb packages
executes untrusted instructions as image-root: REVIEW them before enabling.
Do not put secrets in build arguments, shell commands or copied files.
Rootless Podman is the intended builder. For reproducibility pin versions,
download artifact checksums and base image digest (when released).

## Generic Agent Tools

Agent Tools are repeated [[agent_tools]] tables with id, enabled,
kind ("cli" or "mcp"), placement ("embedded", "sidecar", "external"),
optional repeated [[agent_tools.install]], and integration/runtime.

- embedded + CLI: installed in agent image and used via PATH/shell.
- embedded + MCP stdio: Codex launches the executable as a child process
  on demand from generated [mcp_servers.<id>] in /etc/codex/config.toml.
- sidecar + MCP HTTP: a separate generated image built on plain Debian
  Base (NO Codex auth), connected to internal bridge; Codex gets an HTTP
  MCP URL and unique per-COMPOSE_PROJECT_NAME DNS alias.
- external + MCP HTTPS: only a Codex URL registration; no local image.

Embedded tools and sidecars may optionally declare the same generic state
block, without any special Serena logic:

  [agent_tools.state]
  base = "./volumes/serena"
  target = "/root/.serena"

The host generator appends the source-project identity to the base
directory, creates it with restricted permissions before startup, and
bind-mounts it as writable into the correct tool container. This is
required for tools that write state under a read-only container root.
State bases are restricted to this repository's volumes/ directory.

Sidecars receive read-only /workspace, cap_drop ALL, no host ports and a
read-only root filesystem. Sidecar binaries must be self-contained or
install their OWN runtimes: they do not share the agent's filesystem/PATH.
If the service needs persistent writable state, additional explicitly
reviewed Compose volumes are required (not silently granted).
Healthcheck and custom secret injection are not implemented in this
initial format. Do not configure them as if supported.

Serena example: dependencies/examples/go-serena.toml. This is a plain
embedded MCP tool: its Python venv is isolated in /opt/agent-tools/serena;
Go and gopls are installed ONLY because that example opts into them.
Legacy make up-serena remains supported as a migration option and still
installs Serena using its older specialized image, without mandatory gopls.

## Build and lifecycle

1. Edit dependencies/dependencies.toml (copy individual entries from examples).
2. Run make deps-validate and make deps-plan.
3. Run make build (or make build-project if Base and Codex images exist).
4. Run make up and make doctor; make remote-start if needed.
5. Check codex mcp list from agent shell.

make deps-build rebuilds Dependencies and active sidecar images.
make deps-tools-up brings up only enabled sidecars. All normal web
Compose profiles include generated Compose overlay; make recreate-agent
restarts the agent without deleting persistent CODEX_HOME/Serena state.

IMPORTANT: Changing dependencies currently requires a deliberate rebuild
with make build-project (or make build). make up does NOT transparently
install arbitrary new scripts or recompile an existing image.

## Configurable project commands

The optional [project] table defines commands run inside the agent:
test, lint, race, integration. make test, make deps-lint, make race and
make integration run those exact trusted shell recipes. An unset task
fails with an explanation instead of assuming Go.

Example:
  [project]
  test = "python3 -m pytest -q"
  lint = "python3 -m compileall -q ."

## podman-compose 1.3.0 harmless removal notices

When `make recreate-agent` explicitly removes the old agent container,
`podman-compose up -d agent` may also attempt to stop/remove it during
its own configuration-hash reconciliation. On Debian 13
(`podman-compose 1.3.0`), this can print two
`Error: no container with name or ID ... found` messages **before**
successfully creating a new agent.

These messages alone are not fatal. Confirm success with the exit code
of `make recreate-agent`, `make ps` (agent running), and
`make doctor` (runtime checks pass). Do not suppress all Compose
stderr or ignore nonzero exit codes: other Podman errors can be real.
The upstream implementation calls its down/stop/remove cleanup for
changed compose hashes even when the old service container was
already removed by our host-side helper.

## Backward compatibility

images/serena/Containerfile and old make up-serena targets remain while
projects migrate to [[agent_tools]]. Avoid enabling the TOML Serena
tool AND the legacy Serena overlay simultaneously: both register the
same MCP name and will conflict.

This release does not implement hot-reloading MCP into already active
Codex sessions. Changes to installed tools/configuration require
rebuilding/recreating the affected agent (after saving active work).
