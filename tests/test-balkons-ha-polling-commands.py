#!/usr/bin/env python3
"""Offline-only contract for staged HA Telegram Polling commands."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/homeassistant/balkons-telegram-polling-commands.yaml"
BOT = ROOT / "ops/lib/balkons-bot.py"
NOTIFY = ROOT / "ops/homeassistant/balkons-telegram-native-notify.yaml"
COMMANDS = (("/stop", "stop"), ("/mitrums", "mitrums"),
            ("/statuss", "statuss"), ("/raw", "raw"))
GUARDS = (
    "trigger.to_state is not none",
    "trigger.to_state.entity_id == 'event.balkona_laistisana_update_event'",
    "trigger.to_state.attributes.event_type == 'telegram_command'",
    "trigger.to_state.attributes.bot is mapping",
    "(trigger.to_state.attributes.bot.get('config_entry_id') | default('', true) | string) == 'REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID'",
    "trigger.to_state.attributes.command is string",
    "(trigger.to_state.attributes.chat_id | string) == 'REPLACE_WITH_APPROVED_CHAT_ID'",
    "(trigger.to_state.attributes.user_id | string) == 'REPLACE_WITH_APPROVED_USER_ID'",
    "(trigger.to_state.attributes.args | default([], true) | length) == 0",
)


def validate_contract(source: str) -> None:
    if "\r" in source or "\x00" in source:
        raise ValueError("invalid_bytes")
    active = "\n".join(
        line for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    for item in (
        "SOURCE ONLY (#1525)", "- id: balkons_telegram_polling_commands_staged",
        "  initial_state: false\n", "    - trigger: state\n      enabled: false\n",
        "      entity_id: event.balkona_laistisana_update_event\n",
        "    - choose:\n", "      default: []\n      enabled: false\n",
        "  mode: parallel\n", "  max: 10\n",
    ):
        if item not in source:
            raise ValueError("missing_contract")
    if any(source.count(item) != 1 for item in GUARDS):
        raise ValueError("auth_guard_changed")
    for value, expected in (
        ("- id:", 1), ("trigger: state", 1), ("initial_state:", 1),
        ("entity_id: event.", 1), ("choose:", 1), ("default: []", 1),
        ("mode: parallel", 1), ("max: 10", 1),
        ("enabled: false", 2),
    ):
        if active.count(value) != expected:
            raise ValueError("extra_automation_or_trigger")

    routes = re.split(r"(?m)^        - conditions:\n", source)
    if len(routes) != 7 or any(s.count("          sequence:\n") != 1 for s in routes[1:]):
        raise ValueError("route_structure_changed")
    for index, (command, payload) in enumerate(COMMANDS, start=1):
        route = routes[index]
        guard = f"value_template: \"{{{{ trigger.to_state.attributes.command == '{command}' }}}}\""
        fixed_action = (
            "            - action: mqtt.publish\n"
            "              data:\n"
            '                topic: "balkons/cmd"\n'
            f'                payload: "{payload}"\n'
            "                qos: 0\n"
            "                retain: false\n"
        )
        if guard not in route or fixed_action not in route:
            raise ValueError("fixed_mqtt_route_changed")
    if ("command == '/start'" not in routes[5] or
            routes[5].count("            - action: telegram_bot.send_message") != 1):
        raise ValueError("help_route_changed")
    if ("command == '/laist'" not in routes[6] or
            "command[:7] == '/laist_'" not in routes[6] or
            "Laistīšana bloķēta" not in routes[6] or
            routes[6].count("            - action: telegram_bot.send_message") != 1):
        raise ValueError("manual_denial_changed")
    if any(s.count("            - action:") != 1 for s in routes[1:]):
        raise ValueError("extra_route_action")
    for value, count in (
        ('topic: "balkons/cmd"', 4), ("action: mqtt.publish", 4),
        ("retain: false", 4), ("qos: 0", 4),
        ("action: telegram_bot.send_message", 2),
        ("entity_id: notify.andris", 2), ("parse_mode: plain_text", 2),
    ):
        if active.count(value) != count:
            raise ValueError("action_count_or_target_changed")
    forbidden = (
        "balkons/sukna/komanda", 'payload: "ON"', 'payload: "laist"',
        "switch.turn_on", "script.turn_on", "shell_command.",
        "rest_command.", "getUpdates", "telegram_bot.poll",
        "platform: polling", "api_key:", "token:", "Authorization:",
        "Bearer ", "Environment=", "retain: true", "qos: 1", "qos: 2",
        'topic: "{{', 'payload: "{{',
    )
    if any(x in active for x in forbidden):
        raise ValueError("unsafe_surface")
    if re.search(r"(?m)^\s+topic:\s*[\"']?[^\"'\n]*[#+]", active):
        raise ValueError("wildcard_topic")


class PollingSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_staged_contract(self):
        validate_contract(self.source)

    def test_inert_staging_guards_are_mandatory(self):
        self.assertIn("  initial_state: false\n", self.source)
        for fragment in (
            "    - trigger: state\n      enabled: false\n",
            "      default: []\n      enabled: false\n",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.source)
                for new in (fragment.replace("enabled: false", "enabled: true"),
                            fragment.replace("enabled: false\n", "")):
                    with self.assertRaises(ValueError):
                        validate_contract(self.source.replace(fragment, new))
        self.assertEqual(self.source.count("enabled: false"), 2)

    def test_new_ha_ui_mapping_excludes_source_only_id(self):
        entries = [line for line in self.source.splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(entries[0], "- id: balkons_telegram_polling_commands_staged")
        self.assertTrue(all(line.startswith("  ") for line in entries[1:]))
        ui = "\n".join(line[2:] for line in entries[1:]) + "\n"
        self.assertNotRegex(ui, r"(?m)^\s*id:")
        self.assertIn("initial_state: false", ui)
        self.assertIn("  - trigger: state\n    enabled: false\n", ui)
        self.assertIn("    default: []\n    enabled: false\n", ui)
        self.assertIn("REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID", ui)
        self.assertIn("entity_id: event.balkona_laistisana_update_event", ui)
        self.assertIn("REPLACE_WITH_APPROVED_CHAT_ID", ui)
        self.assertIn("REPLACE_WITH_APPROVED_USER_ID", ui)
        self.assertEqual(ui.count("enabled: false"), 2)

    def test_inert_staging_runbook_guardrails(self):
        doc = (ROOT / "docs/BALKONS_HA_POLLING_COMMANDS_SOURCE_ONLY.md").read_text(
            encoding="utf-8")
        marker = "## HA UI inertā sagatavošana (source only, 2026-11-19)"
        self.assertEqual(doc.count(marker), 1)
        for token in (
            "initial_state: false", "enabled: false", "bez `id:`",
            "Composite STRICT LIVE", "chat_id", "user_id", "config_entry_id",
            "STOP", "bez retry", "getUpdates", "NO MQTT publish",
        ):
            self.assertIn(token, doc.split(marker, 1)[1])
    def test_existing_bot_and_notification_parity(self):
        bot = BOT.read_text(encoding="utf-8")
        notify = NOTIFY.read_text(encoding="utf-8")
        self.assertIn('T_CMD = "balkons/cmd"', bot)
        self.assertIn('elif text == "/stop":', bot)
        for name in ("mitrums", "statuss", "raw"):
            self.assertIn(f'_publish_command_with_feedback("{name}")', bot)
        self.assertIn("balkons/telegram_out", notify)

    def test_unapproved_identity_and_args_rejected(self):
        changes = (
            ("initial_state: false", "initial_state: true"),
            ("'REPLACE_WITH_APPROVED_CHAT_ID'", "'0'"),
            ("'REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID'", "'0'"),
            ("trigger.to_state.attributes.bot is mapping", "true"),
            ("trigger.to_state.entity_id == 'event.balkona_laistisana_update_event'", "true"),
            ("(trigger.to_state.attributes.bot.get('config_entry_id') | default('', true) | string) == 'REPLACE_WITH_VERIFIED_BALKONS_POLLING_CONFIG_ENTRY_ID'", "true"),
            ("'REPLACE_WITH_APPROVED_USER_ID'", "'0'"),
            ("event_type == 'telegram_command'", "event_type == 'telegram_text'"),
            ("trigger.to_state.attributes.command is string", "true"),
            ("(trigger.to_state.attributes.args | default([], true) | length) == 0", "true"),
            ("event.balkona_laistisana_update_event", "event.other"),
        )
        for before, after in changes:
            with self.subTest(before=before):
                self.assertIn(before, self.source)
                with self.assertRaises(ValueError):
                    validate_contract(self.source.replace(before, after))

    def test_no_changed_mqtt_command_or_manual_watering_publish(self):
        changes = (
            ('payload: "stop"', 'payload: "ON"'),
            ('payload: "mitrums"', 'payload: "laist"'),
            ('topic: "balkons/cmd"', 'topic: "balkons/#"'),
            ("                qos: 0", "                qos: 1"),
            ("                retain: false", "                retain: true"),
            ("command == '/stop'", "command == '/laist'"),
            ("command[:7] == '/laist_'", "command[:7] == '/laist'"),
            ("      default: []", "      default:\n        - action: mqtt.publish"),
            ("  mode: parallel", "  mode: queued"),
        )
        for before, after in changes:
            with self.subTest(before=before):
                self.assertIn(before, self.source)
                with self.assertRaises(ValueError):
                    validate_contract(self.source.replace(before, after))

    def test_injection_or_extra_automation_rejected(self):
        for extra in (
            "\n- id: extra\n  initial_state: true\n",
            "\n  actions:\n    - action: script.turn_on\n",
            "\n  mode: parallel\n  max: 20\n",
        ):
            with self.assertRaises(ValueError):
                validate_contract(self.source + extra)

    def test_no_network_or_credentials_in_offline_test(self):
        self.assertNotIn('payload: "laist"', self.source)
        self.assertNotIn("MQTT_PASSWORD", self.source)
        self.assertNotIn("api_key:", self.source)
        self.assertNotIn("token:", self.source)
        active = "\n".join(
            line for line in self.source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertNotIn("getUpdates", active)


if __name__ == "__main__":
    unittest.main()
