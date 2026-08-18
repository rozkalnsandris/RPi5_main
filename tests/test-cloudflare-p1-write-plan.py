#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "ops" / "contracts" / "cloudflare-p1-exact-write-plan.json"
DOC_PATH = ROOT / "docs" / "CLOUDFLARE_P1_EXACT_WRITE_PLAN.md"


class CloudflareP1WritePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.doc = DOC_PATH.read_text(encoding="utf-8")

    def test_plan_is_non_authorizing_and_one_forward_mutation_per_gate(self) -> None:
        self.assertEqual(self.plan["status"], "plan-only")
        self.assertFalse(self.plan["mutation_authorized"])
        auth = self.plan["authorization_contract"]
        self.assertTrue(auth["explicit_owner_authorization_required"])
        self.assertEqual(auth["max_forward_mutations_per_authorization"], 1)
        self.assertTrue(auth["predeclared_inverse_rollback_included"])
        self.assertTrue(auth["fresh_get_before_each_mutation"])
        self.assertTrue(auth["fresh_get_after_each_mutation"])
        self.assertTrue(auth["stop_on_any_unexpected_diff"])

    def test_write_tokens_are_split_and_dns_is_forbidden(self) -> None:
        creds = self.plan["credential_separation"]
        self.assertEqual(
            creds["access_phase_token_permission"], "Access: Apps and Policies Write"
        )
        self.assertEqual(creds["tunnel_phase_token_permission"], "Cloudflare Tunnel Write")
        self.assertFalse(creds["dns_write_allowed"])
        self.assertFalse(creds["global_api_key_allowed"])
        self.assertFalse(creds["secret_values_in_git_allowed"])

    def test_exact_admin_app_order_matches_fresh_evidence(self) -> None:
        phase = self.plan["phases"][0]
        self.assertEqual(phase["id"], "P1A")
        self.assertEqual(
            [item["target"] for item in phase["mutations"]],
            [
                "kuma.rozkalns.net",
                "grafana.rozkalns.net",
                "prometheus.rozkalns.net",
                "adguard.rozkalns.net",
                "hermes.rozkalns.net",
                "portainer.rozkalns.net",
                "ha.rozkalns.net",
                "control.rozkalns.net",
            ],
        )
        for item in phase["mutations"]:
            self.assertEqual(item["forward_method"], "POST")
            self.assertIn("unauthenticated-access-denied", item["postconditions"])
            self.assertIn("public-hosts-regression-pass", item["postconditions"])
            self.assertTrue(item["rollback"])

    def test_exact_app_template_is_owner_only_without_bypass(self) -> None:
        template = self.plan["exact_app_template"]
        self.assertEqual(template["type"], "self_hosted")
        self.assertEqual(template["session_duration"], "24h")
        self.assertEqual(len(template["policies"]), 1)
        policy = template["policies"][0]
        self.assertEqual(policy["decision"], "allow")
        self.assertEqual(policy["precedence"], 1)
        self.assertEqual(policy["include"], ["exact-owner-email-private-input"])
        self.assertEqual(policy["require"], [])
        self.assertEqual(policy["exclude"], [])
        self.assertIn("bypass", template["forbidden_policy_actions"])
        self.assertIn("everyone", template["forbidden_selectors"])
        self.assertIn("ip", template["forbidden_selectors"])
        self.assertIn("service_token", template["forbidden_selectors"])

    def test_protect_with_access_targets_are_exact_and_full_preimage_guarded(self) -> None:
        phase = self.plan["phases"][1]
        self.assertEqual(phase["id"], "P1B")
        self.assertEqual(
            [item["target"] for item in phase["mutations"]],
            [
                "kuma.rozkalns.net",
                "grafana.rozkalns.net",
                "prometheus.rozkalns.net",
                "adguard.rozkalns.net",
                "hermes.rozkalns.net",
                "portainer.rozkalns.net",
                "ha.rozkalns.net",
            ],
        )
        for item in phase["mutations"]:
            self.assertEqual(item["forward_method"], "PUT")
            self.assertIn(
                "fresh-full-tunnel-config-preimage-captured-locally-0600",
                item["preconditions"],
            )
            self.assertIn("preimage-canonical-hash-recorded-locally", item["preconditions"])
            self.assertIn("unrelated-ingress-hash-unchanged", item["postconditions"])
            self.assertEqual(len(item["allowed_diff"]), 3)
            self.assertTrue(item["rollback"].startswith("put-exact-full-tunnel-config-preimage"))

    def test_family_cleanup_precedes_wildcard_and_public_cleanup(self) -> None:
        phase = self.plan["phases"][2]
        self.assertEqual(phase["id"], "P1C")
        self.assertEqual(
            [item["id"] for item in phase["mutations"]],
            [
                "p1c-01-deals-remove-ip-bypass",
                "p1c-02-deals-protect",
                "p1c-03-retire-parent-wildcard",
                "p1c-04-remove-tech-public-carveout",
            ],
        )
        self.assertEqual(phase["mutations"][0]["forward_method"], "DELETE")
        self.assertEqual(phase["mutations"][1]["forward_method"], "PUT")
        self.assertEqual(phase["mutations"][2]["target"], "*.rozkalns.net")
        self.assertEqual(phase["mutations"][3]["target"], "tech.rozkalns.net")
        self.assertIn("parent-wildcard-absent", phase["mutations"][3]["preconditions"])

    def test_dashboard_and_apex_public_are_never_mutation_targets(self) -> None:
        targets = {
            mutation["target"]
            for phase in self.plan["phases"]
            for mutation in phase["mutations"]
        }
        self.assertNotIn("dash.rozkalns.net", targets)
        self.assertNotIn("rozkalns.net", targets)
        self.assertIn("tech.rozkalns.net", targets)
        self.assertIn("*.rozkalns.net", targets)

    def test_owner_phone_mutation_remains_blocked_for_source_decision(self) -> None:
        phone = self.plan["owner_phone_phase"]
        self.assertEqual(phone["id"], "P1D")
        self.assertEqual(phone["status"], "blocked-source-decision")
        self.assertFalse(phone["mutation_authorized"])
        self.assertIn("Require WARP", phone["reason"])
        self.assertIn("Require Gateway", phone["reason"])
        self.assertIn(
            "treat-authenticate-with-cloudflare-one-client-as-beta-and-separate-canary",
            phone["required_next_source_decision"],
        )

    def test_plan_contains_only_documented_bounded_write_surfaces(self) -> None:
        surfaces = self.plan["write_surfaces"]
        self.assertEqual(
            set(surfaces),
            {
                "access_application_create",
                "access_application_delete",
                "access_application_policy_delete",
                "tunnel_configuration_put",
            },
        )
        methods = {value.split(" ", 1)[0] for value in surfaces.values()}
        self.assertEqual(methods, {"POST", "PUT", "DELETE"})
        serialized = json.dumps(self.plan)
        self.assertNotIn("PATCH /", serialized)
        self.assertNotIn("dns_records", serialized)

    def test_public_safe_source_contains_no_private_identity_or_token_value(self) -> None:
        combined = PLAN_PATH.read_text(encoding="utf-8") + "\n" + self.doc
        self.assertIsNone(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined))
        bearer_marker = "Authorization:" + " Bearer"
        token_assignment_marker = "CLOUDFLARE_API_TOKEN" + "="
        self.assertNotIn(bearer_marker, combined)
        self.assertNotIn(token_assignment_marker, combined)
        self.assertNotIn("home public ip:", combined.lower())


if __name__ == "__main__":
    unittest.main()
