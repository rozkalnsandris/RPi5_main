#!/usr/bin/env python3
"""Synthetic, offline tests for the untrusted identity claim builder."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLAIM = ROOT / "ops/lib/balkons-telegram-identity-claim.py"
COMPARATOR = ROOT / "ops/bin/balkons-telegram-identity-compare"


def load(name: str, file: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(file))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


claim = load("balkons_identity_claim", CLAIM)
compare = load("balkons_identity_compare", COMPARATOR)

BOT = b"synthetic-bot-id-value"
CHAT = b"synthetic-chat-id-value"
KEY = bytes(range(32))
NONCE = bytes(range(16))


def ha(**changes):
    args = dict(token=BOT, chat=CHAT, session_key=KEY, challenge=NONCE,
                entity_id="notify.andris", entry_mode="Broadcast",
                registry_link_checked=True)
    args.update(changes)
    return claim.ha_claim(**args)


def rpi5(**changes):
    args = dict(token=BOT, chat=CHAT, session_key=KEY, challenge=NONCE,
                service="balkons-bot.service")
    args.update(changes)
    return claim.rpi5_claim(**args)


class EvidenceClaimTests(unittest.TestCase):
    def test_synthetic_consistency_is_not_origin_proof(self):
        output = compare.compare_evidence({"schema": claim.SCHEMA,
                                           "ha": ha(), "rpi5": rpi5()})
        self.assertEqual(output["result"], "EVIDENCE_CONSISTENT_ORIGIN_UNVERIFIED")
        self.assertFalse(output["cutover_ready"])
        self.assertFalse(output["user_allowlist_verified"])
        self.assertFalse(output["ha_registry_link_independently_verified"])
        self.assertFalse(output["mutation"])

    def test_fixed_known_hmac_vectors_guard_wire_format(self):
        self.assertEqual(
            ha()["bot_hmac"],
            "d8b802fb7e5ed3ab6798e499294f0efc4b6f9ea03bb126d8af771383ed73ad2d",
        )
        self.assertEqual(
            rpi5()["chat_hmac"],
            "48daa8c35da1321d1b0825fa2ba67c9d5cae73df29fa006bfabb65ca64f184e8",
        )

    def test_token_mismatch_never_forges_match(self):
        with self.assertRaisesRegex(compare.Blocked, "BOT_IDENTITY_MISMATCH"):
            compare.compare_evidence({"schema": claim.SCHEMA, "ha": ha(),
                                      "rpi5": rpi5(token=b"another-synthetic-id")})

    def test_chat_mismatch_never_forges_match(self):
        with self.assertRaisesRegex(compare.Blocked, "CHAT_IDENTITY_MISMATCH"):
            compare.compare_evidence({"schema": claim.SCHEMA, "ha": ha(),
                                      "rpi5": rpi5(chat=b"another-synthetic-chat")})

    def test_nonce_mismatch_is_rejected(self):
        with self.assertRaisesRegex(compare.Blocked, "CHALLENGE_MISMATCH"):
            compare.compare_evidence({"schema": claim.SCHEMA, "ha": ha(),
                                      "rpi5": rpi5(challenge=bytes(range(1, 17)))})

    def test_independent_bot_and_chat_domain_separation(self):
        swapped = rpi5(token=CHAT, chat=BOT)
        self.assertNotEqual(ha()["bot_hmac"], swapped["chat_hmac"])
        self.assertNotEqual(ha()["chat_hmac"], swapped["bot_hmac"])
        self.assertEqual(len(ha()["bot_hmac"]), 64)
        self.assertEqual(ha()["challenge"], NONCE.hex())

    def test_invalid_ha_provenance_claim_is_blocked(self):
        for changes in ({"entity_id": "notify.andris_2"},
                        {"entry_mode": "Polling"},
                        {"registry_link_checked": False},
                        {"registry_link_checked": 1},
                        {"registry_link_checked": "true"}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(claim.ClaimInputError, "HA_LINK_CLAIM_INVALID"):
                    ha(**changes)

    def test_invalid_rpi5_target_is_blocked(self):
        for name in ("other.service", "balkons-bot.service ", None):
            with self.subTest(name=name):
                with self.assertRaisesRegex(claim.ClaimInputError, "RPI5_SERVICE_CLAIM_INVALID"):
                    rpi5(service=name)

    def test_invalid_key_challenge_and_secret_values_are_blocked(self):
        for changes in ({"session_key": b"short"},
                        {"challenge": b"short"},
                        {"token": "raw-token-not-allowed"},
                        {"chat": b""},
                        {"chat": b"\xff"},
                        {"token": b"nul\x00token"},
                        {"token": b"x" * 513},
                        {"session_key": bytearray(KEY)}):
            with self.subTest(changes=changes):
                with self.assertRaises(claim.ClaimInputError):
                    ha(**changes)

    def test_fixed_errors_never_echo_supplied_values(self):
        bad = b"SYNTHETIC_PRIVATE_VALUE_MUST_NOT_LEAK\x00"
        with self.assertRaises(claim.ClaimInputError) as raised:
            ha(token=bad)
        self.assertNotIn("SYNTHETIC_PRIVATE", repr(raised.exception))
        self.assertNotIn("SYNTHETIC_PRIVATE", str(raised.exception))

    def test_output_schema_exact_and_no_raw_fields(self):
        data = {"schema": claim.SCHEMA, "ha": ha(), "rpi5": rpi5()}
        self.assertEqual(set(data["ha"]), compare.HA_KEYS)
        self.assertEqual(set(data["rpi5"]), compare.RPI5_KEYS)
        text = json.dumps(data)
        self.assertNotIn(BOT.decode(), text)
        self.assertNotIn(CHAT.decode(), text)
        self.assertNotIn(KEY.hex(), text)
        self.assertNotIn("user_id", text)

    def test_source_contains_no_sensitive_io_or_live_calls(self):
        source = CLAIM.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.environ", "sys.argv", "sys.stdin", "open(",
                          "os.read", "requests", "http.client", "urllib", "getUpdates",
                          "telegram_bot.send_message", "mqtt.publish", ".storage", "Path("):
            self.assertNotIn(forbidden, source)
        self.assertIn("hmac.new", source)
        self.assertNotIn("random", source)


if __name__ == "__main__":
    unittest.main()
