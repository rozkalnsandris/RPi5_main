#!/usr/bin/env python3
"""Offline tests for the source-only GET adapter; network never accessed."""
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ausmalwiese_redirect_get_adapter as adapter

ZONE = "a" * 32
ENTRY = "b" * 32
TOKEN = "T" * 32
BASE = adapter.API_ORIGIN


def envelope(result):
    return json.dumps({"success": True, "result": result}).encode("utf-8")


class FakeResponse:
    def __init__(self, url, content, status=200, target=None):
        self.status = status
        self.url = target or url
        self.body = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, count):
        return self.body[:count]


class FakeOpener:
    def __init__(self):
        self.calls = []
        self.overrides = {}
        self.routes = {
            f"/zones/{ZONE}": envelope({"id": ZONE, "name": "rozkalns.net", "status": "active"}),
            f"/zones/{ZONE}/rulesets": envelope([
                {"id": ENTRY, "kind": "zone", "phase": adapter.PHASE},
            ]),
            f"/zones/{ZONE}/rulesets/phases/{adapter.PHASE}/entrypoint": envelope({
                "id": ENTRY, "kind": "zone", "phase": adapter.PHASE, "rules": [
                    {"expression": 'http.host eq "coloring.rozkalns.net"', "enabled": True},
                    {"expression": 'http.host eq "other.rozkalns.net"', "enabled": True},
                    {"expression": 'true', "enabled": False},
                ],
            }),
        }

    def open(self, request, timeout):
        path = request.full_url.removeprefix(BASE)
        self.calls.append((request, timeout, path))
        override = self.overrides.get(path, None)
        if isinstance(override, Exception):
            raise override
        return FakeResponse(
            request.full_url,
            self.routes[path] if override is None else override,
        )


