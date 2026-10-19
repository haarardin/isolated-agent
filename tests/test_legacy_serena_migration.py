"""Legacy Serena detection: verify old images and generic Agent Tools via make up."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("legacy_serena", ROOT / "scripts/check-legacy-serena.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
CID = "a"*64


def record(project="isolated-agent-demo", service="agent",
           image="localhost/isolated-agent-serena-old:dev", old_env=False):
    return {
        "Id": CID,
        "ImageName": image,
        "Config": {
            "Labels": {"io.podman.compose.project": project,
                       "io.podman.compose.service": service},
            "Env": (["SERENA_PROJECT_KEY=old"] if old_env else ["HOME=/root"]),
            "Image": image,
        },
        "Mounts": [{"Type": "bind", "Destination": "/root/.serena",
                    "Source": "/safe/serena"}],
    }


class MigrationGuardTests(unittest.TestCase):
    def test_existing_old_env_settings(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td)/".env"
            f.write_text("# SERENA_VERSION=comment\nSERENA_STATE_VOLUME=old-volume\n")
            self.assertEqual(guard.obsolete_keys(f, {}), {"SERENA_STATE_VOLUME"})
            self.assertEqual(guard.obsolete_keys(f, {"SERENA_IMAGE": "custom"}),
                             {"SERENA_STATE_VOLUME", "SERENA_IMAGE"})

    def test_old_image_custom_environment_and_generic_differ(self):
        self.assertIn("legacy Serena agent image", guard.legacy_agent(record(), "unused"))
        self.assertIn("legacy Serena container environment",
                      guard.legacy_agent(record(image="custom:dev",old_env=True), "unused"))
        self.assertIn("unrecognized agent image",
                      guard.legacy_agent(record(image="custom:dev"), "localhost/isolated-agent-project-ci:dev"))
        self.assertIsNone(guard.legacy_agent(
            record(image="localhost/isolated-agent-project-ci:dev"),
            "localhost/isolated-agent-project-ci:dev"))

    def make_fixture(self, root, agent):
        (root/"scripts").mkdir()
        (root/"bin").mkdir()
        for path in ["Makefile", "scripts/check-legacy-serena.py", "scripts/project-state.py"]:
            shutil.copy2(ROOT/path, root/path)
        (root/"scripts/check-agent-state.sh").write_text("#!/bin/sh\nexit 0\n")
        (root/"inspect.json").write_text(json.dumps([agent] if agent else []))
        podman = root/"bin/podman"
        podman.write_text("""#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
records=json.load(open(os.environ['FAKE_PODMAN_RECORDS']))
if args==['ps','-a','-q']:
    print('\\n'.join(v['Id'] for v in records))
elif args[0]=='inspect':
    print(json.dumps([v for v in records if v['Id']==args[1]]))
else:
    print('unexpected Podman request: '+str(args),file=sys.stderr)
    sys.exit(90)
""")
        podman.chmod(0o755)
        compose = root/"fake-compose.sh"
        compose.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$FAKE_COMPOSE_LOG\"\n")
        compose.chmod(0o755)
        (root/"override.mk").write_text("""preflight:
\t@python3 scripts/check-legacy-serena.py --project "$(COMPOSE_PROJECT_NAME)" --podman "$(PODMAN)" --project-image "$(PROJECT_IMAGE)"
network-ensure: preflight
\t@true
prepare-state:
\t@true
deps-generate:
\t@true
deps-tool-state:
\t@true
deps-reconcile:
\t@true
prepare-web: preflight
\t@true
""")
        return podman,compose

    def make_up(self, root, agent):
        podman,compose=self.make_fixture(root,agent)
        env={k:v for k,v in os.environ.items() if k not in guard.LEGACY_KEYS}
        env["FAKE_PODMAN_RECORDS"]=str(root/"inspect.json")
        env["FAKE_COMPOSE_LOG"]=str(root/"compose.log")
        result=subprocess.run([
            "make","--no-print-directory","-s","-f","Makefile","-f","override.mk",
            "up",f"PODMAN={podman}",f"COMPOSE_WEB=bash {compose}",
            "COMPOSE_PROJECT_NAME=isolated-agent-demo",
            "PROJECT_IMAGE=localhost/isolated-agent-project-ci:dev",
        ],cwd=root,env=env,capture_output=True,text=True)
        return result,(root/"compose.log")

    def test_make_up_refuses_old_default_image_before_compose(self):
        # Original make up-serena used defaults, with no SERENA_* in .env.
        with tempfile.TemporaryDirectory() as td:
            res,log=self.make_up(Path(td),record())
            self.assertNotEqual(res.returncode,0,res.stdout+res.stderr)
            self.assertIn("legacy Serena agent image",res.stderr)
            self.assertIn("make remove-agent",res.stderr)
            self.assertFalse(log.exists())

    def test_make_up_accepts_current_generic_serena_mount(self):
        with tempfile.TemporaryDirectory() as td:
            res,log=self.make_up(
                Path(td),record(image="localhost/isolated-agent-project-ci:dev"))
            self.assertEqual(res.returncode,0,res.stdout+res.stderr)
            self.assertEqual(log.read_text().strip(),"up -d")

    def test_unrelated_project_legacy_agent_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            res,log=self.make_up(Path(td),record(project="another-project"))
            self.assertEqual(res.returncode,0,res.stdout+res.stderr)
            self.assertEqual(log.read_text().strip(),"up -d")


if __name__=="__main__":
    unittest.main()
