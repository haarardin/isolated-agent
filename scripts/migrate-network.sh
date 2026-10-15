#!/usr/bin/env bash
set -Eeuo pipefail
# Deliberate one-time migration from old Compose-owned internal:false network.
cd "$(dirname "$0")/.."
project="${COMPOSE_PROJECT_NAME:-isolated-agent-demo}"
[[ "$project" =~ ^[[:alnum:]][[:alnum:]_.-]*$ ]] || {
  echo "ERROR: invalid COMPOSE_PROJECT_NAME" >&2; exit 2;
}
name="${project}_isolated-dev"
echo "Stopping project Compose services without removing named volumes ..."
bash scripts/compose.sh -f compose.yaml -f compose.web.yaml \
  -f compose.example-services.yaml -f compose.serena.yaml down
if podman network exists "$name"; then
  internal="$(podman network inspect "$name" --format '{{.Internal}}')"
  if [[ "$internal" != true ]]; then
    # Do not delete a same-named network labeled as somebody else's project.
    labels="$(podman network inspect "$name" --format '{{json .Labels}}')"
    python3 - "$project" "$labels" <<'PY'
import json, sys
project, raw = sys.argv[1:]
labels = json.loads(raw) or {}
for key in ('io.isolated-agent.project', 'io.podman.compose.project',
            'com.docker.compose.project'):
    if key in labels and labels[key] != project:
        raise SystemExit('ERROR: foreign project owns this network; refusing migration')
PY
    users="$(podman ps -aq --filter "network=$name")"
    if [[ -n "$users" ]]; then
      echo "ERROR: old network $name still has containers attached; refusing removal." >&2
      echo "Check: podman ps -a --filter network=$name" >&2
      exit 1
    fi
    echo "Removing ONLY old same-project unrestricted network $name ..."
    podman network rm "$name"
  else
    echo "Project network is already internal; keeping $name."
  fi
fi
echo "Old volumes remain untouched. Recreate with: make up && make network-check"
