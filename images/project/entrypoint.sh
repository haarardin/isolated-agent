#!/usr/bin/env bash
set -euo pipefail

: "${CODEX_HOME:=/root/.codex}"

mkdir -p "${CODEX_HOME}" /root/.cache

# CODEX_HOME is persistent. Refresh only the image-owned global instructions,
# while preserving authentication, sessions, history, skills and other state.
if [[ -f /opt/isolated-agent/AGENTS.md ]]; then
  install -m 0644 /opt/isolated-agent/AGENTS.md "${CODEX_HOME}/AGENTS.md"
fi

exec "$@"
