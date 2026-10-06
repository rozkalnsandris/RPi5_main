#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_phase5_deals_ip_bypass_remove as remove

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

bridge = load(
    "phase5_deals_remove_bridge",
    ROOT / "scripts/github_phase5_deals_ip_bypass_remove_bridge.py",
)

SHA = "a" * 40
ACCOUNT = "a" * 32
APP = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
BYPASS = "33333333-3333-4333-8333-333333333333"
ALLOW = "44444444-4444-4444-8444-444444444444"
SERVICE = "55555555-5555-4555-8555-555555555555"
SECOND_BYPASS = "66666666-6666-4666-8666-666666666666"
PRIVATE_IP_SENTINEL = "192.0.2.44/32"
PRIVATE_IDENTITY_SENTINEL = "private-identity-fixture-sentinel"
PRIVATE_TOKEN_SENTINEL = "private-service-token-fixture-sentinel"
OWNER_ID = 277435981


def fixture() -> dict:
    return {
        "inventory_complete": True,
        "organization": {"strict_service_token_auth": True},
        "apps": [
            {"id": APP, "type": "self_hosted", "domain": "deals.rozkalns.net"},
            {"id": OTHER, "type": "self_hosted", "domain": "kuma.rozkalns.net"},
        ],
        "policies_by_app": {
            APP: [
                {
                    "id": BYPASS,
                    "decision": "bypass",
                    "precedence": 1,
                    "include": [{"ip": {"ip": PRIVATE_IP_SENTINEL}}],
                },
                {
                    "id": ALLOW,
                    "decision": "allow",
                    "precedence": 2,
                    "include": [{"email": {"email": PRIVATE_IDENTITY_SENTINEL}}],
                },
                {
                    "id": SERVICE,
                    "decision": "service_auth",
                    "precedence": 3,
                    "include": [{"service_token": {"token_id": PRIVATE_TOKEN_SENTINEL}}],
                },
            ],
            OTHER: [],
        },
        "account_reusable_policies": [],
    }


def after_delete(state: dict) -> dict:
    value = copy.deepcopy(state)
    value["policies_by_app"][APP] = [
        p for p in value["policies_by_app"][APP] if p["id"] != BYPASS
    ]
    return value


def event(body: str, *, app: bool = False, issue: int = 897) -> dict:
    return {
        "action": "created",
        "issue": {"number": issue},
        "comment": {
            "id": 123,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": {"id": 1} if app else None,
            "user": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
    }


class FakeWrite:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.error = error

    def delete_deals_application_policy(
        self, account_id: str, app_id: str, policy_id: str
    ) -> None:
        self.calls.append((account_id, app_id, policy_id))
        if self.error is not None:
            raise self.error


class SequenceCollector:
    def __init__(self, values: list[dict]) -> None:
        self.values = [copy.deepcopy(x) for x in values]
        self.calls = 0

    def __call__(self, _client, _account_id: str) -> dict:
        if self.calls >= len(self.values):
            raise AssertionError("unexpected extra GET snapshot")
        value = copy.deepcopy(self.values[self.calls])
        self.calls += 1
        return value


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


class CapturingOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout: int):
        self.requests.append((request, timeout))
        return FakeResponse({"success": True, "result": {"id": BYPASS}})


