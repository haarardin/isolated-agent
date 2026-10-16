#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .state
python3 scripts/render-blocklist.py --base config/blocked-cidrs.txt \
  --output .state/blocked-cidrs.txt --extra "${BLOCK_CIDRS:-}"
python3 - <<'PY'
import ipaddress, json, os, pathlib
state = json.loads(pathlib.Path(".state/network.json").read_text())
project = os.environ.get("COMPOSE_PROJECT_NAME") or "isolated-agent-demo"
if state["project"] != project or state["name"] != (os.environ.get("AGENT_NETWORK_NAME") or project + "_isolated-dev"):
    raise SystemExit("Network state does not belong to this Compose project")
net = ipaddress.ip_network(state["subnet"], strict=True)
if net.version != 4:
    raise SystemExit("Resolved project network must be IPv4")
out = pathlib.Path(".state/squid.conf")
tmp = out.with_suffix(".tmp")
tmp.write_text(pathlib.Path("config/squid.conf").read_text().replace("@AGENT_SUBNET@", str(net)))
tmp.chmod(0o644)
tmp.replace(out)
print("Filtered Squid configuration prepared.")
PY
