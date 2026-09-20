#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v10_dispatch_caller as caller
from deploy_executor import weather_operator_upgrade_v9_dispatch_caller as legacy

PREDECESSOR = "4ed279e04b240858fc8a2ce69e95f9c546e3a26b"
ENTRYPOINT = ROOT / "ops/bin/rozkalns-weather-operator-v9-dispatch-caller"
SUCCESSOR = ROOT / "ops/lib/deploy_executor/weather_operator_upgrade_v10_dispatch_caller.py"
LEGACY = ROOT / "ops/lib/deploy_executor/weather_operator_upgrade_v9_dispatch_caller.py"
REFRESH = ROOT / "scripts/refresh-weather-operator-v10-successor-dispatch-caller.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-dispatch-caller-refresh.json"


class FakeClient:
    def __init__(self, rows: list[dict[str, object]], now: datetime):
        self.rows = rows
        self.now = now

    def get_json(self, path: str):
        if path == "/repos/rozkalnsandris/ops-workflows":
            return SimpleNamespace(
                value={"id": legacy.AUTHORIZATION_REPOSITORY_ID, "full_name": legacy.AUTHORIZATION_REPOSITORY},
                next_url=None,
                server_time=self.now,
            )
        return SimpleNamespace(value=self.rows, next_url=None, server_time=self.now)


def payload(request_id: str = "weather-v10-test-request") -> dict[str, object]:
    return {
        "schema": caller.AUTH_SCHEMA,
        "request_id": request_id,
        "queue_issue": 86,
        "source_sha": "a" * 40,
        "operation_id": caller.OPERATION_ID,
        "target_alias": caller.TARGET_ALIAS,
        "expected_predecessor_sha256": caller.OLD_SHA256,
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in caller.MUTATION_BUDGET
        ],
        "rollback_policy": "NONE",
        "exclusions": list(caller.REQUIRED_EXCLUSIONS),
    }


def issue(now: datetime, *, number: int = 87, title: str = caller.AUTH_TITLE, request_id: str = "weather-v10-test-request", age: int = 0) -> dict[str, object]:
    body = caller.AUTH_START + "\n```json\n" + json.dumps(payload(request_id), sort_keys=True, separators=(",", ":")) + "\n```\n" + caller.AUTH_END
    return {
        "id": 900000 + number,
        "number": number,
        "state": "open",
        "title": title,
        "body": body,
        "user": {"id": 277435981, "type": "User"},
        "performed_via_github_app": None,
        "created_at": (now - timedelta(seconds=age)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def git_show(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout


def git_mode(path: Path) -> str:
    row = subprocess.run(
        ["git", "ls-files", "-s", "--", str(path.relative_to(ROOT))], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.strip()
    return row.split()[0] if row else ""


class WeatherV10SuccessorDispatchCallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)

    def test_sources_compile_and_entrypoint_selects_successor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for source in (SUCCESSOR, ENTRYPOINT, REFRESH):
                py_compile.compile(str(source), cfile=str(Path(temp) / (source.name + ".pyc")), doraise=True)
        self.assertEqual(git_mode(ENTRYPOINT), "100755")
        self.assertEqual(git_mode(REFRESH), "100755")
        self.assertIn("weather_operator_upgrade_v10_dispatch_caller", ENTRYPOINT.read_text(encoding="utf-8"))

    def test_historical_v9_caller_source_is_unchanged(self) -> None:
        self.assertEqual(LEGACY.read_bytes(), git_show(PREDECESSOR, str(LEGACY.relative_to(ROOT))))

    def test_exact_v10_owner_authorization_is_discovered(self) -> None:
        candidate = caller.discover_candidate(FakeClient([issue(self.now)], self.now))
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.request.authorization_issue_number, 87)
        self.assertEqual(candidate.request.request_id, "weather-v10-test-request")

    def test_v9_authorization_is_not_reused_by_successor(self) -> None:
        row = issue(self.now, title="[LIVE-AUTH][PENDING] rpi5-main-weather-operator-upgrade-v9")
        self.assertIsNone(caller.discover_candidate(FakeClient([row], self.now)))

    def test_dispatch_payload_remains_identity_only(self) -> None:
        candidate = caller.discover_candidate(FakeClient([issue(self.now)], self.now))
        assert candidate is not None
        value = json.loads(legacy._request_payload(candidate.request).decode("utf-8"))
        self.assertEqual(set(value), {
            "schema",
            "authorization_repository",
            "authorization_repository_id",
            "authorization_issue_id",
            "authorization_issue_number",
            "request_id",
        })
        forbidden = {"source_sha", "operation_id", "target_alias", "path", "argv", "env", "mutation_budget"}
        self.assertFalse(forbidden.intersection(value))

    def test_one_request_id_has_at_most_one_dispatch_attempt(self) -> None:
        rows = [issue(self.now)]
        client = FakeClient(rows, self.now)
        calls: list[str] = []

        def dispatch(request):
            calls.append(request.request_id)
            return {
                "result": "PASS",
                "authorization_issue_number": request.authorization_issue_number,
                "request_id": request.request_id,
            }

        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            os.chmod(state, 0o700)
            first = caller.run_once(client, state_dir=state, dispatcher=dispatch)
            second = caller.run_once(client, state_dir=state, dispatcher=dispatch)
        self.assertEqual(first["result"], "PASS")
        self.assertEqual(second["result"], "AUTHORIZATION_ALREADY_ATTEMPTED")
        self.assertEqual(calls, ["weather-v10-test-request"])

    def test_malformed_multiple_stale_and_app_auth_fail_closed(self) -> None:
        malformed = issue(self.now)
        malformed["body"] = "malformed"
        with self.assertRaises(Exception):
            caller.discover_candidate(FakeClient([malformed], self.now))
        with self.assertRaises(Exception):
            caller.discover_candidate(FakeClient([issue(self.now), issue(self.now, number=88)], self.now))
        with self.assertRaises(Exception):
            caller.discover_candidate(FakeClient([issue(self.now, age=601)], self.now))
        via_app = issue(self.now)
        via_app["performed_via_github_app"] = {"id": 1}
        with self.assertRaises(Exception):
            caller.discover_candidate(FakeClient([via_app], self.now))

    def test_refresh_contract_is_fixed_and_has_no_systemd_mutation(self) -> None:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(value["issue"], 650)
        self.assertEqual(value["predecessor_source_sha"], PREDECESSOR)
        self.assertEqual(value["replacement_order"], ["successor_module", "dispatch_caller_entrypoint"])
        self.assertEqual(value["fixed_targets"], {
            "/usr/local/libexec/rozkalns-weather-operator-v9-capability/deploy_executor/weather_operator_upgrade_v10_dispatch_caller.py": "0644",
            "/usr/local/libexec/rozkalns-weather-operator-v9-dispatch-caller": "0755",
        })
        self.assertFalse(value["systemd_mutation"])
        self.assertFalse(value["broker_mutation"])
        self.assertFalse(value["registration_mutation"])
        self.assertFalse(value["replay_state_db_mutation"])
        self.assertFalse(value["source_merge_authorizes_live"])
        script = REFRESH.read_text(encoding="utf-8")
        self.assertNotIn("systemctl", script)
        self.assertNotIn("shell=True", script)


if __name__ == "__main__":
    unittest.main()
