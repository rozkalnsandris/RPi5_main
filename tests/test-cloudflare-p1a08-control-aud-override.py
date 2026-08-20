#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERRIDE_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1a08-control-aud-preserving-override.json"
DOC_PATH = ROOT / "docs" / "CLOUDFLARE_P1A08_CONTROL_AUD_TRANSITION.md"


class CloudflareP1A08ControlAudOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.override = json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
        cls.doc = DOC_PATH.read_text(encoding="utf-8")
        cls.units = {item["id"]: item for item in cls.override["replacement_units"]}

    def test_override_is_plan_only_and_non_authorizing(self) -> None:
        self.assertEqual(self.override["status"], "plan-only")
        self.assertFalse(self.override["mutation_authorized"])
        auth = self.override["authorization_state"]
        self.assertEqual(
            auth["old_p1a08_authorization"],
            "retired-before-execution-because-contract-materially-changed",
        )
        self.assertFalse(auth["forward_attempt_started"])
        self.assertFalse(auth["cloudflare_write_executed"])
        self.assertFalse(auth["rollback_executed"])
        self.assertTrue(auth["new_live_authorization_required"])

    def test_only_exact_units_are_overridden(self) -> None:
        self.assertEqual(
            self.override["precedence"]["scope"],
            [
                "p1a-08-control-root-exact-app",
                "p1c-03-retire-parent-wildcard",
                "p1c-04-remove-tech-public-carveout",
            ],
        )
        self.assertEqual(
            self.override["precedence"]["rule"],
            "this-file-supersedes-base-contract-only-for-listed-units-after-merge",
        )

    def test_p1a08_is_deferred_without_forward_write(self) -> None:
        unit = self.units["p1a-08-control-root-exact-app"]
        self.assertEqual(unit["status"], "deferred-no-write")
        self.assertEqual(unit["forward_method"], "NONE")
        self.assertEqual(unit["replacement"], "p1c-03-control-root-retarget")
        self.assertIn("control-worker-jwt-validation-remains-healthy", unit["postconditions"])

    def test_p1c03_retargets_same_application_in_place(self) -> None:
        unit = self.units["p1c-03-control-root-retarget"]
        self.assertEqual(unit["replaces"], "p1c-03-retire-parent-wildcard")
        self.assertEqual(unit["target_before"], "*.rozkalns.net")
        self.assertEqual(unit["target_after"], "control.rozkalns.net")
        self.assertEqual(unit["forward_method"], "PUT")
        self.assertEqual(
            unit["operation"], "update_existing_parent_wildcard_application_in_place"
        )
        self.assertIn("same-application-id-preserved-privately", unit["postconditions"])
        self.assertIn("same-application-aud-preserved-privately", unit["postconditions"])
        self.assertIn("parent-wildcard-domain-absent", unit["postconditions"])
        self.assertIn("control-worker-jwt-validation-remains-healthy", unit["postconditions"])
        self.assertIn(
            "control-webhook-path-remains-more-specific-and-unchanged",
            unit["postconditions"],
        )
        self.assertTrue(unit["rollback"].startswith("put-exact-full-parent-application"))

    def test_retarget_waits_for_existing_p1c_safety_gates(self) -> None:
        preconditions = set(self.units["p1c-03-control-root-retarget"]["preconditions"])
        required = {
            "all-admin-roots-except-control-resolve-exact-no-bypass",
            "all-required-tunnel-protect-canaries-pass",
            "deals-no-bypass-and-protect-pass",
            "dash-exact-and-protect-still-pass",
            "tech-public-exact-bypass-carveout-still-present",
            "rozkalns-net-public-pass",
            "no-unclassified-hostname-or-route",
            "control-worker-expected-aud-matches-current-parent-wildcard-aud-privately",
        }
        self.assertTrue(required.issubset(preconditions))

    def test_delete_recreate_is_forbidden_for_parent_retarget(self) -> None:
        rules = self.override["execution_rules"]
        self.assertIn("do-not-delete-and-recreate-the-parent-application-during-retarget", rules)
        serialized = json.dumps(self.override)
        self.assertNotIn("POST /accounts/{account_id}/access/apps", serialized)
        self.assertNotIn("DELETE /accounts/{account_id}/access/apps/{app_id}", serialized)

    def test_tech_cleanup_stays_after_parent_wildcard_disappears(self) -> None:
        unit = self.units["p1c-04-remove-tech-public-carveout"]
        self.assertEqual(unit["forward_method"], "DELETE")
        self.assertEqual(
            unit["required_precondition"],
            "p1c-03-control-root-retarget-pass-and-parent-wildcard-domain-absent",
        )

    def test_public_source_contains_no_private_identity_or_token_value(self) -> None:
        combined = OVERRIDE_PATH.read_text(encoding="utf-8") + "\n" + self.doc
        self.assertIsNone(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined))
        self.assertNotIn("Authorization: Bearer", combined)
        self.assertNotIn("CLOUDFLARE_API_TOKEN=", combined)
        self.assertNotRegex(combined, r"\b[0-9a-f]{64}\b")


if __name__ == "__main__":
    unittest.main()
