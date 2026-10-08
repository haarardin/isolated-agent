#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARNING: %s\n' "$*" >&2
}

command -v podman >/dev/null 2>&1 || fail "podman is not installed"

podman info >/dev/null 2>&1 || fail "podman is installed but not usable by the current user"

provider="${PODMAN_COMPOSE_PROVIDER:-podman-compose}"
command -v "${provider}" >/dev/null 2>&1 || fail "Compose provider is not installed: ${provider}"

if ! podman compose version >/dev/null 2>&1; then
  fail "podman compose cannot use provider: ${provider}"
fi

if ! podman compose config >/dev/null 2>&1; then
  fail "compose.yaml is not valid for the configured Compose provider"
fi

project_dir="${PROJECT_DIR:-}"

if [[ -z "${project_dir}" && -f .env ]]; then
  project_dir="$(sed -n 's/^PROJECT_DIR=//p' .env | tail -n1)"
fi

project_dir="${project_dir:-./workspace}"

[[ -d "${project_dir}" ]] || fail "PROJECT_DIR does not exist: ${project_dir}"

rootless="$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
[[ "${rootless}" == "true" ]] || fail "rootless Podman is required by the default sandbox profile"

if grep -R -E 'docker\.sock|podman\.sock|\.ssh([/:]|$)' compose*.yaml >/dev/null 2>&1; then
  fail "compose configuration contains a container-runtime socket or SSH path"
fi

printf 'Podman:          OK\n'
printf 'Compose:         OK\n'
printf 'Project dir:     %s\n' "${project_dir}"
printf 'Sandbox checks:  OK\n'