class GetOnlyTrustedAdapterTests(unittest.TestCase):
    def test_exact_three_gets_and_only_sanitized_output(self):
        op = FakeOpener()
        output = adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
        self.assertEqual(output["active_exact_legacy_positions"], [1])
        self.assertEqual(output["other_exact_host_count"], 1)
        self.assertEqual(output["disabled_scope_unknown_count"], 1)
        self.assertFalse(output["safe_to_apply"])
        self.assertFalse(output["account_level_checked"])
        self.assertEqual([x[2] for x in op.calls], [
            f"/zones/{ZONE}",
            f"/zones/{ZONE}/rulesets",
            f"/zones/{ZONE}/rulesets/phases/{adapter.PHASE}/entrypoint",
        ])
        for request, timeout, _ in op.calls:
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(timeout, adapter.TIMEOUT_SECONDS)
            self.assertTrue(request.full_url.startswith(BASE + "/zones/" + ZONE))
            self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertNotIn(TOKEN, json.dumps(output))
        self.assertNotIn(ENTRY, json.dumps(output))

    def test_disallow_any_other_method_route_zone_and_invalid_token(self):
        op = FakeOpener()
        client = adapter.FixedZoneGetAdapter(ZONE, TOKEN, opener=op)
        for method, path in (
            ("POST", f"/zones/{ZONE}/rulesets"),
            ("PATCH", f"/zones/{ZONE}/rulesets"),
            ("GET", f"/zones/{ZONE}/dns_records"),
            ("GET", f"/zones/{ZONE}/rulesets?page=2"),
            ("GET", f"/zones/{ZONE}/rulesets/../other"),
            ("GET", f"/zones/{'c'*32}/rulesets"),
            ("GET", f"/zones/{ZONE}/rulesets/"),
        ):
            with self.subTest(method=method, path=path):
                with self.assertRaisesRegex(adapter.AdapterBlocked, "non_allowlisted_request"):
                    client(method, path)
        self.assertEqual(op.calls, [])
        for zone in ("", "b" * 31, "B" * 32, "../../hidden", None):
            with self.assertRaisesRegex(adapter.AdapterBlocked, "invalid_zone_identity"):
                adapter.FixedZoneGetAdapter(zone, TOKEN, opener=op)
        for secret in ("", "short", "A\nB" + "C" * 40, "E" * 600, None):
            with self.assertRaisesRegex(adapter.AdapterBlocked, "invalid_in_memory_credential"):
                adapter.FixedZoneGetAdapter(ZONE, secret, opener=op)
        self.assertEqual(op.calls, [])

    def test_404_is_only_valid_for_phase_and_core_confirmed_absence(self):
        op = FakeOpener()
        phase = f"/zones/{ZONE}/rulesets/phases/{adapter.PHASE}/entrypoint"
        op.overrides[phase] = urllib.error.HTTPError(
            BASE + phase, 404, "not found", {}, io.BytesIO(b"SECRET_SHOULD_NOT_LEAK"),
        )
        # Core insists phase is absent from zone ruleset list.
        with self.assertRaisesRegex(adapter.AdapterBlocked, "entrypoint_list_disagreement"):
            adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
        op.routes[f"/zones/{ZONE}/rulesets"] = envelope([])
        output = adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
        self.assertEqual(output["entrypoint"], "absent")
        self.assertFalse(output["safe_to_apply"])
        op = FakeOpener()
        op.overrides[f"/zones/{ZONE}"] = urllib.error.HTTPError(
            BASE + f"/zones/{ZONE}", 404, "not found", {}, io.BytesIO(b"SECRET"),
        )
        with self.assertRaisesRegex(adapter.AdapterBlocked, "read_only_transport_failed"):
            adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)

    def test_unexpected_403_302_or_network_exception_fail_closed(self):
        route = f"/zones/{ZONE}"
        for err in (
            urllib.error.HTTPError(BASE + route, 403, "forbidden", {}, io.BytesIO(b"LEAK")),
            urllib.error.HTTPError(BASE + route, 302, "moved", {}, io.BytesIO(b"LEAK")),
            OSError("PRIVATE_VALUE_MUST_NOT_PRINT"),
        ):
            with self.subTest(kind=type(err).__name__):
                op = FakeOpener()
                op.overrides[route] = err
                with self.assertRaises(adapter.AdapterBlocked) as ctx:
                    adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
                self.assertNotIn("PRIVATE_VALUE", str(ctx.exception))
                self.assertNotIn(TOKEN, str(ctx.exception))
                self.assertEqual(len(op.calls), 1)

    def test_invalid_json_duplicate_key_provider_error_and_oversize(self):
        route = f"/zones/{ZONE}"
        bodies = [
            b"{",
            b'{"success":true,"success":true,"result":{}}',
            b'{"success":false,"result":{}}',
            b'[]',
            b"A" * (adapter.MAX_BODY_BYTES + 3),
        ]
        for body in bodies:
            with self.subTest(size=len(body)):
                op = FakeOpener()
                op.overrides[route] = body
                with self.assertRaises(adapter.AdapterBlocked):
                    adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
                self.assertEqual(len(op.calls), 1)

    def test_incomplete_pagination_fails_before_third_get(self):
        op = FakeOpener()
        op.routes[f"/zones/{ZONE}/rulesets"] = json.dumps({
            "success": True, "result": [],
            "result_info": {"cursors": {"after": "more"}},
        }).encode("utf-8")
        with self.assertRaisesRegex(adapter.AdapterBlocked, "incomplete_ruleset_list"):
            adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
        self.assertEqual(len(op.calls), 2)

    def test_injected_opener_is_test_only_and_no_default_network_used(self):
        # This test never constructs an opener without a FakeOpener.
        op = FakeOpener()
        inv = adapter.sanitized_redirect_inventory(ZONE, TOKEN, opener=op)
        self.assertEqual(inv["zone_name"], "rozkalns.net")
        self.assertEqual(len(op.calls), 3)
        code = (ROOT / "scripts/ausmalwiese_redirect_get_adapter.py").read_text("utf-8")
        for banned in ("if __name__", "import argparse", "getpass", "os.environ",
                       "subprocess", "os.system", "secret_path", ".env"):
            self.assertNotIn(banned, code)


    def test_install_preflight_contract_requires_separate_owner_gates(self):
        policy_path = ROOT / "ops/contracts/ausmalwiese-redirect-get-adapter-preflight-v1.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        self.assertEqual(
            policy["schema"],
            "rozkalns.rpi5-main.ausmalwiese-redirect-get-adapter-preflight.v1",
        )
        self.assertEqual(policy["zone"], "rozkalns.net")
        self.assertEqual(policy["permitted_methods"], ["GET"])
        self.assertEqual(policy["network_policy"]["max_http_requests_per_invocation"], 3)
        self.assertFalse(policy["proposed_artifact_policy"]["installation_operation_authorized"])
        self.assertFalse(policy["proposed_artifact_policy"]["privileged_fs_write_authorized"])
        self.assertFalse(policy["output_policy"]["safe_to_apply_always"])
        self.assertFalse(policy["output_policy"]["token_or_credential_material"])
        required = policy["planned_runtime_prerequisites"]
        for condition in (
            "separate_explicit_owner_install_authorization",
            "independently_authorized_exact_zone_scoped_Dynamic_URL_Redirects_Read_token",
            "no_token_in_argv_env_stdin_repo_logs_or_chat",
            "runtime_get_execution_requires_fresh_distinct_owner_review_authorization",
        ):
            self.assertIn(condition, required)
        doc = (ROOT / "docs/AUSMALWIESE_REDIRECT_GET_ADAPTER_V1.md").read_text("utf-8")
        self.assertIn("Not installed", doc)
        self.assertIn("No automatic retry", doc)


if __name__ == "__main__":
    unittest.main()
