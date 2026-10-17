#!/usr/bin/env python3
"""Offline-only report trusted-transport regressions. No external requests."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ausmalwiese_report_trusted_transport.py"
spec = importlib.util.spec_from_file_location("report_transport_source", SCRIPT)
assert spec and spec.loader
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

ACCOUNT = "a" * 32
ZONE = "b" * 32
VERSION = "11111111-2222-3333-4444-555555555555"
DIGEST = "a" * 64
PROOF_SHA = "b" * 64


def spec_for(operation, **values):
    with patch.object(t, "ACCOUNT_FINGERPRINT",
                      hashlib.sha256(ACCOUNT.encode()).hexdigest()):
        return t.blueprint(operation, ACCOUNT, ZONE, **values)


def body(kind, route=None):
    result = {"id": VERSION}
    if kind == "route":
        result = {"id": "c" * 32, "pattern": route, "script": t.WORKER}
    return json.dumps({
        "success": True, "errors": [], "messages": [], "result": result,
    }).encode("utf-8")


def provisioning():
    return {
        "source": t.SOURCE_SHA256,
        "binding_kinds": dict(t.KINDS),
        "rate_limits": copy.deepcopy(t.RATES),
        "namespace_ids": {"REPORT_RATE": "1001", "REPORT_DUP": "1002"},
        "sealed_private_names": list(t.SECRET_NAMES),
        "sitekey_hostname_set": ["ausmalwiese.de", "www.ausmalwiese.de"],
        "siteverify_action": "report",
        "private_provider_ready": True,
        "account_verified": True, "zone_verified": True,
        "atomic_version_upload_capability": True,
        "no_reusable_secret_in_evidence": True,
    }


def version_proof():
    p = provisioning()
    return {
        "collector": "INDEPENDENT_AUTHENTICATED_READ_ONLY_COLLECTOR",
        "account_sha256": t.ACCOUNT_FINGERPRINT,
        "zone": t.ZONE, "worker": t.WORKER,
        "version": VERSION, "active_version": VERSION,
        "source_sha256": t.SOURCE_SHA256,
        "source_git_blob": t.SOURCE_BLOB,
        "binding_kinds": dict(t.KINDS), "rates": copy.deepcopy(t.RATES),
        "namespace_ids": dict(p["namespace_ids"]),
        "unrelated_routes_sha256": DIGEST,
        "report_routes": {r: t.WORKER for r in t.ROUTES},
    }


class TransportTests(unittest.TestCase):
    def test_contract_and_source_only_flags(self):
        c = json.loads(t.CONTRACT.read_text(encoding="utf-8"))
        t.check_contract(c)
        self.assertEqual(len(t.KINDS), 6)
        self.assertEqual(len(t.ROUTES), 4)
        self.assertEqual(c["host"], "api.cloudflare.com")
        self.assertEqual(c["port"], 443)
        self.assertEqual(c["constraints"]["allow_in_checkout_network"], False)
        for field in ("allow_live", "allow_cli_send", "allow_credential_access",
                      "allow_legacy_put", "allow_retry", "allow_rollback",
                      "allow_cleanup", "allow_merge"):
            self.assertFalse(c["constraints"][field])

    def test_contract_scope_drift_fails(self):
        mutations = [
            lambda x: x.update(worker="coloring-pages-stats-v1"),
            lambda x: x.update(host="other.example"),
            lambda x: x.update(port=80),
            lambda x: x.update(protocol="HTTP"),
            lambda x: x["methods"].update(upload="PUT"),
            lambda x: x["paths"].update(upload="/client/v4/anything"),
            lambda x: x["routes"].append("ausmalwiese.de/api/report*"),
            lambda x: x["bindings"].update(OTHER="secret_text"),
            lambda x: x["rates"]["REPORT_RATE"].update(limit=120),
            lambda x: x["constraints"].update(allow_retry=True),
        ]
        for mutation in mutations:
            c = copy.deepcopy(t.expected_contract())
            mutation(c)
            with self.subTest(mutation=repr(mutation)), self.assertRaises(t.Stop):
                t.check_contract(c)

    def test_exact_networkless_blueprints(self):
        upload = spec_for("upload")
        deploy = spec_for("deploy", version=VERSION)
        self.assertEqual(upload["body"], None)
        self.assertEqual(upload["method"], "POST")
        self.assertTrue(upload["path"].endswith("/coloring-pages-report-v1/versions"))
        self.assertEqual(upload["body_policy"],
                         "SEALED_MULTIPART_NOT_AVAILABLE_IN_THIS_SOURCE")
        self.assertEqual(deploy["body"], {
            "strategy": "percentage", "versions": [{
                "version_id": VERSION, "percentage": 100,
            }],
        })
        for route in t.ROUTES:
            add = spec_for("route", route=route)
            self.assertEqual(add["body"], {"pattern": route, "script": t.WORKER})
            self.assertTrue(add["path"].endswith("/workers/routes"))
        for blueprint in [upload, deploy, *[spec_for("route", route=r) for r in t.ROUTES]]:
            self.assertEqual((blueprint["scheme"], blueprint["host"], blueprint["port"]),
                             ("https", "api.cloudflare.com", 443))
            self.assertTrue(blueprint["tls_verified"])
            self.assertIsNone(blueprint["proxy"])
            self.assertFalse(blueprint["redirects"])
            self.assertEqual(blueprint["retries"], 0)
            self.assertNotIn("authorization", repr(blueprint).lower())
            self.assertNotIn("api_key", repr(blueprint).lower())

    def test_wrong_targets_and_broader_routes(self):
        with self.assertRaises(t.Stop):
            t.blueprint("upload", ACCOUNT, ZONE)
        with self.assertRaises(t.Stop):
            spec_for("upload", version=VERSION)
        with self.assertRaises(t.Stop):
            spec_for("deploy", version="latest")
        with self.assertRaises(t.Stop):
            spec_for("route", route="ausmalwiese.de/api/stats/*")
        for route in ("ausmalwiese.de/*", "www.ausmalwiese.de/api/report*",
                      "ausmalwiese.de/api/report?foo=1", "other.example/api/report"):
            with self.assertRaises(t.Stop):
                spec_for("route", route=route)
        for operation in ("legacy_script_put", "delete", "settings", "retry", "GET"):
            with self.assertRaises(t.Stop):
                spec_for(operation)
        with patch.object(t, "ACCOUNT_FINGERPRINT",
                          hashlib.sha256(ACCOUNT.encode()).hexdigest()):
            for invalid in ("bad", "z" * 32, "b" * 31, "b" * 32 + "\n"):
                with self.assertRaises(t.Stop):
                    t.blueprint("route", ACCOUNT, invalid, route=t.ROUTES[0])

    def test_http_reply_accepts_only_success_and_no_redirect(self):
        for operation in ("upload", "deploy"):
            record = t.inspect_https_reply(operation, 200,
                                            {"content-type": "application/json"}, body(operation))
            self.assertEqual(len(record), 1)
        route = t.ROUTES[0]
        self.assertEqual(t.inspect_https_reply("route", 201,
                         {"content-type": "application/json; charset=utf-8"},
                         body("route", route), route=route),
                         {"route": route, "worker": t.WORKER})
        for status in (0, 201.0, 202, 301, 302, 307, 401, 403, 429, 500):
            with self.assertRaises(t.Stop):
                t.inspect_https_reply("upload", status, {"content-type": "application/json"}, body("upload"))
        for headers in ({}, {"location": "other.example", "content-type": "application/json"},
                        {"content-type": "text/html"}):
            with self.assertRaises(t.Stop):
                t.inspect_https_reply("upload", 200, headers, body("upload"))
        for invalid in (b"{}", b"invalid", b"\xff", b"x" * 16385, None, '{"foo":"bar"}'):
            with self.assertRaises(t.Stop):
                t.inspect_https_reply("upload", 200, {"content-type": "application/json"}, invalid)
        packet = json.loads(body("upload").decode())
        packet["errors"] = [{"message": "private failure"}]
        with self.assertRaises(t.Stop) as err:
            t.inspect_https_reply("upload", 200, {"content-type": "application/json"},
                                  json.dumps(packet).encode())
        self.assertNotIn("private failure", str(err.exception))

    def test_six_binding_provisioning_attestation_is_non_sensitive(self):
        self.assertEqual(t.validate_provisioning_attestation(provisioning())["result"],
                         "SANITIZED_PROVISIONING_SHAPE_OK_NOT_AUTHORITY")
        base = provisioning()
        changes = [
            lambda x: x["binding_kinds"].update(EXTRA="secret_text"),
            lambda x: x["binding_kinds"].update(REPORT_TO="plain_text"),
            lambda x: x["namespace_ids"].update(REPORT_DUP="1001"),
            lambda x: x["namespace_ids"].update(REPORT_RATE=1001),
            lambda x: x["namespace_ids"].update(REPORT_RATE="0"),
            lambda x: x["namespace_ids"].update(REPORT_RATE="4294967296"),
            lambda x: x["rate_limits"]["REPORT_DUP"].update(limit=12),
            lambda x: x["sealed_private_names"].remove("REPORT_TO"),
            lambda x: x.update(siteverify_action="login"),
            lambda x: x["sitekey_hostname_set"].append("other.example"),
            lambda x: x.update(atomic_version_upload_capability=False),
            lambda x: x.update(private_provider_ready=False),
            lambda x: x.update(private_secret_value="fake"),
        ]
        for change in changes:
            bad = copy.deepcopy(base)
            change(bad)
            with self.subTest(change=repr(change)), self.assertRaises(t.Stop):
                t.validate_provisioning_attestation(bad)

    def test_independent_version_proof_requires_exact_active_code_and_six_bindings(self):
        self.assertEqual(t.verify_independent_version(version_proof(), VERSION, DIGEST)["version"],
                         VERSION)
        changes = [
            lambda x: x.update(worker="coloring-pages-stats-v1"),
            lambda x: x.update(source_sha256="0" * 64),
            lambda x: x.update(source_git_blob="0" * 40),
            lambda x: x.update(active_version="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            lambda x: x.update(unrelated_routes_sha256="1" * 64),
            lambda x: x["binding_kinds"].pop("BREVO_API_KEY"),
            lambda x: x["rates"]["REPORT_RATE"].update(period=30),
            lambda x: x["report_routes"].update({"ausmalwiese.de/*": t.WORKER}),
            lambda x: x["report_routes"].update({t.ROUTES[0]: "coloring-pages-stats-v1"}),
            lambda x: x["namespace_ids"].update(REPORT_DUP="1001"),
            lambda x: x.update(secret_like_field="redacted"),
        ]
        for change in changes:
            bad = version_proof()
            change(bad)
            with self.subTest(change=repr(change)), self.assertRaises(t.Stop):
                t.verify_independent_version(bad, VERSION, DIGEST)

    def test_source_cli_denies_all_live_actions(self):
        yes = subprocess.run([sys.executable, str(SCRIPT), "--check-contract"],
                             text=True, capture_output=True, timeout=10)
        self.assertEqual((yes.returncode, yes.stdout.strip()),
                         (0, "REPORT_TRUSTED_TRANSPORT_SOURCE_OK_NOT_LIVE"))
        for flag in ("--apply", "--deploy", "--send", "--install", "--secrets", "--retry"):
            no = subprocess.run([sys.executable, str(SCRIPT), flag],
                                text=True, capture_output=True, timeout=10)
            self.assertEqual(no.returncode, 2)
            self.assertEqual(no.stdout.strip(), t.STOP)


class DurableGateTests(unittest.TestCase):
    def test_no_production_installed_gate_available(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(t.Stop):
                t.OfflineDurableGate(Path(folder))

    def test_atomic_reservation_replay_and_crash_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gate = t.OfflineDurableGate(root, synthetic_test_only=True)
            self.assertEqual(gate.reserve(0, DIGEST), "upload")
            # Simulated crash after durable reservation, before send.
            another = t.OfflineDurableGate(root, synthetic_test_only=True)
            with self.assertRaises(t.Stop):
                another.reserve(0, DIGEST)
            with self.assertRaises(t.Stop):
                another.reserve(1, DIGEST, PROOF_SHA)
            gate.mark_verified(0, DIGEST, PROOF_SHA)
            with self.assertRaises(t.Stop):
                gate.mark_verified(0, DIGEST, PROOF_SHA)
            self.assertEqual(another.reserve(1, DIGEST, PROOF_SHA), "deploy")
            with self.assertRaises(t.Stop):
                gate.reserve(1, DIGEST, PROOF_SHA)
            with self.assertRaises(t.Stop):
                another.reserve(2, DIGEST, PROOF_SHA)
            another.mark_verified(1, DIGEST, PROOF_SHA)
            for step in range(2, len(t.STEPS)):
                gate.reserve(step, DIGEST, PROOF_SHA)
                gate.mark_verified(step, DIGEST, PROOF_SHA)
            with self.assertRaises(t.Stop):
                gate.reserve(5, DIGEST, PROOF_SHA)
            self.assertEqual(len(list(root.glob("step-*.reserved"))), 6)
            self.assertEqual(len(list(root.glob("step-*.verified"))), 6)

    def test_no_previous_unverified_step_or_wrong_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            gate = t.OfflineDurableGate(Path(folder), synthetic_test_only=True)
            with self.assertRaises(t.Stop):
                gate.reserve(1, DIGEST, PROOF_SHA)
            with self.assertRaises(t.Stop):
                gate.reserve(0, DIGEST, PROOF_SHA)
            gate.reserve(0, DIGEST)
            with self.assertRaises(t.Stop):
                gate.mark_verified(0, "f" * 64, PROOF_SHA)
            gate.mark_verified(0, DIGEST, PROOF_SHA)
            with self.assertRaises(t.Stop):
                gate.reserve(1, DIGEST, "0" * 64)

    def test_untrusted_journal_directory_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            alias = directory / "symlink"
            alias.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(t.Stop):
                t.OfflineDurableGate(alias, synthetic_test_only=True)
            directory.chmod(0o777)
            try:
                with self.assertRaises(t.Stop):
                    t.OfflineDurableGate(directory, synthetic_test_only=True)
            finally:
                directory.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
