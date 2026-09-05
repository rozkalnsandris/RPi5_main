#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import termios

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/provision-hermes-origin-source-app-credential.py"
CREDENTIAL_DIR = Path("/etc/rozkalns-hermes-deals-origin-broker")
CREDENTIAL_PATH = CREDENTIAL_DIR / "source-github-app.pem"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
BODY_LINE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _pem_boundary(action: str, key_kind: str = "") -> str:
    dashes = "-" * 5
    kind = f"{key_kind} " if key_kind else ""
    return f"{dashes}{action} {kind}" + "PRIVATE " + "KEY" + dashes


RSA_BEGIN = _pem_boundary("BEGIN", "RSA")
RSA_END = _pem_boundary("END", "RSA")
PKCS8_BEGIN = _pem_boundary("BEGIN")
PKCS8_END = _pem_boundary("END")
BEGIN_TO_END = {
    RSA_BEGIN: RSA_END,
    PKCS8_BEGIN: PKCS8_END,
}
MIN_DER_BYTES = 256
MAX_DER_BYTES = 16384
MAX_PEM_BYTES = 32768
DIR_MODE = 0o700
CREDENTIAL_MODE = 0o600
ROOT_UID = 0
ROOT_GID = 0


class ProvisioningError(RuntimeError):
    pass


