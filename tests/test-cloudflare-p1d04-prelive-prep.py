#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_browser_sso_prelive_prep as prep  # noqa: E402
import cloudflare_owner_browser_sso_prelive_prep_actions as prep_actions  # noqa: E402
import github_p1d04_prelive_prep_bridge as prep_bridge  # noqa: E402

ACCOUNT_ID = "a" * 32
AUTH_DOMAIN = "private.cloudflareaccess.com"
READ_TOKEN = "r" * 32
WRITE_TOKEN = "w" * 32
SHA = "b" * 40


class FakeGetClient:
    def __init__(self, organization: dict[str, object]) -> None:
        self.organization = organization
        self.paths: list[str] = []

    def get(self, path: str) -> dict[str, object]:
        self.paths.append(path)
        if path == "/user/tokens/verify":
            return {"result": {"status": "active"}}
        if path == f"/accounts/{ACCOUNT_ID}/access/organizations":
            return {"result": self.organization}
        raise AssertionError(f"unexpected GET path: {path}")


def owner_event(body: str) -> dict[str, object]:
    return {
        "action": "created",
        "issue": {"number": 179},
        "comment": {
            "id": 12345,
            "body": body,
            "author_association": "OWNER",
            "performed_via_github_app": None,
            "user": {"login": "rozkalnsandris", "id": 277435981, "type": "User"},
        },
        "sender": {"login": "rozkalnsandris", "id": 277435981, "type": "User"},
    }


