from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".github/github-first-rdc-v1.json"
ROUTING = ROOT / ".github/start-mode-routing.json"
AGENTS = ROOT / "AGENTS.md"
DOCS = ROOT / "docs/GITHUB_FIRST_RDC_ADOPTION_V1.md"
UPSTREAM = "4e89b75d7f496dfb43fd9c1eb10a995fad53fdd8"


def route(c):
    if c["error"]:
        return "STOP"
    if c["github"]:
        return "GITHUB"
    if c["ci"]:
        return "GITHUB_ACTIONS"
    return "RDC_EXCEPTION" if c["host"] and c["authority"] else "STOP"


class GitHubFirstRdcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.routing = json.loads(ROUTING.read_text(encoding="utf-8"))
        cls.agents = AGENTS.read_text(encoding="utf-8")
        cls.docs = DOCS.read_text(encoding="utf-8")

    def test_identity_and_pin(self):
        self.assertEqual(self.policy["schema"], "rozkalns.github-first-rdc-fallback.consumer.v1")
        self.assertEqual(self.policy["repository"], "rozkalnsandris/RPi5_main")
        self.assertEqual(self.policy["shared_contract"]["revision"], UPSTREAM)
        self.assertEqual(len(UPSTREAM), 40)
        self.assertEqual(self.routing["github_first_rdc_fallback"]["shared_revision"], UPSTREAM)

    def test_tool_selection(self):
        p = self.policy["selection"]
        self.assertTrue(p["per_step_classification_required"])
        self.assertTrue(p["github_native_mandatory_when_capable"])
        self.assertTrue(p["github_actions_for_equivalent_source_tests"])
        self.assertFalse(p["convenience_habit_or_speed_is_rdc_reason"])
        self.assertEqual(p["order"], [
            "GITHUB_CONNECTED_TOOLS", "GITHUB_HOSTED_CI_WHEN_APPLICABLE",
            "MINIMAL_AUTHORIZED_RDC_IF_GITHUB_INCAPABLE", "STOP",
        ])

    def test_rdc_exception_and_safe_failures(self):
        for key, value in self.policy["rdc_exception"].items():
            if key != "fields":
                self.assertIs(value, True, key)
        self.assertEqual(len(self.policy["rdc_exception"]["fields"]), 8)
        for key, value in self.policy["fail_closed"].items():
            self.assertIs(value, True, key)

    def test_local_boundaries(self):
        for key, value in self.policy["repository_local_stricter"].items():
            self.assertIs(value, True, key)
        p = self.routing["github_first_rdc_fallback"]
        self.assertTrue(p["mandatory_per_step"])
        self.assertTrue(p["independent_of_command_mode"])
        self.assertTrue(p["rdc_requires_proven_capability_gap"])
        self.assertTrue(p["github_errors_are_not_rdc_fallback"])
        self.assertTrue(p["cannot_expand_owner_authority"])
        self.assertEqual(self.routing["default_continuation_mode"], "FAST-LANE v2.2")
        self.assertIn("RDC is execution/transport only, never source or authorization authority", self.agents)
        self.assertIn("Do not read process/container environments", self.agents)
        self.assertIn("Merge remains explicit owner authority in FAST", self.agents)

    def test_matrix(self):
        cases = self.policy["cases"]
        self.assertEqual(len(cases), 8)
        self.assertEqual(len({c["name"] for c in cases}), len(cases))
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(route(case), case["route"])

    def test_human_contract_references(self):
        for key in (UPSTREAM, ".github/github-first-rdc-v1.json",
                    "docs/GITHUB_FIRST_RDC_ADOPTION_V1.md"):
            self.assertIn(key, self.agents)
        for key in (UPSTREAM, "GitHub -> minimal RDC -> GitHub",
                    "GitHub Actions", "does not"):
            self.assertIn(key, self.docs)


if __name__ == "__main__":
    unittest.main()