class Phase5DealsAccessMutatorTests(unittest.TestCase):
    def test_plan_requires_exact_legacy_unshared_ip_bypass(self):
        plan = remove.build_delete_plan(
            fixture(), expected_main=SHA, observed_main=SHA
        )
        self.assertEqual(plan.app_id, APP)
        self.assertEqual(plan.policy_id, BYPASS)
        self.assertEqual(len(plan.private_prestate_digest), 64)

    def test_success_dispatches_exactly_one_delete_and_emits_no_private_values(self):
        before = fixture()
        collector = SequenceCollector([before, before, after_delete(before)])
        writer = FakeWrite()
        report = remove.execute_canary(
            object(),
            writer,
            ACCOUNT,
            expected_main=SHA,
            observed_main=SHA,
            collect_state_fn=collector,
        )
        self.assertEqual(report["result"], "PASS")
        self.assertTrue(report["mutation_performed"])
        self.assertEqual(report["forward_request_count"], 1)
        self.assertEqual(writer.calls, [(ACCOUNT, APP, BYPASS)])
        self.assertEqual(collector.calls, 3)
        self.assertTrue(report["post_write_proof"]["target_bypass_absent"])
        encoded = json.dumps(report, sort_keys=True)
        for private in (
            ACCOUNT,
            APP,
            BYPASS,
            PRIVATE_IP_SENTINEL,
            PRIVATE_IDENTITY_SENTINEL,
            PRIVATE_TOKEN_SENTINEL,
        ):
            self.assertNotIn(private, encoded)

    def test_reusable_and_shared_policy_both_block_before_write(self):
        state = fixture()
        state["account_reusable_policies"] = [
            {"id": BYPASS, "decision": "bypass", "precedence": 1}
        ]
        with self.assertRaisesRegex(remove.AuditError, "reusable_policy_requires_separate_design"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

        state = fixture()
        state["policies_by_app"][OTHER] = [
            {"id": BYPASS, "decision": "bypass", "precedence": 1}
        ]
        with self.assertRaisesRegex(remove.AuditError, "policy_shared_with_other_app"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

    def test_ambiguous_bypass_family_allow_and_service_auth_block(self):
        state = fixture()
        state["policies_by_app"][APP].append(
            {
                "id": SECOND_BYPASS,
                "decision": "bypass",
                "precedence": 4,
                "include": [{"ip": {"ip": "198.51.100.1/32"}}],
            }
        )
        with self.assertRaisesRegex(remove.AuditError, "bypass_not_unique"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

        state = fixture()
        state["policies_by_app"][APP][1]["require"] = [{"email": {"email": "sentinel"}}]
        with self.assertRaisesRegex(remove.AuditError, "family_allow_not_strictly_proven"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

        state = fixture()
        state["policies_by_app"][APP][2]["include"] = [{"ip": {"ip": "203.0.113.1/32"}}]
        with self.assertRaisesRegex(remove.AuditError, "service_auth_not_strictly_proven"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

    def test_strict_service_token_state_and_exact_main_are_required(self):
        state = fixture()
        del state["organization"]["strict_service_token_auth"]
        with self.assertRaisesRegex(remove.AuditError, "strict_service_token_state_unknown"):
            remove.build_delete_plan(state, expected_main=SHA, observed_main=SHA)

        with self.assertRaisesRegex(remove.AuditError, "exact_main_unproven"):
            remove.build_delete_plan(
                fixture(), expected_main=SHA, observed_main="b" * 40
            )

    def test_double_read_prestate_drift_blocks_before_delete(self):
        before = fixture()
        drifted = copy.deepcopy(before)
        drifted["policies_by_app"][APP][1]["precedence"] = 7
        collector = SequenceCollector([before, drifted])
        writer = FakeWrite()
        report = remove.execute_canary(
            object(), writer, ACCOUNT,
            expected_main=SHA, observed_main=SHA,
            collect_state_fn=collector,
        )
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["reason"], "protected_prestate_drifted_before_delete")
        self.assertEqual(writer.calls, [])
        self.assertEqual(collector.calls, 2)

    def test_delete_attempt_error_stops_without_retry_or_post_read(self):
        before = fixture()
        collector = SequenceCollector([before, before])
        writer = FakeWrite(
            remove.CloudflareAccessPolicyDeleteAttemptError(
                "cloudflare_access_policy_delete_http_403", None
            )
        )
        report = remove.execute_canary(
            object(), writer, ACCOUNT,
            expected_main=SHA, observed_main=SHA,
            collect_state_fn=collector,
        )
        self.assertEqual(report["result"], "STOP_ERROR")
        self.assertIsNone(report["mutation_performed"])
        self.assertEqual(report["forward_request_count"], 1)
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(collector.calls, 2)

    def test_post_write_unexpected_other_app_change_stops(self):
        before = fixture()
        after = after_delete(before)
        after["policies_by_app"][OTHER] = [
            {
                "id": "77777777-7777-4777-8777-777777777777",
                "decision": "allow",
                "precedence": 1,
                "include": [{"email": {"email": "unrelated-sentinel"}}],
            }
        ]
        collector = SequenceCollector([before, before, after])
        writer = FakeWrite()
        report = remove.execute_canary(
            object(), writer, ACCOUNT,
            expected_main=SHA, observed_main=SHA,
            collect_state_fn=collector,
        )
        self.assertEqual(report["result"], "STOP_ERROR")
        self.assertTrue(report["mutation_performed"])
        self.assertIn("post_write_proof_failed:", report["reason"])
        self.assertEqual(len(writer.calls), 1)

    def test_client_exposes_only_fixed_application_policy_delete(self):
        client = remove.CloudflareAccessApplicationPolicyDeleteClient("x" * 30)
        opener = CapturingOpener()
        client._opener = opener
        client.delete_deals_application_policy(ACCOUNT, APP, BYPASS)
        self.assertEqual(len(opener.requests), 1)
        request, _timeout = opener.requests[0]
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(
            request.full_url,
            (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{ACCOUNT}/access/apps/{APP}/policies/{BYPASS}"
            ),
        )

    def test_bridge_is_direct_owner_exact_sha_and_rerun_bound(self):
        body = (
            f"/rpi5-p5-deals-ip-bypass-remove apply HEAD={SHA} "
            "CANARY=phase5-deals-ip-bypass-remove-v1"
        )
        out = bridge.authorize_event(
            event(body),
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(out["expected_sha"], SHA)
        with self.assertRaisesRegex(bridge.AuthorizationError, "workflow_rerun_forbidden"):
            bridge.authorize_event(
                event(body),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="2",
            )
        with self.assertRaisesRegex(bridge.AuthorizationError, "app_authored_comment_forbidden"):
            bridge.authorize_event(
                event(body, app=True),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )
        with self.assertRaisesRegex(bridge.AuthorizationError, "issue_mismatch"):
            bridge.authorize_event(
                event(body, issue=895),
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_workflow_reuses_only_p1d04_secret_lane_and_has_no_manual_dispatch(self):
        workflow = (
            ROOT / ".github/workflows/cloudflare-phase5-deals-ip-bypass-remove.yml"
        ).read_text(encoding="utf-8")
        for expected in (
            "CLOUDFLARE_P1D04_ACCOUNT_ID",
            "CLOUDFLARE_P1D04_READ_API_TOKEN",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
            "github.event.issue.number == 897",
            "scripts/github_phase5_deals_ip_bypass_remove_bridge.py",
            "scripts/cloudflare_phase5_deals_ip_bypass_remove_actions.py",
        ):
            self.assertIn(expected, workflow)
        for forbidden in (
            "workflow_dispatch",
            "wrangler ",
            "curl ",
            "CLOUDFLARE_TUNNEL_API_TOKEN:",
            "CLOUDFLARE_WRITE_API_TOKEN:",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_source_contains_no_reusable_policy_delete_or_generic_method(self):
        source = (
            ROOT / "scripts/cloudflare_phase5_deals_ip_bypass_remove.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(source.count('method="DELETE"'), 1)
        self.assertNotIn("/access/policies/{policy_id}", source)
        self.assertNotIn("method: str", source)
        self.assertNotIn("requests.", source)


if __name__ == "__main__":
    unittest.main()
