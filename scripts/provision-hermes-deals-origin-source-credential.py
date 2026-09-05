#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import termios

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/provision-hermes-deals-origin-source-credential.py"
CREDENTIAL_DIR = Path("/etc/rozkalns-hermes-deals-origin-broker")
CREDENTIAL_PATH = CREDENTIAL_DIR / "source-github-app.pem"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
MIN_PEM_BYTES = 256
MAX_PEM_BYTES = 16 * 1024
ROOT_UID = 0
ROOT_GID = 0
CREDENTIAL_DIR_MODE = 0o700
CREDENTIAL_MODE = 0o600
PEM_ENVELOPES = {
    "-----BEGIN RSA PRIVATE KEY-----": "-----END RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----": "-----END PRIVATE KEY-----",
}
MUTATION_STARTED = False


class ProvisioningError(RuntimeError):
    pass


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(REPO_ROOT), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
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


def _require_secure_directory(path: Path, *, exact_mode: int | None = None) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ProvisioningError(f"required parent directory is missing: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ProvisioningError(f"required parent is not a real directory: {path}")
    if info.st_uid != ROOT_UID or info.st_gid != ROOT_GID:
        raise ProvisioningError(f"required parent ownership drifted: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if exact_mode is None:
        if mode & 0o022:
            raise ProvisioningError(f"required parent is group/world writable: {path}")
    elif mode != exact_mode:
        raise ProvisioningError(f"credential directory mode drifted: {path}")


def _credential_dir_state() -> bool:
    try:
        CREDENTIAL_DIR.lstat()
    except FileNotFoundError:
        return False
    _require_secure_directory(CREDENTIAL_DIR, exact_mode=CREDENTIAL_DIR_MODE)
    return True


def _require_target_absent() -> None:
    try:
        CREDENTIAL_PATH.lstat()
    except FileNotFoundError:
        return
    raise ProvisioningError("credential target already exists; overwrite/rotation is not authorized")


def validate_pem(value: str) -> bytes:
    if type(value) is not str:
        raise ProvisioningError("credential input has the wrong type")
    if "\r" in value or "\x00" in value:
        raise ProvisioningError("credential contains forbidden control characters")
    try:
        raw = value.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise ProvisioningError("credential must be ASCII-armored PEM") from exc
    if not MIN_PEM_BYTES <= len(raw) <= MAX_PEM_BYTES:
        raise ProvisioningError("credential length is outside reviewed PEM bounds")

    lines = value.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 4:
        raise ProvisioningError("credential PEM envelope is incomplete")
    begin = lines[0]
    expected_end = PEM_ENVELOPES.get(begin)
    if expected_end is None or lines[-1] != expected_end:
        raise ProvisioningError("credential PEM envelope is not an accepted private-key form")
    body = lines[1:-1]
    if not body:
        raise ProvisioningError("credential PEM body is empty")
    for line in body:
        if not 1 <= len(line) <= 128 or BASE64_LINE_RE.fullmatch(line) is None:
            raise ProvisioningError("credential PEM body is not canonical base64 text")
    return ("\n".join(lines) + "\n").encode("ascii")


def _read_hidden_multiline_pem() -> str:
    try:
        tty = open("/dev/tty", "r+", encoding="utf-8", newline="")
    except OSError as exc:
        raise ProvisioningError("credential provisioning requires an interactive TTY") from exc
    with tty:
        if not tty.isatty():
            raise ProvisioningError("credential provisioning requires an interactive TTY")
        fd = tty.fileno()
        previous = termios.tcgetattr(fd)
        hidden = list(previous)
        hidden[3] &= ~termios.ECHO
        tty.write(
            "Paste the owner-supplied GitHub App private key (input hidden).\n"
            "Enter a single dot (.) on its own line to finish.\n"
        )
        tty.flush()
        lines: list[str] = []
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, hidden)
            while True:
                line = tty.readline()
                if line == "":
                    raise ProvisioningError("credential input ended before the terminator")
                line = line.rstrip("\r\n")
                if line == ".":
                    break
                lines.append(line)
                if sum(len(item) + 1 for item in lines) > MAX_PEM_BYTES:
                    raise ProvisioningError("credential input exceeds reviewed PEM bounds")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)
            tty.write("\n")
            tty.flush()
    return "\n".join(lines) + "\n"


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise ProvisioningError("credential write made no progress")
        offset += written


