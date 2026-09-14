from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib/deploy_executor"
sys.path.insert(0, str(LIB))

import control_phase5_observation_credential_reconciliation as reconciliation

bootstrap = reconciliation.bootstrap
CLI_PATH = ROOT / "ops/bin/rpi5-control-phase5-observation-credential-reconcile"


def run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    )


def make_repo(root: Path) -> str:
    root.mkdir()
    run([bootstrap.GIT_BINARY, "init", "-q", "-b", "main"], cwd=root)
    run([bootstrap.GIT_BINARY, "config", "user.name", "Test"], cwd=root)
    run([bootstrap.GIT_BINARY, "config", "user.email", "fixture" + chr(64) + "example.invalid"], cwd=root)
    (root / "README").write_text("fixture\n", encoding="utf-8")
    run([bootstrap.GIT_BINARY, "add", "README"], cwd=root)
    committed = run([bootstrap.GIT_BINARY, "commit", "-q", "-m", "fixture"], cwd=root)
    if committed.returncode != 0:
        raise AssertionError(committed.stderr.decode("utf-8", "replace"))
    run(
        [
            bootstrap.GIT_BINARY,
            "remote",
            "add",
            "origin",
            "https://github.com/rozkalnsandris/RPi5_main.git",
        ],
        cwd=root,
    )
    return run([bootstrap.GIT_BINARY, "rev-parse", "HEAD"], cwd=root).stdout.decode("ascii").strip()


def private_args(directory: Path, repo: Path, sha: str) -> dict[str, object]:
    return {
        "directory_path": str(directory),
        "repo_root": repo,
        "approved_source_sha": sha,
        "expected_uid": os.geteuid(),
        "expected_gid": os.getegid(),
        "required_euid": os.geteuid(),
        "openssl_binary": bootstrap.OPENSSL_BINARY,
        "openssl_owner_uid": 0,
    }


def generate_key(target: Path) -> None:
    result = run(
        [bootstrap.OPENSSL_BINARY, "genpkey", "-algorithm", "ED25519", "-out", str(target)]
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", "replace"))
    target.chmod(0o600)


class ControlPhase5CredentialReconciliationTests(unittest.TestCase):
    def test_contract_is_fixed_and_cli_rejects_authority_widening(self):
        self.assertEqual(reconciliation.CONTRACT, "CONTROL_PHASE5_OBSERVATION_CREDENTIAL_RECONCILIATION_V1")
        self.assertEqual(bootstrap.PRIVATE_KEY_FILENAME, "control-phase5-observation-ed25519.pem")
        for forbidden in ("--target", "--directory", "--openssl", "--key-id"):
            with self.subTest(forbidden=forbidden):
                result = run(
                    [
                        sys.executable,
                        str(CLI_PATH),
                        "--approved-source-sha",
                        "0" * 40,
                        forbidden,
                        "attacker-value",
                    ]
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"unrecognized arguments", result.stderr)

    def test_reconcile_valid_existing_ed25519_is_read_only_and_public_safe(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            generate_key(target)
            before_bytes = target.read_bytes()
            before_stat = target.stat()

            receipt = reconciliation._reconcile_at(**private_args(credstore, repo, sha))

            after_stat = target.stat()
            self.assertEqual(target.read_bytes(), before_bytes)
            self.assertEqual(before_stat.st_ino, after_stat.st_ino)
            self.assertEqual(before_stat.st_size, after_stat.st_size)
            self.assertEqual(stat.S_IMODE(after_stat.st_mode), 0o600)
            self.assertEqual(receipt["status"], reconciliation.STATUS_RECONCILED)
            self.assertFalse(receipt["mutation_started"])
            self.assertFalse(receipt["authorization_consumed"])
            self.assertRegex(receipt["publicKeyBase64url"], r"^[A-Za-z0-9_-]{43}$")
            raw_public = base64.urlsafe_b64decode(receipt["publicKeyBase64url"] + "=")
            self.assertEqual(len(raw_public), 32)
            self.assertNotIn(str(credstore), json.dumps(receipt, sort_keys=True))

    def test_target_absent_and_staging_present_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "TARGET_ABSENT")

            staging = credstore / bootstrap.STAGING_FILENAME
            staging.write_text("prior-state", encoding="utf-8")
            staging.chmod(0o600)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "STAGING_EXISTS")

    def test_symlink_wrong_mode_and_hardlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            real = credstore / "real-key"
            generate_key(real)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            target.symlink_to(real.name)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "TARGET_STATE_AMBIGUOUS")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            generate_key(target)
            target.chmod(0o640)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "KEY_FILE_INVALID")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            generate_key(target)
            os.link(target, credstore / "second-link")
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "KEY_FILE_INVALID")

    def test_non_key_content_fails_without_leaking_content_or_path(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            marker = "sensitive-fixture-marker"
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            target.write_text(marker, encoding="utf-8")
            target.chmod(0o600)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "KEY_VALIDATION_FAILED")
            rendered = json.dumps(reconciliation.public_error_receipt(caught.exception), sort_keys=True)
            self.assertNotIn(marker, rendered)
            self.assertNotIn(str(credstore), rendered)

    def test_source_sha_is_still_bound(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            generate_key(target)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                reconciliation._reconcile_at(**private_args(credstore, repo, "0" * 40))
            self.assertEqual(caught.exception.code, "SOURCE_SHA_MISMATCH")

    def test_consistency_check_discards_output_and_has_no_export_flags(self):
        with tempfile.TemporaryFile() as handle:
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=None, stderr=None)
            state = bootstrap._OperationState()
            with mock.patch.object(bootstrap, "_run_command", return_value=completed) as command:
                reconciliation._check_key_consistency(
                    handle.fileno(), bootstrap.OPENSSL_BINARY, state
                )
            argv = command.call_args.args[0]
            self.assertIn("-check", argv)
            self.assertIn("-noout", argv)
            self.assertNotIn("-text", argv)
            self.assertNotIn("-pubout", argv)
            self.assertNotIn("-out", argv)
            self.assertEqual(command.call_args.kwargs["stdout_target"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
