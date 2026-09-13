#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_browser_sso_preflight as preflight  # noqa: E402

OWNER = "owner@example.com"
DASH_APP = "22222222-2222-4222-8222-222222222222"


def base_state() -> dict:
    return {
        "organization": {"auth_domain": "private.cloudflareaccess.com", "session_duration": "24h"},
        "apps": [{
            "id": DASH_APP,
            "type": "self_hosted",
            "name": "RPi5 Dashboard",
            "domain": "dash.rozkalns.net",
            "session_duration": "24h",
            "allow_authenticate_via_warp": False,
        }],
        "policies": {DASH_APP: [{
            "decision": "allow",
            "precedence": 1,
            "include": [{"email": {"email": OWNER}}],
            "require": [],
            "exclude": [],
            "session_duration": "24h",
        }]},
    }


class CloudflareOwnerBrowserSSOPreflightTests(unittest.TestCase):
    def test_happy_preflight_routes_to_global_session_change(self) -> None:
        report = preflight.build_report(OWNER, base_state())
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(report["dashboard"]["owner_only_allow"])
        self.assertEqual(report["dashboard"]["application_session_duration"], "24h")
        self.assertEqual(report["dashboard"]["policy_session_durations"], ["24h"])
        self.assertTrue(report["global_session"]["change_required"])
        self.assertEqual(report["remaining_gates"], ["p1d-04-global-browser-sso-session"])

    def test_already_720h_routes_directly_to_browser_canary(self) -> None:
        state = base_state()
        state["organization"]["session_duration"] = "720h"
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["global_session"]["change_required"])
        self.assertEqual(report["remaining_gates"], ["p1d-05-a55-browser-sso-canary"])

    def test_bypass_or_broad_selector_blocks(self) -> None:
        state = base_state()
        state["policies"][DASH_APP] = [{
            "decision": "bypass",
            "precedence": 1,
            "include": [{"everyone": {}}],
            "require": [],
            "exclude": [],
        }]
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("dashboard_bypass_present", report["blockers"])
        self.assertIn("dashboard_broad_or_nonhuman_selector_present", report["blockers"])

    def test_wrong_owner_or_nonexact_dashboard_blocks(self) -> None:
        state = base_state()
        state["policies"][DASH_APP][0]["include"] = [{"email": {"email": "other@example.com"}}]
        self.assertIn("dashboard_exact_owner_allow_policy_not_proven", preflight.build_report(OWNER, state)["blockers"])
        state = base_state()
        state["apps"][0]["domain"] = "*.rozkalns.net"
        self.assertIn("dashboard_exact_access_application_missing", preflight.build_report(OWNER, state)["blockers"])

    def test_report_is_public_safe(self) -> None:
        report = preflight.build_report(OWNER, base_state())
        rendered = json.dumps(report, sort_keys=True)
        for private_value in (OWNER, DASH_APP, "private.cloudflareaccess.com"):
            self.assertNotIn(private_value, rendered)

    def test_collect_state_uses_get_only(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls = []
            def get(self, path, query=None):
                self.calls.append((path, query))
                if path == "/user/tokens/verify":
                    return {"success": True, "result": {"status": "active"}}
                if path.endswith("/access/organizations"):
                    return {"success": True, "result": {"auth_domain": "private", "session_duration": "24h"}}
                if path.endswith("/access/apps"):
                    return {"success": True, "result": [], "result_info": {"total_pages": 1}}
                raise AssertionError(path)
        client = FakeClient()
        state = preflight.collect_state(client, "0123456789abcdef0123456789abcdef")
        self.assertEqual(state["apps"], [])
        self.assertTrue(client.calls)

    def test_source_has_no_http_write_primitive_or_owner_env(self) -> None:
        combined = "\n".join([
            (ROOT / "scripts/cloudflare_owner_browser_sso_preflight.py").read_text(),
            (ROOT / "scripts/cloudflare_owner_browser_sso_preflight_stdin.py").read_text(),
            (ROOT / "ops/bin/cloudflare-owner-browser-sso-preflight").read_text(),
        ])
        for forbidden in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"', '.post(', '.put(', '.patch(', '.delete(', 'CLOUDFLARE_OWNER_EMAIL'):
            self.assertNotIn(forbidden, combined)
        self.assertIn("CloudflareGetClient", combined)
        self.assertIn("Owner email (hidden)", combined)


if __name__ == "__main__":
    unittest.main()
