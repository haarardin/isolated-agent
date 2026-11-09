#!/usr/bin/env bash
set -euo pipefail

: "${CODEX_HOME:=/root/.codex}"

# Only enabled coding runtimes have persistent state mounted. Avoid touching
# Codex's home or claiming a Codex volume in OpenCode-only deployments.
if grep -Fxq codex /opt/isolated-agent/agents-enabled.txt; then
  bash /usr/local/bin/isolated-agent-claim-state "${CODEX_HOME}" "${CODEX_PROJECT_KEY:-}" "${CODEX_BIND_EXISTING_STATE:-false}" codex
  mkdir -p "${CODEX_HOME}" /root/.cache

  # Refresh image-owned global instructions while keeping all user sessions.
  if [[ -f /opt/isolated-agent/AGENTS.md ]]; then
    install -m 0644 /opt/isolated-agent/AGENTS.md "${CODEX_HOME}/AGENTS.md"
  fi

  # Seed the full official managed runtime only when Codex is installed.
  if [[ ! -x "$CODEX_HOME/packages/standalone/current/bin/codex" &&
        -x /opt/isolated-agent/codex-standalone/current/bin/codex ]]; then
    mkdir -p "$CODEX_HOME/packages/standalone"
    cp -a /opt/isolated-agent/codex-standalone/. "$CODEX_HOME/packages/standalone/"
  fi
fi
mkdir -p /root/.cache

# Apply LSP executable bindings only after persistent state has been claimed
# and mounted. Fail the agent start if a declared dependency is unavailable.
# This never marks /workspace as a trusted Serena project.
bash /usr/local/bin/isolated-agent-tool-lsp-runtime apply

exec "$@"
