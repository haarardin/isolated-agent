#!/usr/bin/env bash
set -euo pipefail

: "${CODEX_HOME:=/root/.codex}"

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
