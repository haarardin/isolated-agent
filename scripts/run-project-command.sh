#!/usr/bin/env bash
# Run explicit, trusted project tasks inside the agent.
set -Eeuo pipefail
name="${1:?project task required}"
case "$name" in test|race|integration|lint) ;; *) echo "Unknown project task" >&2; exit 2;; esac
cd "$(dirname "$0")/.."
command="$(python3 scripts/dependencies.py project-command --name "$name")"
bash scripts/compose.sh exec agent /bin/bash -euo pipefail -c "$command"
