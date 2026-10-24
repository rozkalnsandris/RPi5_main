#!/usr/bin/env python3
"""Offline tests for the pinned Wrangler Stats Worker plan (#1050)."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_version_module_proof_v1.py"
spec = importlib.util.spec_from_file_location("stats_wrangler_1050", SOURCE)
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
        "name": plan.WORKER,
        "main": plan.SOURCE_PATH,
        "compatibility_date": plan.COMPATIBILITY_DATE,
        "workers_dev": False,
        "keep_vars": True,
        "d1_databases": [{
            "binding": "DB",
            "database_name": plan.D1_DATABASE_NAME,
            "database_id": plan.D1_DATABASE_ID,
        }],
        "ratelimits": [{
            "name": "RATE_LIMITER",
            "namespace_id": plan.RATE_LIMIT_NAMESPACE_ID,
            "simple": {"limit": plan.RATE_LIMIT, "period": plan.RATE_PERIOD},
        }],
        "secrets": {
            "required": ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"],
        },
    }


def cfg_bytes(value=None):
    obj = cfg() if value is None else value
    return (json.dumps(obj, indent=2) + "\n").encode("utf-8")


def blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data
    ).hexdigest()


class WranglerPlanTests(unittest.TestCase):
    def test_contract_and_cli_are_source_only(self):
        c = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(c)
        self.assertFalse(c["actions"]["run_wrangler"])
        self.assertFalse(c["actions"]["package_install"])
        self.assertFalse(c["actions"]["credential_access"])
        self.assertFalse(c["actions"]["merge"])
        self.assertFalse(c["actions"]["live"])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--deploy"]), 2)

    def test_pinned_provenance_constants(self):
        self.assertEqual(plan.WRANGLER_VERSION, "4.135.0")
        self.assertEqual(
            plan.SOURCE_COMMIT,
            "180368f3b81abddde3df94637512436ca50c358f",
        )
        self.assertEqual(
            plan.SOURCE_BLOB,
            "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4",
        )
        self.assertEqual(
            plan.CONFIG_BLOB,
            "3733263a391274f2b6b0f2023c8656565bde8e1a",
        )

    def test_upload_is_exact_version_no_bundle_strict_and_never_routes(self):
        raw_cfg = cfg_bytes()
        expected_config_blob = blob(raw_cfg)
        with (
            mock.patch.object(plan, "SOURCE_BLOB", FIXTURE_BLOB),
            mock.patch.object(plan, "CONFIG_BLOB", expected_config_blob),
        ):
            cmd = plan.upload_command(
                plan.SOURCE_COMMIT,
                plan.WRANGLER_VERSION,
                raw_cfg,
                FIXTURE,
            )
        self.assertEqual(
            cmd[:5],
            ["npx", "--yes", "wrangler@4.135.0", "versions", "upload"],
        )
        self.assertIn("--no-bundle", cmd)
        self.assertIn("--keep-vars", cmd)
        self.assertIn("--strict", cmd)
        self.assertNotIn("deploy", cmd)
        self.assertNotIn("--routes", cmd)
        self.assertNotIn("--route", cmd)
        self.assertNotIn("--secrets-file", cmd)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", " ".join(cmd))
        self.assertIn("config-blob:" + expected_config_blob, " ".join(cmd))

    def test_exact_version_deploy_only(self):
        cmd = plan.deploy_command(VERSION, plan.WRANGLER_VERSION)
        self.assertEqual(
            cmd[:5],
            ["npx", "--yes", "wrangler@4.135.0", "versions", "deploy"],
        )
        self.assertIn(VERSION + "@100%", cmd)
        self.assertIn("-y", cmd)
        for bad in ("latest", "abc", VERSION[:8], VERSION.upper(),
                    VERSION + "@100%"):
            with self.assertRaises(plan.Blocked):
                plan.deploy_command(bad, plan.WRANGLER_VERSION)
        with self.assertRaisesRegex(plan.Blocked, "WRANGLER_VERSION_DRIFT"):
            plan.deploy_command(VERSION, "4.134.0")

    def test_source_is_bound_to_git_blob(self):
        with mock.patch.object(plan, "SOURCE_BLOB", FIXTURE_BLOB):
            plan.verify_source(FIXTURE)
            with self.assertRaisesRegex(plan.Blocked, "SOURCE_BLOB_DRIFT"):
                plan.verify_source(FIXTURE + b" ")
        with self.assertRaises(plan.Blocked):
            plan.verify_source(b"")

    def test_config_is_bound_to_git_blob_and_exact_settings(self):
        raw = cfg_bytes()
        with mock.patch.object(plan, "CONFIG_BLOB", blob(raw)):
            self.assertEqual(plan.verify_config(raw), cfg())
            with self.assertRaisesRegex(plan.Blocked, "CONFIG_BLOB_DRIFT"):
                plan.verify_config(raw + b" ")

        changed = cfg()
        changed["ratelimits"][0]["simple"]["limit"] = 99
        changed_raw = cfg_bytes(changed)
        with mock.patch.object(plan, "CONFIG_BLOB", blob(changed_raw)):
            with self.assertRaisesRegex(plan.Blocked, "CONFIG_RATE_LIMIT"):
                plan.verify_config(changed_raw)

    def test_config_rejects_routes_vars_flags_and_binding_drift(self):
        mutations = (
            lambda x: x.update(routes=["ausmalwiese.de/*"]),
            lambda x: x.update(triggers={"crons": ["* * * * *"]}),
            lambda x: x.update(vars={"PUBLIC_ORIGIN": "x"}),
            lambda x: x.update(compatibility_flags=[]),
            lambda x: x.update(compatibility_date="2026-10-07"),
            lambda x: x["d1_databases"][0].update(database_id="other"),
            lambda x: x["ratelimits"][0].update(namespace_id="999"),
            lambda x: x["secrets"].update(required=["VISITOR_HMAC_KEY"]),
        )
        for mutation in mutations:
            changed = copy.deepcopy(cfg())
            mutation(changed)
            with self.assertRaises(plan.Blocked):
                plan.validate_wrangler_config(changed)

    def test_provenance_rejects_commit_or_wrangler_drift(self):
        raw_cfg = cfg_bytes()
        with (
            mock.patch.object(plan, "SOURCE_BLOB", FIXTURE_BLOB),
            mock.patch.object(plan, "CONFIG_BLOB", blob(raw_cfg)),
        ):
            with self.assertRaisesRegex(plan.Blocked, "SOURCE_COMMIT_DRIFT"):
                plan.verify_provenance(
                    "0" * 40, plan.WRANGLER_VERSION, raw_cfg, FIXTURE
                )
            with self.assertRaisesRegex(plan.Blocked, "WRANGLER_VERSION_DRIFT"):
                plan.verify_provenance(
                    plan.SOURCE_COMMIT, "4.134.0", raw_cfg, FIXTURE
                )

    def test_duplicate_config_key_rejected(self):
        raw = (
            '{"name":"coloring-pages-stats-v1",'
            '"name":"coloring-pages-stats-v1"}'
        ).encode()
        with mock.patch.object(plan, "CONFIG_BLOB", blob(raw)):
            with self.assertRaisesRegex(
                plan.Blocked, "CONFIG_DUPLICATE_FIELD"
            ):
                plan.verify_config(raw)

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
