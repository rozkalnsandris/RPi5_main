#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "cloudflare_rdc_operator.py"
CONTRACT = ROOT / "ops" / "contracts" / "cloudflare-rdc-operator-v1.json"

spec = importlib.util.spec_from_file_location("cloudflare_rdc_operator", SOURCE)
assert spec and spec.loader
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

WILDCARD_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
TARGET_ID = "33333333-3333-4333-8333-333333333333"


def wildcard_app() -> dict:
    return {
        "id": WILDCARD_ID,
        "name": "homelab-private",
        "type": "self_hosted",
        "domain": "*.rozkalns.net",
        "updated_at": "before",
    }


def other_app() -> dict:
    return {
        "id": OTHER_ID,
        "name": "Hermes Tech Public",
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": "tech.rozkalns.net"}],
    }


def target_app() -> dict:
    return {
        "id": TARGET_ID,
        "name": "Coloring Pages Public",
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": "coloring.rozkalns.net"}],
    }


class FakeClient:
    def __init__(self) -> None:
        self.created_bodies = []
        self.list_calls = 0

    def list_applications(self, account_id: str):
        self.list_calls += 1
        if self.list_calls == 1:
            return [wildcard_app(), other_app()]
        wildcard = wildcard_app()
        wildcard["updated_at"] = "after"
        return [wildcard, other_app(), target_app()]

    def create_application(self, account_id: str, body: dict):
        self.created_bodies.append(body)
        return target_app()

    def list_application_policies(self, account_id: str, app_id: str):
        self.assert_id = app_id
        return [{
            "id": "44444444-4444-4444-8444-444444444444",
            "name": "public-access",
            "decision": "bypass",
            "include": [{"everyone": {}}],
            "require": [],
            "exclude": [],
        }]


class CloudflareRdcOperatorTests(unittest.TestCase):
    def test_create_body_is_one_exact_inline_public_bypass(self) -> None:
        self.assertEqual(
            op.build_create_body(),
            {
                "name": "Coloring Pages Public",
                "type": "self_hosted",
                "destinations": [
                    {"type": "public", "uri": "coloring.rozkalns.net"}
                ],
                "policies": [{
                    "name": "public-access",
                    "decision": "bypass",
                    "include": [{"everyone": {}}],
                }],
            },
        )

    def test_preflight_accepts_parent_wildcard_and_absent_exact_app(self) -> None:
        report = op.preflight_applications([wildcard_app(), other_app()])
        self.assertTrue(report["parent_wildcard_present"])
        self.assertTrue(report["exact_target_absent"])
        self.assertEqual(
            set(report["preexisting_apps"]), {WILDCARD_ID, OTHER_ID}
        )

    def test_preflight_refuses_existing_exact_target(self) -> None:
        with self.assertRaisesRegex(
            op.OperatorError, "exact_target_application_already_exists"
        ):
            op.preflight_applications([wildcard_app(), target_app()])

    def test_preflight_refuses_missing_parent_wildcard(self) -> None:
        with self.assertRaisesRegex(
            op.OperatorError, "parent_wildcard_missing_or_ambiguous"
        ):
            op.preflight_applications([other_app()])

    def test_apply_uses_one_create_call_and_get_only_post_verification(self) -> None:
        client = FakeClient()
        result = op.run_operator(client, "a" * 32, apply=True)
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["mutation_performed"])
        self.assertEqual(len(client.created_bodies), 1)
        self.assertEqual(client.created_bodies[0], op.build_create_body())
        self.assertEqual(client.assert_id, TARGET_ID)

    def test_dry_run_never_calls_create(self) -> None:
        client = FakeClient()
        result = op.run_operator(client, "a" * 32, apply=False)
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["apply_ready"])
        self.assertEqual(client.created_bodies, [])
        self.assertEqual(client.list_calls, 1)

    def test_post_write_rejects_unrelated_application_change(self) -> None:
        before = op.preflight_applications([wildcard_app(), other_app()])
        changed = other_app()
        changed["name"] = "changed"
        policies = [{
            "name": "public-access",
            "decision": "bypass",
            "include": [{"everyone": {}}],
        }]
        with self.assertRaisesRegex(
            op.OperatorError, "preexisting_application_changed_after_write"
        ):
            op.verify_post_write(
                before,
                [wildcard_app(), changed, target_app()],
                policies,
                TARGET_ID,
            )

    def test_contract_separates_access_tunnel_and_dns_credentials(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        lanes = contract["secret_lanes"]
        self.assertEqual(set(lanes), {"access", "tunnel", "dns"})
        self.assertEqual(len({item["path"] for item in lanes.values()}), 3)
        self.assertTrue(lanes["access"]["implemented"])
        self.assertFalse(lanes["tunnel"]["implemented"])
        self.assertFalse(lanes["dns"]["implemented"])
        self.assertIn(
            "Access: Apps and Policies",
            lanes["access"]["cloudflare_permission"],
        )
        self.assertEqual(lanes["dns"]["scope"], "zone:rozkalns.net")

    def test_contract_enforces_single_write_and_no_retry_or_rollback(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        operation = contract["operations"][0]
        self.assertEqual(operation["max_write_requests"], 1)
        self.assertEqual(operation["cloudflare_method"], "POST")
        forbidden = set(contract["forbidden"])
        self.assertIn("automatic retry", forbidden)
        self.assertIn(
            "automatic rollback or cleanup after write uncertainty",
            forbidden,
        )
        self.assertIn("API Tokens Edit permission", forbidden)


if __name__ == "__main__":
    unittest.main()
