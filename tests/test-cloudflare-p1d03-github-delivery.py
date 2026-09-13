#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cloudflare_owner_browser_sso_preflight_actions as p1d03_actions  # noqa: E402
import github_p1d03_browser_sso_bridge as p1d03_bridge  # noqa: E402

CONTRACT = ROOT / "ops/contracts/cloudflare-p1d03-github-delivery.json"
WORKFLOW = ROOT / ".github/workflows/cloudflare-p1d03-browser-sso-preflight.yml"
ADAPTER = ROOT / "scripts/cloudflare_owner_browser_sso_preflight_actions.py"
DOC = ROOT / "docs/CLOUDFLARE_P1D03_NO_RDC_DELIVERY.md"


class CloudflareP1D03GitHubDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")

    @staticmethod
    def owner_event(sha: str) -> dict[str, object]:
        return {
            "action": "created",
            "issue": {"number": 179},
            "comment": {
                "id": 12345,
                "body": f"/rpi5-p1d03 check HEAD={sha} CANARY={p1d03_bridge.CANARY_ID}",
                "author_association": "OWNER",
                "performed_via_github_app": None,
                "user": {"login": "rozkalnsandris", "id": 277435981, "type": "User"},
            },
            "sender": {"login": "rozkalnsandris", "id": 277435981, "type": "User"},
        }

    def test_owner_comment_authorizer_is_issue_sha_and_user_bound(self) -> None:
        sha = "a" * 40
        event = self.owner_event(sha)
        result = p1d03_bridge.authorize_event(
            event,
            repository="rozkalnsandris/RPi5_main",
            github_sha=sha,
            run_attempt="1",
        )
        self.assertEqual(result["expected_sha"], sha)
        self.assertEqual(result["canary"], p1d03_bridge.CANARY_ID)

        with self.assertRaisesRegex(p1d03_bridge.AuthorizationError, "workflow_rerun_forbidden"):
            p1d03_bridge.authorize_event(event, repository="rozkalnsandris/RPi5_main", github_sha=sha, run_attempt="2")

        app_event = json.loads(json.dumps(event))
        app_event["comment"]["performed_via_github_app"] = {"id": 1}
        with self.assertRaisesRegex(p1d03_bridge.AuthorizationError, "app_authored_comment_forbidden"):
            p1d03_bridge.authorize_event(app_event, repository="rozkalnsandris/RPi5_main", github_sha=sha, run_attempt="1")

        wrong_issue = json.loads(json.dumps(event))
        wrong_issue["issue"]["number"] = 180
        with self.assertRaisesRegex(p1d03_bridge.AuthorizationError, "issue_mismatch"):
            p1d03_bridge.authorize_event(wrong_issue, repository="rozkalnsandris/RPi5_main", github_sha=sha, run_attempt="1")

        drift = json.loads(json.dumps(event))
        drift["comment"]["body"] = f"/rpi5-p1d03 check HEAD={'b' * 40} CANARY={p1d03_bridge.CANARY_ID}"
        with self.assertRaisesRegex(p1d03_bridge.AuthorizationError, "command_sha_not_event_main"):
            p1d03_bridge.authorize_event(drift, repository="rozkalnsandris/RPi5_main", github_sha=sha, run_attempt="1")

    def test_contract_defines_get_only_non_authorizing_delivery(self) -> None:
        delivery = self.contract["delivery"]
        self.assertEqual(delivery["workflow"], ".github/workflows/cloudflare-p1d03-browser-sso-preflight.yml")
        self.assertEqual(delivery["trigger_issue"], 179)
        self.assertTrue(delivery["exact_sha_bound"])
        self.assertFalse(delivery["workflow_rerun_allowed"])
        self.assertEqual(delivery["github_write_permissions"], [])
        self.assertEqual(delivery["cloudflare_allowed_methods"], ["GET"])
        self.assertEqual(delivery["cloudflare_write_methods"], [])
        self.assertEqual(
            delivery["cloudflare_secret_inputs"],
            ["CLOUDFLARE_P1D03_ACCOUNT_ID", "CLOUDFLARE_P1D03_READ_API_TOKEN", "CLOUDFLARE_P1D03_OWNER_EMAIL"],
        )
        self.assertFalse(delivery["secret_provisioning_authorized_by_source"])
        self.assertFalse(delivery["source_merge_authorizes_workflow_execution"])

    def test_workflow_is_read_only_and_has_no_write_secret_surface(self) -> None:
        self.assertIn("contents: read", self.workflow)
        self.assertIn("actions: read", self.workflow)
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("issues: write", self.workflow)
        self.assertNotIn("pull-requests: write", self.workflow)
        self.assertNotIn("CLOUDFLARE_P1D04_WRITE_API_TOKEN", self.workflow)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_actions_adapter_contains_no_cloudflare_write_client_or_method(self) -> None:
        self.assertIn("CloudflareGetClient", self.adapter)
        self.assertNotIn("CloudflareOrganizationSessionUpdateClient", self.adapter)
        for token in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"'):
            self.assertNotIn(token, self.adapter)

    def test_actions_adapter_runs_existing_preflight_after_exact_main_gate(self) -> None:
        sha = "c" * 40
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "rozkalnsandris/RPi5_main",
            "GITHUB_SHA": sha,
            "GITHUB_TOKEN": "g" * 40,
            "P1D03_EXPECTED_SHA": sha,
            "P1D03_CANARY": p1d03_actions.CANARY_ID,
            "CLOUDFLARE_P1D03_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_P1D03_READ_API_TOKEN": "t" * 40,
            "CLOUDFLARE_P1D03_OWNER_EMAIL": "owner@example.com",
        }
        report = {
            "schema_version": 1,
            "audit": p1d03_actions.AUDIT_NAME,
            "canonical_issue": 179,
            "result": "PASS",
            "mutation_performed": False,
            "global_session": {"current_duration": "24h", "target_duration": "720h", "change_required": True},
        }
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(p1d03_actions, "fetch_and_validate_exact_main") as gate, \
             mock.patch.object(p1d03_actions, "CloudflareGetClient") as client_cls, \
             mock.patch.object(p1d03_actions, "collect_state", return_value={"state": "private"}) as collect, \
             mock.patch.object(p1d03_actions, "build_report", return_value=report) as build, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = p1d03_actions.main()
        self.assertEqual(rc, 0)
        gate.assert_called_once()
        client_cls.assert_called_once_with("t" * 40, p1d03_actions.DEFAULT_API_BASE)
        collect.assert_called_once()
        build.assert_called_once_with("owner@example.com", {"state": "private"})
        emitted = json.loads(stdout.getvalue())
        self.assertEqual(emitted["result"], "PASS")
        self.assertFalse(emitted["mutation_performed"])

    def test_doc_states_raw_api_evidence_and_separate_live_boundary(self) -> None:
        self.assertIn("GET-only", self.doc)
        self.assertIn("CLOUDFLARE_P1D03_READ_API_TOKEN", self.doc)
        self.assertIn("separate P1D-04 credential/LIVE authorization boundary", self.doc)


if __name__ == "__main__":
    unittest.main()
