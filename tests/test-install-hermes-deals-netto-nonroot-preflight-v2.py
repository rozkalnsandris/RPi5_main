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
SCRIPT = ROOT / "scripts/install-hermes-deals-netto-nonroot-preflight-v2.py"
MANIFEST = ROOT / "ops/deploy/hermes-deals-netto-nonroot-preflight-v2-installer.json"
spec = importlib.util.spec_from_file_location("netto_v2_installer", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class NettoPreflightV2InstallerTests(unittest.TestCase):
    def test_source_and_target_surface_is_fixed(self) -> None:
        self.assertEqual(
            installer.HERMES_SOURCE_SHA,
            "067db7bd4b8057bc16a9bf0ef9ed8487127a0a05",
        )
        self.assertEqual(
            installer.HERMES_SOURCE_ROOT,
            installer.ROOT.parent / "hermes-deals-netto-nonroot-preflight-v2-trusted",
        )
        self.assertEqual(
            installer.HELPER_SOURCE,
            "tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py",
        )
        self.assertEqual(
            str(installer.HELPER_TARGET),
            "/usr/local/libexec/hermes-deals-audits/"
            "netto-missing-normal-price-nonroot-preflight-v2/"
            "netto_missing_normal_price_nonroot_preflight_v2.py",
        )
        self.assertEqual(
            str(installer.REGISTRATION_TARGET),
            "/etc/hermes-deals-audits.d/"
            "netto-missing-normal-price-nonroot-preflight-v2.json",
        )
        self.assertEqual(
            installer.INSTALL_MUTATION_BUDGET,
            (("trusted-directory-materialization", 1), ("trusted-file-materialization", 2)),
        )

    def test_reviewed_helper_identity_is_exact(self) -> None:
        self.assertEqual(
            installer.HELPER_BLOB,
            "0f8b01ed3129323cc59e526262b369cf33346aba",
        )
        self.assertEqual(
            installer.HELPER_SHA256,
            "275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c",
        )
        self.assertEqual(installer.HELPER_FILE.mode, 0o555)

    def test_registration_is_canonical_and_exact(self) -> None:
        raw = installer._registration_bytes()
        value = json.loads(raw)
        self.assertEqual(
            set(value),
            {"schema", "capability", "registered_source_sha", "helper_sha256"},
        )
        self.assertEqual(value["registered_source_sha"], installer.HERMES_SOURCE_SHA)
        self.assertEqual(value["capability"], installer.CAPABILITY)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "887ad4e9295864307a24df6773e98f75056961aebeedd57b95641ba3e7386a1f",
        )
        self.assertEqual(
            installer._git_blob(raw),
            "848773cf981f49265ca3e3a968c71fdd93c8aee2",
        )
        self.assertEqual(installer._registration_target().mode, 0o444)

    def test_git_scope_has_no_global_safe_directory(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b"ok\n", stderr=b"")
        with mock.patch.object(installer.subprocess, "run", return_value=completed) as run:
            installer._git(installer.HERMES_SOURCE_ROOT, "rev-parse", "HEAD")
        argv = run.call_args.args[0]
        self.assertEqual(
            argv[:5],
            (
                str(installer.GIT),
                "-c",
                f"safe.directory={installer.HERMES_SOURCE_ROOT}",
                "-C",
                str(installer.HERMES_SOURCE_ROOT),
            ),
        )
        self.assertNotIn("safe.directory=*", argv)
        self.assertNotIn("--global", argv)
        self.assertNotIn("--system", argv)

    def test_existing_target_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            installer._require_absent(target)
            target.write_bytes(b"x")
            with self.assertRaises(installer.NettoPreflightV2InstallerError):
                installer._require_absent(target)

    def test_directory_creation_is_exact_and_not_adopted(self) -> None:
        old_uid, old_gid = installer.ROOT_UID, installer.ROOT_GID
        old_parents = installer.SHARED_PARENTS
        try:
            installer.ROOT_UID, installer.ROOT_GID = os.getuid(), os.getgid()
            with tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                os.chmod(parent, 0o755)
                child = parent / "capability"
                installer.SHARED_PARENTS = ((parent, 0o755),)
                installer._create_directory(child, 0o755)
                self.assertEqual(child.stat().st_mode & 0o777, 0o755)
                with self.assertRaises(installer.NettoPreflightV2InstallerError):
                    installer._create_directory(child, 0o755)
        finally:
            installer.SHARED_PARENTS = old_parents
            installer.ROOT_UID, installer.ROOT_GID = old_uid, old_gid

    def test_file_materialization_is_exclusive_and_exact(self) -> None:
        old_uid, old_gid = installer.ROOT_UID, installer.ROOT_GID
        old_dirs = installer.DIR_TARGETS
        try:
            installer.ROOT_UID, installer.ROOT_GID = os.getuid(), os.getgid()
            with tempfile.TemporaryDirectory() as temp:
                parent = Path(temp)
                os.chmod(parent, 0o755)
                path = parent / "helper.py"
                desired = b"reviewed\n"
                target = installer.FileTarget(
                    path,
                    0o555,
                    None,
                    installer._git_blob(desired),
                    hashlib.sha256(desired).hexdigest(),
                )
                installer.DIR_TARGETS = ((parent, 0o755),)
                installer._write_file(target, desired)
                installer._verify_file(target, desired)
                self.assertEqual(path.stat().st_mode & 0o777, 0o555)
                with self.assertRaises(installer.NettoPreflightV2InstallerError):
                    installer._write_file(target, desired)
        finally:
            installer.DIR_TARGETS = old_dirs
            installer.ROOT_UID, installer.ROOT_GID = old_uid, old_gid

    def test_post_install_verification_is_descriptor_safe(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        block = source[source.index("def _verify_file"):source.index("def _receipt")]
        self.assertIn("os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC", block)
        self.assertIn("opened.st_dev, opened.st_ino", block)
        self.assertIn("follow_symlinks=False", block)

    def test_apply_failure_preserves_progress_and_has_no_cleanup(self) -> None:
        d1 = Path("/tmp/netto-test-dir")
        prepared = ((installer.HELPER_FILE, b"x"),)
        with mock.patch.object(installer, "ROOT_UID", os.geteuid()), \
             mock.patch.object(installer, "DIR_TARGETS", ((d1, 0o755),)), \
             mock.patch.object(installer, "_preflight", return_value=prepared), \
             mock.patch.object(installer, "_create_directory", return_value=None), \
             mock.patch.object(
                 installer,
                 "_write_file",
                 side_effect=installer.NettoPreflightV2InstallerError("boom"),
             ):
            with self.assertRaises(installer.ApplyFailure) as caught:
                installer.apply("a" * 40)
        progress = caught.exception.progress
        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.directories_materialized, 1)
        self.assertEqual(progress.files_materialized, 0)

    def test_receipt_never_claims_out_of_scope_authority(self) -> None:
        value = json.loads(installer._receipt("TEST", "a" * 40, installer.Progress()))
        for field in (
            "credential_content_read",
            "credential_mutated",
            "github_api_request",
            "helper_executed",
            "canary_authorized",
            "parser_executed",
            "database_write_performed",
            "review_write_performed",
            "deployment_performed",
            "user_group_mutation",
            "docker_mutation",
            "systemd_mutation",
            "execution_wiring_changed",
            "automatic_retry",
            "automatic_rollback",
            "automatic_cleanup",
            "host_mutation_started",
        ):
            self.assertFalse(value[field], field)

    def test_no_generic_execution_or_privilege_bridge(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("os.system(", source)
        self.assertNotIn("subprocess.Popen", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/usr/bin/sudo", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("/var/run/docker.sock", source)
        self.assertIn('GIT = Path("/usr/bin/git")', source)
        self.assertIn('parser.add_argument("expected_source_sha")', source)
        self.assertIn('parser.add_argument("--apply", action="store_true")', source)

    def test_manifest_binds_exact_source_and_budget(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            value["installer"]["source_blob"],
            installer._git_blob(SCRIPT.read_bytes()),
        )
        self.assertEqual(value["hermes_source"]["sha"], installer.HERMES_SOURCE_SHA)
        self.assertEqual(value["reviewed_source"]["git_blob"], installer.HELPER_BLOB)
        self.assertEqual(value["reviewed_source"]["sha256"], installer.HELPER_SHA256)
        self.assertEqual(
            value["mutation_budget"],
            [list(row) for row in installer.INSTALL_MUTATION_BUDGET],
        )
        self.assertEqual(
            value["registration"]["sha256"],
            "887ad4e9295864307a24df6773e98f75056961aebeedd57b95641ba3e7386a1f",
        )
        self.assertEqual(
            value["registration"]["git_blob"],
            "848773cf981f49265ca3e3a968c71fdd93c8aee2",
        )
        self.assertEqual(len(value["directory_targets"]), 1)
        self.assertEqual(len(value["file_targets"]), 2)
        self.assertFalse(value["safety"]["helper_execution"])
        self.assertFalse(value["safety"]["canary_authorized"])
        self.assertFalse(value["safety"]["execution_wiring_changed"])

    def test_dedicated_workflow_runs_this_contract(self) -> None:
        workflow = ROOT / ".github/workflows/netto-v2-installer-contract.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn(
            "python3 ./tests/test-install-hermes-deals-netto-nonroot-preflight-v2.py",
            source,
        )
        self.assertIn("runs-on: ubuntu-latest", source)
        self.assertNotIn("self-hosted", source)


if __name__ == "__main__":
    unittest.main()
