#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_host_capability as v7cap
from deploy_executor import weather_operator_upgrade_v9_host_capability as cap
from deploy_executor import weather_operator_upgrade_v9_dispatch_caller as caller

REQUEST_ID = "123e4567-e89b-42d3-a456-426614174603"


def auth_issue(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": cap.AUTH_SCHEMA,
        "request_id": REQUEST_ID,
        "queue_issue": 6030,
        "source_sha": "a" * 40,
        "operation_id": cap.OPERATION_ID,
        "target_alias": cap.TARGET_ALIAS,
        "expected_predecessor_sha256": cap.OLD_SHA256,
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in cap.MUTATION_BUDGET
        ],
        "rollback_policy": cap.ROLLBACK_POLICY,
        "exclusions": list(cap.REQUIRED_EXCLUSIONS),
    }
    payload.update(overrides)
    body = (
        cap.AUTH_START
        + "\n```json\n"
        + json.dumps(payload, sort_keys=True)
        + "\n```\n"
        + cap.AUTH_END
    )
    return {
        "state": "open",
        "title": cap.AUTH_TITLE,
        "number": 6031,
        "id": 6031001,
        "created_at": "2026-09-18T16:15:00Z",
        "user": {"id": cap.OWNER_USER_ID, "type": "User"},
        "performed_via_github_app": None,
        "body": body,
    }


class FakeClient:
    def __init__(self, rows: list[dict[str, object]]):
        self.rows = rows
        self.server_time = datetime(2026, 9, 18, 16, 20, tzinfo=timezone.utc)

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


