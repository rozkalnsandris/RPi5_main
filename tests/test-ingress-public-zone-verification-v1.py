#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops" / "contracts" / "public-zone-verification-v1.json"
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
HOSTNAME_POLICY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"
DOC_PATH = ROOT / "docs" / "INGRESS_PUBLIC_ZONE_VERIFICATION_V1.md"

PRIVATE_COORDINATE_PATTERNS = [
    re.compile(r"\\b10\\.(?:\\d{1,3}\\.){2}\\d{1,3}\\b"),
    re.compile(r"\\b192\\.168\\.(?:\\d{1,3}\\.)\\d{1,3}\\b"),
    re.compile(r"\\b172\\.(?:1[6-9]|2\\d|3[01])\\.(?:\\d{1,3}\\.)\\d{1,3}\\b"),
    re.compile(r"\\b127\\.0\\.0\\.1\\b"),
]


class PublicZoneVerificationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.host_policy = HOSTNAME_POLICY_PATH.read_text(encoding="utf-8")
        cls.doc = DOC_PATH.read_text(encoding="utf-8")

    def test_contract_is_source_only_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.public-zone-verification.v1",
        )
        self.assertEqual(self.contract["schema_version"], 1)
        self.assertEqual(self.contract["roadmap_issue"], 60)
        self.assertEqual(self.contract["implementation_issue"], 816)
        authority = self.contract["authority"]
        self.assertFalse(authority["source_merge_proves_runtime_state"])
        self.assertFalse(authority["source_merge_authorizes_runtime_verification"])
        self.assertFalse(authority["source_merge_authorizes_live_mutation"])
        self.assertTrue(authority["runtime_verification_requires_fresh_owner_authorization"])
        self.assertTrue(authority["remediation_requires_separate_issue_and_owner_authorization"])

    def test_public_set_is_derived_exactly_from_registry(self) -> None:
        public_services = [
            item for item in self.registry["services"] if item["zone"] == "PUBLIC"
        ]
        expected = self.contract["public_service_selection"]
        self.assertEqual(expected["source"], "registry-zone-filter")
        self.assertEqual(expected["zone"], "PUBLIC")
        self.assertEqual(
            [item["service_id"] for item in public_services],
            expected["expected_service_ids"],
        )
        self.assertEqual(
            [item["hostname"] for item in public_services],
            expected["expected_hostnames"],
        )
        self.assertEqual(
            expected["expected_service_ids"],
            ["apex-web", "hermes-tech"],
        )
        self.assertEqual(
            expected["expected_hostnames"],
            ["rozkalns.net", "tech.rozkalns.net"],
        )

    def test_public_registry_entries_match_phase3_policy(self) -> None:
        expected = self.contract["expected_policy"]
        for service in self.registry["services"]:
            if service["zone"] != "PUBLIC":
                continue
            self.assertFalse(service["access_required"])
            self.assertEqual(service["access_class"], expected["access_class"])
            self.assertEqual(
                service["desired_origin_class"], expected["desired_origin_class"]
            )
            self.assertEqual(
                service["lan_break_glass"], expected["lan_break_glass"]
            )
            self.assertEqual(
                service["firewall_expectation"], expected["firewall_expectation"]
            )
        self.assertFalse(expected["access_required"])
        self.assertEqual(expected["shared_connector_owner"], "rozkalnsandris/RPi5_main")

    def test_hostname_policy_keeps_public_hosts_outside_access(self) -> None:
        for hostname in self.contract["public_service_selection"]["expected_hostnames"]:
            self.assertIn(f"hostname: {hostname}", self.host_policy)
        for marker in (
            "trust_class: PUBLIC",
            "desired_origin_scope: loopback",
            "access_application_scope: none",
            "protect_with_access: false",
        ):
            self.assertIn(marker, self.host_policy)

    def test_anonymous_http_behavior_is_public_and_body_free(self) -> None:
        http = self.contract["external_http_expectation"]
        self.assertEqual(http["scheme"], "https")
        self.assertEqual(http["method"], "GET")
        self.assertEqual(http["path"], "/")
        self.assertEqual(http["accepted_status_classes"], ["2xx", "3xx"])
        self.assertFalse(http["access_challenge_expected"])
        self.assertFalse(http["response_body_collection_allowed"])
        self.assertEqual(http["redirect_policy"], "public-endpoint-only")

    def test_connector_health_is_bounded_to_reviewed_contract(self) -> None:
        connector = self.contract["connector_health_expectation"]
        self.assertEqual(connector["unit_name"], "cloudflared.service")
        self.assertTrue(connector["service_active"])
        self.assertTrue(connector["service_enabled"])
        self.assertEqual(connector["exact_unit_source_ref"], "ops/systemd/cloudflared.service")
        self.assertEqual(connector["active_edge_connections"], 4)
        self.assertFalse(connector["metrics_payload_storage_allowed"])

    def test_evidence_schema_is_exact_and_sanitized(self) -> None:
        evidence = self.contract["evidence_schema"]
        self.assertEqual(
            evidence["required_top_level_fields"],
            [
                "schema",
                "observed_at",
                "source_main_sha",
                "services",
                "shared_connector",
                "result",
            ],
        )
        self.assertEqual(
            evidence["allowed_service_fields"],
            [
                "service_id",
                "hostname",
                "anonymous_http_status_class",
                "anonymous_http_redirect_class",
                "access_challenge_present",
                "route_origin_class",
                "lan_firewall_exception_present",
                "result",
            ],
        )
        self.assertEqual(
            evidence["allowed_connector_fields"],
            [
                "service_active",
                "service_enabled",
                "unit_identity_matches",
                "active_edge_connections",
                "result",
            ],
        )
        self.assertIn("private-origin-coordinates", evidence["forbidden_evidence"])
        self.assertIn("credential-values", evidence["forbidden_evidence"])
        self.assertIn("token-values", evidence["forbidden_evidence"])
        self.assertIn("application-logs", evidence["forbidden_evidence"])

    def test_pass_criteria_match_phase3_assertions(self) -> None:
        per_service = self.contract["pass_criteria"]["per_service"]
        self.assertEqual(per_service["anonymous_http_status_class"], ["2xx", "3xx"])
        self.assertEqual(
            per_service["anonymous_http_redirect_class"],
            ["none", "public-endpoint"],
        )
        self.assertFalse(per_service["access_challenge_present"])
        self.assertEqual(per_service["route_origin_class"], "loopback")
        self.assertFalse(per_service["lan_firewall_exception_present"])
        self.assertEqual(per_service["result"], "PASS")
        connector = self.contract["pass_criteria"]["shared_connector"]
        self.assertTrue(connector["service_active"])
        self.assertTrue(connector["service_enabled"])
        self.assertTrue(connector["unit_identity_matches"])
        self.assertEqual(connector["active_edge_connections"], 4)
        self.assertEqual(connector["result"], "PASS")

    def test_new_source_files_contain_no_private_coordinates_or_secret_values(self) -> None:
        combined = CONTRACT_PATH.read_text(encoding="utf-8") + "\n" + self.doc
        for pattern in PRIVATE_COORDINATE_PATTERNS:
            self.assertIsNone(pattern.search(combined))
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", combined)
        )
        self.assertNotIn("Authorization:" + " Bearer", combined)
        self.assertNotIn("CLOUDFLARE_API_" + "TOKEN=", combined)
        self.assertNotIn("/etc/cloudflared/", combined)

    def test_docs_keep_runtime_completion_behind_fresh_owner_gate(self) -> None:
        self.assertIn("source readiness only", self.doc)
        self.assertIn("does not prove current Cloudflare Access configuration", self.doc)
        self.assertIn("fresh owner authorization", self.doc)
        self.assertIn("Phase 3 stays incomplete after source merge", self.doc)
        self.assertIn("remediation is a separate issue", self.doc)


if __name__ == "__main__":
    unittest.main()
