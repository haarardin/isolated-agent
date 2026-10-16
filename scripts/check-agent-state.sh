#!/usr/bin/env bash
set -Eeuo pipefail
# Do not silently keep a still-running old Codex container after PROJECT_DIR
# changes: podman-compose may reuse it instead of adopting new mounts.
cd "$(dirname "$0")/.."
id="$(bash scripts/service-id.sh agent || true)"
[[ -n "$id" ]] || exit 0
mounts="$(podman inspect "$id" --format '{{json .Mounts}}')"
python3 - "$mounts" "${PROJECT_DIR:-./workspace}" "${CODEX_STATE_VOLUME:?}" <<'PY'
import json, os, sys
mounts, expected_path, expected_volume = sys.argv[1:]
info = json.loads(mounts)
if not isinstance(info, list):
    raise SystemExit("ERROR: invalid running agent mounts")
by_dest = {m.get("Destination", ""): m for m in info}
workspace = by_dest.get("/workspace", {})
codex = by_dest.get("/root/.codex", {})
actual_path = workspace.get("Source", "")
current_volume = codex.get("Name", "")
want_path = os.path.realpath(expected_path)
if os.path.realpath(actual_path) != want_path or current_volume != expected_volume:
    print("ERROR: existing agent uses another project path or Codex state volume", file=sys.stderr)
    print(f"Expected workspace: {want_path}", file=sys.stderr)
    print(f"Expected CODEX_STATE_VOLUME: {expected_volume}", file=sys.stderr)
    print("Stop/save active turns, then use make recreate-agent (or make up-serena).", file=sys.stderr)
    raise SystemExit(1)
PY