class WeatherV9PrivilegedDeliveryTests(unittest.TestCase):
    def test_source_readiness_is_v9_strict_and_inactive(self) -> None:
        ready = cap.source_readiness()
        self.assertEqual(ready["operation_id"], "rpi5-main.weather-operator-upgrade-v9.v1")
        self.assertEqual(ready["authorization_class"], "STRICT")
        self.assertFalse(ready["ordinary_live_all_eligible"])
        self.assertFalse(ready["host_capability_installed"])
        self.assertFalse(ready["privileged_dispatch_enabled"])
        self.assertFalse(ready["v7_authority_reuse_allowed"])
        self.assertFalse(ready["p8_mutation_dispatch_enabled"])
        self.assertFalse(ready["global_executor_execution_enabled"])
        self.assertFalse(ready["source_merge_authorizes_live"])

    def test_exact_identity_only_v9_authorization_is_admitted(self) -> None:
        candidate = caller.discover_candidate(FakeClient([auth_issue()]))
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.request.authorization_issue_number, 6031)
        self.assertEqual(candidate.request.request_id, REQUEST_ID)

    def test_payload_expansion_and_wrong_owner_are_rejected(self) -> None:
        with self.assertRaises((caller.WeatherV9DispatchCallerError, cap.WeatherV9HostCapabilityError)):
            caller.discover_candidate(FakeClient([auth_issue(command="id")]))
        issue = auth_issue()
        issue["user"] = {"id": 1, "type": "User"}
        with self.assertRaises(cap.WeatherV9HostCapabilityError):
            caller.discover_candidate(FakeClient([issue]))

    def test_v7_authorization_cannot_trigger_v9_caller(self) -> None:
        issue = auth_issue()
        issue["title"] = v7cap.AUTH_TITLE
        self.assertIsNone(caller.discover_candidate(FakeClient([issue])))
        self.assertNotEqual(cap.AUTH_SCHEMA, v7cap.AUTH_SCHEMA)
        self.assertNotEqual(cap.OPERATION_ID, v7cap.OPERATION_ID)
        self.assertNotEqual(cap.TARGET_ALIAS, v7cap.TARGET_ALIAS)

    def test_attempt_is_persisted_before_dispatch_and_never_retried(self) -> None:
        calls = 0

        def failing_dispatch(_request):
            nonlocal calls
            calls += 1
            raise caller.WeatherV9DispatchCallerError("synthetic transport failure")

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            state.chmod(0o700)
            with self.assertRaises(caller.WeatherV9DispatchCallerError):
                caller.run_once(FakeClient([auth_issue()]), state_dir=state, dispatcher=failing_dispatch)
            result = caller.run_once(
                FakeClient([auth_issue()]), state_dir=state, dispatcher=failing_dispatch
            )
        self.assertEqual(calls, 1)
        self.assertEqual(result["result"], "AUTHORIZATION_ALREADY_ATTEMPTED")
        self.assertFalse(result["dispatch_attempted"])

    def test_v9_mutation_budget_matches_merged_checkout_contract(self) -> None:
        checkout = json.loads(
            (ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v9-trusted-checkout-bootstrap.json").read_text()
        )
        merged = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9.json").read_text()
        )
        delivery = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9-privileged-delivery.json").read_text()
        )
        expected = (
            ("git.weather-operator-upgrade-v9-checkout-fetch", 1),
            ("git.weather-operator-upgrade-v9-checkout-worktree-add", 1),
            ("filesystem.weather-operator-upgrade-v9-atomic-replace", 1),
        )
        self.assertEqual(cap.MUTATION_BUDGET, expected)
        self.assertEqual(
            tuple((row["mutation_category"], row["max_operations"]) for row in checkout["allowed_git_mutations"]),
            expected[:2],
        )
        self.assertEqual(
            tuple((row["category"], row["max_operations"]) for row in delivery["mutation_budget"]),
            expected,
        )
        self.assertEqual(delivery["predecessor_sha256"], merged["old_sha256"])
        self.assertEqual(delivery["target_sha256"], merged["new_sha256"])
        self.assertEqual(delivery["target"], merged["target_destination"])
        self.assertFalse(delivery["v7_authority_reuse"])

    def test_broker_delegates_replacement_to_merged_v9_entrypoint(self) -> None:
        source = (ROOT / "ops/bin/rozkalns-weather-operator-v9-privileged-broker").read_text()
        self.assertEqual(cap.ENTRYPOINT, "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9")
        self.assertIn("entrypoint = plan.trusted_checkout / cap.ENTRYPOINT", source)
        self.assertIn("UPGRADE_ENTRYPOINT_BLOB", source)
        self.assertIn("UPGRADE_MODULE_BLOB", source)
        self.assertIn("WORKTREE_ADD_UMASK = 0o022", source)
        self.assertIn("umask=umask", source)
        self.assertIn("child_umask=WORKTREE_ADD_UMASK", source)
        self.assertNotIn("os.replace(", source)
        self.assertNotIn("/usr/bin/sudo", source)
        self.assertNotIn("shell=True", source)

    def test_worktree_add_child_umask_preserves_executable_mode(self) -> None:
        os_module = __import__("os")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = root / "RPi5_main"
            subprocess.run(
                ["git", "init", str(manager)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            entrypoint = manager / "entrypoint"
            entrypoint.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            subprocess.run(["git", "-C", str(manager), "add", "entrypoint"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(manager),
                    "-c",
                    "user.name=Weather v9 test",
                    "-c",
                    "user.email=weather-v9-test@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            head = subprocess.run(
                ["git", "-C", str(manager), "rev-parse", "HEAD"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.strip()
            target = root / "weather-v9-worktree"
            original_umask = os_module.umask(0o077)
            try:
                subprocess.run(
                    ["git", "-C", str(manager), "worktree", "add", "--detach", str(target), head],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                    umask=0o022,
                )
            finally:
                os_module.umask(original_umask)
            self.assertEqual((target / "entrypoint").stat().st_mode & 0o777, 0o755)

    def test_systemd_and_installers_are_v9_specific_and_source_only(self) -> None:
        socket_unit = (ROOT / "ops/systemd/rozkalns-weather-operator-v9-privileged-broker.socket").read_text()
        service_unit = (ROOT / "ops/systemd/rozkalns-weather-operator-v9-privileged-broker@.service").read_text()
        caller_unit = (ROOT / "ops/systemd/rozkalns-weather-operator-v9-dispatch-caller.service").read_text()
        host_installer = (ROOT / "scripts/install-weather-operator-v9-host-capability.py").read_text()
        caller_installer = (ROOT / "scripts/install-weather-operator-v9-dispatch-caller.py").read_text()
        self.assertIn("/run/rozkalns-weather-operator-v9-capability/request.sock", socket_unit)
        self.assertIn("User=root", service_unit)
        self.assertIn("UMask=0077", service_unit)
        self.assertIn("NoNewPrivileges=true", service_unit)
        self.assertIn("@@WEATHER_V9_MANAGER_PARENT@@", service_unit)
        self.assertIn("User=rozkalns-deploy-executor", caller_unit)
        self.assertIn("NoNewPrivileges=true", caller_unit)
        for text in (host_installer, caller_installer):
            self.assertNotIn("/usr/bin/sudo", text)
            self.assertNotIn("shell=True", text)
        self.assertNotIn("rozkalns-weather-operator-v7-capability", socket_unit + service_unit + caller_unit)

    def test_source_delivery_is_fixed_and_non_live(self) -> None:
        contract = json.loads(
            (ROOT / "ops/deploy/rpi5-main-weather-v9-privileged-delivery-installer-source-trusted-checkout-bootstrap.json").read_text()
        )
        self.assertFalse(contract["source_merge_enables_live"])
        self.assertEqual(len(contract["allowed_git_mutations"]), 2)
        self.assertFalse(contract["failure"]["automatic_retry"])
        self.assertFalse(contract["failure"]["automatic_cleanup"])
        self.assertFalse(contract["failure"]["automatic_rollback"])
        self.assertIn(
            "RPi5_main-weather-v9-privileged-delivery-installer-source-trusted",
            contract["trusted_checkout"]["name"],
        )

    def test_security_critical_entrypoints_are_executable_in_git(self) -> None:
        for path in (
            "ops/bin/rozkalns-weather-operator-v9-privileged-broker",
            "ops/bin/rozkalns-weather-operator-v9-dispatch-caller",
            "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9",
        ):
            row = subprocess.run(
                ["git", "ls-tree", "HEAD", "--", path],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.strip()
            self.assertTrue(row.startswith("100755 blob "), row)


if __name__ == "__main__":
    unittest.main()
