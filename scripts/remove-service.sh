#!/usr/bin/env bash
set -euo pipefail

service="${1:-}"
if [[ -z "${service}" ]]; then
  printf 'Usage: %s <service>\n' "$0" >&2
  exit 2
fi

project="${COMPOSE_PROJECT_NAME:-}"
if [[ -z "${project}" && -f .env ]]; then
  project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n1)"
fi

if [[ -z "${project}" ]]; then
  printf 'ERROR: COMPOSE_PROJECT_NAME must be set in the environment or .env\n' >&2
  exit 1
fi

mapfile -t containers < <(
  podman ps -aq \
    --filter "label=io.podman.compose.project=${project}" \
    --filter "label=io.podman.compose.service=${service}"
)

if (( ${#containers[@]} == 0 )); then
  printf 'No container found for service %s in project %s\n' "${service}" "${project}"
  exit 0
fi

printf 'Removing service %s container(s) from project %s:\n' "${service}" "${project}"
printf '  %s\n' "${containers[@]}"
podman rm -f "${containers[@]}"
