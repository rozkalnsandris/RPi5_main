#!/usr/bin/env python3
"""Offline adversarial tests of fixed-target balcony bot rollout operator (#925)."""
from __future__ import annotations

import datetime as dt
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
SOURCE = ROOT / "ops/bin/balkons-bot-latency-operator"
loader = importlib.machinery.SourceFileLoader("balkons_latency_operator_925", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
operator = importlib.util.module_from_spec(spec)
loader.exec_module(operator)

MAIN = "a" * 40
BASELINE = "b" * 64
FRAGMENT = "c" * 64
USER = "d" * 64
K10 = operator.digest(b"K10")


def options():
    return SimpleNamespace(
        expected_main=MAIN,
        expected_baseline_live_path_sha256=BASELINE,
        expected_fragment_path_sha256=FRAGMENT,
        expected_service_user_sha256=USER,
        expected_k10_sha256=K10,
        owner_comment_id=123456789,
    )


def auth(args, sha):
    return {
        "schema": "rozkalns.balkons-bot-latency-live-approval.v1",
        "issue": 925, "target": "balkons-bot.service", "repo_sha": args.expected_main,
        "source_sha256": sha,
        "baseline_live_path_sha256": args.expected_baseline_live_path_sha256,
        "fragment_path_sha256": args.expected_fragment_path_sha256,
        "service_user_sha256": args.expected_service_user_sha256,
        "k10_sha256": args.expected_k10_sha256,
        "allow": ["install_two_public_files", "daemon_reload_once", "restart_once"],
        "no_rollback": True,
    }


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.bytes = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size):
        return self.bytes[:size]


