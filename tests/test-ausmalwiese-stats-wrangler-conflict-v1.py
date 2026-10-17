#!/usr/bin/env python3
"""Offline tests for Stats Wrangler strict-conflict takeover plan (#1052)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_wrangler_conflict_v1.py"
STEADY = ROOT / "scripts/ausmalwiese_stats_version_module_proof_v1.py"
spec = importlib.util.spec_from_file_location("stats_wrangler_conflict_1052", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)

NEW_VERSION = "12345678-1234-4234-a234-123456789abc"


def before():
    return {
        "schema": "ausmalwiese.stats-wrangler-conflict-inventory.v1",
        "worker": plan.WORKER,
        "environment": "production",
        "wrangler_version": plan.WRANGLER_VERSION,
        "source_commit": plan.SOURCE_COMMIT,
        "source_blob": plan.SOURCE_BLOB,
        "config_blob": plan.CONFIG_BLOB,
        "source_class": "script_api",
        "latest_uploaded_version": plan.BASELINE_VERSION,
        "active_versions": [{
            "version_id": plan.BASELINE_VERSION,
            "percentage": 100,
        }],
        "compatibility_date": plan.COMPATIBILITY_DATE,
        "compatibility_flags": [],
        "d1": copy.deepcopy(plan.D1),
        "rate_limit": copy.deepcopy(plan.RATE_LIMIT),
        "secret_names": list(plan.SECRET_NAMES),
        "plain_text_vars": {
            "CF_ANALYTICS_HOST": {
                "kind": "plain_text",
                "fingerprint": "1" * 64,
            },
            "CF_ZONE_TAG": {
                "kind": "plain_text",
                "fingerprint": "2" * 64,
            },
            "PUBLIC_ORIGIN": {
                "kind": "plain_text",
                "fingerprint": "3" * 64,
            },
        },
        "settings_sha256": "4" * 64,
    }


def after_upload():
    state = before()
    state["source_class"] = "wrangler_versions_upload"
    state["latest_uploaded_version"] = NEW_VERSION
    return state


def approval(state):
    return {
        "worker": plan.WORKER,
        "baseline_version": plan.BASELINE_VERSION,
        "inventory_sha256": plan.canonical_sha256(state),
        "allow_non_strict_upload_once": True,
        "allow_deploy_exact_returned_id": True,
    }


class StrictConflictPlanTests(unittest.TestCase):
    def test_contract_is_source_only(self):
        data = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        self.assertEqual(plan.SOURCE_COMMIT, "699c036b7f952aa98be06e166a9705069b7e9eb2")
        self.assertEqual(plan.SOURCE_BLOB, "94e802ce145dd75f5701c4c9274a4ac7959c7f5e")
        self.assertFalse(data["actions"]["run_wrangler"])
        self.assertFalse(data["actions"]["cloudflare_request"])
        self.assertFalse(data["actions"]["credential_access"])
        self.assertFalse(data["actions"]["merge"])
        self.assertFalse(data["actions"]["live"])
        self.assertFalse(data["actions"]["retry"])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--run"]), 2)

    def test_takeover_command_is_non_strict_but_bounded(self):
        state = before()
        cmd = plan.takeover_upload_command(state, approval(state))
        self.assertEqual(
            cmd[:5],
            ["npx", "--yes", "wrangler@4.135.0", "versions", "upload"],
        )
        self.assertNotIn("--strict", cmd)
        self.assertIn("--no-bundle", cmd)
        self.assertIn("--keep-vars", cmd)
        self.assertNotIn("--secrets-file", cmd)
        self.assertIn("takeover-from:" + plan.BASELINE_VERSION, " ".join(cmd))

    def test_steady_state_planner_remains_strict(self):
        text = STEADY.read_text("utf-8")
        self.assertIn('"--strict"', text)
        self.assertIn("STATS_WRANGLER_PINNED_PROVENANCE", text)

    def test_before_requires_latest_single_active_baseline_at_100(self):
        cases = []
        state = before()
        state["latest_uploaded_version"] = NEW_VERSION
        cases.append(state)
        state = before()
        state["active_versions"][0]["percentage"] = 90
        cases.append(state)
        state = before()
        state["active_versions"].append({
            "version_id": NEW_VERSION,
            "percentage": 0,
        })
        cases.append(state)
        state = before()
        state["source_class"] = "unknown"
        cases.append(state)
        for bad in cases:
            with self.assertRaises(plan.Blocked):
                plan.validate_snapshot(bad, stage="before")

    def test_before_pins_settings_and_binding_identities(self):
        mutations = (
            lambda x: x.update(compatibility_date="2026-10-07"),
            lambda x: x.update(compatibility_flags=["nodejs_compat"]),
            lambda x: x["d1"].update(database_id="other"),
            lambda x: x["rate_limit"].update(namespace_id="999"),
            lambda x: x.update(secret_names=["VISITOR_HMAC_KEY"]),
            lambda x: x["plain_text_vars"].pop("CF_ZONE_TAG"),
            lambda x: x["plain_text_vars"]["CF_ZONE_TAG"].update(
                fingerprint="bad"
            ),
            lambda x: x.update(settings_sha256="bad"),
        )
        for mutation in mutations:
            bad = before()
            mutation(bad)
            with self.assertRaises(plan.Blocked):
                plan.validate_snapshot(bad, stage="before")

    def test_owner_gate_binds_inventory_digest(self):
        state = before()
        good = approval(state)
        plan.validate_approval(state, good)
        bad = copy.deepcopy(good)
        bad["inventory_sha256"] = "0" * 64
        with self.assertRaisesRegex(plan.Blocked, "OWNER_GATE_UNBOUND"):
            plan.validate_approval(state, bad)

    def test_post_upload_requires_old_active_and_preservation(self):
        old = before()
        new = after_upload()
        self.assertEqual(plan.validate_post_upload(old, new, NEW_VERSION), new)

        bad = after_upload()
        bad["active_versions"][0]["version_id"] = NEW_VERSION
        with self.assertRaises(plan.Blocked):
            plan.validate_post_upload(old, bad, NEW_VERSION)

        bad = after_upload()
        bad["plain_text_vars"]["PUBLIC_ORIGIN"]["fingerprint"] = "5" * 64
        with self.assertRaisesRegex(plan.Blocked, "POST_UPLOAD_VAR_DRIFT"):
            plan.validate_post_upload(old, bad, NEW_VERSION)

        bad = after_upload()
        bad["settings_sha256"] = "6" * 64
        with self.assertRaisesRegex(plan.Blocked, "SETTINGS_DRIFT"):
            plan.validate_post_upload(old, bad, NEW_VERSION)

    def test_deploy_requires_post_upload_proof_and_exact_uuid(self):
        old = before()
        new = after_upload()
        cmd = plan.deploy_command(old, new, NEW_VERSION, approval(old))
        self.assertEqual(
            cmd[:5],
            ["npx", "--yes", "wrangler@4.135.0", "versions", "deploy"],
        )
        self.assertIn(NEW_VERSION + "@100%", cmd)
        self.assertIn("-y", cmd)
        with self.assertRaises(plan.Blocked):
            plan.deploy_command(old, new, "latest", approval(old))

    def test_verify_is_head_q(self):
        cmd = plan.verify_command()
        self.assertIn("--head", cmd)
        self.assertEqual(cmd[-1], "https://ausmalwiese.de/q")

    def test_source_contains_no_executor_or_credential_reader(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "subprocess",
            "os.environ",
            "requests",
            "http.client",
            "urllib.request",
            "Authorization: Bearer",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
