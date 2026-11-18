#!/usr/bin/env python3
"""Offline, source-level contract for staged HA-native Telegram notifications.

No Home Assistant imports, MQTT clients, network, protected config or live hosts.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ops/homeassistant/balkons-telegram-native-notify.yaml"
BOT = ROOT / "ops/lib/balkons-bot.py"
CONTROLLER = ROOT / "ops/bin/balcony-watering-autumn"

SOURCE_ONLY = "SOURCE ONLY (#1490)"
EVENT_TOPIC = "balkons/telegram_out"
CHAT_ENTITY = "notify.replace_with_approved_telegram_chat"
PAYLOAD_GUARD = (
    "{{ trigger.topic == 'balkons/telegram_out'\n"
    "           and trigger.payload is string\n"
    "           and 0 < (trigger.payload | length) <= 1024 }}"
)


def validate_native_reference(text: str) -> None:
    """Reject deployment-like changes even when test cases mutate a fixture."""
    required = (
        SOURCE_ONLY,
        "- id: balkons_telegram_native_notification_staged",
        "  initial_state: false\n",
        "    - trigger: mqtt\n",
        f'      topic: "{EVENT_TOPIC}"\n',
        "      qos: 0\n",
        "    - condition: template\n",
        PAYLOAD_GUARD,
        "    - action: telegram_bot.send_message\n",
        f"        entity_id: {CHAT_ENTITY}\n",
        '        message: "{{ trigger.payload }}"\n',
        "        parse_mode: plain_text\n",
        "  mode: queued\n",
        "  max: 5\n",
    )
    if not all(text.count(fragment) == 1 for fragment in required):
        raise ValueError("native_reference_contract_changed")
    # No extra automations, action targets, automation triggers or sources.
    if (len(re.findall(r"^- id:", text, flags=re.MULTILINE)) != 1
            or len(re.findall(r"^\s+- trigger:", text, flags=re.MULTILINE)) != 1
            or len(re.findall(r"^\s+- action:", text, flags=re.MULTILINE)) != 1
            or text.count("initial_state:") != 1
            or text.count("entity_id:") != 1):
        raise ValueError("native_reference_extra_action")
    # Restrict the actual YAML (not comments). There can be no actuator or
    # MQTT publishing actions, no credential fields and no second bot poller.
    executable = "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    forbidden = (
        "balkons/cmd", "mqtt.publish", "switch.turn_on",
        "homeassistant.turn_on", "rest_command.", "shell_command.",
        "script.turn_on", "telegram_bot.get_updates", "getUpdates",
        "telegram_bot.poll", "platform: telegram",
        "notify.telegram", "Bearer ", "HASS_TOKEN",
        "api_key:", "token:", "chat_id:",
        "client.publish", "curl ", "requests.",
        "retain: true", "retain: True", "qos: 1", "qos: 2",
        "laist", "stop",
    )
    if any(fragment in executable for fragment in forbidden):
        raise ValueError("native_reference_forbidden_action")
    if re.search(r"^\s+topic:\s*[\"']?[^\"'\n]*[#+]", executable, re.MULTILINE):
        raise ValueError("native_reference_wildcard_topic")



# This source-only drop-in is not installed or activated by the test suite.
CUTOVER_DROPIN = ROOT / "ops/systemd/balkons-bot-telegram-forward-off.conf"


def validate_forward_off_dropin(text: str) -> None:
    """Reject anything besides one exact non-secret service environment value."""
    if "\r" in text or "\x00" in text:
        raise ValueError("forward_off_dropin_invalid_bytes")
    effective = tuple(
        line.strip() for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if effective != (
        "[Service]",
        "Environment=BALKONS_MQTT_TELEGRAM_FORWARD=0",
    ):
        raise ValueError("forward_off_dropin_extra_directive")
    if any(token in text for token in (
        "LoadCredential", "ExecStart", "ExecStop", "EnvironmentFile",
        "PassEnvironment", "UnsetEnvironment", "mqtt.publish",
        "balkons/cmd", "telegram-token", "mqtt-secret",
    )):
        raise ValueError("forward_off_dropin_forbidden_content")

class HANativeTelegramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = TEMPLATE.read_text(encoding="utf-8")

    def test_one_exact_staged_notification_only(self):
        validate_native_reference(self.source)

    def test_current_bridge_topic_matches_native_reference(self):
        bridge = BOT.read_text(encoding="utf-8")
        self.assertIn('T_OUT = "balkons/telegram_out"', bridge)
        self.assertIn('T_CMD = "balkons/cmd"', bridge)
        self.assertIn('tg_send(text, source="mqtt")', bridge)

    def test_current_controller_publishes_notification_only(self):
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn(
            '{"topic": "balkons/telegram_out", "payload": sys.stdin.read(), "qos": 0, "retain": False}',
            controller,
        )
        self.assertIn("/api/services/mqtt/publish", controller)

    def test_manual_watering_is_safety_gated_in_current_bot(self):
        bridge = BOT.read_text(encoding="utf-8")
        for invariant in (
            'SAFETY_STATE_SCHEMA = "rozkalns.balcony-watering-safety.v1"',
            "SAFETY_STATE_DEFAULT_MAX_AGE_S = 6 * 60 * 60",
            "sensor_total != 10", "already_watered_today",
            "frost_blocked", "sensor_coverage_ok",
            'data["decision"] != "manual_permit"',
            "allowed, reason = _manual_watering_admission()",
            'if text == "/laist":',
            'elif text.startswith("/laist_"):',
            'elif text == "/stop":',
        ):
            self.assertIn(invariant, bridge)

    def test_historical_command_topic_not_in_native_automation(self):
        executable = "\n".join(line for line in self.source.splitlines()
                               if not line.lstrip().startswith("#"))
        self.assertNotIn("balkons/cmd", executable)
        self.assertNotIn("mqtt.publish", executable)

    def test_no_active_telegram_second_poller(self):
        self.assertNotIn("getUpdates", self.source)
        self.assertNotIn("platform: polling", self.source.lower())

    def test_legacy_notify_platform_is_absent(self):
        self.assertNotIn("platform: telegram", self.source)
        self.assertNotIn("notify.telegram", self.source)

    def test_no_secret_or_direct_http_transport(self):
        for word in ("HASS_TOKEN", "api_key:", "Authorization:",
                     "Bearer ", "requests.post", "curl "):
            self.assertNotIn(word, self.source)

    def test_unauthorized_enabling_rejected(self):
        with self.assertRaisesRegex(ValueError, "native_reference_contract_changed"):
            validate_native_reference(
                self.source.replace("initial_state: false", "initial_state: true")
            )

    def test_extra_action_rejected(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source.replace(
                    "  mode: queued\n",
                    "    - action: mqtt.publish\n"
                    "      data:\n"
                    "        topic: balkons/cmd\n"
                    "        payload: laist\n"
                    "  mode: queued\n",
                )
            )

    def test_changed_topic_rejected(self):
        with self.assertRaisesRegex(ValueError, "native_reference_contract_changed"):
            validate_native_reference(
                self.source.replace('topic: "balkons/telegram_out"', 'topic: "balkons/cmd"')
            )

    def test_unapproved_recipient_rejected(self):
        with self.assertRaisesRegex(ValueError, "native_reference_contract_changed"):
            validate_native_reference(
                self.source.replace(
                    "notify.replace_with_approved_telegram_chat",
                    "notify.some_other_chat",
                )
            )

    def test_no_topic_wildcard(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source.replace('topic: "balkons/telegram_out"', 'topic: "balkons/#"')
            )

    def test_no_telegram_send_without_recipient(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source.replace(
                    "        entity_id: notify.replace_with_approved_telegram_chat\n", ""
                )
            )

    def test_no_unbounded_mqtt_payload(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source.replace("<= 1024", "<= 999999")
            )

    def test_plain_text_parse_mode_required(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source.replace("parse_mode: plain_text", "parse_mode: markdownv2")
            )

    def test_no_extra_automation_even_if_disabled(self):
        with self.assertRaises(ValueError):
            validate_native_reference(
                self.source + "\n- id: extra_unsafe\n  initial_state: false\n"
            )

    def test_forward_off_dropin_exact_and_inert(self):
        source = CUTOVER_DROPIN.read_text(encoding="utf-8")
        validate_forward_off_dropin(source)
        self.assertIn("SOURCE ONLY (#1523)", source)
        self.assertIn("96-balkons-telegram-forward-off.conf", source)

    def test_forward_off_dropin_rejects_unsafe_edits(self):
        source = CUTOVER_DROPIN.read_text(encoding="utf-8")
        for altered in (
            source.replace("BALKONS_MQTT_TELEGRAM_FORWARD=0",
                           "BALKONS_MQTT_TELEGRAM_FORWARD=1"),
            source + "ExecStart=/bin/sh -c true\\n",
            source + "Environment=EXTRA_VAR=anything\\n",
            source + "Environment=\\n",
            source + "LoadCredential=telegram-token:unsafe\\n",
            source + "ExecStop=/usr/bin/systemctl restart balkons-bot.service\\n",
        ):
            with self.subTest(altered=altered[-75:]):
                with self.assertRaises(ValueError):
                    validate_forward_off_dropin(altered)

    def test_forward_off_preserves_stop_and_fails_closed_against_duplication(self):
        bot = BOT.read_text(encoding="utf-8")
        self.assertIn(
            'return os.environ.get("BALKONS_MQTT_TELEGRAM_FORWARD", "1") == "1"',
            bot,
        )
        self.assertIn('if not _mqtt_notifications_enabled():\\n        return', bot)
        self.assertIn('client.subscribe(T_OUT)', bot)
        self.assertIn(
            'elif text == "/stop":\\n        _publish_command_with_feedback("stop")',
            bot,
        )
        self.assertIn('allowed, reason = _manual_watering_admission()', bot)



if __name__ == "__main__":
    unittest.main()
