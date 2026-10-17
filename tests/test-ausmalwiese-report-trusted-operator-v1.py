#!/usr/bin/env python3
"""Synthetic, offline-only tests for dedicated report Worker future protocol.

Every adapter here is in-memory, never Cloudflare. Fake source validation is
explicitly patched for choreography tests; this is not LIVE/source evidence.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ausmalwiese_report_worker_trusted_operator.py"
spec = importlib.util.spec_from_file_location("report_trusted_core", SCRIPT)
assert spec and spec.loader
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

VERSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DEPLOYMENT = "11111111-2222-3333-4444-555555555555"


def envelope():
    return {
        "worker": op.TARGET["worker"], "zone": op.TARGET["zone"],
        "source_blob": op.SOURCE["blob"], "upload_once": True,
        "deploy_once": True, "add_four_exact_routes_once": True,
    }


class FakeProtectedAdapter:
    """Unit-test double only: no network/credentials/filesystem mutation."""

    def __init__(self, fail_at=None):
        self.stage = "absent"
        self.routes = []
        self.calls = []
        self.fail_at = fail_at
        self.modified = None
        self.reads = 0

    def read_sanitized(self):
        self.reads += 1
        if self.fail_at == "read1":
            raise RuntimeError("synthetic")
        status = self.stage
        present = status != "absent"
        active = status == "active"
        result = {
            "schema": "ausmalwiese.report-worker.sanitized-snapshot.v1",
            "target": dict(op.TARGET),
            "proof": {
                "account_verified": True,
                "zone_verified": True,
                "operator_capability_verified": True,
                "turnstile_hostnames_verified": True,
                "brevo_account_eligibility_verified": True,
                "protected_binding_provisioner_ready": True,
                "privacy_review_completed": True,
                "unrelated_routes_inventory_verified": True,
            },
            "worker_exists": present,
            "active_version": VERSION if active else None,
            "latest_uploaded_version": VERSION if present else None,
            "deployment_id": DEPLOYMENT if active else None,
            "traffic_percent": 100 if active else None,
            "active_code_sha256": op.SOURCE["sha256"] if active else None,
            "latest_code_sha256": op.SOURCE["sha256"] if present else None,
            "binding_kinds": dict(op.KINDS) if present else {},
            "rate_limits": copy.deepcopy(op.LIMITS) if present else {},
            "namespace_ids": {"REPORT_RATE": "1001", "REPORT_DUP": "1002"} if present else {},
            "report_routes": {r: op.TARGET["worker"] for r in self.routes},
            "unrelated_routes_sha256": "0" * 64,
        }
        if self.modified:
            self.modified(result)
        return result

    def upload_report_version_once(self, **arguments):
        self.calls.append("upload")
        if self.fail_at == "upload":
            raise RuntimeError("synthetic dispatch uncertain")
        self.stage = "uploaded"
        return {"version_id": VERSION}

    def deploy_report_version_once(self, **arguments):
        self.calls.append("deploy")
        if self.fail_at == "deploy":
            raise RuntimeError("synthetic dispatch uncertain")
        self.stage = "active"
        return {"deployment_id": DEPLOYMENT}

    def add_exact_report_route_once(self, **arguments):
        route = arguments["route"]
        self.calls.append("route:" + route)
        if self.fail_at == "route":
            raise RuntimeError("synthetic dispatch uncertain")
        self.routes.append(route)
        return {"route": route, "worker": op.TARGET["worker"]}


def simulated(trusted, approval=None):
    with patch.object(op, "verify_source", lambda _: None):
        return op.future_protocol(trusted, envelope() if approval is None else approval, b"synthetic")


class ReportProtocolTests(unittest.TestCase):
    def test_static_contract_exact_and_no_live_authority(self):
        cfg = op.load_contract()
        op.check_contract(cfg)
        self.assertFalse(cfg["owner_live_approval"])
        self.assertFalse(cfg["credential_access"])
        self.assertFalse(cfg["settings_access"])
        self.assertFalse(cfg["host_mutation"])
        self.assertEqual(len(cfg["report_routes"]), 4)
        self.assertEqual(set(cfg["binding_kinds"]), set(op.KINDS))
        self.assertEqual(len(cfg["binding_kinds"]), 6)

    def test_cli_only_static_contract_check(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--check-contract"], capture_output=True, text=True, timeout=5)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "SOURCE_CONTRACT_OK_NOT_LIVE_PROOF"))
        bad = subprocess.run([sys.executable, str(SCRIPT), "--deploy"], capture_output=True, text=True, timeout=5)
        self.assertEqual((bad.returncode, bad.stdout.strip()), (2, op.STOP))

    def test_contract_rejects_scope_expansion(self):
        for mutate in (
            lambda cfg: cfg["binding_kinds"].update(SECRET_EXTRA="secret_text"),
            lambda cfg: cfg["target"].update(worker="coloring-pages-stats-v1"),
            lambda cfg: cfg["report_routes"].append("ausmalwiese.de/*"),
            lambda cfg: cfg.update(owner_live_approval=True),
            lambda cfg: cfg.update(allow_retry=True),
        ):
            cfg = copy.deepcopy(op.contract_expected())
            mutate(cfg)
            with self.assertRaises(op.Blocked):
                op.check_contract(cfg)

    def test_source_bytes_reject_unpinned_file(self):
        for blob in (b"synthetic", b"", None, "string"):
            with self.assertRaises(op.Blocked):
                op.verify_source(blob)

    def test_snapshot_requires_zero_existing_report_worker(self):
        fake = FakeProtectedAdapter()
        before = fake.read_sanitized()
        self.assertIs(op.validate_snapshot(before, "absent"), before)
        before["worker_exists"] = True
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(before, "absent")

    def test_snapshot_rejects_stats_route_widening(self):
        f = FakeProtectedAdapter()
        f.routes = ["ausmalwiese.de/api/stats/*"]
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(f.read_sanitized(), "absent")

    def test_snapshot_rejects_cross_account_or_unverified_preflight(self):
        f = FakeProtectedAdapter()
        f.modified = lambda x: x["target"].update(zone="other.example")
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(f.read_sanitized(), "absent")
        f.modified = lambda x: x["proof"].update(privacy_review_completed=False)
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(f.read_sanitized(), "absent")

    def test_six_binding_names_and_no_secret_values(self):
        intent = op.upload_intent()
        self.assertEqual(set(intent["expected_binding_kinds"]), set(op.KINDS))
        self.assertFalse(intent["secret_values_in_source"])
        self.assertFalse(any(x in str(intent).lower() for x in ("api-key:", "bearer ", "recipient@example")))
        f = FakeProtectedAdapter()
        f.stage = "uploaded"
        snap = f.read_sanitized()
        op.validate_snapshot(snap, "uploaded")
        snap["binding_kinds"]["REPORT_TO"] = "plain_text"
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(snap, "uploaded")
        snap = f.read_sanitized()
        snap["binding_kinds"]["EXTRA"] = "secret_text"
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(snap, "uploaded")

    def test_namespace_and_policy_validation(self):
        f = FakeProtectedAdapter()
        f.stage = "uploaded"
        for values in (
            {"REPORT_RATE": "1001", "REPORT_DUP": "1001"},
            {"REPORT_RATE": "0", "REPORT_DUP": "1002"},
            {"REPORT_RATE": "01", "REPORT_DUP": "1002"},
            {"REPORT_RATE": 1001, "REPORT_DUP": "1002"},
            {"REPORT_RATE": "4294967296", "REPORT_DUP": "1002"},
        ):
            snap = f.read_sanitized()
            snap["namespace_ids"] = values
            with self.assertRaises(op.Blocked):
                op.validate_snapshot(snap, "uploaded")
        snap = f.read_sanitized()
        snap["rate_limits"]["REPORT_RATE"]["limit"] = 120
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(snap, "uploaded")

    def test_no_forged_metadata_fields(self):
        f = FakeProtectedAdapter()
        f.stage = "uploaded"
        snap = f.read_sanitized()
        snap["secret"] = "fake-value"
        with self.assertRaises(op.Blocked):
            op.validate_snapshot(snap, "uploaded")

    def test_no_owner_authority_never_dispatches(self):
        fake = FakeProtectedAdapter()
        for approval in ({}, dict(envelope(), worker="coloring-pages-stats-v1"),
                         dict(envelope(), deploy_once=False)):
            with self.assertRaises(op.Blocked):
                simulated(fake, approval=approval)
            self.assertEqual(fake.calls, [])
        with self.assertRaises(op.Blocked):
            op.future_protocol(fake, None, b"synthetic")
        self.assertEqual(fake.calls, [])

    def test_synthetic_protocol_orders_six_dispatches_once(self):
        fake = FakeProtectedAdapter()
        result = simulated(fake)
        self.assertEqual(fake.calls, ["upload", "deploy"] + ["route:" + route for route in op.ROUTES])
        self.assertEqual(fake.routes, list(op.ROUTES))
        self.assertEqual(result["result"], "FUTURE_PROTOCOL_FINISHED_NEEDS_INDEPENDENT_HTTP_AND_MAIL_PROOF")

    def test_preflight_failure_no_mutation(self):
        fake = FakeProtectedAdapter(fail_at="read1")
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "PREFLIGHT_UNAVAILABLE_STOP")
        self.assertEqual(fake.calls, [])

    def test_preflight_drift_no_mutation(self):
        fake = FakeProtectedAdapter()
        fake.modified = lambda x: x.update(
            unrelated_routes_sha256=("1" * 64 if fake.reads > 1 else "0" * 64)
        )
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "PREFLIGHT_DRIFT_STOP")
        self.assertEqual(fake.calls, [])

    def test_upload_outcome_unknown_no_retry(self):
        fake = FakeProtectedAdapter(fail_at="upload")
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "UPLOAD_OUTCOME_UNKNOWN_STOP")
        self.assertEqual(fake.calls, ["upload"])

    def test_post_upload_drift_stops_before_deploy(self):
        fake = FakeProtectedAdapter()
        fake.modified = lambda x: x.update(unrelated_routes_sha256="f" * 64) if fake.stage != "absent" else None
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "POST_UPLOAD_UNVERIFIED_STOP")
        self.assertEqual(fake.calls, ["upload"])

    def test_deploy_failure_stops_once(self):
        fake = FakeProtectedAdapter(fail_at="deploy")
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "DEPLOY_OUTCOME_UNKNOWN_STOP")
        self.assertEqual(fake.calls, ["upload", "deploy"])

    def test_route_failure_stops_before_next_route(self):
        fake = FakeProtectedAdapter(fail_at="route")
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "ROUTE_OUTCOME_UNKNOWN_STOP")
        self.assertEqual(fake.calls, ["upload", "deploy", "route:" + op.ROUTES[0]])

    def test_route_wrong_worker_reply_rejected(self):
        fake = FakeProtectedAdapter()
        def wrong_route(**arguments):
            fake.calls.append("route:wrong")
            return {"route": arguments["route"], "worker": "coloring-pages-stats-v1"}
        fake.add_exact_report_route_once = wrong_route
        with self.assertRaises(op.Blocked) as err:
            simulated(fake)
        self.assertEqual(str(err.exception), "ROUTE_REPLY_AMBIGUOUS_STOP")
        self.assertEqual(fake.calls, ["upload", "deploy", "route:wrong"])


if __name__ == "__main__":
    unittest.main()
