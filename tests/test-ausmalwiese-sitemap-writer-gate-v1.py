"""Offline-only adversarial tests. No RPi5 services, cron or content paths touched."""
from __future__ import annotations

import fcntl
import importlib.machinery
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "ops/bin/ausmalwiese-sitemap-writer-gate"
mod = importlib.machinery.SourceFileLoader("sitemap_gate_v1", str(MODULE)).load_module()


class GateTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.attestation = self.root / "attestation"
        self.marker = self.root / "marker"
        self.stage = self.root / "stage"
        self.lock = self.root / "lock"
        self.attestation.write_bytes(mod.ATTESTATION_BYTES)
        self.marker.write_bytes(mod.POST_PUBLISH_BYTES)
        self.attestation.chmod(0o444)
        self.marker.chmod(0o444)
        self.lock.touch()
        self.lock.chmod(0o600)

    @staticmethod
    def idle(_unit):
        return {"ActiveState": "inactive", "SubState": "dead", "LoadState": "loaded"}

    def run_gate(self, unit_reader=None, **overrides):
        kwargs = dict(attestation=self.attestation, marker=self.marker,
                      stage=self.stage, lock=self.lock,
                      root_uid=os.getuid(), root_gid=os.getgid(),
                      owner_uid=os.getuid(), owner_gid=os.getgid(),
                      unit_reader=self.idle if unit_reader is None else unit_reader)
        kwargs.update(overrides)
        return mod.check(**kwargs)

    def test_pass_is_bounded_and_never_claims_external_exclusion(self):
        result = self.run_gate()
        self.assertEqual(result["result"], "BOUNDED_GATE_PASS")
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["external_writers_proven_quiesced"])
        self.assertTrue(result["required_independent_external_writer_proof"])
        self.assertFalse(self.stage.exists())

    def test_exact_fixed_units_are_preserved(self):
        deployer = "rozkalns-simple-deployer" + chr(64) + "coloring-pages-public-rpi5"
        self.assertEqual(
            mod.UNITS,
            ("cron.service", deployer + ".timer", deployer + ".service"),
        )

    def test_each_active_unit_blocks(self):
        for selected in mod.UNITS:
            def active(unit):
                data = self.idle(unit)
                if unit == selected:
                    data["ActiveState"] = "active"
                return data
            with self.subTest(unit=selected), self.assertRaisesRegex(mod.Hold, "WRITER_TRIGGER"):
                self.run_gate(unit_reader=active)

    def test_missing_or_failed_units_block(self):
        with self.assertRaisesRegex(mod.Hold, "WRITER_TRIGGER"):
            self.run_gate(unit_reader=lambda unit: dict(LoadState="not-found", ActiveState="inactive", SubState="dead"))
        with self.assertRaisesRegex(mod.Hold, "WRITER_TRIGGER"):
            self.run_gate(unit_reader=lambda unit: dict(LoadState="loaded", ActiveState="failed", SubState="failed"))
        with self.assertRaisesRegex(mod.Hold, "UNEXPECTED_UNIT"):
            mod.read_unit("ssh.service")

    def test_staging_leftover_blocks(self):
        self.stage.write_bytes(b"unfinished")
        with self.assertRaisesRegex(mod.Hold, "STAGE_PRESENT"):
            self.run_gate()
        self.assertEqual(self.stage.read_bytes(), b"unfinished")

    def test_attestation_missing_tampered_mode_or_symlink_blocks(self):
        self.attestation.unlink()
        with self.assertRaisesRegex(mod.Hold, "TRUST_MARKER"):
            self.run_gate()
        self.attestation.write_bytes(b"wrong")
        self.attestation.chmod(0o444)
        with self.assertRaisesRegex(mod.Hold, "TRUST_MARKER"):
            self.run_gate()
        self.attestation.chmod(0o644)
        self.attestation.write_bytes(mod.ATTESTATION_BYTES)
        with self.assertRaisesRegex(mod.Hold, "TRUST_MARKER"):
            self.run_gate()
        self.attestation.unlink()
        self.attestation.symlink_to(self.marker)
        with self.assertRaisesRegex(mod.Hold, "TRUST_MARKER"):
            self.run_gate()

    def test_enabled_marker_identity_is_mandatory(self):
        self.marker.unlink()
        with self.assertRaisesRegex(mod.Hold, "TRUST_MARKER"):
            self.run_gate()

    def test_lock_busy_rejected_without_unlocking_other_holder(self):
        # POSIX flock on a separately opened fd conflicts even in this process.
        with self.lock.open("r+b") as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(mod.Hold, "LOCK_BUSY"):
                self.run_gate()
        self.assertEqual(self.run_gate()["result"], "BOUNDED_GATE_PASS")

    def test_lock_symlink_wrong_mode_missing_blocks(self):
        self.lock.chmod(0o644)
        with self.assertRaisesRegex(mod.Hold, "LOCK_IDENTITY"):
            self.run_gate()
        self.lock.unlink()
        self.lock.symlink_to(self.marker)
        with self.assertRaisesRegex(mod.Hold, "LOCK_IDENTITY"):
            self.run_gate()
        self.lock.unlink()
        with self.assertRaisesRegex(mod.Hold, "LOCK_UNAVAILABLE"):
            self.run_gate()

    def test_lock_other_identity_blocks(self):
        with self.assertRaisesRegex(mod.Hold, "LOCK_IDENTITY"):
            self.run_gate(owner_uid=os.getuid() + 8000)

    def test_no_deploy_or_publish_calls_present(self):
        source = MODULE.read_text()
        self.assertNotIn("--apply", source)
        self.assertNotIn("os.replace(", source)
        self.assertNotIn("systemctl\", \"stop", source)
        self.assertNotIn("systemctl\", \"start", source)


if __name__ == "__main__":
    unittest.main()
