#!/usr/bin/env python3
"""Offline-only safety regressions for exact #1332 Category ↔ Topic 21-pair operator."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/ausmalwiese-category-topic-links-bulk-v1.py"
loader = SourceFileLoader("category_topic_bulk_1332", str(FILE))
spec = spec_from_loader(loader.name, loader)
operator = module_from_spec(spec)
spec.loader.exec_module(operator)


def public_taxonomy():
    return {"categories": [{"id": cid, "label": cid} for cid in operator.CATEGORY_IDS],
            "topics": [{"id": tid, "kind": "seasonal" if tid in operator.SEASONAL else "evergreen"}
                       for tid in (*operator.SEASONAL, *operator.EVERGREEN)]}


class AtomicCategoryTopicTest(unittest.TestCase):
    def test_fixed_plan_complete_and_hash_deterministic(self):
        data = operator.planned_bytes()
        doc = json.loads(data)
        self.assertEqual(data, operator.canonical(doc))
        self.assertEqual(doc["revision"], 2)
        self.assertEqual(doc["schema"], operator.SCHEMA)
        pairs = [(x["category"], x["topic"]) for x in doc["links"]]
        self.assertEqual(pairs, sorted(set(pairs)))
        self.assertEqual(len(pairs), 21)
        self.assertEqual(set(t for _, t in pairs), set(operator.SEASONAL) | set(operator.EVERGREEN))
        self.assertTrue(all(c == "jahreszeiten" for c, t in pairs if t in operator.SEASONAL))
        self.assertTrue(all(c != "jahreszeiten" for c, t in pairs if t in operator.EVERGREEN))
        self.assertEqual(hashlib.sha256(data).hexdigest(), operator.sha256(data))

    def test_exact_initial_baseline_sha(self):
        data = operator.canonical({"schema": operator.SCHEMA, "revision": 1, "links": []})
        self.assertEqual(operator.sha256(data), operator.BASELINE_SHA)

    def test_invalid_topic_and_category_sets_fail_closed(self):
        operator.validate_taxonomy(public_taxonomy())
        wrong = public_taxonomy()
        wrong["topics"][0]["kind"] = "evergreen"
        with self.assertRaises(operator.Stop):
            operator.validate_taxonomy(wrong)
        wrong = public_taxonomy()
        wrong["topics"].append(wrong["topics"][0])
        with self.assertRaises(operator.Stop):
            operator.validate_taxonomy(wrong)
        wrong = public_taxonomy()
        wrong["categories"].pop()
        with self.assertRaises(operator.Stop):
            operator.validate_taxonomy(wrong)

    def test_default_plan_never_reads_live_or_writes(self):
        output = subprocess.run([sys.executable, str(FILE), "--plan"], check=True,
                                capture_output=True, text=True, timeout=6)
        doc = json.loads(output.stdout)
        self.assertEqual(doc["operation"], "PLAN_ONLY_NO_WRITES")
        self.assertEqual(len(doc["links"]), 21)
        self.assertEqual(doc["next_registry_sha256"], operator.sha256(operator.planned_bytes()))
        output = subprocess.run([sys.executable, str(FILE), "--apply"], check=False,
                                capture_output=True, text=True, timeout=6)
        self.assertNotEqual(output.returncode, 0)
        self.assertIn("STOP:", output.stderr)
        self.assertNotIn("EXACT_21_CATEGORY_TOPIC_LINKS=PASS", output.stdout)

    def test_existing_registry_mode_link_and_partial_stage_guards(self):
        uid,gid = os.geteuid(), os.getegid()
        empty = operator.canonical({"schema": operator.SCHEMA, "revision": 1, "links": []})
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "category-topic-links.json"
            target.write_bytes(empty)
            target.chmod(0o600)
            self.assertEqual(operator.check_existing(target, uid, gid), empty)
            target.chmod(0o644)
            with self.assertRaises(operator.Stop):
                operator.check_existing(target, uid, gid)
            target.chmod(0o600)
            other = Path(d) / "hardlink.json"
            os.link(target, other)
            with self.assertRaises(operator.Stop):
                operator.check_existing(target, uid, gid)
            other.unlink()
            stage = Path(d) / ".category-topic-links.admin.leftover.tmp"
            stage.write_text("interrupted")
            with self.assertRaises(operator.Stop):
                operator.check_existing(target, uid, gid)
            stage.unlink()
            target.write_text("{}")
            with self.assertRaises(operator.Stop):
                operator.check_existing(target, uid, gid)
            target.unlink()
            target.symlink_to(Path(d) / "untrusted")
            with self.assertRaises(operator.Stop):
                operator.check_existing(target, uid, gid)

    def test_one_atomic_replace_and_readback(self):
        uid,gid = os.geteuid(), os.getegid()
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "category-topic-links.json"
            target.write_bytes(operator.canonical({"schema": operator.SCHEMA, "revision": 1, "links": []}))
            target.chmod(0o600)
            payload = operator.planned_bytes()
            original = operator.os.replace
            calls = []
            def counted(src, dst):
                calls.append((src, dst))
                return original(src, dst)
            with patch.object(operator.os, "replace", side_effect=counted):
                operator.replace_once(target, payload, uid, gid)
            self.assertEqual(len(calls), 1, "single atomic replacement, never 21 separate API POSTs")
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(target.stat().st_nlink, 1)

    def test_interrupted_replace_does_not_retry_rollback_or_cleanup(self):
        uid,gid = os.geteuid(), os.getegid()
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "category-topic-links.json"
            initial = operator.canonical({"schema": operator.SCHEMA, "revision": 1, "links": []})
            target.write_bytes(initial)
            target.chmod(0o600)
            with patch.object(operator.os, "replace", side_effect=OSError("synthetic interrupted replace")) as replace:
                with self.assertRaises(OSError):
                    operator.replace_once(target, operator.planned_bytes(), uid, gid)
            self.assertEqual(replace.call_count, 1)
            self.assertEqual(target.read_bytes(), initial, "never cleanup or rewrite target after a fault")
            self.assertEqual(len(list(Path(d).glob(".category-topic-links.admin.*.tmp"))), 1,
                             "interrupted stage is retained as evidence; next apply must STOP")

    def test_protected_live_registry_hash_gate(self):
        exact = {
            "enabled": True, "revision": 1, "links": [],
            "registry_sha256": operator.BASELINE_SHA,
            "category_sha256": operator.CATEGORY_SHA, "topic_sha256": operator.TOPIC_SHA,
        }
        state = {
            "/api/jobs/active": {"active": False, "job": None},
            "/api/categories": public_taxonomy(),
            "/api/category-topics/manage": exact,
        }
        with patch.object(operator, "get_json", side_effect=lambda p: state[p]):
            operator.verify_runtime()
            state["/api/category-topics/manage"] = dict(exact, registry_sha256="0" * 64)
            with self.assertRaises(operator.Stop):
                operator.verify_runtime()
            state["/api/category-topics/manage"] = exact
            state["/api/jobs/active"] = {"active": True, "job": {"status": "queued"}}
            with self.assertRaises(operator.Stop):
                operator.verify_runtime()


if __name__ == "__main__":
    unittest.main()
