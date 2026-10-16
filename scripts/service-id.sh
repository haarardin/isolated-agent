#!/usr/bin/env bash
set -Eeuo pipefail
service="$1"
project="$COMPOSE_PROJECT_NAME"
label() { podman inspect "$1" --format "{{ index .Config.Labels \"$2\" }}" 2>/dev/null || true; }
while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  p1="$(label "$id" io.podman.compose.project)"
  p2="$(label "$id" com.docker.compose.project)"
  [[ "$project" == "$p1" || "$project" == "$p2" ]] || continue
  s1="$(label "$id" io.podman.compose.service)"
  s2="$(label "$id" com.docker.compose.service)"
  [[ "$service" == "$s1" || "$service" == "$s2" ]] || continue
  echo "$id"
  exit 0
done < <(podman ps -aq)
exit 1
