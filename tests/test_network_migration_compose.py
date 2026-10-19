"""Execute network migration with fake Podman/Compose on a clean checkout."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NetworkMigrationComposeTests(unittest.TestCase):
    def test_migration_generates_overlay_and_stops_sidecars_without_volume_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"scripts").mkdir()
            (root/"dependencies").mkdir()
            (root/"bin").mkdir()
            for path in ["scripts/migrate-network.sh", "scripts/check-legacy-serena.py",
                         "scripts/dependencies.py", "dependencies/dependencies.toml",
                         "compose.yaml", "compose.web.yaml",
                         "compose.example-services.yaml"]:
                shutil.copy2(ROOT/path, root/path)
            # Exercise an enabled generic MCP sidecar, not just an empty overlay.
            (root/"dependencies/scripts").mkdir()
            shutil.copy2(ROOT/"dependencies/examples/ci-smoke.toml",
                         root/"dependencies/dependencies.toml")
            shutil.copy2(ROOT/"dependencies/scripts/install-ci-smoke.sh",
                         root/"dependencies/scripts/install-ci-smoke.sh")
            fake_podman = root/"bin/podman"
            fake_podman.write_text("""#!/usr/bin/env bash
if [[ "$1 $2 $3" == 'ps -a -q' ]]; then exit 0; fi
if [[ "$1 $2" == 'network exists' ]]; then exit 1; fi
echo "unexpected Podman: $*" >&2
exit 90
""")
            fake_podman.chmod(0o755)
            compose = root/"scripts/compose.sh"
            compose.write_text("""#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$*" == *".generated/compose.tools.yaml"* ]]
[[ "$*" != *"compose.serena.yaml"* ]]
[[ "$*" != *" --volumes"* ]]
[[ "$*" != *" -v"* ]]
for file in compose.yaml compose.web.yaml compose.example-services.yaml .generated/compose.tools.yaml; do
  [[ -f "$file" ]] || exit 51
done
printf '%s\\n' "$*" >> "$FAKE_COMPOSE_LOG"
""")
            compose.chmod(0o755)
            env = dict(os.environ)
            for name in ("SERENA_IMAGE", "SERENA_VERSION", "SERENA_PROJECT_KEY",
                         "SERENA_STATE_VOLUME", "SERENA_GOPLS_VERSION",
                         "SERENA_BIND_EXISTING_STATE", "SERENA_CREATE_NAMED_VOLUME"):
                env.pop(name, None)
            env.update(PATH=str(root/"bin") + os.pathsep + env.get("PATH",""),
                       PODMAN=str(fake_podman),
                       COMPOSE_PROJECT_NAME="isolated-agent-demo",
                       AGENT_NETWORK_NAME="isolated-agent-demo_isolated-dev",
                       PROJECT_IMAGE="localhost/isolated-agent-project-ci:dev",
                       FAKE_COMPOSE_LOG=str(root/"compose.log"))
            result = subprocess.run(["bash", "scripts/migrate-network.sh"],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertTrue((root/".generated/compose.tools.yaml").exists())
            self.assertIn("tool-ci-mcp",
                          (root/".generated/compose.tools.yaml").read_text())
            actual = (root/"compose.log").read_text().strip()
            self.assertIn(".generated/compose.tools.yaml", actual)
            self.assertNotIn("compose.serena.yaml", actual)
            self.assertTrue(actual.endswith(" down"), actual)


if __name__ == "__main__":
    unittest.main()
