#!/usr/bin/env bash
set -euo pipefail

# Static validation; no container engine or external downloads needed.
for script in scripts/test-serena-static.sh scripts/serena-doctor.sh scripts/compose.sh scripts/remove-service.sh; do
  bash -n "$script"
done

grep -Fq '[mcp_servers.serena]' images/serena/Containerfile
grep -Fq 'serena-agent==${SERENA_VERSION}' images/serena/Containerfile
grep -Fq 'GOBIN=/usr/local/bin go install' images/serena/Containerfile
grep -Fq -- '--transport=stdio' images/serena/Containerfile
grep -Fq -- '--enable-web-dashboard=false' images/serena/Containerfile
grep -Fq -- '--project=/workspace' images/serena/Containerfile
grep -Fq 'serena-state:/root/.serena' compose.serena.yaml
grep -Fq 'image: ${SERENA_IMAGE:-localhost/isolated-agent-serena:dev}' compose.serena.yaml

# Ensure we do not accidentally elevate the container or publish a port.
if grep -Eq '(privileged:|docker.sock|podman.sock|network_mode:.*host|cap_add:)' compose.serena.yaml; then
  echo 'ERROR: Serena overlay weakens Podman isolation' >&2
  exit 1
fi

make -n build-serena | grep -Fq 'images/serena/Containerfile'
make -n up-serena | grep -Fq 'compose.serena.yaml'

# Regression test for duplicate container-name failures with podman-compose:
# a repeat Serena start must only create the agent, not Postgres/Redis.
serena_plan="$(make -n up-serena-example)"
printf '%s\n' "$serena_plan" | grep -Fq 'compose.example-services.yaml'
printf '%s\n' "$serena_plan" | grep -Fq 'compose.serena.yaml up -d agent'
if printf '%s\n' "$serena_plan" | grep -Fxq 'bash scripts/compose.sh -f compose.yaml -f compose.example-services.yaml -f compose.serena.yaml up -d'; then
  echo 'ERROR: up-serena-example would recreate all services' >&2
  exit 1
fi

# Baseline rollback must also target only the agent.
make -n recreate-agent | grep -Fq 'compose.example-services.yaml up -d agent'

echo 'Serena static integration checks: OK'
