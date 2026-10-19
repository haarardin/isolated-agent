#!/usr/bin/env bash
# A single generic bridge for declared Agent Tool LSP adapters. Tool-specific
# YAML edits are delegated to each tool's own Python environment.
set -Eeuo pipefail

mode="${1:-}"
case "$mode" in
  apply|check|probe) ;;
  *) echo "Usage: tool-lsp-runtime.sh apply|check|probe" >&2; exit 2 ;;
esac
manifest=/opt/isolated-agent/tool-lsp.json
[[ -f "$manifest" ]] || { echo "ERROR: tool-lsp.json missing; rebuild Project image" >&2; exit 1; }
jq -e 'type == "array"' "$manifest" >/dev/null

while IFS= read -r tool; do
  python_bin="$(jq -r '.python' <<<"$tool")"
  server_bin="$(jq -r '.command' <<<"$tool")"
  [[ -x "$python_bin" ]] || { echo "ERROR: LSP adapter Python missing: $python_bin" >&2; exit 1; }
  [[ -x "$server_bin" ]] || { echo "ERROR: LSP consumer missing: $server_bin" >&2; exit 1; }

  if [[ "$mode" == apply ]]; then
    "$python_bin" /usr/local/bin/isolated-agent-tool-lsp-configure "$tool"
  else
    "$python_bin" /usr/local/bin/isolated-agent-tool-lsp-configure --check "$tool"
  fi

  if [[ "$mode" == probe ]]; then
    # Serena 1.7's health-check starts its actual LanguageServerManager and
    # returns nonzero on initialization / symbols failure. This is purposely
    # explicit rather than running on every empty-workspace 'make doctor'.
    adapter="$(jq -r '.adapter' <<<"$tool")"
    case "$adapter" in
      serena)
        echo "Probing Serena LSP via project health-check (/workspace) ..."
        timeout 120 "$server_bin" project health-check /workspace
        ;;
      *) echo "ERROR: no probe for LSP consumer $adapter" >&2; exit 1 ;;
    esac
  fi
done < <(jq -c '.[]' "$manifest")
