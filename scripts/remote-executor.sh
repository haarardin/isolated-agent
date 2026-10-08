#!/usr/bin/env bash
set -euo pipefail
# Self-hosted Agents API executor; NOT native ChatGPT mobile/web Remote host registration.
[[ $# -eq 2 ]] || { echo 'Usage: remote-executor.sh <environment.remote_url> <environment.id>' >&2; exit 2; }
remote="$1"
environment_id="$2"
case "$remote" in
  https://api.openai.com/*|wss://codex-cloud-environments.chatgpt.com/*) ;;
  *) echo 'ERROR: unsupported executor TLS remote host' >&2; exit 2 ;;
esac
[[ "$environment_id" =~ ^[a-zA-Z0-9_-]{1,128}$ ]] || { echo 'ERROR: invalid environment ID' >&2; exit 2; }
secret_file="${REMOTE_EXECUTOR_ENV_FILE:-.secrets/remote-executor.env}"
[[ -f "$secret_file" ]] || { echo "ERROR: missing $secret_file" >&2; exit 2; }
mode="$(stat -c '%a' "$secret_file")"
if (( (8#$mode & 077) != 0 )); then
  echo 'ERROR: chmod 600 on restricted executor key file required' >&2; exit 2
fi
grep -Eq '^CODEX_API_KEY=[^[:space:]]+' "$secret_file" || { echo 'ERROR: CODEX_API_KEY missing' >&2; exit 2; }
if grep -Eq '^OPENAI_API_KEY=' "$secret_file"; then
  echo 'ERROR: never give the application key to the executor' >&2; exit 2
fi
project="${COMPOSE_PROJECT_NAME:-}"
if [[ -z "$project" && -f .env ]]; then
  project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n1)"
fi
[[ -n "$project" ]] || { echo 'ERROR: COMPOSE_PROJECT_NAME required' >&2; exit 2; }
matches() {
  local id="$1" key val=""
  for key in io.podman.compose.project com.docker.compose.project; do
    val="$(podman inspect --format "{{ index .Config.Labels \"$key\" }}" "$id" 2>/dev/null || true)"
    [[ "$val" == "$project" ]] && break
  done
  [[ "$val" == "$project" ]] || return 1
  for key in io.podman.compose.service com.docker.compose.service; do
    val="$(podman inspect --format "{{ index .Config.Labels \"$key\" }}" "$id" 2>/dev/null || true)"
    [[ "$val" == agent ]] && return 0
  done
  return 1
}
ids=()
while IFS= read -r id; do
  [[ -z "$id" ]] && continue
  if matches "$id"; then ids+=("$id"); fi
done < <(podman ps -q)
(( ${#ids[@]} == 1 )) || { echo "ERROR: expected exactly one running agent; found ${#ids[@]}" >&2; exit 1; }
if ! podman exec "${ids[0]}" codex exec-server --help >/dev/null 2>&1; then
  echo 'ERROR: Codex image lacks exec-server; use a compatible official CLI build' >&2; exit 1
fi
# Only restricted key reaches this process; no host runtime socket is mounted.
exec podman exec --env-file "$secret_file" --workdir /workspace "${ids[0]}" \
  codex exec-server --remote "$remote" --environment-id "$environment_id"
