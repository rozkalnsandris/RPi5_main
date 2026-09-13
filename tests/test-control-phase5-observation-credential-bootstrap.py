from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_observation_credential_bootstrap.py"
CLI_PATH = ROOT / "ops/bin/rpi5-control-phase5-observation-credential-bootstrap"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = load_module("phase5_credential_bootstrap_test", MODULE_PATH)


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
    run([bootstrap.GIT_BINARY, "config", "user.email", "test@example.invalid"], cwd=root)
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
    head = run([bootstrap.GIT_BINARY, "rev-parse", "HEAD"], cwd=root)
    return head.stdout.decode("ascii").strip()


def private_args(
    directory: Path,
    repo: Path,
    sha: str,
    openssl: str = bootstrap.OPENSSL_BINARY,
    openssl_owner_uid: int = 0,
):
    return {
        "directory_path": str(directory),
        "repo_root": repo,
        "approved_source_sha": sha,
        "expected_uid": os.geteuid(),
        "expected_gid": os.getegid(),
        "required_euid": os.geteuid(),
        "openssl_binary": openssl,
        "openssl_owner_uid": openssl_owner_uid,
    }


class ControlPhase5ObservationCredentialBootstrapTests(unittest.TestCase):
    def test_public_contract_is_fixed_and_cli_rejects_authority_widening_arguments(self):
        self.assertEqual(bootstrap.REPOSITORY_IDENTITY, "rozkalnsandris/RPi5_main")
        self.assertEqual(bootstrap.CREDSTORE_DIRECTORY, "/etc/credstore")
        self.assertEqual(
            bootstrap.PRIVATE_KEY_FILENAME,
            "control-phase5-observation-ed25519.pem",
        )
        self.assertEqual(bootstrap.OPENSSL_BINARY, "/usr/bin/openssl")
        self.assertEqual(bootstrap.GIT_BINARY, "/usr/bin/git")
        self.assertEqual(bootstrap.KEY_ID, "rpi5-prod-2026-09")
        for forbidden in ("--target", "--directory", "--algorithm", "--openssl", "--key-id"):
            with self.subTest(forbidden=forbidden):
                result = run(
                    [
                        sys.executable,
                        str(CLI_PATH),
                        "--preflight",
                        "--approved-source-sha",
                        "0" * 40,
                        forbidden,
                        "attacker-value",
                    ]
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"unrecognized arguments", result.stderr)

    def test_preflight_is_non_mutating_and_public_safe(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            before = list(credstore.iterdir())
            receipt = bootstrap._preflight_at(**private_args(credstore, repo, sha))
            self.assertEqual(before, list(credstore.iterdir()))
            self.assertEqual(
                receipt,
                {
                    "authorization_consumed": False,
                    "contract": bootstrap.CONTRACT,
                    "keyId": bootstrap.KEY_ID,
                    "mutation_started": False,
                    "publicKeyBase64url": None,
                    "status": bootstrap.STATUS_PREFLIGHT_PASS,
                    "targetClass": bootstrap.TARGET_CLASS,
                },
            )
            self.assertNotIn(str(credstore), json.dumps(receipt))

    def test_apply_creates_exact_ed25519_credential_atomically(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            receipt = bootstrap._apply_at(**private_args(credstore, repo, sha))

            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            self.assertTrue(target.is_file())
            self.assertFalse((credstore / bootstrap.STAGING_FILENAME).exists())
            info = target.stat()
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(info.st_uid, os.geteuid())
            self.assertEqual(info.st_gid, os.getegid())
            self.assertEqual(receipt["status"], bootstrap.STATUS_CREATED)
            self.assertTrue(receipt["mutation_started"])
            self.assertTrue(receipt["authorization_consumed"])
            self.assertEqual(receipt["keyId"], bootstrap.KEY_ID)
            self.assertRegex(receipt["publicKeyBase64url"], r"^[A-Za-z0-9_-]{43}$")
            self.assertNotIn("=", receipt["publicKeyBase64url"])
            raw_public = base64.urlsafe_b64decode(receipt["publicKeyBase64url"] + "=")
            self.assertEqual(len(raw_public), 32)

            derived = run(
                [
                    bootstrap.OPENSSL_BINARY,
                    "pkey",
                    "-in",
                    str(target),
                    "-pubout",
                    "-outform",
                    "DER",
                ]
            )
            self.assertEqual(derived.returncode, 0)
            self.assertEqual(derived.stdout, bootstrap.ED25519_SPKI_PREFIX + raw_public)

    def test_existing_final_or_symlink_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            target.write_text("keep-me", encoding="utf-8")
            target.chmod(0o600)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._apply_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "TARGET_EXISTS")
            self.assertFalse(caught.exception.mutation_started)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep-me")

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            other = credstore / "other"
            other.write_text("keep-me", encoding="utf-8")
            target = credstore / bootstrap.PRIVATE_KEY_FILENAME
            target.symlink_to(other.name)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "TARGET_EXISTS")
            self.assertFalse(caught.exception.mutation_started)
            self.assertEqual(other.read_text(encoding="utf-8"), "keep-me")

    def test_directory_permissions_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            credstore.chmod(0o770)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "CREDSTORE_INVALID")

            credstore.chmod(0o700)
            alias = root / "credstore-link"
            alias.symlink_to(credstore.name)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(alias, repo, sha))
            self.assertEqual(caught.exception.code, "CREDSTORE_INVALID")

    def test_source_sha_repository_and_dirty_tree_are_bound(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)

            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(credstore, repo, "0" * 40))
            self.assertEqual(caught.exception.code, "SOURCE_SHA_MISMATCH")

            run(
                [
                    bootstrap.GIT_BINARY,
                    "remote",
                    "set-url",
                    "origin",
                    "https://github.com/example/other.git",
                ],
                cwd=repo,
            )
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "SOURCE_REPOSITORY_MISMATCH")

            run(
                [
                    bootstrap.GIT_BINARY,
                    "remote",
                    "set-url",
                    "origin",
                    "https://github.com/rozkalnsandris/RPi5_main.git",
                ],
                cwd=repo,
            )
            (repo / "README").write_text("dirty\n", encoding="utf-8")
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._preflight_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "SOURCE_WORKTREE_DIRTY")

    def test_post_mutation_openssl_error_is_secret_safe_and_leaves_staging_for_stop(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            marker = "private-marker-must-not-leak"
            fake = root / "openssl"
            fake.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    if [ "$1" = "list" ]; then
                      echo ED25519
                      exit 0
                    fi
                    if [ "$1" = "genpkey" ]; then
                      echo '{marker}' >&2
                      exit 17
                    fi
                    exit 19
                    """
                ),
                encoding="utf-8",
            )
            fake.chmod(0o755)
            state = bootstrap._OperationState()
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._apply_at(
                    **private_args(
                        credstore,
                        repo,
                        sha,
                        str(fake),
                        openssl_owner_uid=os.geteuid(),
                    ),
                    state=state,
                )
            self.assertEqual(caught.exception.code, "KEY_GENERATION_FAILED")
            self.assertTrue(caught.exception.mutation_started)
            self.assertTrue(caught.exception.authorization_consumed)
            self.assertTrue((credstore / bootstrap.STAGING_FILENAME).is_file())
            self.assertFalse((credstore / bootstrap.PRIVATE_KEY_FILENAME).exists())
            public = bootstrap.public_error_receipt(caught.exception)
            rendered = json.dumps(public, sort_keys=True)
            self.assertNotIn(marker, rendered)
            self.assertNotIn(str(credstore), rendered)
            self.assertNotIn(str(fake), rendered)
            self.assertEqual(public["status"], bootstrap.STATUS_FAIL_CLOSED)
            self.assertTrue(public["mutation_started"])
            self.assertTrue(public["authorization_consumed"])

    def test_preexisting_staging_blocks_without_consuming_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            sha = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            staging = credstore / bootstrap.STAGING_FILENAME
            staging.write_text("prior-attempt-marker", encoding="utf-8")
            staging.chmod(0o600)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._apply_at(**private_args(credstore, repo, sha))
            self.assertEqual(caught.exception.code, "STAGING_EXISTS")
            self.assertFalse(caught.exception.mutation_started)
            self.assertFalse(caught.exception.authorization_consumed)
            self.assertEqual(staging.read_text(encoding="utf-8"), "prior-attempt-marker")

    def test_invalid_approved_sha_fails_before_filesystem_mutation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            _ = make_repo(repo)
            credstore = root / "credstore"
            credstore.mkdir(mode=0o700)
            with self.assertRaises(bootstrap.Phase5CredentialBootstrapError) as caught:
                bootstrap._apply_at(**private_args(credstore, repo, "not-a-sha"))
            self.assertEqual(caught.exception.code, "SOURCE_SHA_INVALID")
            self.assertFalse(caught.exception.mutation_started)
            self.assertEqual(list(credstore.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
