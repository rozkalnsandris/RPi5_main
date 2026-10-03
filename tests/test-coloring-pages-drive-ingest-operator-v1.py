#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/coloring-pages-drive-ingest"
CONTRACT = ROOT / "ops/contracts/coloring-pages-drive-ingest-operator-v1.json"
INSTALLER = ROOT / "scripts/install-coloring-pages-drive-ingest-operator-v1.sh"
HOST_CONTRACT = ROOT / "ops/contracts/simple-deploy-host-v1.json"

LOADER = importlib.machinery.SourceFileLoader("coloring_pages_drive_ingest", str(OPERATOR))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
drive_ingest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(drive_ingest)


class ColoringPagesDriveIngestOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.operator = OPERATOR.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.installer = INSTALLER.read_text(encoding="utf-8")

    def valid_manifest(self) -> dict:
        return {
            "schema": "rozkalns.coloring-pages.drive-staging-manifest.v1",
            "id": "aviator-pup-001",
            "sha256": "a" * 64,
            "size_bytes": 1162127,
            "title": "Aviator Pup",
            "character": "",
            "category": "rettungshunde",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
            "source_kind": "chatgpt-generated-png",
            "approval_class": "explicit-owner-chat-approval",
        }

    def test_python_and_installer_sources_parse(self) -> None:
        completed = subprocess.run(
            ["python3", "-c", f"compile(open({str(OPERATOR)!r}).read(), {str(OPERATOR)!r}, 'exec')"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        completed = subprocess.run(
            ["bash", "-n", str(INSTALLER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_contract_fixes_drive_boundary_and_never_mutates_drive(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.coloring-pages-drive-ingest-operator.v1",
        )
        drive = self.contract["drive"]
        self.assertEqual(drive["remote"], "gdrive")
        self.assertEqual(
            drive["root_folder_id"],
            "1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn",
        )
        self.assertEqual(drive["pending_subdirectory"], "pending")
        self.assertEqual(
            drive["config_path"],
            "/home/andris/.config/rclone/rclone.conf",
        )
        self.assertEqual(drive["config_expected_identity"], "root:andris:0600")
        self.assertFalse(drive["config_content_read_or_emit_allowed"])
        self.assertEqual(drive["download_command"], "cat")
        self.assertFalse(drive["copyto_allowed"])
        self.assertFalse(drive["fast_list_allowed"])
        self.assertFalse(drive["drive_mutation_allowed"])

    def test_operator_streams_to_precreated_andris_file_without_shell(self) -> None:
        for marker in (
            "os.O_CREAT | os.O_EXCL",
            "os.O_NOFOLLOW",
            "0o600",
            'rclone_command("cat"',
            "stdout=destination",
            '"--drive-root-folder-id"',
            "rclone_noninteractive_config_flag()",
        ):
            self.assertIn(marker, self.operator)
        self.assertNotIn("shell=True", self.operator)
        self.assertNotIn("copyto", self.operator)
        self.assertNotIn("--fast-list", self.operator)
        self.assertNotIn("chown", self.operator)
        self.assertNotIn("chmod", self.operator)

    def test_rclone_noninteractive_flag_preserves_exact_runtime_behavior(self) -> None:
        expected = "".join(("--ask-", "password", "=false"))
        self.assertEqual(drive_ingest.rclone_noninteractive_config_flag(), expected)
        command = drive_ingest.rclone_command("lsf", "gdrive:")
        self.assertIn(expected, command)
        self.assertEqual(command.count(expected), 1)

    def test_operator_only_stats_root_protected_config(self) -> None:
        self.assertIn(
            'RCLONE_CONFIG = Path("/home/andris/.config/rclone/rclone.conf")',
            self.operator,
        )
        self.assertIn(
            "require_identity(\n        RCLONE_CONFIG,",
            self.operator,
        )
        for forbidden in (
            "RCLONE_CONFIG.read_text",
            "RCLONE_CONFIG.read_bytes",
            "open(RCLONE_CONFIG",
            "rclone config show",
        ):
            self.assertNotIn(forbidden, self.operator)

    def test_manifest_is_bound_to_owner_cli_identity(self) -> None:
        manifest = self.valid_manifest()
        metadata = drive_ingest.validate_manifest(
            manifest,
            expected_id="aviator-pup-001",
            expected_sha256="a" * 64,
            expected_size=1162127,
        )
        self.assertEqual(metadata["id"], "aviator-pup-001")
        self.assertEqual(metadata["title"], "Aviator Pup")
        self.assertEqual(metadata["category"], "rettungshunde")

        changed = dict(manifest)
        changed["sha256"] = "b" * 64
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest(
                changed,
                expected_id="aviator-pup-001",
                expected_sha256="a" * 64,
                expected_size=1162127,
            )

        changed = dict(manifest)
        changed["unexpected"] = True
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest(
                changed,
                expected_id="aviator-pup-001",
                expected_sha256="a" * 64,
                expected_size=1162127,
            )

    def test_manifest_rejects_control_characters_and_unsupported_metadata(self) -> None:
        manifest = self.valid_manifest()
        manifest["title"] = "bad\nname"
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest(
                manifest,
                expected_id="aviator-pup-001",
                expected_sha256="a" * 64,
                expected_size=1162127,
            )

        manifest = self.valid_manifest()
        manifest["language"] = "en"
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest(
                manifest,
                expected_id="aviator-pup-001",
                expected_sha256="a" * 64,
                expected_size=1162127,
            )

    def test_secure_state_writer_creates_0600_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "receipt.partial"
            drive_ingest.write_json_exclusive(
                path,
                {"result": "PASS"},
                owner_uid=os.getuid(),
                owner_gid=os.getgid(),
            )
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(drive_ingest.OperatorError):
                drive_ingest.write_json_exclusive(
                    path,
                    {"result": "PASS"},
                    owner_uid=os.getuid(),
                    owner_gid=os.getgid(),
                )

    def test_atomic_publish_is_same_filesystem_no_copy_no_clobber(self) -> None:
        atomic = self.contract["atomic_publish"]
        self.assertTrue(atomic["same_filesystem_required"])
        self.assertEqual(atomic["command"], "/usr/bin/mv")
        self.assertEqual(
            atomic["required_flags"],
            ["--no-copy", "--no-target-directory", "--no-clobber"],
        )
        for marker in (
            '"--no-copy"',
            '"--no-target-directory"',
            '"--no-clobber"',
            "source.parent.stat().st_dev != destination.parent.stat().st_dev",
        ):
            self.assertIn(marker, self.operator)

    def test_existing_immutable_importer_is_reused_by_exact_identity(self) -> None:
        consumer = self.contract["consumer"]
        self.assertEqual(
            consumer["ingestion_contract_revision"],
            "0f5290c57f68de32b4a20f3baded8126c0a6efa6",
        )
        self.assertEqual(
            consumer["importer_installed_path"],
            "/usr/local/bin/coloring-pages-import",
        )
        self.assertEqual(
            consumer["importer_source_blob_sha"],
            "83f6a25918bb377a407c3fe264b825327172f9e3",
        )
        self.assertIn(
            'IMPORTER = Path("/usr/local/bin/coloring-pages-import")',
            self.operator,
        )
        self.assertIn("GIT, \"hash-object\", str(IMPORTER)", self.operator)
        self.assertNotIn("docker run", self.operator)
        self.assertNotIn("docker pull", self.operator)

    def test_post_import_verification_and_receipt_are_required(self) -> None:
        required = set(self.contract["post_import_verification"]["required"])
        for proof in (
            "original-source-size-and-sha256-match",
            "public-source-size-and-sha256-match",
            "catalog-has-exactly-one-matching-entry",
            "public-catalog-http-200",
            "public-thumb-http-200",
            "public-preview-http-200",
            "public-source-http-200",
            "public-pdf-http-200",
        ):
            self.assertIn(proof, required)
        self.assertEqual(
            self.contract["idempotency"]["receipt_schema"],
            "rozkalns.rpi5-main.coloring-pages-drive-ingest-receipt.v1",
        )
        self.assertFalse(self.contract["idempotency"]["automatic_overwrite"])
        self.assertFalse(
            self.contract["idempotency"]["automatic_retry_after_failure"]
        )

    def test_installer_is_exact_sha_bounded_and_does_not_touch_credentials(self) -> None:
        for marker in (
            "--expected-rpi5-main-sha",
            "RPi5_main checkout does not match authorized SHA",
            "RPi5_main checkout must be on main",
            "RPi5_main checkout must be clean",
            "install -d -o andris -g andris -m 0755",
            "install -o andris -g andris -m 0600 /dev/null",
            "install -o root -g root -m 0755",
            "/usr/local/bin/coloring-pages-drive-ingest",
            "RCLONE_CONFIG_CHANGED=false",
            "SUDOERS_CHANGED=false",
            "RCLONE_EXECUTED=false",
            "CONTENT_IMPORTED=false",
        ):
            self.assertIn(marker, self.installer)
        for forbidden in (
            "rclone config",
            "systemctl ",
            "/etc/sudoers",
            "docker run",
            "docker pull",
        ):
            self.assertNotIn(forbidden, self.installer)

    def test_host_registry_records_drive_ingest_identity_without_live_authority(self) -> None:
        host = json.loads(HOST_CONTRACT.read_text(encoding="utf-8"))
        targets = {
            item["target_alias"]: item
            for item in host["registry"]["reviewed_targets"]
        }
        coloring = targets["coloring-pages-public-rpi5"]
        self.assertEqual(
            coloring["drive_ingest_operator_contract"],
            "ops/contracts/coloring-pages-drive-ingest-operator-v1.json",
        )
        self.assertEqual(
            coloring["drive_ingest_installed_path"],
            "/usr/local/bin/coloring-pages-drive-ingest",
        )
        self.assertEqual(coloring["drive_ingest_execution_owner"], "andris")
        self.assertEqual(coloring["drive_ingest_remote"], "gdrive")
        self.assertEqual(
            coloring["drive_ingest_root_folder_id"],
            "1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn",
        )
        self.assertFalse(coloring["drive_ingest_mutates_drive"])


if __name__ == "__main__":
    unittest.main()