def _create_credential(payload: bytes) -> None:
    global MUTATION_STARTED
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            raise ProvisioningError("required credential file guard is unavailable")
        flags |= value
    MUTATION_STARTED = True
    try:
        fd = os.open(CREDENTIAL_PATH, flags, CREDENTIAL_MODE)
    except OSError as exc:
        raise ProvisioningError("credential file creation failed after mutation entry; STOP") from exc
    try:
        try:
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fchmod(fd, CREDENTIAL_MODE)
            _write_all(fd, payload)
            os.fsync(fd)
            info = os.fstat(fd)
        except OSError as exc:
            raise ProvisioningError("credential file materialization failed after mutation entry; STOP") from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or stat.S_IMODE(info.st_mode) != CREDENTIAL_MODE
            or info.st_size != len(payload)
        ):
            raise ProvisioningError("credential post-write metadata mismatch after mutation entry; STOP")
    finally:
        os.close(fd)


def _create_credential_directory() -> None:
    global MUTATION_STARTED
    MUTATION_STARTED = True
    try:
        os.mkdir(CREDENTIAL_DIR, CREDENTIAL_DIR_MODE)
        os.chown(CREDENTIAL_DIR, ROOT_UID, ROOT_GID)
        os.chmod(CREDENTIAL_DIR, CREDENTIAL_DIR_MODE)
    except OSError as exc:
        raise ProvisioningError("credential directory creation failed after mutation entry; STOP") from exc


def _receipt(*, result: str, source_sha: str, mutation_started: bool, reason: str | None = None) -> str:
    value: dict[str, object] = {
        "schema": "rozkalns.hermes-deals.origin-source-credential-provision.v1",
        "result": result,
        "source_sha": source_sha,
        "credential_target": str(CREDENTIAL_PATH),
        "credential_owner": "root",
        "credential_group": "root",
        "credential_mode": "0600",
        "credential_input": "HIDDEN_TTY_MULTILINE",
        "credential_content_emitted": False,
        "credential_overwrite": False,
        "credential_rotation": False,
        "github_api_request": False,
        "permission_mutation": False,
        "broker_install": False,
        "helper_executed": False,
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_rollback": False,
        "automatic_cleanup": False,
        "mutation_started": mutation_started,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="First-install-only Hermes source GitHub App credential provisioner"
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main SHA")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() != ROOT_UID:
        raise ProvisioningError("Hermes source credential provisioning requires root")

    _require_exact_source(args.expected_sha)
    _require_secure_directory(Path("/etc"))
    credential_dir_exists = _credential_dir_state()
    _require_target_absent()

    secret = _read_hidden_multiline_pem()
    payload = validate_pem(secret)
    del secret

    # Final fail-closed race gate immediately before the first authorized mutation.
    _require_exact_source(args.expected_sha)
    _require_secure_directory(Path("/etc"))
    if credential_dir_exists != _credential_dir_state():
        raise ProvisioningError("credential directory state changed before mutation")
    _require_target_absent()

    if not credential_dir_exists:
        _create_credential_directory()
        _require_secure_directory(CREDENTIAL_DIR, exact_mode=CREDENTIAL_DIR_MODE)
    _create_credential(payload)
    del payload

    print(
        _receipt(
            result="HERMES_SOURCE_CREDENTIAL_PROVISIONED",
            source_sha=args.expected_sha,
            mutation_started=MUTATION_STARTED,
        )
    )
    return 0


if __name__ == "__main__":
    source_sha = sys.argv[1] if len(sys.argv) > 1 else "UNRESOLVED"
    try:
        raise SystemExit(main())
    except ProvisioningError as exc:
        print(
            _receipt(
                result="FAIL_CLOSED",
                source_sha=source_sha,
                mutation_started=MUTATION_STARTED,
                reason=str(exc),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
