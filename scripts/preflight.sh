#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v podman >/dev/null 2>&1 || fail "podman is not installed"

podman info >/dev/null 2>&1 || fail "podman is installed but not usable by the current user"

if ! podman compose version >/dev/null 2>&1; then
  fail "podman compose has no usable Compose provider"
fi

project_dir="${PROJECT_DIR:-}"

if [[ -z "${project_dir}" && -f .env ]]; then
  project_dir="$(sed -n 's/^PROJECT_DIR=//p' .env | tail -n1)"
fi

project_dir="${project_dir:-./workspace}"

[[ -d "${project_dir}" ]] || fail "PROJECT_DIR does not exist: ${project_dir}"

printf 'Podman:          OK\n'
printf 'Compose:         OK\n'
printf 'Project dir:     %s\n' "${project_dir}"
printf 'Sandbox checks:  OK\n'

if grep -R -E '/var/run/docker\.sock|podman\.sock|/home/[^$]|/root' compose*.yaml >/dev/null 2>&1; then
  printf 'WARNING: compose files contain potentially sensitive host paths or runtime sockets. Review them manually.\n' >&2
fi
