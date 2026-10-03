from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "ops/bin/coloring-pages-import"
CONTRACT = ROOT / "ops/contracts/coloring-pages-importer-operator-v1.json"
INSTALLER = ROOT / "scripts/install-coloring-pages-importer-operator-v1.sh"
HOST_CONTRACT = ROOT / "ops/contracts/simple-deploy-host-v1.json"

CONSUMER_SHA = "ab8f874f681fb2adb6f18f4a7c8066b44ace443b"
IMAGE_DIGEST = "sha256:5f61560cb674224052bc3ab8ca086c7997930027459f6c2648714d12c60af796"
IMAGE_REF = f"ghcr.io/rozkalnsandris/coloring-pages@{IMAGE_DIGEST}"


class ColoringPagesImporterOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.installer = INSTALLER.read_text(encoding="utf-8")

    def test_shell_sources_parse(self) -> None:
        for path in (WRAPPER, INSTALLER):
            completed = subprocess.run(
                ["bash", "-n", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_contract_freezes_exact_consumer_image_and_entrypoint(self) -> None:
        consumer = self.contract["consumer"]
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.coloring-pages-importer-operator.v1",
        )
        self.assertEqual(self.contract["issue"], 858)
        self.assertEqual(consumer["repository"], "rozkalnsandris/coloring-pages")
        self.assertEqual(consumer["source_sha"], CONSUMER_SHA)
        self.assertEqual(consumer["image_digest"], IMAGE_DIGEST)
        self.assertEqual(consumer["image_ref"], IMAGE_REF)
        self.assertEqual(consumer["entrypoint"], "/usr/local/bin/coloring-pages-import")

    def test_wrapper_uses_only_exact_digest_and_never_auto_pulls(self) -> None:
        self.assertIn(f"CONSUMER_SHA='{CONSUMER_SHA}'", self.wrapper)
        self.assertIn(f"IMAGE_REF='{IMAGE_REF}'", self.wrapper)
        self.assertIn("--pull=never", self.wrapper)
        self.assertNotIn("docker pull", self.wrapper)
        self.assertNotIn("coloring-pages:production", self.wrapper)
        self.assertNotIn("coloring-pages:latest", self.wrapper)

    def test_wrapper_enforces_isolated_one_off_container(self) -> None:
        for marker in (
            "--rm",
            "--network none",
            "--read-only",
            "--tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m",
            "--cap-drop ALL",
            "--security-opt no-new-privileges:true",
            '--user "$(id -u):$(id -g)"',
            '--mount "type=bind,src=$CONTENT_ROOT,dst=$CONTENT_ROOT"',
            '--entrypoint "$ENTRYPOINT"',
            "--env PYTHONDONTWRITEBYTECODE=1",
        ):
            self.assertIn(marker, self.wrapper)

        docker = self.contract["docker"]
        self.assertEqual(docker["pull"], "never")
        self.assertEqual(docker["network"], "none")
        self.assertTrue(docker["read_only_root"])
        self.assertEqual(docker["cap_drop"], ["ALL"])
        self.assertTrue(docker["no_new_privileges"])
        self.assertEqual(
            docker["mounts"],
            [{
                "type": "bind",
                "source": "/srv/coloring-pages-content",
                "target": "/srv/coloring-pages-content",
                "mode": "read-write",
            }],
        )

    def test_wrapper_is_nonroot_and_andris_only(self) -> None:
        for marker in (
            "operator must not run as root",
            '[[ "$(id -un)" == "$OWNER" ]]',
            "operator must run as andris",
        ):
            self.assertIn(marker, self.wrapper)
        operator = self.contract["operator"]
        self.assertEqual(operator["execution_owner"], "andris")
        self.assertFalse(operator["root_execution_allowed"])

    def test_wrapper_requires_bootstrapped_content_store_identity(self) -> None:
        content = self.contract["content"]
        self.assertEqual(content["root"], "/srv/coloring-pages-content")
        self.assertEqual(
            content["source_directory"],
            "/srv/coloring-pages-content/inbox",
        )
        self.assertEqual(
            content["source_scope"],
            "direct-child-regular-nonsymlink-png",
        )
        self.assertEqual(
            content["expected_directory_identity"],
            "andris:andris:0755",
        )
        self.assertEqual(
            content["expected_catalog_identity"],
            "andris:andris:0644",
        )
        for marker in (
            "required directory is missing or unsafe",
            "required directory metadata drifted",
            "catalog is missing or unsafe",
            "catalog metadata drifted",
            "source must be a regular non-symlink file",
            "source must be a direct child of the content inbox",
            "source file name must end in .png",
        ):
            self.assertIn(marker, self.wrapper)

    def test_wrapper_allows_only_reviewed_metadata_options(self) -> None:
        expected = [
            "--id",
            "--title",
            "--character",
            "--category",
            "--age",
            "--difficulty",
            "--language",
        ]
        self.assertEqual(self.contract["allowed_metadata_options"], expected)
        for option in expected:
            self.assertIn(option, self.wrapper)
        self.assertIn("--content-root is fixed by the trusted operator", self.wrapper)
        self.assertIn("unsupported importer argument", self.wrapper)

    def test_installer_is_exact_sha_install_only(self) -> None:
        for marker in (
            "--expected-rpi5-main-sha",
            "RPi5_main checkout does not match authorized SHA",
            "RPi5_main checkout must be on main",
            "RPi5_main checkout must be clean",
            "install -o root -g root -m 0755",
            "/usr/local/bin/coloring-pages-import",
            "DOCKER_EXECUTED=false",
            "CONTENT_MUTATED=false",
            "SYSTEMD_CHANGED=false",
        ):
            self.assertIn(marker, self.installer)
        for forbidden in (
            "git fetch",
            "docker run",
            "docker pull",
            "systemctl ",
            "/srv/coloring-pages-content",
        ):
            self.assertNotIn(forbidden, self.installer)

    def test_host_contract_registers_importer_identity_without_live_authority(self) -> None:
        host = json.loads(HOST_CONTRACT.read_text(encoding="utf-8"))
        targets = {
            item["target_alias"]: item
            for item in host["registry"]["reviewed_targets"]
        }
        coloring = targets["coloring-pages-public-rpi5"]
        self.assertEqual(coloring["importer_operator_issue"], 858)
        self.assertEqual(
            coloring["importer_operator_contract"],
            "ops/contracts/coloring-pages-importer-operator-v1.json",
        )
        self.assertEqual(coloring["importer_consumer_revision"], CONSUMER_SHA)
        self.assertEqual(coloring["importer_image_digest"], IMAGE_DIGEST)
        self.assertEqual(
            coloring["importer_installed_path"],
            "/usr/local/bin/coloring-pages-import",
        )
        self.assertEqual(coloring["importer_execution_owner"], "andris")
        self.assertFalse(coloring["importer_auto_pull"])
        self.assertTrue(
            self.contract["live_authority_required"]["install_operator"]
        )
        self.assertTrue(
            self.contract["live_authority_required"]["production_import"]
        )


if __name__ == "__main__":
    unittest.main()
