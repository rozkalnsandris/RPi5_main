#!/usr/bin/env python3
"""Synthetic-only contract tests: no network, secrets, RPi5 host or Cloudflare calls."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ausmalwiese_report_worker_preflight.py"
spec = importlib.util.spec_from_file_location("report_preflight", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def proposal():
    cfg = module.contract_data()
    return {
        "schema_version": 1, "target": copy.deepcopy(cfg["target"]),
        "routes": copy.deepcopy(cfg["routes"]),
        "binding_kinds": copy.deepcopy(cfg["binding_kinds"]),
        "rate_limits": copy.deepcopy(cfg["rate_limits"]),
        "namespace_ids": {"REPORT_RATE": 1001, "REPORT_DUP": 1002},
        "turnstile": copy.deepcopy(cfg["turnstile"]),
        "brevo": copy.deepcopy(cfg["brevo"]),
    }


class ReportWorkerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.contract = module.contract_data()

    def test_contract_source_only(self):
        module.validate_contract(self.contract)
        self.assertFalse(self.contract["scope"]["live_authorized"])
        self.assertFalse(self.contract["scope"]["merge_authorized"])

    def test_valid_synthetic_plan_is_not_live_evidence(self):
        module.validate_synthetic_candidate(proposal(), self.contract)
        result = subprocess.run([sys.executable, str(SCRIPT), "--check-contract"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "SOURCE_CONTRACT_OK_NOT_LIVE_PROOF")

    def deny(self, change):
        value = proposal()
        change(value)
        with self.assertRaises(module.PlanStop) as err:
            module.validate_synthetic_candidate(value, self.contract)
        self.assertEqual(str(err.exception), module.STOP)

    def test_rejects_stats_worker_widening(self):
        self.deny(lambda v: v["target"].update(worker="coloring-pages-stats-v1"))

    def test_rejects_wrong_account_fingerprint(self):
        self.deny(lambda v: v["target"].update(account_sha256="a"*64))

    def test_rejects_wrong_source_revision_and_hash(self):
        self.deny(lambda v: v["target"].update(source_commit="a"*40))
        self.deny(lambda v: v["target"].update(source_sha256="b"*64))

    def test_rejects_nonexact_routes_and_wildcards(self):
        for bad in ("ausmalwiese.de/api/report*", "ausmalwiese.de/api/stats/*", "ausmalwiese.de/*", "other.example/api/report"):
            self.deny(lambda v, bad=bad: v["routes"].__setitem__(0, bad))
        self.deny(lambda v: v["routes"].append("ausmalwiese.de/catalog.json"))
        self.deny(lambda v: v["routes"].pop())
        self.deny(lambda v: v["routes"].__setitem__(1, v["routes"][0]))

    def test_rejects_secret_values_or_extra_fields(self):
        self.deny(lambda v: v.update(api_token="not-a-real-token"))
        self.deny(lambda v: v["binding_kinds"].update(REPORT_TO="operator@example.test"))
        self.deny(lambda v: v.update(recipient="operator@example.test"))
        self.deny(lambda v: v["binding_kinds"].update(SECRET_EXTRA="secret_text"))

    def test_requires_distinct_namespace_ids(self):
        for first, second in ((1,1), (0,2), (-1,2), (4294967296,2), (True,2), ("1",2)):
            self.deny(lambda v, first=first, second=second: v.update(namespace_ids={"REPORT_RATE": first, "REPORT_DUP": second}))

    def test_rejects_rate_limit_drift(self):
        self.deny(lambda v: v["rate_limits"]["REPORT_RATE"].update(limit=120))
        self.deny(lambda v: v["rate_limits"]["REPORT_DUP"].update(period=10))
        self.deny(lambda v: v["rate_limits"].update(THIRD={"limit": 1, "period": 60}))

    def test_rejects_turnstile_scope_drift(self):
        self.deny(lambda v: v["turnstile"].update(action="login"))
        self.deny(lambda v: v["turnstile"].update(hostnames=["other.example"]))

    def test_rejects_brevo_transport_drift(self):
        self.deny(lambda v: v["brevo"].update(sender="noreply@example.test"))
        self.deny(lambda v: v["brevo"].update(accepted_response="HTTP_200"))

    def test_rejects_contract_authority_widening(self):
        copy_contract = copy.deepcopy(self.contract)
        copy_contract["scope"]["live_authorized"] = True
        with self.assertRaises(module.PlanStop):
            module.validate_contract(copy_contract)

    def test_rejects_cli_apply_without_secret_output(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--apply"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), module.STOP)
        self.assertFalse(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
