#!/usr/bin/env bash
set -Eeuo pipefail
# CI-only local installer: demonstrates declared scripts work without Go.
cat >/usr/local/bin/isolated-agent-smoke-tool <<'EOF'
#!/bin/sh
printf 'smoke-installed\n'
EOF
chmod 0755 /usr/local/bin/isolated-agent-smoke-tool
