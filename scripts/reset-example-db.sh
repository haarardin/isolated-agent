#!/usr/bin/env bash
set -euo pipefail

project="${COMPOSE_PROJECT_NAME:-}"
if [[ -z "${project}" && -f .env ]]; then
  project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n1)"
fi

if [[ -z "${project}" ]]; then
  printf 'ERROR: COMPOSE_PROJECT_NAME must be set in the environment or .env\n' >&2
  exit 1
fi

# Remove the PostgreSQL container first if it exists.
mapfile -t containers < <(
  podman ps -aq \
    --filter "label=io.podman.compose.project=${project}" \
    --filter "label=com.docker.compose.service=postgres"
)

if (( ${#containers[@]} > 0 )); then
  podman rm -f "${containers[@]}"
fi

# podman-compose labels named volumes with both the project and compose volume key.
mapfile -t volumes < <(
  podman volume ls -q \
    --filter "label=io.podman.compose.project=${project}" \
    --filter "label=com.docker.compose.volume=postgres-data"
)

if (( ${#volumes[@]} == 0 )); then
  printf 'No PostgreSQL data volume found for project %s\n' "${project}"
  exit 0
fi

printf 'Removing PostgreSQL data volume(s) for project %s:\n' "${project}"
printf '  %s\n' "${volumes[@]}"
podman volume rm "${volumes[@]}"
