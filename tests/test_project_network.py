"""Project-scoped Podman network selection and reuse, without live Podman."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts/network-preflight.py"
spec = importlib.util.spec_from_file_location("project_network", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def net(name, subnet, internal=True, driver="bridge", ipv6=False, labels=None):
    return {"name": name, "internal": internal, "driver": driver,
            "ipv6_enabled": ipv6, "subnets": [{"subnet": subnet}],
            "labels": labels or {}}


class ProjectNetworkTests(unittest.TestCase):
    def test_independent_projects_select_distinct_subnets(self):
        a, _ = mod.resolve([], "backend-a", "auto", None)
        b, _ = mod.resolve([net("backend-a_isolated-dev", a)], "backend-b", "auto", None)
        self.assertNotEqual(a, b)

    def test_two_compose_projects_share_explicit_network_name(self):
        # First creates with network-scoped label; second reuses with no
        # change to its own Compose identity or named volumes.
        chosen = "team-development"
        subnet, exists = mod.resolve([], "api-one", "auto", None, chosen)
        self.assertFalse(exists)
        existing = net(chosen, subnet, labels={mod.NETWORK_LABEL: chosen})
        reused, exists = mod.resolve([existing], "api-two", "auto", None, chosen)
        self.assertTrue(exists)
        self.assertEqual(subnet, reused)

    def test_shared_name_reuses_legacy_project_owned_network(self):
        existing = net("api-one_isolated-dev", "10.203.44.0/24",
                       labels={mod.MANAGED_LABEL: "api-one"})
        subnet, exists = mod.resolve([existing], "api-two", "auto", None,
                                      "api-one_isolated-dev")
        self.assertTrue(exists)
        self.assertEqual(subnet, "10.203.44.0/24")

    def test_legacy_project_owned_network_not_implicitly_shared(self):
        existing = net("api-one_isolated-dev", "10.203.44.0/24",
                       labels={mod.MANAGED_LABEL: "another-owner"})
        with self.assertRaisesRegex(ValueError, "belongs to"):
            mod.resolve([existing], "api-one", "auto", None)

    def test_unsafe_shared_network_rejected(self):
        for params in ({"internal": False}, {"driver": "macvlan"}, {"ipv6": True}):
            with self.subTest(params=params):
                existing = net("team-development", "10.203.44.0/24", **params)
                with self.assertRaises(ValueError):
                    mod.resolve([existing], "api-two", "auto", None,
                                "team-development")

    def test_custom_network_name_validation(self):
        with self.assertRaises(ValueError):
            mod.network_name("api-one", "../../invalid")
        self.assertEqual(mod.network_name("api-one", "team-development"), "team-development")

    def test_switch_from_private_to_shared_network_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "network.json"
            mod.save_state(state, "api-one", "10.203.11.0/24")
            self.assertIsNone(mod.load_state(state, "api-one", "team-development"))
            mod.save_state(state, "api-one", "10.203.44.0/24", "team-development")
            self.assertEqual(mod.load_state(state, "api-one", "team-development"),
                             "10.203.44.0/24")

    def test_reuse_same_project_network_and_cidr(self):
        existing = net("my-project_isolated-dev", "10.203.55.0/24", labels={
            mod.MANAGED_LABEL: "my-project"
        })
        subnet, exists = mod.resolve([existing], "my-project", "auto", None)
        self.assertTrue(exists)
        self.assertEqual(subnet, "10.203.55.0/24")

    def test_wrong_owner_name_is_rejected(self):
        existing = net("my-project_isolated-dev", "10.203.55.0/24", labels={
            mod.MANAGED_LABEL: "unrelated"
        })
        with self.assertRaisesRegex(ValueError, "belongs to"):
            mod.resolve([existing], "my-project", "auto", None)

    def test_unrestricted_same_name_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "NOT internal"):
            mod.resolve([net("my-project_isolated-dev", "10.203.55.0/24", internal=False)],
                        "my-project", "auto", None)

    def test_wrong_driver_and_ipv6_rejected(self):
        for network in (
            net("my-project_isolated-dev", "10.203.55.0/24", driver="macvlan"),
            net("my-project_isolated-dev", "10.203.55.0/24", ipv6=True),
        ):
            with self.subTest(network=network):
                with self.assertRaises(ValueError):
                    mod.resolve([network], "my-project", "auto", None)

    def test_explicit_different_subnet_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            mod.resolve([net("my-project_isolated-dev", "10.203.55.0/24")],
                        "my-project", "10.203.56.0/24", None)

    def test_overlap_with_unrelated_network_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            mod.resolve([net("other_net", "10.203.0.0/16")],
                        "my-project", "10.203.55.0/24", None)

    def test_persisted_subnet_stable_after_removal(self):
        subnet, exists = mod.resolve([], "my-project", "auto", "10.203.55.0/24")
        self.assertFalse(exists)
        self.assertEqual(subnet, "10.203.55.0/24")

    def test_existing_subnet_must_match_saved_registry(self):
        with self.assertRaisesRegex(ValueError, "Saved subnet"):
            mod.resolve([net("my-project_isolated-dev", "10.203.55.0/24")],
                        "my-project", "auto", "10.203.56.0/24")

    def test_create_once_then_reuse(self):
        project = "my-project"
        created = []
        networks = []
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "network.json"

            def fake_run(argv, **kwargs):
                created.append(argv)
                networks.append(net(
                    mod.network_name(project), "10.203.56.0/24", labels={
                        mod.MANAGED_LABEL: project
                    }))
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch.object(mod, "inspect_networks", side_effect=lambda: list(networks)), \
                 mock.patch.object(mod.subprocess, "run", side_effect=fake_run):
                subnet, action = mod.run(project, "10.203.56.0/24", state, True)
                self.assertEqual(action, "created")
                self.assertEqual(subnet, "10.203.56.0/24")
                _, second_action = mod.run(project, "auto", state, True)
                self.assertEqual(second_action, "reused")
                self.assertEqual(len(created), 1)
            self.assertEqual(json.loads(state.read_text())["name"], "my-project_isolated-dev")

    def test_explicit_ipv6_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "IPv4"):
                mod.run("test-project", "fd00::/64", Path(temp) / "network.json", False)

    def test_reject_bad_project_name(self):
        with self.assertRaises(ValueError):
            mod.network_name("../../other")
        with self.assertRaises(ValueError):
            mod.network_name("other space")


if __name__ == "__main__":
    unittest.main()
