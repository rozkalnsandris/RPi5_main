#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs" / "CLOUDFLARE_P1D_OWNER_PHONE_POSTURE_DECISION.md"
OWNER_PATH = ROOT / "docs" / "CLOUDFLARE_OWNER_PHONE_ACCESS_CONTRACT.md"
CONTRACT_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1d-owner-phone-posture.json"
REGISTRY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"
PREFLIGHT_PATH = ROOT / "scripts" / "cloudflare_owner_phone_preflight.py"
PREFLIGHT_RUNNER_PATH = ROOT / "scripts" / "cloudflare_owner_phone_preflight_stdin.py"
PREFLIGHT_WRAPPER_PATH = ROOT / "ops" / "bin" / "cloudflare-owner-phone-preflight"


class CloudflareP1DOwnerPhoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.decision = DECISION_PATH.read_text(encoding="utf-8")
        cls.owner = OWNER_PATH.read_text(encoding="utf-8")
        cls.registry = REGISTRY_PATH.read_text(encoding="utf-8")

    def test_source_decision_is_complete_but_non_authorizing(self) -> None:
        self.assertEqual(self.contract["status"], "source-decision-complete-plan-only")
        self.assertEqual(self.contract["canonical_issue"], 179)
        self.assertFalse(self.contract["mutation_authorized"])
        auth = self.contract["authorization_contract"]
        self.assertTrue(auth["explicit_owner_authorization_required_for_each_state_change"])
        self.assertTrue(auth["one_forward_state_change_per_authorization"])
        self.assertTrue(auth["predeclared_rollback_or_revocation_only"])
        self.assertTrue(auth["stop_on_unexpected_diff"])

    def test_gateway_selected_and_reusable_gateway_rule_is_explicit(self) -> None:
        decision = self.contract["decision"]
        self.assertEqual(decision["identity_requirement"], "exact-owner-identity")
        self.assertEqual(decision["selected_posture"], "require_gateway")
        self.assertFalse(decision["require_warp_sufficient_for_enrolled_device_proof"])
        self.assertTrue(decision["android_supported"])
        self.assertTrue(decision["gateway_posture_rule_must_exist_before_access_policy_reference"])
        self.assertIn("Require Gateway", self.decision)
        self.assertIn("consumer WARP", self.decision)
        self.assertIn("reusable Gateway posture", self.owner)

    def test_registry_matches_p1d_decision(self) -> None:
        self.assertRegex(
            self.registry,
            r"(?m)^\s*owner_phone_initial_posture:\s*require_gateway\s*$",
        )
        self.assertNotRegex(
            self.registry,
            r"(?m)^\s*owner_phone_initial_posture:\s*require_warp\s*$",
        )
        self.assertRegex(self.registry, r"(?m)^last_reviewed:\s*2026-08-19\s*$")

    def test_policy_shape_keeps_identity_and_gateway_conjunctive(self) -> None:
        shape = self.contract["policy_shape"]
        self.assertEqual(shape["action"], "allow")
        self.assertEqual(shape["include"], ["exact-owner-identity-private-input"])
        self.assertEqual(shape["require"], ["gateway"])
        self.assertEqual(shape["exclude"], [])
        self.assertFalse(shape["session_change_allowed_in_initial_posture_canary"])
        for selector in ("everyone", "ip", "email_domain", "service_token"):
            self.assertIn(selector, shape["forbidden_selectors"])
        self.assertIn("exact owner identity **and** Gateway posture", self.owner)

    def test_readonly_preflight_contract_is_secret_safe_and_get_only(self) -> None:
        preflight = self.contract["readonly_preflight"]
        self.assertEqual(preflight["operator"], "ops/bin/cloudflare-owner-phone-preflight")
        self.assertFalse(preflight["mutation_performed"])
        self.assertTrue(preflight["exact_main_push_ci_must_be_positively_green_before_live_execution"])
        self.assertIn("exact-owner-email-hidden-stdin", preflight["private_inputs"])
        self.assertIn("/accounts/{account_id}/devices/registrations", preflight["get_surfaces"])
        self.assertIn("/accounts/{account_id}/devices/physical-devices", preflight["get_surfaces"])
        for forbidden in (
            "owner-email",
            "device-id",
            "registration-id",
            "public-key",
            "access-app-id",
            "device-posture-rule-id",
        ):
            self.assertIn(forbidden, preflight["forbidden_output"])
        self.assertTrue(PREFLIGHT_PATH.exists())
        self.assertTrue(PREFLIGHT_RUNNER_PATH.exists())
        self.assertTrue(PREFLIGHT_WRAPPER_PATH.exists())

    def test_enrollment_does_not_depend_on_posture(self) -> None:
        enrollment = self.contract["enrollment"]
        self.assertEqual(enrollment["application_type"], "warp")
        self.assertEqual(enrollment["policy_basis"], "exact-owner-identity")
        self.assertFalse(enrollment["posture_selector_allowed_in_enrollment_policy"])
        self.assertTrue(enrollment["fresh_get_only_preflight_required"])
        self.assertTrue(
            enrollment["write_only_if_current_enrollment_policy_is_not_already_owner_only"]
        )

    def test_canary_order_includes_conditional_gateway_rule_creation(self) -> None:
        canaries = self.contract["future_canaries"]
        ids = [item["id"] for item in canaries]
        self.assertEqual(
            ids,
            [
                "p1d-00-fresh-owner-phone-preflight",
                "p1d-01-owner-only-enrollment-policy",
                "p1d-02-owner-phone-enrollment",
                "p1d-02a-enable-gateway-posture-check",
                "p1d-03-dash-require-gateway",
                "p1d-04-control-require-gateway",
            ],
        )
        posture_write = canaries[3]
        self.assertFalse(posture_write["authorized"])
        self.assertEqual(posture_write["forward_method"], "POST")
        self.assertEqual(
            posture_write["allowed_diff"],
            ["create-exactly-one-device-posture-rule-type-gateway"],
        )
        self.assertEqual(canaries[4]["target"], "dash.rozkalns.net")
        self.assertIn(
            "exactly-one-enabled-android-compatible-gateway-posture-check",
            canaries[4]["preconditions"],
        )
        self.assertEqual(canaries[5]["target"], "control.rozkalns.net")
        self.assertIn(
            "p1c-03-control-root-retarget-accepted",
            canaries[5]["preconditions"],
        )
        self.assertIn("control-parent-app-id-aud-preserved", canaries[5]["preconditions"])
        self.assertIn("control-webhook-app-unchanged", canaries[5]["preconditions"])
        self.assertTrue(all(not item["authorized"] for item in canaries))

    def test_initial_posture_canary_does_not_mix_session_beta(self) -> None:
        beta = self.contract["client_session_beta"]
        self.assertEqual(
            beta["authenticate_with_cloudflare_one_client"],
            "separate-canary",
        )
        self.assertFalse(beta["included_in_initial_posture_canary"])
        self.assertFalse(beta["session_duration_change_allowed"])
        self.assertFalse(beta["bulk_apply_to_all_allowed_in_first_canary"])
        self.assertIn("near-passwordless-owner-phone", beta["goal"])
        self.assertIn("client-session Beta", self.decision)
        self.assertIn("separate Beta canary", self.owner)

    def test_device_uuid_and_hardware_backed_registration_are_not_assumed(self) -> None:
        decision = self.contract["decision"]
        self.assertFalse(decision["device_uuid_initial_control"])
        self.assertFalse(decision["hardware_backed_registration_required"])
        self.assertFalse(decision["hardware_backed_registration_android_available"])

    def test_only_official_cloudflare_sources_are_pinned(self) -> None:
        refs = self.contract["source_references"]
        self.assertGreaterEqual(len(refs), 15)
        for ref in refs:
            self.assertTrue(ref.startswith("https://developers.cloudflare.com/"))

    def test_public_safe_source_contains_no_private_identity_or_token_value(self) -> None:
        combined = "\n".join(
            [
                DECISION_PATH.read_text(encoding="utf-8"),
                OWNER_PATH.read_text(encoding="utf-8"),
                CONTRACT_PATH.read_text(encoding="utf-8"),
                REGISTRY_PATH.read_text(encoding="utf-8"),
            ]
        )
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined)
        )
        bearer_marker = "Authorization:" + " Bearer"
        token_assignment_marker = "CLOUDFLARE_API_TOKEN" + "="
        self.assertNotIn(bearer_marker, combined)
        self.assertNotIn(token_assignment_marker, combined)
        self.assertNotIn("home public ip:", combined.lower())

    def test_preflight_source_does_not_embed_owner_identity_or_write_methods(self) -> None:
        combined = "\n".join(
            [
                PREFLIGHT_PATH.read_text(encoding="utf-8"),
                PREFLIGHT_RUNNER_PATH.read_text(encoding="utf-8"),
                PREFLIGHT_WRAPPER_PATH.read_text(encoding="utf-8"),
            ]
        )
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined)
        )
        self.assertNotIn("CLOUDFLARE_OWNER_EMAIL", combined)
        for method in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"'):
            self.assertNotIn(method, combined)


if __name__ == "__main__":
    unittest.main()
