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


if __name__ == "__main__":
    unittest.main()
