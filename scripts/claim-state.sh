#!/usr/bin/env bash
# Claim a persistent volume for exactly one Compose deployment + PROJECT_DIR.
# Refuse silent reuse of an already-populated/other-project CODEX_HOME.
set -Eeuo pipefail
if (( $# != 4 )); then
  echo "Usage: claim-state.sh DIRECTORY PROJECT_KEY ALLOW_EXISTING COMPONENT" >&2
  exit 2
fi
root="$1"
key="$2"
allow="$3"
component="$4"
[[ "$key" =~ ^[0-9a-f]{24}$ ]] || {
  echo "ERROR: $component project key missing or invalid; use make targets" >&2
  exit 2
}
[[ "$component" == codex || "$component" == serena ]] || exit 2
[[ "$allow" == true || "$allow" == false ]] || {
  echo "ERROR: $component legacy state confirmation must be true or false" >&2
  exit 2
}
mkdir -p "$root"
marker="$root/.isolated-agent-project-key"
[[ ! -L "$marker" ]] || { echo "ERROR: refusing symlink project marker in $component state" >&2; exit 1; }
if [[ -e "$marker" ]]; then
  actual="$(cat "$marker")"
  [[ "$actual" == "$key" ]] || {
    echo "ERROR: $component persistent volume belongs to a different PROJECT_DIR or Compose project." >&2
    echo "Choose a different volume name. Never reuse a CODEX_HOME volume across projects." >&2
    exit 1
  }
  exit 0
fi
# An old Codex/Serena volume has no marker but already contains user data.
# It must be explicitly adopted to avoid silent memory contamination.
if [[ -n "$(find "$root" -mindepth 1 -maxdepth 1 -print -quit)" && "$allow" != true ]]; then
  echo "ERROR: existing unbound $component state detected at $root" >&2
  echo "Check it belongs to this project, then temporarily set the corresponding BIND_EXISTING_STATE=true option." >&2
  echo "Set the option back to false afterward. No data has been removed." >&2
  exit 1
fi
umask 077
# noclobber avoids one process overwriting another process's claim.
if ! ( set -C; printf '%s\n' "$key" > "$marker" ) 2>/dev/null; then
  echo "ERROR: $component state volume was concurrently claimed; retry/inspect" >&2
  exit 1
fi
