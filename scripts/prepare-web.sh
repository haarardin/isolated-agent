#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .state
python3 scripts/render-blocklist.py --base config/blocked-cidrs.txt \
  --output .state/blocked-cidrs.txt --extra "${BLOCK_CIDRS:-}"
python3 - <<'PY'
import ipaddress, os, pathlib
subnet = os.environ.get("AGENT_SUBNET") or "10.89.71.0/24"
net = ipaddress.ip_network(subnet, strict=True)
if net.version != 4:
    raise SystemExit("AGENT_SUBNET must be IPv4")
out = pathlib.Path(".state/squid.conf")
tmp = out.with_suffix(".tmp")
tmp.write_text(pathlib.Path("config/squid.conf").read_text().replace("@AGENT_SUBNET@", str(net)))
tmp.chmod(0o644)
tmp.replace(out)
print("Filtered Squid configuration prepared.")
PY
