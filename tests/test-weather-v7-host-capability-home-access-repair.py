#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_host_capability as cap
from deploy_executor.dispatch_contract import parse_dispatch_request

BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v7-privileged-broker"
SERVICE = ROOT / "ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service"
INSTALLER = ROOT / "scripts/install-weather-operator-v7-host-capability.py"
REPAIR = ROOT / "scripts/repair-weather-operator-v7-host-capability-home-access.py"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair-v2.json"
DOC = ROOT / "docs/WEATHER_OPERATOR_V7_REPAIR_595.md"
WORKFLOW = ROOT / ".github/workflows/validate.yml"
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174595"


def request() -> cap.DispatchRequest:
    return parse_dispatch_request({
        "schema": "rozkalns.deploy-dispatch-request.v1",
        "authorization_repository": "rozkalnsandris/ops-workflows",
        "authorization_repository_id": 1328835922,
        "authorization_issue_id": 9000595,
        "authorization_issue_number": 95,
        "request_id": REQUEST_ID,
    })


def auth_issue(*, performed_via_github_app: object = None) -> dict[str, object]:
    payload = {
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
    return {
        "state": "open",
        "title": cap.AUTH_TITLE,
        "number": 95,
        "id": 9000595,
        "created_at": "2026-09-17T10:00:00Z",
        "user": {"id": cap.OWNER_USER_ID, "type": "User"},
        "performed_via_github_app": performed_via_github_app,
        "body": cap.AUTH_START + "\n```json\n" + json.dumps(payload, sort_keys=True) + "\n```\n" + cap.AUTH_END,
    }


class WeatherV7HomeAccessRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.broker = BROKER.read_text(encoding="utf-8")
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.repair = REPAIR.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_direct_owner_authorization_is_accepted_and_app_mediated_is_rejected(self) -> None:
        parsed = cap.parse_authorization_issue(
            auth_issue(),
            server_time=datetime(2026, 9, 17, 10, 5, tzinfo=timezone.utc),
            request=request(),
        )
        self.assertEqual(parsed.request_id, REQUEST_ID)
        with self.assertRaises(cap.WeatherV7HostCapabilityError):
            cap.parse_authorization_issue(
                auth_issue(performed_via_github_app={"id": 1144995}),
                server_time=datetime(2026, 9, 17, 10, 5, tzinfo=timezone.utc),
                request=request(),
            )

    def test_registration_v2_binds_strict_numeric_manager_identity(self) -> None:
        valid = {
            "schema": cap.REGISTRATION_SCHEMA,
            "capability_source_sha": "a" * 40,
            "manager_checkout": "/home/andris/RPi5_main",
            "manager_uid": 1000,
            "manager_gid": 1000,
            "artifact_count": 15,
            "module_sha256": "1" * 64,
            "broker_sha256": "2" * 64,
            "socket_sha256": "3" * 64,
            "service_sha256": "4" * 64,
        }
        with mock.patch.object(cap, "_safe_file", return_value=(json.dumps(valid) + "\n").encode()):
            self.assertEqual(cap.load_registration()["manager_uid"], 1000)
        for bad in (0, -1, True, cap.MAX_UID + 1):
            changed = dict(valid)
            changed["manager_uid"] = bad
            with self.subTest(bad=bad), mock.patch.object(
                cap, "_safe_file", return_value=(json.dumps(changed) + "\n").encode()
            ):
                with self.assertRaises(cap.WeatherV7HostCapabilityError):
                    cap.load_registration()

    def test_git_and_home_access_children_drop_to_registered_identity(self) -> None:
        self.assertIn("user=uid", self.broker)
        self.assertIn("group=gid", self.broker)
        self.assertIn("extra_groups=()", self.broker)
        self.assertIn('f"safe.directory={reviewed}"', self.broker)
        self.assertIn('"/usr/bin/test"', self.broker)
        self.assertNotIn("safe.directory=*", self.broker)
        for forbidden in ("--global", "--system", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
            self.assertNotIn(forbidden, self.broker)

    def test_root_broker_does_not_execute_upgrade_code_from_user_home(self) -> None:
        self.assertNotIn("[str(entrypoint)]", self.broker)
        self.assertNotIn("cwd=plan.trusted_checkout", self.broker)
        self.assertIn('"show"', self.broker)
        self.assertIn("OPERATOR_SOURCE_BLOB", self.broker)
        self.assertIn("UPGRADE_ENTRYPOINT_BLOB", self.broker)
        self.assertIn("_atomic_replace_operator(data)", self.broker)
        self.assertIn("os.replace(temp, cap.TARGET_PATH)", self.broker)

    def test_service_has_only_identity_drop_capabilities_and_narrow_home_write_path(self) -> None:
        self.assertIn("User=root", self.service)
        self.assertIn("NoNewPrivileges=true", self.service)
        self.assertIn("ProtectHome=read-only", self.service)
        self.assertIn("CapabilityBoundingSet=CAP_SETUID CAP_SETGID", self.service)
        self.assertIn("AmbientCapabilities=\n", self.service)
        self.assertNotIn("CAP_DAC_OVERRIDE", self.service)
        self.assertNotIn("CAP_DAC_READ_SEARCH", self.service)
        self.assertIn("ReadWritePaths=/home/andris", self.service)
        self.assertNotIn("ReadWritePaths=/home\n", self.service)

    def test_first_install_registration_contains_manager_uid_gid(self) -> None:
        self.assertIn('REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v2"', self.installer)
        self.assertIn('"manager_uid": manager_uid', self.installer)
        self.assertIn('"manager_gid": manager_gid', self.installer)
        self.assertIn("manager_identity(manager)", self.installer)

    def test_repair_contract_is_exact_and_does_not_restart_runtime(self) -> None:
        self.assertEqual(self.contract["issue"], 595)
        self.assertFalse(self.contract["source_merge_authorizes_live"])
        self.assertEqual(
            self.contract["service_sandbox"]["capability_bounding_set"],
            ["CAP_SETUID", "CAP_SETGID"],
        )
        self.assertFalse(self.contract["service_sandbox"]["cap_dac_override_allowed"])
        self.assertFalse(self.contract["authorization_provenance"]["app_mediated_live_auth_allowed"])
        categories = [item["category"] for item in self.contract["repair"]["mutation_budget"]]
        self.assertEqual(categories, [
            "filesystem.weather-v7-capability-module-atomic-replace",
            "filesystem.weather-v7-capability-broker-atomic-replace",
            "filesystem.weather-v7-capability-service-template-atomic-replace",
            "filesystem.weather-v7-capability-registration-v2-atomic-replace",
            "systemd.weather-v7-capability-daemon-reload",
        ])
        self.assertFalse(self.contract["repair"]["socket_restart"])
        self.assertFalse(self.contract["repair"]["caller_timer_restart"])
        self.assertFalse(self.contract["repair"]["operator_replacement"])

    def test_repair_script_has_only_four_replacements_and_daemon_reload(self) -> None:
        self.assertEqual(self.repair.count("atomic_replace("), 5)  # definition + four calls
        self.assertEqual(self.repair.count("systemctl_daemon_reload()"), 2)  # definition + call
        for forbidden in (
            'systemctl", "restart"',
            'systemctl", "start"',
            'systemctl", "enable"',
            'systemctl", "stop"',
            "/usr/bin/sudo",
        ):
            self.assertNotIn(forbidden, self.repair)
        self.assertIn("no retry/cleanup/rollback is authorized", self.repair)

    def test_weather_operator_upgrade_budget_remains_one_plus_one_plus_one(self) -> None:
        self.assertEqual(cap.MUTATION_BUDGET, (
            ("git.weather-operator-upgrade-v7-checkout-fetch", 1),
            ("git.weather-operator-upgrade-v7-checkout-worktree-add", 1),
            ("filesystem.weather-operator-upgrade-v7-atomic-replace", 1),
        ))

    def test_docs_and_workflow_bind_595_recovery(self) -> None:
        self.assertIn("Weather v7 home-access / LIVE-AUTH provenance repair (#595)", self.doc)
        self.assertIn("performed_via_github_app", self.doc)
        self.assertIn("extra_groups=()", self.doc)
        self.assertIn("CAP_DAC_OVERRIDE", self.doc)
        self.assertIn(
            "python3 ./tests/test-weather-v7-host-capability-home-access-repair.py",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
