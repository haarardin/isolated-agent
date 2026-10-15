#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ -z "$COMPOSE_PROJECT_NAME" ]]; then
  COMPOSE_PROJECT_NAME="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env 2>/dev/null | tail -1)"
fi
export COMPOSE_PROJECT_NAME
agent="$(bash scripts/service-id.sh agent)" || { echo "ERROR: agent missing" >&2; exit 1; }
nets="$(podman inspect "$agent" --format '{{json .NetworkSettings.Networks}}')"
network="$(python3 -c 'import json,sys; o=json.loads(sys.argv[1]); assert len(o)==1,"Agent must have exactly one network"; print(next(iter(o)))' "$nets")"
[[ "$(podman network inspect -f '{{.Internal}}' "$network")" == true ]] || { echo "ERROR: $network is not internal" >&2; exit 1; }
echo "Agent only on internal network: $network"
if podman exec "$agent" curl --noproxy '*' -kfsS --connect-timeout 3 --max-time 5 https://1.1.1.1/ -o /dev/null >/dev/null 2>&1; then
  echo "FAIL: direct public Internet reachable!" >&2; exit 1
fi
for addr in 192.168.1.1 169.254.169.254; do
  if podman exec "$agent" curl --noproxy '*' -fsS --connect-timeout 3 --max-time 5 "http://$addr/" -o /dev/null >/dev/null 2>&1; then
    echo "FAIL: direct forbidden $addr reachable!" >&2; exit 1
  fi
done
# Container NO_PROXY deliberately includes 127.0.0.1 and peer services.
# For tests asserting Squid ACLs, curl MUST explicitly override NO_PROXY
# using --noproxy '' (even when -x is supplied); --noproxy '*' above
# deliberately checks the direct/no-proxy routing boundary instead.
squid="$(bash scripts/service-id.sh squid || true)"
if [[ -z "$squid" ]]; then
  if podman exec "$agent" curl -fsS --noproxy '' -x http://squid:3128 --max-time 5 https://example.com/ -o /dev/null >/dev/null 2>&1; then
    echo "FAIL: offline agent reached proxy" >&2; exit 1
  fi
  echo "Offline checks passed"
  exit 0
fi
[[ "$(podman inspect "$squid" --format '{{.State.Running}}')" == true ]] || { echo "ERROR: squid stopped" >&2; exit 1; }
podman exec "$agent" curl -fLsS --noproxy '' -x http://squid:3128 --max-time 30 https://example.com/ -o /dev/null
for addr in 127.0.0.1 169.254.169.254 192.168.1.1 100.100.100.200; do
  code="$(podman exec "$agent" curl -sS --noproxy '' -x http://squid:3128 -o /dev/null -w '%{http_code}' --max-time 8 "http://$addr/" || true)"
  [[ "$code" == 403 ]] || { echo "FAIL: Squid $addr returned $code, expected 403 (verify proxy access/ACL; forced --noproxy empty)" >&2; exit 1; }
done
code="$(podman exec "$agent" curl -ksS --noproxy '' -x http://squid:3128 -o /dev/null -w '%{http_connect}' --max-time 8 https://192.168.1.1:8443/ || true)"
[[ "$code" == 403 ]] || { echo "FAIL: CONNECT private returned $code" >&2; exit 1; }
echo "Filtered Web checks passed. Also test real host/LAN/VPN listeners and IPv6 on Debian."
