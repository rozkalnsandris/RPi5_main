#!/usr/bin/env python3
"""Offline tests for exact privacy D1 migration planner (#1061)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_privacy_d1_migration_v1.py"
spec = importlib.util.spec_from_file_location("stats_privacy_d1_1061", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)


def inventory():
    return {
        "schema": "ausmalwiese.stats-wrangler-conflict-inventory.v1",
        "worker": plan.WORKER,
        "environment": "production",
        "wrangler_version": plan.WRANGLER_VERSION,
        "source_commit": plan.SOURCE_COMMIT,
        "source_blob": "94e802ce145dd75f5701c4c9274a4ac7959c7f5e",
        "config_blob": plan.CONFIG_BLOB,
        "source_class": "script_api",
        "latest_uploaded_version": "e47f145f-1851-4917-be5c-387f96549539",
        "active_versions": [{
            "version_id": "e47f145f-1851-4917-be5c-387f96549539",
            "percentage": 100,
        }],
        "compatibility_date": "2026-10-06",
        "compatibility_flags": [],
        "d1": {
            "binding": "DB",
            "database_name": plan.DATABASE_NAME,
            "database_id": plan.DATABASE_ID,
        },
        "rate_limit": {
            "binding": "RATE_LIMITER",
            "namespace_id": "1152026106",
            "limit": 100,
            "period": 60,
        },
        "secret_names": ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"],
        "plain_text_vars": {
            "CF_ANALYTICS_HOST": {"kind": "plain_text", "fingerprint": "1" * 64},
            "CF_ZONE_TAG": {"kind": "plain_text", "fingerprint": "2" * 64},
            "PUBLIC_ORIGIN": {"kind": "plain_text", "fingerprint": "3" * 64},
        },
        "settings_sha256": "4" * 64,
    }


def schema_before():
    return {
        "schema": plan.SCHEMA,
        "database_name": plan.DATABASE_NAME,
        "database_id": plan.DATABASE_ID,
        "objects": {name: None for name in plan.TARGETS},
    }


def schema_after():
    return {
        "schema": plan.SCHEMA,
        "database_name": plan.DATABASE_NAME,
        "database_id": plan.DATABASE_ID,
        "objects": copy.deepcopy(plan.EXPECTED_POST),
    }


def approval(inv, before):
    return {
        "worker": plan.WORKER,
        "database_id": plan.DATABASE_ID,
        "source_commit": plan.SOURCE_COMMIT,
        "migration_blob": plan.MIGRATION_BLOB,
        "inventory_sha256": plan.canonical_sha256(inv),
        "pre_schema_sha256": plan.canonical_sha256(before),
        "allow_additive_d1_migration_once": True,
    }


class PrivacyD1MigrationTests(unittest.TestCase):
    def test_contract_is_source_only_and_cleanup_is_separate(self):
        data = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        self.assertTrue(data["cleanup_is_later_separate_gate"])
        for key in (
            "run_wrangler", "cloudflare_request", "credential_access",
            "d1_write", "worker_upload", "worker_deploy", "cron_change",
            "cleanup", "merge", "live", "retry", "rollback",
        ):
            self.assertFalse(data["actions"][key])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--apply"]), 2)

    def test_inventory_binds_exact_privacy_source_and_d1(self):
        self.assertEqual(plan.validate_inventory(inventory()), inventory())
        bad = inventory()
        bad["source_commit"] = "0" * 40
        with self.assertRaises(Exception):
            plan.validate_inventory(bad)
        bad = inventory()
        bad["d1"]["database_id"] = "other"
        with self.assertRaises(Exception):
            plan.validate_inventory(bad)

    def test_pre_schema_requires_all_targets_absent(self):
        self.assertEqual(
            plan.validate_schema_snapshot(schema_before(), stage="before"),
            schema_before(),
        )
        bad = schema_before()
        bad["objects"]["like_cookie_sessions"] = copy.deepcopy(
            plan.EXPECTED_POST["like_cookie_sessions"]
        )
        with self.assertRaisesRegex(plan.Blocked, "TARGET_ALREADY_PRESENT"):
            plan.validate_schema_snapshot(bad, stage="before")

    def test_post_schema_is_exact_semantic_shape(self):
        self.assertEqual(
            plan.validate_schema_snapshot(schema_after(), stage="after"),
            schema_after(),
        )
        bad = schema_after()
        bad["objects"]["like_cookie_sessions"]["columns"].append(
            {"name": "unexpected", "type": "TEXT", "pk": False}
        )
        with self.assertRaisesRegex(plan.Blocked, "POST_SCHEMA_MISMATCH"):
            plan.validate_schema_snapshot(bad, stage="after")

    def test_schema_read_plan_is_three_fixed_remote_json_queries(self):
        commands = plan.schema_read_commands()
        self.assertEqual(len(commands), 3)
        for cmd in commands:
            joined = " ".join(cmd)
            self.assertIn("wrangler@4.135.0 d1 execute DB", joined)
            self.assertIn("--remote", cmd)
            self.assertIn("--command", cmd)
            self.assertIn("--json", cmd)
            self.assertIn("--config", cmd)
            self.assertNotIn("--file", cmd)
            self.assertNotIn(plan.CLEANUP_PATH, joined)

    def test_owner_gate_binds_inventory_and_pre_schema(self):
        inv = inventory()
        before = schema_before()
        plan.validate_approval(inv, before, approval(inv, before))
        bad = approval(inv, before)
        bad["pre_schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(plan.Blocked, "OWNER_GATE_UNBOUND"):
            plan.validate_approval(inv, before, bad)

    def test_migration_command_is_one_exact_additive_file_only(self):
        inv = inventory()
        before = schema_before()
        cmd = plan.migration_command(inv, before, approval(inv, before))
        joined = " ".join(cmd)
        self.assertIn("wrangler@4.135.0 d1 execute DB", joined)
        self.assertIn("--remote", cmd)
        self.assertIn("--file", cmd)
        self.assertIn(plan.MIGRATION_PATH, cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("--config", cmd)
        self.assertNotIn("--command", cmd)
        self.assertNotIn(plan.CLEANUP_PATH, joined)

    def test_post_requires_same_inventory_and_exact_new_schema(self):
        self.assertEqual(
            plan.validate_post(inventory(), schema_before(), schema_after()),
            schema_after(),
        )
        bad = schema_after()
        bad["objects"]["idx_like_cookie_sessions_expiry"]["columns"] = [
            "cookie_hash"
        ]
        with self.assertRaises(plan.Blocked):
            plan.validate_post(inventory(), schema_before(), bad)

    def test_source_has_no_executor_transport_or_secret_access(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "subprocess", "requests", "http.client", "urllib.request",
            "os.environ", "Authorization: Bearer", "/etc/rpi5-secrets",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
