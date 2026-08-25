#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_CONTRACT_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1d-owner-phone-posture.json"
COMPAT_CONTRACT_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1d-client-session-compat.json"
DOC_PATH = ROOT / "docs" / "CLOUDFLARE_P1D_CLIENT_SESSION_COMPATIBILITY.md"


class CloudflareP1DClientSessionCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.compat = json.loads(COMPAT_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.doc = DOC_PATH.read_text(encoding="utf-8")

    def test_extension_is_plan_only_and_preserves_separate_beta_gate(self) -> None:
        self.assertEqual(self.compat["canonical_issue"], 179)
        self.assertEqual(self.compat["status"], "source-decision-complete-plan-only")
        self.assertEqual(self.compat["source_revalidated"], "2026-08-25")
        self.assertFalse(self.compat["mutation_authorized"])
        self.assertEqual(
            self.compat["extends"],
            "ops/contracts/cloudflare-p1d-owner-phone-posture.json#client_session_beta",
        )
        self.assertEqual(
            self.base["client_session_beta"]["authenticate_with_cloudflare_one_client"],
            "separate-canary",
        )
        self.assertFalse(self.base["mutation_authorized"])

    def test_cloudflare_client_session_compatibility_is_fail_closed(self) -> None:
        compatibility = self.compat["compatibility"]
        self.assertEqual(
            compatibility["supported_access_policy_actions"],
            ["allow", "block"],
        )
        self.assertTrue(compatibility["binding_cookie_must_be_disabled"])
        self.assertFalse(
            compatibility["binding_cookie_change_allowed_in_first_beta_canary"]
        )
        self.assertEqual(
            compatibility["when_binding_cookie_enabled"],
            "stop-and-require-separate-source-security-decision-and-owner-authorization",
        )
        self.assertTrue(compatibility["one_user_per_device"])
        self.assertTrue(compatibility["team_domain_and_idp_reachability_required"])
        self.assertTrue(
            compatibility["fresh_get_only_target_application_preflight_required"]
        )
        self.assertEqual(
            compatibility["fresh_get_fields"],
            ["allow_authenticate_via_warp", "enable_binding_cookie", "policy_actions"],
        )

    def test_first_beta_canary_has_one_semantic_write_and_no_bundled_relaxation(self) -> None:
        canary = self.compat["first_beta_canary"]
        self.assertFalse(canary["authorized"])
        self.assertEqual(canary["target_scope"], "one-exact-admin-access-application")
        self.assertEqual(canary["forward_method"], "PUT")
        self.assertEqual(canary["required_permission"], "Access: Apps and Policies Write")
        self.assertEqual(
            canary["semantic_allowed_diff"],
            ["target-application-allow_authenticate_via_warp-false-to-true"],
        )
        self.assertFalse(canary["bulk_apply_to_all_allowed"])
        self.assertFalse(canary["session_duration_change_allowed"])
        for forbidden in (
            "binding-cookie-change",
            "access-policy-change",
            "gateway-posture-change",
            "session-duration-change",
            "organization-apply-to-all-change",
        ):
            self.assertIn(forbidden, canary["forbidden_diff"])
        self.assertIn("no-blind-retry", canary["failure_contract"])

    def test_document_pins_current_cloudflare_limitations(self) -> None:
        self.assertIn("Allow or Block", self.doc)
        self.assertIn("Binding Cookie is not supported", self.doc)
        self.assertIn("only one user", self.doc.lower())
        self.assertIn("Apply to all Access applications", self.doc)
        self.assertIn("do not silently disable Binding Cookie", self.doc)
        self.assertIn("near-passwordless", self.doc)

    def test_only_official_cloudflare_sources_are_pinned(self) -> None:
        refs = self.compat["source_references"]
        self.assertGreaterEqual(len(refs), 4)
        for ref in refs:
            self.assertTrue(ref.startswith("https://developers.cloudflare.com/"))


if __name__ == "__main__":
    unittest.main()
