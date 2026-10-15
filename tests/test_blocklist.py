import tempfile
import unittest
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render-blocklist.py"
spec = importlib.util.spec_from_file_location("render_blocklist", SCRIPT)
blocklist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blocklist)


class BlocklistTests(unittest.TestCase):
    def test_ipv4_ipv6_deduplicated(self):
        self.assertEqual(
            blocklist.parse_networks("127.0.0.0/8\nfc00::/7\n", "192.168.1.1,fc00::/7"),
            ["127.0.0.0/8", "fc00::/7", "192.168.1.1/32"],
        )

    def test_rejects_config_injection(self):
        for invalid in ("allowed.example.com", "192.168.0.0/16\nhttp_access allow all", "x/24"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    blocklist.parse_networks("127.0.0.0/8", invalid)

    def test_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            blocklist.parse_networks("# none\n", "")

    def test_output_not_overwritten_if_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "base"
            output = Path(temp) / "blocked"
            base.write_text("127.0.0.0/8\n")
            output.write_text("existing\n")
            with self.assertRaises(ValueError):
                blocklist.render(base, output, "invalid-input")
            self.assertEqual(output.read_text(), "existing\n")
            blocklist.render(base, output, "192.168.1.0/24")
            self.assertIn("192.168.1.0/24", output.read_text())

    def test_repo_base_has_private_ranges(self):
        base = Path(__file__).resolve().parents[1] / "config" / "blocked-cidrs.txt"
        networks = blocklist.parse_networks(base.read_text(), "")
        self.assertIn("192.168.0.0/16", networks)
        self.assertIn("fc00::/7", networks)
        self.assertIn("169.254.0.0/16", networks)


if __name__ == "__main__":
    unittest.main()
