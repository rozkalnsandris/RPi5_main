#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "cloudflare-phase5-private-external.yml"
BRIDGE_PATH = ROOT / "scripts" / "github_phase5_private_external_bridge.py"


class Phase5PrivateExternalSecurityTests(unittest.TestCase):
    def test_privileged_checkout_uses_only_event_sha(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 2)
        self.assertNotIn(
            "ref: ${{ needs.authorize.outputs.expected_sha }}",
            workflow,
        )

    def test_authorizer_binds_expected_sha_to_event_sha_and_forbids_rerun(self) -> None:
        source = BRIDGE_PATH.read_text(encoding="utf-8")
        self.assertIn('if run_attempt!="1"', source)
        self.assertIn("if expected_sha!=github_sha", source)
        self.assertIn('performed_via_github_app', source)


if __name__ == "__main__":
    unittest.main()
