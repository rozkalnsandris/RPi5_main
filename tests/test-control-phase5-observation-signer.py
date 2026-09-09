from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISIBILITY_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_production_visibility.py"
TRANSPORT_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_observation_transport.py"
SIGNER_PATH = ROOT / "ops/lib/deploy_executor/control_phase5_observation_signer.py"
FIXTURE_PATH = ROOT / "tests/fixtures/control_phase5_production_visibility_cases.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


visibility = load_module("phase5_visibility_signer_test", VISIBILITY_PATH)
transport = load_module("phase5_transport_signer_test", TRANSPORT_PATH)
signer = load_module("phase5_observation_signer_test", SIGNER_PATH)
CASES = json.loads(FIXTURE_PATH.read_text())

TRANSPORT_PROVENANCE = {
    "control_repository": transport.CONTROL_TRANSPORT_REPOSITORY,
    "control_main_sha": transport.CONTROL_TRANSPORT_MAIN_SHA,
    "control_path": transport.CONTROL_TRANSPORT_PATH,
    "control_blob_sha": transport.CONTROL_TRANSPORT_BLOB_SHA,
    "contract_mode": transport.CONTROL_TRANSPORT_CONTRACT_MODE,
}
DELIVERY_ID = "123e4567-e89b-42d3-a456-426614174000"
SENT_AT = "2026-09-08T18:00:00.000Z"
KEY_ID = "rpi5.prod:2026-09_key"


def normalized_visibility():
    return visibility.normalize_production_visibility(
        CASES["valid"],
        expected_project_id="rpi5-main",
        expected_repository="rozkalnsandris/RPi5_main",
        expected_main_sha="504239fb8f98b6785c4aeb6d55681a6c4fdf1399",
        now_iso="2026-09-08T18:04:00.000Z",
        provenance={
            "consumer_repository": visibility.CONTROL_CONSUMER_REPOSITORY,
            "consumer_main_sha": visibility.CONTROL_CONSUMER_MAIN_SHA,
            "consumer_path": visibility.CONTROL_CONSUMER_PATH,
            "consumer_blob_sha": visibility.CONTROL_CONSUMER_BLOB_SHA,
            "contract_mode": "SOURCE_ONLY_NO_OBSERVATION_AUTHORITY",
        },
    )


