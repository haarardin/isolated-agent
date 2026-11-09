#!/usr/bin/env bash
# OpenCode V2 in the rootless-Podman agent; Codex state remains untouched.
set -Eeuo pipefail

state=/root/.isolated-opencode
if [[ ! -d "$state" || ! -w "$state" ]]; then
  echo "ERROR: OpenCode state is not mounted; enable the opencode Agent Tool, build and recreate." >&2
  exit 2
fi
if ! command -v opencode >/dev/null 2>&1; then
  echo "ERROR: OpenCode V2 is not installed; enable the opencode Agent Tool and rebuild." >&2
  exit 127
fi

# XDG paths are scoped to the mounted volume: settings, auth, sessions and
# SQLite survive agent recreation; the root filesystem stays read-only.
export XDG_CONFIG_HOME="$state/config"
export XDG_DATA_HOME="$state/data"
export XDG_STATE_HOME="$state/state"
export XDG_CACHE_HOME=/root/.cache
mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME"

# The local provider/model config is a read-only single-file bind sourced
# from config/opencode.jsonc in the isolated-agent checkout, never /workspace.
# MCP remains generated and image-owned at /etc/opencode/opencode.json.
config=/opt/isolated-agent/opencode-user.jsonc
if [[ ! -f "$config" ]]; then
  echo "ERROR: OpenCode config is not mounted; create config/opencode.jsonc from the example and recreate agent." >&2
  exit 2
fi
export OPENCODE_CONFIG="$config"
exec opencode "$@"