class CloudflareP1D04PrelivePrepTests(unittest.TestCase):
    def base_organization(self) -> dict[str, object]:
        return {
            "auth_domain": AUTH_DOMAIN,
            "name": "private-team",
            "deny_unmatched_requests": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "cache_device_posture": True,
            "has_migrated_private_apps": False,
            "trusted_accounts": ["private-account"],
        }

    def test_get_only_prep_builds_private_fingerprint_and_default_rollback(self) -> None:
        client = FakeGetClient(self.base_organization())
        result = prep.execute_prep(client, ACCOUNT_ID)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(client.paths, [f"/accounts/{ACCOUNT_ID}/access/organizations"])
        self.assertFalse(result["forward_request_attempted"])
        self.assertEqual(result["forward_request_count"], 0)
        self.assertFalse(result["mutation_performed"])
        self.assertRegex(result["organization"]["preimage_fingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(result["organization"]["current_session_duration"], "24h")
        self.assertEqual(result["organization"]["current_session_source"], "cloudflare_documented_default")
        self.assertEqual(result["organization"]["target_session_duration"], "720h")
        self.assertEqual(result["organization"]["semantic_diff"], ["session_duration"])
        self.assertEqual(result["rollback"]["target_session_duration"], "24h")
        self.assertFalse(result["rollback"]["automatic"])
        self.assertTrue(result["rollback"]["fresh_get_required"])
        self.assertTrue(result["rollback"]["separate_owner_authorization_required"])
        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn(AUTH_DOMAIN, rendered)
        self.assertNotIn(ACCOUNT_ID, rendered)
        self.assertNotIn("private-account", rendered)

    def test_fingerprint_is_stable_for_equivalent_key_order(self) -> None:
        first = self.base_organization()
        second = dict(reversed(list(first.items())))
        a = prep.execute_prep(FakeGetClient(first), ACCOUNT_ID)
        b = prep.execute_prep(FakeGetClient(second), ACCOUNT_ID)
        self.assertEqual(
            a["organization"]["preimage_fingerprint"],
            b["organization"]["preimage_fingerprint"],
        )

    def test_explicit_current_session_becomes_bounded_rollback_target(self) -> None:
        organization = self.base_organization()
        organization["session_duration"] = "12h"
        result = prep.execute_prep(FakeGetClient(organization), ACCOUNT_ID)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["organization"]["current_session_source"], "api_explicit")
        self.assertEqual(result["rollback"]["target_session_duration"], "12h")

    def test_unknown_field_already_target_and_invalid_session_fail_closed(self) -> None:
        unknown = self.base_organization()
        unknown["surprise_server_field"] = True
        result = prep.execute_prep(FakeGetClient(unknown), ACCOUNT_ID)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reason"], "organization_response_field_unclassified")

        already = self.base_organization()
        already["session_duration"] = "720h"
        result = prep.execute_prep(FakeGetClient(already), ACCOUNT_ID)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reason"], "global_session_already_target")

        invalid = self.base_organization()
        invalid["session_duration"] = "forever"
        result = prep.execute_prep(FakeGetClient(invalid), ACCOUNT_ID)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reason"], "global_session_duration_invalid")

    def test_owner_bridge_binds_issue_owner_sha_and_rejects_rerun_or_app(self) -> None:
        body = f"/rpi5-p1d04 prep HEAD={SHA} CANARY={prep_bridge.CANARY_ID}"
        event = owner_event(body)
        result = prep_bridge.authorize_event(
            event,
            repository="rozkalnsandris/RPi5_main",
            github_sha=SHA,
            run_attempt="1",
        )
        self.assertEqual(result["expected_sha"], SHA)
        self.assertEqual(result["canary"], prep_bridge.CANARY_ID)

        with self.assertRaisesRegex(prep_bridge.AuthorizationError, "workflow_rerun_forbidden"):
            prep_bridge.authorize_event(
                event,
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="2",
            )

        app_event = json.loads(json.dumps(event))
        app_event["comment"]["performed_via_github_app"] = {"id": 1}
        with self.assertRaisesRegex(prep_bridge.AuthorizationError, "app_authored_comment_forbidden"):
            prep_bridge.authorize_event(
                app_event,
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

        drift_event = json.loads(json.dumps(event))
        drift_event["comment"]["body"] = (
            f"/rpi5-p1d04 prep HEAD={'c' * 40} CANARY={prep_bridge.CANARY_ID}"
        )
        with self.assertRaisesRegex(prep_bridge.AuthorizationError, "command_sha_not_event_main"):
            prep_bridge.authorize_event(
                drift_event,
                repository="rozkalnsandris/RPi5_main",
                github_sha=SHA,
                run_attempt="1",
            )

    def test_actions_adapter_rejects_sha_rerun_and_equal_tokens_before_prep(self) -> None:
        base_env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "issue_comment",
            "P1D04_PRELIVE_CANARY": prep.CANARY_ID,
            "P1D04_PRELIVE_EXPECTED_SHA": SHA,
            "GITHUB_SHA": SHA,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "rozkalnsandris/RPi5_main",
            "GITHUB_TOKEN": "g" * 32,
            "CLOUDFLARE_P1D04_ACCOUNT_ID": ACCOUNT_ID,
            "CLOUDFLARE_P1D04_READ_API_TOKEN": READ_TOKEN,
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN": READ_TOKEN,
        }
        with mock.patch.dict(os.environ, base_env, clear=True), mock.patch.object(
            prep_actions, "fetch_and_validate_exact_main", return_value={"all_required_workflows_green": True}
        ), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(prep_actions.main(), 2)
            self.assertIn("read_and_write_tokens_must_differ", output.getvalue())

        rerun_env = dict(base_env)
        rerun_env["GITHUB_RUN_ATTEMPT"] = "2"
        with mock.patch.dict(os.environ, rerun_env, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(prep_actions.main(), 2)
            self.assertIn("workflow_rerun_forbidden", output.getvalue())

        drift_env = dict(base_env)
        drift_env["GITHUB_SHA"] = "d" * 40
        with mock.patch.dict(os.environ, drift_env, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(prep_actions.main(), 2)
            self.assertIn("exact_main_sha_binding_invalid", output.getvalue())

    def test_actions_adapter_verifies_both_tokens_then_runs_get_only_prep(self) -> None:
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "issue_comment",
            "P1D04_PRELIVE_CANARY": prep.CANARY_ID,
            "P1D04_PRELIVE_EXPECTED_SHA": SHA,
            "GITHUB_SHA": SHA,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "rozkalnsandris/RPi5_main",
            "GITHUB_TOKEN": "g" * 32,
            "CLOUDFLARE_P1D04_ACCOUNT_ID": ACCOUNT_ID,
            "CLOUDFLARE_P1D04_READ_API_TOKEN": READ_TOKEN,
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN": WRITE_TOKEN,
        }
        clients: list[FakeGetClient] = []

        def client_factory(token: str, _api_base: str) -> FakeGetClient:
            client = FakeGetClient(self.base_organization())
            clients.append(client)
            return client

        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
            prep_actions, "fetch_and_validate_exact_main", return_value={"all_required_workflows_green": True}
        ), mock.patch.object(prep_actions, "CloudflareGetClient", side_effect=client_factory), redirect_stdout(
            io.StringIO()
        ) as output:
            self.assertEqual(prep_actions.main(), 0)
            decoded = json.loads(output.getvalue())
            self.assertEqual(decoded["result"], "PASS")
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0].paths, ["/user/tokens/verify", f"/accounts/{ACCOUNT_ID}/access/organizations"])
        self.assertEqual(clients[1].paths, ["/user/tokens/verify"])

    def test_workflow_and_adapter_have_no_cloudflare_write_authority(self) -> None:
        workflow = (ROOT / ".github/workflows/cloudflare-p1d04-prelive-prep.yml").read_text(encoding="utf-8")
        live_workflow = (ROOT / ".github/workflows/cloudflare-p1d04-browser-sso-session.yml").read_text(encoding="utf-8")
        adapter = (ROOT / "scripts/cloudflare_owner_browser_sso_prelive_prep_actions.py").read_text(encoding="utf-8")
        prep_source = (ROOT / "scripts/cloudflare_owner_browser_sso_prelive_prep.py").read_text(encoding="utf-8")

        self.assertIn("contents: read", workflow)
        self.assertIn("actions: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("/rpi5-p1d04 prep ", workflow)
        self.assertIn("/rpi5-p1d04 apply ", live_workflow)
        self.assertNotIn("startsWith(github.event.comment.body, '/rpi5-p1d04 ')", live_workflow)
        for secret in (
            "CLOUDFLARE_P1D04_ACCOUNT_ID",
            "CLOUDFLARE_P1D04_READ_API_TOKEN",
            "CLOUDFLARE_P1D04_WRITE_API_TOKEN",
        ):
            self.assertIn(secret, workflow)
        combined = adapter + prep_source
        for forbidden in (
            "CloudflareOrganizationSessionUpdateClient",
            "update_global_session(",
            "method=\"PUT\"",
            "method=\"POST\"",
            "method=\"PATCH\"",
            "method=\"DELETE\"",
        ):
            self.assertNotIn(forbidden, combined)

    def test_contract_and_docs_make_prelive_gate_explicit_and_non_authorizing(self) -> None:
        contract = json.loads(
            (ROOT / "ops/contracts/cloudflare-p1d-browser-sso.json").read_text(encoding="utf-8")
        )
        prelive = contract["prelive_preparation"]
        self.assertEqual(prelive["canary_id"], prep.CANARY_ID)
        self.assertEqual(prelive["workflow"], ".github/workflows/cloudflare-p1d04-prelive-prep.yml")
        self.assertTrue(prelive["get_only"])
        self.assertEqual(prelive["cloudflare_write_primitives"], [])
        self.assertFalse(prelive["source_merge_authorizes_execution"])
        self.assertTrue(prelive["fresh_separate_owner_authorization_required"])
        self.assertEqual(prelive["rollback"]["omitted_session_duration_target"], "24h")
        docs = (ROOT / "docs/CLOUDFLARE_P1D_BROWSER_SSO_DECISION.md").read_text(encoding="utf-8")
        self.assertIn("## No-RDC P1D-04 pre-LIVE preparation", docs)
        self.assertIn("/rpi5-p1d04 prep HEAD=<exact-main-sha> CANARY=p1d-04-prelive-prep", docs)
        self.assertIn("separate owner authorization", docs)


if __name__ == "__main__":
    unittest.main()
