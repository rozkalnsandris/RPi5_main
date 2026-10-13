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

    def test_override_requires_exact_deployer_owner_parent_and_permissions(self):
        """Simulated deployer-owned directory: other UID/mode fails before bytes."""
        override_dir = self.base / "override-owned-by-service"
        override_dir.mkdir(mode=0o700)
        override_dir.chmod(0o700)
        override = override_dir / "cv.yaml"
        override.write_text('{"services":{"cv":{"image":"synthetic"}}}', encoding="utf-8")
        override.chmod(0o600)
        service_uid = os.getuid()
        with patch.object(op, "ROOT_UID", service_uid + 1):
            _, payload = op.fixed_file(
                override, None, 0o600, owner_uid=service_uid,
                parent_uid=service_uid, parent_mode=0o700,
            )
            self.assertIn(b"synthetic", payload)
            # Root-only policy still rejects the exact same service-owned file.
            with self.assertRaises(op.Block):
                op.fixed_file(override, None, 0o600)
            with self.assertRaises(op.Block):
                op.fixed_file(override, None, 0o600, owner_uid=service_uid + 1,
                              parent_uid=service_uid, parent_mode=0o700)
            with self.assertRaises(op.Block):
                op.fixed_file(override, None, 0o600, owner_uid=service_uid,
                              parent_uid=service_uid + 1, parent_mode=0o700)
            override_dir.chmod(0o750)
            with self.assertRaises(op.Block):
                op.fixed_file(override, None, 0o600, owner_uid=service_uid,
                              parent_uid=service_uid, parent_mode=0o700)
            override_dir.chmod(0o700)
            override.chmod(0o640)
            with self.assertRaises(op.Block):
                op.fixed_file(override, None, 0o600, owner_uid=service_uid,
                              parent_uid=service_uid, parent_mode=0o700)
            override.chmod(0o600)
            override_symlink = override_dir / "cv-link.yaml"
            override_symlink.symlink_to(override)
            with self.assertRaises(OSError):
                op.fixed_file(override_symlink, None, 0o600, owner_uid=service_uid,
                              parent_uid=service_uid, parent_mode=0o700)

    def test_service_account_lookup_is_exact_and_fail_closed(self):
        with patch.object(op.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=4321)) as lookup:
            self.assertEqual(op.deployer_uid(), 4321)
            lookup.assert_called_once_with("rozkalns-simple-deployer")
        for value in (0, -1, "4321", None):
            with self.subTest(invalid_uid=value), patch.object(
                op.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=value)
            ):
                with self.assertRaises(op.Block):
                    op.deployer_uid()
        with patch.object(op.pwd, "getpwnam", side_effect=KeyError):
            with self.assertRaises(op.Block):
                op.deployer_uid()

    def test_check_narrows_service_owner_exception_to_override(self):
        captured = []
        def fake_file(path, expected, mode, *args, **kwargs):
            captured.append((path, mode, kwargs))
            if path == op.OVERRIDE:
                return (("fixture",), json.dumps(
                    {"services": {"cv": {"image": op.IMAGE_REF}}}
                ).encode("utf-8"))
            return (("fixture",), b"fixture")
        with patch.object(op, "fixed_file", side_effect=fake_file), \
             patch.object(op, "deployer_uid", return_value=4321), \
             patch.object(op, "quiescent"), \
             patch.object(op, "target_only_registry", return_value=b"new-registry"), \
             patch.object(op, "producer"), \
             patch.object(op, "runtime"):
            self.assertEqual(op.check()[2], b"new-registry")
        self.assertEqual(len(captured), 4)
        for path, mode, kwargs in captured:
            if path == op.OVERRIDE:
                self.assertEqual(mode, 0o600)
                self.assertEqual(kwargs, {"limit": 8192, "owner_uid": 4321,
                                          "parent_uid": 4321, "parent_mode": 0o700})
            else:
                self.assertEqual(kwargs, {})
                self.assertEqual(mode, 0o444)

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
