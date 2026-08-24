#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_phone_preflight as preflight  # noqa: E402

OWNER = "owner@example.com"
ENROLL_APP = "11111111-1111-4111-8111-111111111111"
DASH_APP = "22222222-2222-4222-8222-222222222222"
WILDCARD_APP = "33333333-3333-4333-8333-333333333333"
DEVICE_ID = "44444444-4444-4444-8444-444444444444"
POLICY_ID = "55555555-5555-4555-8555-555555555555"


def base_state() -> dict:
    return {
        "organization": {
            "auth_domain": "private-team.cloudflareaccess.com",
            "allow_authenticate_via_warp": False,
            "warp_auth_session_duration": "24h",
        },
        "apps": [
            {
                "id": ENROLL_APP,
                "type": "warp",
                "name": "Warp device enrollment",
                "allowed_idps": ["private-idp-id"],
                "auto_redirect_to_identity": True,
            },
            {
                "id": DASH_APP,
                "type": "self_hosted",
                "name": "RPi5 Dashboard",
                "domain": "dash.rozkalns.net",
                "session_duration": "24h",
                "allow_authenticate_via_warp": False,
            },
            {
                "id": WILDCARD_APP,
                "type": "self_hosted",
                "name": "RPi5 Admin Wildcard",
                "domain": "*.rozkalns.net",
                "session_duration": "24h",
            },
        ],
        "policies": {
            ENROLL_APP: [
                {
                    "decision": "allow",
                    "precedence": 1,
                    "include": [{"email": {"email": OWNER}}],
                    "require": [],
                    "exclude": [],
                }
            ],
            DASH_APP: [
                {
                    "decision": "allow",
                    "precedence": 1,
                    "include": [{"email": {"email": OWNER}}],
                    "require": [],
                    "exclude": [],
                }
            ],
            WILDCARD_APP: [
                {
                    "decision": "allow",
                    "precedence": 1,
                    "include": [{"email": {"email": OWNER}}],
                    "require": [],
                    "exclude": [],
                }
            ],
        },
        "posture": [
            {
                "id": "66666666-6666-4666-8666-666666666666",
                "name": "Owner Gateway",
                "type": "gateway",
                "enabled": True,
                "match": [{"platform": "android"}],
            }
        ],
        "registrations": [
            {
                "id": "77777777-7777-4777-8777-777777777777",
                "revoked_at": None,
                "deleted_at": None,
                "tunnel_type": "masque",
                "user": {"email": OWNER, "name": "private-owner"},
                "device": {
                    "id": DEVICE_ID,
                    "name": "private-phone-name",
                    "client_version": "9.9.9",
                },
                "policy": {
                    "id": POLICY_ID,
                    "default": True,
                    "name": "private-profile-name",
                },
                "key": "private-public-key",
                "virtual_ipv4": "100.64.0.1",
            }
        ],
        "devices": [
            {
                "id": DEVICE_ID,
                "name": "private-phone-name",
                "device_type": "android",
                "deleted_at": None,
                "active_registrations": 1,
                "hardware_id": "private-hardware-id",
            }
        ],
        "default_profile": {
            "policy_id": POLICY_ID,
            "default": True,
            "name": "private-profile-name",
            "service_mode_v2": {"mode": "warp"},
        },
        "custom_profiles": [],
    }


