#!/usr/bin/env bash
set -Eeuo pipefail
# No raw Codex output stored in logs. Pair code is printed only to caller.
mode="$1"
case "$mode" in start|pair|status|stop|logs|doctor) ;; *) echo "Usage: remote-control.sh start|pair|status|stop|logs|doctor" >&2; exit 2;; esac
cd "$(dirname "$0")/.."
if [[ -z "$COMPOSE_PROJECT_NAME" ]]; then
  COMPOSE_PROJECT_NAME="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env 2>/dev/null | tail -1)"
fi
export COMPOSE_PROJECT_NAME
id="$(bash scripts/service-id.sh agent)" || { echo "Agent not found; run make up first" >&2; exit 1; }
[[ "$(podman inspect "$id" --format '{{.State.Running}}')" == true ]] || { echo "Agent stopped" >&2; exit 1; }
umask 077
mkdir -p .state
events=.state/remote-events.log
event() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$events"; chmod 600 "$events"; }
running() {
  podman exec "$id" codex app-server daemon version 2>/dev/null |
    python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("status")=="running" else 1)'
}
case "$mode" in
 start)
   if ! podman exec "$id" codex remote-control start --json >/dev/null 2>&1; then
     event start-failed
     echo "Remote start failed. Verify Codex login, version, managed install and proxy." >&2; exit 1
   fi
   if ! running; then
     event daemon-not-running
     echo "Start returned but managed app-server is not running." >&2; exit 1
   fi
   event started
   echo "Codex app-server daemon running. No remote TCP port is published."
   ;;
 pair)
   running || { echo "Start Remote Control first: make remote-start" >&2; exit 1; }
   echo "Pairing code appears only here. Do NOT paste it in logs or CI."
   podman exec "$id" codex remote-control pair
   ;;
 status)
   if running; then echo "Managed Codex app-server: running"; else echo "Managed Codex app-server: not running"; exit 1; fi
   ;;
 stop)
   if ! podman exec "$id" codex remote-control stop --json >/dev/null 2>&1; then
     event stop-failed; echo "Remote stop failed." >&2; exit 1
   fi
   event stopped
   echo "Codex app-server stopped; persistent CODEX_HOME retained."
   ;;
 logs)
   if [[ -e "$events" ]]; then tail -n 80 "$events"; else echo "No lifecycle events"; fi
   echo "Raw Codex logs omitted (may contain tokens, code or pairing data)."
   ;;
 doctor)
   echo "Compose project: $COMPOSE_PROJECT_NAME"
   podman exec "$id" sh -c 'codex --version; codex remote-control --help >/dev/null && echo "Remote Control CLI: available"; test -w "$CODEX_HOME" && echo "CODEX_HOME: writable"'
   if running; then echo "Managed daemon: running"; else echo "Managed daemon: stopped"; fi
   nets="$(podman inspect "$id" --format '{{json .NetworkSettings.Networks}}')"
   python3 -c 'import json,sys; n=json.loads(sys.argv[1]); assert len(n)==1,"agent must have one network"; print("Agent network: "+next(iter(n)))' "$nets"
   if podman exec "$id" curl -fILsS --max-time 15 -x http://squid:3128 https://chatgpt.com/ -o /dev/null >/dev/null 2>&1; then
     echo "OpenAI HTTPS via Squid: reachable"
   else
     echo "OpenAI HTTPS via Squid: failed; check Squid/DNS/ACL"
     exit 1
   fi
   ;;
esac
