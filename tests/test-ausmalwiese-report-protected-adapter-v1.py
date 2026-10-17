#!/usr/bin/env python3
"""Offline contract/adapter/installer regressions: no Cloudflare, credentials or LIVE."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: str):
    source = ROOT / path
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load("ausmalwiese_report_protected_adapter", "scripts/ausmalwiese_report_protected_adapter.py")
installer = load("ausmalwiese_report_protected_installer", "scripts/ausmalwiese_report_protected_installer.py")
ACCOUNT = "a" * 32
ZONE = "b" * 32
V1 = "11111111-2222-3333-4444-555555555555"
V2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def bound_request(operation: str, **kwargs):
    with patch.object(adapter, "ACCOUNT_SHA256", hashlib.sha256(ACCOUNT.encode()).hexdigest()):
        return adapter.request_spec(operation, ACCOUNT, ZONE, **kwargs)


def good_reply(kind: str, route: str | None = None):
    if kind == "upload":
        record = {"id": V1}
    elif kind == "deploy":
        record = {"id": V2}
    else:
        record = {"id": "c" * 32, "pattern": route, "script": adapter.WORKER}
    return {"success": True, "errors": [], "messages": [], "result": record}


def install_metadata(plan):
    paths = {
        installer.INSTALL_ROOT: {
            "kind": "directory", "uid": 0, "gid": 0,
            "mode": 0o755, "nlink": 2, "sha256": None,
        },
        installer.ENTRYPOINT: {
            "kind": "file", "uid": 0, "gid": 0,
            "mode": 0o755, "nlink": 1, "sha256": None,
        },
    }
    for f in plan["files"]:
        paths[f["path"]] = {
            "kind": "file", "uid": 0, "gid": 0,
            "mode": 0o644, "nlink": 1, "sha256": f["sha256"],
        }
    parents = {
        x: {"kind": "directory", "uid": 0, "gid": 0,
            "mode": 0o755, "symlink": False}
        for x in ("/", "/usr", "/usr/local", "/usr/local/libexec", "/usr/local/sbin")
    }
    return {"parent_chain": parents, "paths": paths}


class AdapterTests(unittest.TestCase):
    def test_contract_is_pinned_and_source_only(self):
        import json
        c = json.loads(adapter.CONTRACT.read_text(encoding="utf-8"))
        adapter.check_contract(c)
        self.assertEqual(set(c["bindings"]), set(adapter.KINDS))
        self.assertEqual(len(c["bindings"]), 6)
        self.assertEqual(len(c["routes"]), 4)
        for key in ("allow_live", "allow_merge", "allow_install", "allow_retry",
                    "allow_rollback", "allow_cleanup", "allow_credential_access",
                    "allow_network_from_checkout", "allow_legacy_script_put"):
            self.assertFalse(c["boundaries"][key])
        self.assertFalse(c["installer"]["only_dry_run_source"] is False)

    def test_contract_drift_rejected(self):
        variants = [
            lambda c: c["target"].update(worker="coloring-pages-stats-v1"),
            lambda c: c["target"].update(zone="another.example"),
            lambda c: c["bindings"].update(OTHER="secret_text"),
            lambda c: c["bindings"].update(REPORT_TO="plain_text"),
            lambda c: c["routes"].append("ausmalwiese.de/*"),
            lambda c: c["methods"].update(upload="PUT"),
            lambda c: c["api_paths"].update(upload="/client/v4/accounts/{account_id}/workers/scripts/coloring-pages-stats-v1"),
            lambda c: c["boundaries"].update(allow_live=True),
            lambda c: c["boundaries"].update(allow_retry=True),
        ]
        for modify in variants:
            value = copy.deepcopy(adapter.expected_contract())
            modify(value)
            with self.assertRaises(adapter.Stop):
                adapter.check_contract(value)

    def test_source_provenance_rejects_wrong_file(self):
        for raw in (None, "text", b"", b"fake source", b"fake" * 60000):
            with self.assertRaises(adapter.Stop):
                adapter.verify_worker_bytes(raw)

    def test_api_blueprint_is_exact_and_credential_free(self):
        upload = bound_request("upload")
        deploy = bound_request("deploy", version_id=V1)
        self.assertEqual(upload["method"], "POST")
        self.assertTrue(upload["path"].endswith("/coloring-pages-report-v1/versions"))
        self.assertEqual(upload["body_policy"], "SEALED_MULTIPART_PRIVATE_PROVISIONER_REQUIRED")
        self.assertIsNone(upload["body"])
        self.assertEqual(deploy["body"], {
            "strategy": "percentage",
            "versions": [{"version_id": V1, "percentage": 100}],
        })
        for route in adapter.ROUTES:
            spec = bound_request("add_route", route=route)
            self.assertEqual(spec["method"], "POST")
            self.assertEqual(spec["body"], {"pattern": route, "script": adapter.WORKER})
            self.assertTrue(spec["path"].endswith("/workers/routes"))
        for spec in [upload, deploy, *[bound_request("add_route", route=r) for r in adapter.ROUTES]]:
            self.assertNotIn("Bearer", repr(spec))
            self.assertNotIn("secret", repr(spec).lower())
            self.assertNotIn("/workers/scripts/coloring-pages-stats-v1/", spec["path"])

    def test_wrong_account_zone_and_unsupported_operations(self):
        with self.assertRaises(adapter.Stop):
            adapter.request_spec("upload", ACCOUNT, ZONE)
        for bad_id in ("BAD", "z" * 32, "../" + "a" * 29, "a" * 31):
            with self.assertRaises(adapter.Stop):
                with patch.object(adapter, "ACCOUNT_SHA256", hashlib.sha256(ACCOUNT.encode()).hexdigest()):
                    adapter.request_spec("add_route", ACCOUNT, bad_id, route=adapter.ROUTES[0])
        for operation in ("put_script", "delete_route", "delete_worker", "retry", "get_secrets"):
            with self.assertRaises(adapter.Stop):
                bound_request(operation)

    def test_wildcard_and_unrelated_route_rejected(self):
        for route in ("ausmalwiese.de/api/report*", "ausmalwiese.de/api/stats/*",
                      "ausmalwiese.de/*", "www.example.org/api/report",
                      "ausmalwiese.de/api/report?x=1"):
            with self.assertRaises(adapter.Stop):
                bound_request("add_route", route=route)
        with self.assertRaises(adapter.Stop):
            bound_request("upload", route=adapter.ROUTES[0])
        with self.assertRaises(adapter.Stop):
            bound_request("deploy", version_id="latest")

    def test_six_binding_names_and_two_rate_namespaces(self):
        adapter.validate_namespaces(dict(adapter.KINDS), copy.deepcopy(adapter.LIMITS), {
            "REPORT_RATE": "1001", "REPORT_DUP": "1002"})
        cases = [
            {"REPORT_RATE": "1001", "REPORT_DUP": "1001"},
            {"REPORT_RATE": "01", "REPORT_DUP": "1002"},
            {"REPORT_RATE": "0", "REPORT_DUP": "1002"},
            {"REPORT_RATE": 1001, "REPORT_DUP": "1002"},
            {"REPORT_RATE": "4294967296", "REPORT_DUP": "1002"},
            {"REPORT_RATE": "1001", "REPORT_DUP": "1002", "EXTRA": "1003"},
        ]
        for n in cases:
            with self.assertRaises(adapter.Stop):
                adapter.validate_namespaces(adapter.KINDS, adapter.LIMITS, n)
        bad = dict(adapter.KINDS)
        bad["BREVO_API_KEY"] = "plain_text"
        with self.assertRaises(adapter.Stop):
            adapter.validate_namespaces(bad, adapter.LIMITS, {"REPORT_RATE": "1001", "REPORT_DUP": "1002"})
        rates = copy.deepcopy(adapter.LIMITS)
        rates["REPORT_DUP"]["limit"] = 12
        with self.assertRaises(adapter.Stop):
            adapter.validate_namespaces(adapter.KINDS, rates, {"REPORT_RATE": "1001", "REPORT_DUP": "1002"})

    def test_reply_sanitizer_accepts_only_exact_schema(self):
        self.assertEqual(adapter.validate_response("upload", good_reply("upload")), {"version_id": V1})
        self.assertEqual(adapter.validate_response("deploy", good_reply("deploy")), {"deployment_id": V2})
        route = adapter.ROUTES[0]
        self.assertEqual(adapter.validate_response("add_route", good_reply("add_route", route), route=route),
                         {"route": route, "worker": adapter.WORKER})
        cases = [
            ("upload", dict(good_reply("upload"), secret="test")),
            ("upload", dict(good_reply("upload"), success=False)),
            ("upload", dict(good_reply("upload"), errors=[{"code": 1000}])),
            ("upload", dict(good_reply("upload"), result={"id": "wrong"})),
            ("deploy", dict(good_reply("deploy"), result={"id": "invalid"})),
            ("add_route", dict(good_reply("add_route", route), result={"id": "c" * 32, "pattern": route, "script": "coloring-pages-stats-v1"})),
        ]
        for operation, reply in cases:
            with self.assertRaises(adapter.Stop):
                adapter.validate_response(operation, reply, route=route)

    def test_single_dispatch_ledger_no_double_send_or_reorder(self):
        l = adapter.SingleDispatchLedger()
        with self.assertRaises(adapter.Stop):
            l.reserve("deploy")
        l.reserve("upload")
        with self.assertRaises(adapter.Stop):
            l.reserve("upload")
        l.reserve("deploy")
        for route in adapter.ROUTES:
            l.reserve("add_route", route)
        with self.assertRaises(adapter.Stop):
            l.reserve("add_route", adapter.ROUTES[0])
        l.freeze()
        with self.assertRaises(adapter.Stop):
            l.reserve("upload")

    def test_cli_is_check_only(self):
        for path in (adapter.__file__, installer.__file__):
            result = subprocess.run([sys.executable, path, "--check-contract"], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("NOT_", result.stdout)
            for flag in ("--apply", "--install", "--deploy", "--retry", "--set-token"):
                bad = subprocess.run([sys.executable, path, flag], capture_output=True, text=True, timeout=10)
                self.assertEqual(bad.returncode, 2)
                self.assertTrue(bad.stdout.startswith("STOP_REPORT_"))


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter_raw = adapter.__file__ and Path(adapter.__file__).read_bytes()
        cls.contract_raw = adapter.CONTRACT.read_bytes()

    def plan(self):
        return installer.install_plan(self.adapter_raw, self.contract_raw)

    def test_installer_plan_pins_exact_blobs(self):
        plan = self.plan()
        self.assertEqual(plan["target"], adapter.WORKER)
        self.assertEqual(len(plan["files"]), 2)
        self.assertEqual({f["path"] for f in plan["files"]}, {
            installer.INSTALL_ROOT + "/adapter.py",
            installer.INSTALL_ROOT + "/contract.json"})
        self.assertFalse(plan["may_install_from_repository_checkout"])
        self.assertTrue(plan["requires_separate_authenticated_owner_install_gate"])

    def test_unpinned_source_and_wrong_role_denied(self):
        with self.assertRaises(installer.Stop):
            installer.install_plan(self.adapter_raw + b"\n", self.contract_raw)
        with self.assertRaises(installer.Stop):
            installer.install_plan(self.adapter_raw, self.contract_raw + b"\n")
        with self.assertRaises(installer.Stop):
            installer.verify_source_file(b"source", "secrets")

    def test_install_metadata_root_only(self):
        plan = self.plan()
        metadata = install_metadata(plan)
        installer.verify_install_metadata(metadata, plan)
        mutated = copy.deepcopy(metadata)
        mutated["paths"][installer.ENTRYPOINT]["uid"] = 1000
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(mutated, plan)
        mutated = copy.deepcopy(metadata)
        mutated["paths"][installer.INSTALL_ROOT]["mode"] = 0o777
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(mutated, plan)
        mutated = copy.deepcopy(metadata)
        mutated["paths"][plan["files"][0]["path"]]["sha256"] = "0" * 64
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(mutated, plan)

    def test_parent_symlink_or_untrusted_mode_denied(self):
        plan = self.plan()
        meta = install_metadata(plan)
        meta["parent_chain"]["/usr/local"]["symlink"] = True
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(meta, plan)
        meta = install_metadata(plan)
        meta["parent_chain"]["/usr/local"]["mode"] = 0o777
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(meta, plan)
        meta = install_metadata(plan)
        meta["paths"]["/tmp/unexpected"] = meta["paths"][installer.ENTRYPOINT]
        with self.assertRaises(installer.Stop):
            installer.verify_install_metadata(meta, plan)


if __name__ == "__main__":
    unittest.main()
