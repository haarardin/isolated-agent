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
# Remote defaults to ~/Documents. It must resolve to the existing approved
# workspace via an image-owned symlink, NOT a second host bind mount.
assert '${PROJECT_DIR:-./workspace}:/workspace:rw' in agent
assert "documents_ready || exit 1" in remote
assert "mkdir -p /root/Documents && test -w /root/Documents" in remote
assert "read_only: true" in agent
# Android Remote projectless tasks create ~/Documents/Codex. Ensure that path
# resolves into the *existing* writable PROJECT_DIR bind rather than
# weakening read_only or exposing more host directories.
project_image = Path("images/project/Containerfile").read_text()
assert "ln -s /workspace /root/Documents" in project_image
assert "test ! -e /root/Documents" in project_image
assert "/root/Documents:" not in agent, "Do not introduce extra host mounts"

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
# The Makefile recipe uses /bin/sh (dash on Debian), NOT Bash.
# Execute only the confirmation guard, never the destructive migration body.
import subprocess
migration = mk.split("migrate-network:\n", 1)[1].split("\n\n", 1)[0]
guard = next(line.strip().removeprefix("@") for line in migration.splitlines() if "$(CONFIRM)" in line)
assert guard.startswith('test "$(CONFIRM)" = "YES"'), guard
for value, success in [("YES", True), ("NO", False)]:
    result = subprocess.run(
        ["/bin/sh", "-c", guard.replace("$(CONFIRM)", value)],
        capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) == success, (value, result.stderr)
# Regression: curl honours NO_PROXY even when an explicit -x proxy is given.
# Testing Squid against 127.0.0.1 must *force* use of Squid, not loopback.
checks=Path("scripts/network-check.sh").read_text()
proxied=[line for line in checks.splitlines()
         if 'podman exec' in line and 'curl ' in line and '-x http://squid:3128' in line]
assert len(proxied)==4, f"Expected offline/public/deny/CONNECT proxy probes: {proxied!r}"
for command in proxied:
    assert "curl " in command and "--noproxy '' -x http://squid:3128" in command, command
direct=[line for line in checks.splitlines()
        if 'podman exec' in line and 'curl ' in line and "--noproxy '*'" in line]
assert len(direct)==2, f"Direct routing probes must bypass the proxy: {direct!r}"
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
