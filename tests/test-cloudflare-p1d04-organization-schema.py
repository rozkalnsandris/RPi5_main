#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_browser_sso_prelive_prep as prep  # noqa: E402
import cloudflare_owner_browser_sso_session_update as session_update  # noqa: E402

ACCOUNT_ID = "a" * 32
SERVICE_TOKEN_INACTIVITY = {
    "action": "disable",
    "enabled": True,
    "inactivity_threshold_days": 30,
}


class FakeGetClient:
    def get(self, path: str) -> dict[str, object]:
        if path == f"/accounts/{ACCOUNT_ID}/access/organizations":
            return {"result": base_organization()}
        raise AssertionError(f"unexpected GET path: {path}")


def base_organization() -> dict[str, object]:
    return {
        "auth_domain": "private.cloudflareaccess.com",
        "name": "private-team",
        "service_token_inactivity": dict(SERVICE_TOKEN_INACTIVITY),
    }


class CloudflareP1D04OrganizationSchemaTests(unittest.TestCase):
    def test_documented_service_token_inactivity_is_preserved(self) -> None:
        plan = session_update.build_update_plan(base_organization())
        self.assertEqual(plan.payload["service_token_inactivity"], SERVICE_TOKEN_INACTIVITY)
        self.assertEqual(plan.payload["session_duration"], "720h")
        self.assertEqual(
            session_update._semantic_diff(plan.before_writable, plan.payload),
            {"session_duration"},
        )
        contract = json.loads(
            (ROOT / "ops/contracts/cloudflare-p1d-browser-sso.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            "service_token_inactivity",
            contract["organization_session_writer"]["writable_projection_fields"],
        )

    def test_service_token_inactivity_validation_fails_closed(self) -> None:
        invalid_values = (
            None,
            {},
            {"action": "disable", "enabled": True},
            {**SERVICE_TOKEN_INACTIVITY, "unexpected": True},
            {**SERVICE_TOKEN_INACTIVITY, "action": "archive"},
            {**SERVICE_TOKEN_INACTIVITY, "enabled": 1},
            {**SERVICE_TOKEN_INACTIVITY, "inactivity_threshold_days": True},
            {**SERVICE_TOKEN_INACTIVITY, "inactivity_threshold_days": 29},
            {**SERVICE_TOKEN_INACTIVITY, "inactivity_threshold_days": 366},
            {**SERVICE_TOKEN_INACTIVITY, "inactivity_threshold_days": "30"},
        )
        for value in invalid_values:
            organization = base_organization()
            organization["service_token_inactivity"] = value
            with self.subTest(value=value), self.assertRaises(session_update.AuditError):
                session_update.build_update_plan(organization)

    def test_unknown_top_level_field_still_blocks(self) -> None:
        organization = base_organization()
        organization["future_unknown_field"] = True
        with self.assertRaisesRegex(
            session_update.AuditError,
            "organization_response_field_unclassified",
        ):
            session_update.build_update_plan(organization)

    def test_prelive_accepts_schema_without_emitting_values(self) -> None:
        result = prep.execute_prep(FakeGetClient(), ACCOUNT_ID)
        self.assertEqual(result["result"], "PASS")
        self.assertFalse(result["forward_request_attempted"])
        self.assertFalse(result["mutation_performed"])
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("service_token_inactivity", rendered)
        self.assertNotIn("disable", rendered)


if __name__ == "__main__":
    unittest.main()