def _run_git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("/usr/bin/git", "-C", str(REPO_ROOT), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _require_exact_source(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        raise ProvisioningError("expected SHA must be lowercase 40-character hex")
    head = _run_git("rev-parse", "--verify", "HEAD")
    if head.returncode != 0 or head.stdout.decode("ascii", "strict").strip() != expected_sha:
        raise ProvisioningError("source SHA mismatch")
    tracked = _run_git("show", f"{expected_sha}:{SCRIPT_RELATIVE}")
    if tracked.returncode != 0 or tracked.stdout != Path(__file__).read_bytes():
        raise ProvisioningError("provisioner source differs from exact reviewed SHA")


def _require_secure_directory(path: Path, *, exact_mode: int | None = None) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ProvisioningError(f"required directory is missing: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProvisioningError(f"required directory is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        raise ProvisioningError(f"required directory is not root-owned: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode is not None:
        if mode != exact_mode:
            raise ProvisioningError(f"required directory mode mismatch: {path}")
    elif mode & 0o022:
        raise ProvisioningError(f"required directory is group/world writable: {path}")


def _credential_dir_state() -> bool:
    try:
        CREDENTIAL_DIR.lstat()
    except FileNotFoundError:
        return False
    _require_secure_directory(CREDENTIAL_DIR, exact_mode=DIR_MODE)
    return True


def _require_target_absent() -> None:
    try:
        CREDENTIAL_PATH.lstat()
    except FileNotFoundError:
        return
    raise ProvisioningError(
        "credential target already exists; overwrite/rotation is not authorized"
    )


def validate_pem(value: str) -> bytes:
    if type(value) is not str:
        raise ProvisioningError("credential input has the wrong type")
    try:
        raw = value.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise ProvisioningError("credential PEM must be ASCII") from exc
    if not raw or len(raw) > MAX_PEM_BYTES:
        raise ProvisioningError("credential PEM length is outside reviewed bounds")

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 3:
        raise ProvisioningError("credential PEM is incomplete")

    begin = lines[0]
    expected_end = BEGIN_TO_END.get(begin)
    if expected_end is None or lines[-1] != expected_end:
        raise ProvisioningError("credential PEM boundary is not an accepted private-key form")

    body = lines[1:-1]
    if not body or any(not line or len(line) > 128 for line in body):
        raise ProvisioningError("credential PEM body shape is invalid")
    if any(BODY_LINE.fullmatch(line) is None for line in body):
        raise ProvisioningError("credential PEM body contains invalid characters")

    encoded = "".join(body)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProvisioningError("credential PEM body is not valid base64") from exc
    if not MIN_DER_BYTES <= len(decoded) <= MAX_DER_BYTES:
        raise ProvisioningError("credential private-key payload length is outside reviewed bounds")

    payload = ("\n".join(lines) + "\n").encode("ascii")
    if len(payload) > MAX_PEM_BYTES:
        raise ProvisioningError("credential PEM length is outside reviewed bounds")
    return payload


def _read_hidden_pem_from_tty() -> bytes:
    if not sys.stderr.isatty():
        raise ProvisioningError("credential provisioning requires an interactive TTY")

    try:
        tty = open("/dev/tty", "r+", encoding="ascii", errors="strict", buffering=1)
    except OSError as exc:
        raise ProvisioningError("interactive TTY is unavailable") from exc

    with tty:
        fd = tty.fileno()
        original = termios.tcgetattr(fd)
        hidden = termios.tcgetattr(fd)
        hidden[3] &= ~termios.ECHO
        lines: list[str] = []
        expected_end: str | None = None
        tty.write(
            "Paste the owner-supplied GitHub App private key PEM. "
            "Input is hidden and stops at the PEM end boundary:\n"
        )
        tty.flush()
        termios.tcsetattr(fd, termios.TCSAFLUSH, hidden)
        try:
            while True:
                line = tty.readline()
                if line == "":
                    raise ProvisioningError("credential input ended before a complete PEM")
                line = line.rstrip("\r\n")
                lines.append(line)
                if len(("\n".join(lines)).encode("ascii", "strict")) > MAX_PEM_BYTES:
                    raise ProvisioningError("credential PEM exceeds reviewed size limit")
                if len(lines) == 1:
                    expected_end = BEGIN_TO_END.get(line)
                    if expected_end is None:
                        raise ProvisioningError(
                            "credential PEM boundary is not an accepted private-key form"
                        )
                elif expected_end is not None and line == expected_end:
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, original)
            tty.write("\n")
            tty.flush()

    return validate_pem("\n".join(lines) + "\n")


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise ProvisioningError("credential write made no progress")
        offset += written


def _create_target(payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            raise ProvisioningError("required credential file guard is unavailable")
        flags |= value

    fd = os.open(CREDENTIAL_PATH, flags, CREDENTIAL_MODE)
    try:
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fchmod(fd, CREDENTIAL_MODE)
        _write_all(fd, payload)
        os.fsync(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or stat.S_IMODE(info.st_mode) != CREDENTIAL_MODE
            or info.st_size != len(payload)
        ):
            raise ProvisioningError("credential post-write metadata mismatch")
    finally:
        os.close(fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Provision the fixed Hermes origin GitHub App private-key credential "
            "from hidden interactive TTY input"
        )
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main SHA")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() != ROOT_UID:
        raise ProvisioningError(
            "Hermes source-App credential provisioning requires root owner execution"
        )

    _require_exact_source(args.expected_sha)
    _require_secure_directory(Path("/etc"))
    credential_dir_exists = _credential_dir_state()
    _require_target_absent()

    payload = _read_hidden_pem_from_tty()

    # Final pre-mutation race gate.
    _require_exact_source(args.expected_sha)
    _require_secure_directory(Path("/etc"))
    if credential_dir_exists != _credential_dir_state():
        raise ProvisioningError("credential directory state changed before mutation")
    _require_target_absent()

    # Authorized credential-placement mutation begins here. Any later error is STOP/no retry.
    if not credential_dir_exists:
        os.mkdir(CREDENTIAL_DIR, DIR_MODE)
        os.chown(CREDENTIAL_DIR, ROOT_UID, ROOT_GID)
        os.chmod(CREDENTIAL_DIR, DIR_MODE)
    _create_target(payload)
    del payload

    print(f"HERMES_SOURCE_APP_CREDENTIAL_PROVISION=PASS source_sha={args.expected_sha}")
    print(f"CREDENTIAL_PATH={CREDENTIAL_PATH}")
    print("CREDENTIAL_INPUT=HIDDEN_TTY")
    print("CREDENTIAL_CONTENT_READ_BACK=NO")
    print("CREDENTIAL_OVERWRITE=NO")
    print("GITHUB_API_REQUEST=NO")
    print("APP_PERMISSION_MUTATION=NO")
    print("BROKER_INSTALL_APPLY=NO")
    print("SYSTEMD_MUTATION=NO")
    print("GENUINE_AUDIT=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningError as exc:
        print(
            f"HERMES_SOURCE_APP_CREDENTIAL_PROVISION=STOP reason={exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
