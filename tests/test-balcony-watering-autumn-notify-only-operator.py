#!/usr/bin/env python3
"""Offline one-file Hermes notification-only operator tests (#1498)."""
from __future__ import annotations
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balcony-watering-autumn-notify-only-operator"
loader = importlib.machinery.SourceFileLoader("notify_1498_operator", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class SingleFileTransactionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="notify1498-offline-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.target = self.root / m.TARGET_NAME
        self.old = b"synthetic-old-not-a-controller\n"
        self.new = b"synthetic-new-not-a-controller\n"
        self.target.write_bytes(self.old)
        self.target.chmod(0o700)
        self.uid, self.gid = os.geteuid(), os.getegid()
        self.state = {"mutation_started": False}
        patch_old = mock.patch.object(m, "OLD_SHA", sha(self.old))
        patch_new = mock.patch.object(m, "NEW_SHA", sha(self.new))
        patch_old.start()
        patch_new.start()
        self.addCleanup(patch_new.stop)
        self.addCleanup(patch_old.stop)

    def run_transaction(self):
        m.one_file_replace(self.target, self.new, owner=self.uid, group=self.gid,
                           state=self.state)

    def test_single_file_replace_and_recovery_readback(self):
        self.run_transaction()
        self.assertTrue(self.state["mutation_started"])
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.assertEqual(self.target.stat().st_uid, self.uid)
        backup = self.root / m.BACKUP_NAME
        self.assertEqual(backup.read_bytes(), self.old)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertFalse((self.root / m.STAGE_NAME).exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         sorted([m.TARGET_NAME, m.BACKUP_NAME]))

    def test_no_write_on_original_sha_mismatch(self):
        self.target.write_bytes(b"tampered-old\n")
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "deployed_target_sha_drift")
        self.assertFalse(self.state["mutation_started"])
        self.assertFalse((self.root / m.BACKUP_NAME).exists())

    def test_no_write_on_candidate_sha_mismatch(self):
        self.new += b"tampered\n"
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "candidate_sha_mismatch")
        self.assertFalse(self.state["mutation_started"])

    def test_existing_backup_fails_without_overwrite(self):
        backup = self.root / m.BACKUP_NAME
        backup.write_bytes(b"do-not-touch")
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "recovery_already_exists")
        self.assertFalse(self.state["mutation_started"])
        self.assertEqual(backup.read_bytes(), b"do-not-touch")
        self.assertEqual(self.target.read_bytes(), self.old)

    def test_existing_stage_fails_without_write(self):
        stage = self.root / m.STAGE_NAME
        stage.write_bytes(b"do-not-touch")
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "stage_already_exists")
        self.assertFalse(self.state["mutation_started"])
        self.assertEqual(stage.read_bytes(), b"do-not-touch")

    def test_reject_target_symlink_and_hardlink(self):
        other = self.root / "other"
        self.target.rename(other)
        self.target.symlink_to(other)
        with self.assertRaises(m.Blocked):
            self.run_transaction()
        self.assertFalse(self.state["mutation_started"])
        self.target.unlink()
        os.link(other, self.target)
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "file_metadata_invalid")
        self.assertFalse(self.state["mutation_started"])

    def test_reject_wrong_target_mode(self):
        self.target.chmod(0o755)
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "file_metadata_invalid")
        self.assertFalse(self.state["mutation_started"])

    def test_reject_unsafe_parent_before_mutation(self):
        self.root.chmod(0o777)
        with self.assertRaises(m.Blocked) as error:
            self.run_transaction()
        self.assertEqual(str(error.exception), "directory_unsafe")
        self.assertFalse(self.state["mutation_started"])
        self.root.chmod(0o700)

    def test_interrupted_replace_preserves_backup_and_stage_without_retry(self):
        with mock.patch.object(m.os, "replace", side_effect=OSError("simulated")) as swap:
            with self.assertRaises(OSError):
                self.run_transaction()
            self.assertEqual(swap.call_count, 1)
        self.assertTrue(self.state["mutation_started"])
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual((self.root / m.BACKUP_NAME).read_bytes(), self.old)
        self.assertEqual((self.root / m.STAGE_NAME).read_bytes(), self.new)

    def test_second_run_does_not_mutate(self):
        self.run_transaction()
        original = self.target.read_bytes()
        state = {"mutation_started": False}
        with self.assertRaises(m.Blocked):
            m.one_file_replace(self.target, self.new, owner=self.uid,
                               group=self.gid, state=state)
        self.assertFalse(state["mutation_started"])
        self.assertEqual(self.target.read_bytes(), original)

    def test_imported_preflight_blocked_reason_is_sanitized(self):
        # Synthetic isolated module: never opens a real Hermes store.
        home = self.root / "synthetic-home"
        preflight = (home / "RPi5_main" / m.PRE_REL)
        preflight.parent.mkdir(parents=True)
        for message, expected in (
            ("autumn_job_identity_drift", "preflight_job_identity_drift"),
            ("PRIVATE_SYNTHETIC_NOT_TO_EMIT", "preflight_not_ready"),
        ):
            with self.subTest(message=message):
                preflight.write_text(
                    "class Blocked(Exception): pass\n"
                    "def inspect(**kwargs):\n"
                    "    raise Blocked(" + repr(message) + ")\n",
                    encoding="utf-8",
                )
                with self.assertRaises(m.Blocked) as error:
                    m.preflight_gate(home, owner=self.uid)
                self.assertEqual(str(error.exception), expected)
                self.assertNotIn("PRIVATE_SYNTHETIC_NOT_TO_EMIT",
                                 str(error.exception))
        self.assertFalse((self.root / m.BACKUP_NAME).exists())
        self.assertFalse((self.root / m.STAGE_NAME).exists())

    def test_operator_script_only_branch_requires_complete_guard_report(self):
        # Only a synthetic module; no real cron/job, host or pump access.
        home = self.root / "synthetic-home"
        preflight = home / "RPi5_main" / m.PRE_REL
        preflight.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "result": "SOURCE_NOTIFY_ONLY_PREFLIGHT_PASS",
            "identity_mode": "strict_script_only",
            "script_only_contract_verified": True,
            "job_definition_sha256": "f" * 64,
            "wrapper_sha256": m.WRAPPER_SHA,
            "deployed_controller_sha256": m.OLD_SHA,
            "candidate_controller_sha256": m.NEW_SHA,
            "existing_autumn_job": "enabled_local_unique",
            "legacy_jobs": "three_disabled",
            "mutation_started": False,
            "writes_performed": False,
        }
        for key, value in (
            ("valid", True),
            ("script_only_contract_verified", False),
            ("identity_mode", "unsafe"),
            ("wrapper_sha256", "0" * 64),
            ("existing_autumn_job", "duplicate"),
            ("mutation_started", True),
        ):
            data = dict(report)
            if key != "valid":
                data[key] = value
            preflight.write_text(
                "class Blocked(Exception): pass\n"
                "def inspect(**kwargs):\n"
                "    return " + repr(data) + "\n",
                encoding="utf-8",
            )
            if key == "valid":
                self.assertEqual(m.preflight_gate(home, owner=self.uid), data)
            else:
                with self.assertRaises(m.Blocked) as raised:
                    m.preflight_gate(home, owner=self.uid)
                self.assertEqual(str(raised.exception), "preflight_not_ready")

    def test_static_safety_scope(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.O_CREAT | os.O_EXCL", source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.replace(stage, target)", source)
        self.assertIn("SOURCE_NOTIFY_ONLY_PREFLIGHT_PASS", source)
        self.assertIn("precheck_window()", source)
        self.assertIn("acquire_existing_lock", source)
        for forbidden in ("api.telegram.org", "mosquitto_pub",
                          "switch.turn_on", "switch.turn_off",
                          "hermes cron edit", "systemctl restart"):
            self.assertNotIn(forbidden, source)

if __name__ == "__main__":
    unittest.main()
