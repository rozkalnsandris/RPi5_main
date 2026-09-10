from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision-hermes-origin-source-app-credential.py"

spec = importlib.util.spec_from_file_location("hermes_source_app_provisioner", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load Hermes source-App provisioner")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _pem(begin: str, end: str, *, size: int = 512) -> str:
    encoded = base64.b64encode(b"\x30" * size).decode("ascii")
    body = "\n".join(textwrap.wrap(encoded, 64))
    return f"{begin}\n{body}\n{end}\n"


class HermesSourceAppCredentialProvisionerTests(unittest.TestCase):
    def test_contract_is_fixed_to_reviewed_path_and_metadata(self):
        self.assertEqual(
            module.CREDENTIAL_PATH,
            Path("/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem"),
        )
        self.assertEqual(module.CREDENTIAL_DIR, module.CREDENTIAL_PATH.parent)
        self.assertEqual(module.DIR_MODE, 0o700)
        self.assertEqual(module.CREDENTIAL_MODE, 0o600)
        self.assertEqual(module.ROOT_UID, 0)
        self.assertEqual(module.ROOT_GID, 0)
        self.assertEqual(
            module.SCRIPT_RELATIVE,
            "scripts/provision-hermes-origin-source-app-credential.py",
        )

    def test_runtime_boundaries_cover_rsa_and_pkcs8_forms(self):
        self.assertEqual(module.BEGIN_TO_END[module.RSA_BEGIN], module.RSA_END)
        self.assertEqual(module.BEGIN_TO_END[module.PKCS8_BEGIN], module.PKCS8_END)
        self.assertNotEqual(module.RSA_BEGIN, module.PKCS8_BEGIN)

    def test_accepts_rsa_private_key_pem_and_normalizes_one_trailing_newline(self):
        value = _pem(module.RSA_BEGIN, module.RSA_END)
        payload = module.validate_pem(value)
        self.assertEqual(payload, value.encode("ascii"))
        self.assertTrue(payload.endswith(b"\n"))

    def test_accepts_pkcs8_private_key_pem(self):
        value = _pem(module.PKCS8_BEGIN, module.PKCS8_END)
        self.assertEqual(module.validate_pem(value), value.encode("ascii"))

    def test_rejects_mismatched_private_key_boundaries(self):
        value = _pem(module.RSA_BEGIN, module.PKCS8_END)
        with self.assertRaisesRegex(module.ProvisioningError, "boundary"):
            module.validate_pem(value)

    def test_rejects_non_base64_body(self):
        value = (
            module.PKCS8_BEGIN
            + "\n"
            + ("A" * 64)
            + "!\n"
            + module.PKCS8_END
            + "\n"
        )
        with self.assertRaisesRegex(module.ProvisioningError, "invalid characters"):
            module.validate_pem(value)

    def test_rejects_payload_outside_reviewed_der_bounds(self):
        value = _pem(module.PKCS8_BEGIN, module.PKCS8_END, size=32)
        with self.assertRaisesRegex(module.ProvisioningError, "payload length"):
            module.validate_pem(value)

    def test_rejects_blank_body_lines(self):
        value = _pem(module.PKCS8_BEGIN, module.PKCS8_END).replace("\n", "\n\n", 1)
        with self.assertRaisesRegex(module.ProvisioningError, "body shape"):
            module.validate_pem(value)

    def test_source_has_no_credential_readback_path(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("CREDENTIAL_PATH.read_", source)
        self.assertNotIn("open(CREDENTIAL_PATH, \"r", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("CREDENTIAL_CONTENT_READ_BACK=NO", source)
        self.assertIn("APP_PERMISSION_MUTATION=NO", source)


if __name__ == "__main__":
    unittest.main()
