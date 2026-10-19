"""Legacy Serena configuration must fail before provisioning, not lose state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("legacy_serena", ROOT / "scripts/check-legacy-serena.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class LegacyMigrationGuardTests(unittest.TestCase):
    def test_old_named_volume_or_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / ".env"
            settings.write_text("# SERENA_VERSION=ignored\n"
                                "CODEX_STATE_VOLUME=./volumes/codex\n"
                                "SERENA_STATE_VOLUME=legacy-serena-state\n"
                                "SERENA_IMAGE=localhost/serena:dev\n")
            self.assertEqual(guard.obsolete_keys(settings, {}),
                             {"SERENA_STATE_VOLUME", "SERENA_IMAGE"})
            self.assertEqual(guard.obsolete_keys(settings, {"SERENA_VERSION": "1.7.0"}),
                             {"SERENA_STATE_VOLUME", "SERENA_IMAGE", "SERENA_VERSION"})

    def test_generic_module_needs_no_legacy_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / ".env"
            settings.write_text("CODEX_STATE_VOLUME=./volumes/codex\n"
                                "# SERENA_STATE_VOLUME=unused\n")
            self.assertEqual(guard.obsolete_keys(settings, {}), set())
            self.assertEqual(guard.obsolete_keys(settings.with_name("missing"), {}), set())
        self.assertFalse(any("SERENA_" in line and not line.lstrip().startswith("#")
                             for line in (ROOT / ".env.example").read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
