#!/usr/bin/env bash
# Install official standalone Codex and keep its COMPLETE runtime package.
# Executed only when [[agents]] id="codex", enabled=true.
set -Eeuo pipefail

curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex --version

source_dir=/root/.codex/packages/standalone
target_dir=/opt/isolated-agent/codex-standalone
test -x "$source_dir/current/bin/codex"
test -f "$source_dir/current/codex-package.json"
release_dir="$(readlink -f "$source_dir/current")"
test -d "$release_dir"
release_name="$(basename "$release_dir")"

mkdir -p "$target_dir" /root/.local/bin
cp -a "$source_dir/." "$target_dir/"
test -d "$target_dir/releases/$release_name"
ln -sfn "releases/$release_name" "$target_dir/current"
test -x "$target_dir/current/bin/codex"
test -f "$target_dir/current/codex-package.json"
test -x "$target_dir/current/bin/codex-code-mode-host"
test -x "$target_dir/current/codex-path/rg"
ln -sfn "$target_dir/current/bin/codex" /usr/local/bin/codex
ln -sfn "$target_dir/current/bin/codex" /root/.local/bin/codex
test "$(readlink -f /usr/local/bin/codex)" = "$(readlink -f /root/.local/bin/codex)"
codex --version
