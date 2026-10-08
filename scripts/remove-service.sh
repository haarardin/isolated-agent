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

label_value() {
  local id="$1"
  local key="$2"
  podman inspect --format "{{ index .Config.Labels \"${key}\" }}" "${id}" 2>/dev/null || true
}

matches_project() {
  local id="$1"
  local value
  value="$(label_value "${id}" "io.podman.compose.project")"
  [[ "${value}" == "${project}" ]] && return 0

  value="$(label_value "${id}" "com.docker.compose.project")"
  [[ "${value}" == "${project}" ]]
}

matches_service() {
  local id="$1"
  local value
  value="$(label_value "${id}" "io.podman.compose.service")"
  [[ "${value}" == "${service}" ]] && return 0

  value="$(label_value "${id}" "com.docker.compose.service")"
  [[ "${value}" == "${service}" ]]
}

containers=()
while IFS= read -r id; do
  [[ -n "${id}" ]] || continue
  if matches_project "${id}" && matches_service "${id}"; then
    containers+=("${id}")
  fi
done < <(podman ps -aq)

if (( ${#containers[@]} == 0 )); then
  printf 'No container found for service %s in project %s\n' "${service}" "${project}"
  printf 'Diagnostic labels for containers with matching name pattern:\n'
  podman ps -a --format '{{.ID}} {{.Names}}' | grep -E "(^|[ _-])${project}[ _-].*${service}" || true
  exit 0
fi

printf 'Removing service %s container(s) from project %s:\n' "${service}" "${project}"
printf '  %s\n' "${containers[@]}"
podman rm -f "${containers[@]}"
