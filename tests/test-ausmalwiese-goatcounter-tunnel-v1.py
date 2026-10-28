#!/usr/bin/env python3
"""Disconnected route and write-budget regressions. No credentials or network."""
from copy import deepcopy
import importlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
m = importlib.import_module("ausmalwiese_goatcounter_tunnel_v1")
ACCOUNT = "a" * 32
TUNNEL = "00000000-0000-4000-8000-000000000001"


def config():
    return {"originRequest": {}, "warp-routing": {"enabled": False}, "ingress": [
        {"hostname": "other.example", "service": "http://localhost:8000"},
        {"hostname": m.HOSTS[0], "service": "http://127.0.0.1:8088", "originRequest": {"connectTimeout": 8}},
        {"hostname": m.HOSTS[1], "service": "http://127.0.0.1:8088"},
        {"service": "http_status:404"},
    ]}


class Fake:
    def __init__(self):
        self.config = config()
        self.version = 7
        self.calls = []
        self.fail_write = False
        self.fail_post = False
        self.drift = False
        self.bad_post = False
        self.wrote = False
        self.config_reads = 0

    def _request(self, method, path, body=None):
        self.calls.append((method, path, deepcopy(body)))
        if method == "PUT":
            self.wrote = True
            self.config = deepcopy(body["config"])
            self.version += 1
            if self.fail_write:
                raise TimeoutError("sensitive provider error")
            return {"success": True}
        if "?name=" in path:
            return {"result": [{"id": TUNNEL, "name": "rpi5-tunnel", "config_src": "cloudflare"}]}
        self.config_reads += 1
        if self.wrote and self.fail_post:
            raise ValueError("sensitive post-write error")
        observed = deepcopy(self.config)
        if (self.drift and self.config_reads == 2) or (self.bad_post and self.wrote):
            observed["warp-routing"]["enabled"] = True
        return {"result": {"config": observed, "version": self.version}}

    def baseline(self):
        return m.digest({"tunnel_id": TUNNEL, "version": self.version, "config": self.config})


class Routes(unittest.TestCase):
    def test_preserves_every_original_field_and_order(self):
        original = config()
        before = deepcopy(original)
        desired, changed = m.prepare(original)
        self.assertTrue(changed)
        self.assertEqual(original, before)
        filtered = [r for r in desired["ingress"] if r not in [m.entry(h) for h in m.HOSTS]]
        self.assertEqual(filtered, original["ingress"])
        self.assertEqual(desired["warp-routing"], original["warp-routing"])
        for host in m.HOSTS:
            entries = [r for r in desired["ingress"] if r.get("hostname") == host]
            self.assertEqual(entries[0], m.entry(host))
            self.assertNotIn("path", entries[1])

    def test_exact_existing_state_is_read_only_noop(self):
        desired, _ = m.prepare(config())
        self.assertEqual(m.prepare(desired), (desired, False))

    def test_partial_state_rejected(self):
        c = config(); c["ingress"].insert(1, m.entry(m.HOSTS[0]))
        with self.assertRaises(m.OperatorError): m.prepare(c)

    def test_conflicting_path_or_host_header_rejected(self):
        for change in ({"path": "/api/.*"}, {"originRequest": {"httpHostHeader": "other.example"}}, {"service": "http://127.0.0.1:9194"}):
            c = config(); r = m.entry(m.HOSTS[0]); r.update(change); c["ingress"].insert(1, r)
            with self.subTest(change=change), self.assertRaises(m.OperatorError): m.prepare(c)

    def test_shadowed_route_rejected(self):
        c, _ = m.prepare(config()); rule = c["ingress"].pop(1); c["ingress"].insert(-1, rule)
        with self.assertRaises(m.OperatorError): m.prepare(c)

    def test_duplicate_fallback_rejected(self):
        c = config(); c["ingress"].insert(1, deepcopy(c["ingress"][1]))
        with self.assertRaises(m.OperatorError): m.prepare(c)

    def test_matching_wildcard_and_early_catchall_rejected(self):
        for host in ("*.ausmalwiese.de", "*", "", None, "AUSMALWIESE.DE", "ausmalwiese.de."):
            c = config(); c["ingress"].insert(0, {"hostname": host, "service": "http_status:403"})
            with self.subTest(host=host), self.assertRaises(m.OperatorError): m.prepare(c)

    def test_global_origin_settings_rejected(self):
        for settings in ({"httpHostHeader": "other.example"}, {"access": {"required": True}}, None):
            c = config(); c["originRequest"] = settings
            with self.assertRaises(m.OperatorError): m.prepare(c)

    def test_unsafe_fallback_rejected(self):
        for service in (m.SERVICE, "http://localhost:9194", "http://127.0.0.1:9194", "http://external.example:80", "http://localhost:99999"):
            c = config(); c["ingress"][1]["service"] = service
            with self.assertRaises(m.OperatorError): m.prepare(c)

    def test_catchall_must_be_exact_404(self):
        c = config(); c["ingress"][-1] = {"service": "http://127.0.0.1:9194"}
        with self.assertRaises(m.OperatorError): m.prepare(c)


