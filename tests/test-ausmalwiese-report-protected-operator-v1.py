#!/usr/bin/env python3
"""Offline-only negative report protected operator SOURCE tests (#1044)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ausmalwiese_report_protected_operator_v1 as o
import ausmalwiese_report_trusted_transport as t

ACCOUNT = "a" * 32
ZONE = "b" * 32
VERSION = "11111111-2222-3333-4444-555555555555"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def layout_for(plan):
    ancestors = {
        path: {"kind": "directory", "uid": 0, "gid": 0,
               "mode": 0o755, "symlink": False}
        for path in ("/", "/usr", "/usr/local",
                     "/usr/local/libexec", "/usr/local/sbin")
    }
    nodes = {}
    for name, kind, mode, sha in [
        (o.INSTALL_ROOT, "directory", 0o755, None),
        (o.LAUNCHER, "file", 0o755, None),
    ]:
        nodes[name] = {"kind": kind, "uid": 0, "gid": 0,
                       "mode": mode, "nlink": 2 if kind == "directory" else 1,
                       "symlink": False, "sha256": sha}
    for item in plan["files"]:
        nodes[item["path"]] = {
            "kind": "file", "uid": 0, "gid": 0,
            "mode": int(item["mode"], 8), "nlink": 1,
            "symlink": False, "sha256": item["sha256"],
        }
    return {"ancestors": ancestors, "nodes": nodes}


class OperatorTests(unittest.TestCase):
    def test_strict_contract_and_cli(self):
        o.check_contract(json.loads(o.CONTRACT.read_text(encoding="utf8")))
        self.assertEqual(len(o.expected_contract()["steps"]), 6)
        self.assertEqual(len(o.expected_contract()["binding_kinds"]), 6)
        for change in [
            lambda x: x["routes"].append("ausmalwiese.de/api/stats/*"),
            lambda x: x["rules"].update(may_live=True),
            lambda x: x["rules"].update(may_read_credentials=True),
            lambda x: x.update(worker="coloring-pages-stats-v1"),
            lambda x: x.update(steps=["upload", "retry"]),
        ]:
            obj = copy.deepcopy(o.expected_contract())
            change(obj)
            with self.assertRaises(o.Stop):
                o.check_contract(obj)
        script = ROOT / "scripts/ausmalwiese_report_protected_operator_v1.py"
        ok = subprocess.run([sys.executable, str(script), "--check-contract"],
                            capture_output=True, text=True, timeout=10)
        self.assertEqual((ok.returncode, ok.stdout.strip()),
                         (0, "REPORT_PROTECTED_OPERATOR_SOURCE_OK_NOT_INSTALLED"))
        for option in ("--apply", "--send", "--install", "--secrets",
                       "--cloudflare", "--retry"):
            denied = subprocess.run([sys.executable, str(script), option],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual((denied.returncode, denied.stdout.strip()),
                             (2, o.STOP))

    def test_pinned_source_bytes_fail_closed(self):
        for invalid in (None, "", b"", b"fake-worker-source", b"x" * 120001):
            with self.assertRaises(o.Stop):
                o.verify_worker_bytes(invalid)

    def test_install_release_layout_is_shape_only(self):
        hashes = {name: SHA_A for name in o.FILES}
        plan = o.installation_plan(hashes)
        self.assertFalse(plan["may_install"])
        self.assertEqual(o.validate_install_layout(layout_for(plan), plan),
                         "SANITIZED_INSTALL_SHAPE_ONLY_NOT_AUTHORITY")
        for invalid in ({}, {"extra": SHA_A}, {**hashes, "adapter.py": "bad"}):
            with self.assertRaises(o.Stop):
                o.installation_plan(invalid)
        def bad(change):
            evidence = layout_for(plan)
            change(evidence)
            with self.assertRaises(o.Stop):
                o.validate_install_layout(evidence, plan)
        bad(lambda x: x["ancestors"]["/usr"].update(mode=0o777))
        bad(lambda x: x["ancestors"]["/usr"].update(symlink=True))
        bad(lambda x: x["nodes"][o.LAUNCHER].update(uid=1000))
        bad(lambda x: x["nodes"][o.LAUNCHER].update(nlink=2))
        bad(lambda x: x["nodes"][o.INSTALL_ROOT + "/operator.py"].update(sha256=SHA_B))
        bad(lambda x: x["nodes"][o.INSTALL_ROOT + "/transport.py"].update(symlink=True))

    def test_https_intent_pinned_no_dispatch(self):
        with patch.object(t, "ACCOUNT_FINGERPRINT",
                          hashlib.sha256(ACCOUNT.encode()).hexdigest()):
            upload = o.https_intent("upload", ACCOUNT, ZONE)
            self.assertEqual(upload["state"], "NOT_DISPATCHABLE_SOURCE_INTENT")
            self.assertEqual(upload["tls_hostname"], "api.cloudflare.com")
            self.assertEqual(upload["authorization"],
                             "FUTURE_INSTALLED_PRIVATE_PROVIDER_REQUIRED")
            self.assertIsNone(upload["request"]["body"])
            self.assertEqual(upload["request"]["retries"], 0)
            self.assertFalse(upload["request"]["redirects"])
            for route in t.ROUTES:
                obj = o.https_intent("route", ACCOUNT, ZONE, route=route)
                self.assertEqual(obj["request"]["body"]["pattern"], route)
            obj = o.https_intent("deploy", ACCOUNT, ZONE, version=VERSION)
            self.assertEqual(obj["request"]["body"]["versions"][0]["percentage"], 100)
            for operation, kwargs in [
                ("delete", {}), ("route", {"route": "ausmalwiese.de/*"}),
                ("route", {"route": "ausmalwiese.de/api/report?x=1"}),
                ("upload", {"version": VERSION}), ("deploy", {"version": "latest"}),
            ]:
                with self.assertRaises(t.Stop):
                    o.https_intent(operation, ACCOUNT, ZONE, **kwargs)
        with self.assertRaises(t.Stop):
            o.https_intent("upload", ACCOUNT, ZONE)

    def test_synthetic_six_step_replay_and_crash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gate = t.OfflineDurableGate(root, synthetic_test_only=True)
            env0 = o.immutable_step(0, SHA_A, SHA_B)
            self.assertEqual(o.synthetic_reserve(gate, 0, env0), "upload")
            after_crash = t.OfflineDurableGate(root, synthetic_test_only=True)
            with self.assertRaises(t.Stop):
                o.synthetic_reserve(after_crash, 0, env0)
            with self.assertRaises(t.Stop):
                o.synthetic_reserve(after_crash, 1,
                                    o.immutable_step(1, SHA_A, SHA_B, SHA_C), SHA_C)
            gate.mark_verified(0, env0["sha256"], SHA_C)
            for step in range(1, 6):
                env = o.immutable_step(step, SHA_A, SHA_B, SHA_C)
                self.assertEqual(o.synthetic_reserve(after_crash, step, env, SHA_C),
                                 t.STEPS[step])
                after_crash.mark_verified(step, env["sha256"], SHA_C)
            self.assertEqual(len(list(root.glob("*.reserved"))), 6)
            with self.assertRaises(t.Stop):
                o.synthetic_reserve(gate, 5,
                                    o.immutable_step(5, SHA_A, SHA_B, SHA_C), SHA_C)
        for step, gate, baseline, prior in [
            (6, SHA_A, SHA_B, SHA_C),
            (0, "wrong", SHA_B, None),
            (0, SHA_A, SHA_B, SHA_C),
            (1, SHA_A, SHA_B, None),
        ]:
            with self.assertRaises(o.Stop):
                o.immutable_step(step, gate, baseline, prior)
        self.assertNotEqual(o.immutable_step(0, SHA_A, SHA_B)["sha256"],
                            o.immutable_step(0, SHA_C, SHA_B)["sha256"])

    def test_shape_never_claims_live_proof(self):
        with self.assertRaises(t.Stop):
            o.check_provisioning_shape({"private_provider_ready": True})
        with self.assertRaises(t.Stop):
            o.check_version_shape({"collector": "fake"}, VERSION, SHA_A)
        self.assertNotIn("LIVE", o.immutable_step(0, SHA_A, SHA_B)["state"])


if __name__ == "__main__":
    unittest.main()
