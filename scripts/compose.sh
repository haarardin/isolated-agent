#!/usr/bin/env bash
set -euo pipefail

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
