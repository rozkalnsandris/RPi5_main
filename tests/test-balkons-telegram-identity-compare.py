#!/usr/bin/env python3
"""Adversarial source-only tests for sanitized balcony identity comparison."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops/bin/balkons-telegram-identity-compare"
loader = importlib.machinery.SourceFileLoader("balkons_identity_compare", str(TOOL))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)


def evidence():
    return {
        "schema": mod.SCHEMA,
        "ha": {
            "origin": "HA_PRIVATE_COLLECTOR_CLAIM",
            "entity_id": "notify.andris",
            "entry_mode": "Broadcast",
            "registry_link_checked": True,
            "challenge": "a" * 32,
            "bot_hmac": "b" * 64,
            "chat_hmac": "c" * 64,
        },
        "rpi5": {
            "origin": "RPI5_PRIVATE_COLLECTOR_CLAIM",
            "service": "balkons-bot.service",
            "challenge": "a" * 32,
            "bot_hmac": "b" * 64,
            "chat_hmac": "c" * 64,
        },
    }


class IdentityCompareTests(unittest.TestCase):
    def test_identical_proofs_are_only_consistent_not_cutover_verified(self):
        report = mod.compare_evidence(evidence())
        self.assertEqual(report["result"], "EVIDENCE_CONSISTENT_ORIGIN_UNVERIFIED")
        self.assertTrue(report["bot_chat_claims_match"])
        self.assertFalse(report["ha_registry_link_independently_verified"])
        self.assertFalse(report["user_allowlist_verified"])
        self.assertFalse(report["cutover_ready"])
        self.assertFalse(report["mutation"])

    def test_wrong_bot_chat_or_challenge_are_independent_fail_closed(self):
        for field, code in (("bot_hmac", "BOT_IDENTITY_MISMATCH"),
                            ("chat_hmac", "CHAT_IDENTITY_MISMATCH"),
                            ("challenge", "CHALLENGE_MISMATCH")):
            with self.subTest(field=field):
                data = evidence()
                data["rpi5"][field] = "d" * (32 if field == "challenge" else 64)
                with self.assertRaisesRegex(mod.Blocked, code):
                    mod.compare_evidence(data)

    def test_ha_target_mode_or_registry_link_must_be_exact(self):
        for key, bad in (("entity_id", "notify.andris_2"),
                         ("entry_mode", "Polling"),
                         ("registry_link_checked", False),
                         ("registry_link_checked", 1)):
            data = evidence()
            data["ha"][key] = bad
            with self.assertRaisesRegex(mod.Blocked, "HA_RECIPIENT_LINK_UNCONFIRMED"):
                mod.compare_evidence(data)

    def test_no_unexpected_fields_token_chat_id_or_user_id(self):
        for side, name in (("ha", "token"), ("ha", "chat_id"),
                           ("rpi5", "user_id")):
            data = evidence()
            data[side][name] = "FAKE_SECRET_CANNOT_APPEAR"
            with self.assertRaises(mod.Blocked):
                mod.compare_evidence(data)

    def test_bad_hmac_and_false_origin_claim_block(self):
        for side, name, value in (("ha", "bot_hmac", "x" * 64),
                                  ("rpi5", "chat_hmac", "0"),
                                  ("ha", "origin", "ANOTHER_SOURCE"),
                                  ("rpi5", "service", "random.service")):
            data = evidence()
            data[side][name] = value
            with self.assertRaises(mod.Blocked):
                mod.compare_evidence(data)

    def test_cli_echoes_nothing_from_bad_private_input(self):
        bad = evidence()
        bad["ha"]["token"] = "DO_NOT_ECHO_PRIVATE_VALUE"
        proc = subprocess.run([sys.executable, "-I", str(TOOL)],
                              input=json.dumps(bad).encode(), capture_output=True,
                              check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stderr, b"")
        result = json.loads(proc.stdout)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertNotIn("DO_NOT_ECHO_PRIVATE_VALUE", proc.stdout.decode())
        self.assertFalse(result["cutover_ready"])

    def test_cli_blocks_duplicate_keys_unbounded_and_invalid_json(self):
        for raw in (b'{"schema": 1,"schema":2}', b'x' * 4097, b'not json'):
            with self.subTest(raw=raw[:12]):
                proc = subprocess.run([sys.executable, "-I", str(TOOL)],
                                      input=raw, capture_output=True, check=False)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(json.loads(proc.stdout)["result"], "BLOCKED")
                self.assertEqual(proc.stderr, b"")

    def test_cli_valid_report_cannot_claim_cutover_ready(self):
        proc = subprocess.run([sys.executable, "-I", str(TOOL)],
                              input=json.dumps(evidence()).encode(),
                              capture_output=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(json.loads(proc.stdout)["cutover_ready"])

    def test_source_never_reads_protected_runtime_or_network(self):
        source = TOOL.read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "http.client", "subprocess",
                          "open(", "Path(", "os.environ", "os.system", "getUpdates",
                          "mqtt.publish", "send_message", "getpass", "LoadCredential"):
            self.assertNotIn(forbidden, source)
        self.assertIn("hmac.compare_digest", source)
        self.assertIn("cutover_ready", source)


if __name__ == "__main__":
    unittest.main()
