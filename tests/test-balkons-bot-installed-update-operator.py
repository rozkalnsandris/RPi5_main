#!/usr/bin/env python3
"""Offline, fake-root tests for the one-shot installed balcony bot update."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "ops/bin/balkons-bot-installed-update-operator"
loader = importlib.machinery.SourceFileLoader("balkons_installed_update_1484", str(ARTIFACT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
op = importlib.util.module_from_spec(spec)
loader.exec_module(op)


class Response:
    status = 200

    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.raw[:n]


class Opener:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return Response(self.payload)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.public_dir = self.root / "local/lib"
        self.overlay_dir = self.root / "systemd"
        self.recovery_dir = self.root / "var/lib/recovery"
        for path in (self.public_dir, self.overlay_dir, self.recovery_dir.parent):
            path.mkdir(parents=True)
        self.source = self.public_dir / "bot.py"
        self.overlay = self.overlay_dir / "source-overlay.conf"
        self.k10 = self.overlay_dir / "k10.conf"
        self.stage = self.public_dir / ".bot-stage"
        self.public_old = b"public before update\n"
        self.public_new = b"public after update\n"
        self.public_overlay = b"public overlay fixture\n"
        self.public_k10 = b"public K10 fixture\n"
        for path, data in (
            (self.source, self.public_old),
            (self.overlay, self.public_overlay),
            (self.k10, self.public_k10),
        ):
            path.write_bytes(data)
            path.chmod(0o644)
        self.files = {
            op.OPERATOR_REL: b"reviewed operator",
            op.SOURCE_REL: self.public_new,
            op.OVERLAY_REL: self.public_overlay,
            op.PREFLIGHT_REL: b"reviewed preflight",
            op.VERIFIER_REL: b"reviewed verifier",
        }
        self.old_sha = op.digest(self.public_old)
        self.new_sha = op.digest(self.public_new)
        self.overlay_sha = op.digest(self.public_overlay)
        self.k10_sha = op.digest(self.public_k10)
        self.args = SimpleNamespace(
            expected_main="a" * 40,
            expected_old_source_sha256=self.old_sha,
            expected_new_source_sha256=self.new_sha,
            expected_overlay_sha256=self.overlay_sha,
            expected_k10_sha256=self.k10_sha,
            expected_fragment_path_sha256="b" * 64,
            expected_service_user_sha256="c" * 64,
            owner_comment_id=12345,
        )

    def fake_read(self, path, *, owner, mode, max_bytes=op.MAX_PUBLIC_BYTES):
        st = path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or stat.S_IMODE(st.st_mode) != mode or not 0 < st.st_size <= max_bytes):
            raise op.Blocked("public_file_metadata_invalid")
        return path.read_bytes()

    def checks(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(op, "PREVIOUS_PUBLIC_SHA", self.old_sha))
        stack.enter_context(patch.object(op, "REVIEWED_OVERLAY_SHA", self.overlay_sha))
        stack.enter_context(patch.object(op, "REVIEWED_K10_SHA", self.k10_sha))
        stack.enter_context(patch.object(op, "SOURCE_TARGET", self.source))
        stack.enter_context(patch.object(op, "OVERLAY_TARGET", self.overlay))
        stack.enter_context(patch.object(op, "K10_TARGET", self.k10))
        stack.enter_context(patch.object(op, "RECOVERY", self.recovery_dir))
        stack.enter_context(patch.object(op, "STAGE", self.stage))
        stack.enter_context(patch.object(op, "check_repo", return_value=dict(self.files)))
        stack.enter_context(patch.object(op, "read_public", side_effect=self.fake_read))
        stack.enter_context(patch.object(op, "directory", return_value=None))
        stack.enter_context(patch.object(op, "preflight", return_value=None))
        stack.enter_context(patch.object(op.os, "geteuid", return_value=0))
        return stack

    def test_check_ready_is_read_only(self):
        self.checks()
        output = op.check(self.args)
        self.assertEqual(output["old_public_bytes"], self.public_old)
        self.assertFalse(self.stage.exists())
        self.assertFalse(self.recovery_dir.exists())
        self.assertEqual(self.source.read_bytes(), self.public_old)

    def test_old_source_drift_blocks(self):
        self.checks()
        self.source.write_bytes(b"unreviewed already installed source")
        with self.assertRaisesRegex(op.Blocked, "installed_public_source_drift"):
            op.check(self.args)

    def test_overlay_drift_blocks(self):
        self.checks()
        self.overlay.write_bytes(b"unexpected overlay")
        with self.assertRaisesRegex(op.Blocked, "installed_overlay_drift"):
            op.check(self.args)

    def test_candidate_new_source_drift_blocks(self):
        self.checks()
        self.args.expected_new_source_sha256 = "f" * 64
        with self.assertRaisesRegex(op.Blocked, "candidate_source_identity_mismatch"):
            op.check(self.args)

    def test_k10_drift_blocks(self):
        self.checks()
        self.k10.write_bytes(b"unexpected K10")
        with self.assertRaisesRegex(op.Blocked, "k10_drift"):
            op.check(self.args)

    def test_missing_or_existing_stage_and_recovery_block(self):
        self.checks()
        self.stage.write_text("stale", encoding="utf-8")
        with self.assertRaisesRegex(op.Blocked, "staging_target_exists"):
            op.check(self.args)
        self.stage.unlink()
        self.recovery_dir.mkdir()
        with self.assertRaisesRegex(op.Blocked, "recovery_state_exists"):
            op.check(self.args)

    def test_public_source_symlink_and_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.write_bytes(b"public fixture")
            target.symlink_to(source)
            with self.assertRaisesRegex(op.Blocked, "public_file_metadata_invalid"):
                op.read_public(target, owner=os.getuid(), mode=0o644)
            target.unlink()
            os.link(source, target)
            with self.assertRaisesRegex(op.Blocked, "public_file_metadata_invalid"):
                op.read_public(target, owner=os.getuid(), mode=0o644)
            self.assertEqual(source.read_bytes(), b"public fixture")

    def test_owner_comment_exact_new_issue_and_current_sha(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        approval = {
            "schema": "rozkalns.balkons-bot-installed-update-live-approval.v1",
            "issue": 1484, "target": "balkons-bot.service",
            "repo_sha": self.args.expected_main,
            "old_source_sha256": self.args.expected_old_source_sha256,
            "new_source_sha256": self.args.expected_new_source_sha256,
            "overlay_sha256": self.args.expected_overlay_sha256,
            "k10_sha256": self.args.expected_k10_sha256,
            "fragment_path_sha256": self.args.expected_fragment_path_sha256,
            "service_user_sha256": self.args.expected_service_user_sha256,
            "allow": ["backup_public_source", "atomic_replace_public_source",
                      "restart_once", "postverify"],
            "no_automatic_rollback": True,
        }
        envelope = {
            "user": {"id": op.AUTH_OWNER_ID, "type": "User"},
            "issue_url": "https://api.github.com/repos/rozkalnsandris/RPi5_main/issues/1484",
            "created_at": now, "body": json.dumps(approval),
        }
        connection = Opener(envelope)
        with patch.object(op.urllib.request, "build_opener", return_value=connection):
            op.verify_owner_comment(self.args.owner_comment_id, self.args)
        self.assertEqual(connection.calls, [(op.AUTH_URL + "12345", 8)])
        for mutation in (
            {**envelope, "user": {"id": 999, "type": "User"}},
            {**envelope, "issue_url": "https://api.github.com/repos/rozkalnsandris/RPi5_main/issues/925"},
            {**envelope, "body": json.dumps({**approval, "repo_sha": "f" * 40})},
            {**envelope, "body": json.dumps({**approval, "allow": ["restart_once"]})},
            {**envelope, "body": json.dumps({**approval, "unknown_field": "synthetic"})},
            {**envelope, "created_at": (dt.datetime.now(dt.timezone.utc) -
                 dt.timedelta(minutes=16)).isoformat().replace("+00:00", "Z")},
        ):
            with self.subTest(case=str(mutation)[:70]):
                with patch.object(op.urllib.request, "build_opener",
                                  return_value=Opener(mutation)):
                    with self.assertRaises(op.Blocked):
                        op.verify_owner_comment(self.args.owner_comment_id, self.args)

    def test_preflight_accepts_only_complete_sanitized_contract(self):
        meta = {
            "load_state": "loaded", "active_state": "active", "sub_state": "running",
            "user_sha256": self.args.expected_service_user_sha256,
            "user_is_root": False,
            "python_executable_path_sha256": op.CANONICAL_PYTHON_PATH_SHA,
            "live_source_path_sha256": op.digest_path(str(op.SOURCE_TARGET)),
            "fragment_path_sha256": self.args.expected_fragment_path_sha256,
            "restart": "always", "restart_usec": "10s",
            "timeout_stop_usec": "1min 30s", "send_sigkill": "no",
        }
        creds = {
            "contract": "systemd_load_credential_encrypted_host_bound_v1",
            "ids": ["telegram-token", "telegram-chat-id", "mqtt-host",
                    "mqtt-username", "mqtt-secret"],
            "expected_count": 5, "metadata_valid_count": 5,
            "directory_metadata_valid": True, "all_metadata_valid": True,
            "content_read": False, "content_hashed": False,
        }
        report = {
            "schema": "rpi5.balkons_bot_preflight.v1",
            "preflight": "PASS", "blockers": [], "scope": "READ_ONLY",
            "observed_repo_sha": self.args.expected_main,
            "expected_repo_sha": self.args.expected_main,
            "live_source_sha256": self.old_sha,
            "live_source_provenance_match": True,
            "critical_worktree_clean": True, "critical_paths_tracked": True,
            "tracked_source_sha256": op.digest(self.files[op.SOURCE_REL]),
            "tracked_dropin_sha256": op.digest(self.files[op.OVERLAY_REL]),
            "preflight_artifact_sha256": op.digest(self.files[op.PREFLIGHT_REL]),
            "mutation_started": False, "writes_performed": False,
            "service_metadata": meta, "encrypted_credentials": creds,
        }
        with patch.object(op, "run", return_value=json.dumps(report)):
            op.preflight(self.args.expected_main, self.old_sha, self.files,
                         self.args.expected_fragment_path_sha256,
                         self.args.expected_service_user_sha256)
        for invalid in (
            {**report, "preflight": "BLOCKED"},
            {**report, "encrypted_credentials": {**creds, "metadata_valid_count": 4}},
            {**report, "encrypted_credentials": {**creds, "content_read": True}},
            {**report, "service_metadata": {**meta, "send_sigkill": "yes"}},
            {**report, "service_metadata": {**meta, "live_source_path_sha256": "a" * 64}},
        ):
            with patch.object(op, "run", return_value=json.dumps(invalid)):
                with self.assertRaises(op.Blocked):
                    op.preflight(self.args.expected_main, self.old_sha, self.files,
                                 self.args.expected_fragment_path_sha256,
                                 self.args.expected_service_user_sha256)

    def test_apply_backs_up_public_only_and_restarts_once(self):
        self.checks()
        calls = []
        def write(path, data, *, mode):
            calls.append(("write", path.name, mode))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        def run(argv, *, timeout=25):
            calls.append(("run", argv))
            return ""
        with patch.object(op, "service_generation", return_value=(4321, 987654)), \
             patch.object(op, "verify_owner_comment", return_value=None), \
             patch.object(op, "write_exclusive", side_effect=write), \
             patch.object(op, "run", side_effect=run), \
             patch.object(op, "postverify", side_effect=lambda *_: calls.append(("verify",))):
            self.assertEqual(op.apply(self.args), "PASS")
        self.assertEqual(self.source.read_bytes(), self.public_new)
        self.assertEqual((self.recovery_dir / "previous-public-bot.py").read_bytes(),
                         self.public_old)
        self.assertEqual(stat.S_IMODE((self.recovery_dir / "previous-public-bot.py").stat().st_mode),
                         0o600)
        self.assertEqual([x[0] for x in calls],
                         ["write", "write", "write", "run", "verify"])
        self.assertEqual(calls[-2][1][:2], ("/usr/bin/systemctl", "restart"))
        self.assertFalse(self.stage.exists())

    def test_authorization_rejection_makes_no_writes(self):
        self.checks()
        with patch.object(op, "service_generation", return_value=(4321, 987654)), \
             patch.object(op, "verify_owner_comment", side_effect=op.Blocked("denied")):
            with self.assertRaisesRegex(op.Blocked, "denied"):
                op.apply(self.args)
        self.assertFalse(self.recovery_dir.exists())
        self.assertEqual(self.source.read_bytes(), self.public_old)

    def test_service_generation_drift_blocks_before_first_write(self):
        self.checks()
        with patch.object(op, "service_generation", side_effect=[
                (4321, 987654), (4322, 987654)]), \
             patch.object(op, "verify_owner_comment", return_value=None):
            with self.assertRaisesRegex(op.Blocked, "service_generation_drift"):
                op.apply(self.args)
        self.assertFalse(self.recovery_dir.exists())
        self.assertEqual(self.source.read_bytes(), self.public_old)

    def test_failure_after_restart_has_no_cleanup_or_retry(self):
        self.checks()
        calls = []
        def write(path, data, *, mode):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        def run(argv, *, timeout=25):
            calls.append(argv)
            raise op.Blocked("restart_failed")
        with patch.object(op, "service_generation", return_value=(4321, 987654)), \
             patch.object(op, "verify_owner_comment", return_value=None), \
             patch.object(op, "write_exclusive", side_effect=write), \
             patch.object(op, "run", side_effect=run):
            with self.assertRaisesRegex(op.Blocked, "restart_failed"):
                op.apply(self.args)
        self.assertTrue(self.recovery_dir.exists())
        self.assertEqual((self.recovery_dir / "previous-public-bot.py").read_bytes(),
                         self.public_old)
        self.assertEqual(self.source.read_bytes(), self.public_new)
        self.assertEqual(len(calls), 1)

    def test_stage_exclusive_no_overwrite(self):
        existing = self.root / "existing"
        existing.write_bytes(b"already exists")
        with self.assertRaisesRegex(op.Blocked, "exclusive_write_failed_no_cleanup"):
            op.write_exclusive(existing, b"new file", mode=0o644)
        self.assertEqual(existing.read_bytes(), b"already exists")

    def test_service_generation_metadata_shape(self):
        with patch.object(op, "run",
                          return_value="MainPID=1001\nActiveEnterTimestampMonotonic=21122\n"):
            self.assertEqual(op.service_generation(), (1001, 21122))
        for invalid in ("MainPID=0\nActiveEnterTimestampMonotonic=21122\n",
                        "MainPID=1001\nActiveEnterTimestampMonotonic=abc\n",
                        "MainPID=1001\n", "MainPID=1001\nMainPID=1002\n"):
            with patch.object(op, "run", return_value=invalid):
                with self.assertRaises(op.Blocked):
                    op.service_generation()

    def test_source_never_opens_private_files_or_issues_device_commands(self):
        content = ARTIFACT.read_text(encoding="utf-8")
        self.assertIn("O_EXCL", content)
        self.assertIn("os.replace(STAGE, SOURCE_TARGET)", content)
        self.assertNotIn("shell=True", content)
        self.assertNotIn("shutil.copy", content)
        self.assertNotIn("rollback(", content)
        self.assertNotIn("unlink(", content)
        self.assertNotIn("mqtt.publish(", content)
        self.assertNotIn("systemctl\", \"daemon-reload", content)
        self.assertNotIn("balkons/cmd", content)
        self.assertNotIn("/etc/credstore.encrypted/", content)
        self.assertNotIn("os.environ[", content)
        self.assertIn("NoRedirect", content)


if __name__ == "__main__":
    unittest.main()
