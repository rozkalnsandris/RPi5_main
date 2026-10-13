#!/usr/bin/env python3
"""Synthetic no-host tests for #1000 CV-only stats alignment."""
from __future__ import annotations
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/bin/rozkalns-cv-live-stats-rollout-1000"
loader = importlib.machinery.SourceFileLoader("cv_stats_1000", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
op = importlib.util.module_from_spec(spec)
loader.exec_module(op)


class CvStatsRolloutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.compose_dir = self.base / "compose"
        self.registry_dir = self.base / "registry"
        self.compose_dir.mkdir()
        self.registry_dir.mkdir()
        self.compose = self.compose_dir / "rozkalns-cv.yml"
        self.registry = self.registry_dir / "targets.json"
        self.baseline = (ROOT / "ops/deploy/baselines/simple-deploy-targets-weather-rebind-v1.json").read_bytes()
        self.compose.write_bytes(b"old")
        self.registry.write_bytes(self.baseline)
        self.compose.chmod(0o444)
        self.registry.chmod(0o444)
        for context in (patch.object(op, "COMPOSE", self.compose),
                        patch.object(op, "REGISTRY", self.registry),
                        patch.object(op, "ROOT_UID", os.getuid())):
            context.start()
            self.addCleanup(context.stop)

    def test_only_cv_pin_changes_and_historical_sha_is_pinned(self):
        self.assertEqual(op.sha(self.baseline), op.OLD_REGISTRY)
        result = op.target_only_registry(self.baseline)
        self.assertEqual(len(result), len(self.baseline))
        old, new = json.loads(self.baseline), json.loads(result)
        for first, second in zip(old["targets"], new["targets"]):
            if first["target_alias"] == op.TARGET:
                self.assertEqual(second["compose"]["file_sha256"], op.NEW_COMPOSE)
                second["compose"]["file_sha256"] = op.OLD_COMPOSE
            self.assertEqual(first, second)

    def test_bad_registry_and_non_cv_drift_rejected(self):
        for changed in (self.baseline.replace(b"hermes-deals", b"hermes-extra"),
                        self.baseline.replace(op.OLD_COMPOSE.encode(), b"0" * 64)):
            with self.assertRaises(op.Block):
                op.target_only_registry(changed)

    def stats_home(self, name):
        home = self.base / name
        snapshot = home / op.STATS_RELATIVE
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text('{"synthetic":true}', encoding="utf-8")
        return SimpleNamespace(pw_dir=str(home), pw_uid=os.getuid()), snapshot

    def test_passwd_home_snapshot_is_unique_and_fresh(self):
        account, snapshot = self.stats_home("first")
        with patch.object(op.pwd, "getpwall", return_value=[account]):
            self.assertEqual(op.stats_path(), snapshot)
            op.producer()  # Metadata only: no contents are read by production.

    def test_missing_or_ambiguous_passwd_homes_are_rejected(self):
        a, _ = self.stats_home("first")
        b, _ = self.stats_home("second")
        with patch.object(op.pwd, "getpwall", return_value=[]):
            with self.assertRaises(op.Block):
                op.stats_path()
        with patch.object(op.pwd, "getpwall", return_value=[a, b]):
            with self.assertRaises(op.Block):
                op.stats_path()

    def test_unsafe_stats_ancestor_and_symlink_are_rejected(self):
        account, snapshot = self.stats_home("first")
        with patch.object(op.pwd, "getpwall", return_value=[account]):
            snapshot.parent.chmod(0o777)
            with self.assertRaises(op.Block):
                op.stats_path()
            snapshot.parent.chmod(0o755)
            moved = snapshot.parent.with_name("archived-html")
            snapshot.parent.rename(moved)
            snapshot.parent.symlink_to(moved, target_is_directory=True)
            with self.assertRaises(op.Block):
                op.stats_path()

    def test_stats_path_bad_owner_and_nonregular_file_are_rejected(self):
        account, snapshot = self.stats_home("first")
        with patch.object(op.pwd, "getpwall", return_value=[account]):
            changed = SimpleNamespace(pw_dir=account.pw_dir, pw_uid=os.getuid() + 1)
            with patch.object(op.pwd, "getpwall", return_value=[changed]):
                with self.assertRaises(op.Block):
                    op.stats_path()
            snapshot.unlink()
            snapshot.mkdir()
            with self.assertRaises(op.Block):
                op.stats_path()

    def test_source_file_mode_and_symlink_fail_closed(self):
        with patch.object(op, "OLD_COMPOSE", op.sha(b"old")):
            self.assertEqual(op.fixed_file(self.compose, op.OLD_COMPOSE, 0o444)[1], b"old")
            self.compose.chmod(0o666)
            with self.assertRaises(op.Block):
                op.fixed_file(self.compose, op.OLD_COMPOSE, 0o444)
            self.compose.chmod(0o444)
            link = self.compose_dir / "link"
            link.symlink_to(self.compose)
            with self.assertRaises(OSError):
                op.fixed_file(link, op.OLD_COMPOSE, 0o444)

    def test_two_file_atomic_replace_only(self):
        with patch.object(op, "OLD_COMPOSE", op.sha(b"old")), \
             patch.object(op, "OLD_REGISTRY", op.sha(self.baseline)):
            ids = (op.fixed_file(self.compose, op.OLD_COMPOSE, 0o444)[0],
                   op.fixed_file(self.registry, op.OLD_REGISTRY, 0o444)[0])
            op.replace_once(ids, b"new", b"new-registry")
        self.assertEqual(self.compose.read_bytes(), b"new")
        self.assertEqual(self.registry.read_bytes(), b"new-registry")
        self.assertEqual(len(list(self.compose_dir.iterdir())), 1)
        self.assertEqual(len(list(self.registry_dir.iterdir())), 1)

    def test_second_replace_failure_keeps_stage_and_partial_evidence(self):
        real_replace = os.replace
        counter = [0]
        def fail_second(a, b):
            counter[0] += 1
            if counter[0] == 2:
                raise OSError("synthetic")
            return real_replace(a, b)
        with patch.object(op, "OLD_COMPOSE", op.sha(b"old")), \
             patch.object(op, "OLD_REGISTRY", op.sha(self.baseline)), \
             patch.object(op.os, "replace", side_effect=fail_second):
            ids = (op.fixed_file(self.compose, op.OLD_COMPOSE, 0o444)[0],
                   op.fixed_file(self.registry, op.OLD_REGISTRY, 0o444)[0])
            with self.assertRaises(OSError):
                op.replace_once(ids, b"new", b"new-registry")
        self.assertEqual(self.compose.read_bytes(), b"new")
        self.assertEqual(self.registry.read_bytes(), self.baseline)
        self.assertTrue((self.registry_dir / op.STAGE).exists())

    def test_recreate_is_cv_only_without_pull_or_build(self):
        argv = []
        with patch.object(op, "command", side_effect=lambda args, **kw: argv.append(args)):
            op.recreate()
        self.assertEqual(len(argv), 1)
        self.assertEqual(argv[0][-1], "cv")
        self.assertIn("--no-deps", argv[0])
        self.assertIn("--force-recreate", argv[0])
        self.assertEqual(argv[0][argv[0].index("--pull") + 1], "never")
        self.assertIn("--no-build", argv[0])
        self.assertNotIn("down", argv[0])

    def test_apply_without_owner_receipt_is_not_mutation(self):
        with patch.object(op, "owner_approval", side_effect=op.Block("ROOT_REQUIRED")), \
             patch.object(op, "replace_once") as changed:
            self.assertEqual(op.main(["apply"]), 2)
            changed.assert_not_called()

    def test_check_does_not_recreate(self):
        with patch.object(op, "check", return_value=None), \
             patch.object(op, "recreate") as deploy:
            self.assertEqual(op.main(["check"]), 0)
            deploy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
