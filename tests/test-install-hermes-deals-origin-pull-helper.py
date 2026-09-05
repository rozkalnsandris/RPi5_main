from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-hermes-deals-origin-pull-helper.py"
MANIFEST = ROOT / "ops/deploy/hermes-deals-origin-pull-helper-installer.json"
spec = importlib.util.spec_from_file_location("origin_pull_helper_installer", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class HermesOriginPullHelperInstallerTests(unittest.TestCase):
    def test_source_and_target_surface_is_fixed(self) -> None:
        self.assertEqual(installer.HERMES_SOURCE_SHA, "2f47f64ab15e767f4e53ad182326e64e313d5094")
        self.assertEqual(installer.HERMES_SOURCE_ROOT, installer.ROOT.parent / "hermes-deals-origin-pull-trusted")
        self.assertEqual(installer.HERMES_ORIGIN, "https://github.com/rozkalnsandris/hermes-deals.git")
        self.assertEqual([str(item.path) for item in installer.FILE_TARGETS], [
            "/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch",
            "/usr/local/libexec/hermes-deals-audits/origin-path-probe.py",
        ])
        self.assertEqual(str(installer.REGISTRATION_TARGET), "/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json")
        self.assertEqual(len(installer.DIR_TARGETS), 4)
        self.assertEqual(installer.INSTALL_MUTATION_BUDGET, (
            ("trusted-directory-materialization", 4),
            ("trusted-file-materialization", 3),
        ))

    def test_reviewed_hermes_source_identities_are_exact(self) -> None:
        helper, probe = installer.FILE_TARGETS
        self.assertEqual(helper.expected_blob, "51bb23cc6c2083ab7c8b4e81ba82dd880e46d673")
        self.assertEqual(helper.expected_sha256, "f2f6e4ca823eb6c0872de0a5e92531ebacb076c48934c80654d84f3ef6f7e625")
        self.assertEqual(probe.expected_blob, "2362e8eb578a7279c38fe4ed2a7d1edd05df891a")
        self.assertEqual(probe.expected_sha256, "96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43")

    def test_registration_is_canonical_and_exact(self) -> None:
        raw = installer._registration_bytes()
        value = json.loads(raw)
        self.assertEqual(set(value), {"schema", "capability", "registered_source_sha", "helper_sha256", "probe_sha256"})
        self.assertEqual(value["registered_source_sha"], installer.HERMES_SOURCE_SHA)
        self.assertEqual(value["capability"], "origin-path-audit")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "b92564a93d67098c9ec264e88d48096ae1323430547ed14b6d22b590ac8591bc")
        self.assertEqual(installer._git_blob(raw), "eac8778b2c09e191ca2d3abac3a4f5e243cd41c3")

    def test_git_safe_directory_scope_is_exact(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b"ok\n", stderr=b"")
        with mock.patch.object(installer.subprocess, "run", return_value=completed) as run:
            installer._git(installer.HERMES_SOURCE_ROOT, "rev-parse", "HEAD")
        argv = run.call_args.args[0]
        self.assertEqual(argv[:5], (
            str(installer.GIT), "-c", f"safe.directory={installer.HERMES_SOURCE_ROOT}",
            "-C", str(installer.HERMES_SOURCE_ROOT),
        ))
        self.assertNotIn("safe.directory=*", argv)
        self.assertNotIn("--global", argv)
        self.assertNotIn("--system", argv)

    def test_existing_first_install_target_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            installer._require_absent(target)
            target.write_bytes(b"x")
            with self.assertRaises(installer.HermesOriginPullHelperInstallerError):
                installer._require_absent(target)

    def test_directory_creation_is_exact_and_existing_target_is_not_adopted(self) -> None:
        old_uid, old_gid = installer.ROOT_UID, installer.ROOT_GID
        try:
            installer.ROOT_UID, installer.ROOT_GID = os.getuid(), os.getgid()
            with tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                child = parent / "child"
                old_dirs = installer.DIR_TARGETS
                installer.DIR_TARGETS = (child,)
                try:
                    os.chmod(parent, 0o755)
                    installer._create_directory(child)
                    self.assertEqual(child.stat().st_mode & 0o777, 0o700)
                    with self.assertRaises(installer.HermesOriginPullHelperInstallerError):
                        installer._create_directory(child)
                finally:
                    installer.DIR_TARGETS = old_dirs
        finally:
            installer.ROOT_UID, installer.ROOT_GID = old_uid, old_gid

    def test_file_materialization_is_exclusive_and_exact(self) -> None:
        old_uid, old_gid = installer.ROOT_UID, installer.ROOT_GID
        old_parents = installer.SHARED_PARENTS
        try:
            installer.ROOT_UID, installer.ROOT_GID = os.getuid(), os.getgid()
            with tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                os.chmod(parent, 0o755)
                path = parent / "helper"
                desired = b"reviewed\n"
                target = installer.FileTarget(
                    path, 0o755, None, installer._git_blob(desired), hashlib.sha256(desired).hexdigest()
                )
                installer.SHARED_PARENTS = ((parent, 0o755),)
                installer._write_file(target, desired)
                installer._verify_file(target, desired)
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
                with self.assertRaises(installer.HermesOriginPullHelperInstallerError):
                    installer._write_file(target, desired)
        finally:
            installer.SHARED_PARENTS = old_parents
            installer.ROOT_UID, installer.ROOT_GID = old_uid, old_gid

    def test_post_install_verification_is_descriptor_safe(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        block = source[source.index("def _verify_file"):source.index("def _receipt")]
        self.assertIn("os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC", block)
        self.assertIn("opened.st_dev, opened.st_ino", block)
        self.assertIn("follow_symlinks=False", block)

    def test_apply_failure_after_first_mutation_preserves_fail_closed_progress(self) -> None:
        d1, d2 = Path("/tmp/a"), Path("/tmp/b")
        with mock.patch.object(installer, "ROOT_UID", os.geteuid()), \
             mock.patch.object(installer, "DIR_TARGETS", (d1, d2)), \
             mock.patch.object(installer, "_preflight", return_value=()), \
             mock.patch.object(installer, "_create_directory", side_effect=[None, installer.HermesOriginPullHelperInstallerError("boom")]):
            with self.assertRaises(installer.ApplyFailure) as caught:
                installer.apply("a" * 40)
        progress = caught.exception.progress
        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.directories_materialized, 1)
        self.assertEqual(progress.files_materialized, 0)

    def test_receipt_never_claims_forbidden_authority(self) -> None:
        value = json.loads(installer._receipt("TEST", "a" * 40, installer.Progress()))
        for field in (
            "credential_content_read", "credential_mutated", "github_api_request",
            "helper_executed", "genuine_audit_authorized", "socket_request_sent",
            "systemd_mutation", "broker_dispatch_enabled", "production_mutation_started",
            "automatic_retry", "automatic_rollback", "automatic_cleanup",
        ):
            self.assertFalse(value[field], field)

    def test_manifest_binds_exact_operator_and_targets(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(value["installer"]["source_blob"], installer._git_blob(SCRIPT.read_bytes()))
        self.assertEqual(value["hermes_source"]["sha"], installer.HERMES_SOURCE_SHA)
        self.assertEqual(value["hermes_source"]["trusted_checkout_derivation"], "RPi5_CHECKOUT_PARENT/hermes-deals-origin-pull-trusted")
        self.assertEqual(value["mutation_budget"], [list(row) for row in installer.INSTALL_MUTATION_BUDGET])
        self.assertEqual(value["registration"]["sha256"], "b92564a93d67098c9ec264e88d48096ae1323430547ed14b6d22b590ac8591bc")
        self.assertEqual(value["registration"]["git_blob"], "eac8778b2c09e191ca2d3abac3a4f5e243cd41c3")
        self.assertEqual(len(value["directory_targets"]), 4)
        self.assertEqual(len(value["file_targets"]), 3)


if __name__ == "__main__":
    unittest.main()
