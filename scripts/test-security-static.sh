#!/usr/bin/env bash
set -Eeuo pipefail
# Static security contract; no Podman needed.
for f in scripts/*.sh images/project/entrypoint.sh; do bash -n "$f"; done
python3 - <<'PY'
from pathlib import Path
agent=Path("compose.yaml").read_text()
web=Path("compose.web.yaml").read_text()
mk=Path("Makefile").read_text()
remote=Path("scripts/remote-control.sh").read_text()
assert "internal: true" in agent
assert "enable_ipv6: false" in agent
assert agent.count("      - isolated-dev")==1
assert "codex-state:/root/.codex" in agent
assert "agent-cache:/root/.cache" in agent
assert "read_only: true" in agent
assert "cap_drop:\n      - ALL" in agent
assert "in_pod: false" in agent
assert "      - outbound" in web and "      - isolated-dev" in web
assert "http_access deny blocked_dst" in Path("config/squid.conf").read_text()
assert "http_access deny !sandbox_clients" in Path("config/squid.conf").read_text()
assert "http_access deny to_localhost" in Path("config/squid.conf").read_text()
assert "http_access deny to_linklocal" in Path("config/squid.conf").read_text()
assert "podman.sock" not in agent + web
assert "docker.sock" not in agent + web
assert "privileged:" not in agent + web
assert "network_mode:" not in agent + web
for target in ("remote-start","remote-pair","remote-status","remote-stop","remote-logs","remote-doctor","offline","network-check"):
    assert f"{target}:" in mk, target
for cmd in ("codex remote-control start","codex remote-control pair","codex remote-control stop", "codex app-server daemon version"):
    assert cmd in remote
assert '>/dev/null 2>&1' in remote, "CLI lifecycle output must not leak to CI logs"
assert remote.count("secure_network || exit 1") >= 3, "start/pair/doctor must reject unrestricted egress"
assert "podman network inspect --format" in remote
assert "CODEX_APPROVAL_POLICY ?= never" in mk
assert "CODEX_SANDBOX_MODE ?= danger-full-access" in mk
print("Security and Remote Control static policy: OK")
PY
# Existing public Makefile targets must remain usable without remapping to new names.
for goal in ensure-images up login codex shell doctor up-example up-serena test down; do
  make -n "$goal" >/dev/null
done
# Check correct Compose combos (not raw outbound for agent).
make -n up | grep -Fq 'compose.web.yaml'
make -n offline | grep -Fq 'up -d agent'
make -n up-serena-example | grep -Fq 'compose.serena.yaml up -d agent'
echo "Makefile backward compatibility plans: OK"
