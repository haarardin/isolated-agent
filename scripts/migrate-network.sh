#!/usr/bin/env bash
set -Eeuo pipefail
# Deliberate one-time migration from old Compose-owned internal:false network.
cd "$(dirname "$0")/.."
project="${COMPOSE_PROJECT_NAME:-isolated-agent-demo}"
[[ "$project" =~ ^[[:alnum:]][[:alnum:]_.-]*$ ]] || {
  echo "ERROR: invalid COMPOSE_PROJECT_NAME" >&2; exit 2;
}
name="${project}_isolated-dev"
# Never remove a named shared network. Legacy migration only applies to
# the project-derived old network and requires explicit confirmation.
if [[ -n "${AGENT_NETWORK_NAME:-}" && "$AGENT_NETWORK_NAME" != "$name" ]]; then
  echo "ERROR: migrate-network only handles the legacy project network $name." >&2
  echo "Shared network $AGENT_NETWORK_NAME will not be removed. Inspect it manually." >&2
  exit 1
fi
# Refuse to mutate a legacy Serena deployment even when this script is
# invoked directly (outside Make). No old volumes or mounts are removed.
python3 scripts/check-legacy-serena.py --project "$project" --podman "${PODMAN:-podman}" --project-image "${PROJECT_IMAGE:-}"
# This overlay must exist BEFORE Compose is asked to stop enabled Agent Tools.
# Generation updates files under .generated/ only; it does not start services.
python3 scripts/dependencies.py generate
test -f .generated/compose.tools.yaml || {
  echo "ERROR: generated Agent Tools Compose overlay is missing" >&2; exit 1;
}
echo "Stopping current project Compose services without deleting volumes ..."
bash scripts/compose.sh -f compose.yaml -f compose.web.yaml \
  -f compose.example-services.yaml -f .generated/compose.tools.yaml down
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
