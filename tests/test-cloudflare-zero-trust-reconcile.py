#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "cloudflare_zero_trust_reconcile.py"
SPEC = importlib.util.spec_from_file_location("cloudflare_zero_trust_reconcile", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
cf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cf
SPEC.loader.exec_module(cf)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class RecordingOpener:
    def __init__(self) -> None:
        self.methods: list[str] = []

    def open(self, request, timeout=0):  # type: ignore[no-untyped-def]
        self.methods.append(request.get_method())
        return FakeResponse({"success": True, "result": {"status": "active"}})


class FakeClient:
    def __init__(self, mapping: dict[str, dict[str, Any]]) -> None:
        self.mapping = mapping
        self.calls: list[tuple[str, dict[str, str | int] | None]] = []

    def get(self, path: str, query=None):  # type: ignore[no-untyped-def]
        self.calls.append((path, query))
        try:
            return self.mapping[path]
        except KeyError as exc:
            raise AssertionError(f"unexpected path: {path}") from exc


def registry_text() -> str:
    return """\
schema_version: 1
status: desired-state
hostnames:
  - hostname: tech.rozkalns.net
    delivery: shared_rpi5_tunnel
    trust_class: PUBLIC
    desired_origin_scope: loopback
    access_application_scope: none
    protect_with_access: false
    lan_break_glass: false
    audit_route_presence: present

  - hostname: portainer.rozkalns.net
    delivery: shared_rpi5_tunnel
    trust_class: ADMIN
    desired_origin_scope: explicit-lan-break-glass
    access_application_scope: exact-or-narrow-admin
    protect_with_access: true
    lan_break_glass: true
    audit_route_presence: present

  - hostname: control.rozkalns.net
    delivery: cloudflare_worker
    trust_class: ADMIN
    desired_origin_scope: cloudflare-worker
    access_application_scope: exact-owner
    protect_with_access: not-applicable
    lan_break_glass: false
    audit_route_presence: not-applicable
"""


WILDCARD_ID = "11111111-1111-4111-8111-111111111111"
CONTROL_ID = "22222222-2222-4222-8222-222222222222"
ACCOUNT_ID = "a" * 32
TUNNEL_ID = "33333333-3333-4333-8333-333333333333"


def sample_registry() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.yaml"
        path.write_text(registry_text(), encoding="utf-8")
        return cf.load_registry(path)


def sample_state() -> dict[str, Any]:
    raw_email = "redacted-owner@example.com"
    raw_ip = "198.51.100.44/32"
    apps = [
        {
            "id": WILDCARD_ID,
            "name": "homelab-private",
            "type": "self_hosted",
            "domain": "*.rozkalns.net",
            "session_duration": "730h",
            "aud": "raw-audience-must-not-leak",
        },
        {
            "id": CONTROL_ID,
            "name": "control-owner",
            "type": "self_hosted",
            "domain": "control.rozkalns.net",
            "session_duration": "24h",
            "aud": "second-raw-audience",
            "allow_authenticate_via_warp": True,
        },
    ]
    policies = {
        WILDCARD_ID: [
            {
                "decision": "bypass",
                "precedence": 1,
                "include": [{"ip": {"ip": raw_ip}}],
            },
            {
                "decision": "allow",
                "precedence": 2,
                "include": [{"email": {"email": raw_email}}],
            },
        ],
        CONTROL_ID: [
            {
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": raw_email}}],
                "require": [{"device_posture": {"integration_uid": "redacted"}}],
            }
        ],
    }
    return {
        "organization": {
            "auth_domain": "team-redacted.cloudflareaccess.com",
            "allow_authenticate_via_warp": True,
            "session_duration": "24h",
        },
        "apps": apps,
        "policies": policies,
        "tunnel": {
            "name": "rpi5-tunnel",
            "config_src": "cloudflare",
            "status": "healthy",
            "connections": [{"origin_ip": "192.0.2.10"}] * 4,
        },
        "config": {
            "ingress": [
                {
                    "hostname": "tech.rozkalns.net",
                    "service": "http://127.0.0.1:9118",
                },
                {
                    "hostname": "portainer.rozkalns.net",
                    "service": "http://10.20.30.40:9000",
                    "originRequest": {
                        "access": {
                            "required": True,
                            "audTag": ["raw-audience-must-not-leak"],
                            "teamName": "team-redacted",
                        }
                    },
                },
                {"service": "http_status:404"},
            ]
        },
    }


class CloudflareP0Tests(unittest.TestCase):
    def test_registry_parser_is_narrow_and_complete(self) -> None:
        registry = sample_registry()
        self.assertEqual(
            set(registry),
            {
                "tech.rozkalns.net",
                "portainer.rozkalns.net",
                "control.rozkalns.net",
            },
        )
        self.assertEqual(registry["tech.rozkalns.net"].trust_class, "PUBLIC")
        self.assertEqual(
            registry["control.rozkalns.net"].audit_route_presence, "not-applicable"
        )

    def test_http_client_can_only_issue_get(self) -> None:
        client = cf.CloudflareGetClient(
            "x" * 32,
            "http://127.0.0.1:9999",
        )
        opener = RecordingOpener()
        client._opener = opener
        payload = client.get("/user/tokens/verify")
        self.assertTrue(payload["success"])
        self.assertEqual(opener.methods, ["GET"])

        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        request_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Request"
        ]
        self.assertEqual(len(request_calls), 1)
        method_keywords = [
            kw
            for kw in request_calls[0].keywords
            if kw.arg == "method"
        ]
        self.assertEqual(len(method_keywords), 1)
        self.assertIsInstance(method_keywords[0].value, ast.Constant)
        self.assertEqual(method_keywords[0].value.value, "GET")

    def test_non_https_api_base_is_localhost_only(self) -> None:
        with self.assertRaisesRegex(cf.AuditError, "non_https_api_base_forbidden"):
            cf.CloudflareGetClient("x" * 32, "http://example.invalid")

    def test_exact_application_precedes_parent_wildcard(self) -> None:
        state = sample_state()
        resolved = cf.resolve_application(state["apps"], "control.rozkalns.net")
        self.assertEqual(resolved["status"], "exact")
        self.assertEqual(resolved["selected"]["id"], CONTROL_ID)

    def test_wildcard_is_single_subdomain_level(self) -> None:
        state = sample_state()
        self.assertEqual(
            cf.resolve_application(state["apps"], "tech.rozkalns.net")["status"],
            "wildcard",
        )
        self.assertEqual(
            cf.resolve_application(state["apps"], "deep.tech.rozkalns.net")["status"],
            "none",
        )
        self.assertEqual(
            cf.resolve_application(state["apps"], "rozkalns.net")["status"],
            "none",
        )

    def test_policy_sanitizer_never_emits_selector_values(self) -> None:
        policy = {
            "decision": "allow",
            "include": [
                {"email": {"email": "redacted-owner@example.com"}},
                {"ip": {"ip": "198.51.100.44/32"}},
            ],
        }
        rendered = json.dumps(cf.sanitize_policy(policy), sort_keys=True)
        self.assertNotIn("redacted-owner@example.com", rendered)
        self.assertNotIn("198.51.100.44", rendered)
        self.assertIn('"email"', rendered)
        self.assertIn('"ip"', rendered)

    def test_service_classification_hides_exact_origin(self) -> None:
        self.assertEqual(cf.classify_service("http://127.0.0.1:8080"), "loopback")
        self.assertEqual(cf.classify_service("http://10.20.30.40:8080"), "private-lan")
        self.assertEqual(cf.classify_service("http_status:404"), "http-status")

    def test_build_report_fails_closed_on_known_wildcard_bypass_drift(self) -> None:
        report = cf.build_report(sample_registry(), sample_state())
        self.assertEqual(report["result"], "BLOCKED")
        self.assertFalse(report["mutation_performed"])
        blockers = set(report["blockers"])
        self.assertIn(
            "public_hostname_has_access_application:tech.rozkalns.net", blockers
        )
        self.assertIn(
            "matching_access_application_has_bypass:portainer.rozkalns.net", blockers
        )

        serialized = json.dumps(report, sort_keys=True)
        for forbidden in (
            "redacted-owner@example.com",
            "198.51.100.44",
            "raw-audience-must-not-leak",
            "second-raw-audience",
            ACCOUNT_ID,
            TUNNEL_ID,
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("team-redacted.cloudflareaccess.com", serialized)
        self.assertNotIn('"teamName"', serialized)

    def test_collect_state_uses_only_documented_get_endpoints(self) -> None:
        apps = [
            {
                "id": CONTROL_ID,
                "name": "control-owner",
                "type": "self_hosted",
                "domain": "control.rozkalns.net",
            }
        ]
        mapping = {
            "/user/tokens/verify": {
                "success": True,
                "result": {"status": "active"},
            },
            f"/accounts/{ACCOUNT_ID}/access/organizations": {
                "success": True,
                "result": {"auth_domain": "team.cloudflareaccess.com"},
            },
            f"/accounts/{ACCOUNT_ID}/access/apps": {
                "success": True,
                "result": apps,
                "result_info": {"total_pages": 1},
            },
            f"/accounts/{ACCOUNT_ID}/access/apps/{CONTROL_ID}/policies": {
                "success": True,
                "result": [],
                "result_info": {"total_pages": 1},
            },
            f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}": {
                "success": True,
                "result": {
                    "name": "rpi5-tunnel",
                    "config_src": "cloudflare",
                },
            },
            f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations": {
                "success": True,
                "result": {
                    "config": {
                        "ingress": [{"service": "http_status:404"}]
                    }
                },
            },
        }
        client = FakeClient(mapping)
        state = cf.collect_state(client, ACCOUNT_ID, TUNNEL_ID)
        self.assertEqual(state["apps"], apps)
        self.assertEqual(
            [path for path, _ in client.calls],
            [
                "/user/tokens/verify",
                f"/accounts/{ACCOUNT_ID}/access/organizations",
                f"/accounts/{ACCOUNT_ID}/access/apps",
                f"/accounts/{ACCOUNT_ID}/access/apps/{CONTROL_ID}/policies",
                f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}",
                f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations",
            ],
        )

    def test_repository_registry_has_explicit_route_expectations(self) -> None:
        registry = cf.load_registry(
            ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"
        )
        self.assertGreaterEqual(len(registry), 12)
        self.assertEqual(
            registry["dash.rozkalns.net"].audit_route_presence, "present"
        )
        self.assertEqual(
            registry["control.rozkalns.net"].audit_route_presence, "not-applicable"
        )
        for item in registry.values():
            if item.delivery == "shared_rpi5_tunnel":
                self.assertEqual(item.audit_route_presence, "present")

    def test_repository_registry_tracks_dashboard_live_route_contract(self) -> None:
        registry = cf.load_registry(
            ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"
        )
        dash = registry["dash.rozkalns.net"]
        self.assertEqual(dash.delivery, "shared_rpi5_tunnel")
        self.assertEqual(dash.trust_class, "ADMIN")
        self.assertEqual(dash.desired_origin_scope, "loopback")
        self.assertEqual(dash.access_application_scope, "exact-owner")
        self.assertTrue(dash.protect_with_access)
        self.assertFalse(dash.lan_break_glass)
        self.assertEqual(dash.audit_route_presence, "present")

    def test_wrapper_preserves_hidden_token_boundary(self) -> None:
        wrapper = (
            ROOT / "ops" / "bin" / "cloudflare-zero-trust-reconcile"
        ).read_text(encoding="utf-8")
        self.assertIn("read -r -s", wrapper)
        self.assertIn("</dev/tty", wrapper)
        self.assertIn("unset CLOUDFLARE_API_TOKEN", wrapper)
        self.assertIn("cloudflare_zero_trust_reconcile.py", wrapper)
        self.assertNotIn('echo "$CLOUDFLARE_API_TOKEN"', wrapper)
        self.assertNotIn("set -x", wrapper)


if __name__ == "__main__":
    unittest.main()
