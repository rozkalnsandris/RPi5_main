#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_dispatch_caller as caller
from deploy_executor import weather_operator_upgrade_v7_host_capability as cap

REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def auth_issue(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": cap.AUTH_SCHEMA,
        "request_id": REQUEST_ID,
        "queue_issue": 63,
        "source_sha": "a" * 40,
        "operation_id": cap.OPERATION_ID,
        "target_alias": cap.TARGET_ALIAS,
        "expected_predecessor_sha256": cap.OLD_SHA256,
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in cap.MUTATION_BUDGET
        ],
        "rollback_policy": "NONE",
        "exclusions": list(cap.REQUIRED_EXCLUSIONS),
    }
    payload.update(overrides)
    body = cap.AUTH_START + "\n```json\n" + json.dumps(payload, sort_keys=True) + "\n```\n" + cap.AUTH_END
    return {
        "state": "open",
        "title": cap.AUTH_TITLE,
        "number": 64,
        "id": 123456789,
        "created_at": "2026-09-16T20:40:00Z",
        "user": {"id": cap.OWNER_USER_ID, "type": "User"},
        "body": body,
    }


class FakeClient:
    def __init__(self, rows: list[dict[str, object]]):
        self.rows = rows
        self.server_time = datetime(2026, 9, 16, 20, 45, tzinfo=timezone.utc)

    def get_json(self, path: str):
        if path == f"/repos/{caller.AUTHORIZATION_REPOSITORY}":
            return SimpleNamespace(
                value={
                    "id": caller.AUTHORIZATION_REPOSITORY_ID,
                    "full_name": caller.AUTHORIZATION_REPOSITORY,
                },
                next_url=None,
                server_time=self.server_time,
            )
        return SimpleNamespace(value=self.rows, next_url=None, server_time=self.server_time)


class WeatherV7DispatchCallerTests(unittest.TestCase):
    def test_exact_identity_only_authorization_is_admitted(self) -> None:
        candidate = caller.discover_candidate(FakeClient([auth_issue()]))
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.request.authorization_issue_number, 64)
        self.assertEqual(candidate.request.request_id, REQUEST_ID)

    def test_payload_expansion_is_rejected(self) -> None:
        with self.assertRaises((caller.WeatherV7DispatchCallerError, cap.WeatherV7HostCapabilityError)):
            caller.discover_candidate(FakeClient([auth_issue(command="id")]))

    def test_wrong_owner_is_rejected(self) -> None:
        issue = auth_issue()
        issue["user"] = {"id": 1, "type": "User"}
        with self.assertRaises(cap.WeatherV7HostCapabilityError):
            caller.discover_candidate(FakeClient([issue]))

    def test_multiple_matching_authorizations_fail_closed(self) -> None:
        with self.assertRaises(caller.WeatherV7DispatchCallerError):
            caller.discover_candidate(FakeClient([auth_issue(), auth_issue()]))

    def test_no_matching_authorization_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            state.chmod(0o700)
            result = caller.run_once(FakeClient([]), state_dir=state)
        self.assertEqual(result["result"], "NO_PENDING_AUTHORIZATION")
        self.assertFalse(result["dispatch_attempted"])

    def test_attempt_is_persisted_before_dispatch_and_never_retried(self) -> None:
        calls = 0

        def failing_dispatch(_request):
            nonlocal calls
            calls += 1
            raise caller.WeatherV7DispatchCallerError("synthetic transport failure")

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            state.chmod(0o700)
            with self.assertRaises(caller.WeatherV7DispatchCallerError):
                caller.run_once(FakeClient([auth_issue()]), state_dir=state, dispatcher=failing_dispatch)
            result = caller.run_once(
                FakeClient([auth_issue()]), state_dir=state, dispatcher=failing_dispatch
            )
        self.assertEqual(calls, 1)
        self.assertEqual(result["result"], "AUTHORIZATION_ALREADY_ATTEMPTED")
        self.assertFalse(result["dispatch_attempted"])

    def test_contracts_and_units_preserve_narrow_boundary(self) -> None:
        service = (ROOT / "ops/systemd/rozkalns-weather-operator-v7-dispatch-caller.service").read_text()
        timer = (ROOT / "ops/systemd/rozkalns-weather-operator-v7-dispatch-caller.timer").read_text()
        installer = (ROOT / "scripts/install-weather-operator-v7-dispatch-caller.py").read_text()
        contract = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-dispatch-caller-installer.json").read_text()
        )
        source_delivery = json.loads(
            (ROOT / "ops/deploy/rpi5-main-weather-v7-dispatch-caller-installer-source-trusted-checkout-bootstrap.json").read_text()
        )
        self.assertIn("User=rozkalns-deploy-executor", service)
        self.assertIn("Group=rozkalns-deploy-executor", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("LoadCredential=github-app.pem:", service)
        self.assertIn("rozkalns-weather-operator-v7-privileged-broker.socket", service)
        self.assertIn("Unit=rozkalns-weather-operator-v7-dispatch-caller.service", timer)
        self.assertNotIn("/usr/bin/sudo", installer)
        self.assertNotIn("shell=True", installer)
        self.assertFalse(contract["separation"]["socket_permission_or_acl_mutation"])
        self.assertFalse(contract["separation"]["user_or_group_membership_mutation"])
        self.assertFalse(contract["separation"]["p8_mutation_dispatch_enabled"])
        self.assertFalse(contract["separation"]["global_executor_execution_enabled"])
        self.assertTrue(contract["host_install_gate"]["requires_separate_exact_owner_live_authorization"])
        self.assertFalse(source_delivery["source_merge_enables_live"])
        self.assertEqual(len(source_delivery["allowed_git_mutations"]), 2)

    def test_installer_verifies_full_installed_support_closure(self) -> None:
        installer = (ROOT / "scripts/install-weather-operator-v7-dispatch-caller.py").read_text()
        required_support = (
            "__init__.py",
            "dispatch_contract.py",
            "github_app_auth.py",
            "p9_canary.py",
            "p9_isolated_auth_surface.py",
            "p9_runtime.py",
            "protocol.py",
            "queue_normalizer.py",
            "registry.py",
            "state.py",
            "transport.py",
            "weather_operator_upgrade_v7_host_capability.py",
            "rozkalns-weather-operator-v7-privileged-broker",
            "rozkalns-weather-operator-v7-privileged-broker.socket",
            "rozkalns-weather-operator-v7-privileged-broker@.service",
        )
        for artifact in required_support:
            self.assertIn(artifact, installer)
        self.assertIn('"verified_prerequisite_artifact_count": len(PREREQUISITES)', installer)

    def test_source_has_fixed_socket_and_no_generic_process_launch(self) -> None:
        source = (ROOT / "ops/lib/deploy_executor/weather_operator_upgrade_v7_dispatch_caller.py").read_text()
        self.assertIn("socket.AF_UNIX", source)
        self.assertIn(str(caller.SOCKET_PATH), source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn('get("command")', source)
        self.assertNotIn('get("path")', source)
        self.assertNotIn('get("argv")', source)
        self.assertNotIn('get("environment")', source)


if __name__ == "__main__":
    unittest.main()
