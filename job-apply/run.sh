#!/usr/bin/env bash
set -euo pipefail
APP="$(cd -- "$(dirname -- "$0")" && pwd)"
STATE="$APP/state"
cd "$APP"
export COMPOSE_PROJECT_NAME=isolated-job-apply
mode="$(cat "$STATE/browser-mode" 2>/dev/null || echo headless)"
[[ "$mode" == headless || "$mode" == headed ]] || { echo "Invalid saved browser mode" >&2; exit 2; }
export BROWSER_MODE="$mode"
compose() { podman-compose -f compose.yaml "$@"; }
cmd="${1:-help}"
case "$cmd" in
  up) compose up -d ;;
  down) compose down ;;
  ps) compose ps ;;
  logs) compose logs --tail 100 ;;
  agent) compose exec agent codex ;;
  login) compose exec agent codex login --device-auth ;;
  shell) compose exec agent bash ;;
  status) python3 jobctl.py --root "$STATE" status "$2" ;;
  approve)
    [[ -n "${2:-}" ]] || { echo "Usage: run.sh approve APP-ID" >&2; exit 2; }
    compose exec -T agent python3 /opt/jobapply/jobctl.py audit "$2"
    python3 jobctl.py --root "$STATE" approve "$2" ;;
  browser)
    mode="${2:-}"
    [[ "$mode" == headless || "$mode" == headed ]] || { echo "Usage: run.sh browser headed|headless" >&2; exit 2; }
    printf '%s\n' "$mode" > "$STATE/browser-mode"
    export BROWSER_MODE="$mode"
    compose up -d --force-recreate browser
    echo "Browser mode: $mode"
    if [[ "$mode" == headed ]]; then
      echo "noVNC: http://127.0.0.1:6080/vnc.html or VNC: localhost:5901"
      echo "Password stored in state/vnc/password.txt"
    fi ;;
  help|*) cat <<'HELP'
Usage:
  ./job-apply/run.sh up|down|ps|logs
  ./job-apply/run.sh login
  ./job-apply/run.sh agent
  ./job-apply/run.sh browser headed|headless
  ./job-apply/run.sh approve APPLICATION-ID  # only on host
  ./job-apply/run.sh status APPLICATION-ID
HELP
    ;;
esac
