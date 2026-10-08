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

container_matches_project() {
  local id="$1"
  local value

  value="$(podman inspect --format '{{ index .Config.Labels "io.podman.compose.project" }}' "${id}" 2>/dev/null || true)"
  [[ "${value}" == "${project}" ]] && return 0

  value="$(podman inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "${id}" 2>/dev/null || true)"
  [[ "${value}" == "${project}" ]]
}

containers=()
while IFS= read -r id; do
  [[ -n "${id}" ]] || continue
  if container_matches_project "${id}"; then
    containers+=("${id}")
  fi
done < <(podman ps -aq)

if (( ${#containers[@]} > 0 )); then
  printf 'Removing %d container(s) for project %s\n' "${#containers[@]}" "${project}"
  podman rm -f "${containers[@]}"
else
  printf 'No containers found for project %s\n' "${project}"
fi

# Network/volume label support differs between podman-compose versions.
# Try both current Podman labels and Docker Compose compatibility labels.
networks=()
for key in io.podman.compose.project com.docker.compose.project; do
  while IFS= read -r id; do
    [[ -n "${id}" ]] || continue
    networks+=("${id}")
  done < <(podman network ls -q --filter "label=${key}=${project}" 2>/dev/null || true)
done

if (( ${#networks[@]} > 0 )); then
  mapfile -t networks < <(printf '%s\n' "${networks[@]}" | awk '!seen[$0]++')
  printf 'Removing %d network(s) for project %s\n' "${#networks[@]}" "${project}"
  podman network rm "${networks[@]}"
else
  printf 'No labeled networks found for project %s\n' "${project}"
fi

if [[ "${remove_volumes}" == "true" ]]; then
  volumes=()
  for key in io.podman.compose.project com.docker.compose.project; do
    while IFS= read -r id; do
      [[ -n "${id}" ]] || continue
      volumes+=("${id}")
    done < <(podman volume ls -q --filter "label=${key}=${project}" 2>/dev/null || true)
  done

  if (( ${#volumes[@]} > 0 )); then
    mapfile -t volumes < <(printf '%s\n' "${volumes[@]}" | awk '!seen[$0]++')
    printf 'Removing %d volume(s) for project %s\n' "${#volumes[@]}" "${project}"
    podman volume rm "${volumes[@]}"
  else
    printf 'No labeled volumes found for project %s\n' "${project}"
  fi
fi
