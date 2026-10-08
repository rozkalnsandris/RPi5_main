#!/usr/bin/env python3
"""Offline source+rollout boundary tests for issue #920."""
from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balkons-bot-latency-rollout-plan"
loader = importlib.machinery.SourceFileLoader("balcony_latency_plan", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
plan = importlib.util.module_from_spec(spec)
loader.exec_module(plan)


class RolloutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in plan.PATHS:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
        self.sha = "a" * 40
        self.bundle = plan.source_bundle(self.root, self.sha)

    def clean_evidence(self):
        evidence = dict(plan.EXPECTED)
        evidence.update(self.bundle)
        return evidence

    def test_missing_evidence_fails_closed(self):
        result = plan.classify(self.bundle)
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["blockers"], ["evidence_not_supplied"])
        self.assertFalse(result["live_authority"])
        self.assertFalse(result["merge_authority"])

    def test_projection_never_authorizes_live(self):
        result = plan.classify(self.bundle, self.clean_evidence())
        self.assertEqual(result["result"], "SOURCE_CANDIDATE")
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["live_authority"])
        self.assertFalse(result["writes_performed"])

    def test_protected_extra_fields_rejected_without_echo(self):
        evidence = self.clean_evidence()
        evidence["telegram_token"] = "private-example"
        result = plan.classify(self.bundle, evidence)
        self.assertEqual(result["blockers"], ["evidence_shape_invalid"])
        self.assertNotIn("private-example", json.dumps(result))
        self.assertNotIn("telegram_token", json.dumps(result))

    def test_each_runtime_gate_fails_closed(self):
        for field in plan.REASONS:
            with self.subTest(field=field):
                evidence = self.clean_evidence()
                evidence[field] = True
                result = plan.classify(self.bundle, evidence)
                self.assertEqual(result["result"], "BLOCKED")
                self.assertFalse(result["live_authority"])

    def test_sha_drift_and_modified_source_rejected(self):
        for field in ("repo_sha", "source_sha256", "bundle_sha256"):
            with self.subTest(field=field):
                evidence = self.clean_evidence()
                evidence[field] = "0" * (40 if field == "repo_sha" else 64)
                self.assertEqual(plan.classify(self.bundle, evidence)["blockers"], [field + "_mismatch"])
        source = self.root / plan.SOURCE
        source.write_bytes(source.read_bytes() + b"\n# drift\n")
        new_bundle = plan.source_bundle(self.root, self.sha)
        self.assertNotEqual(new_bundle["bundle_sha256"], self.bundle["bundle_sha256"])

    def test_symlink_and_contract_violation_block(self):
        source = self.root / plan.SOURCE
        source.unlink()
        source.symlink_to(self.root / plan.CONTRACT)
        with self.assertRaises(ValueError):
            plan.source_bundle(self.root, self.sha)
        source.unlink()
        shutil.copyfile(ROOT / plan.SOURCE, source)
        contract_path = self.root / plan.CONTRACT
        payload = json.loads(contract_path.read_text())
        payload["can_apply"] = True
        contract_path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "contract_drift"):
            plan.source_bundle(self.root, self.sha)

    def test_sensitive_mqtt_semantics_and_auth_unchanged(self):
        source = (ROOT / plan.SOURCE).read_text(encoding="utf-8")
        tree = ast.parse(source)
        defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        pubs = [
            n for n in ast.walk(defs["_publish_command"])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "publish"
        ]
        self.assertEqual(len(pubs), 1)
        self.assertEqual(len(pubs[0].args), 2)
        self.assertEqual(pubs[0].keywords, [])  # Paho publish QoS 0, retain=False
        self.assertIn('str(incoming_chat_id) != _allowed_chat_id', source)
        self.assertIn('T_CMD = "balkons/cmd"', source)
        self.assertIn('T_OUT = "balkons/telegram_out"', source)
        self.assertIn("TELEGRAM_SEND_QUEUE_SIZE = 16", source)
        self.assertIn("_outbound_messages.put_nowait", source)
        self.assertIn("timeout=10", source)
        self.assertNotIn("wait_for_publish", source)
        cmd = ast.get_source_segment(source, defs["handle_command"])
        for key in ("/laist", "/laist_", "/stop", "/mitrums", "/statuss", "/raw"):
            self.assertIn(key, cmd)

    def test_encrypted_overlay_and_no_sigkill_unchanged(self):
        lines = (ROOT / "ops/systemd/balkons-bot-runtime-override.conf").read_text().splitlines()
        self.assertEqual(lines.count("LoadCredential="), 1)
        self.assertEqual(sum(x.startswith("LoadCredentialEncrypted=") and x != "LoadCredentialEncrypted=" for x in lines), 5)
        self.assertIn("SendSIGKILL=no", lines)

    def test_planner_contains_no_mutation_primitives(self):
        text = SCRIPT.read_text()
        for forbidden in ("subprocess", "requests.", "paho.", "os.system", "systemctl ", "docker ", "mqtt.publish", "unlink(", "write_text(", "write_bytes("):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
