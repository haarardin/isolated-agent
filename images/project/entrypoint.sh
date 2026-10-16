#!/usr/bin/env bash
set -euo pipefail

: "${CODEX_HOME:=/root/.codex}"

# Claim the mounted full CODEX_HOME before installing global instructions or
# copying a binary. A changed PROJECT_DIR must not inherit old memories.
bash /usr/local/bin/isolated-agent-claim-state "${CODEX_HOME}" "${CODEX_PROJECT_KEY:-}" "${CODEX_BIND_EXISTING_STATE:-false}" codex
# Optional Serena global volume; project Serena memories stay in /workspace.
if [[ -n "${SERENA_PROJECT_KEY:-}" ]]; then
  bash /usr/local/bin/isolated-agent-claim-state /root/.serena "${SERENA_PROJECT_KEY}" "${SERENA_BIND_EXISTING_STATE:-false}" serena
fi
mkdir -p "${CODEX_HOME}" /root/.cache

# CODEX_HOME is persistent. Refresh only the image-owned global instructions,
# while preserving authentication, sessions, history, skills and other state.
if [[ -f /opt/isolated-agent/AGENTS.md ]]; then
  install -m 0644 /opt/isolated-agent/AGENTS.md "${CODEX_HOME}/AGENTS.md"
fi

# Seed only the managed standalone binary hidden by the persistent volume.
# This does not overwrite authentication, sessions or user Codex settings.
if [[ ! -x "$CODEX_HOME/packages/standalone/current/codex" &&
      -x /opt/isolated-agent/codex-standalone/current/codex ]]; then
  mkdir -p "$CODEX_HOME/packages/standalone"
  cp -a /opt/isolated-agent/codex-standalone/. "$CODEX_HOME/packages/standalone/"
fi

exec "$@"
