#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import getpass
import http.client
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/replace-deploy-executor-p9-control-d1-read-token.py"

ROOT_CONFIG = Path("/root/.config")
CREDENTIAL_DIR = ROOT_CONFIG / "rozkalns-deploy-executor-p9"
CREDENTIAL_PATH = CREDENTIAL_DIR / "control-d1-read-token"

ACCOUNT_ID = "70e29dbca0e8363358659102d2b74178"
API_HOST = "api.cloudflare.com"
VERIFY_PATH = f"/client/v4/accounts/{ACCOUNT_ID}/tokens/verify"
TOKEN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

MIN_TOKEN_BYTES = 20
MAX_TOKEN_BYTES = 4096
MAX_VERIFY_RESPONSE_BYTES = 64 * 1024


class ReplacementError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialSnapshot:
    dev: int
    ino: int
    uid: int
    gid: int
    mode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class VerifiedToken:
    token_id: str
    status: str


VerifyRequester = Callable[[str], tuple[int, bytes]]


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
        raise ReplacementError("expected SHA must be lowercase 40-character hex")
    head = _git("rev-parse", "--verify", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != expected_sha:
        raise ReplacementError("source SHA mismatch")
    clean = _git("diff", "--quiet", expected_sha, "--", SCRIPT_RELATIVE)
    if clean.returncode != 0:
        raise ReplacementError(
            "reviewed replacement source differs from exact expected SHA"
        )


def _validate_expected_token_id(value: str) -> str:
    if type(value) is not str or TOKEN_ID_RE.fullmatch(value) is None:
        raise ReplacementError("expected token ID must be lowercase 32-character hex")
    return value


def validate_token(value: str) -> bytes:
    if type(value) is not str:
        raise ReplacementError("credential input has the wrong type")
    try:
        raw = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ReplacementError("credential input is not UTF-8 encodable") from exc
    if not MIN_TOKEN_BYTES <= len(raw) <= MAX_TOKEN_BYTES:
        raise ReplacementError("credential length is outside reviewed bounds")
    if any(char.isspace() for char in value):
        raise ReplacementError("credential contains whitespace")
    return raw + b"\n"


def _require_root_config_metadata() -> None:
    try:
        info = ROOT_CONFIG.lstat()
    except FileNotFoundError as exc:
        raise ReplacementError("root config parent is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReplacementError("root config parent must be a non-symlink directory")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise ReplacementError("root config parent ownership/mode is unsafe")


def _require_credential_dir_metadata() -> None:
    try:
        info = CREDENTIAL_DIR.lstat()
    except FileNotFoundError as exc:
        raise ReplacementError("credential directory is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReplacementError("credential directory must be a non-symlink directory")
    if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ReplacementError("credential directory ownership/mode mismatch")


def _snapshot_from_stat(info: os.stat_result) -> CredentialSnapshot:
    return CredentialSnapshot(
        dev=info.st_dev,
        ino=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
    )


def _credential_prestate() -> CredentialSnapshot:
    _require_root_config_metadata()
    _require_credential_dir_metadata()
    try:
        info = CREDENTIAL_PATH.lstat()
    except FileNotFoundError as exc:
        raise ReplacementError("credential target is missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ReplacementError("credential target must be a regular non-symlink file")
    snapshot = _snapshot_from_stat(info)
    if (snapshot.uid, snapshot.gid, snapshot.mode) != (0, 0, 0o400):
        raise ReplacementError("credential target ownership/mode mismatch")
    if not (MIN_TOKEN_BYTES + 1) <= snapshot.size <= (MAX_TOKEN_BYTES + 1):
        raise ReplacementError("credential target size is outside reviewed bounds")
    return snapshot


def _require_credential_unchanged(expected: CredentialSnapshot) -> None:
    current = _credential_prestate()
    if current != expected:
        raise ReplacementError("credential target changed before replacement")


def _default_verify_requester(token: str) -> tuple[int, bytes]:
    connection = http.client.HTTPSConnection(API_HOST, timeout=20)
    try:
        connection.request(
            "GET",
            VERIFY_PATH,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "rozkalns-deploy-executor-p9-d1-credential-replacement/1",
            },
        )
        response = connection.getresponse()
        raw = response.read(MAX_VERIFY_RESPONSE_BYTES + 1)
        if len(raw) > MAX_VERIFY_RESPONSE_BYTES:
            raise ReplacementError("token_verify_response_too_large")
        return int(response.status), raw
    except ReplacementError:
        raise
    except (OSError, TimeoutError, http.client.HTTPException):
        raise ReplacementError("token_verify_request") from None
    finally:
        connection.close()


def verify_candidate_token(
    token: str,
    expected_token_id: str,
    *,
    requester: VerifyRequester | None = None,
) -> VerifiedToken:
    expected_token_id = _validate_expected_token_id(expected_token_id)
    status, raw = (requester or _default_verify_requester)(token)
    if status != 200:
        raise ReplacementError("token_verify_status")
    if len(raw) > MAX_VERIFY_RESPONSE_BYTES:
        raise ReplacementError("token_verify_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReplacementError("token_verify_payload") from None
    if type(payload) is not dict or payload.get("success") is not True:
        raise ReplacementError("token_verify_payload")
    result = payload.get("result")
    if type(result) is not dict:
        raise ReplacementError("token_verify_payload")
    token_id = result.get("id")
    token_status = result.get("status")
    if (
        type(token_id) is not str
        or TOKEN_ID_RE.fullmatch(token_id) is None
        or token_id != expected_token_id
    ):
        raise ReplacementError("token_verify_identity")
    if token_status != "active":
        raise ReplacementError("token_verify_state")
    return VerifiedToken(token_id=token_id, status=token_status)


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise ReplacementError("credential write made no progress")
        offset += written


def _replace_target(payload: bytes, expected: CredentialSnapshot) -> None:
    flags = os.O_WRONLY
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            raise ReplacementError("required credential file guard is unavailable")
        flags |= value

    try:
        fd = os.open(CREDENTIAL_PATH, flags)
    except OSError:
        raise ReplacementError("unable to open credential target for replacement") from None

    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ReplacementError("opened credential target is not regular")
        opened_snapshot = _snapshot_from_stat(opened)
        if opened_snapshot != expected:
            raise ReplacementError("opened credential target changed before replacement")

        path_now = CREDENTIAL_PATH.lstat()
        if _snapshot_from_stat(path_now) != expected:
            raise ReplacementError("credential target path changed before replacement")

        # Authorized one-target credential mutation begins at the first ftruncate.
        os.ftruncate(fd, 0)
        _write_all(fd, payload)
        os.fsync(fd)

        after = os.fstat(fd)
        if (
            not stat.S_ISREG(after.st_mode)
            or after.st_uid != 0
            or after.st_gid != 0
            or stat.S_IMODE(after.st_mode) != 0o400
            or after.st_size != len(payload)
            or (after.st_dev, after.st_ino) != (expected.dev, expected.ino)
        ):
            raise ReplacementError("credential post-write metadata mismatch")

        path_after = CREDENTIAL_PATH.lstat()
        if (path_after.st_dev, path_after.st_ino) != (expected.dev, expected.ino):
            raise ReplacementError("credential target path changed during replacement")
        if (
            path_after.st_uid != 0
            or path_after.st_gid != 0
            or stat.S_IMODE(path_after.st_mode) != 0o400
            or path_after.st_size != len(payload)
        ):
            raise ReplacementError("credential path post-write metadata mismatch")
    finally:
        os.close(fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace the fixed P9 Control D1 credential after an exact account-owned "
            "token identity proof"
        )
    )
    parser.add_argument("expected_sha", help="exact reviewed RPi5_main SHA")
    parser.add_argument(
        "expected_token_id",
        help="public-safe 32-character Cloudflare Account API token ID",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_token_id = _validate_expected_token_id(args.expected_token_id)

    if os.geteuid() != 0:
        raise ReplacementError("P9 Control D1 credential replacement requires root")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ReplacementError("credential replacement requires an interactive TTY")

    _require_exact_source(args.expected_sha)
    prestate = _credential_prestate()

    candidate = getpass.getpass(
        "Enter owner-created exact-account D1 Read token "
        "(hidden; never paste into chat): "
    )
    payload = validate_token(candidate)

    # Final pre-network race gate. No old credential bytes have been read.
    _require_exact_source(args.expected_sha)
    _require_credential_unchanged(prestate)

    print(
        "PRE_NETWORK_GATE=PASS "
        f"source_sha={args.expected_sha} "
        f"account_id={ACCOUNT_ID} "
        f"expected_token_id={expected_token_id}"
    )
    print(
        "AUTHORIZATION_CONSUMED=YES "
        "operation=d1_credential_candidate_token_verify"
    )

    verified = verify_candidate_token(candidate, expected_token_id)
    del candidate

    print(
        "TOKEN_VERIFY=PASS "
        f"account_id={ACCOUNT_ID} "
        f"token_id={verified.token_id} "
        f"status={verified.status}"
    )

    # Final pre-mutation race gate after the consumed credential-use operation.
    _require_exact_source(args.expected_sha)
    _require_credential_unchanged(prestate)

    _replace_target(payload, prestate)
    del payload

    print(
        "P9_CONTROL_D1_CREDENTIAL_REPLACEMENT=PASS "
        f"source_sha={args.expected_sha} "
        f"account_id={ACCOUNT_ID} "
        f"token_id={verified.token_id}"
    )
    print("CREDENTIAL_INPUT=HIDDEN_TTY")
    print("OLD_CREDENTIAL_CONTENT_READ=NO")
    print("TOKEN_VERIFY_REQUEST=YES")
    print("D1_REQUEST=NO")
    print("CLOUDFLARE_PERMISSION_MUTATION=NO")
    print("BASELINE_COLLECTION=NO")
    print("P9_EXECUTION=NO")
    print("STATE_STORE_TOUCHED=NO")
    print("ROLLBACK_PATH=NO")
    print("RETRY_PATH=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplacementError as exc:
        print(
            f"P9_CONTROL_D1_CREDENTIAL_REPLACEMENT=STOP stage={exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except Exception:
        print(
            "P9_CONTROL_D1_CREDENTIAL_REPLACEMENT=STOP stage=unexpected_failure",
            file=sys.stderr,
        )
        raise SystemExit(1)
