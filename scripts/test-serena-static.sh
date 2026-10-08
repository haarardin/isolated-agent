#!/usr/bin/env bash
set -euo pipefail

# Static validation; no container engine or external downloads needed.
for script in scripts/serena-doctor.sh scripts/compose.sh scripts/remove-service.sh; do
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
make -n up-serena-example | grep -Fq 'compose.example-services.yaml'

echo 'Serena static integration checks: OK'
