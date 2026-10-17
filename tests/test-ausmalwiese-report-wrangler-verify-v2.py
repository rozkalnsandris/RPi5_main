#!/usr/bin/env python3
"""Offline tests for report Script/Version Settings provenance verifier (#1079)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_report_wrangler_verify_v2.py"
spec = importlib.util.spec_from_file_location("report_wrangler_verify_1079", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)

VERSION = "12345678-1234-4234-a234-123456789abc"


def annotations():
    return {
        "workers/message": plan.expected_message(),
        "workers/tag": plan.expected_tag(),
        "workers/triggered_by": "upload",
    }


class ReportWranglerVerifyV2Tests(unittest.TestCase):
    def test_contract_is_source_only_and_pins_legacy_runtime_blob(self):
        data = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        self.assertEqual(
            data["legacy_deploy_blob"],
            "c92da027aea2d2b41f1e901bd14ae91a2a4bc834",
        )
        self.assertFalse(data["actions"]["run_wrangler"])
        self.assertFalse(data["actions"]["cloudflare_request"])
        self.assertFalse(data["actions"]["credential_or_secret_access"])
        self.assertFalse(data["actions"]["live"])
        self.assertEqual(plan.main(["--check-contract"]), 0)

    def test_exact_annotations_map_into_legacy_snapshot_fields(self):
        self.assertEqual(
            plan.provenance_adapter(annotations()),
            {
                "version_tag": plan.expected_tag(),
                "version_message": plan.expected_message(),
                "version_triggered_by": "upload",
            },
        )

    def test_annotations_fail_closed_on_missing_extra_or_drift(self):
        mutations = (
            lambda x: x.pop("workers/tag"),
            lambda x: x.update(extra="no"),
            lambda x: x.update({"workers/tag": "wrong"}),
            lambda x: x.update({"workers/message": "wrong"}),
            lambda x: x.update({"workers/triggered_by": ""}),
            lambda x: x.update({"workers/triggered_by": "x\nsecret"}),
        )
        for mutation in mutations:
            bad = copy.deepcopy(annotations())
            mutation(bad)
            with self.assertRaises(plan.Blocked):
                plan.validate_annotations(bad)

    def test_read_only_plan_uses_settings_annotations_for_provenance(self):
        value = plan.read_only_verification_plan(VERSION)
        self.assertEqual(len(value["provider_reads"]), 1)
        read = value["provider_reads"][0]
        self.assertEqual(read["method"], "GET")
        self.assertEqual(
            read["path_template"],
            "/accounts/{account_id}/workers/scripts/"
            "coloring-pages-report-v1/settings",
        )
        self.assertEqual(
            read["evidence"], "script-and-version-settings.annotations"
        )
        joined = [" ".join(cmd) for cmd in value["wrangler_commands"]]
        self.assertTrue(any("versions list" in x for x in joined))
        self.assertTrue(any("deployments list" in x for x in joined))
        self.assertTrue(any("versions view " + VERSION in x for x in joined))
        self.assertTrue(any("secret list" in x for x in joined))
        for command in joined:
            self.assertNotIn(" deploy ", " " + command + " ")
            self.assertNotIn(" secret put ", " " + command + " ")
            self.assertNotIn(" secret delete ", " " + command + " ")

    def test_source_contains_no_network_or_credential_client(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "http.client",
            "requests",
            "urllib.request",
            "Authorization",
            "auth token",
            "CLOUDFLARE_API_TOKEN",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
