#!/usr/bin/env bash
# Install the isolated job-application profile without touching the development profile.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
APP="$ROOT/job-apply"
STATE="$APP/state"
umask 077

fail() { echo "ERROR: $*" >&2; exit 1; }
[[ -r /etc/os-release ]] || fail "Cannot identify OS"
. /etc/os-release
[[ "$ID" == debian && "${VERSION_ID%%.*}" == 13 ]] || fail "Debian 13 required"
[[ "$(uname -m)" == x86_64 || "$(uname -m)" == aarch64 ]] || fail "Supported: amd64/arm64"
for dep in podman podman-compose make python3; do command -v "$dep" >/dev/null || fail "Install host dependency: $dep"; done
[[ "$(podman info --format '{{.Host.Security.Rootless}}')" == true ]] || fail "Rootless Podman required"
for dir in candidate applications approvals browser-profile captures downloads vnc codex cache; do
  mkdir -p "$STATE/$dir"
  chmod 700 "$STATE/$dir"
done
for name in profile.json master-resume.json answers.json preferences.json; do
  if [[ ! -e "$STATE/candidate/$name" ]]; then
    cp "$APP/examples/$name" "$STATE/candidate/$name"
    chmod 600 "$STATE/candidate/$name"
  fi
done
if [[ ! -f "$STATE/codex/config.toml" ]]; then
  cat > "$STATE/codex/config.toml" <<'TOML'
# Codex user configuration for the dedicated job-application container.
sandbox_mode = "danger-full-access"
approval_policy = "never"
[mcp_servers.playwright]
url = "http://browser:8931/mcp"
startup_timeout_sec = 40
tool_timeout_sec = 90
[mcp_servers.docx]
command = "/usr/local/bin/docx-mcp-server"
startup_timeout_sec = 30
tool_timeout_sec = 60
TOML
  chmod 600 "$STATE/codex/config.toml"
else
  if ! grep -q 'mcp_servers.playwright' "$STATE/codex/config.toml"; then
    fail "Existing Codex config lacks job-apply MCP. Keep it safe; configure manually."
  fi
fi
[[ -f "$STATE/browser-mode" ]] || printf 'headless\n' > "$STATE/browser-mode"
cd "$ROOT"
python3 -m unittest discover -s job-apply -p test_state.py
make ensure-codex-image
if ! podman image exists localhost/isolated-job-apply:dev || [[ "${1:-}" == "--rebuild" ]]; then
  podman build -f job-apply/Containerfile \
    --build-arg CODEX_IMAGE=localhost/isolated-agent-codex:dev \
    -t localhost/isolated-job-apply:dev .
fi
if [[ ! -f "$STATE/vnc/passwd" ]]; then
  python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(8)))" > "$STATE/vnc/password.txt"
  cat "$STATE/vnc/password.txt" | podman run --rm -i \
     -v "$STATE/vnc:/secrets:rw" localhost/isolated-job-apply:dev \
     sh -c 'IFS= read -r secret; x11vnc -storepasswd "$secret" /secrets/passwd >/dev/null'
  chmod 600 "$STATE/vnc/"{passwd,password.txt}
fi
"$APP/run.sh" up
"$APP/smoke.sh"
cat <<'INFO'
Installation finished. Private candidate data: job-apply/state/candidate/
Import your existing baseline DOCX into master-resume.docx there.
Authenticate: ./job-apply/run.sh login
Start agent:  ./job-apply/run.sh agent
Headed mode:  ./job-apply/run.sh browser headed
VNC (loopback only): localhost:5901; password: job-apply/state/vnc/password.txt
See job-apply/README.md; never commit job-apply/state/.
INFO
