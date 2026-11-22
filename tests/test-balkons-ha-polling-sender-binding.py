#!/usr/bin/env python3
"""Synthetic adversarial tests for private sender-binding adapter core."""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/lib/balkons-ha-polling-sender-binding.py"
loader = importlib.machinery.SourceFileLoader("sender_binding", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
binding = importlib.util.module_from_spec(spec)
loader.exec_module(binding)


def evidence():
    event = dict(entity_id=binding.EVENT, event_type="telegram_command",
                 bot_config_entry_id="SYNTHETIC01", chat_id=-1001234,
                 user_id=123456, args="")
    approved = dict(bot_config_entry_id="SYNTHETIC01", chat_id="-1001234",
                    user_id="123456")
    registry = dict(entity_id=binding.EVENT,
                    bot_config_entry_id="SYNTHETIC01", entry_mode="Polling",
                    registry_event_link_checked=True)
    return dict(event=event, approved=approved, registry=registry)


class SenderBindingTests(unittest.TestCase):
    def test_synthetic_match_is_never_proven_authentication(self):
        report = binding.evaluate_binding(**evidence())
        self.assertEqual(report["result"], "CONSISTENT_INPUTS_ORIGIN_UNVERIFIED")
        self.assertTrue(report["sender_claims_match"])
        for field in ("independent_provenance_verified", "sender_authorization_verified",
                      "event_freshness_verified", "cutover_ready", "mutation"):
            self.assertIs(report[field], False)
        for forbidden in ("SYNTHETIC01", "123456", "-1001234", "chat_id", "user_id"):
            self.assertNotIn(forbidden, repr(report))

    def test_missing_or_wrong_fields_fail_closed(self):
        for section, field, replacement, code in (
            ("event", "entity_id", "event.other", "EVENT_UNEXPECTED"),
            ("event", "event_type", "telegram_text", "EVENT_UNEXPECTED"),
            ("event", "args", ["unexpected"], "EVENT_UNEXPECTED"),
            ("event", "bot_config_entry_id", "ANOTHER01", "BOT_ENTRY_MISMATCH"),
            ("registry", "bot_config_entry_id", "ANOTHER01", "BOT_ENTRY_MISMATCH"),
            ("registry", "entry_mode", "Broadcast", "REGISTRY_LINK_CLAIM_INVALID"),
            ("registry", "registry_event_link_checked", False, "REGISTRY_LINK_CLAIM_INVALID"),
            ("approved", "chat_id", "-1001235", "CHAT_ID_MISMATCH"),
            ("approved", "user_id", "123457", "USER_ID_MISMATCH"),
        ):
            with self.subTest(section=section, field=field):
                values = evidence()
                values[section][field] = replacement
                with self.assertRaisesRegex(binding.BindingRejected, code):
                    binding.evaluate_binding(**values)

    def test_chat_and_user_cannot_be_swapped_or_inferred_from_name(self):
        values = evidence()
        values["approved"]["user_id"] = values["event"]["chat_id"]
        with self.assertRaises(binding.BindingRejected):
            binding.evaluate_binding(**values)
        values = evidence()
        values["event"]["friendly_name"] = "Andris"
        with self.assertRaisesRegex(binding.BindingRejected, "EVENT_SHAPE_INVALID"):
            binding.evaluate_binding(**values)

    def test_invalid_ids_and_coercion_rejected_without_echo(self):
        for part, key, value in (
            ("event", "chat_id", 0), ("event", "chat_id", "-0"),
            ("approved", "chat_id", "  -1001234"),
            ("event", "user_id", -1), ("event", "user_id", True),
            ("event", "user_id", "00123456"),
            ("approved", "user_id", "SYNTHETIC_SECRET_ID"),
            ("approved", "bot_config_entry_id", "SYNTHETIC_SECRET_ID!"),
            ("event", "args", True),
        ):
            with self.subTest(part=part, key=key, value=value):
                data = evidence()
                data[part][key] = value
                with self.assertRaises(binding.BindingRejected) as ctx:
                    binding.evaluate_binding(**data)
                self.assertNotIn(str(value), str(ctx.exception))

    def test_exact_shape_no_raw_private_fields(self):
        for section in ("event", "approved", "registry"):
            data = evidence()
            data[section]["token"] = "SYNTHETIC_SECRET"
            with self.assertRaises(binding.BindingRejected):
                binding.evaluate_binding(**data)

    def test_no_runtime_access_or_transport(self):
        source = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.environ", "sys.argv", "sys.stdin",
                          "open(", "Path(", "requests", "urllib", "http.client",
                          "getUpdates", "mqtt.publish", "send_message", ".storage",
                          "print(", "logging."):
            self.assertNotIn(forbidden, source)
        self.assertIn("hmac.compare_digest", source)


if __name__ == "__main__":
    unittest.main()
