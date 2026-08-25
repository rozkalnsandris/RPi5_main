#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_phone_enrollment_create as create  # noqa: E402

ACCOUNT = "0123456789abcdef0123456789abcdef"
OWNER = "owner@example.com"
CREATED = "11111111-1111-4111-8111-111111111111"
DASH = "22222222-2222-4222-8222-222222222222"
DEVICE = "33333333-3333-4333-8333-333333333333"


def state(with_enrollment: bool = False) -> dict:
    result = {
        "organization": {"auth_domain": "private.cloudflareaccess.com"},
        "apps": [{"id": DASH, "type": "self_hosted", "name": "dashboard"}],
        "policies": {
            DASH: [
                {
                    "decision": "allow",
                    "precedence": 1,
                    "include": [{"email": {"email": OWNER}}],
                    "require": [],
                    "exclude": [],
                }
            ]
        },
        "posture": [{"id": "private-posture-id", "type": "gateway", "enabled": True}],
        "registrations": [],
        "devices": [{"id": DEVICE, "device_type": "android", "name": "private-device"}],
        "default_profile": {"default": True, "service_mode_v2": {"mode": "warp"}},
        "custom_profiles": [],
    }
    if with_enrollment:
        result["apps"].append(
            {"id": CREATED, "type": "warp", "name": create.APPLICATION_NAME}
        )
        result["policies"][CREATED] = [
            {
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": OWNER}}],
                "require": [],
                "exclude": [],
            }
        ]
    return result


def report(count: int) -> dict:
    return {
        "result": "PASS",
        "blockers": [],
        "organization_binding_present": True,
        "enrollment": {
            "application_count": count,
            "application_state": "single" if count else "missing",
            "owner_only": bool(count),
            "owner_exact_email_match": bool(count),
            "policy_count": 1 if count else 0,
            "policy_actions": ["allow"] if count else [],
            "require_selector_types": [],
            "exclude_selector_types": [],
        },
        "gateway_posture": {"ready": True, "ambiguous": False},
        "owner_device": {
            "owner_android_active_registration_count": 0,
            "selected_android_gateway_routing_mode": False,
        },
        "client_session_beta": {
            "authenticate_with_cloudflare_one_client_default": False,
            "client_session_duration": None,
        },
        "access": {
            "dashboard": {"client_session_auth_effective": False},
            "control": {"client_session_auth_effective": False},
        },
        "remaining_gates": (
            [create.CANARY_ID]
            if count == 0
            else ["p1d-02-owner-phone-enrollment"]
        ),
    }


class Writer:
    def __init__(self, result=None, error=None):
        self.result = {"id": CREATED} if result is None else result
        self.error = error
        self.calls = 0

    def create_owner_enrollment_application(self, account_id, owner_email):
        self.calls += 1
        if self.error:
            raise self.error
        return deepcopy(self.result)


def execute(states: list[dict], reports: list[dict], writer: Writer) -> dict:
    state_index = 0
    report_index = 0

    def collect(_client, _account):
        nonlocal state_index
        value = deepcopy(states[state_index])
        state_index += 1
        return value

    def build(_owner, _state):
        nonlocal report_index
        value = deepcopy(reports[report_index])
        report_index += 1
        return value

    return create.execute_canary(
        object(),
        writer,
        ACCOUNT,
        OWNER,
        collect_state_fn=collect,
        build_report_fn=build,
    )


