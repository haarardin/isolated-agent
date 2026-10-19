#!/usr/bin/env bash
# Exercise the real Makefile recipe without launching Podman or touching
# developer state/config. Regression: make expanded $services into "ervices".
set -Eeuo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/scripts" "$tmp/dependencies/scripts"
cp Makefile "$tmp/Makefile"
cp scripts/dependencies.py scripts/project-state.py scripts/reconcile-tool-sidecars.py "$tmp/scripts/"
cat > "$tmp/fake-podman.sh" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "ps" ]] && exit 0
exit 2
EOF
chmod 0755 "$tmp/fake-podman.sh"
cp dependencies/dependencies.toml "$tmp/dependencies/dependencies.toml"
cp dependencies/scripts/install-ci-smoke.sh "$tmp/dependencies/scripts/"

cat > "$tmp/fake-compose.sh" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >> "$FAKE_COMPOSE_LOG"
EOF
chmod 0755 "$tmp/fake-compose.sh"
log="$tmp/calls.log"

# Default TOML has Serena disabled/no sidecars. Compose must not be invoked
# at all, not even with a spurious "ervices" service.
(
  cd "$tmp"
  FAKE_COMPOSE_LOG="$log" make --no-print-directory -s deps-tools-up \
    COMPOSE_WEB="bash $tmp/fake-compose.sh" PODMAN="bash $tmp/fake-podman.sh"
)
test ! -e "$log" || {
  printf 'ERROR: Compose invoked without enabled sidecars: %s\n' "$(cat "$log")" >&2
  exit 1
}

# A real enabled sidecar fixture must invoke Compose with exactly one service.
cp dependencies/examples/ci-smoke.toml "$tmp/dependencies/dependencies.toml"
(
  cd "$tmp"
  FAKE_COMPOSE_LOG="$log" make --no-print-directory -s deps-tools-up \
    COMPOSE_WEB="bash $tmp/fake-compose.sh" PODMAN="bash $tmp/fake-podman.sh"
)
test "$(cat "$log")" = 'up -d tool-ci-mcp' || {
  printf 'ERROR: expected only tool-ci-mcp; got: %s\n' "$(cat "$log")" >&2
  exit 1
}
# Run actual make offline with fake Podman/Compose: verify sidecar+agent.
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/scripts/check-agent-state.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$tmp/scripts/remove-service.sh"
cat > "$tmp/override.mk" <<'EOF'
preflight:
	@true
network-ensure:
	@true
prepare-state:
	@true
EOF
: > "$log"
(
  cd "$tmp"
  FAKE_COMPOSE_LOG="$log" make --no-print-directory -s -f Makefile -f override.mk offline \
    COMPOSE_OFFLINE="bash $tmp/fake-compose.sh" PODMAN="bash $tmp/fake-podman.sh"
)
test "$(cat "$log")" = "$(printf 'up -d tool-ci-mcp\nup -d agent')" || {
  printf 'ERROR: offline must start sidecar and agent without squid: %s\n' "$(cat "$log")" >&2
  exit 1
}
echo 'Agent Tools Make lifecycle: OK'
