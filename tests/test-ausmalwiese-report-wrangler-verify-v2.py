#!/usr/bin/env python3
"""Offline tests for the minimal report provenance verifier (#1095)."""
from __future__ import annotations
import copy, importlib.util, json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_report_wrangler_verify_v2.py"
spec=importlib.util.spec_from_file_location("report_wrangler_verify_1095",SOURCE); plan=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(plan)
VERSION="12345678-1234-4234-a234-123456789abc"
def annotations(): return {"workers/message":plan.expected_message(),"workers/tag":plan.expected_tag(),"workers/triggered_by":"upload"}
class ReportWranglerVerifyV2Tests(unittest.TestCase):
    def test_contract_pins_minimal_deploy_source_and_has_no_old_dependencies(self):
        data=json.loads(plan.CONTRACT.read_text("utf-8")); plan.check_contract(data)
        self.assertEqual(data["deploy_blob"],"6a5b15e121bbca41b6b33582bcc62964df723927"); self.assertEqual(data["send_failure_diagnostic"],plan.SEND_FAILURE_DIAGNOSTIC)
        self.assertFalse(data["verification"]["secret_inventory_required"]); self.assertFalse(data["verification"]["public_config_endpoint_required"]); self.assertFalse(data["verification"]["stats_snapshot_required"]); self.assertEqual(plan.main(["--check-contract"]),0)
    def test_exact_application_and_diagnostic_provenance(self):
        self.assertEqual(plan.SOURCE_COMMIT,"15059f7178afcb6c14ad88a22d46f5a04c9e07cf")
        self.assertEqual(plan.WORKER_BLOB,"50bbcd868aa9f91b7fb6d78a2925e867380ef421")
        self.assertEqual(plan.DEPLOY_BLOB,"6a5b15e121bbca41b6b33582bcc62964df723927")
        self.assertEqual(plan.SEND_FAILURE_DIAGNOSTIC["event"],"report_email_send_failed")
        self.assertTrue(plan.SEND_FAILURE_DIAGNOSTIC["source_provenance_only"])

    def test_exact_annotations_map_to_snapshot_provenance(self):
        self.assertEqual(plan.provenance_adapter(annotations()),{"version_tag":plan.expected_tag(),"version_message":plan.expected_message()})
    def test_annotations_fail_closed_on_drift(self):
        for mutation in (lambda x:x.pop("workers/tag"),lambda x:x.update(extra="no"),lambda x:x.update({"workers/tag":"wrong"}),lambda x:x.update({"workers/message":"wrong"}),lambda x:x.update({"workers/triggered_by":""})):
            bad=copy.deepcopy(annotations()); mutation(bad)
            with self.assertRaises(plan.Blocked): plan.validate_annotations(bad)
    def test_read_only_plan_has_three_wrangler_reads_and_no_secret_or_public_get(self):
        value=plan.read_only_verification_plan(VERSION); self.assertEqual(len(value["wrangler_commands"]),3); self.assertEqual(len(value["provider_reads"]),1); self.assertNotIn("public_gets",value)
        joined=[" ".join(cmd) for cmd in value["wrangler_commands"]]
        self.assertTrue(any("versions list" in x for x in joined)); self.assertTrue(any("deployments list" in x for x in joined)); self.assertTrue(any("versions view "+VERSION in x for x in joined))
        for command in joined: self.assertNotIn(" secret "," "+command+" "); self.assertNotIn("/api/report/config",command)
    def test_source_contains_no_network_or_credential_client(self):
        text=SOURCE.read_text("utf-8")
        for forbidden in ("http.client","requests","urllib.request","Authorization","CLOUDFLARE_API_TOKEN","/api/report/config"): self.assertNotIn(forbidden,text)
if __name__=="__main__": unittest.main()
