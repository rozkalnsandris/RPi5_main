#!/usr/bin/env python3
"""Synthetic only: safety gates of Ausmalwiese Stats Worker #1032."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/ausmalwiese_stats_worker_exact_deploy.py"
spec = importlib.util.spec_from_file_location("ausmalwiese_stats_exact", FILE)
op = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = op
spec.loader.exec_module(op)

OLD = "e47f145f-1234-4123-a456-0123456789ab"
NEW = "2e44a0dc-1234-4123-a456-0123456789ab"
OLD_DEPLOYMENT = "11111111-1234-4123-a456-0123456789ab"
NEW_DEPLOYMENT = "22222222-1234-4123-a456-0123456789ab"
FINGERPRINT = "a" * 64
SOURCE_FIXTURE = b"synthetic-does-not-match-a-production-blob"


def bindings():
    return {name: {"kind": kind, "fingerprint": None if kind == "secret_text" else FINGERPRINT}
            for name, kind in op.KINDS.items()}


def snapshot(*, active=OLD, latest=OLD, deployment=OLD_DEPLOYMENT):
    config = {
        "compatibility_date": "2026-09-01",
        "compatibility_flags": ["nodejs_compat"],
        "settings_sha256": FINGERPRINT,
    }
    return {
        "schema": "ausmalwiese.stats-worker-protected-inventory.v1",
        "account_sha256": op.ACCOUNT_SHA256,
        "worker": op.WORKER,
        "environment": "production",
        "active_version": active,
        "latest_uploaded_version": latest,
        "active_code_sha256": op.canonical_sha256(SOURCE_FIXTURE) if active == NEW else "c" * 64,
        "latest_code_sha256": op.canonical_sha256(SOURCE_FIXTURE) if latest == NEW else "c" * 64,
        "deployment_id": deployment,
        "traffic_percent": 100,
        "routes": dict(op.ROUTES),
        "active_bindings": bindings(),
        "latest_bindings": bindings(),
        "active_configuration": copy.deepcopy(config),
        "latest_configuration": copy.deepcopy(config),
    }


def approval(before=None):
    value = snapshot() if before is None else before
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return {
        "source_blob": op.SOURCE_BLOB,
        "config_blob": op.CONFIG_BLOB,
        "worker": op.WORKER,
        "preflight_sha256": op.canonical_sha256(raw),
        "allow_upload_once": True,
        "allow_deploy_once": True,
    }


class FakeProtectedBoundary:
    """Never contacts Cloudflare, reads credentials, or changes external state."""

    def __init__(self, reads, *, upload_reply=None, deployment_reply=None, fail_upload=False,
                 fail_deploy=False):
        self.reads = iter(copy.deepcopy(reads))
        self.calls = []
        self.upload_reply = upload_reply if upload_reply is not None else {"version_id": NEW}
        self.deployment_reply = (deployment_reply if deployment_reply is not None
                                 else {"deployment_id": NEW_DEPLOYMENT})
        self.fail_upload = fail_upload
        self.fail_deploy = fail_deploy

    def read_snapshot(self):
        self.calls.append("read")
        return next(self.reads)

    def upload_version_once(self, **kwargs):
        self.calls.append(("upload", kwargs))
        if self.fail_upload:
            raise RuntimeError("untrusted raw provider error containing token")
        return copy.deepcopy(self.upload_reply)

    def deploy_version_once(self, **kwargs):
        self.calls.append(("deploy", kwargs))
        if self.fail_deploy:
            raise RuntimeError("untrusted raw provider error containing token")
        return copy.deepcopy(self.deployment_reply)


class ExactWorkerGateTests(unittest.TestCase):
    def test_contract_source_only_and_exact_identity(self):
        c = json.loads(op.CONTRACT_PATH.read_text(encoding="utf-8"))
        op.check_contract(c)
        self.assertFalse(c["credential_access"])
        self.assertFalse(c["owner_live_approval"])
        self.assertTrue(c["merge_approval"])
        self.assertEqual(c["issue"], 1118)
        self.assertEqual(
            c["source_commit"], "97741638b4cb52a3241533f30485c0e7529fdd82"
        )
        self.assertEqual(
            c["source_blob"], "ccb68d7bbf12474f32e0f94d574ead1b02cd9c7e"
        )
        self.assertEqual(
            c["config_blob"], "3733263a391274f2b6b0f2023c8656565bde8e1a"
        )
        self.assertEqual(len(c["routes"]), 4)
        self.assertEqual(len(c["bindings"]), 7)
        self.assertEqual(c["account_sha256"], op.ACCOUNT_SHA256)
        for key, value in (("mode", "WRITABLE_LIVE"), ("source_blob", "a" * 40),
                           ("worker", "wrong-worker")):
            bad = dict(c, **{key: value})
            with self.assertRaises(op.Blocked):
                op.check_contract(bad)

    def test_cli_source_check_only(self):
        self.assertEqual(op.main(["--check-contract"]), 0)
        self.assertEqual(op.main(["--apply"]), 2)
        self.assertEqual(op.main(["--deploy"]), 2)

    def test_no_real_transport_or_credential_reader(self):
        source = FILE.read_text(encoding="utf-8")
        for snippet in ("import requests", "import http.client", "import urllib.request",
                        "subprocess.run", "CLOUDFLARE_API_TOKEN", "wrangler deploy",
                        "os.environ", "open('/etc/"):
            self.assertNotIn(snippet, source)

    def test_source_must_match_git_blob_not_only_qr_snippet(self):
        with self.assertRaisesRegex(op.Blocked, "SOURCE_BLOB_DRIFT"):
            op.verify_source(b'const PRINT_QR_DESTINATION = "https://ausmalwiese.de/";')
        with self.assertRaisesRegex(op.Blocked, "SOURCE_SIZE"):
            op.verify_source(b"")

    def test_source_traffic_contract_rejects_missing_fields(self):
        raw = (
            'const PRINT_QR_HOST = "ausmalwiese.de";\n'
            'const PRINT_QR_DESTINATION = "https://ausmalwiese.de/";\n'
            'const host = "ausmalwiese.de";\n'
            "clientRequestHTTPHost: host,\n"
            "ANALYTICS_RANGE_DAYS.has(requestedDays)\n"
            "cloudflare_traffic_version:1\n"
            "http_requests:httpRequests\n"
            'http_requests_basis:"cloudflare-http-eyeball-requests"\n'
        ).encode("utf-8")
        with mock.patch.object(op, "git_blob", return_value=op.SOURCE_BLOB):
            op.verify_source(raw)
            for lost in (
                b'const host = "ausmalwiese.de";',
                b"clientRequestHTTPHost: host,",
                b"ANALYTICS_RANGE_DAYS.has(requestedDays)",
                b"cloudflare_traffic_version:1",
                b"http_requests:httpRequests",
                b'http_requests_basis:"cloudflare-http-eyeball-requests"',
            ):
                with self.subTest(lost=lost):
                    with self.assertRaisesRegex(op.Blocked, "SOURCE_TRAFFIC_DRIFT"):
                        op.verify_source(raw.replace(lost, b""))
    def test_snapshot_positive_and_upload_metadata(self):
        x = snapshot()
        self.assertEqual(op.validate_snapshot(x), x)
        meta = op.upload_metadata(x)
        self.assertEqual(meta["main_module"], "stats-worker.js")
        self.assertEqual(meta["compatibility_date"], "2026-09-01")
        self.assertEqual(meta["compatibility_flags"], ["nodejs_compat"])
        self.assertEqual(len(meta["bindings"]), 7)
        self.assertEqual(set(b["name"] for b in meta["bindings"]), set(op.KINDS))
        for b in meta["bindings"]:
            self.assertEqual(b, {"type": "inherit", "name": b["name"], "version_id": "latest"})
        self.assertNotIn("secret", str(meta).lower())

    def test_version_mismatch_stops_before_inheritance(self):
        x = snapshot(latest=NEW)
        with self.assertRaisesRegex(op.Blocked, "LATEST_NOT_ACTIVE"):
            op.upload_metadata(x)

    def test_snapshot_rejects_split_traffic_and_invalid_version(self):
        for changed in ({"traffic_percent": 99}, {"traffic_percent": True},
                        {"active_version": "e47f145f"}, {"deployment_id": "x"},
                        {"account_sha256": "b" * 64},
                        {"environment": "preview"}):
            x = dict(snapshot(), **changed)
            with self.assertRaises(op.Blocked):
                op.validate_snapshot(x)

    def test_route_extraneous_or_wrong_zone_is_rejected(self):
        for k, v in (("ausmalwiese.de/q", "rozkalns.net"),
                     ("dangerous.other/*", "other.example")):
            x = snapshot()
            x["routes"][k] = v
            with self.assertRaisesRegex(op.Blocked, "ROUTE_DRIFT"):
                op.validate_snapshot(x)
        x = snapshot()
        del x["routes"]["ausmalwiese.de/q"]
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(x)

    def test_seven_exact_binding_names_kinds_fingerprints(self):
        x = snapshot()
        del x["active_bindings"]["VISITOR_HMAC_KEY"]
        with self.assertRaisesRegex(op.Blocked, "BINDING_SET"):
            op.validate_snapshot(x)
        x = snapshot()
        x["latest_bindings"]["RATE_LIMITER"]["kind"] = "plain_text"
        with self.assertRaisesRegex(op.Blocked, "BINDING_KIND"):
            op.validate_snapshot(x)
        x = snapshot()
        x["active_bindings"]["VISITOR_HMAC_KEY"]["fingerprint"] = "a" * 64
        with self.assertRaisesRegex(op.Blocked, "SECRET_DISCLOSURE"):
            op.validate_snapshot(x)
        x = snapshot()
        x["latest_bindings"]["DB"]["fingerprint"] = None
        with self.assertRaisesRegex(op.Blocked, "BINDING_IDENTITY"):
            op.validate_snapshot(x)
        x = snapshot()
        x["active_bindings"]["CF_ANALYTICS_HOST"]["value"] = "secret-or-raw-config"
        with self.assertRaisesRegex(op.Blocked, "BINDING_DESCRIPTOR"):
            op.validate_snapshot(x)

    def test_configuration_unknown_or_drift(self):
        x = snapshot()
        x["active_configuration"]["unsafe_new_key"] = True
        with self.assertRaisesRegex(op.Blocked, "CONFIG_DESCRIPTOR"):
            op.validate_snapshot(x)
        x = snapshot()
        x["active_configuration"]["compatibility_flags"] = ["nodejs_compat", "nodejs_compat"]
        with self.assertRaisesRegex(op.Blocked, "COMPATIBILITY_FLAGS"):
            op.validate_snapshot(x)
        x = snapshot()
        x["latest_configuration"]["settings_sha256"] = "b" * 64
        with self.assertRaisesRegex(op.Blocked, "LATEST_METADATA_DRIFT"):
            op.upload_metadata(x)

    def run_protocol(self, boundary, permit=None):
        with mock.patch.object(op, "verify_source") as source:
            permit_value = approval(snapshot()) if permit is None else permit
            result = op.future_run_once(boundary, permit_value, SOURCE_FIXTURE)
        source.assert_called_once_with(SOURCE_FIXTURE)
        return result

    @staticmethod
    def good_boundary():
        return FakeProtectedBoundary([snapshot(), snapshot(),
                                      snapshot(active=OLD, latest=NEW),
                                      snapshot(active=NEW, latest=NEW,
                                               deployment=NEW_DEPLOYMENT)])

    def test_happy_path_exactly_one_upload_one_deploy(self):
        boundary = self.good_boundary()
        r = self.run_protocol(boundary)
        self.assertEqual(r["new_version"], NEW)
        uploads = [x for x in boundary.calls if isinstance(x, tuple) and x[0] == "upload"]
        deploys = [x for x in boundary.calls if isinstance(x, tuple) and x[0] == "deploy"]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(len(deploys), 1)
        self.assertEqual(uploads[0][1]["bindings_inherit"], "strict")
        self.assertEqual(uploads[0][1]["module_name"], "stats-worker.js")
        self.assertEqual(deploys[0][1]["payload"],
                         {"strategy": "percentage",
                          "versions": [{"version_id": NEW, "percentage": 100}]})

    def test_missing_owner_gate_never_reads_or_writes(self):
        boundary = self.good_boundary()
        with self.assertRaisesRegex(op.Blocked, "OWNER_GATE_UNBOUND"):
            self.run_protocol(boundary, dict(approval(), allow_deploy_once=False))
        self.assertEqual(boundary.calls, [])

    def test_drift_on_second_read_stops_before_first_mutation(self):
        y = snapshot()
        y["deployment_id"] = NEW_DEPLOYMENT
        boundary = FakeProtectedBoundary([snapshot(), y])
        with self.assertRaisesRegex(op.Blocked, "PREFLIGHT_STATE_DRIFT"):
            self.run_protocol(boundary)
        self.assertEqual(boundary.calls, ["read", "read"])

    def test_upload_error_is_terminal_and_no_retry(self):
        boundary = FakeProtectedBoundary([snapshot(), snapshot()], fail_upload=True)
        with self.assertRaisesRegex(op.Blocked, "UPLOAD_OUTCOME_UNKNOWN_STOP"):
            self.run_protocol(boundary)
        self.assertEqual(len([x for x in boundary.calls if isinstance(x, tuple)]), 1)
        self.assertNotIn("untrusted raw provider error", str(boundary.calls))

    def test_upload_reply_invalid_stops_without_deploy(self):
        boundary = FakeProtectedBoundary([snapshot(), snapshot()],
                                         upload_reply={"version_id": "bad"})
        with self.assertRaisesRegex(op.Blocked, "UPLOAD_VERSION_INVALID_STOP"):
            self.run_protocol(boundary)
        self.assertEqual(len([x for x in boundary.calls if isinstance(x, tuple)]), 1)

    def test_post_upload_unverified_stops_without_deploy(self):
        middle = snapshot(active=OLD, latest=NEW)
        middle["latest_bindings"]["DB"]["fingerprint"] = "b" * 64
        boundary = FakeProtectedBoundary([snapshot(), snapshot(), middle])
        with self.assertRaisesRegex(op.Blocked, "POST_UPLOAD_UNVERIFIED_STOP"):
            self.run_protocol(boundary)
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "deploy" for x in boundary.calls))

    def test_uploaded_code_mismatch_stops_before_promotion(self):
        middle = snapshot(active=OLD, latest=NEW)
        middle["latest_code_sha256"] = "d" * 64
        boundary = FakeProtectedBoundary([snapshot(), snapshot(), middle])
        with self.assertRaisesRegex(op.Blocked, "POST_UPLOAD_UNVERIFIED_STOP"):
            self.run_protocol(boundary)
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "deploy" for x in boundary.calls))

    def test_deployed_code_mismatch_is_terminal(self):
        last = snapshot(active=NEW, latest=NEW, deployment=NEW_DEPLOYMENT)
        last["active_code_sha256"] = "d" * 64
        boundary = FakeProtectedBoundary([snapshot(), snapshot(),
                                          snapshot(active=OLD, latest=NEW), last])
        with self.assertRaisesRegex(op.Blocked, "POST_DEPLOY_UNVERIFIED_STOP"):
            self.run_protocol(boundary)
        self.assertEqual(len([x for x in boundary.calls if isinstance(x, tuple)]), 2)

    def test_post_upload_active_changed_stops_without_deploy(self):
        middle = snapshot(active=NEW, latest=NEW)
        boundary = FakeProtectedBoundary([snapshot(), snapshot(), middle])
        with self.assertRaisesRegex(op.Blocked, "POST_UPLOAD_UNVERIFIED_STOP"):
            self.run_protocol(boundary)

    def test_deploy_error_terminal_no_retry(self):
        boundary = FakeProtectedBoundary([snapshot(), snapshot(),
                                          snapshot(active=OLD, latest=NEW)],
                                         fail_deploy=True)
        with self.assertRaisesRegex(op.Blocked, "DEPLOY_OUTCOME_UNKNOWN_STOP"):
            self.run_protocol(boundary)
        self.assertEqual(len([x for x in boundary.calls if isinstance(x, tuple)
                              and x[0] == "deploy"]), 1)

    def test_deploy_post_verify_failure_no_rollback(self):
        final = snapshot(active=NEW, latest=NEW, deployment=NEW_DEPLOYMENT)
        final["routes"]["ausmalwiese.de/q"] = "bad-zone"
        boundary = FakeProtectedBoundary([snapshot(), snapshot(),
                                          snapshot(active=OLD, latest=NEW), final])
        with self.assertRaisesRegex(op.Blocked, "POST_DEPLOY_UNVERIFIED_STOP"):
            self.run_protocol(boundary)
        self.assertEqual(len([x for x in boundary.calls if isinstance(x, tuple)]), 2)

if __name__ == "__main__":
    unittest.main()
