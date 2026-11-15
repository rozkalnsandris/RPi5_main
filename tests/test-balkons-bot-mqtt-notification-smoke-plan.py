#!/usr/bin/env python3
"""Adversarial, completely offline MQTT->Telegram notification plan tests."""
from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "ops/bin/balkons-bot-mqtt-notification-smoke-plan"
loader = importlib.machinery.SourceFileLoader("balkons_mqtt_smoke_plan", str(ARTIFACT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
plan = importlib.util.module_from_spec(spec)
loader.exec_module(plan)


class SmokePlanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for relative in (plan.BOT, plan.CONTROLLER):
            source = ROOT / relative
            dest = self.root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())

    def change(self, relative, original, replacement):
        path = self.root / relative
        content = path.read_text(encoding="utf-8")
        self.assertEqual(content.count(original), 1, original)
        path.write_text(content.replace(original, replacement), encoding="utf-8")

    def test_current_reviewed_source_contract(self):
        self.assertIsNone(plan.validate_source_contract(ROOT))
        self.assertIsNone(plan.validate_source_contract(self.root))

    def test_plan_is_pure_and_identifies_fixed_notification(self):
        actual = plan.source_only_plan(self.root)
        self.assertEqual(actual["schema"], plan.SCHEMA)
        self.assertFalse(actual["can_publish"])
        self.assertFalse(actual["mutation_started"])
        self.assertEqual(actual["network_calls"], 0)
        request = actual["request_specification"]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["endpoint_path"], "/api/services/mqtt/publish")
        self.assertEqual(request["maximum_live_attempts_after_separate_owner_authorization"], 1)
        self.assertEqual(
            request["body"],
            {
                "topic": "balkons/telegram_out",
                "payload": "Balkona MQTT-Telegram sakaru tests. Tikai pazinojums.",
                "qos": 0,
                "retain": False,
            },
        )
        self.assertNotIn("balkons/cmd", json.dumps(request))
        self.assertTrue(actual["proof_limits"]["recipient_must_check_exact_text"])
        self.assertFalse(actual["proof_limits"]["telegram_api_acceptance_is_chat_receipt"])

    def test_changed_bot_topic_blocks(self):
        self.change(plan.BOT, 'T_OUT = "balkons/telegram_out"',
                    'T_OUT = "balkons/cmd"')
        with self.assertRaisesRegex(plan.ContractError, "bot_mqtt_topics_changed"):
            plan.source_only_plan(self.root)

    def test_changed_command_topic_blocks(self):
        self.change(plan.BOT, 'T_CMD = "balkons/cmd"',
                    'T_CMD = "balkons/telegram_out"')
        with self.assertRaisesRegex(plan.ContractError, "bot_mqtt_topics_changed"):
            plan.source_only_plan(self.root)

    def test_missing_subscribe_blocks(self):
        self.change(plan.BOT, "client.subscribe(T_OUT)", "client.subscribe(T_CMD)")
        with self.assertRaisesRegex(plan.ContractError, "bot_notification_subscription_changed"):
            plan.source_only_plan(self.root)

    def test_missing_mqtt_provenance_blocks(self):
        self.change(plan.BOT, 'tg_send(text, source="mqtt")', "tg_send(text)")
        with self.assertRaisesRegex(plan.ContractError, "bot_notification_provenance_changed"):
            plan.source_only_plan(self.root)

    def test_changed_ha_destination_blocks(self):
        self.change(plan.CONTROLLER,
                    '{"topic": "balkons/telegram_out", "payload": sys.stdin.read(), "qos": 0, "retain": False}',
                    '{"topic": "balkons/cmd", "payload": sys.stdin.read(), "qos": 0, "retain": False}')
        with self.assertRaisesRegex(plan.ContractError, "controller_ha_notification_contract_changed"):
            plan.source_only_plan(self.root)

    def test_changed_retain_blocks(self):
        self.change(plan.CONTROLLER, '"qos": 0, "retain": False',
                    '"qos": 0, "retain": True')
        with self.assertRaisesRegex(plan.ContractError, "controller_ha_notification_contract_changed"):
            plan.source_only_plan(self.root)

    def test_changed_qos_blocks(self):
        self.change(plan.CONTROLLER, '"qos": 0, "retain": False',
                    '"qos": 1, "retain": False')
        with self.assertRaisesRegex(plan.ContractError, "controller_ha_notification_contract_changed"):
            plan.source_only_plan(self.root)

    def test_changed_ha_endpoint_blocks(self):
        self.change(plan.CONTROLLER, "/api/services/mqtt/publish",
                    "/api/services/switch/turn_on")
        with self.assertRaisesRegex(plan.ContractError, "controller_ha_notification_contract_changed"):
            plan.source_only_plan(self.root)

    def test_invalid_python_blocks(self):
        self.change(plan.BOT, "def on_message(client, userdata, msg) -> None:",
                    "def on_message(")
        with self.assertRaisesRegex(plan.ContractError, "bot_python_invalid"):
            plan.source_only_plan(self.root)

    def test_symlink_source_blocks(self):
        source = self.root / plan.BOT
        external = self.root / "external-public-fixture"
        external.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(external)
        with self.assertRaisesRegex(plan.ContractError, "source_file_unsafe"):
            plan.source_only_plan(self.root)

    def test_oversized_source_blocks(self):
        source = self.root / plan.BOT
        source.write_bytes(b"x" * 131073)
        with self.assertRaisesRegex(plan.ContractError, "source_file_unsafe"):
            plan.source_only_plan(self.root)

    def test_non_notification_topic_payload_and_wildcards_block(self):
        bad = [
            {"topic": "balkons/cmd", "payload": "statuss", "qos": 0, "retain": False},
            {"topic": "balkons/#", "payload": "safe", "qos": 0, "retain": False},
            {"topic": "balkons/telegram_out", "payload": "laist", "qos": 0, "retain": False},
            {"topic": "balkons/telegram_out", "payload": "safe", "qos": 1, "retain": False},
            {"topic": "balkons/telegram_out", "payload": "safe", "qos": 0, "retain": True},
        ]
        for value in bad:
            with self.subTest(value=value), patch.object(plan, "notification_body", return_value=value):
                with self.assertRaisesRegex(plan.ContractError, "notification_payload_unsafe"):
                    plan.source_only_plan(self.root)

    def test_script_cannot_send_or_read_credentials(self):
        tree = ast.parse(ARTIFACT.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports.intersection({
            "socket", "subprocess", "requests", "urllib", "http",
            "paho", "paho_mqtt", "paho.mqtt", "os", "shutil"
        }))
        self.assertNotIn("balkons-bot.service", ARTIFACT.read_text(encoding="utf-8"))
        self.assertNotIn("HASS_TOKEN", ARTIFACT.read_text(encoding="utf-8"))
        self.assertNotIn("CREDENTIALS_DIRECTORY", ARTIFACT.read_text(encoding="utf-8"))
        self.assertNotIn("balkons/cmd", plan.notification_body()["topic"])
        self.assertNotIn("switch.turn_on", ARTIFACT.read_text(encoding="utf-8"))

    def test_cli_check_is_offline_and_sanitized(self):
        for args, expected_mode in (
            ([], "SOURCE_ONLY_PLAN"),
            (["--check"], "PASS"),
        ):
            proc = subprocess.run(
                [sys.executable, "-I", "-B", str(ARTIFACT), *args],
                capture_output=True, text=True, timeout=6, check=True,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            )
            obj = json.loads(proc.stdout)
            self.assertEqual(obj["result"], expected_mode)
            self.assertFalse(obj["can_publish"])
            self.assertEqual(obj["network_calls"], 0)
            self.assertFalse(obj["mutation_started"])
            self.assertEqual(proc.stderr, "")

    def test_cli_rejects_live_publish_and_arbitrary_arguments(self):
        for args in (
            ["--publish"], ["--send"], ["--execute"], ["--topic", "balkons/cmd"],
            ["--payload", "laist"], ["--retain"], ["--qos", "1"],
        ):
            with self.subTest(args=args):
                proc = subprocess.run(
                    [sys.executable, "-I", "-B", str(ARTIFACT), *args],
                    capture_output=True, text=True, timeout=6, check=False,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertNotIn("SOURCE_ONLY_PLAN", proc.stdout)


if __name__ == "__main__":
    unittest.main()
