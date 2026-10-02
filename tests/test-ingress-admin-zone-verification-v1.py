#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ops" / "contracts" / "admin-zone-verification-v1.json"
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
HOST_POLICY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"
DOC_PATH = ROOT / "docs" / "INGRESS_ADMIN_ZONE_VERIFICATION_V1.md"

PRIVATE_COORDINATE_PATTERNS = [
    re.compile(r"\b10\.(?:\d{1,3}\.){2}\d{1,3}\b"),
    re.compile(r"\b192\.168\.(?:\d{1,3}\.)\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3}\b"),
    re.compile(r"\b127\.0\.0\.1\b"),
]


class AdminZoneVerificationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.host_policy = HOST_POLICY_PATH.read_text(encoding="utf-8")
        cls.doc = DOC_PATH.read_text(encoding="utf-8")
        cls.admin = [item for item in cls.registry["services"] if item["zone"] == "ADMIN"]

    def test_contract_is_source_only_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.contract["schema"], "rozkalns.rpi5-main.admin-zone-verification.v1"
        )
        self.assertEqual(self.contract["schema_version"], 1)
        self.assertEqual(self.contract["roadmap_issue"], 60)
        self.assertEqual(self.contract["implementation_issue"], 819)
        authority = self.contract["authority"]
        for key in (
            "source_merge_proves_runtime_state",
            "source_merge_authorizes_runtime_verification",
            "source_merge_authorizes_protected_admin_verification",
            "source_merge_authorizes_live_mutation",
        ):
            self.assertFalse(authority[key])
        self.assertTrue(authority["infrastructure_verification_requires_fresh_owner_authorization"])
        self.assertTrue(authority["protected_admin_verification_requires_separate_owner_authorization"])
        self.assertTrue(authority["remediation_requires_separate_issue_and_owner_authorization"])

    def test_admin_set_is_derived_exactly_from_registry(self) -> None:
        selection = self.contract["admin_service_selection"]
        self.assertEqual(selection["source"], "registry-zone-filter")
        self.assertEqual(selection["zone"], "ADMIN")
        self.assertEqual(
            [item["service_id"] for item in self.admin],
            selection["expected_service_ids"],
        )
        self.assertEqual(
            [item["hostname"] for item in self.admin],
            selection["expected_hostnames"],
        )
        self.assertEqual(len(self.admin), 8)

    def test_service_projections_match_registry(self) -> None:
        projections = {item["service_id"]: item for item in self.contract["service_projections"]}
        self.assertEqual(set(projections), {item["service_id"] for item in self.admin})
        for service in self.admin:
            projected = projections[service["service_id"]]
            self.assertEqual(projected["hostname"], service["hostname"])
            self.assertEqual(projected["expected_origin_class"], service["desired_origin_class"])
            self.assertEqual(projected["lan_break_glass"], service["lan_break_glass"])
            self.assertEqual(projected["runtime_owner"], service["runtime_owner"])
            self.assertEqual(projected["recovery_ref"], service["recovery_ref"])
            self.assertTrue(projected["recovery_ref"])

    def test_access_semantics_are_admin_only(self) -> None:
        semantics = self.contract["policy_semantics"]
        self.assertTrue(semantics["access_required"])
        self.assertEqual(semantics["access_class"], "ADMIN")
        self.assertEqual(
            semantics["allowed_access_application_scopes"],
            ["exact-owner", "exact-or-narrow-admin"],
        )
        self.assertFalse(semantics["persistent_bypass_allowed"])
        self.assertFalse(semantics["alternate_public_bypass_allowed"])
        self.assertEqual(
            semantics["unauthenticated_external_expected"],
            ["access-challenge", "denied"],
        )
        self.assertFalse(semantics["protected_identity_material_in_evidence_allowed"])

    def test_hostname_policy_matches_each_admin_projection(self) -> None:
        for projected in self.contract["service_projections"]:
            hostname = re.escape(projected["hostname"])
            match = re.search(
                rf"(?ms)^  - hostname: {hostname}\n(?P<body>.*?)(?=^  - hostname:|\Z)",
                self.host_policy,
            )
            self.assertIsNotNone(match, projected["hostname"])
            body = match.group("body")
            self.assertIn("trust_class: ADMIN", body)
            self.assertIn("protect_with_access: true", body)
            self.assertIn(
                f"access_application_scope: {projected['expected_access_application_scope']}",
                body,
            )

    def test_lan_break_glass_semantics_are_explicit(self) -> None:
        semantics = self.contract["lan_break_glass_semantics"]
        self.assertEqual(semantics["required_allowed_runtime_states"], ["present"])
        self.assertEqual(
            semantics["allowed_allowed_runtime_states"], ["present", "absent"]
        )
        self.assertEqual(semantics["forbidden_allowed_runtime_states"], ["absent"])
        self.assertEqual(
            {item["lan_break_glass"] for item in self.contract["service_projections"]},
            {"required", "allowed", "forbidden"},
        )

    def test_evidence_schema_is_bounded(self) -> None:
        evidence = self.contract["evidence_schema"]
        self.assertEqual(
            evidence["allowed_verification_classes"],
            ["unauthenticated-infrastructure", "protected-authorized-admin"],
        )
        self.assertEqual(
            evidence["allowed_authorized_admin_results"],
            ["PASS", "FAIL", "UNKNOWN"],
        )
        self.assertIn("identity-values", evidence["forbidden_evidence"])
        self.assertIn("session-material", evidence["forbidden_evidence"])
        self.assertIn("private-origin-coordinates", evidence["forbidden_evidence"])
        self.assertIn("application-data", evidence["forbidden_evidence"])

    def test_pass_criteria_require_both_runtime_gates(self) -> None:
        per_service = self.contract["pass_criteria"]["per_service"]
        self.assertEqual(
            per_service["unauthenticated_external_class"],
            ["access-challenge", "denied"],
        )
        self.assertEqual(per_service["authorized_admin_result"], "PASS")
        self.assertFalse(per_service["alternate_public_bypass_present"])
        self.assertTrue(per_service["runtime_owner_matches"])
        self.assertTrue(per_service["recovery_ref_present"])
        self.assertTrue(
            self.contract["runtime_gates"]["unauthenticated_infrastructure"]["separately_authorized"]
        )
        self.assertTrue(
            self.contract["runtime_gates"]["protected_authorized_admin"]["separately_authorized"]
        )

    def test_new_source_files_contain_no_private_coordinates_or_identity_values(self) -> None:
        combined = CONTRACT_PATH.read_text(encoding="utf-8") + "\n" + self.doc
        for pattern in PRIVATE_COORDINATE_PATTERNS:
            self.assertIsNone(pattern.search(combined))
        self.assertIsNone(
            re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", combined)
        )
        self.assertNotIn("/etc/cloudflared/", combined)

    def test_docs_preserve_separate_protected_admin_gate(self) -> None:
        self.assertIn("source readiness only", self.doc)
        self.assertIn("separate owner authorization", self.doc)
        self.assertIn("Phase 4 stays incomplete after source merge", self.doc)
        self.assertIn("If a safe protected check cannot be completed", self.doc)
        self.assertIn("separate owner-gated remediation", self.doc)


if __name__ == "__main__":
    unittest.main()
