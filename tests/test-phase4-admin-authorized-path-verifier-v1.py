#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/phase4_admin_authorized_path_receipt.py"
CONTRACT_PATH = ROOT / "ops/contracts/admin-zone-protected-authorized-verifier-v1.json"
ADMIN_PATH = ROOT / "ops/contracts/admin-zone-verification-v1.json"

spec = importlib.util.spec_from_file_location("phase4_admin_authorized_path_receipt", MODULE_PATH)
assert spec and spec.loader
receipt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = receipt
spec.loader.exec_module(receipt)


class Phase4AdminAuthorizedPathVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.admin = json.loads(ADMIN_PATH.read_text(encoding="utf-8"))
        cls.projections = cls.admin["service_projections"]

    def submission(self, result: str = "PASS") -> dict:
        return {
            "source_main_sha": "a" * 40,
            "services": [
                {
                    "service_id": item["service_id"],
                    "hostname": item["hostname"],
                    "authorized_admin_result": result,
                }
                for item in self.projections
            ],
        }

    def test_contract_is_non_authorizing_and_browser_session_safe(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.phase4-admin-protected-authorized-verifier.v1",
        )
        authority = self.contract["authority"]
        self.assertFalse(authority["source_merge_proves_runtime_state"])
        self.assertFalse(authority["source_merge_authorizes_execution"])
        self.assertFalse(authority["source_merge_authorizes_protected_session_access"])
        self.assertFalse(authority["source_merge_authorizes_live_mutation"])
        self.assertTrue(authority["execution_requires_fresh_owner_authorization"])

        mechanism = self.contract["protected_access_mechanism"]
        self.assertEqual(mechanism["class"], "standard-cloudflare-access-browser-sso")
        self.assertFalse(mechanism["agent_or_operator_may_handle_credentials"])
        self.assertFalse(mechanism["browser_profile_read_allowed"])
        self.assertFalse(mechanism["cookie_or_session_material_read_allowed"])

    def test_admin_contract_binds_protected_verifier(self) -> None:
        gate = self.admin["runtime_gates"]["protected_authorized_admin"]["protected_verifier"]
        self.assertEqual(
            gate["contract_ref"],
            "ops/contracts/admin-zone-protected-authorized-verifier-v1.json",
        )
        self.assertEqual(
            gate["entrypoint"],
            "scripts/phase4_admin_authorized_path_receipt.py",
        )
        self.assertEqual(
            gate["browser_sso_contract_ref"],
            "ops/contracts/cloudflare-p1d-browser-sso.json",
        )
        self.assertTrue(gate["all_admin_services_pass_required"])
        self.assertFalse(gate["operator_reads_browser_profile_or_session_material"])
        self.assertFalse(gate["source_merge_authorizes_execution"])

    def test_all_pass_builds_sanitized_pass(self) -> None:
        services = receipt.validate_submission(self.submission(), self.projections, "a" * 40)
        report = receipt.build_report("a" * 40, services)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(report["services"]), 8)
        self.assertEqual(
            set(report["services"][0]),
            {"service_id", "hostname", "authorized_admin_result", "result"},
        )
        self.assertFalse(report["mutation_performed"])
        self.assertTrue(all(value is False for value in report["privacy"].values()))

    def test_fail_and_unknown_block_completion(self) -> None:
        failed = self.submission()
        failed["services"][0]["authorized_admin_result"] = "FAIL"
        services = receipt.validate_submission(failed, self.projections, "a" * 40)
        self.assertEqual(receipt.build_report("a" * 40, services)["result"], "FAIL")

        unknown = self.submission()
        unknown["services"][0]["authorized_admin_result"] = "UNKNOWN"
        services = receipt.validate_submission(unknown, self.projections, "a" * 40)
        self.assertEqual(receipt.build_report("a" * 40, services)["result"], "UNKNOWN")

    def test_rejects_extra_identity_or_session_fields(self) -> None:
        payload = self.submission()
        payload["owner_identity"] = "forbidden"
        with self.assertRaises(receipt.ReceiptError):
            receipt.validate_submission(payload, self.projections, "a" * 40)

        payload = self.submission()
        payload["services"][0]["cookie"] = "forbidden"
        with self.assertRaises(receipt.ReceiptError):
            receipt.validate_submission(payload, self.projections, "a" * 40)

    def test_rejects_service_drift_duplicate_and_wrong_hostname(self) -> None:
        payload = self.submission()
        payload["services"][0]["hostname"] = "wrong.example"
        with self.assertRaises(receipt.ReceiptError):
            receipt.validate_submission(payload, self.projections, "a" * 40)

        payload = self.submission()
        payload["services"][1]["service_id"] = payload["services"][0]["service_id"]
        with self.assertRaises(receipt.ReceiptError):
            receipt.validate_submission(payload, self.projections, "a" * 40)

    def test_operator_has_no_browser_or_network_automation(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "requests",
            "selenium",
            "playwright",
            "urllib.request",
            "http.client",
            "socket.",
            "browser_cookie",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