class CloudflareOwnerPhonePreflightTests(unittest.TestCase):
    def test_happy_fixture_is_public_safe_and_gets_to_dashboard_sequence(self) -> None:
        report = preflight.build_report(OWNER, base_state())
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["enrollment"]["application_state"], "single")
        self.assertTrue(report["enrollment"]["owner_only"])
        self.assertEqual(report["owner_device"]["owner_android_active_registration_count"], 1)
        self.assertTrue(report["owner_device"]["selected_android_gateway_routing_mode"])
        self.assertTrue(report["gateway_posture"]["ready"])
        self.assertNotIn(
            "p1d-01a-create-owner-only-enrollment-application",
            report["remaining_gates"],
        )
        self.assertNotIn("p1d-01-owner-only-enrollment-policy", report["remaining_gates"])
        self.assertNotIn("p1d-02a-enable-gateway-posture-check", report["remaining_gates"])
        self.assertIn("p1d-02-owner-phone-enrollment-canary", report["remaining_gates"])
        self.assertIn("p1d-03-dash-require-gateway", report["remaining_gates"])

        rendered = json.dumps(report, sort_keys=True)
        for private_value in (
            OWNER,
            "private-team",
            DEVICE_ID,
            "private-phone-name",
            "private-public-key",
            "100.64.0.1",
            "private-hardware-id",
            POLICY_ID,
        ):
            self.assertNotIn(private_value, rendered)

    def test_missing_enrollment_application_routes_to_create_canary(self) -> None:
        state = base_state()
        state["apps"] = [app for app in state["apps"] if app["id"] != ENROLL_APP]
        state["policies"].pop(ENROLL_APP)
        state["registrations"] = []
        state["devices"] = []

        report = preflight.build_report(OWNER, state)

        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["enrollment"]["application_count"], 0)
        self.assertEqual(report["enrollment"]["application_state"], "missing")
        self.assertFalse(report["enrollment"]["owner_only"])
        self.assertNotIn("device_enrollment_application_ambiguous", report["blockers"])
        self.assertIn(
            "p1d-01a-create-owner-only-enrollment-application",
            report["remaining_gates"],
        )
        self.assertNotIn("p1d-01-owner-only-enrollment-policy", report["remaining_gates"])
        self.assertIn("p1d-02-owner-phone-enrollment", report["remaining_gates"])

    def test_multiple_enrollment_applications_fail_closed(self) -> None:
        state = base_state()
        second_id = "aaaaaaaa-1111-4111-8111-111111111111"
        state["apps"].append(
            {
                "id": second_id,
                "type": "warp",
                "name": "Unexpected second enrollment app",
            }
        )
        state["policies"][second_id] = [
            {
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": OWNER}}],
                "require": [],
                "exclude": [],
            }
        ]

        report = preflight.build_report(OWNER, state)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["enrollment"]["application_count"], 2)
        self.assertEqual(report["enrollment"]["application_state"], "ambiguous")
        self.assertIn("device_enrollment_application_ambiguous", report["blockers"])
        self.assertNotIn(
            "p1d-01a-create-owner-only-enrollment-application",
            report["remaining_gates"],
        )
        self.assertNotIn("p1d-01-owner-only-enrollment-policy", report["remaining_gates"])

    def test_non_owner_only_enrollment_routes_to_p1d01(self) -> None:
        state = base_state()
        state["policies"][ENROLL_APP][0]["include"] = [
            {"email_domain": {"domain": "@example.invalid"}}
        ]
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["enrollment"]["application_state"], "single")
        self.assertFalse(report["enrollment"]["owner_only"])
        self.assertIn("p1d-01-owner-only-enrollment-policy", report["remaining_gates"])
        self.assertNotIn(
            "p1d-01a-create-owner-only-enrollment-application",
            report["remaining_gates"],
        )

    def test_missing_owner_android_registration_routes_to_p1d02(self) -> None:
        state = base_state()
        state["registrations"] = []
        state["devices"] = []
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "PASS")
        self.assertIn("p1d-02-owner-phone-enrollment", report["remaining_gates"])

    def test_missing_gateway_check_routes_to_conditional_p1d02a(self) -> None:
        state = base_state()
        state["posture"] = []
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "PASS")
        self.assertFalse(report["gateway_posture"]["ready"])
        self.assertIn("p1d-02a-enable-gateway-posture-check", report["remaining_gates"])

    def test_multiple_gateway_checks_fail_closed(self) -> None:
        state = base_state()
        state["posture"].append(
            {
                "id": "88888888-8888-4888-8888-888888888888",
                "type": "gateway",
                "enabled": True,
                "match": [],
            }
        )
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("multiple_android_gateway_posture_checks", report["blockers"])

    def test_wrong_android_profile_mode_fails_closed(self) -> None:
        state = base_state()
        state["default_profile"]["service_mode_v2"]["mode"] = "postureonly"
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("owner_android_gateway_routing_mode_not_proven", report["blockers"])

    def test_multiple_owner_android_registrations_fail_closed(self) -> None:
        state = base_state()
        second = deepcopy(state["registrations"][0])
        second["id"] = "99999999-9999-4999-8999-999999999999"
        second["device"] = {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "name": "second-private-phone",
            "client_version": "9.9.9",
        }
        state["registrations"].append(second)
        state["devices"].append(
            {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "name": "second-private-phone",
                "device_type": "android",
                "deleted_at": None,
                "active_registrations": 1,
            }
        )
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("owner_android_registration_ambiguous", report["blockers"])

    def test_missing_organization_binding_fails_closed(self) -> None:
        state = base_state()
        state["organization"]["auth_domain"] = ""
        report = preflight.build_report(OWNER, state)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("organization_binding_missing", report["blockers"])

    def test_invalid_owner_identity_is_rejected_without_echo(self) -> None:
        with self.assertRaisesRegex(Exception, "missing_or_invalid_owner_email"):
            preflight.build_report("not-an-email", base_state())

    def test_collect_state_uses_only_get_surface(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict | None]] = []

            def get(self, path: str, query: dict | None = None) -> dict:
                self.calls.append((path, query))
                if path == "/user/tokens/verify":
                    return {"success": True, "result": {"status": "active"}}
                if path.endswith("/access/organizations"):
                    return {"success": True, "result": {"auth_domain": "private"}}
                if path.endswith("/access/apps"):
                    return {
                        "success": True,
                        "result": [],
                        "result_info": {"total_pages": 1},
                    }
                if path.endswith("/devices/posture"):
                    return {"success": True, "result": []}
                if path.endswith("/devices/registrations"):
                    return {"success": True, "result": [], "result_info": {}}
                if path.endswith("/devices/physical-devices"):
                    return {"success": True, "result": [], "result_info": {}}
                if path.endswith("/devices/policy"):
                    return {"success": True, "result": {"default": True}}
                if path.endswith("/devices/policies"):
                    return {"success": True, "result": []}
                self.fail(f"unexpected path {path}")
                return {}

        client = FakeClient()
        state = preflight.collect_state(client, "0123456789abcdef0123456789abcdef")
        self.assertEqual(state["apps"], [])
        self.assertTrue(client.calls)
        self.assertTrue(all(path.startswith("/") for path, _ in client.calls))

    def test_source_has_no_http_write_primitive_or_private_owner_env(self) -> None:
        source = (ROOT / "scripts" / "cloudflare_owner_phone_preflight.py").read_text(
            encoding="utf-8"
        )
        runner = (
            ROOT / "scripts" / "cloudflare_owner_phone_preflight_stdin.py"
        ).read_text(encoding="utf-8")
        wrapper = (ROOT / "ops" / "bin" / "cloudflare-owner-phone-preflight").read_text(
            encoding="utf-8"
        )
        combined = "\n".join([source, runner, wrapper])
        for forbidden in (
            'method="POST"',
            'method="PUT"',
            'method="PATCH"',
            'method="DELETE"',
            ".post(",
            ".put(",
            ".patch(",
            ".delete(",
            "CLOUDFLARE_OWNER_EMAIL",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertIn("CloudflareGetClient", source)
        self.assertIn("Owner email (hidden)", wrapper)
        self.assertNotIn('owner_email="${', wrapper)


if __name__ == "__main__":
    unittest.main()
