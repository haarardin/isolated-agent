#!/usr/bin/env bash
set -euo pipefail

# Make supplies both identities. A direct call must not silently select the
# isolated-agent-demo project and network when this checkout has another .env.
# Read only these values, never execute .env as shell code.
read_setting() {
  local key="$1"
  if [[ -f .env ]]; then
    sed -n "s/^$key=//p" .env | tail -n 1
  fi
}

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  COMPOSE_PROJECT_NAME="$(read_setting COMPOSE_PROJECT_NAME)"
  COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-isolated-agent-demo}"
  export COMPOSE_PROJECT_NAME
fi
if [[ -z "${AGENT_NETWORK_NAME:-}" ]]; then
  AGENT_NETWORK_NAME="$(read_setting AGENT_NETWORK_NAME)"
  AGENT_NETWORK_NAME="${AGENT_NETWORK_NAME:-${COMPOSE_PROJECT_NAME}_isolated-dev}"
  export AGENT_NETWORK_NAME
fi
name_pattern='^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'
if [[ ! "$COMPOSE_PROJECT_NAME" =~ $name_pattern || ! "$AGENT_NETWORK_NAME" =~ $name_pattern ]]; then
  echo "ERROR: invalid Compose project or agent network name" >&2
  exit 2
fi

if ! command -v podman-compose >/dev/null 2>&1; then
  printf 'ERROR: podman-compose is required but was not found in PATH\n' >&2
  exit 127
fi

# Deliberately invoke podman-compose directly.
#
# Do not replace this with an unqualified "podman compose": Podman treats that
# command as a wrapper around an external provider and prefers docker-compose
# when both providers are installed. docker-compose talks to Podman through its
# API socket, while this project intentionally does not require a Podman service
# socket for normal local orchestration.
exec podman-compose "$@"
