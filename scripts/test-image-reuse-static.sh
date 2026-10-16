#!/usr/bin/env bash
set -euo pipefail

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

log="${tmpdir}/podman.log"
fake_podman="${tmpdir}/podman"

cat > "${fake_podman}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "${FAKE_PODMAN_LOG:?}"

if [[ "${1:-}" == "image" && "${2:-}" == "exists" && -n "${3:-}" ]]; then
  exit 0
fi

printf 'unexpected fake podman invocation: %s\n' "$*" >&2
exit 99
EOF

chmod +x "${fake_podman}"

key="$(python3 scripts/project-state.py --project-dir "./workspace" --compose-project "isolated-agent-demo" --field key)"
output="$(
  FAKE_PODMAN_LOG="${log}" \
    make --no-print-directory PODMAN="${fake_podman}" ensure-images
)"

for image in \
  localhost/isolated-agent-base:dev \
  localhost/isolated-agent-codex:dev \
  "localhost/isolated-agent-project-${key}:dev" \
  "localhost/isolated-agent-serena-${key}:dev"
do
  printf '%s\n' "${output}" | grep -Fq "Reusing existing image: ${image}"
  grep -Fq "image exists ${image}" "${log}"
done

if grep -Eq '(^| )build( |$)' "${log}"; then
  echo 'ERROR: ensure-images rebuilt an image that already exists' >&2
  cat "${log}" >&2
  exit 1
fi

echo 'Image reuse static test: OK'
