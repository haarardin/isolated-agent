import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "network-preflight.py"
spec = importlib.util.spec_from_file_location("network_preflight", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NetworkPreflightTests(unittest.TestCase):
    def test_unused_subnet(self):
        existing = [{"name": "podman", "internal": False,
                     "subnets": [{"subnet": "10.88.0.0/16"}]}]
        self.assertEqual(module.find_collisions(existing, "10.89.71.0/24", "demo_isolated"), [])

    def test_previous_standalone_network_blocks_compose(self):
        existing = [{"name": "isolated-ui-int", "internal": True,
                     "subnets": [{"subnet": "10.89.71.0/24"}]}]
        errors = module.find_collisions(existing, "10.89.71.0/24", "isolated-agent-demo_isolated-dev")
        self.assertTrue(errors)
        self.assertIn("isolated-ui-int", errors[0])

    def test_overlapping_broader_network(self):
        existing = [{"name": "other", "internal": False,
                     "subnets": [{"subnet": "10.89.0.0/16"}]}]
        self.assertTrue(module.find_collisions(existing, "10.89.71.0/24", "demo_isolated"))

    def test_project_owned_network_is_reusable(self):
        existing = [{"name": "demo_isolated", "internal": True,
                     "subnets": [{"subnet": "10.89.71.0/24"}]}]
        self.assertEqual(module.find_collisions(existing, "10.89.71.0/24", "demo_isolated"), [])

    def test_project_owned_network_must_be_internal(self):
        existing = [{"name": "demo_isolated", "internal": False,
                     "subnets": [{"subnet": "10.89.71.0/24"}]}]
        errors = module.find_collisions(existing, "10.89.71.0/24", "demo_isolated")
        self.assertTrue(any("NOT internal" in error for error in errors))

    def test_project_owned_network_must_match_cidr(self):
        existing = [{"name": "demo_isolated", "internal": True,
                     "subnets": [{"subnet": "10.89.72.0/24"}]}]
        self.assertTrue(module.find_collisions(existing, "10.89.71.0/24", "demo_isolated"))

    def test_ipv6_other_network_no_conflict(self):
        existing = [{"name": "v6-net", "internal": False,
                     "subnets": [{"subnet": "fd00::/64"}]}]
        self.assertEqual(module.find_collisions(existing, "10.89.71.0/24", "demo_isolated"), [])


if __name__ == "__main__":
    unittest.main()
