#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MODULE_PATH = ROOT / "scripts" / "cloudflare_phase4_admin_access_scope_actions.py"
SPEC = importlib.util.spec_from_file_location("phase4_access", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
phase4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase4)

BRIDGE_PATH = ROOT / "scripts" / "github_phase4_admin_access_scope_bridge.py"
BRIDGE_SPEC = importlib.util.spec_from_file_location("phase4_bridge", BRIDGE_PATH)
assert BRIDGE_SPEC is not None and BRIDGE_SPEC.loader is not None
bridge = importlib.util.module_from_spec(BRIDGE_SPEC)
BRIDGE_SPEC.loader.exec_module(bridge)

WORKFLOW_PATH = ROOT / ".github" / "workflows" / "cloudflare-phase4-admin-access-scope.yml"
CONTRACT_PATH = ROOT / "ops" / "contracts" / "admin-zone-verification-v1.json"
POLICY_PATH = ROOT / "ops" / "contracts" / "cloudflare-hostname-policy.yaml"

OWNER_ID = 277435981
SHA = "a" * 40


def event(body: str) -> dict:
    return {
        "action": "created",
        "issue": {"number": 819},
        "comment": {
            "id": 123,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": None,
            "user": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": OWNER_ID, "type": "User"},
    }


def fake_state(contract: dict) -> dict:
    apps = []
    policies = {}
    for index, projected in enumerate(contract["service_projections"], start=1):
        app_id = f"{index:08d}-1111-4111-8111-{index:012d}"
        apps.append({
            "id": app_id,
            "type": "self_hosted",
            "domain": projected["hostname"],
            "aud": f"raw-aud-{index}",
        })
        if projected["expected_access_application_scope"] == "exact-owner":
            include = [{"email": {"email": "owner_identity_redacted"}}]
        else:
            include = [{"everyone": {}}]
        policies[app_id] = [{
            "decision": "allow",
            "include": include,
            "require": [],
            "exclude": [],
        }]
    return {"organization": {}, "apps": apps, "policies": policies}


class Phase4AdminAccessScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = phase4.load_registry(POLICY_PATH)

    def test_owner_command_is_exact_issue_and_sha_bound(self) -> None:
        body = f"/rpi5-p4-access-scope check HEAD={SHA} CANARY=phase4-admin-access-scope-v1"
        out = bridge.authorize_event(
            event(body),
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(out["expected_sha"], SHA)
        broken = event(body)
        broken["issue"]["number"] = 818
        with self.assertRaisesRegex(bridge.AuthorizationError, "issue_mismatch"):
            bridge.authorize_event(
                broken,
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_exact_apps_pass_and_report_is_sanitized(self) -> None:
        state = fake_state(self.contract)
        report = phase4.build_report(self.contract, self.registry, state)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(report["services"]), 8)
        by_host = {item["hostname"]: item for item in report["services"]}
        self.assertEqual(by_host["dash.rozkalns.net"]["access_scope_class"], "exact-owner")
        self.assertTrue(all(item["bypass_present"] is False for item in report["services"]))

        rendered = json.dumps(report, sort_keys=True)
        for forbidden in (
            "owner_identity_redacted",
            "raw-aud-",
            "1111-4111-8111",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_wildcard_covering_non_admin_is_broader(self) -> None:
        state = fake_state(self.contract)
        first_id = state["apps"][0]["id"]
        state["apps"][0]["domain"] = "*.rozkalns.net"
        state["policies"][first_id] = [{
            "decision": "bypass",
            "include": [{"everyone": {}}],
        }]
        report = phase4.build_report(self.contract, self.registry, state)
        first = report["services"][0]
        self.assertEqual(first["access_scope_class"], "broader-than-admin")
        self.assertTrue(first["bypass_present"])
        self.assertEqual(first["result"], "FAIL")
        self.assertEqual(report["result"], "BLOCKED")

    def test_missing_application_fails_closed(self) -> None:
        state = fake_state(self.contract)
        state["apps"] = state["apps"][1:]
        report = phase4.build_report(self.contract, self.registry, state)
        self.assertEqual(report["services"][0]["access_scope_class"], "missing")
        self.assertEqual(report["services"][0]["result"], "FAIL")

    def test_workflow_reuses_only_p1d03_read_secret_lane(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("CLOUDFLARE_P1D03_ACCOUNT_ID", workflow)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", workflow)
        for forbidden in (
            "CLOUDFLARE_P1D03_OWNER_EMAIL",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
            "CLOUDFLARE_WRITE_API_TOKEN",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_actions_output_contract_contains_no_raw_identifier_fields(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden_output_key in (
            '"account_id":',
            '"app_id":',
            '"policy_id":',
            '"aud":',
            '"email":',
            '"raw_api_payload":',
        ):
            self.assertNotIn(forbidden_output_key, source)
        self.assertIn("CloudflareGetClient", source)
        self.assertIn("collect_state", source)


if __name__ == "__main__":
    unittest.main()
