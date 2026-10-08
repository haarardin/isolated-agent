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

# Reuse the version-compatible service matcher.
bash scripts/remove-service.sh postgres

volumes=()
for project_key in io.podman.compose.project com.docker.compose.project; do
  for volume_key in io.podman.compose.volume com.docker.compose.volume; do
    while IFS= read -r id; do
      [[ -n "${id}" ]] || continue
      volumes+=("${id}")
    done < <(
      podman volume ls -q \
        --filter "label=${project_key}=${project}" \
        --filter "label=${volume_key}=postgres-data" 2>/dev/null || true
    )
  done
done

if (( ${#volumes[@]} == 0 )); then
  printf 'No PostgreSQL data volume found for project %s\n' "${project}"
  exit 0
fi

mapfile -t volumes < <(printf '%s\n' "${volumes[@]}" | awk '!seen[$0]++')
printf 'Removing PostgreSQL data volume(s) for project %s:\n' "${project}"
printf '  %s\n' "${volumes[@]}"
podman volume rm "${volumes[@]}"
