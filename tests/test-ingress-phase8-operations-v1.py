#!/usr/bin/env python3
"""Source-only Phase 8 documentation, privacy and boundary checks (#951)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "INGRESS_PHASE8_OPERATIONS_V1.md"
REGISTRY = ROOT / "ops" / "contracts" / "ingress-registry-v1.json"

REFERENCES = (
    "docs/INGRESS_REGISTRY_V1.md",
    "ops/contracts/ingress-registry-v1.json",
    "docs/INGRESS_PUBLIC_ZONE_VERIFICATION_V1.md",
    "docs/INGRESS_ADMIN_ZONE_VERIFICATION_V1.md",
    "docs/INGRESS_PRIVATE_ZONE_VERIFICATION_V1.md",
    "docs/INGRESS_DRIFT_AUDIT_V1.md",
    "docs/V13_CLOUDFLARE_TUNNEL_OWNERSHIP_CONTRACT.md",
    "docs/CLOUDFLARE_TUNNEL_OPERATOR_V1.md",
    "docs/DISASTER_RECOVERY.md",
)


class IngressPhase8OperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOC.read_text(encoding="utf-8")
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_canonical_public_safe_references_are_real(self) -> None:
        for path in REFERENCES:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertIn(f"`{path}`", self.text)

    def test_all_three_zones_derived_from_registry(self) -> None:
        services = self.registry["services"]
        self.assertEqual({item["zone"] for item in services},
                         {"PUBLIC", "ADMIN", "PRIVATE"})
        self.assertEqual(len({item["service_id"] for item in services}),
                         len(services))
        for zone in ("PUBLIC", "ADMIN", "PRIVATE"):
            self.assertIn(f"| {zone} |", self.text)
        self.assertIn("Do not duplicate a hand-maintained service inventory",
                      self.text)

    def test_recovery_gates_and_no_automatic_live_authority(self) -> None:
        for required in (
            "Connector failure / restoration",
            "Route-change rollback",
            "ADMIN LAN break-glass and PRIVATE recovery",
            "Reboot-survival and final acceptance gate",
            "Separate SIMPLE-DEPLOY scheduler gate",
            "13 registered services",
            "mutation_performed=false",
            "separate",
            "owner LIVE authority",
            "NOT RUN HERE",
            "enabled/inactive/dead",
            "enabled/active/waiting",
            "Production deploy/change required for this source-only guide: **NO**",
            "merge does not authorize LIVE",
        ):
            with self.subTest(marker=required):
                self.assertIn(required, self.text)

    def test_public_document_exposes_no_private_coordinates(self) -> None:
        forbidden = (
            r"\b10\.(?:\d{1,3}\.){3}\b",
            r"\b192\.168\.(?:\d{1,3}\.){2}\b",
            r"\b172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.){2}\b",
            r"\b(?:127\.0\.0\.1|::1):\d+\b",
            r"\b(?:account_id|zone_id|tunnel_id)\s*[:=]\s*[0-9a-f]{16,}",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.text, re.IGNORECASE))
        for command in ("systemctl start ", "systemctl restart ",
                        "docker compose up ", "docker inspect ",
                        "cloudflared tunnel run "):
            self.assertNotIn(command, self.text.lower())


if __name__ == "__main__":
    unittest.main()
