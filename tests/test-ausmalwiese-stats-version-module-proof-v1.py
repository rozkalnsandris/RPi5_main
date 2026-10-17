#!/usr/bin/env python3
"""Offline tests for the simplified Wrangler Stats Worker plan (#1045)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_version_module_proof_v1.py"
spec = importlib.util.spec_from_file_location("stats_wrangler_1045", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)

FIXTURE = b"export default {fetch(){return new Response('ok')}};\n"
FIXTURE_BLOB = hashlib.sha1(
    b"blob " + str(len(FIXTURE)).encode() + b"\0" + FIXTURE
).hexdigest()
VERSION = "12345678-1234-4234-a234-123456789abc"

def cfg():
    return {
        "$schema": "./node_modules/wrangler/config-schema.json",
        "name": plan.WORKER,
        "main": plan.SOURCE_PATH,
        "compatibility_date": "2026-09-01",
        "compatibility_flags": [],
        "workers_dev": False,
        "keep_vars": True,
        "d1_databases": [{
            "binding": "DB",
            "database_name": "stats",
            "database_id": "11111111-2222-3333-4444-555555555555",
        }],
        "ratelimits": [{
            "name": "RATE_LIMITER",
            "namespace_id": "1001",
            "simple": {"limit": 60, "period": 60},
        }],
        "secrets": {
            "required": ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"],
        },
    }

class WranglerPlanTests(unittest.TestCase):
    def test_contract_and_cli_are_source_only(self):
        c = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(c)
        self.assertFalse(c["actions"]["run_wrangler"])
        self.assertFalse(c["actions"]["credential_access"])
        self.assertFalse(c["actions"]["live"])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--deploy"]), 2)

    def test_upload_is_no_bundle_strict_and_never_routes(self):
        with mock.patch.object(plan, "SOURCE_BLOB", FIXTURE_BLOB):
            cmd = plan.upload_command(cfg(), FIXTURE)
        self.assertEqual(cmd[:4], ["npx", "wrangler", "versions", "upload"])
        self.assertIn("--no-bundle", cmd)
        self.assertIn("--keep-vars", cmd)
        self.assertIn("--strict", cmd)
        self.assertNotIn("deploy", cmd)
        self.assertNotIn("--routes", cmd)
        self.assertNotIn("--route", cmd)
        self.assertNotIn("--secrets-file", cmd)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", " ".join(cmd))

    def test_exact_version_deploy_only(self):
        cmd = plan.deploy_command(VERSION)
        self.assertEqual(
            cmd[:4], ["npx", "wrangler", "versions", "deploy"])
        self.assertIn(VERSION + "@100%", cmd)
        self.assertIn("-y", cmd)
        for bad in ("latest", "abc", VERSION[:8], VERSION.upper(), VERSION + "@100%"):
            with self.assertRaises(plan.Blocked):
                plan.deploy_command(bad)

    def test_source_is_bound_to_git_blob(self):
        with mock.patch.object(plan, "SOURCE_BLOB", FIXTURE_BLOB):
            plan.verify_source(FIXTURE)
            with self.assertRaisesRegex(plan.Blocked, "SOURCE_BLOB_DRIFT"):
                plan.verify_source(FIXTURE + b" ")
        with self.assertRaises(plan.Blocked):
            plan.verify_source(b"")

    def test_config_preserves_remote_vars_and_existing_routes(self):
        self.assertEqual(plan.validate_wrangler_config(cfg()), cfg())
        for mutation in (
            lambda x: x.update(routes=["ausmalwiese.de/*"]),
            lambda x: x.update(route={"pattern": "ausmalwiese.de/*"}),
            lambda x: x.update(triggers={"crons": ["* * * * *"]}),
            lambda x: x.update(vars={"PUBLIC_ORIGIN": "x"}),
            lambda x: x.update(keep_vars=False),
            lambda x: x.update(workers_dev=True),
        ):
            x = cfg()
            mutation(x)
            with self.assertRaises(plan.Blocked):
                plan.validate_wrangler_config(x)

    def test_required_bindings_and_secret_names(self):
        bad = cfg()
        bad["d1_databases"][0]["binding"] = "OTHER"
        with self.assertRaises(plan.Blocked):
            plan.validate_wrangler_config(bad)
        bad = cfg()
        bad["ratelimits"][0]["name"] = "OTHER"
        with self.assertRaises(plan.Blocked):
            plan.validate_wrangler_config(bad)
        bad = cfg()
        bad["ratelimits"][0]["namespace_id"] = "0"
        with self.assertRaises(plan.Blocked):
            plan.validate_wrangler_config(bad)
        bad = cfg()
        bad["secrets"]["required"] = ["VISITOR_HMAC_KEY"]
        with self.assertRaises(plan.Blocked):
            plan.validate_wrangler_config(bad)

    def test_read_only_verify_is_head_q(self):
        cmd = plan.verify_command()
        self.assertEqual(cmd[0], "curl")
        self.assertIn("--head", cmd)
        self.assertEqual(cmd[-1], "https://ausmalwiese.de/q")

    def test_source_contains_no_executor_or_credential_reader(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "subprocess", "os.environ", "requests", "http.client",
            "urllib.request", "Authorization: Bearer",
        ):
            self.assertNotIn(forbidden, text)

if __name__ == "__main__":
    unittest.main()
