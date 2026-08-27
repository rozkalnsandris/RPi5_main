#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.protocol import (  # noqa: E402
    AUTHORIZATION_REPOSITORY,
    ProtocolError,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from deploy_executor.state import InvalidTransition, ReplayError, StateStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
REPOSITORY_ID = 1328835922
OPERATOR_APP_ID = 1144995
SERVER_TIME = datetime(2026, 8, 27, 20, 5, 0, tzinfo=timezone.utc)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def replace_payload(issue: dict, transform):
    marker = "<!-- rozkalns-live-auth:v1 -->\n```json\n"
    end = "\n```\n<!-- /rozkalns-live-auth:v1 -->"
    before, rest = issue["body"].split(marker, 1)
    raw, after = rest.split(end, 1)
    payload = json.loads(raw)
    transform(payload)
    issue["body"] = before + marker + json.dumps(payload, indent=2) + end + after


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.issue = load_fixture("live_auth_valid.json")
        self.queue = load_fixture("queue_ready_valid.json")

    def accept(self, issue=None, server_time=SERVER_TIME, governance_ok=True):
        return accept_issue(
            self.issue if issue is None else issue,
            repository_id=REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=server_time,
            governance_ok=governance_ok,
            approved_operator_app_ids=frozenset({OPERATOR_APP_ID}),
        )

    def assert_code(self, code: str, fn):
        with self.assertRaises(ProtocolError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_valid_owner_authored_request_via_operator_integration(self):
        accepted = self.accept()
        self.assertEqual(accepted.request_id, "4a5da3f4-ccf1-4c63-ae8f-3eb8506f2b61")
        self.assertEqual(accepted.performed_via_github_app_id, OPERATOR_APP_ID)
        self.assertEqual(accepted.performed_via_github_app_slug, "chatgpt-codex-connector")
        validate_queue_binding(accepted, self.queue)

    def test_unapproved_operator_integration_rejected(self):
        issue = copy.deepcopy(self.issue)
        issue["performed_via_github_app"]["id"] = 999999
        self.assert_code("UNAPPROVED_OPERATOR_INTEGRATION", lambda: self.accept(issue))

    def test_bot_authored_rejected_even_if_numeric_id_matches(self):
        issue = copy.deepcopy(self.issue)
        issue["user"]["type"] = "Bot"
        self.assert_code("BOT_AUTHOR_REJECTED", lambda: self.accept(issue))

    def test_wrong_owner_rejected(self):
        issue = copy.deepcopy(self.issue)
        issue["user"]["id"] = 42
        self.assert_code("WRONG_OWNER", lambda: self.accept(issue))

    def test_governance_unknown_fails_closed(self):
        self.assert_code("GOVERNANCE_UNTRUSTED", lambda: self.accept(governance_ok=False))

    def test_malformed_or_unknown_schema_rejected(self):
        issue = copy.deepcopy(self.issue)
        replace_payload(issue, lambda p: p.__setitem__("unexpected", True))
        self.assert_code("MALFORMED_SCHEMA", lambda: self.accept(issue))

    def test_duplicate_json_key_rejected(self):
        issue = copy.deepcopy(self.issue)
        issue["body"] = issue["body"].replace(
            '"schema": "rozkalns.live-auth.v1",',
            '"schema": "rozkalns.live-auth.v1",\n  "schema": "rozkalns.live-auth.v1",',
            1,
        )
        self.assert_code("DUPLICATE_JSON_KEY", lambda: self.accept(issue))

    def test_expired_rejected(self):
        self.assert_code(
            "AUTH_EXPIRED",
            lambda: self.accept(server_time=SERVER_TIME + timedelta(seconds=301)),
        )

    def test_material_future_clock_skew_rejected(self):
        issue = copy.deepcopy(self.issue)
        issue["created_at"] = "2026-08-27T20:06:00Z"
        self.assert_code("SERVER_TIME_SKEW", lambda: self.accept(issue))

    def test_edited_raw_body_rejected_even_when_payload_semantics_unchanged(self):
        accepted = self.accept()
        edited = copy.deepcopy(self.issue)
        edited["body"] += "\n"
        self.assert_code(
            "RAW_BODY_DRIFT",
            lambda: verify_authorization_unchanged(
                accepted,
                edited,
                server_time=SERVER_TIME,
                governance_ok=True,
                approved_operator_app_ids=frozenset({OPERATOR_APP_ID}),
            ),
        )

    def test_queue_issue_and_ready_state_are_bound(self):
        accepted = self.accept()

        wrong_issue = copy.deepcopy(self.queue)
        wrong_issue["issue_number"] += 1
        self.assert_code(
            "QUEUE_BINDING_MISMATCH",
            lambda: validate_queue_binding(accepted, wrong_issue),
        )

        not_ready = copy.deepcopy(self.queue)
        not_ready["state"] = "WAITING"
        self.assert_code("QUEUE_NOT_READY", lambda: validate_queue_binding(accepted, not_ready))

    def test_queue_sha_target_and_operation_mismatch_rejected(self):
        accepted = self.accept()
        variants = {
            "source_sha": "f" * 40,
            "target_alias": "different-target",
            "operation_id": "hermes-tech.other-operation.v1",
        }
        for key, value in variants.items():
            with self.subTest(key=key):
                queue = copy.deepcopy(self.queue)
                queue[key] = value
                self.assert_code(
                    "QUEUE_BINDING_MISMATCH",
                    lambda q=queue: validate_queue_binding(accepted, q),
                )

    def test_unsupported_rollback_policy_rejected(self):
        issue = copy.deepcopy(self.issue)
        replace_payload(issue, lambda p: p.__setitem__("rollback_policy", "AUTO_ANYTHING"))
        self.assert_code("UNSUPPORTED_ROLLBACK_POLICY", lambda: self.accept(issue))

    def test_title_target_must_match_payload(self):
        issue = copy.deepcopy(self.issue)
        issue["title"] = "[LIVE-AUTH][PENDING] another-target"
        self.assert_code("TITLE_TARGET_MISMATCH", lambda: self.accept(issue))


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        issue = load_fixture("live_auth_valid.json")
        self.accepted = accept_issue(
            issue,
            repository_id=REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=SERVER_TIME,
            governance_ok=True,
            approved_operator_app_ids=frozenset({OPERATOR_APP_ID}),
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def discover(self, store: StateStore, *, issue_id=None, request_id=None):
        return store.discover(
            repository_id=self.accepted.repository_id,
            issue_id=self.accepted.issue_id if issue_id is None else issue_id,
            request_id=self.accepted.request_id if request_id is None else request_id,
            canonical_payload_sha256=self.accepted.canonical_payload_sha256,
            raw_body_sha256=self.accepted.raw_body_sha256,
        )

    def test_duplicate_request_or_issue_identity_is_replay(self):
        with StateStore(self.db_path) as store:
            self.discover(store)
            with self.assertRaises(ReplayError):
                self.discover(store, issue_id=self.accepted.issue_id + 1)
            with self.assertRaises(ReplayError):
                self.discover(
                    store,
                    request_id="c9a75889-3c34-4d1c-9f37-b750fef9c4be",
                )

    def test_state_transitions_restart_and_consumption_are_fail_closed(self):
        with StateStore(self.db_path) as store:
            self.discover(store)
            with self.assertRaises(InvalidTransition):
                store.transition(self.accepted.request_id, "SUCCEEDED")
            store.transition(self.accepted.request_id, "VALIDATING")
            store.transition(self.accepted.request_id, "ACCEPTED")
            consumed = store.consume(self.accepted.request_id)
            self.assertEqual(consumed.state, "CONSUMED")
            self.assertIsNotNone(consumed.consumed_at)

        with StateStore(self.db_path) as restarted:
            self.assertEqual(restarted.get(self.accepted.request_id).state, "CONSUMED")
            with self.assertRaises(ReplayError):
                restarted.consume(self.accepted.request_id)
            restarted.transition(self.accepted.request_id, "VERIFYING")
            restarted.transition(self.accepted.request_id, "SUCCEEDED")
            with self.assertRaises(InvalidTransition):
                restarted.transition(self.accepted.request_id, "VERIFYING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