def run_openssl(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [signer.OPENSSL_BINARY, *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env={"LC_ALL": "C"},
    )


def generate_key(path: Path, algorithm: str = "ED25519") -> None:
    args = ["genpkey", "-algorithm", algorithm]
    if algorithm == "RSA":
        args.extend(["-pkeyopt", "rsa_keygen_bits:2048"])
    args.extend(["-out", str(path)])
    result = run_openssl(args)
    if result.returncode != 0:
        raise AssertionError("fixture key generation failed")
    path.chmod(0o600)


def make_credentials_directory(root: Path) -> Path:
    root.chmod(0o700)
    generate_key(root / signer.PRIVATE_KEY_CREDENTIAL)
    return root


def signer_error(code: str):
    def check(error: BaseException) -> bool:
        return isinstance(error, signer.Phase5ObservationSignerError) and error.code == code

    return check


class ControlPhase5ObservationSignerTests(unittest.TestCase):
    def test_signs_existing_transport_bytes_and_exports_public_receipt(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = make_credentials_directory(Path(raw_directory))
            credential_signer = signer.load_phase5_observation_signer(
                key_id=KEY_ID,
                environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
            )
            delivery = transport.build_signed_rpi5_observation_delivery(
                normalized_visibility(),
                delivery_id=DELIVERY_ID,
                sent_at=SENT_AT,
                key_id=credential_signer.key_id,
                signer=credential_signer,
                transport_provenance=TRANSPORT_PROVENANCE,
            )

            receipt = credential_signer.verification_key_receipt()
            self.assertEqual(set(receipt), {"keyId", "publicKeyBase64url"})
            self.assertEqual(receipt["keyId"], KEY_ID)
            self.assertRegex(receipt["publicKeyBase64url"], r"^[A-Za-z0-9_-]{43}$")
            self.assertNotIn("=", receipt["publicKeyBase64url"])
            public_key = base64.urlsafe_b64decode(receipt["publicKeyBase64url"] + "=")
            self.assertEqual(len(public_key), 32)

            signing_input = transport.build_rpi5_observation_signing_input(
                delivery_id=delivery.metadata["deliveryId"],
                sent_at=delivery.metadata["sentAt"],
                key_id=delivery.metadata["keyId"],
                payload=delivery.payload,
            )
            signature = base64.urlsafe_b64decode(delivery.metadata["signature"] + "==")
            public_der = directory / "fixture-public.der"
            signing_file = directory / "fixture-signing-input.bin"
            signature_file = directory / "fixture-signature.bin"
            public_der.write_bytes(signer.ED25519_SPKI_PREFIX + public_key)
            signing_file.write_bytes(signing_input)
            signature_file.write_bytes(signature)

            verified = run_openssl(
                [
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-keyform",
                    "DER",
                    "-inkey",
                    str(public_der),
                    "-in",
                    str(signing_file),
                    "-sigfile",
                    str(signature_file),
                ]
            )
            self.assertEqual(verified.returncode, 0, verified.stderr.decode("utf-8", "replace"))
            self.assertEqual(len(signature), 64)
            self.assertEqual(delivery.metadata["keyId"], KEY_ID)

    def test_key_id_validation_is_exact_and_precedes_credential_access(self):
        for bad_key_id in ("", "bad key", "../bad", "a" * 65, "rpi5/invalid"):
            with self.subTest(key_id=bad_key_id):
                with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                    signer.load_phase5_observation_signer(key_id=bad_key_id, environ={})
                self.assertEqual(caught.exception.code, "INVALID_KEY_ID")
                self.assertEqual(str(caught.exception), "phase5 observation signer failed closed")

    def test_credential_boundary_rejects_missing_relative_and_insecure_sources(self):
        with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
            signer.load_phase5_observation_signer(key_id=KEY_ID, environ={})
        self.assertEqual(caught.exception.code, "CREDENTIAL_BOUNDARY_INVALID")

        with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
            signer.load_phase5_observation_signer(
                key_id=KEY_ID,
                environ={signer.CREDENTIALS_DIRECTORY_ENV: "relative/credentials"},
            )
        self.assertEqual(caught.exception.code, "CREDENTIAL_BOUNDARY_INVALID")

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "CREDENTIAL_MISSING")

            key_path = directory / signer.PRIVATE_KEY_CREDENTIAL
            generate_key(key_path)
            key_path.chmod(0o644)
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "CREDENTIAL_INSECURE")

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            target = directory / "fixture-target.pem"
            generate_key(target)
            (directory / signer.PRIVATE_KEY_CREDENTIAL).symlink_to(target.name)
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "CREDENTIAL_INSECURE")

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = make_credentials_directory(Path(raw_directory))
            directory.chmod(0o755)
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "CREDENTIAL_BOUNDARY_INVALID")

    def test_malformed_and_non_ed25519_keys_fail_without_secret_leakage(self):
        marker = "temporary-fixture-private-marker"
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            key_path = directory / signer.PRIVATE_KEY_CREDENTIAL
            key_path.write_text(marker, encoding="utf-8")
            key_path.chmod(0o600)
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "INVALID_KEY")
            self.assertNotIn(marker, str(caught.exception))
            self.assertNotIn(marker, repr(caught.exception))

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            generate_key(directory / signer.PRIVATE_KEY_CREDENTIAL, algorithm="RSA")
            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                signer.load_phase5_observation_signer(
                    key_id=KEY_ID,
                    environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
                )
            self.assertEqual(caught.exception.code, "INVALID_KEY")
            self.assertEqual(str(caught.exception), "phase5 observation signer failed closed")

    def test_signer_refuses_other_domain_or_key_id(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = make_credentials_directory(Path(raw_directory))
            credential_signer = signer.load_phase5_observation_signer(
                key_id=KEY_ID,
                environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
            )
            payload = b"{}"
            valid = transport.build_rpi5_observation_signing_input(
                delivery_id=DELIVERY_ID,
                sent_at=SENT_AT,
                key_id=KEY_ID,
                payload=payload,
            )
            self.assertEqual(len(credential_signer(valid)), 64)

            wrong_key = transport.build_rpi5_observation_signing_input(
                delivery_id=DELIVERY_ID,
                sent_at=SENT_AT,
                key_id="other-key",
                payload=payload,
            )
            for invalid in (wrong_key, b"arbitrary bytes"):
                with self.subTest(invalid=invalid[:16]):
                    with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                        credential_signer(invalid)
                    self.assertEqual(caught.exception.code, "SIGNING_INPUT_INVALID")

    def test_loaded_signer_fails_closed_if_credential_changes(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = make_credentials_directory(Path(raw_directory))
            credential_signer = signer.load_phase5_observation_signer(
                key_id=KEY_ID,
                environ={signer.CREDENTIALS_DIRECTORY_ENV: str(directory)},
            )
            initial = credential_signer.verification_key_receipt()
            replacement = directory / "replacement.pem"
            generate_key(replacement)
            os.replace(replacement, directory / signer.PRIVATE_KEY_CREDENTIAL)

            with self.assertRaises(signer.Phase5ObservationSignerError) as caught:
                credential_signer.verification_key_receipt()
            self.assertEqual(caught.exception.code, "CREDENTIAL_CHANGED")
            self.assertEqual(set(initial), {"keyId", "publicKeyBase64url"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
