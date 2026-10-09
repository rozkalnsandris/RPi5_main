#!/usr/bin/env python3
"""Source-only regression guards for CV edge IP quota policy (#946)."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/contracts/cv-contact-edge-rate-limit-v1.json"
DOC = ROOT / "docs/CV_CONTACT_EDGE_RATE_LIMIT_V1.md"


class CVContactEdgeRateLimitV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text("utf-8"))
        cls.doc = DOC.read_text("utf-8")

    def test_exact_public_scope_and_source_only_gate(self):
        p = self.policy
        self.assertEqual(p["schema"], "rozkalns.rpi5-main.cv-contact-edge-rate-limit.v1")
        self.assertEqual(p["schema_version"], 1)
        self.assertEqual(p["status"], "source-proposal-not-activated")
        self.assertEqual(p["public_hostname"], "rozkalns.net")
        self.assertEqual(p["implementation_issue"], 946)
        self.assertEqual(p["consumer_issue"], 522)
        self.assertEqual(p["consumer_repository"], "rozkalnsandris/rozkalns-cv")
        self.assertFalse(p["gate"]["production_ready"])
        self.assertFalse(p["gate"]["exact_rule_active"])
        self.assertTrue(p["gate"]["separate_explicit_owner_live_authorization"])
        self.assertEqual(p["boundary"]["mutations_this_source_delivery"], [])

    def test_edge_only_per_client_identity_and_precise_expression(self):
        rule = self.policy["proposed_cloudflare_rule"]
        self.assertEqual(rule["phase"], "http_ratelimit")
        self.assertFalse(rule["enabled"])
        self.assertEqual(rule["expression"], (
            '(http.host eq "rozkalns.net" and '
            'http.request.uri.path eq "/api/contact-reveal")'
        ))
        self.assertEqual(rule["action"], "block")
        self.assertEqual(rule["ratelimit"]["characteristics"], ["cf.colo.id", "ip.src"])
        self.assertEqual(rule["ratelimit"]["period"], 60)
        self.assertEqual(rule["ratelimit"]["requests_per_period"], 6)
        self.assertEqual(rule["ratelimit"]["mitigation_timeout"], 60)
        self.assertNotIn("CF-Connecting-IP", json.dumps(rule))
        self.assertNotIn("http.request.headers", json.dumps(rule))
        self.assertNotIn("172.23.", json.dumps(rule))

    def test_origin_is_global_spoof_resistant_and_does_not_claim_per_client(self):
        authority = self.policy["source_authority"]
        self.assertEqual(authority["edge_ip_characteristic"], "ip.src")
        self.assertFalse(authority["untrusted_client_header_authority"])
        self.assertFalse(authority["docker_bridge_gateway_authenticates_http_headers"])
        guard = self.policy["origin_backstop"]
        self.assertEqual(guard["exact_location"], "/api/contact-reveal")
        self.assertEqual(guard["quota_identity"], "$server_name")
        self.assertEqual(guard["global_rate"], "60r/m")
        self.assertEqual(guard["global_burst"], 15)
        self.assertFalse(guard["forwards_untrusted_cloudflare_client_ip"])
        self.assertTrue(guard["allows_loopback_gunicorn_only"])

    def test_deploy_and_edge_policies_stay_separately_gated(self):
        p = self.policy
        for requirement in (
            "zone_capability_proven",
            "exact_rule_active",
            "origin_route_and_loopback_proven",
            "ip_spoof_resistance_proven",
            "conflict_free_ruleset_proven",
            "production_ready",
            "exact_consumer_sha_resolved",
        ):
            self.assertIs(p["gate"][requirement], False)
        for term in (
            "no LIVE",
            "source-only",
            "Cloudflare",
            "ip.src",
            "host",
            "/api/contact-reveal",
            "loopback",
            "per-colo",
            "plan",
            "spoof",
        ):
            self.assertIn(term.lower(), self.doc.lower())
        for sensitive in ("CLOUDFLARE_API_TOKEN", "cf_account_id", "private_key"):
            self.assertNotIn(sensitive, json.dumps(p))

    def test_free_plan_selected_baseline_and_waf_preservation(self):
        p = self.policy
        decision = p["free_plan_decision"]
        self.assertEqual(decision["decision_issue"], 948)
        self.assertEqual(decision["state"], "source-only-selected-not-deployed")
        baseline = decision["selected_baseline"]
        self.assertEqual(baseline["protection"], [
            "turnstile-siteverify-fail-closed",
            "nginx-exact-path-global-rate-backstop",
        ])
        self.assertEqual(baseline["endpoint"], "/api/contact-reveal")
        self.assertEqual(baseline["nginx_global_rate"], "60r/m")
        self.assertEqual(baseline["nginx_global_burst"], 15)
        self.assertFalse(baseline["numerical_per_visitor_ip_quota"])
        self.assertFalse(baseline["production_deployment_verified"])
        preserved = decision["existing_waf_rate_limit"]
        self.assertEqual(preserved["disposition"], "preserve-unchanged")
        self.assertTrue(preserved["no_change_authorized"])
        self.assertFalse(preserved["additional_rule_slot_assumed_available"])
        self.assertFalse(preserved["account_rule_state_publicly_asserted"])
        legacy = decision["legacy_rule"]
        self.assertFalse(legacy["free_eligible"])
        self.assertFalse(legacy["activate"])
        self.assertTrue(legacy["no_path_only_downgrade"])
        self.assertFalse(p["proposed_cloudflare_rule"]["enabled"])
        self.assertFalse(p["proposed_cloudflare_rule"]["free_plan_eligible"])
        self.assertIn("free-plan-period-10-seconds-not-60", legacy["incompatible_reasons"])

    def test_optional_enhancements_remain_disabled_and_gated(self):
        p = self.policy
        alt = p["free_plan_decision"]["alternatives"]
        waf = alt["custom_waf_managed_challenge"]
        self.assertEqual(waf["state"], "deferred-not-active")
        self.assertFalse(waf["enabled"])
        self.assertFalse(waf["numeric_per_ip_quota"])
        self.assertFalse(waf["api_fetch_json_and_turnstile_compatibility_proven"])
        self.assertFalse(waf["modifies_existing_waf_rule"])
        worker = alt["worker_rate_limiting"]
        self.assertEqual(worker["state"], "candidate-not-active")
        self.assertFalse(worker["enabled"])
        self.assertFalse(worker["installed"])
        self.assertEqual(worker["endpoint_host"], "rozkalns.net")
        self.assertEqual(worker["endpoint_path"], "/api/contact-reveal")
        self.assertEqual(worker["period_seconds"], 60)
        self.assertEqual(worker["requests_per_period"], 6)
        self.assertEqual(worker["key_authority"], "verified-cloudflare-inbound-edge-client-ip-only")
        self.assertEqual(worker["on_missing_verified_ip"], "reject-not-bypass")
        self.assertEqual(worker["on_workers_daily_limit"], "fail-closed-1027-not-fail-open")
        self.assertEqual(worker["daily_free_account_request_budget"], 100000)
        self.assertFalse(worker["counters_global_and_exact"])
        self.assertTrue(worker["counters_per_cloudflare_location"])
        self.assertFalse(worker["logs_private_ip_contact_or_tokens"])
        for key in ("runtime_and_binding_proven_for_account", "route_and_same_zone_origin_fetch_proven",
                    "request_response_turnstile_integrity_proven", "synthetic_429_verified"):
            self.assertIs(worker[key], False)
        gate = p["free_plan_decision"]["gates"]
        self.assertTrue(gate["source_ready_only"])
        self.assertTrue(gate["explicit_separate_owner_live_authorization_required"])
        for key, value in gate.items():
            if key.endswith("_verified") or key == "production_eligible":
                self.assertIs(value, False)
        self.assertFalse(p["gate"]["production_ready"])

    def test_free_decision_documentation_and_privacy(self):
        for term in ("Free", "Turnstile", "Siteverify", "60r/m", "burst=15",
                     "one", "10-second", "Managed Challenge", "Worker",
                     "100,000", "1027", "429", "same-zone", "fail-closed",
                     "source-only", "not production-verified", "no LIVE"):
            self.assertIn(term.lower(), self.doc.lower())
        p = self.policy
        for sensitive in ("cf_account_id", "zone_id", "account_id",
                          "CLOUDFLARE_API_TOKEN", "private_key", "authorization_bearer"):
            self.assertNotIn(sensitive, json.dumps(p))


if __name__ == "__main__":
    unittest.main()
