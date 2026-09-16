#!/usr/bin/env python3
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_host_capability as cap
from deploy_executor.dispatch_contract import DispatchContractError, parse_dispatch_request

CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-installer.json"
INSTALLER = ROOT / "scripts/install-weather-operator-v7-host-capability.py"
BROKER = ROOT / "ops/bin/rozkalns-weather-operator-v7-privileged-broker"
SOCKET = ROOT / "ops/systemd/rozkalns-weather-operator-v7-privileged-broker.socket"
SERVICE = ROOT / "ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service"
DELIVERY = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-privileged-delivery.json"
DOC = ROOT / "docs/WEATHER_OPERATOR_V7_PRIVILEGED_DELIVERY.md"
WORKFLOW = ROOT / ".github/workflows/validate.yml"
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def request() -> cap.DispatchRequest:
    return parse_dispatch_request({
        "schema": "rozkalns.deploy-dispatch-request.v1",
        "authorization_repository": "rozkalnsandris/ops-workflows",
        "authorization_repository_id": 1328835922,
        "authorization_issue_id": 9000001,
        "authorization_issue_number": 77,
        "request_id": REQUEST_ID,
    })


def auth_issue(**payload_overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": cap.AUTH_SCHEMA,
        "request_id": REQUEST_ID,
        "queue_issue": 88,
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
    payload.update(payload_overrides)
    body = cap.AUTH_START + "\n```json\n" + json.dumps(payload, sort_keys=True) + "\n```\n" + cap.AUTH_END
    return {
        "state": "open",
        "title": cap.AUTH_TITLE,
        "number": 77,
        "id": 9000001,
        "created_at": "2026-09-16T13:00:00Z",
        "user": {"id": cap.OWNER_USER_ID, "type": "User"},
        "body": body,
    }


class WeatherV7HostCapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.broker = BROKER.read_text(encoding="utf-8")
        cls.socket = SOCKET.read_text(encoding="utf-8")
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.delivery = json.loads(DELIVERY.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_source_status_is_install_ready_but_live_inactive(self) -> None:
        ready = cap.source_readiness()
        self.assertEqual(ready["result"], "SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL")
        self.assertEqual(ready["operation_id"], cap.OPERATION_ID)
        for key in (
            "host_capability_installed",
            "privileged_dispatch_enabled",
            "p8_mutation_dispatch_enabled",
            "global_executor_execution_enabled",
            "source_merge_authorizes_live",
            "caller_command_allowed",
            "caller_path_allowed",
            "caller_argv_allowed",
            "caller_environment_allowed",
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
            "production_mutation_started",
        ):
            self.assertFalse(ready[key], key)

    def test_contract_is_first_install_only_and_does_not_enable_p8(self) -> None:
        self.assertEqual(self.contract["issue"], 571)
        self.assertEqual(self.contract["status"], "SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL")
        self.assertEqual(self.contract["artifact_count"], 15)
        self.assertTrue(self.contract["generated_runtime_state"]["first_install_only"])
        self.assertFalse(self.contract["separation"]["p8_mutation_dispatch_enabled"])
        self.assertFalse(self.contract["separation"]["global_executor_execution_enabled"])
        self.assertFalse(self.contract["host_install_gate"]["source_merge_authorizes_live"])
        self.assertTrue(self.contract["host_install_gate"]["requires_separate_exact_owner_live_authorization"])
        self.assertEqual(self.contract["host_install_gate"]["installer_default_mode"], "READ_ONLY_PREFLIGHT")

    def test_fixed_registry_matches_543_operation_identity_and_budget(self) -> None:
        registry = cap.fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, self.delivery["operation"]["operation_id"])
        self.assertEqual(operation.target_alias, self.delivery["operation"]["target_alias"])
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(
            tuple((item.category, item.max_operations) for item in operation.mutation_budget),
            cap.MUTATION_BUDGET,
        )

    def test_authorization_is_owner_ttl_issue_id_request_id_and_fixed_budget_bound(self) -> None:
        parsed = cap.parse_authorization_issue(
            auth_issue(),
            server_time=datetime(2026, 9, 16, 13, 5, tzinfo=timezone.utc),
            request=request(),
        )
        self.assertEqual(parsed.request_id, REQUEST_ID)
        self.assertEqual(parsed.source_sha, "a" * 40)
        self.assertEqual(parsed.queue_issue, 88)

        fixtures = (
            ({"source_sha": "b" * 39}, "source"),
            ({"operation_id": "other.operation"}, "operation"),
            ({"target_alias": "other-target"}, "target"),
            ({"expected_predecessor_sha256": "0" * 64}, "predecessor"),
            ({"mutation_budget": [{"category": "other", "max_operations": 1}]}, "budget"),
            ({"rollback_policy": "BUILTIN_TRANSACTIONAL_V1"}, "rollback"),
            ({"exclusions": []}, "exclusions"),
        )
        for overrides, _name in fixtures:
            with self.subTest(overrides=overrides):
                with self.assertRaises(cap.WeatherV7HostCapabilityError):
                    cap.parse_authorization_issue(
                        auth_issue(**overrides),
                        server_time=datetime(2026, 9, 16, 13, 5, tzinfo=timezone.utc),
                        request=request(),
                    )

    def test_stale_or_wrong_owner_authorization_is_rejected(self) -> None:
        with self.assertRaises(cap.WeatherV7HostCapabilityError):
            cap.parse_authorization_issue(
                auth_issue(),
                server_time=datetime(2026, 9, 16, 13, 20, tzinfo=timezone.utc),
                request=request(),
            )
        wrong = auth_issue()
        wrong["user"] = {"id": 1, "type": "User"}
        with self.assertRaises(cap.WeatherV7HostCapabilityError):
            cap.parse_authorization_issue(
                wrong,
                server_time=datetime(2026, 9, 16, 13, 5, tzinfo=timezone.utc),
                request=request(),
            )

    def test_identity_payload_rejects_command_path_argv_environment(self) -> None:
        base = {
            "schema": "rozkalns.deploy-dispatch-request.v1",
            "authorization_repository": "rozkalnsandris/ops-workflows",
            "authorization_repository_id": 1328835922,
            "authorization_issue_id": 9000001,
            "authorization_issue_number": 77,
            "request_id": REQUEST_ID,
        }
        for key, value in (
            ("command", "id"),
            ("path", "/tmp/x"),
            ("argv", ["--force"]),
            ("environment", {"X": "Y"}),
            ("source_sha", "a" * 40),
            ("target", "/tmp/x"),
        ):
            changed = dict(base)
            changed[key] = value
            with self.subTest(key=key):
                with self.assertRaises(DispatchContractError):
                    parse_dispatch_request(changed)

    def test_installer_has_read_only_default_root_apply_and_no_retry_cleanup_rollback(self) -> None:
        tree = ast.parse(self.installer)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ]
        apply_calls = [
            node for node in calls
            if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "--apply"
        ]
        self.assertEqual(len(apply_calls), 1)
        self.assertIn("os.geteuid() != 0", self.installer)
        self.assertIn('systemctl("daemon-reload")', self.installer)
        self.assertIn('systemctl("enable", "--now", SOCKET_NAME)', self.installer)
        self.assertIn('os.environ.get("SUDO_UID")', self.installer)
        self.assertNotIn("/usr/bin/sudo", self.installer)
        self.assertNotIn('["sudo"', self.installer)
        self.assertNotIn("shell=True", self.installer)
        self.assertIn("no retry/cleanup/rollback is authorized", self.installer)

    def test_broker_and_units_are_fixed_identity_only(self) -> None:
        self.assertIn("runtime_main()", self.broker)
        self.assertNotIn("argparse", self.broker)
        self.assertIn("Accept=yes", self.socket)
        self.assertIn("SocketGroup=rozkalns-deploy-executor", self.socket)
        self.assertIn("SocketMode=0660", self.socket)
        self.assertIn("User=root", self.service)
        self.assertIn("LoadCredential=github-app.pem:/etc/rozkalns-deploy-executor/github-app.pem", self.service)
        self.assertIn("ExecStart=/usr/local/libexec/rozkalns-weather-operator-v7-privileged-broker", self.service)
        self.assertNotIn("ExecStart=/bin/sh", self.service)
        self.assertNotIn("ExecStart=/bin/bash", self.service)

    def test_host_capability_module_has_no_shell_or_caller_selected_execution(self) -> None:
        source = (ROOT / "ops/lib/deploy_executor/weather_operator_upgrade_v7_host_capability.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("exec(", source)
        self.assertIn("[str(entrypoint)]", source)
        self.assertIn('"/usr/bin/git"', source)
        self.assertNotIn('request_value.get("command")', source)
        self.assertNotIn('request_value.get("path")', source)
        self.assertNotIn('request_value.get("argv")', source)
        self.assertNotIn('request_value.get("environment")', source)

    def test_docs_and_workflow_preserve_owner_gate_order(self) -> None:
        ordered = (
            "source merge + exact-main CI",
            "one-time privileged-boundary host install/upgrade",
            "sanitized capability verification",
            "fresh exact Weather v7 LIVE authorization",
            "installed-closure verification",
            "rozkalns_weather public rollout reconciliation",
        )
        positions = [self.doc.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("RPi5_main#571", self.doc)
        self.assertIn("SOURCE_READY_FOR_HOST_CAPABILITY_INSTALL", self.doc)
        self.assertIn(
            "python3 ./tests/test-weather-operator-v7-host-capability-installer.py",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
