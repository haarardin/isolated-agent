#!/usr/bin/env bash
set -euo pipefail

# Project context must come from /workspace, while /root remains runtime/global
# state. Keep this distinction stable across image, Compose and docs changes.

grep -Fq 'working_dir: /workspace' compose.yaml
grep -Fq '${PROJECT_DIR:-./workspace}:/workspace:rw' compose.yaml

grep -Fq 'CODEX_AGENTS_FILE=templates/AGENTS.global.md' .env.example
grep -Fq 'CODEX_AGENTS_FILE ?= templates/AGENTS.global.md' Makefile
grep -Fq 'ARG CODEX_AGENTS_FILE=templates/AGENTS.global.md' images/project/Containerfile

grep -Fq 'Treat /workspace as the canonical project root.' templates/AGENTS.global.md
grep -Fq '/workspace/AGENTS.md' templates/AGENTS.global.md
grep -Fq '/workspace/.codex/config.toml' templates/AGENTS.global.md
grep -Fq '/workspace/.serena/' templates/AGENTS.global.md

grep -Fq 'Adapt this file and place it at the root of the target project as AGENTS.md.' templates/AGENTS.project.md

grep -Fq -- '--project=/workspace' images/serena/Containerfile

grep -Fq 'Project root:     /workspace' scripts/doctor.sh
grep -Fq '/workspace/.codex/config.toml' scripts/doctor.sh

# The project template must never become the default image-global policy.
if grep -Eq 'CODEX_AGENTS_FILE(=| \?=)templates/AGENTS\.project\.md' .env.example Makefile images/project/Containerfile; then
  echo 'ERROR: project AGENTS template is configured as image-global policy' >&2
  exit 1
fi

echo 'Project context static checks: OK'