class Transaction(unittest.TestCase):
    def test_read_only_reports_no_raw_config(self):
        f = Fake(); r = m.run(f, ACCOUNT)
        self.assertEqual([v[0] for v in f.calls], ["GET", "GET"])
        self.assertFalse(r["public_readiness_verified"])
        self.assertNotIn(TUNNEL, json.dumps(r)); self.assertNotIn("other.example", json.dumps(r))

    def test_one_put_preserves_config_and_verifies(self):
        f = Fake(); r = m.run(f, ACCOUNT, apply=True, expected_baseline=f.baseline())
        self.assertEqual([v[0] for v in f.calls], ["GET", "GET", "GET", "PUT", "GET"])
        self.assertTrue(r["mutation_verified"])
        self.assertEqual(f.calls[3][2], {"config": m.prepare(config())[0]})

    def test_stale_baseline_no_write(self):
        f = Fake()
        with self.assertRaises(m.OperatorError): m.run(f, ACCOUNT, apply=True, expected_baseline="0" * 64)
        self.assertFalse(f.wrote)

    def test_drift_no_write(self):
        f = Fake(); f.drift = True
        with self.assertRaises(m.OperatorError): m.run(f, ACCOUNT, apply=True, expected_baseline=f.baseline())
        self.assertFalse(f.wrote)

    def test_uncertain_write_never_retried_or_rolled_back(self):
        f = Fake(); f.fail_write = True
        with self.assertRaises(m.PostDispatchError): m.run(f, ACCOUNT, apply=True, expected_baseline=f.baseline())
        self.assertEqual([v[0] for v in f.calls], ["GET", "GET", "GET", "PUT"])

    def test_postcheck_failure_no_recovery(self):
        for attr in ("fail_post", "bad_post"):
            f = Fake(); setattr(f, attr, True)
            with self.assertRaises(m.PostDispatchError): m.run(f, ACCOUNT, apply=True, expected_baseline=f.baseline())
            self.assertEqual(sum(v[0] == "PUT" for v in f.calls), 1)

    def test_already_present_no_write(self):
        f = Fake(); f.config, _ = m.prepare(f.config)
        self.assertFalse(m.run(f, ACCOUNT, apply=True, expected_baseline=f.baseline())["write_attempted"])
        self.assertFalse(f.wrote)

    def test_missing_gates_do_not_load_credentials(self):
        for args in (["--confirm-read", "wrong"], ["--confirm-read", m.READ_CONFIRM, "--apply"]):
            with patch.object(m.os, "geteuid", return_value=0), patch.object(m, "load_tunnel_credentials") as loader, redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(args), 2); loader.assert_not_called()

    def test_errors_are_sanitized(self):
        for error, code, attempted in ((ValueError("SECRET"), 3, False), (m.PostDispatchError("SECRET"), 4, True)):
            output = io.StringIO()
            with patch.object(m.os, "geteuid", return_value=0), patch.object(m, "ACCOUNT_SHA256", m.hashlib.sha256(ACCOUNT.encode()).hexdigest()), patch.object(m, "load_tunnel_credentials", return_value=(ACCOUNT, "x" * 24)), patch.object(m.CloudflareClient, "verify_active_account_token"), patch.object(m, "run", side_effect=error), redirect_stdout(output):
                self.assertEqual(m.main(["--confirm-read", m.READ_CONFIRM]), code)
            self.assertNotIn("SECRET", output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["write_attempted"], attempted)

    def test_wrong_account_never_calls_api(self):
        with patch.object(m.os, "geteuid", return_value=0), patch.object(m, "load_tunnel_credentials", return_value=(ACCOUNT, "x" * 24)), patch.object(m, "CloudflareClient") as client, redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(["--confirm-read", m.READ_CONFIRM]), 3)
            client.assert_not_called()

    def test_invalid_config_version_rejected(self):
        for version in (None, True, -1, "7"):
            with patch.object(Fake, "_request", return_value={"result": {"config": config(), "version": version}}):
                with self.assertRaises(m.OperatorError): m.read_config(Fake(), ACCOUNT, TUNNEL)


if __name__ == "__main__":
    unittest.main()