class Tests(unittest.TestCase):
    def test_payload_exact_and_omits_guessed_fields(self):
        payload = create.build_create_payload(OWNER)
        self.assertEqual(payload["type"], "warp")
        self.assertEqual(payload["name"], create.APPLICATION_NAME)
        self.assertEqual(len(payload["policies"]), 1)
        policy = payload["policies"][0]
        self.assertEqual(policy["decision"], "allow")
        self.assertEqual(policy["precedence"], 1)
        self.assertEqual(policy["include"], [{"email": {"email": OWNER}}])
        self.assertEqual(policy["require"], [])
        self.assertEqual(policy["exclude"], [])
        rendered = json.dumps(payload)
        for key in ("allowed_idps", "auto_redirect_to_identity", "session_duration"):
            self.assertNotIn(key, rendered)

    def test_happy_path_one_post_and_public_safe_proof(self):
        writer = Writer()
        result = execute([state(False), state(True)], [report(0), report(1)], writer)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(writer.calls, 1)
        self.assertEqual(result["forward_request_count"], 1)
        self.assertTrue(result["mutation_performed"])
        self.assertTrue(result["post_write_proof"]["unrelated_state_unchanged"])
        rendered = json.dumps(result, sort_keys=True)
        for private in (ACCOUNT, OWNER, CREATED, DASH, DEVICE, "private-device", "private-posture-id"):
            self.assertNotIn(private, rendered)

    def test_nonzero_preflight_blocks_before_write(self):
        writer = Writer()
        result = create.execute_canary(
            object(),
            writer,
            ACCOUNT,
            OWNER,
            collect_state_fn=lambda *_: state(True),
            build_report_fn=lambda *_: report(1),
        )
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reason"], "fresh_preflight_enrollment_not_zero")
        self.assertEqual(writer.calls, 0)
        self.assertFalse(result["forward_request_attempted"])

    def test_post_error_stops_without_retry_or_post_get(self):
        calls = 0

        def collect(*_):
            nonlocal calls
            calls += 1
            return state(False)

        writer = Writer(
            error=create.CloudflareCreateAttemptError("cloudflare_create_http_500", None)
        )
        result = create.execute_canary(
            object(),
            writer,
            ACCOUNT,
            OWNER,
            collect_state_fn=collect,
            build_report_fn=lambda *_: report(0),
        )
        self.assertEqual(result["result"], "STOP_ERROR")
        self.assertEqual(writer.calls, 1)
        self.assertEqual(calls, 1)
        self.assertIsNone(result["mutation_performed"])

    def test_ambiguous_success_stops_without_post_get(self):
        calls = 0

        def collect(*_):
            nonlocal calls
            calls += 1
            return state(False)

        writer = Writer(result={})
        result = create.execute_canary(
            object(),
            writer,
            ACCOUNT,
            OWNER,
            collect_state_fn=collect,
            build_report_fn=lambda *_: report(0),
        )
        self.assertEqual(result["result"], "STOP_ERROR")
        self.assertEqual(result["reason"], "created_application_attribution_missing")
        self.assertEqual(writer.calls, 1)
        self.assertEqual(calls, 1)
        self.assertTrue(result["mutation_performed"])

    def test_unrelated_device_state_change_fails_post_write_proof(self):
        after = state(True)
        after["devices"].append(
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "device_type": "android",
                "name": "unexpected-private-device",
            }
        )
        writer = Writer()
        result = execute([state(False), after], [report(0), report(1)], writer)
        self.assertEqual(result["result"], "STOP_ERROR")
        self.assertEqual(result["reason"], "post_write_proof_failed")
        self.assertFalse(result["post_write_proof"]["unrelated_state_unchanged"])
        self.assertEqual(writer.calls, 1)

    def test_volatile_timestamps_do_not_false_fail_state_proof(self):
        before = state(False)
        after = state(True)
        before["devices"][0]["updated_at"] = "2026-08-25T20:00:00Z"
        after["devices"][0]["updated_at"] = "2026-08-25T20:01:00Z"
        result = execute([before, after], [report(0), report(1)], Writer())
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["post_write_proof"]["unrelated_state_unchanged"])

    def test_source_and_wrapper_are_narrow(self):
        source = (
            ROOT / "scripts" / "cloudflare_owner_phone_enrollment_create.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "ops" / "bin" / "cloudflare-owner-phone-enrollment-create"
        ).read_text(encoding="utf-8")
        self.assertEqual(source.count('method="POST"'), 1)
        for forbidden in (
            'method="PUT"',
            'method="PATCH"',
            'method="DELETE"',
            ".delete(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn(create.CANARY_ID, wrapper)
        self.assertIn("Cloudflare READ API token (hidden)", wrapper)
        self.assertIn("Cloudflare WRITE API token (hidden)", wrapper)
        self.assertIn("custom CLOUDFLARE_API_BASE forbidden", wrapper)


if __name__ == "__main__":
    unittest.main()
