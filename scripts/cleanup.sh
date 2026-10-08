#!/usr/bin/env bash
set -euo pipefail

remove_volumes=false
if [[ "${1:-}" == "--volumes" ]]; then
  remove_volumes=true
elif [[ -n "${1:-}" ]]; then
  printf 'Usage: %s [--volumes]\n' "$0" >&2
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

label="io.podman.compose.project=${project}"

mapfile -t containers < <(podman ps -aq --filter "label=${label}")
if (( ${#containers[@]} > 0 )); then
  printf 'Removing %d container(s) for project %s\n' "${#containers[@]}" "${project}"
  podman rm -f "${containers[@]}"
else
  printf 'No containers found for project %s\n' "${project}"
fi

mapfile -t networks < <(podman network ls -q --filter "label=${label}")
if (( ${#networks[@]} > 0 )); then
  printf 'Removing %d network(s) for project %s\n' "${#networks[@]}" "${project}"
  podman network rm "${networks[@]}"
else
  printf 'No networks found for project %s\n' "${project}"
fi

if [[ "${remove_volumes}" == "true" ]]; then
  mapfile -t volumes < <(podman volume ls -q --filter "label=${label}")
  if (( ${#volumes[@]} > 0 )); then
    printf 'Removing %d volume(s) for project %s\n' "${#volumes[@]}" "${project}"
    podman volume rm "${volumes[@]}"
  else
    printf 'No volumes found for project %s\n' "${project}"
  fi
fi
