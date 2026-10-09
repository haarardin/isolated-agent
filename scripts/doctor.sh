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

command -v go >/dev/null 2>&1 || {
  printf "ERROR: go is not available in container PATH\n" >&2
  printf "Expected Go binary at /usr/local/go/bin/go\n" >&2
  exit 1
}

command -v codex >/dev/null 2>&1 || {
  printf "ERROR: codex is not available in container PATH\n" >&2
  exit 1
}

printf "Go:              "
go version

printf "Codex:           "
codex --version

workspace="$(pwd -P)"
if [ "$workspace" != "/workspace" ]; then
  printf "ERROR: agent working directory is %s, expected /workspace\n" "$workspace" >&2
  exit 1
fi

test -w /workspace || {
  printf "ERROR: /workspace is not writable\n" >&2
  exit 1
}

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

printf "CODEX_HOME:       writable runtime state\n"
printf "Cache:            writable runtime state\n"
printf "Root filesystem:  read-only\n"
printf "Runtime doctor:   OK\n"
'
