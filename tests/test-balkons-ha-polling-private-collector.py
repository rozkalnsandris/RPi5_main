#!/usr/bin/env python3
"""Synthetic HA-object tests; no credentials, HA package, network or I/O."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/lib/balkons-ha-polling-private-collector.py"
loader = importlib.machinery.SourceFileLoader("ha_private_collector", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
collector = importlib.util.module_from_spec(spec)
loader.exec_module(collector)


def obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


class FakeRegistry:
    def __init__(self, entity):
        self.entity = entity

    def async_get(self, entity_id):
        return self.entity if entity_id == collector.EVENT_ENTITY else None


class FakeConfigEntries:
    def __init__(self, entry):
        self.entry = entry

    def async_get_entry(self, entry_id):
        return self.entry if entry_id == self.entry.entry_id else None


def setup():
    registry = FakeRegistry(obj(platform="telegram_bot", config_entry_id="SYNTHETIC_BOT"))
    config = obj(entry_id="SYNTHETIC_BOT", domain="telegram_bot", state="loaded",
                 data={"platform": "polling", "secret_dont_read": "SYNTHETIC_SECRET"},
                 subentries={"sub-id": obj(subentry_type="allowed_chat_ids",
                                              data={"chat_id": -1002345})})
    attributes = {"bot": {"config_entry_id": "SYNTHETIC_BOT"},
                  "event_type": "telegram_command", "command": "/statuss",
                  "args": "", "chat_id": -1002345, "user_id": 731234}
    state = obj(attributes=attributes, last_changed=datetime.now(timezone.utc))
    hass = obj(config_entries=FakeConfigEntries(config),
               states=obj(get=lambda _: state))
    modules = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
    }
    modules["homeassistant.config_entries"].ConfigEntryState = obj(LOADED="loaded")
    modules["homeassistant.helpers"].entity_registry = obj(async_get=lambda _: registry)
    return hass, registry, config, state, modules


class HACollectorTests(unittest.TestCase):
    def run_check(self, setup_data=None, *, chat=-1002345, user=731234):
        hass, registry, config, state, modules = setup_data or setup()
        with patch.dict(sys.modules, modules):
            return collector.collect_sender_binding(
                hass=hass, approved_chat_id=chat, approved_user_id=user)

    def test_valid_synthetic_match_still_not_cutover(self):
        result = self.run_check()
        self.assertEqual(result["result"], "INPUTS_CONSISTENT_PROVENANCE_UNVERIFIED")
        self.assertEqual(result["reason"], "MATCH_NO_OWNER_ATTESTATION")
        self.assertTrue(result["ha_registry_binding_checked"])
        self.assertTrue(result["allowed_chat_subentry_checked"])
        for field in ("owner_user_provenance_verified", "notify_andris_binding_verified",
                      "cutover_ready", "mutation"):
            self.assertIs(result[field], False)
        for secret in ("731234", "-1002345", "SYNTHETIC_BOT", "SYNTHETIC_SECRET"):
            self.assertNotIn(secret, repr(result))

    def test_no_owner_or_wrong_sender(self):
        for chat, user, reason in ((-1002344, 731234, "CHAT_ID_MISMATCH"),
                                   (-1002345, 731235, "USER_ID_MISMATCH"),
                                   (None, 731234, "ID_FORMAT_INVALID"),
                                   (-1002345, None, "ID_FORMAT_INVALID")):
            with self.subTest(chat=chat, user=user):
                out = self.run_check(chat=chat, user=user)
                self.assertEqual(out["reason"], reason)
                self.assertFalse(out["cutover_ready"])

    def test_wrong_registry_or_bot_never_matches(self):
        for item, key, value, reason in (
            ("registry", "platform", "other", "EVENT_REGISTRY_UNVERIFIED"),
            ("config", "domain", "other", "POLLING_ENTRY_UNVERIFIED"),
            ("config", "state", "not_loaded", "POLLING_ENTRY_UNVERIFIED"),
            ("state", "event_type", "telegram_text", "COMMAND_EVENT_UNEXPECTED"),
            ("state", "command", "/laist", "COMMAND_EVENT_UNEXPECTED"),
            ("state", "args", ["unexpected"], "COMMAND_EVENT_UNEXPECTED"),
            ("state", "bot", {"config_entry_id": "OTHER"}, "BOT_ENTRY_MISMATCH"),
        ):
            with self.subTest(item=item, key=key):
                args = setup()
                target = {"registry": args[1], "config": args[2], "state": args[3]}[item]
                if item == "state":
                    target.attributes[key] = value
                else:
                    setattr(target.entity if item == "registry" else target, key, value)
                self.assertEqual(self.run_check(args)["reason"], reason)

    def test_allowlist_rejects_missing_or_duplicated_chat(self):
        data = setup()
        data[2].subentries = {}
        self.assertEqual(self.run_check(data)["reason"], "ALLOWLIST_UNVERIFIED")
        data = setup()
        data[2].subentries["second"] = obj(subentry_type="allowed_chat_ids",
                                            data={"chat_id": -1002345})
        self.assertEqual(self.run_check(data)["reason"], "ALLOWLIST_UNVERIFIED")

    def test_old_or_future_event_rejected(self):
        for delta in (-150, 15):
            data = setup()
            data[3].last_changed = datetime.now(timezone.utc) + timedelta(seconds=delta)
            self.assertEqual(self.run_check(data)["reason"], "EVENT_FRESHNESS_UNVERIFIED")

    def test_synthetic_error_never_prints_identifiers(self):
        data = setup()
        data[2].subentries["sub-id"].data["chat_id"] = "SYNTHETIC_PRIVATE_VALUE"
        result = self.run_check(data)
        self.assertEqual(result["reason"], "ID_FORMAT_INVALID")
        self.assertNotIn("SYNTHETIC_PRIVATE_VALUE", repr(result))
        self.assertNotIn("SYNTHETIC_SECRET", repr(result))

    def test_no_files_network_secrets_or_commands(self):
        source = SOURCE.read_text(encoding="utf-8")
        for bad in ("subprocess", "os.environ", "sys.argv", "sys.stdin", "open(",
                    "Path(", "requests", "urllib", "http.client", "getUpdates",
                    "mqtt.publish", "send_message", ".storage", "print(",
                    "logging.", "config_entry.data[\"api_key\"]", "entry.data.get(\"api_key\")"):
            self.assertNotIn(bad, source)
        self.assertIn("async_get_entry", source)
        self.assertIn("allowed_chat_ids", source)
        self.assertIn("hmac.compare_digest", source)


if __name__ == "__main__":
    unittest.main()