class FakeOpener:
    def __init__(self, obj):
        self.obj = obj
        self.urls = []

    def open(self, request, timeout):
        self.urls.append((request.full_url, timeout))
        return FakeResponse(self.obj)


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = options()
        self.files = {
            operator.SOURCE: b"public bot source",
            operator.OVERLAY: b"public overlay",
            operator.PREFLIGHT: b"public preflight",
            operator.VERIFIER: b"public verifier",
            "ops/bin/balkons-bot-latency-operator": b"reviewed operator",
        }
        self.source_target = self.root / "usr/local/lib/bot.py"
        self.dropin_target = self.root / "etc/systemd/bot.conf"
        self.source_target.parent.mkdir(parents=True)
        self.dropin_target.parent.mkdir(parents=True)
        self.recovery = self.root / "var/lib/recovery"
        self.recovery.parent.mkdir(parents=True)

    def baseline(self, *, report=None, existing=False, recovery=False, sha=None):
        if existing:
            self.source_target.write_bytes(b"old target")
        if recovery:
            self.recovery.mkdir()
        value = {
            "schema": "rpi5.balkons_bot_deploy_verifier.v1",
            "mode": "check", "result": "READY",
            "credential_content_read": False, "credential_content_hashed": False,
            "mutation_started": False, "writes_performed": False,
        } if report is None else report
        source = lambda *_args: dict(self.files)
        require = lambda path, **_kwargs: (
            b"K10" if path == operator.K10
            else self.files["ops/bin/balkons-bot-latency-operator"]
        )
        patches = [
            patch.object(operator, "TARGETS", (
                (operator.SOURCE, self.source_target), (operator.OVERLAY, self.dropin_target))),
            patch.object(operator, "RECOVERY", self.recovery),
            patch.object(operator, "OPERATOR", self.root / "installed-operator"),
            patch.object(operator, "check_source", side_effect=source),
            patch.object(operator, "require_file", side_effect=require),
            patch.object(operator, "require_directory", return_value=None),
            patch.object(operator.os, "geteuid", return_value=0),
        ]
        return patches, lambda _cmd: json.dumps(value)

    def test_check_success_is_read_only(self):
        patches, verifier = self.baseline()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            actual = operator.check_baseline(self.args, cmd=verifier)
        self.assertEqual(actual, self.files)
        self.assertFalse(self.recovery.exists())
        self.assertFalse(self.source_target.exists())
        self.assertFalse(self.dropin_target.exists())

    def test_existing_target_blocks_without_overwrite(self):
        patches, verifier = self.baseline(existing=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(operator.Blocked, "initial_install_target_exists"):
                operator.check_baseline(self.args, cmd=verifier)
        self.assertEqual(self.source_target.read_bytes(), b"old target")

    def test_recovery_state_blocks_replay(self):
        patches, verifier = self.baseline(recovery=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(operator.Blocked, "recovery_state_already_exists"):
                operator.check_baseline(self.args, cmd=verifier)

    def test_root_required(self):
        with patch.object(operator.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(operator.Blocked, "root_required"):
                operator.check_baseline(self.args)

    def test_invalid_bound_sha_blocks(self):
        patches, verifier = self.baseline()
        self.args.expected_k10_sha256 = "unexpected"
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(operator.Blocked, "k10_sha_invalid"):
                operator.check_baseline(self.args, cmd=verifier)

    def test_verifier_failure_blocks(self):
        cases = (
            {"result": "BLOCKED", "mode": "check", "schema": "rpi5.balkons_bot_deploy_verifier.v1"},
            {"result": "READY", "mode": "check", "schema": "rpi5.balkons_bot_deploy_verifier.v1",
             "credential_content_read": True},
            {"result": "READY", "mode": "verify", "schema": "rpi5.balkons_bot_deploy_verifier.v1"},
        )
        for result in cases:
            with self.subTest(result=result):
                patches, verifier = self.baseline(report=result)
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                    with self.assertRaisesRegex(operator.Blocked, "verifier_not_ready"):
                        operator.check_baseline(self.args, cmd=verifier)

    def fake_authorization(self, *, user_id=operator.OWNER_ID, issue=925, payload=None, age_minutes=0):
        date = (dt.datetime.now(dt.timezone.utc) -
                dt.timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
        return {
            "user": {"id": user_id, "type": "User"},
            "issue_url": "https://api.github.com/repos/rozkalnsandris/RPi5_main/issues/" + str(issue),
            "created_at": date,
            "body": json.dumps(auth(self.args, "f" * 64) if payload is None else payload),
        }

    def check_auth(self, envelope):
        opener = FakeOpener(envelope)
        with patch.object(operator.urllib.request, "build_opener", return_value=opener):
            operator.verify_owner_live_comment(123456789, self.args, "f" * 64)
        self.assertEqual(opener.urls, [(operator.AUTH_BASE + "123456789", 8)])

    def test_owner_approved_exact_comment(self):
        self.check_auth(self.fake_authorization())

    def test_wrong_owner_wrong_issue_expired_or_extra_fields_block(self):
        scenarios = (
            self.fake_authorization(user_id=OWNER_ID_PLACEHOLDER),
            self.fake_authorization(issue=926),
            self.fake_authorization(age_minutes=16),
            self.fake_authorization(payload={**auth(self.args, "f" * 64), "secret": "TOKEN_DO_NOT_ECHO"}),
            self.fake_authorization(payload={**auth(self.args, "f" * 64), "repo_sha": "e" * 40}),
        )
        for entry in scenarios:
            with self.subTest(entry=entry["issue_url"], created=entry["created_at"]):
                with self.assertRaises(operator.Blocked):
                    self.check_auth(entry)

    def test_missing_authorization_blocks_before_writes(self):
        with patch.object(operator, "check_baseline", return_value=self.files), \
             patch.object(operator, "verify_owner_live_comment", side_effect=operator.Blocked("denied")), \
             patch.object(operator, "service_generation", return_value=(1234, 5678)), \
             patch.object(operator.os, "mkdir") as mkdir:
            with self.assertRaisesRegex(operator.Blocked, "denied"):
                operator.apply_one_shot(self.args)
            mkdir.assert_not_called()

    def test_apply_order_and_postcondition_are_offline(self):
        calls = []
        def writing(path, data, *, mode=0o644):
            calls.append(("write", path.name, mode))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        def runner(cmd, *, timeout=25):
            calls.append(("run", cmd[-2] if cmd[0] == "/usr/bin/systemctl" and len(cmd) == 3 else cmd[1] if cmd[0] == "/usr/bin/systemctl" else "verify", timeout))
            if "--verify" in cmd:
                return json.dumps({"result": "PASS", "mode": "verify",
                    "credential_content_read": False,
                    "credential_content_hashed": False, "mutation_started": False})
            return ""
        patches, _ = self.baseline()
        with patches[0], patches[1], patches[2], \
             patch.object(operator, "check_baseline", return_value=self.files), \
             patch.object(operator, "verify_owner_live_comment", return_value=None), \
             patch.object(operator, "require_directory", return_value=None), \
             patch.object(operator, "write_exclusive", side_effect=writing), \
             patch.object(operator, "service_generation", return_value=(1234, 5678)), \
             patch.object(operator, "safe_run", side_effect=runner):
            self.assertEqual(operator.apply_one_shot(self.args), "PASS")
        self.assertEqual([x[0] for x in calls], ["write", "write", "write", "run", "run", "run"])
        self.assertEqual(calls[0][2], 0o600)
        self.assertTrue(self.recovery.exists())

    def test_failure_after_first_mutation_has_no_implicit_cleanup(self):
        patches, _ = self.baseline()
        def failing(_cmd, *, timeout=25):
            raise operator.Blocked("restart_failed")
        with patches[0], patches[1], patches[2], \
             patch.object(operator, "check_baseline", return_value=self.files), \
             patch.object(operator, "verify_owner_live_comment", return_value=None), \
             patch.object(operator, "require_directory", return_value=None), \
             patch.object(operator, "service_generation", return_value=(1234, 5678)), \
             patch.object(operator, "safe_run", side_effect=failing):
            # This test uses temp paths, but production-only owner/mode validation
            # is injected because the fake root has no root-owned metadata.
            def fake_write(path, data, *, mode=0o644):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            with patch.object(operator, "write_exclusive", side_effect=fake_write):
                with self.assertRaisesRegex(operator.Blocked, "restart_failed"):
                    operator.apply_one_shot(self.args)
        self.assertTrue(self.recovery.exists())
        self.assertTrue(self.source_target.exists())
        self.assertTrue(self.dropin_target.exists())

    def test_exclusive_public_install_no_overwrite(self):
        dest = self.root / "public.py"
        dest.write_bytes(b"existing")
        with self.assertRaisesRegex(operator.Blocked, "write_failed_no_automatic_cleanup"):
            operator.write_exclusive(dest, b"replacement")
        self.assertEqual(dest.read_bytes(), b"existing")

    def test_competing_service_change_blocks_before_first_write(self):
        with patch.object(operator, "check_baseline", return_value=self.files), \
             patch.object(operator, "verify_owner_live_comment", return_value=None), \
             patch.object(operator, "service_generation", side_effect=[(1234, 5678), (1235, 5678)]), \
             patch.object(operator.os, "mkdir") as mkdir:
            with self.assertRaisesRegex(operator.Blocked, "service_changed_before_mutation"):
                operator.apply_one_shot(self.args)
            mkdir.assert_not_called()

    def test_service_generation_shape_is_bounded(self):
        good = "MainPID=1234\nActiveEnterTimestampMonotonic=5678\n"
        with patch.object(operator, "safe_run", return_value=good):
            self.assertEqual(operator.service_generation(), (1234, 5678))
        for bad in ("MainPID=0\nActiveEnterTimestampMonotonic=5678\n",
                    "MainPID=1234\n",
                    "MainPID=1234\nActiveEnterTimestampMonotonic=5678\nExtra=1\n",
                    "MainPID=1234\nActiveEnterTimestampMonotonic=abc\n"):
            with self.subTest(output=bad):
                with patch.object(operator, "safe_run", return_value=bad):
                    with self.assertRaisesRegex(operator.Blocked, "service_generation_invalid"):
                        operator.service_generation()

    def test_privileged_operator_must_execute_from_installed_path(self):
        with self.assertRaisesRegex(operator.Blocked, "operator_not_running_at_installed_path"):
            operator.check_source(MAIN)

    def test_tracked_source_drift_is_denied_before_runtime_actions(self):
        for relative, data in self.files.items():
            p = self.root / "trusted-repo" / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        checkout = self.root / "trusted-repo"
        paths = tuple(self.files)
        owner = SimpleNamespace(pw_uid=os.getuid())
        def fake_git(*argv):
            if argv == ("rev-parse", "HEAD"):
                return MAIN + "\n"
            if argv == ("branch", "--show-current"):
                return "main\n"
            if argv == ("status", "--porcelain=v1", "--untracked-files=all"):
                return ""
            if argv == ("rev-parse", "refs/remotes/origin/main"):
                return MAIN + "\n"
            if argv[:2] == ("ls-files", "--"):
                return "\n".join(paths) + "\n"
            if argv[:2] == ("hash-object", "--"):
                return "a" * 40 + "\n"
            if argv[0] == "rev-parse" and argv[1].startswith(MAIN + ":"):
                return "a" * 40 + "\n"
            self.fail("unexpected Git command: " + repr(argv))
        with patch.object(operator, "REPO", checkout), \
             patch.object(operator, "OPERATOR", SOURCE), \
             patch.object(operator.pwd, "getpwnam", return_value=owner), \
             patch.object(operator, "safe_git", side_effect=fake_git):
            self.assertEqual(operator.check_source(MAIN), self.files)
        def dirty_git(*argv):
            if argv[0] == "status":
                return " M ops/lib/balkons-bot.py\n"
            return fake_git(*argv)
        with patch.object(operator, "REPO", checkout), \
             patch.object(operator, "OPERATOR", SOURCE), \
             patch.object(operator.pwd, "getpwnam", return_value=owner), \
             patch.object(operator, "safe_git", side_effect=dirty_git):
            with self.assertRaisesRegex(operator.Blocked, "checkout_not_clean"):
                operator.check_source(MAIN)
        def origin_drift(*argv):
            if argv == ("rev-parse", "refs/remotes/origin/main"):
                return "b" * 40 + "\n"
            return fake_git(*argv)
        with patch.object(operator, "REPO", checkout), \
             patch.object(operator, "OPERATOR", SOURCE), \
             patch.object(operator.pwd, "getpwnam", return_value=owner), \
             patch.object(operator, "safe_git", side_effect=origin_drift):
            with self.assertRaisesRegex(operator.Blocked, "origin_main_mismatch"):
                operator.check_source(MAIN)
        def blob_drift(*argv):
            if argv[:2] == ("hash-object", "--") and argv[2] == operator.SOURCE:
                return "c" * 40 + "\n"
            return fake_git(*argv)
        with patch.object(operator, "REPO", checkout), \
             patch.object(operator, "OPERATOR", SOURCE), \
             patch.object(operator.pwd, "getpwnam", return_value=owner), \
             patch.object(operator, "safe_git", side_effect=blob_drift):
            with self.assertRaisesRegex(operator.Blocked, "source_blob_mismatch"):
                operator.check_source(MAIN)

    def test_source_does_not_add_legacy_secret_copy_or_automatic_recovery(self):
        data = SOURCE.read_text()
        self.assertNotIn("shutil.copy", data)
        self.assertNotIn("shell=True", data)
        self.assertNotIn("os.system(", data)
        self.assertNotIn("docker ", data)
        self.assertNotIn("/etc/credstore.encrypted/", data)
        self.assertNotIn("unlink(", data)
        self.assertNotIn("rollback()", data)
        self.assertIn("O_EXCL", data)
        self.assertIn("NoRedirect", data)


OWNER_ID_PLACEHOLDER = 777

if __name__ == "__main__":
    unittest.main(verbosity=2)
