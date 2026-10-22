#!/usr/bin/env bash
set -euo pipefail
APP="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$APP"
export COMPOSE_PROJECT_NAME=isolated-job-apply
export BROWSER_MODE="$(cat state/browser-mode)"
echo "Smoke: DOCX table, LibreOffice, PDF render and text"
podman-compose -f compose.yaml exec -T agent python3 /opt/jobapply/jobctl.py smoke
echo "Smoke: Chromium, example.com, screenshot and local file-upload form"
podman-compose -f compose.yaml exec -T browser node /opt/jobapply/smoke_browser.js
echo "Smoke: configured MCP servers"
podman-compose -f compose.yaml exec -T agent codex mcp list
echo "PASS: smoke suite (no external application was submitted)"
