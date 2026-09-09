from __future__ import annotations

import base64
import os
import re
import stat
import subprocess
from typing import Mapping

OPENSSL_BINARY = "/usr/bin/openssl"
CREDENTIALS_DIRECTORY_ENV = "CREDENTIALS_DIRECTORY"
PRIVATE_KEY_CREDENTIAL = "control-phase5-observation-ed25519.pem"
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
SIGNING_DOMAIN = b"rozkalns-control-center.phase5.rpi5-production-visibility.v1"
TRANSPORT_VERSION = b"control-phase5-rpi5-observation-v1"
MAX_PAYLOAD_BYTES = 16 * 1024
MAX_PRIVATE_KEY_CREDENTIAL_BYTES = 16 * 1024
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


class Phase5ObservationSignerError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("phase5 observation signer failed closed")
        self.code = code


def _fail(code: str) -> None:
    raise Phase5ObservationSignerError(code)


def _require_key_id(value: str) -> str:
    if type(value) is not str or KEY_ID_PATTERN.fullmatch(value) is None:
        _fail("INVALID_KEY_ID")
    return value


def _require_credentials_directory(environ: Mapping[str, str]) -> str:
    try:
        raw = environ.get(CREDENTIALS_DIRECTORY_ENV, "")
    except Exception:
        _fail("CREDENTIAL_BOUNDARY_INVALID")
    if type(raw) is not str or not raw or not os.path.isabs(raw):
        _fail("CREDENTIAL_BOUNDARY_INVALID")
    try:
        absolute = os.path.abspath(raw)
        resolved = os.path.realpath(raw, strict=True)
    except (OSError, RuntimeError):
        _fail("CREDENTIAL_BOUNDARY_INVALID")
    if resolved != absolute:
        _fail("CREDENTIAL_BOUNDARY_INVALID")
    return absolute


def _open_private_key_fd(credentials_directory: str) -> int:
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(credentials_directory, directory_flags)
    except OSError:
        _fail("CREDENTIAL_BOUNDARY_INVALID")
    try:
        directory_stat = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_mode & 0o077:
            _fail("CREDENTIAL_BOUNDARY_INVALID")

        key_flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        try:
            key_fd = os.open(PRIVATE_KEY_CREDENTIAL, key_flags, dir_fd=directory_fd)
        except FileNotFoundError:
            _fail("CREDENTIAL_MISSING")
        except OSError:
            _fail("CREDENTIAL_INSECURE")
    finally:
        os.close(directory_fd)

    key_stat = os.fstat(key_fd)
    if not stat.S_ISREG(key_stat.st_mode) or key_stat.st_mode & 0o077:
        os.close(key_fd)
        _fail("CREDENTIAL_INSECURE")
    if key_stat.st_size <= 0 or key_stat.st_size > MAX_PRIVATE_KEY_CREDENTIAL_BYTES:
        os.close(key_fd)
        _fail("INVALID_KEY")
    return key_fd


def _run_openssl(args: list[str], *, pass_fds: tuple[int, ...]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [OPENSSL_BINARY, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
            pass_fds=pass_fds,
            env={"LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        _fail("OPENSSL_UNAVAILABLE")


def _derive_public_key(key_fd: int) -> bytes:
    result = _run_openssl(
        [
            "pkey",
            "-in",
            f"/proc/self/fd/{key_fd}",
            "-passin",
            "pass:",
            "-pubout",
            "-outform",
            "DER",
        ],
        pass_fds=(key_fd,),
    )
    if result.returncode != 0:
        _fail("INVALID_KEY")
    if len(result.stdout) != len(ED25519_SPKI_PREFIX) + 32:
        _fail("INVALID_KEY")
    if not result.stdout.startswith(ED25519_SPKI_PREFIX):
        _fail("INVALID_KEY")
    return result.stdout[len(ED25519_SPKI_PREFIX) :]


def _require_signing_input(signing_input: bytes, key_id: str) -> bytes:
    if type(signing_input) is not bytes or not signing_input:
        _fail("SIGNING_INPUT_INVALID")
    parts = signing_input.split(b"\n", 6)
    if len(parts) != 7:
        _fail("SIGNING_INPUT_INVALID")
    if parts[0] != SIGNING_DOMAIN or parts[1] != TRANSPORT_VERSION:
        _fail("SIGNING_INPUT_INVALID")
    if parts[4] != key_id.encode("ascii"):
        _fail("SIGNING_INPUT_INVALID")
    payload = parts[6]
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        _fail("SIGNING_INPUT_INVALID")
    if parts[5] != str(len(payload)).encode("ascii"):
        _fail("SIGNING_INPUT_INVALID")
    return signing_input


def _write_all(fd: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            _fail("SIGNING_FAILED")
        view = view[written:]


def _sign_with_key_fd(key_fd: int, signing_input: bytes) -> bytes:
    try:
        input_fd = os.memfd_create(
            "phase5-observation-signing-input",
            flags=getattr(os, "MFD_CLOEXEC", 0),
        )
    except (AttributeError, OSError):
        _fail("SIGNING_FAILED")
    try:
        _write_all(input_fd, signing_input)
        os.lseek(input_fd, 0, os.SEEK_SET)
        result = _run_openssl(
            [
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                f"/proc/self/fd/{key_fd}",
                "-passin",
                "pass:",
                "-in",
                f"/proc/self/fd/{input_fd}",
            ],
            pass_fds=(key_fd, input_fd),
        )
    finally:
        os.close(input_fd)
    if result.returncode != 0:
        _fail("SIGNING_FAILED")
    if len(result.stdout) != 64:
        _fail("INVALID_SIGNATURE")
    return result.stdout


class Phase5ObservationCredentialSigner:
    __slots__ = ("_key_id", "_credentials_directory", "_public_key")

    def __init__(self, key_id: str, credentials_directory: str, public_key: bytes):
        self._key_id = key_id
        self._credentials_directory = credentials_directory
        self._public_key = public_key

    @property
    def key_id(self) -> str:
        return self._key_id

    def _open_current_key(self) -> int:
        key_fd = _open_private_key_fd(self._credentials_directory)
        try:
            current_public_key = _derive_public_key(key_fd)
        except Exception:
            os.close(key_fd)
            raise
        if current_public_key != self._public_key:
            os.close(key_fd)
            _fail("CREDENTIAL_CHANGED")
        return key_fd

    def __call__(self, signing_input: bytes) -> bytes:
        return self.sign(signing_input)

    def sign(self, signing_input: bytes) -> bytes:
        validated = _require_signing_input(signing_input, self._key_id)
        key_fd = self._open_current_key()
        try:
            return _sign_with_key_fd(key_fd, validated)
        finally:
            os.close(key_fd)

    def verification_key_receipt(self) -> dict[str, str]:
        key_fd = self._open_current_key()
        os.close(key_fd)
        public_key_text = (
            base64.urlsafe_b64encode(self._public_key).rstrip(b"=").decode("ascii")
        )
        return {
            "keyId": self._key_id,
            "publicKeyBase64url": public_key_text,
        }


def load_phase5_observation_signer(
    *,
    key_id: str,
    environ: Mapping[str, str] | None = None,
) -> Phase5ObservationCredentialSigner:
    normalized_key_id = _require_key_id(key_id)
    runtime_environ = os.environ if environ is None else environ
    credentials_directory = _require_credentials_directory(runtime_environ)
    key_fd = _open_private_key_fd(credentials_directory)
    try:
        public_key = _derive_public_key(key_fd)
    finally:
        os.close(key_fd)
    return Phase5ObservationCredentialSigner(
        normalized_key_id,
        credentials_directory,
        public_key,
    )
