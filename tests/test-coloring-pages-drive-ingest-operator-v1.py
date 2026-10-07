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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/coloring-pages-drive-ingest"
CONTRACT = ROOT / "ops/contracts/coloring-pages-drive-ingest-operator-v1.json"
INSTALLER = ROOT / "scripts/install-coloring-pages-drive-ingest-operator-v1.sh"
HOST_CONTRACT = ROOT / "ops/contracts/simple-deploy-host-v1.json"

IMAGE_DIGEST = "sha256:fe1cbd2fccaecfc536b78c048d3c0baaf3c4b809b8c28c9fb760373525a16b5b"
IMAGE_REF = f"ghcr.io/rozkalnsandris/coloring-pages@{IMAGE_DIGEST}"

LOADER = importlib.machinery.SourceFileLoader(
    "coloring_pages_drive_ingest", str(OPERATOR)
)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
drive_ingest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(drive_ingest)


class ColoringPagesPublishOperatorTests(unittest.TestCase):
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
            "category": "tiere",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
            "source_kind": "chatgpt-generated-png",
            "approval_class": "explicit-owner-chat-approval",
        }

    def valid_manifest_v2(self) -> dict:
        return {
            "schema": "rozkalns.coloring-pages.drive-staging-manifest.v2",
            "id": "kuerbis-gesicht-001",
            "pages": [
                {
                    "index": 1,
                    "file": "kuerbis-gesicht-001-1.png",
                    "sha256": "a" * 64,
                    "size_bytes": 1000000,
                },
                {
                    "index": 2,
                    "file": "kuerbis-gesicht-001-2.png",
                    "sha256": "b" * 64,
                    "size_bytes": 1100000,
                },
            ],
            "title": "Kürbis-Gesicht",
            "character": "",
            "category": "lernen",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
            "source_kind": "chatgpt-generated-png-set",
            "approval_class": "explicit-owner-chat-approval",
        }

    def test_sources_parse(self) -> None:
        compile(self.operator, str(OPERATOR), "exec")
        completed = subprocess.run(
            ["bash", "-n", str(INSTALLER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_contract_is_one_operator_with_direct_immutable_import(self) -> None:
        consumer = self.contract["consumer"]
        self.assertEqual(consumer["image_digest"], IMAGE_DIGEST)
        self.assertEqual(consumer["image_ref"], IMAGE_REF)
        self.assertEqual(
            consumer["importer_entrypoint"],
            "/usr/local/bin/coloring-pages-import",
        )

        import_contract = self.contract["import"]
        self.assertEqual(import_contract["method"], "direct-immutable-container")
        self.assertEqual(import_contract["runtime"], "/usr/bin/docker")
        self.assertEqual(import_contract["image_ref"], IMAGE_REF)
        self.assertEqual(import_contract["pull_policy"], "never")
        self.assertEqual(import_contract["network"], "none")
        self.assertTrue(import_contract["read_only_root"])
        self.assertTrue(import_contract["cap_drop_all"])
        self.assertTrue(import_contract["no_new_privileges"])
        self.assertFalse(import_contract["application_redeploy_required"])

        self.assertNotIn("importer_installed_path", consumer)
        self.assertNotIn("importer_source_blob_sha", consumer)
        self.assertNotIn("exact_git_blob_sha_required", import_contract)

    def test_operator_directly_runs_hardened_importer_container(self) -> None:
        metadata = {
            "id": "aviator-pup-001",
            "title": "Aviator Pup",
            "character": "",
            "category": "tiere",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
        }
        with mock.patch.object(drive_ingest.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="IMPORTED=aviator-pup-001 PAGES=1\n",
            )
            drive_ingest.run_importer(
                [Path("/srv/coloring-pages-content/inbox/aviator-pup-001.png")],
                metadata,
                owner_uid=1000,
                owner_gid=1000,
            )

        argv = run.call_args.args[0]
        self.assertEqual(argv[0:2], ["/usr/bin/docker", "run"])
        for marker in (
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "no-new-privileges:true",
            "--user",
            "1000:1000",
            "--entrypoint",
            "/usr/local/bin/coloring-pages-import",
            IMAGE_REF,
        ):
            self.assertIn(marker, argv)
        self.assertIn(
            "type=bind,src=/srv/coloring-pages-content,dst=/srv/coloring-pages-content",
            argv,
        )

        for obsolete in (
            "IMPORTER_BLOB_SHA",
            "check_importer_identity",
            "hash-object",
            'GIT = "/usr/bin/git"',
        ):
            self.assertNotIn(obsolete, self.operator)

    def test_drive_boundary_is_fixed_and_read_only(self) -> None:
        drive = self.contract["drive"]
        self.assertEqual(drive["remote"], "gdrive")
        self.assertEqual(
            drive["root_folder_id"],
            "1F0pxqoRgtZl7JQVcyvYVZxKvx6eOnytn",
        )
        self.assertEqual(drive["pending_subdirectory"], "pending")
        self.assertEqual(drive["download_command"], "cat")
        self.assertFalse(drive["copyto_allowed"])
        self.assertFalse(drive["fast_list_allowed"])
        self.assertFalse(drive["drive_mutation_allowed"])
        self.assertNotIn("shell=True", self.operator)
        self.assertNotIn("copyto", self.operator)
        self.assertNotIn("--fast-list", self.operator)

    def test_manifest_is_bound_to_owner_identity(self) -> None:
        manifest = self.valid_manifest()
        metadata = drive_ingest.validate_manifest(
            manifest,
            expected_id="aviator-pup-001",
            expected_sha256="a" * 64,
            expected_size=1162127,
        )
        self.assertEqual(metadata["id"], "aviator-pup-001")
        self.assertEqual(metadata["category"], "tiere")

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

        changed = dict(manifest)
        changed["category"] = "rettungshunde"
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest(
                changed,
                expected_id="aviator-pup-001",
                expected_sha256="a" * 64,
                expected_size=1162127,
            )

        self.assertEqual(
            set(self.contract["manifest"]["allowed_category"]),
            {"tiere", "fahrzeuge", "alphabet", "lernen", "figuren", "jahreszeiten"},
        )

    def test_v2_cli_and_manifest_bind_every_ordered_page(self) -> None:
        args = drive_ingest.parse_args(
            [
                "--id",
                "kuerbis-gesicht-001",
                "--expected-page",
                f"1:{'a' * 64}:1000000",
                "--expected-page",
                f"2:{'b' * 64}:1100000",
            ]
        )
        drive_ingest.validate_cli(args)
        pages = drive_ingest.expected_pages_from_args(args)
        self.assertEqual(
            [page["index"] for page in pages],
            [1, 2],
        )
        self.assertEqual(
            [page["file"] for page in pages],
            ["kuerbis-gesicht-001-1.png", "kuerbis-gesicht-001-2.png"],
        )

        metadata = drive_ingest.validate_manifest_v2(
            self.valid_manifest_v2(),
            expected_id="kuerbis-gesicht-001",
            expected_pages=pages,
        )
        self.assertEqual(metadata["category"], "lernen")
        self.assertEqual(metadata["pages"], pages)

        changed = self.valid_manifest_v2()
        changed["pages"][1]["sha256"] = "c" * 64
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_manifest_v2(
                changed,
                expected_id="kuerbis-gesicht-001",
                expected_pages=pages,
            )

        bad_order = drive_ingest.parse_args(
            [
                "--id",
                "kuerbis-gesicht-001",
                "--expected-page",
                f"1:{'a' * 64}:1000000",
                "--expected-page",
                f"3:{'b' * 64}:1100000",
            ]
        )
        with self.assertRaises(drive_ingest.OperatorError):
            drive_ingest.validate_cli(bad_order)

    def test_v2_importer_receives_ordered_pages_once(self) -> None:
        metadata = {
            "id": "kuerbis-gesicht-001",
            "title": "Kürbis-Gesicht",
            "character": "",
            "category": "lernen",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
        }
        paths = [
            Path("/srv/coloring-pages-content/inbox/kuerbis-gesicht-001-1.png"),
            Path("/srv/coloring-pages-content/inbox/kuerbis-gesicht-001-2.png"),
        ]
        with mock.patch.object(drive_ingest.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="IMPORTED=kuerbis-gesicht-001 PAGES=2\n",
            )
            drive_ingest.run_importer(
                paths,
                metadata,
                owner_uid=1000,
                owner_gid=1000,
            )

        argv = run.call_args.args[0]
        image_index = argv.index(IMAGE_REF)
        self.assertEqual(
            argv[image_index + 1 : image_index + 3],
            [str(paths[0]), str(paths[1])],
        )
        self.assertEqual(argv[image_index + 3 : image_index + 5], ["--id", "kuerbis-gesicht-001"])

    def test_v2_catalog_and_public_urls_preserve_page_order(self) -> None:
        metadata = {
            "id": "kuerbis-gesicht-001",
            "title": "Kürbis-Gesicht",
            "character": "",
            "category": "lernen",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
        }
        entry = drive_ingest.expected_catalog_entry_v2(metadata, 2)
        self.assertEqual(entry["preview"], entry["pages"][0]["preview"])
        self.assertEqual(entry["print"], entry["pages"][0]["print"])
        self.assertEqual(
            entry["pages"],
            [
                {
                    "preview": "/media/kuerbis-gesicht-001/preview-1.webp",
                    "print": "/media/kuerbis-gesicht-001/print-1.png",
                },
                {
                    "preview": "/media/kuerbis-gesicht-001/preview-2.webp",
                    "print": "/media/kuerbis-gesicht-001/print-2.png",
                },
            ],
        )
        self.assertEqual(
            drive_ingest.public_urls_v2("kuerbis-gesicht-001", 2),
            [
                "https://coloring.rozkalns.net/catalog.json",
                "https://coloring.rozkalns.net/media/kuerbis-gesicht-001/thumb.webp",
                "https://coloring.rozkalns.net/media/kuerbis-gesicht-001/preview-1.webp",
                "https://coloring.rozkalns.net/media/kuerbis-gesicht-001/print-1.png",
                "https://coloring.rozkalns.net/media/kuerbis-gesicht-001/preview-2.webp",
                "https://coloring.rozkalns.net/media/kuerbis-gesicht-001/print-2.png",
            ],
        )

    def test_v2_contract_keeps_one_operator_and_verifies_all_pages_first(self) -> None:
        self.assertEqual(
            self.contract["consumer"]["source_revision"],
            "6d55dd16c3eb2a303bf963cb5ec2a036f709ba02",
        )
        self.assertIn("--expected-page", self.contract["operator"]["allowed_arguments"])
        self.assertEqual(
            self.contract["manifest"]["multi_page_schema"],
            "rozkalns.coloring-pages.drive-staging-manifest.v2",
        )
        self.assertEqual(self.contract["manifest"]["multi_page"]["minimum_pages"], 2)
        self.assertEqual(self.contract["manifest"]["multi_page"]["maximum_pages"], 12)
        self.assertTrue(self.contract["import"]["ordered_multi_page_sources"])
        self.assertEqual(self.contract["import"]["maximum_pages"], 12)
        self.assertEqual(
            self.contract["idempotency"]["receipt_schema_v2"],
            "rozkalns.rpi5-main.coloring-pages-drive-ingest-receipt.v2",
        )
        download_loop = self.operator.index(
            "for position, (page_name, partial) in enumerate"
        )
        first_inbox_publish = self.operator.index(
            "atomic_move_no_replace(manifest_partial, manifest_final)"
        )
        self.assertLess(download_loop, first_inbox_publish)

    def test_staging_and_publish_remain_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            state = Path(tempdir)
            receipt = state / "receipt.partial"
            drive_ingest.write_json_exclusive(
                receipt,
                {"result": "PASS"},
                owner_uid=os.getuid(),
                owner_gid=os.getgid(),
            )
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            with self.assertRaises(drive_ingest.OperatorError):
                drive_ingest.write_json_exclusive(
                    receipt,
                    {"result": "PASS"},
                    owner_uid=os.getuid(),
                    owner_gid=os.getgid(),
                )

        atomic = self.contract["atomic_publish"]
        self.assertTrue(atomic["same_filesystem_required"])
        self.assertEqual(
            atomic["required_flags"],
            ["--no-target-directory", "--no-clobber"],
        )
        self.assertFalse(self.contract["idempotency"]["automatic_overwrite"])
        self.assertFalse(
            self.contract["idempotency"]["automatic_retry_after_failure"]
        )

    def test_post_import_verification_and_receipt_remain_required(self) -> None:
        required = set(self.contract["post_import_verification"]["required"])
        for proof in (
            "original-source-size-and-sha256-match",
            "catalog-has-exactly-one-matching-entry",
            "public-catalog-http-200",
            "public-thumb-http-200",
            "public-preview-http-200",
        ):
            self.assertIn(proof, required)
        self.assertNotIn("public-source-size-and-sha256-match", required)
        self.assertNotIn("public-source-http-200", required)
        self.assertEqual(
            set(self.contract["post_import_verification"]["current_media_contract"]),
            {
                "print-png-exists",
                "catalog-print-field-points-to-print-png",
                "public-print-png-http-200",
            },
        )
        self.assertEqual(
            set(self.contract["post_import_verification"]["legacy_compatibility"]),
            {
                "public-source-size-and-sha256-match-when-present",
                "public-source-http-200-when-present",
                "legacy-print-catalog-field-only-with-public-source",
            },
        )
        self.assertEqual(
            self.contract["post_import_verification"]["catalog_matching"],
            "required-fields-exact-additive-legacy-fields-tolerated",
        )
        self.assertEqual(
            self.contract["idempotency"]["receipt_schema"],
            "rozkalns.rpi5-main.coloring-pages-drive-ingest-receipt.v1",
        )

    def test_catalog_and_public_urls_support_old_and_new_media_contracts(self) -> None:
        metadata = {
            "id": "aviator-pup-001",
            "title": "Aviator Pup",
            "character": "",
            "category": "tiere",
            "age": "3-6",
            "difficulty": "easy",
            "language": "de",
        }
        current = drive_ingest.expected_catalog_entry(
            metadata,
            legacy_public_source=False,
        )
        self.assertEqual(
            current["print"],
            "/media/aviator-pup-001/print.png",
        )
        self.assertEqual(
            drive_ingest.public_urls(
                "aviator-pup-001",
                legacy_public_source=False,
            ),
            [
                "https://coloring.rozkalns.net/catalog.json",
                "https://coloring.rozkalns.net/media/aviator-pup-001/thumb.webp",
                "https://coloring.rozkalns.net/media/aviator-pup-001/preview.webp",
                "https://coloring.rozkalns.net/media/aviator-pup-001/print.png",
            ],
        )

        additive_legacy = dict(current)
        additive_legacy["legacy-extra"] = "/media/aviator-pup-001/legacy-extra"
        self.assertTrue(
            drive_ingest.catalog_entry_matches(additive_legacy, current)
        )
        changed = dict(additive_legacy)
        changed["title"] = "Different"
        self.assertFalse(
            drive_ingest.catalog_entry_matches(changed, current)
        )

        legacy = drive_ingest.expected_catalog_entry(
            metadata,
            legacy_public_source=True,
        )
        self.assertEqual(
            legacy["print"],
            "/media/aviator-pup-001/source.png",
        )
        self.assertIn(
            "https://coloring.rozkalns.net/media/aviator-pup-001/source.png",
            drive_ingest.public_urls(
                "aviator-pup-001",
                legacy_public_source=True,
            ),
        )

    def test_single_installer_does_not_run_publish_work(self) -> None:
        for marker in (
            "--expected-rpi5-main-sha",
            "/usr/local/bin/coloring-pages-drive-ingest",
            "RCLONE_EXECUTED=false",
            "CONTENT_IMPORTED=false",
            "SYSTEMD_CHANGED=false",
        ):
            self.assertIn(marker, self.installer)
        for forbidden in (
            "rclone config",
            "docker run",
            "docker pull",
            "systemctl ",
            "/etc/sudoers",
        ):
            self.assertNotIn(forbidden, self.installer)

    def test_host_registry_has_only_single_publish_operator_identity(self) -> None:
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
        self.assertEqual(coloring["drive_ingest_image_digest"], IMAGE_DIGEST)
        self.assertFalse(coloring["drive_ingest_mutates_drive"])
        for obsolete in (
            "importer_operator_contract",
            "importer_installed_path",
            "importer_image_digest",
            "importer_consumer_revision",
        ):
            self.assertNotIn(obsolete, coloring)

    def test_obsolete_second_operator_sources_are_removed(self) -> None:
        for relative in (
            "ops/bin/coloring-pages-import",
            "ops/contracts/coloring-pages-importer-operator-v1.json",
            "scripts/install-coloring-pages-importer-operator-v1.sh",
            "tests/test-coloring-pages-importer-operator-v1.py",
            "docs/COLORING_PAGES_IMPORTER_OPERATOR_V1.md",
            ".github/workflows/coloring-pages-importer-operator-source.yml",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
