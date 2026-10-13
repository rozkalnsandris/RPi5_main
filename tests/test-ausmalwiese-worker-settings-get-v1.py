#!/usr/bin/env python3
"""Offline no-network tests for the fixed Cloudflare Worker-settings sanitizer."""

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_worker_settings_get.py"
CONTRACT = ROOT / "ops/contracts/ausmalwiese-worker-settings-get-v1.json"
spec = importlib.util.spec_from_file_location("ausmalwiese_settings", SOURCE)
mod = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(mod)

ACCOUNT = "a" * 32


def fixture():
    return {"success": True, "result": {"logpush": False,
        "tags": ["private-tag"], "tail_consumers": [{"service": "do-not-log"}],
        "secret": "DONT_ECHO_SECRET", "observability": {
            "enabled": True, "head_sampling_rate": 0.75,
            "logs": {"enabled": True, "invocation_logs": False, "persist": True,
                     "redact_query_string": True, "head_sampling_rate": 0.25,
                     "destinations": ["secret-destination", "another-private-name"]},
            "traces": {"enabled": False, "persist": False, "head_sampling_rate": 0,
                       "destinations": ["trace-private-name"]}}}}


class WorkerSettingsTests(unittest.TestCase):
    def test_source_only_contract(self):
        cfg = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(cfg["status"], "SOURCE_ONLY_NO_TRUSTED_RUNTIME_BACKEND")
        self.assertEqual(cfg["worker"], mod.WORKER_NAME)
        self.assertEqual(cfg["api"]["method"], "GET")
        self.assertEqual(cfg["api"]["maximum_requests"], 1)
        self.assertEqual(cfg["api"]["maximum_writes"], 0)
        self.assertFalse(cfg["authorization"]["credential_access_in_source_work"])
        self.assertTrue(cfg["authorization"]["runtime_requires_separate_owner_gate"])

    def test_fixed_target_and_one_call(self):
        calls = []
        def get(url):
            calls.append(url)
            return fixture()
        got = mod.collect_once(trusted_account_id=ACCOUNT, trusted_get=get)
        self.assertEqual(calls, [f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/scripts/coloring-pages-stats-v1/script-settings"])
        self.assertTrue(got["verified_get"])
        self.assertIs(got["logpush"], False)
        self.assertEqual(got["observability"]["logs"]["destination_count"], 2)
        self.assertEqual(got["observability"]["traces"]["destination_count"], 1)
        self.assertEqual(got["observability"]["logs"]["head_sampling_rate"], 0.25)

    def test_secrets_and_names_never_in_sanitized_output(self):
        text = json.dumps(mod.sanitize_settings(fixture()))
        for forbidden in ("DONT_ECHO_SECRET", "do-not-log", "private-tag",
                          "secret-destination", "another-private-name",
                          "trace-private-name", ACCOUNT):
            self.assertNotIn(forbidden, text)

    def test_absence_does_not_mean_false(self):
        got = mod.sanitize_settings({"success": True, "result": {}})
        self.assertIsNone(got["logpush"])
        self.assertIsNone(got["observability"]["enabled"])
        self.assertIsNone(got["observability"]["logs"]["persist"])
        self.assertIsNone(got["observability"]["traces"]["head_sampling_rate"])

    def test_refuse_unpinned_account_id_without_call(self):
        calls = []
        for bad in ("", "A"*32, "ab"*15, "../secrets", "b"*33, None):
            with self.subTest(bad=bad), self.assertRaises(mod.ReviewStop):
                mod.collect_once(trusted_account_id=bad, trusted_get=lambda url: calls.append(url))
        self.assertEqual(calls, [])

    def test_api_errors_never_echo_upstream_body(self):
        for payload in ({"success": False, "errors": [{"message": "private-secret"}]},
                        {"success": True, "result": {}, "errors": ["private-secret"]},
                        {"success": True, "result": "private-secret"},
                        ["private-secret"], None):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(mod.ReviewStop) as caught:
                mod.sanitize_settings(payload)
            self.assertNotIn("private-secret", str(caught.exception))

    def test_injected_transport_failure_no_retry(self):
        calls = []
        def failed(url):
            calls.append(url)
            raise RuntimeError("SECRET IN ORIGINAL ERROR")
        with self.assertRaises(mod.ReviewStop) as caught:
            mod.collect_once(trusted_account_id=ACCOUNT, trusted_get=failed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(str(caught.exception), "trusted_get_failed")
        self.assertNotIn("SECRET", str(caught.exception))

    def test_invalid_types_and_rates_fail_closed(self):
        for value in ("true", 1, [], {}):
            with self.subTest(value=value), self.assertRaises(mod.ReviewStop):
                mod.sanitize_settings({"success": True, "result": {"logpush": value}})
        for value in (-0.1, 1.1, True, "1", float("nan"), float("inf")):
            with self.subTest(rate=value), self.assertRaises(mod.ReviewStop):
                mod.sanitize_settings({"success": True, "result": {"observability": {"logs": {"head_sampling_rate": value}}}})

    def test_unexpected_destination_shape_fails_closed(self):
        for val in ("private", [42], ["x"]*129):
            with self.subTest(val=type(val).__name__), self.assertRaises(mod.ReviewStop):
                mod.sanitize_settings({"success": True, "result": {"observability": {"logs": {"destinations": val}}}})

    def test_no_transport_fails_before_get(self):
        with self.assertRaises(mod.ReviewStop):
            mod.collect_once(trusted_account_id=ACCOUNT, trusted_get=None)


if __name__ == "__main__":
    unittest.main()
