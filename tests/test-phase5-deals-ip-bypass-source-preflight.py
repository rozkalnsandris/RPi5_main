#!/usr/bin/env python3
"""Offline synthetic fixtures only; never use actual Cloudflare policy data in tests."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/phase5_deals_ip_bypass_source_preflight.py"
spec = importlib.util.spec_from_file_location("deals_ip_bypass_preflight", MODULE)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

SHA = "a" * 40
APP = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
BYPASS = "33333333-3333-4333-8333-333333333333"
ALLOW = "44444444-4444-4444-8444-444444444444"
SERVICE = "55555555-5555-4555-8555-555555555555"
SYNTHETIC_IP = "192.0.2.44/32"
SYNTHETIC_EMAIL = "private-identity-fixture-sentinel"


def fixture():
    return {
        "inventory_complete": True,
        "organization": {"strict_service_token_auth": True},
        "apps": [
            {"id": APP, "type": "self_hosted", "domain": "deals.rozkalns.net"},
            {"id": OTHER, "type": "self_hosted", "domain": "kuma.rozkalns.net"},
        ],
        "policies_by_app": {
            APP: [
                {"id": BYPASS, "decision": "bypass", "precedence": 1,
                 "include": [{"ip": {"ip": SYNTHETIC_IP}}]},
                {"id": ALLOW, "decision": "allow", "precedence": 2,
                 "include": [{"email": {"email": SYNTHETIC_EMAIL}}]},
            ],
            OTHER: [],
        },
        "account_reusable_policies": [],
    }


def assess(state, required=False, current=SHA):
    return preflight.assess(
        state, expected_main=SHA, observed_main=current,
        service_token_required=required,
    )


class Phase5DealsBypassSourcePreflightTests(unittest.TestCase):
    def test_one_legacy_target_has_only_source_candidate_no_live_authority(self):
        report = assess(fixture())
        self.assertEqual(report["result"], "SOURCE_ONLY_CANDIDATE")
        self.assertEqual(report["reason"], "legacy_target_only_preflight_shape")
        self.assertFalse(report["mutation_authorized"])
        self.assertEqual(report["cloudflare_requests_performed"], 0)
        self.assertFalse(report["identity_or_policy_ids_emitted"])
        encoded = json.dumps(report)
        for sensitive in (APP, BYPASS, SYNTHETIC_IP, SYNTHETIC_EMAIL):
            self.assertNotIn(sensitive, encoded)

    def test_missing_explicit_dependency_or_main_drift_blocks(self):
        state = fixture()
        self.assertEqual(preflight.assess(
            state, expected_main=SHA, observed_main=SHA,
            service_token_required=None,
        )["reason"], "service_token_dependency_unknown")
        self.assertEqual(assess(state, current="b"*40)["reason"], "exact_main_unproven")

    def test_incomplete_inventory_and_app_scope_block(self):
        state = fixture()
        state["inventory_complete"] = False
        self.assertEqual(assess(state)["reason"], "inventory_incomplete")
        state = fixture()
        del state["policies_by_app"][OTHER]
        self.assertEqual(assess(state)["reason"], "per_application_inventory_incomplete")
        state = fixture()
        state["apps"].append({"id":"66666666-6666-4666-8666-666666666666",
                              "domain":"deals.rozkalns.net","type":"self_hosted"})
        state["policies_by_app"][state["apps"][-1]["id"]] = []
        self.assertEqual(assess(state)["reason"], "exact_application_not_unique")
        state = fixture()
        state["apps"][0]["destinations"] = [{"uri":"https://another.example.invalid"}]
        self.assertEqual(assess(state)["reason"], "application_scope_unproven")

    def test_reusable_or_shared_policy_never_eligible(self):
        state = fixture()
        state["account_reusable_policies"] = [{"id": BYPASS}]
        self.assertEqual(assess(state)["reason"], "reusable_policy_requires_separate_design")
        state = fixture()
        state["policies_by_app"][OTHER] = [{"id": BYPASS, "decision":"bypass", "precedence":1}]
        self.assertEqual(assess(state)["reason"], "policy_shared_with_other_app")

    def test_documented_optional_reusable_id_is_safe_only_when_app_count_zero(self):
        state = fixture()
        state["account_reusable_policies"] = [
            {"app_count": 0, "decision": "allow", "precedence": 9}
        ]
        self.assertEqual(assess(state)["result"], "SOURCE_ONLY_CANDIDATE")

        state = fixture()
        state["account_reusable_policies"] = [
            {"app_count": 1, "decision": "allow", "precedence": 9}
        ]
        self.assertEqual(
            assess(state)["reason"], "reusable_policy_identity_unproven"
        )

        state = fixture()
        state["account_reusable_policies"] = [
            {"decision": "allow", "precedence": 9}
        ]
        self.assertEqual(
            assess(state)["reason"], "reusable_policy_identity_unproven"
        )

        state = fixture()
        state["account_reusable_policies"] = [
            {"id": "not-a-valid-policy-id", "app_count": 0}
        ]
        self.assertEqual(
            assess(state)["reason"], "reusable_policy_identity_unproven"
        )

    def test_application_policy_without_stable_id_blocks_cross_app_proof(self):
        state = fixture()
        del state["policies_by_app"][OTHER]
        state["policies_by_app"][OTHER] = [
            {"decision": "allow", "precedence": 1, "include": [{"email": {}}]}
        ]
        self.assertEqual(
            assess(state)["reason"], "application_policy_identity_unproven"
        )

        state = fixture()
        del state["policies_by_app"][APP][1]["id"]
        self.assertEqual(
            assess(state)["reason"], "application_policy_identity_unproven"
        )

    def test_multiple_bypass_or_non_ip_scope_blocks(self):
        state = fixture()
        state["policies_by_app"][APP].append({
            "id": "77777777-7777-4777-8777-777777777777",
            "decision":"bypass", "precedence":3,"include":[{"everyone":{}}],
        })
        self.assertEqual(assess(state)["reason"], "bypass_not_unique")
        state = fixture()
        state["policies_by_app"][APP][0]["include"] = [{"everyone":{}}]
        self.assertEqual(assess(state)["reason"], "ip_bypass_scope_unproven")
        state = fixture()
        state["policies_by_app"][APP][0]["exclude"] = [{"email":{"email":SYNTHETIC_EMAIL}}]
        self.assertEqual(assess(state)["reason"], "ip_bypass_scope_unproven")

    def test_missing_allow_or_order_ambiguity_blocks(self):
        state = fixture()
        state["policies_by_app"][APP].pop()
        self.assertEqual(assess(state)["reason"], "family_allow_unproven")
        state = fixture()
        state["policies_by_app"][APP][1]["precedence"] = 1
        self.assertEqual(assess(state)["reason"], "policy_order_ambiguous")

    def test_service_auth_requires_explicit_policy_and_strict_setting(self):
        state = fixture()
        self.assertEqual(assess(state, required=True)["reason"], "service_auth_not_proven")
        state["policies_by_app"][APP].append({
            "id":SERVICE,"decision":"service_auth","precedence":3,
            "include":[{"service_token":{"token_id":"synthetic"}}],
        })
        self.assertEqual(assess(state, required=True)["result"], "SOURCE_ONLY_CANDIDATE")
        del state["organization"]["strict_service_token_auth"]
        self.assertEqual(assess(state, required=True)["reason"], "strict_service_token_state_unknown")


if __name__ == "__main__":
    unittest.main()
