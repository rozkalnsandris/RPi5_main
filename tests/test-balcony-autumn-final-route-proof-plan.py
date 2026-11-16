#!/usr/bin/env python3
"""Synthetic offline adversarial checks: 11:00 final route proof plan (#1502)."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balcony-autumn-final-route-proof-plan"
loader = importlib.machinery.SourceFileLoader("balcony_final_route_1502", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class FinalRoutePlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="balcony-proof-offline-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel in (m.CANDIDATE, m.BOT, m.SMOKE):
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((ROOT / rel).read_bytes())
            dst.chmod(0o644)

    def change(self, relative: str, old: str, new: str) -> None:
        p = self.root / relative
        contents = p.read_text(encoding="utf-8")
        self.assertIn(old, contents)
        p.write_text(contents.replace(old, new, 1), encoding="utf-8")

    def block(self, code: str) -> None:
        with self.assertRaises(m.Blocked) as exc:
            m.plan(self.root)
        self.assertEqual(str(exc.exception), code)

    def test_offline_pass_explicitly_never_means_live_delivery(self):
        before = {rel: ((self.root / rel).read_bytes(),
                        (self.root / rel).stat().st_mtime_ns)
                  for rel in (m.CANDIDATE, m.BOT, m.SMOKE)}
        obj = m.plan(self.root)
        self.assertEqual(obj["result"], "SOURCE_ROUTE_CONTRACT_PASS")
        self.assertEqual(obj["scope"], "OFFLINE_SOURCE_ONLY")
        self.assertFalse(obj["live_route_ready"])
        self.assertFalse(obj["runtime_mutation_authorized"])
        self.assertFalse(obj["writes_performed"])
        self.assertFalse(obj["mqtt_publish_performed"])
        self.assertFalse(obj["telegram_send_performed"])
        self.assertFalse(obj["actuator_commands_performed"])
        self.assertEqual(obj["network_calls"], 0)
        self.assertTrue(obj["existing_smoke_plan_reused"])
        self.assertTrue(obj["no_live_credential_delegate_assumed"])
        for value in obj["requires_separate_readonly_evidence"].values():
            self.assertEqual(value, "UNVERIFIED")
        self.assertEqual(obj["human_message_receipt"],
                         "UNVERIFIED_NOT_PROVABLE_FROM_API")
        for rel, snapshot in before.items():
            self.assertEqual(((self.root / rel).read_bytes(),
                              (self.root / rel).stat().st_mtime_ns), snapshot)

    def test_candidate_source_byte_drift_blocks(self):
        with (self.root / m.CANDIDATE).open("ab") as f:
            f.write(b"\n# byte drift\n")
        self.block("candidate_sha_drift")

    def test_reject_wrong_bot_subscription_topic(self):
        self.change(m.BOT, 'T_OUT = "balkons/telegram_out"',
                    'T_OUT = "balkons/cmd"')
        self.block("bot_topic_drift")

    def test_reject_no_mqtt_suback_source_subscription(self):
        self.change(m.BOT, "client.subscribe(T_OUT)",
                    'client.subscribe("balkons/cmd")')
        self.block("bot_subscription_drift")

    def test_reject_callback_provenance_changed(self):
        self.change(m.BOT, 'tg_send(text, source="mqtt")',
                    'tg_send(text, source="local")')
        self.block("bot_forwarding_drift")

    def test_reject_wrong_smoke_topic(self):
        self.change(m.SMOKE, 'TOPIC = "balkons/telegram_out"',
                    'TOPIC = "balkons/cmd"')
        self.block("smoke_topic_drift")

    def test_reject_wrong_smoke_rest_route(self):
        self.change(m.SMOKE, 'HA_ROUTE = "/api/services/mqtt/publish"',
                    'HA_ROUTE = "/api/services/switch/turn_on"')
        self.block("smoke_route_drift")

    def test_reject_changed_smoke_message(self):
        self.change(m.SMOKE, "Balkona MQTT-Telegram sakaru tests. Tikai pazinojums.",
                    "laist")
        self.block("smoke_payload_drift")

    def test_reject_retained_or_qos_changed(self):
        self.change(m.SMOKE, '"qos": 0, "retain": False}',
                    '"qos": 1, "retain": True}')
        self.block("smoke_request_drift")

    def test_reject_unsafe_symlink(self):
        p = self.root / m.CANDIDATE
        alternate = self.root / "synthetic-private-value"
        alternate.write_text("SYNTHETIC_SECRET_DO_NOT_LEAK", encoding="utf-8")
        p.unlink()
        p.symlink_to(alternate)
        self.block("public_source_unsafe")

    def test_reject_hardlink_and_world_writable(self):
        p = self.root / m.BOT
        alias = self.root / "hardlink"
        os.link(p, alias)
        self.block("public_source_unsafe")
        alias.unlink()
        p.chmod(0o666)
        self.block("public_source_unsafe")

    def test_unsupported_path_refused(self):
        with self.assertRaises(m.Blocked) as e:
            m.read_public(self.root, ".env")
        self.assertEqual(str(e.exception), "public_source_not_allowlisted")

    def test_no_network_secret_or_write_implementation(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("import requests", "import socket",
                          "import urllib", "import subprocess",
                          "api.telegram.org/bot", "mosquitto_pub",
                          "os.replace(", "os.O_CREAT", "switch.turn_on",
                          "open('.env'", 'open(".env"'):
            self.assertNotIn(forbidden, source)
        self.assertIn('"/api/"', json.dumps(m.plan(self.root)))
        self.assertIn('"getMe"', json.dumps(m.plan(self.root)))
        self.assertIn('"getChat"', json.dumps(m.plan(self.root)))

    def test_cli_check_offline_output_not_a_live_pass(self):
        proc = subprocess.run(
            ["/usr/bin/python3", "-I", "-B", str(SCRIPT), "--check"],
            cwd=ROOT, capture_output=True, text=True, timeout=12, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[:120])
        report = json.loads(proc.stdout)
        self.assertEqual(report["result"], "SOURCE_ROUTE_CONTRACT_PASS")
        self.assertFalse(report["live_route_ready"])
        self.assertEqual(report["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()
