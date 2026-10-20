#!/usr/bin/env bash
# Test direct invocation of the Compose wrapper without running Podman.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/scripts" "$scratch/bin"
cp scripts/compose.sh "$scratch/scripts/"
cat > "$scratch/bin/podman-compose" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s|%s|%s\n' "$COMPOSE_PROJECT_NAME" "$AGENT_NETWORK_NAME" "$*" > "$CAPTURE"
EOF
chmod +x "$scratch/bin/podman-compose"
cat > "$scratch/.env" <<'EOF'
COMPOSE_PROJECT_NAME=isolated-agent-sip-server
PROJECT_DIR=/workspace/repo
EOF
(
  cd "$scratch"
  env -u COMPOSE_PROJECT_NAME -u AGENT_NETWORK_NAME \
    PATH="$scratch/bin:$PATH" CAPTURE="$scratch/captured" \
    bash scripts/compose.sh -f compose.yaml up -d squid
)
test "$(cat "$scratch/captured")" = \
  'isolated-agent-sip-server|isolated-agent-sip-server_isolated-dev|-f compose.yaml up -d squid'
cat >> "$scratch/.env" <<'EOF'
AGENT_NETWORK_NAME=team-bridge
EOF
(
  cd "$scratch"
  env -u COMPOSE_PROJECT_NAME -u AGENT_NETWORK_NAME \
    PATH="$scratch/bin:$PATH" CAPTURE="$scratch/captured" \
    bash scripts/compose.sh ps
)
test "$(cat "$scratch/captured")" = 'isolated-agent-sip-server|team-bridge|ps'
(
  cd "$scratch"
  COMPOSE_PROJECT_NAME=custom AGENT_NETWORK_NAME=override \
    PATH="$scratch/bin:$PATH" CAPTURE="$scratch/captured" \
    bash scripts/compose.sh ps
)
test "$(cat "$scratch/captured")" = 'custom|override|ps'
if (
  cd "$scratch"
  COMPOSE_PROJECT_NAME=../bad AGENT_NETWORK_NAME=good \
    PATH="$scratch/bin:$PATH" CAPTURE="$scratch/captured" \
    bash scripts/compose.sh ps >/dev/null 2>&1
); then
  echo 'ERROR: invalid name accepted' >&2
  exit 1
fi
echo 'Direct Compose project/network identity: OK'
