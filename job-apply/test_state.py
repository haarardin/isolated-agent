"""Host-only tests for idempotence, transitions, approvals, and duplicate prevention."""
import json
from pathlib import Path
import tempfile
import unittest
import jobctl

class ApplicationStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "applications").mkdir()
        (self.root / "approvals").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_creation_is_idempotent_and_submitted_cannot_repeat(self):
        url = "https://example.com/jobs/senior-go"
        jobctl.new_record(self.root, url, "Example", "Senior Go Engineer")
        apps = list((self.root / "applications").iterdir())
        self.assertEqual(len(apps), 1)
        p = apps[0]
        jobctl.new_record(self.root, url, "Example", "Senior Go Engineer")
        self.assertEqual(len(list((self.root / "applications").iterdir())), 1)
        self.assertEqual(jobctl.read_json(p / "status.json")["status"], "discovered")
        jobctl.state(p, "prepared")
        jobctl.state(p, "awaiting_approval")
        (p / "resume.pdf").write_bytes(b"resume")
        (p / "cover-letter.pdf").write_bytes(b"letter")
        jobctl.approve(self.root, p.name)
        jobctl.submitted(self.root, p.name, "local test confirmation")
        self.assertEqual(jobctl.read_json(p / "status.json")["status"], "submitted")
        with self.assertRaises(ValueError):
            jobctl.submitted(self.root, p.name, "second try")

    def test_approval_is_bound_to_document_hash(self):
        url = "https://example.com/jobs/backend"
        jobctl.new_record(self.root, url, "Example", "Backend")
        p = next((self.root / "applications").iterdir())
        jobctl.state(p, "prepared")
        jobctl.state(p, "awaiting_approval")
        (p / "resume.pdf").write_bytes(b"A")
        (p / "cover-letter.pdf").write_bytes(b"B")
        with self.assertRaises(ValueError):
            jobctl.submitted(self.root, p.name, "looks sent")
        jobctl.approve(self.root, p.name)
        (p / "resume.pdf").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            jobctl.submitted(self.root, p.name, "looks sent")
        self.assertEqual(jobctl.read_json(p / "status.json")["status"], "awaiting_approval")

    def test_invalid_urls_and_transitions(self):
        for url in ("file:///tmp/secret", "http://example.com/jobs", "https://a:b@example.com/"):
            with self.assertRaises(ValueError):
                jobctl.new_record(self.root, url, "Org", "Role")
        jobctl.new_record(self.root, "https://example.com/jobs", "Org", "Role")
        p = next((self.root / "applications").iterdir())
        with self.assertRaises(ValueError):
            jobctl.state(p, "submitted")

if __name__ == "__main__":
    unittest.main()
