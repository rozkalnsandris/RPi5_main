#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_browser_sso_session_update as session_update  # noqa: E402

CONTRACT = ROOT / "ops/contracts/cloudflare-p1d-browser-sso.json"
REGISTRY = ROOT / "ops/contracts/cloudflare-hostname-policy.yaml"
DECISION = ROOT / "docs/CLOUDFLARE_P1D_BROWSER_SSO_DECISION.md"
OLD_DECISION = ROOT / "docs/CLOUDFLARE_P1D_OWNER_PHONE_POSTURE_DECISION.md"
OWNER_CONTRACT = ROOT / "docs/CLOUDFLARE_OWNER_PHONE_ACCESS_CONTRACT.md"
OLD_POSTURE = ROOT / "ops/contracts/cloudflare-p1d-owner-phone-posture.json"
SESSION_WRITER = ROOT / "scripts/cloudflare_owner_browser_sso_session_update.py"
SESSION_WRAPPER = ROOT / "ops/bin/cloudflare-owner-browser-sso-session-update"


class CloudflareP1DBrowserSSOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.registry = REGISTRY.read_text(encoding="utf-8")
        cls.decision = DECISION.read_text(encoding="utf-8")
        cls.old_decision = OLD_DECISION.read_text(encoding="utf-8")
        cls.owner_contract = OWNER_CONTRACT.read_text(encoding="utf-8")
        cls.old = json.loads(OLD_POSTURE.read_text(encoding="utf-8"))

    def test_current_decision_is_non_authorizing_browser_sso(self) -> None:
        self.assertEqual(self.contract["canonical_issue"], 179)
        self.assertFalse(self.contract["mutation_authorized"])
        decision = self.contract["decision"]
        self.assertEqual(decision["identity_requirement"], "exact-owner-identity")
        self.assertEqual(decision["access_model"], "browser-global-sso")
        self.assertFalse(decision["persistent_cloudflare_one_client_required"])
        self.assertFalse(decision["device_posture_required"])
        self.assertFalse(decision["mac_binding_allowed"])
        self.assertEqual(decision["global_session_target"], "720h")
        self.assertEqual(decision["global_session_documented_default"], "24h")
        self.assertFalse(decision["application_or_policy_session_extension_required"])
        self.assertTrue(decision["preserve_existing_application_and_policy_session_durations"])

    def test_policy_keeps_exact_owner_and_forbids_shortcuts(self) -> None:
        policy = self.contract["policy_invariants"]
        self.assertEqual(policy["human_action"], "allow")
        self.assertEqual(policy["include"], ["exact-owner-identity-private-input"])
        self.assertEqual(policy["require"], [])
        self.assertEqual(policy["exclude"], [])
        self.assertIn("bypass", policy["forbidden_actions"])
        for selector in ("everyone", "ip", "email_domain", "service_token"):
            self.assertIn(selector, policy["forbidden_selectors"])

    def test_registry_matches_current_model(self) -> None:
        self.assertRegex(self.registry, r"(?m)^\s*owner_phone_identity_model:\s*access_browser_sso\s*$")
        self.assertRegex(self.registry, r"(?m)^\s*owner_phone_initial_posture:\s*none\s*$")
        self.assertRegex(self.registry, r"(?m)^\s*owner_phone_global_session_target:\s*720h\s*$")
        self.assertRegex(self.registry, r"(?m)^\s*owner_phone_mac_binding:\s*false\s*$")
        self.assertRegex(self.registry, r"(?m)^\s*owner_phone_posture_required:\s*false\s*$")

    def test_old_gateway_plan_is_retained_but_not_selected(self) -> None:
        self.assertFalse(self.old["selected_for_current_owner_phone_access"])
        self.assertEqual(self.old["superseded_by"], "ops/contracts/cloudflare-p1d-browser-sso.json")
        self.assertIn("Superseded for future owner-phone access", self.old_decision)
        self.assertIn("Current decision (2026-09-13): browser SSO", self.owner_contract)

    def test_future_sequence_is_bounded(self) -> None:
        canaries = self.contract["future_canaries"]
        self.assertEqual([item["id"] for item in canaries], [
            "p1d-03-browser-sso-preflight",
            "p1d-04-global-browser-sso-session",
            "p1d-05-a55-browser-sso-canary",
            "p1d-06-owner-phone-client-cleanup",
        ])
        self.assertTrue(all(not item["authorized"] for item in canaries))
        write = canaries[1]
        self.assertEqual(write["allowed_diff"], ["organization-session_duration-to-720h"])
        self.assertEqual(write["operator"], "ops/bin/cloudflare-owner-browser-sso-session-update")
        self.assertIn("access-policy-change", write["forbidden_diff"])
        self.assertIn("device-posture-change", write["forbidden_diff"])
        self.assertTrue(canaries[3]["separate_live_authorization_required"])

    def test_preflight_is_get_only_and_secret_safe_by_contract(self) -> None:
        preflight = self.contract["readonly_preflight"]
        self.assertEqual(preflight["operator"], "ops/bin/cloudflare-owner-browser-sso-preflight")
        self.assertFalse(preflight["mutation_performed"])
        self.assertEqual(len(preflight["get_surfaces"]), 4)
        self.assertTrue(all(surface.startswith("/") for surface in preflight["get_surfaces"]))
        self.assertEqual(preflight["session_duration_field_semantics"]["omitted"], "effective-24h-cloudflare-documented-default")
        self.assertEqual(preflight["session_duration_field_semantics"]["present_but_invalid"], "BLOCKED")
        for forbidden in ("owner-email", "account-id", "access-app-id", "cookie", "jwt", "api-token"):
            self.assertIn(forbidden, preflight["forbidden_output"])

    def test_p1d04_writer_contract_is_narrow_and_non_authorizing(self) -> None:
        writer = self.contract["organization_session_writer"]
        self.assertEqual(writer["api_method"], "PUT")
        self.assertEqual(writer["target_session_duration"], "720h")
        self.assertTrue(writer["response_only_fields_never_in_payload"])
        self.assertFalse(writer["automatic_retry"])
        self.assertFalse(writer["automatic_rollback"])
        self.assertEqual(writer["allowed_semantic_diff"], ["session_duration-to-720h"])
        for key in ("cache_device_posture", "has_migrated_private_apps", "trusted_accounts", "created_at", "updated_at"):
            self.assertIn(key, writer["response_only_fields"])
            self.assertNotIn(key, writer["writable_projection_fields"])
        self.assertFalse(self.contract["authorization_contract"]["source_merge_authorizes_live"])

    def test_p1d04_projection_changes_only_session_duration(self) -> None:
        before = {
            "auth_domain": "private.cloudflareaccess.com",
            "name": "private-team",
            "deny_unmatched_requests": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "cache_device_posture": True,
            "has_migrated_private_apps": False,
            "trusted_accounts": ["private-account"],
        }
        plan = session_update.build_update_plan(before)
        self.assertEqual(plan.current_effective_session, "24h")
        self.assertEqual(plan.payload["session_duration"], "720h")
        self.assertEqual(session_update._semantic_diff(plan.before_writable, plan.payload), {"session_duration"})
        for key in session_update.RESPONSE_ONLY_FIELDS:
            self.assertNotIn(key, plan.payload)

    def test_p1d04_unclassified_response_field_blocks_before_write(self) -> None:
        before = {
            "auth_domain": "private.cloudflareaccess.com",
            "name": "private-team",
            "surprise_server_field": True,
        }
        with self.assertRaisesRegex(session_update.AuditError, "organization_response_field_unclassified"):
            session_update.build_update_plan(before)

    def test_p1d04_response_only_or_writable_drift_fails_post_write(self) -> None:
        before = {
            "auth_domain": "private.cloudflareaccess.com",
            "name": "private-team",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "cache_device_posture": True,
            "has_migrated_private_apps": False,
            "trusted_accounts": ["private-account"],
        }
        plan = session_update.build_update_plan(before)
        after_response_drift = dict(before)
        after_response_drift["session_duration"] = "720h"
        after_response_drift["trusted_accounts"] = ["changed-private-account"]
        with self.assertRaisesRegex(session_update.AuditError, "post_write_response_only_state_changed"):
            session_update.verify_post_write(plan, after_response_drift)

        after_writable_drift = dict(before)
        after_writable_drift["session_duration"] = "720h"
        after_writable_drift["name"] = "unexpected-name"
        with self.assertRaisesRegex(session_update.AuditError, "post_write_writable_projection_changed"):
            session_update.verify_post_write(plan, after_writable_drift)

    def test_p1d04_source_has_one_fixed_put_and_no_other_write_method(self) -> None:
        source = SESSION_WRITER.read_text(encoding="utf-8")
        wrapper = SESSION_WRAPPER.read_text(encoding="utf-8")
        self.assertEqual(source.count('method="PUT"'), 1)
        for forbidden in ('method="POST"', 'method="PATCH"', 'method="DELETE"'):
            self.assertNotIn(forbidden, source)
        self.assertIn(session_update.CANARY_ID, wrapper)
        self.assertIn("exact canary id", wrapper)
        self.assertIn("custom CLOUDFLARE_API_BASE forbidden", wrapper)

    def test_source_references_are_official_cloudflare_docs(self) -> None:
        for ref in self.contract["source_references"]:
            self.assertTrue(ref.startswith("https://developers.cloudflare.com/"))
        self.assertIn("global session token", self.decision.lower())
        self.assertIn("one month", self.decision.lower())
        self.assertIn("response/server-managed", self.decision.lower())

    def test_public_source_contains_no_private_identity_or_secret(self) -> None:
        combined = "\n".join([
            CONTRACT.read_text(encoding="utf-8"),
            DECISION.read_text(encoding="utf-8"),
            OWNER_CONTRACT.read_text(encoding="utf-8"),
            REGISTRY.read_text(encoding="utf-8"),
        ])
        self.assertIsNone(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined))
        self.assertNotIn("Authorization: Bearer", combined)


if __name__ == "__main__":
    unittest.main()
