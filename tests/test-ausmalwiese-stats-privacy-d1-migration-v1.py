#!/usr/bin/env python3
"""Offline tests for exact privacy D1 migration planner (#1061 / #996)."""
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


def remote_evidence():
    return {
        "schema": plan.REMOTE_SCHEMA,
        "worker": plan.WORKER,
        "environment": "production",
        "wrangler_version": plan.WRANGLER_VERSION,
        "reviewed_source": {
            "repository": plan.SOURCE_REPO,
            "commit": plan.SOURCE_COMMIT,
            "worker_blob": plan.SOURCE_BLOB,
            "config_blob": plan.CONFIG_BLOB,
            "migration_blob": plan.MIGRATION_BLOB,
        },
        "latest_uploaded_version": "6477f23a-f3da-40c1-bb57-ad672561d243",
        "active_versions": [{
            "version_id": "e014e7c7-4c08-40c6-a9dd-6593b3afcf3c",
            "percentage": 100,
        }],
        "active_provenance": {
            "source": "dash",
            "last_deployed_from": "dash",
            "annotation_class": "secret_change",
        },
        "active_bindings": [
            {"name": "CF_ANALYTICS_API_TOKEN", "type": "secret_text"},
            {"name": "DB", "type": "d1"},
            {"name": "PUBLIC_ORIGIN", "type": "plain_text"},
            {"name": "RATE_LIMITER", "type": "ratelimit"},
        ],
        "d1": {
            "binding": "DB",
            "database_name": plan.DATABASE_NAME,
            "database_id": plan.DATABASE_ID,
        },
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


def approval(remote, before):
    return {
        "worker": plan.WORKER,
        "database_id": plan.DATABASE_ID,
        "source_commit": plan.SOURCE_COMMIT,
        "source_blob": plan.SOURCE_BLOB,
        "config_blob": plan.CONFIG_BLOB,
        "migration_blob": plan.MIGRATION_BLOB,
        "remote_evidence_sha256": plan.canonical_sha256(remote),
        "pre_schema_sha256": plan.canonical_sha256(before),
        "allow_additive_d1_migration_once": True,
    }


class PrivacyD1MigrationTests(unittest.TestCase):
    def test_contract_is_source_only_and_gate_b_stays_separate(self):
        data = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        self.assertTrue(data["cleanup_is_later_separate_gate"])
        self.assertTrue(data["worker_takeover_gate_unchanged"])
        self.assertFalse(data["visitor_hmac_required_for_gate_a"])
        self.assertFalse(data["latest_must_equal_active_for_gate_a"])
        for key in (
            "run_wrangler", "cloudflare_request", "credential_access",
            "d1_write", "worker_upload", "worker_deploy", "cron_change",
            "cleanup", "merge", "live", "retry", "rollback",
        ):
            self.assertFalse(data["actions"][key])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--apply"]), 2)

    def test_remote_evidence_accepts_observed_divergence_and_absent_unused_secret(self):
        evidence = remote_evidence()
        self.assertNotEqual(
            evidence["latest_uploaded_version"],
            evidence["active_versions"][0]["version_id"],
        )
        self.assertNotIn(
            "VISITOR_HMAC_KEY",
            {item["name"] for item in evidence["active_bindings"]},
        )
        self.assertEqual(plan.validate_remote_evidence(evidence), evidence)

    def test_latest_active_equality_is_also_allowed_for_future_convergence(self):
        evidence = remote_evidence()
        evidence["latest_uploaded_version"] = evidence["active_versions"][0]["version_id"]
        self.assertEqual(plan.validate_remote_evidence(evidence), evidence)

    def test_remote_evidence_requires_single_active_100_percent(self):
        evidence = remote_evidence()
        evidence["active_versions"][0]["percentage"] = 99
        with self.assertRaisesRegex(plan.Blocked, "ACTIVE_TRAFFIC"):
            plan.validate_remote_evidence(evidence)
        evidence = remote_evidence()
        evidence["active_versions"].append({
            "version_id": "6477f23a-f3da-40c1-bb57-ad672561d243",
            "percentage": 0,
        })
        with self.assertRaisesRegex(plan.Blocked, "ACTIVE_VERSION_COUNT"):
            plan.validate_remote_evidence(evidence)

    def test_remote_evidence_requires_exact_reviewed_source_and_d1(self):
        evidence = remote_evidence()
        evidence["reviewed_source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(plan.Blocked, "REVIEWED_SOURCE_DRIFT"):
            plan.validate_remote_evidence(evidence)
        evidence = remote_evidence()
        evidence["d1"]["database_id"] = "other"
        with self.assertRaisesRegex(plan.Blocked, "D1_IDENTITY_DRIFT"):
            plan.validate_remote_evidence(evidence)

    def test_gate_a_binding_set_is_bounded_but_visitor_hmac_is_optional(self):
        evidence = remote_evidence()
        evidence["active_bindings"].append(
            {"name": "VISITOR_HMAC_KEY", "type": "secret_text"}
        )
        self.assertEqual(plan.validate_remote_evidence(evidence), evidence)

        bad = remote_evidence()
        bad["active_bindings"].append(
            {"name": "UNEXPECTED", "type": "secret_text"}
        )
        with self.assertRaisesRegex(plan.Blocked, "BINDING_DRIFT"):
            plan.validate_remote_evidence(bad)

        bad = remote_evidence()
        bad["active_bindings"] = [
            item for item in bad["active_bindings"] if item["name"] != "DB"
        ]
        with self.assertRaisesRegex(plan.Blocked, "REQUIRED_GATE_A_BINDING"):
            plan.validate_remote_evidence(bad)

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

    def test_owner_gate_binds_remote_and_pre_schema(self):
        remote = remote_evidence()
        before = schema_before()
        plan.validate_approval(remote, before, approval(remote, before))
        bad = approval(remote, before)
        bad["remote_evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(plan.Blocked, "OWNER_GATE_UNBOUND"):
            plan.validate_approval(remote, before, bad)

    def test_migration_command_is_one_exact_additive_file_only(self):
        remote = remote_evidence()
        before = schema_before()
        cmd = plan.migration_command(remote, before, approval(remote, before))
        joined = " ".join(cmd)
        self.assertIn("wrangler@4.135.0 d1 execute DB", joined)
        self.assertIn("--remote", cmd)
        self.assertIn("--file", cmd)
        self.assertIn(plan.MIGRATION_PATH, cmd)
        self.assertIn("--yes", cmd)
        self.assertIn("--config", cmd)
        self.assertNotIn("--command", cmd)
        self.assertNotIn(plan.CLEANUP_PATH, joined)

    def test_post_requires_same_remote_evidence_and_exact_new_schema(self):
        self.assertEqual(
            plan.validate_post(remote_evidence(), schema_before(), schema_after()),
            schema_after(),
        )
        bad = schema_after()
        bad["objects"]["idx_like_cookie_sessions_expiry"]["columns"] = [
            "cookie_hash"
        ]
        with self.assertRaises(plan.Blocked):
            plan.validate_post(remote_evidence(), schema_before(), bad)

    def test_source_has_no_executor_transport_or_secret_access(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "subprocess", "requests", "http.client", "urllib.request",
            "os.environ", "Authorization: Bearer", "/etc/rpi5-secrets",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
