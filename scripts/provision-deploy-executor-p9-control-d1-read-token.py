#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/provision-deploy-executor-p9-control-d1-read-token.py"
ROOT_CONFIG = Path("/root/.config")
CREDENTIAL_DIR = ROOT_CONFIG / "rozkalns-deploy-executor-p9"
CREDENTIAL_PATH = CREDENTIAL_DIR / "control-d1-read-token"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
MIN_TOKEN_BYTES = 20
MAX_TOKEN_BYTES = 4096


class ProvisioningError(RuntimeError):
    pass


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(REPO_ROOT), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _require_exact_source(expected_sha: str) -> None:
    if SHA40_RE.fullmatch(expected_sha) is None:
        raise ProvisioningError("expected SHA must be lowercase 40-character hex")
    head = _git("rev-parse", "--verify", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != expected_sha:
        raise ProvisioningError("source SHA mismatch")
    clean = _git("diff", "--quiet", expected_sha, "--", SCRIPT_RELATIVE)
    if clean.returncode != 0:
        raise ProvisioningError("reviewed provisioning source differs from exact expected SHA")


def _require_root_config_metadata() -> None:
    try:
        info = ROOT_CONFIG.lstat()
    except FileNotFoundError as exc:
        raise ProvisioningError("root config parent is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProvisioningError("root config parent must be a non-symlink directory")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise ProvisioningError("root config parent ownership/mode is unsafe")


def _credential_dir_state() -> bool:
    try:
        info = CREDENTIAL_DIR.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProvisioningError("credential directory must be a non-symlink directory")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ProvisioningError("credential directory ownership/mode mismatch")
    return True


def _require_target_absent() -> None:
    try:
        CREDENTIAL_PATH.lstat()
    except FileNotFoundError:
        return
    raise ProvisioningError("credential target already exists; overwrite/rotation is not authorized")


def validate_token(value: str) -> bytes:
    if type(value) is not str:
        raise ProvisioningError("credential input has the wrong type")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ProvisioningError("credential input is not UTF-8 encodable") from exc
    if not MIN_TOKEN_BYTES <= len(raw) <= MAX_TOKEN_BYTES:
        raise ProvisioningError("credential length is outside reviewed bounds")
    if any(char.isspace() for char in value):
        raise ProvisioningError("credential contains whitespace")
    return raw + b"\n"


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
    fd = os.open(CREDENTIAL_PATH, flags, 0o400)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o400)
        _write_all(fd, payload)
        os.fsync(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o400
            or info.st_size != len(payload)
        ):
            raise ProvisioningError("credential post-write metadata mismatch")
    finally:
        os.close(fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision the fixed P9 Control D1 read credential from hidden TTY input"
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main SHA")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() != 0:
        raise ProvisioningError("P9 Control D1 credential provisioning requires root")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ProvisioningError("credential provisioning requires an interactive TTY")

    _require_exact_source(args.expected_sha)
    _require_root_config_metadata()
    credential_dir_exists = _credential_dir_state()
    _require_target_absent()

    token = getpass.getpass(
        "Enter owner-supplied Control D1 read token (hidden; never paste into chat): "
    )
    payload = validate_token(token)
    del token

    # Final pre-mutation race gate.
    _require_exact_source(args.expected_sha)
    _require_root_config_metadata()
    if credential_dir_exists != _credential_dir_state():
        raise ProvisioningError("credential directory state changed before mutation")
    _require_target_absent()

    # Authorized credential-placement mutation begins here. Any later error is STOP/no retry.
    if not credential_dir_exists:
        os.mkdir(CREDENTIAL_DIR, 0o700)
        os.chown(CREDENTIAL_DIR, 0, 0)
        os.chmod(CREDENTIAL_DIR, 0o700)
    _create_target(payload)
    del payload

    print(f"P9_CONTROL_D1_CREDENTIAL_PROVISION=PASS source_sha={args.expected_sha}")
    print("CREDENTIAL_INPUT=HIDDEN_TTY")
    print("CREDENTIAL_OVERWRITE=NO")
    print("D1_REQUEST=NO")
    print("BASELINE_COLLECTION=NO")
    print("P9_EXECUTION=NO")
    print("STATE_STORE_TOUCHED=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningError as exc:
        print(
            f"P9_CONTROL_D1_CREDENTIAL_PROVISION=STOP reason={exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
