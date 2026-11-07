#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /opt/agent-tools/playwright /opt/ms-playwright
npm install --prefix /opt/agent-tools/playwright --no-audit --no-fund --save-exact '@playwright/mcp@0.0.84'
export PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
/opt/agent-tools/playwright/node_modules/.bin/playwright install --with-deps chromium
cat >/usr/local/bin/isolated-agent-playwright-mcp <<'SH'
#!/bin/sh
export PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
exec /opt/agent-tools/playwright/node_modules/.bin/playwright-mcp "$@"
SH
chmod 0755 /usr/local/bin/isolated-agent-playwright-mcp
/usr/local/bin/isolated-agent-playwright-mcp --help >/dev/null
rm -rf /var/lib/apt/lists/*
