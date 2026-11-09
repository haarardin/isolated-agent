#!/usr/bin/env bash
set -euo pipefail

compose=(bash scripts/compose.sh)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

"${compose[@]}" ps >/dev/null 2>&1 || fail "Compose environment is not available"

"${compose[@]}" exec agent sh -c '
set -eu

printf "PATH:            %s\n" "$PATH"

# Enabled agents are declared by the generated image manifest.
enabled=/opt/isolated-agent/agents-enabled.txt
test -f "$enabled" || { echo "ERROR: missing enabled-agent manifest" >&2; exit 1; }

if grep -Fxq codex "$enabled"; then
  command -v codex >/dev/null 2>&1 || { echo "ERROR: enabled Codex missing" >&2; exit 1; }
  printf "Codex:           "
  codex --version
  cli_executable="$(readlink -f "$(command -v codex)")"
  package_root="$(dirname "$(dirname "$cli_executable")")"
  if [ ! -f "$package_root/codex-package.json" ] ||
     [ ! -x "$package_root/bin/codex-code-mode-host" ]; then
    echo "ERROR: incomplete Codex managed runtime" >&2
    exit 1
  fi
  test -w /root/.codex || {
  printf "ERROR: CODEX_HOME (/root/.codex) is not writable\n" >&2
  exit 1
}

test -w /root/.cache || {
  printf "ERROR: cache (/root/.cache) is not writable\n" >&2
  exit 1
}

if touch /isolated-agent-doctor-root-write-test 2>/dev/null; then
  rm -f /isolated-agent-doctor-root-write-test || true
  printf "ERROR: container root filesystem is writable\n" >&2
  exit 1
fi

printf "Project root:     /workspace\n"
printf "Workspace:        writable\n"

if [ -f /workspace/AGENTS.md ]; then
  printf "Project AGENTS:   /workspace/AGENTS.md\n"
else
  printf "Project AGENTS:   not present (optional)\n"
fi

if [ -f /workspace/.codex/config.toml ]; then
  printf "Project config:   /workspace/.codex/config.toml\n"
else
  printf "Project config:   not present (optional)\n"
fi

if [ -d /workspace/.serena ]; then
  printf "Serena project:   /workspace/.serena\n"
else
  printf "Serena project:   not initialized\n"
fi

if grep -Fxq codex "$enabled"; then printf "CODEX_HOME:       writable runtime state\n"; fi
printf "Cache:            writable runtime state\n"
printf "Root filesystem:  read-only\n"
# Check the effective global LSP bindings, not merely installed executables.
# A full Serena symbol/LSP startup probe is available via make lsp-doctor.
bash /usr/local/bin/isolated-agent-tool-lsp-runtime check

printf "Runtime doctor:   OK\n"
'
