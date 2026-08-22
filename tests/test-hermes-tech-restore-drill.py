from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("hermes-tech-restore-drill")
LOADER = SourceFileLoader("restore_drill", str(SCRIPT))
SPEC = spec_from_loader("restore_drill", LOADER)
assert SPEC is not None
restore_drill = module_from_spec(SPEC)
LOADER.exec_module(restore_drill)


def add_file(tar: tarfile.TarFile, name: str, data: bytes = b"fixture\n", mode: int = 0o600) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def make_valid_archive(path: Path) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for parts in sorted(restore_drill.HERMES_REQUIRED):
            name = "./" + "/".join(parts)
            data = b"fixture\n"
            mode = 0o600
            if parts[-1] in {"collector.py", "digest.py", "publish.sh", "run_digests.sh", "ci.sh"}:
                mode = 0o700
            add_file(tar, name, data=data, mode=mode)
        add_file(
            tar,
            "./backup-metadata/manifest.txt",
            b"created_at=2026-08-22T02:00:00+02:00\nbackup_version=12\n",
        )


def write_sidecar(archive: Path, *, digest: str | None = None) -> Path:
    actual = digest or sha256(archive.read_bytes()).hexdigest()
    sidecar = Path(str(archive) + ".sha256")
    sidecar.write_text(f"{actual}  {archive.name}\n", encoding="utf-8")
    return sidecar


class RestoreDrillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_obj = tempfile.TemporaryDirectory(prefix="rpi5-restore-drill-test-")
        self.addCleanup(self.tmp_obj.cleanup)
        self.root = Path(self.tmp_obj.name)
        self.archive = self.root / "rpi5_backup_2026-08-22_02-00-00.tar.gz.age"
        make_valid_archive(self.archive)
        self.sidecar = write_sidecar(self.archive)
        self.identity = self.root / "age.key"
        self.identity.write_text("FIXTURE_PRIVATE_VALUE_DO_NOT_EMIT\n", encoding="utf-8")
        os.chmod(self.identity, 0o600)
        self.evidence = self.root / "evidence.json"
        self.rpi = self.root / "rpi-source"
        self.hermes = self.root / "hermes-source"
        self.rpi.mkdig()
        self.hermes.mkdir()

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            archive=self.archive,
            sidecar=self.sidecar,
            age_identity=self.identity,
            rpi_source_root=self.rpi,
            rpi_source_sha="1" * 40,
            hermes_source_root=self.hermes,
            hermes_source_sha="2" * 40,
            evidence=self.evidence,
            work_dir=self.root,
            min_free_bytes=1,
        )

    @staticmethod
    def fake_verifier_report() -> dict:
        return {
            "status": "pass",
            "mode": "isolated-restore-acceptance",
            "git_head": "3" * 40,
            "git_fsck": "ok",
            "sqlite_sha256": "4" * 64,
            "sqlite_size_bytes": 4096,
            "sqlite_quick_check": "ok",
            "sqlite_user_version": 3,
            "sqlite_unchanged_during_check": True,
            "env_mode": "0600",
            "env_contents_read": False,
            "hugo_index_bytes": 100,
            "hugo_sitemap_bytes": 100,
            "hugo_robots_bytes": 100,
        }

    def test_valid_synthetic_archive_passes_and_cleans_plaintext(self) -> None:
        def fake_decrypt(_identity: Path, archive: Path, output: Path) -> None:
            shutil.copyfile(archive, output)
            os.chmod(output, 0o600)

        with (
            patch.object(restore_drill, "_verify_source_checkout", return_value=self.root / "verifier.py"),
            patch.object(restore_drill, "_run_age_decrypt", side_effect=fake_decrypt),
            patch.object(restore_drill, "_run_hermes_verifier", return_value=self.fake_verifier_report()),
        ):
            code, report = restore_drill.execute(self.args())

        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["cleanup_plaintext_removed"])
        self.assertIsNone(report["failure_category"])
        self.assertEqual(report["verifier"]["sqlite_quick_check"], "ok")
        self.assertEqual(list(self.root.glob("hermes-tech-restore-drill-*")), [])
        encoded = self.evidence.read_text(encoding="utf-8")
        self.assertNotIn("FIXTURE_PRIVATE_VALUE_DO_NOT_EMIT", encoded)
        self.assertNotIn(str(self.identity), encoded)
        self.assertNotIn(str(self.root / "restore"), encoded)

    def test_wrong_sidecar_fails_before_decrypt(self) -> None:
        write_sidecar(self.archive, digest="0" * 64)
        with patch.object(restore_drill, "_run_age_decrypt") as decrypt:
            code, report = restore_drill.execute(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "sidecar_mismatch")
        decrypt.assert_not_called()

    def test_corrupt_age_payload_fails_closed_and_cleans(self) -> None:
        with (
            patch.object(restore_drill, "_verify_source_checkout", return_value=self.root / "verifier.py"),
            patch.object(
                restore_drill,
                "_run_age_decrypt",
                side_effect=restore_drill.DrillError("age_decrypt_failed"),
            ),
        ):
            code, report = restore_drill.execute(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "age_decrypt_failed")
        self.assertTrue(report["cleanup_plaintext_removed"])
        self.assertEqual(list(self.root.glob("hermes-tech-restore-drill-*")), [])

    def test_traversal_and_absolute_paths_are_rejected(self) -> None:
        for bad_name in ("../escape", "/absolute"):
            path = self.root / ("bad-" + bad_name.replace("/", "_").replace(".", "x") + ".tar.gz")
            with tarfile.open(path, "w:gz") as tar:
                add_file(tar, bad_name)
            with self.subTest(name=bad_name):
                with self.assertRaisesRegex(restore_drill.DrillError, "archive_validation_failed"):
                    restore_drill._validate_archive(path)

    def test_unsafe_symlink_and_hardlink_are_rejected(self) -> None:
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            path = self.root / f"bad-link-{kind!r}.tar.gz"
            make_valid_archive(path)
            # Rebuild with the valid entries plus one escaping link.
            rebuilt = self.root / f"rebuilt-{kind!r}.tar.gz"
            with tarfile.open(rebuilt, "w:gz") as tar:
                for parts in sorted(restore_drill.HERMES_REQUIRED):
                    add_file(tar, "./" + "/".join(parts))
                add_file(
                    tar,
                    "./backup-metadata/manifest.txt",
                    b"created_at=2026-08-22T02:00:00+02:00\nbackup_version=12\n",
                )
                info = tarfile.TarInfo("./home/andris/hermes-tech/escape-link")
                info.type = kind
                info.linkname = "../../../../etc/passwd"
                tar.addfile(info)
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(restore_drill.DrillError, "archive_validation_failed"):
                    restore_drill._validate_archive(rebuilt)

    def test_production_work_dir_is_impossible(self) -> None:
        production = self.root / "production-hermes"
        child = production / "child"
        child.mkdir(parents=True)
        with patch.object(restore_drill, "PRODUCTION_APP", production):
            with self.assertRaisesRegex(restore_drill.DrillError, "production_root_forbidden"):
                restore_drill._work_base_preflight(child, 1, 1)

    def test_verifier_failure_propagates_and_plaintext_is_removed(self) -> None:
        def fake_decrypt(_identity: Path, archive: Path, output: Path) -> None:
            shutil.copyfile(archive, output)

        with (
            patch.object(restore_drill, "_verify_source_checkout", return_value=self.root / "verifier.py"),
            patch.object(restore_drill, "_run_age_decrypt", side_effect=fake_decrypt),
            patch.object(
                restore_drill,
                "_run_hermes_verifier",
                side_effect=restore_drill.DrillError("verifier_failed"),
            ),
        ):
            code, report = restore_drill.execute(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "verifier_failed")
        self.assertTrue(report["cleanup_plaintext_removed"])
        self.assertEqual(list(self.root.glob("hermes-tech-restore-drill-*")), [])

    def test_archive_validation_failure_removes_plaintext_workspace(self) -> None:
        bad_archive = self.root / "rpi5_backup_2026-08-22_03-00-00.tar.gz.age"
        with tarfile.open(bad_archive, "w:gz") as tar:
            for parts in sorted(restore_drill.HERMES_REQUIRED):
                add_file(tar, "./" + "/".join(parts))
            add_file(
                tar,
                "./backup-metadata/manifest.txt",
                b"created_at=2026-08-22T03:00:00+02:00\nbackup_version=12\n",
            )
            add_file(tar, "../escape")
        bad_sidecar = write_sidecar(bad_archive)
        args = self.args()
        args.archive = bad_archive
        args.sidecar = bad_sidecar

        def fake_decrypt(_identity: Path, archive: Path, output: Path) -> None:
            shutil.copyfile(archive, output)

        with (
            patch.object(restore_drill, "_verify_source_checkout", return_value=self.root / "verifier.py"),
            patch.object(restore_drill, "_run_age_decrypt", side_effect=fake_decrypt),
        ):
            code, report = restore_drill.execute(args)
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "archive_validation_failed")
        self.assertTrue(report["cleanup_plaintext_removed"])
        self.assertEqual(list(self.root.glob("hermes-tech-restore-drill-*")), [])

    def test_cleanup_failure_is_reported_as_failure(self) -> None:
        def fake_decrypt(_identity: Path, archive: Path, output: Path) -> None:
            shutil.copyfile(archive, output)

        with (
            patch.object(restore_drill, "_verify_source_checkout", return_value=self.root / "verifier.py"),
            patch.object(restore_drill, "_run_age_decrypt", side_effect=fake_decrypt),
            patch.object(restore_drill, "_run_hermes_verifier", return_value=self.fake_verifier_report()),
            patch.object(restore_drill.shutil, "rmtree", side_effect=OSError("fixture cleanup failure")),
        ):
            code, report = restore_drill.execute(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "cleanup_failed")
        self.assertFalse(report["cleanup_plaintext_removed"])

    def test_evidence_path_cannot_write_into_production_tree(self) -> None:
        production = self.root / "production-hermes"
        production.mkdir()
        with patch.object(restore_drill, "PRODUCTION_APP", production):
            with self.assertRaisesRegex(restore_drill.DrillError, "production_root_forbidden"):
                restore_drill._evidence_preflight(production / "evidence.json")

    def test_exact_source_checkout_accepts_reviewed_file_and_rejects_dirty_copy(self) -> None:
        source = self.root / "source-checkout"
        script = source / "tools" / "verify_restore_root.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('reviewed')\n", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(["git", "add", "tools/verify_restore_root.py"], cwd=source, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=Restore Test",
                "-c", "user.email=restore@example.invalid",
                "commit", "-q", "-m", "fixture",
            ],
            cwd=source, check=True,
        )
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        resolved = restore_drill._verify_source_checkout(source, sha, "tools/verify_restore_root.py")
        self.assertEqual(resolved, script.resolve())
        script.write_text("print('dirty')\n", encoding="utf-8")
        with self.assertRaisesRegex(restore_drill.DrillError, "source_verification_failed"):
            restore_drill._verify_source_checkout(source, sha, "tools/verify_restore_root.py")

    def test_evidence_is_sanitized(self) -> None:
        secret = "FIXTURE_PRIVATE_VALUE_MUST_NOT_APPEAR"
        self.identity.write_text(secret + "\n", encoding="utf-8")
        os.chmod(self.identity, 0o600)
        write_sidecar(self.archive, digest="0" * 64)
        code, report = restore_drill.execute(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_category"], "sidecar_mismatch")
        evidence = json.loads(self.evidence.read_text(encoding="utf-8"))
        encoded = json.dumps(evidence, sort_keys=True)
        self.assertNotIn(secret, encoded)
        self.assertNotIn(str(self.identity), encoded)
        self.assertNotIn("/home/andris/hermes-tech", encoded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
