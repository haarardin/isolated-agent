#!/usr/bin/env bash
set -euo pipefail
bash -n scripts/remote-executor.sh
bash -n scripts/test-remote-static.sh
grep -Fq 'podman exec' scripts/remote-executor.sh
grep -Fq -- '--env-file "$secret_file"' scripts/remote-executor.sh
if grep -Eq 'privileged|docker.sock|podman.sock|--cap-add' scripts/remote-executor.sh; then
  echo 'ERROR: remote integration weakens isolation' >&2
  exit 1
fi
make -n remote-exec | grep -Fq 'scripts/remote-executor.sh'
make -n remote-session-create | grep -Fq 'go run . create'
echo 'Remote static integration checks: OK'
