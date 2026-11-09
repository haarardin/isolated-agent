#!/usr/bin/env bash
set -Eeuo pipefail

compose=(bash scripts/compose.sh)
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
"${compose[@]}" ps >/dev/null 2>&1 || fail "Compose environment is not available"

"${compose[@]}" exec agent sh -c '
set -eu

enabled=/opt/isolated-agent/agents-enabled.txt
test -f "$enabled" || { echo "ERROR: missing enabled-agent manifest" >&2; exit 1; }

printf "PATH:            %s\n" "$PATH"
if grep -Fxq codex "$enabled"; then
    command -v codex >/dev/null 2>&1 || {
        echo "ERROR: enabled Codex binary missing" >&2; exit 1;
    }
    printf "Codex:           "
    codex --version
    cli_executable="$(readlink -f "$(command -v codex)")"
    package_root="$(dirname "$(dirname "$cli_executable")")"
    test -f "$package_root/codex-package.json" &&
      test -x "$package_root/bin/codex-code-mode-host" || {
        echo "ERROR: incomplete Codex managed runtime package" >&2; exit 1;
      }
    test -w /root/.codex || { echo "ERROR: Codex state not writable" >&2; exit 1; }
else
    if command -v codex >/dev/null 2>&1; then
        echo "ERROR: disabled Codex binary is installed" >&2; exit 1;
    fi
    printf "Codex:           disabled\n"
fi

if grep -Fxq opencode "$enabled"; then
    command -v opencode >/dev/null 2>&1 || {
        echo "ERROR: enabled OpenCode binary missing" >&2; exit 1;
    }
    printf "OpenCode:        "
    opencode --version
    test -w /root/.isolated-opencode &&
      test -r /opt/isolated-agent/opencode-user.jsonc || {
        echo "ERROR: OpenCode state/config mount is unavailable" >&2; exit 1;
      }
else
    if command -v opencode >/dev/null 2>&1; then
        echo "ERROR: disabled OpenCode binary is installed" >&2; exit 1;
    fi
    printf "OpenCode:        disabled\n"
fi

if command -v go >/dev/null 2>&1; then
    printf "Go:              "
    go version
else
    printf "Go:              not installed (optional)\n"
fi

test "$(pwd -P)" = /workspace || {
    echo "ERROR: expected working directory /workspace" >&2; exit 1;
}
test -w /workspace || { echo "ERROR: workspace not writable" >&2; exit 1; }
test -w /root/.cache || { echo "ERROR: build cache not writable" >&2; exit 1; }

if touch /isolated-agent-doctor-root-write-test 2>/dev/null; then
    rm -f /isolated-agent-doctor-root-write-test || true
    echo "ERROR: container root filesystem writable" >&2
    exit 1
fi

printf "Project root:     /workspace\n"
printf "Workspace:        writable\n"
printf "Root filesystem:  read-only\n"

if [ -f /workspace/AGENTS.md ]; then
    printf "Project AGENTS:   present\n"
else
    printf "Project AGENTS:   not present (optional)\n"
fi
if [ -d /workspace/.serena ]; then
    printf "Serena project:  initialized\n"
else
    printf "Serena project:  not initialized\n"
fi

bash /usr/local/bin/isolated-agent-tool-lsp-runtime check
printf "Runtime doctor:   OK\n"
'
