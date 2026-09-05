from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/provision-hermes-deals-origin-source-credential.py"
spec = importlib.util.spec_from_file_location("hermes_source_credential_provisioner", SCRIPT)
assert spec is not None and spec.loader is not None
provisioner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = provisioner
spec.loader.exec_module(provisioner)


def fake_pem(begin: str = "-----BEGIN PRIVATE KEY-----", end: str = "-----END PRIVATE KEY-----") -> str:
    body = "\n".join(["A" * 64] * 5)
    return f"{begin}\n{body}\n{end}\n"


class HermesSourceCredentialProvisionerTests(unittest.TestCase):
    def setUp(self) -> None:
        provisioner.MUTATION_STARTED = False

    def test_fixed_target_and_modes_match_runtime_contract(self) -> None:
        self.assertEqual(
            provisioner.CREDENTIAL_DIR,
            Path("/etc/rozkalns-hermes-deals-origin-broker"),
        )
        self.assertEqual(
            provisioner.CREDENTIAL_PATH,
            Path("/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem"),
        )
        self.assertEqual(provisioner.CREDENTIAL_DIR_MODE, 0o700)
        self.assertEqual(provisioner.CREDENTIAL_MODE, 0o600)
        self.assertEqual(provisioner.ROOT_UID, 0)
        self.assertEqual(provisioner.ROOT_GID, 0)

    def test_valid_pkcs8_and_rsa_pem_shapes_are_canonicalized(self) -> None:
        pkcs8 = fake_pem()
        rsa = fake_pem(
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----END RSA PRIVATE KEY-----",
        )
        self.assertEqual(provisioner.validate_pem(pkcs8), pkcs8.encode("ascii"))
        self.assertEqual(provisioner.validate_pem(rsa), rsa.encode("ascii"))

    def test_malformed_or_unsafe_pem_is_rejected(self) -> None:
        bad_values = [
            "short",
            fake_pem(end="-----END RSA PRIVATE KEY-----"),
            fake_pem().replace("A" * 64, "." * 64, 1),
            fake_pem().replace("A" * 64, "Ā" * 64, 1),
            fake_pem().replace("\n", "\r\n", 1),
            fake_pem() + "\x00",
        ]
        for value in bad_values:
            with self.subTest(value=value[:40]):
                with self.assertRaises(provisioner.ProvisioningError):
                    provisioner.validate_pem(value)

    def test_existing_target_fails_closed_without_overwrite(self) -> None:
        old_path = provisioner.CREDENTIAL_PATH
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "source-github-app.pem"
                path.write_text("fixture-never-read", encoding="utf-8")
                provisioner.CREDENTIAL_PATH = path
                with self.assertRaisesRegex(
                    provisioner.ProvisioningError,
                    "overwrite/rotation is not authorized",
                ):
                    provisioner._require_target_absent()
        finally:
            provisioner.CREDENTIAL_PATH = old_path

    def test_symlink_credential_directory_is_rejected(self) -> None:
        old_uid = provisioner.ROOT_UID
        old_gid = provisioner.ROOT_GID
        try:
            provisioner.ROOT_UID = os.getuid()
            provisioner.ROOT_GID = os.getgid()
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                real = root / "real"
                link = root / "link"
                real.mkdir()
                link.symlink_to(real, target_is_directory=True)
                with self.assertRaises(provisioner.ProvisioningError):
                    provisioner._require_secure_directory(link)
        finally:
            provisioner.ROOT_UID = old_uid
            provisioner.ROOT_GID = old_gid

    def test_create_credential_is_exclusive_and_mode_bounded(self) -> None:
        old_path = provisioner.CREDENTIAL_PATH
        old_uid = provisioner.ROOT_UID
        old_gid = provisioner.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "source-github-app.pem"
                provisioner.CREDENTIAL_PATH = path
                provisioner.ROOT_UID = os.getuid()
                provisioner.ROOT_GID = os.getgid()
                payload = fake_pem().encode("ascii")
                with mock.patch.object(provisioner.os, "fchown", return_value=None):
                    provisioner._create_credential(payload)
                info = path.stat()
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
                self.assertEqual(path.read_bytes(), payload)
                self.assertTrue(provisioner.MUTATION_STARTED)
                with self.assertRaises(FileExistsError):
                    with mock.patch.object(provisioner.os, "fchown", return_value=None):
                        provisioner._create_credential(payload)
        finally:
            provisioner.CREDENTIAL_PATH = old_path
            provisioner.ROOT_UID = old_uid
            provisioner.ROOT_GID = old_gid

    def test_public_receipt_never_contains_credential_content(self) -> None:
        secret_marker = "DO-NOT-EMIT-THIS-SECRET"
        receipt = provisioner._receipt(
            result="TEST",
            source_sha="a" * 40,
            mutation_started=False,
            reason="fixture failure",
        )
        value = json.loads(receipt)
        self.assertNotIn(secret_marker, receipt)
        self.assertFalse(value["credential_content_emitted"])
        self.assertFalse(value["credential_overwrite"])
        self.assertFalse(value["credential_rotation"])
        self.assertFalse(value["github_api_request"])
        self.assertFalse(value["permission_mutation"])
        self.assertFalse(value["broker_install"])
        self.assertFalse(value["helper_executed"])
        self.assertFalse(value["systemd_mutation"])
        self.assertFalse(value["automatic_retry"])
        self.assertFalse(value["automatic_rollback"])
        self.assertFalse(value["automatic_cleanup"])

    def test_source_uses_hidden_tty_and_required_exclusive_guards(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('open("/dev/tty", "r+"', source)
        self.assertIn("hidden[3] &= ~termios.ECHO", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn('("O_NOFOLLOW", "O_CLOEXEC")', source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("sys.stdin.read", source)


if __name__ == "__main__":
    unittest.main()
