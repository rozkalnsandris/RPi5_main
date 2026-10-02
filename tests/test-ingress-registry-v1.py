#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"
DOC_PATH = ROOT / "docs" / "INGRESS_REGISTRY_V1.md"
HOSTNAME_POLICY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"

ROADMAP_60_SERVICES = {
    "apex website",
    "Hermes Tech",
    "Portainer",
    "Grafana",
    "Home Assistant",
    "AdGuard Home UI",
    "Uptime Kuma",
    "Prometheus",
    "Hermes Deals",
    "Hermes private application",
}

PRIVATE_COORDINATE_PATTERNS = [
    re.compile(r"\\b10\\.(?:\\d{1,3}\\.){2}\\d{1,3}\\b"),
    re.compile(r"\\b192\\.168\\.(?:\\d{1,3}\\.)\\d{1,3}\\b"),
    re.compile(r"\\b172\\.(?:1[6-9]|2\\d|3[01])\\.(?:\\d{1,3}\\.)\\d{1,3}\\b"),
    re.compile(r"\\b127\\.0\\.0\\.1\\b"),
]


class IngressRegistryV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.doc = DOC_PATH.read_text(encoding="utf-8")
        cls.hostname_policy = HOSTNAME_POLICY_PATH.read_text(encoding="utf-8")
        cls.services = cls.registry["services"]

    def test_schema_is_source_only_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.registry["schema"], "rozkalns.rpi5-main.ingress-registry.v1"
        )
        self.assertEqual(self.registry["schema_version"], 1)
        self.assertEqual(self.registry["status"], "source-policy")
        self.assertEqual(self.registry["canonical_roadmap_issue"], 60)
        self.assertEqual(self.registry["implementation_issue"], 814)
        authority = self.registry["authority"]
        self.assertFalse(authority["source_merge_proves_runtime_state"])
        self.assertFalse(authority["source_merge_authorizes_live"])
        self.assertTrue(authority["runtime_verification_requires_fresh_authorized_evidence"])
        self.assertTrue(authority["remediation_requires_separate_owner_authorization"])

    def test_service_ids_and_hostnames_are_unique(self) -> None:
        ids = [item["service_id"] for item in self.services]
        hostnames = [item["hostname"] for item in self.services]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(hostnames), len(set(hostnames)))
        self.assertNotIn("control.rozkalns.net", hostnames)

    def test_every_roadmap_60_service_is_covered_exactly_once(self) -> None:
        aliases = [
            alias
            for service in self.services
            for alias in service.get("roadmap_aliases", [])
            if alias in ROADMAP_60_SERVICES
        ]
        self.assertEqual(set(aliases), ROADMAP_60_SERVICES)
        self.assertEqual(len(aliases), len(ROADMAP_60_SERVICES))

    def test_required_fields_and_enums_are_present(self) -> None:
        semantics = self.registry["semantics"]
        zones = set(semantics["zone_values"])
        origins = set(semantics["origin_class_values"])
        access_classes = set(semantics["access_class_values"])
        break_glass_values = set(semantics["lan_break_glass_values"])
        self.assertEqual(zones, {"PUBLIC", "ADMIN", "PRIVATE"})
        self.assertEqual(access_classes, {"NONE", "ADMIN", "PRIVATE"})
        self.assertEqual(break_glass_values, {"required", "allowed", "forbidden"})

        required = {
            "service_id",
            "hostname",
            "zone",
            "current_origin_class",
            "desired_origin_class",
            "runtime_owner",
            "repository_owner",
            "access_required",
            "access_class",
            "lan_break_glass",
            "firewall_expectation",
            "health_check_method",
            "health_contract_ref",
            "recovery_ref",
            "last_verified_evidence",
        }
        for service in self.services:
            self.assertTrue(required.issubset(service))
            self.assertIn(service["zone"], zones)
            self.assertIn(service["current_origin_class"], origins)
            self.assertIn(service["desired_origin_class"], origins)
            self.assertIn(service["access_class"], access_classes)
            self.assertIn(service["lan_break_glass"], break_glass_values)
            self.assertTrue(service["runtime_owner"])
            self.assertTrue(service["repository_owner"])
            evidence = service["last_verified_evidence"]
            self.assertFalse(evidence["runtime_current"])
            self.assertTrue(evidence["as_of"])
            self.assertTrue(evidence["ref"])

    def test_zone_access_and_break_glass_invariants(self) -> None:
        for service in self.services:
            zone = service["zone"]
            if zone == "PUBLIC":
                self.assertFalse(service["access_required"])
                self.assertEqual(service["access_class"], "NONE")
                self.assertEqual(service["lan_break_glass"], "forbidden")
            elif zone == "ADMIN":
                self.assertTrue(service["access_required"])
                self.assertEqual(service["access_class"], "ADMIN")
            elif zone == "PRIVATE":
                self.assertTrue(service["access_required"])
                self.assertEqual(service["access_class"], "PRIVATE")

        self.assertNotEqual("ADMIN", "PRIVATE")
        self.assertEqual(
            {service["access_class"] for service in self.services if service["zone"] == "ADMIN"},
            {"ADMIN"},
        )
        self.assertEqual(
            {service["access_class"] for service in self.services if service["zone"] == "PRIVATE"},
            {"PRIVATE"},
        )

    def test_coloring_pages_is_registered_as_public_loopback(self) -> None:
        coloring = next(
            service
            for service in self.services
            if service["hostname"] == "coloring.rozkalns.net"
        )
        self.assertEqual(coloring["service_id"], "coloring-pages")
        self.assertEqual(coloring["zone"], "PUBLIC")
        self.assertEqual(coloring["current_origin_class"], "loopback")
        self.assertEqual(coloring["desired_origin_class"], "loopback")
        self.assertEqual(coloring["runtime_owner"], "rozkalnsandris/RPi5_main")
        self.assertEqual(coloring["repository_owner"], "rozkalnsandris/coloring-pages")
        self.assertFalse(coloring["access_required"])
        self.assertEqual(coloring["access_class"], "NONE")
        self.assertEqual(coloring["lan_break_glass"], "forbidden")
        self.assertIn("hostname: coloring.rozkalns.net", self.hostname_policy)
        self.assertIn("audit_route_presence: absent", self.hostname_policy)

    def test_newer_hostname_policy_explicitly_resolves_hermes_zone(self) -> None:
        hermes = next(
            service for service in self.services if service["hostname"] == "hermes.rozkalns.net"
        )
        self.assertEqual(hermes["zone"], "ADMIN")
        self.assertIn("Hermes private application", hermes["roadmap_aliases"])
        self.assertIn("hermes.rozkalns.net", self.doc)
        self.assertIn("newer desired-state contract", self.doc)

    def test_registry_hostnames_align_with_existing_hostname_policy(self) -> None:
        for service in self.services:
            self.assertIn(f"hostname: {service['hostname']}", self.hostname_policy)
        self.assertIn("hostname: control.rozkalns.net", self.hostname_policy)
        excluded = {item["hostname"] for item in self.registry["scope_exclusions"]}
        self.assertEqual(excluded, {"control.rozkalns.net"})

    def test_registry_contains_no_private_coordinates_or_secret_surfaces(self) -> None:
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        for pattern in PRIVATE_COORDINATE_PATTERNS:
            self.assertIsNone(pattern.search(raw))

        forbidden_key_fragments = (
            "token",
            "credential",
            "secret",
            "account_id",
            "tunnel_id",
            "access_aud",
        )

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    lowered = key.lower()
                    self.assertFalse(
                        any(fragment in lowered for fragment in forbidden_key_fragments),
                        key,
                    )
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(self.registry)

    def test_docs_preserve_source_vs_live_boundary(self) -> None:
        self.assertIn("source policy only", self.doc)
        self.assertIn("not a live inventory", self.doc)
        self.assertIn("does not authorize Cloudflare", self.doc)
        self.assertIn("Phase 2 becomes **COMPLETE only after**", self.doc)


if __name__ == "__main__":
    unittest.main()
