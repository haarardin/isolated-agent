#!/usr/bin/env bash
set -Eeuo pipefail
# Reject stale containers after PROJECT_DIR, state, or enabled-agent changes.
# This must run before Compose can silently reuse a previous container.
cd "$(dirname "$0")/.."
id="$(bash scripts/service-id.sh agent || true)"
[[ -n "$id" ]] || exit 0
mounts="$(podman inspect "$id" --format '{{json .Mounts}}')"
codex_enabled="$(python3 scripts/dependencies.py agent-enabled --name codex)"
opencode_enabled="$(python3 scripts/dependencies.py agent-enabled --name opencode)"
python3 - "$mounts" "${PROJECT_DIR:-./workspace}" \
 "${CODEX_STATE_MOUNT_TYPE:?}" "${CODEX_STATE_MOUNT_SOURCE:?}" \
 "${CODEX_NAMED_VOLUME:?}" "$codex_enabled" "$opencode_enabled" <<'PY'
import json, os, pathlib, sys, tomllib
mounts, expected_path, expected_type, expected_source, expected_volume, codex_on, opencode_on = sys.argv[1:]
info = json.loads(mounts)
if not isinstance(info, list):
    raise SystemExit("ERROR: invalid running agent mounts")
by_dest = {m.get("Destination", ""): m for m in info}

def fail(message):
    raise SystemExit("ERROR: " + message + "; stop active turns, then make recreate-agent")

workspace = by_dest.get("/workspace", {})
if os.path.realpath(workspace.get("Source", "")) != os.path.realpath(expected_path):
    fail("existing agent uses another PROJECT_DIR")

codex = by_dest.get("/root/.codex")
if codex_on == "true":
    if codex is None:
        fail("enabled Codex state is not mounted")
    valid = (
        codex.get("Type", "").lower() == "bind" and
        os.path.realpath(codex.get("Source", "")) == os.path.realpath(expected_source)
    ) if expected_type == "bind" else (
        codex.get("Type", "").lower() == "volume" and
        codex.get("Name", "") == expected_volume
    )
    if not valid:
        fail("existing agent uses another Codex state volume")
elif codex is not None:
    fail("disabled Codex still has a volume mounted")

opencode = by_dest.get("/root/.isolated-opencode")
config = by_dest.get("/opt/isolated-agent/opencode-user.jsonc")
if opencode_on == "true":
    if not opencode or not config:
        fail("enabled OpenCode state/config is missing")
    manifest = tomllib.loads(pathlib.Path("dependencies/dependencies.toml").read_text())
    agent = next(a for a in manifest.get("agents", []) if a["id"] == "opencode")
    key = os.environ.get("CODEX_PROJECT_KEY", "")
    expected_state = pathlib.Path(agent["state"]["base"]) / key
    if (os.path.realpath(opencode.get("Source", "")) != os.path.realpath(expected_state)
            or os.path.realpath(config.get("Source", "")) !=
                os.path.realpath("config/opencode.jsonc")
            or config.get("RW", True) is not False):
        fail("existing OpenCode mounts do not match current config")
elif opencode is not None or config is not None:
    fail("disabled OpenCode still has a volume mounted")
PY
