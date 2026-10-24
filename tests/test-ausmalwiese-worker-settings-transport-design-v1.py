#!/usr/bin/env python3
"""Offline acceptance tests for the design-only Worker settings GET transport."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "ops/contracts/ausmalwiese-worker-settings-transport-design-v1.json"
ORIGINAL = ROOT / "ops/contracts/ausmalwiese-worker-settings-get-v1.json"
SOURCE = ROOT / "scripts/ausmalwiese_worker_settings_get.py"
spec = importlib.util.spec_from_file_location("aw_settings", SOURCE)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)


class SettingsTransportDesignTests(unittest.TestCase):
    def setUp(self):
        self.design = json.loads(DESIGN.read_text(encoding="utf-8"))
        self.original = json.loads(ORIGINAL.read_text(encoding="utf-8"))

    def test_not_deployed_or_authenticated(self):
        self.assertEqual(self.design["status"], "SOURCE_IMPLEMENTED_NOT_INSTALLED")
        self.assertEqual(self.design["credential_boundary"]["selected_runtime_authenticator"], "DEDICATED_WORKERS_SCRIPTS_READ_TOKEN_NOT_PROVISIONED")
        self.assertTrue(self.design["deployment"]["future_exact_owner_authorization_required"])
        for field in ("runnable_backend_in_this_pr",
                      "installer_in_this_pr", "host_change_in_this_pr",
                      "cloudflare_get_in_this_pr", "source_merge_authorizes_live"):
            self.assertIs(self.design["deployment"][field], False)
        self.assertIs(self.design["deployment"]["credential_reader_in_this_pr"], True)
        self.assertIs(self.design["credential_boundary"]["executor_source_present"], True)
        self.assertIs(self.design["credential_boundary"]["credential_provisioned"], False)

    def test_fixed_cloudflare_target_matches_existing_adapter(self):
        t = self.design["target"]
        self.assertEqual(t["worker"], self.original["worker"])
        self.assertEqual(t["host"], "rpi5")
        self.assertEqual(t["method"], self.original["api"]["method"])
        self.assertEqual(t["api_origin"], "https://api.cloudflare.com")
        self.assertEqual(t["path_template"],
                         "/client/v4" + self.original["api"]["path"])
        self.assertEqual(t["account_id_binding"], "trusted-executor-internal-verified-account")
        self.assertEqual(module.fixed_url("a" * 32),
                         t["api_origin"] + t["path_template"].replace("{trusted_pinned_account_id}", "a" * 32))

    def test_one_get_no_retry_and_fail_closed_network_limits(self):
        e = self.design["request_envelope"]
        self.assertEqual(e["request_limit"], 1)
        self.assertEqual(e["retry_limit"], 0)
        self.assertEqual(e["redirects_followed"], 0)
        self.assertEqual(e["timeout_seconds"], 10)
        self.assertEqual(e["max_response_bytes"], 32768)
        self.assertTrue(e["tls_verification_required"])
        self.assertTrue(e["fixed_operation_only"])
        self.assertEqual(e["accepted_content_type"], "application/json")
        self.assertEqual(self.original["api"]["maximum_requests"], 1)
        self.assertEqual(self.original["api"]["maximum_writes"], 0)

    def test_no_caller_selected_request_parts(self):
        e = self.design["request_envelope"]
        for flag in ("caller_supplied_host", "caller_supplied_account_id",
                     "caller_supplied_path", "caller_supplied_http_method",
                     "caller_supplied_headers"):
            self.assertIs(e[flag], False)

    def test_no_ambient_credentials_or_unreviewed_oauth(self):
        c = self.design["credential_boundary"]
        for flag in ("existing_wrangler_oauth_material_access_approved",
                     "wrangler_config_or_browser_file_access_allowed",
                     "environment_token_dump_allowed", "token_in_argv_or_logs_allowed",
                     "no_authentication_fallback"):
            self.assertIs(c[flag], flag == "no_authentication_fallback")
        self.assertEqual(c["allowed_least_privilege_permission"], "Workers Scripts Read")
        self.assertEqual(c["dedicated_workers_scripts_read_credential"], "FUTURE_SEPARATE_APPROVAL_ONLY")

    def test_no_unsafe_output_fields(self):
        o = self.design["output_boundary"]
        for field in ("upstream_http_body_logged", "exception_details_logged",
                      "destinations_names_logged", "account_id_emitted"):
            self.assertIs(o[field], False)
        self.assertEqual(o["sanitizer_module"], "scripts/ausmalwiese_worker_settings_get.py")
        self.assertEqual(o["sanitizer_function"], "sanitize_settings")
        self.assertEqual(o["missing_values"], "null")
        self.assertEqual(o["rejection_format"], "stable_code_only")

    def test_sanitizer_still_discards_sensitive_fake_payload(self):
        mock_payload = {"success": True, "result": {
            "logpush": False, "secret": "HIDDEN_TOKEN_NOT_FOR_OUTPUT",
            "observability": {"enabled": True, "logs": {
                "enabled": True, "destinations": ["private-name"]}}}}
        output = module.sanitize_settings(mock_payload)
        text = json.dumps(output, sort_keys=True)
        self.assertNotIn("HIDDEN_TOKEN_NOT_FOR_OUTPUT", text)
        self.assertNotIn("private-name", text)
        self.assertEqual(output["observability"]["logs"]["destination_count"], 1)

    def test_no_standalone_network_or_authentication_code(self):
        text = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("import requests", "import urllib", "import subprocess",
                          "os.environ", "CLOUDFLARE_API_TOKEN", "open('/",
                          "shutil", "aiohttp", "httpx"):
            self.assertNotIn(forbidden, text)
        self.assertIn("SOURCE_ONLY", text)
        self.assertIn("def collect_once", text)

    def test_explicit_separate_future_owner_gates(self):
        gates = self.design["future_gates"]
        self.assertGreaterEqual(len(gates), 5)
        self.assertTrue(any("owner-authorize-credential" in g for g in gates))
        self.assertTrue(any("owner-authorize-one-script" in g for g in gates))
        self.assertTrue(any("without-retry" in g for g in gates))


if __name__ == "__main__":
    unittest.main()
