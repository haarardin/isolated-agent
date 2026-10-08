#!/usr/bin/env bash
set -euo pipefail

# Doctor is run from the host; the MCP server runs inside the same agent.
bash scripts/doctor.sh

bash scripts/compose.sh -f compose.yaml -f compose.serena.yaml exec agent sh -c '
set -eu

test -x /opt/serena/venv/bin/serena || {
  echo "ERROR: Serena executable missing; did you run make build-serena/up-serena?" >&2
  exit 1
}
command -v gopls >/dev/null 2>&1 || {
  echo "ERROR: gopls missing from container PATH" >&2
  exit 1
}
test -w /root/.serena || {
  echo "ERROR: Serena state volume at /root/.serena is not writable" >&2
  exit 1
}
test -w /workspace || {
  echo "ERROR: project /workspace is not writable" >&2
  exit 1
}

echo "Serena CLI:"
/opt/serena/venv/bin/serena --help >/dev/null
echo "  executable: OK"
echo "gopls:"
gopls version

echo "Codex MCP registrations:"
codex mcp list
codex mcp list | grep -q serena || {
  echo "ERROR: Codex does not list Serena MCP; inspect /etc/codex/config.toml" >&2
  exit 1
}

echo "Serena state volume: writable"
echo "Serena doctor: OK"
'
