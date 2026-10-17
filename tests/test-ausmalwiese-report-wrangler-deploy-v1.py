#!/usr/bin/env python3
"""Offline tests for the Ausmalwiese report Wrangler deploy contract (#1048)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_report_wrangler_deploy_v1.py"
spec = importlib.util.spec_from_file_location("report_wrangler_deploy_1048", SOURCE)
plan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(plan)

VERSION = "12345678-1234-4234-a234-123456789abc"
STATS_VERSION = "87654321-4321-4321-a321-cba987654321"


def application():
    return {
        "schema": "ausmalwiese.report-wrangler-source.v1",
        "repository": plan.SOURCE_REPO,
        "commit": plan.SOURCE_COMMIT,
        "worker_path": plan.WORKER_PATH,
        "worker_blob": plan.WORKER_BLOB,
        "config_path": plan.CONFIG_PATH,
        "config_blob": plan.CONFIG_BLOB,
        "config": copy.deepcopy(plan.expected_config()),
    }


def approval(path="/run/credentials/ausmalwiese-report-worker.env"):
    return {
        "worker": plan.WORKER,
        "wrangler_version": plan.WRANGLER_VERSION,
        "source_commit": plan.SOURCE_COMMIT,
        "worker_blob": plan.WORKER_BLOB,
        "config_blob": plan.CONFIG_BLOB,
        "secrets_file": path,
        "allow_deploy_once": True,
    }


def report_snapshot():
    message = (
        "source-commit:" + plan.SOURCE_COMMIT
        + ",source-blob:" + plan.WORKER_BLOB
        + ",config-blob:" + plan.CONFIG_BLOB
    )
    return {
        "schema": "ausmalwiese.report-wrangler-post-deploy.v1",
        "worker": plan.WORKER,
        "wrangler_version": plan.WRANGLER_VERSION,
        "source_commit": plan.SOURCE_COMMIT,
        "source_blob": plan.WORKER_BLOB,
        "config_blob": plan.CONFIG_BLOB,
        "latest_version": VERSION,
        "active_versions": [{"version_id": VERSION, "percentage": 100}],
        "version_tag": "git:" + plan.SOURCE_COMMIT,
        "version_message": message,
        "routes": copy.deepcopy(plan.ROUTES),
        "binding_kinds": copy.deepcopy(plan.BINDING_KINDS),
        "ratelimits": copy.deepcopy(plan.RATELIMITS),
        "config_endpoint": {
            "url": plan.CONFIG_ENDPOINT,
            "status": 200,
            "site_key_present": True,
        },
    }


def stats_snapshot():
    return {
        "schema": "ausmalwiese.stats-unchanged-proof.v1",
        "worker": plan.STATS_WORKER,
        "latest_version": STATS_VERSION,
        "active_versions": [{"version_id": STATS_VERSION, "percentage": 100}],
        "routes_sha256": "1" * 64,
        "bindings_sha256": "2" * 64,
        "settings_sha256": "3" * 64,
    }


class ReportWranglerDeployTests(unittest.TestCase):
    def test_contract_is_source_only(self):
        data = json.loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        self.assertFalse(data["actions"]["run_wrangler"])
        self.assertFalse(data["actions"]["cloudflare_request"])
        self.assertFalse(data["actions"]["credential_or_secret_access"])
        self.assertFalse(data["actions"]["merge"])
        self.assertFalse(data["actions"]["live"])
        self.assertFalse(data["actions"]["retry"])
        self.assertEqual(plan.main(["--check-contract"]), 0)
        self.assertEqual(plan.main(["--deploy"]), 2)

    def test_exact_reviewed_config_is_accepted(self):
        self.assertEqual(plan.validate_config(plan.expected_config()),
                         plan.expected_config())

    def test_config_rejects_target_route_binding_and_rate_drift(self):
        mutations = (
            lambda x: x.update(name="other-worker"),
            lambda x: x.update(main="./other.mjs"),
            lambda x: x.update(workers_dev=True),
            lambda x: x["routes"].append(
                {"pattern": "ausmalwiese.de/*", "zone_name": "ausmalwiese.de"}
            ),
            lambda x: x["routes"][0].update(pattern="ausmalwiese.de/api/*"),
            lambda x: x["secrets"]["required"].remove("REPORT_TO"),
            lambda x: x["secrets"]["required"].append("EXTRA_SECRET"),
            lambda x: x["ratelimits"][0].update(namespace_id="999"),
            lambda x: x["ratelimits"][0]["simple"].update(limit=13),
            lambda x: x["ratelimits"][1]["simple"].update(period=10),
            lambda x: x.update(vars={"REPORT_TO": "forbidden"}),
        )
        for mutation in mutations:
            bad = copy.deepcopy(plan.expected_config())
            mutation(bad)
            with self.assertRaises(plan.Blocked):
                plan.validate_config(bad)

    def test_application_provenance_rejects_wrong_source_or_config_blob(self):
        good = application()
        plan.validate_application_evidence(good)
        for key in ("commit", "worker_blob", "config_blob"):
            bad = copy.deepcopy(good)
            bad[key] = "0" * 40
            with self.assertRaisesRegex(plan.Blocked,
                                        "APPLICATION_PROVENANCE_DRIFT"):
                plan.validate_application_evidence(bad)

    def test_deploy_command_is_exact_pinned_strict_and_secrets_bound(self):
        cmd = plan.deploy_command(application(), approval())
        self.assertEqual(
            cmd[:4],
            ["npx", "--yes", "wrangler@4.135.0", "deploy"],
        )
        self.assertIn("--strict", cmd)
        self.assertIn("--no-bundle", cmd)
        self.assertIn("--secrets-file", cmd)
        self.assertIn("/run/credentials/ausmalwiese-report-worker.env", cmd)
        self.assertIn("git:" + plan.SOURCE_COMMIT, cmd)
        self.assertIn("source-blob:" + plan.WORKER_BLOB, " ".join(cmd))
        self.assertNotIn("--route", cmd)
        self.assertNotIn("--routes", cmd)
        self.assertNotIn("--var", cmd)
        self.assertNotIn("--env-file", cmd)

    def test_deploy_approval_rejects_missing_or_unbound_secrets_reference(self):
        for path in ("relative.env", "../secret.env", ""):
            with self.assertRaises(plan.Blocked):
                plan.validate_deploy_approval(approval(path))
        bad = approval()
        bad.pop("secrets_file")
        with self.assertRaisesRegex(plan.Blocked, "DEPLOY_APPROVAL_FIELDS"):
            plan.validate_deploy_approval(bad)
        bad = approval()
        bad["wrangler_version"] = "4.134.0"
        with self.assertRaisesRegex(plan.Blocked, "DEPLOY_APPROVAL_UNBOUND"):
            plan.validate_deploy_approval(bad)

    def test_report_post_deploy_snapshot_requires_exact_provenance_and_shape(self):
        good = report_snapshot()
        self.assertEqual(plan.validate_report_snapshot(good), good)

        mutations = (
            lambda x: x.update(wrangler_version="4.134.0"),
            lambda x: x.update(source_blob="0" * 40),
            lambda x: x["active_versions"][0].update(percentage=90),
            lambda x: x["routes"].append(
                {"pattern": "ausmalwiese.de/*", "zone_name": "ausmalwiese.de"}
            ),
            lambda x: x["binding_kinds"].update(EXTRA="secret_text"),
            lambda x: x["binding_kinds"].update(REPORT_TO="plain_text"),
            lambda x: x["ratelimits"][0]["simple"].update(limit=99),
            lambda x: x["config_endpoint"].update(status=503),
            lambda x: x.update(version_tag="wrong"),
        )
        for mutation in mutations:
            bad = report_snapshot()
            mutation(bad)
            with self.assertRaises(plan.Blocked):
                plan.validate_report_snapshot(bad)

    def test_stats_pre_post_must_be_byte_equivalent(self):
        before = stats_snapshot()
        after = copy.deepcopy(before)
        digest = plan.validate_stats_unchanged(before, after)
        self.assertEqual(len(digest), 64)

        for mutation in (
            lambda x: x.update(latest_version=VERSION),
            lambda x: x["active_versions"][0].update(percentage=90),
            lambda x: x.update(routes_sha256="4" * 64),
            lambda x: x.update(bindings_sha256="5" * 64),
            lambda x: x.update(settings_sha256="6" * 64),
        ):
            bad = copy.deepcopy(after)
            mutation(bad)
            with self.assertRaises(plan.Blocked):
                plan.validate_stats_unchanged(before, bad)

    def test_verification_commands_are_read_only_and_exact_target(self):
        commands = plan.read_only_verification_commands(VERSION)
        joined = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any("versions list" in item for item in joined))
        self.assertTrue(any("deployments list" in item for item in joined))
        self.assertTrue(any("versions view " + VERSION in item for item in joined))
        self.assertTrue(any("secret list" in item for item in joined))
        self.assertTrue(any(plan.CONFIG_ENDPOINT in item for item in joined))
        for item in joined:
            self.assertNotIn(" deploy ", " " + item + " ")
            self.assertNotIn(" secret put ", " " + item + " ")
            self.assertNotIn(" secret delete ", " " + item + " ")
            self.assertNotIn(" d1 execute ", " " + item + " ")

    def test_source_has_no_executor_or_network_client(self):
        text = SOURCE.read_text("utf-8")
        for forbidden in (
            "subprocess",
            "os.system",
            "os.environ",
            "requests",
            "http.client",
            "urllib.request",
            "Authorization: Bearer",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
