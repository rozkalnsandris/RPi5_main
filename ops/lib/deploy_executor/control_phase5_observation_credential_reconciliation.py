from __future__ import annotations

import base64
import os
from pathlib import Path
import stat
import subprocess
from typing import Final

import control_phase5_observation_credential_bootstrap as bootstrap

CONTRACT: Final = "CONTROL_PHASE5_OBSERVATION_CREDENTIAL_RECONCILIATION_V1"
STATUS_RECONCILED: Final = "EXISTING_CREDENTIAL_VALID"
STATUS_FAIL_CLOSED: Final = "FAIL_CLOSED"
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]


def _receipt(*, status: str, public_key: bytes | None = None, error: str | None = None) -> dict[str, object]:
    public_key_text = None
    if public_key is not None:
        if type(public_key) is not bytes or len(public_key) != 32:
            raise ValueError("invalid public key")
        public_key_text = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("ascii")
    value: dict[str, object] = {
        "authorization_consumed": False,
        "contract": CONTRACT,
        "keyId": bootstrap.KEY_ID,
        "mutation_started": False,
        "publicKeyBase64url": public_key_text,
        "status": status,
        "targetClass": bootstrap.TARGET_CLASS,
    }
    if error is not None:
        value["error"] = error
    return value


def public_error_receipt(exc: BaseException) -> dict[str, object]:
    if isinstance(exc, bootstrap.Phase5CredentialBootstrapError):
        code = exc.code
    else:
        code = "UNEXPECTED_ERROR"
    return _receipt(status=STATUS_FAIL_CLOSED, error=code)


def _fail(code: str, state: bootstrap._OperationState) -> None:
    bootstrap._fail(code, state)


def _validate_read_capabilities(state: bootstrap._OperationState) -> None:
    if not getattr(os, "O_NOFOLLOW", 0):
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    if os.stat not in os.supports_follow_symlinks:
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    if not os.path.isdir("/proc/self/fd"):
        _fail("PLATFORM_CAPABILITY_MISSING", state)


def _check_key_consistency(key_fd: int, openssl_binary: str, state: bootstrap._OperationState) -> None:
    try:
        os.lseek(key_fd, 0, os.SEEK_SET)
    except OSError:
        _fail("KEY_VALIDATION_FAILED", state)
    result = bootstrap._run_command(
        [
            openssl_binary,
            "pkey",
            "-in",
            f"/proc/self/fd/{key_fd}",
            "-passin",
            "pass:",
            "-check",
            "-noout",
        ],
        state=state,
        pass_fds=(key_fd,),
        stdout_target=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        _fail("KEY_VALIDATION_FAILED", state)


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size")
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _reconcile_at(
    *,
    directory_path: str,
    repo_root: Path,
    approved_source_sha: str,
    expected_uid: int,
    expected_gid: int,
    required_euid: int,
    openssl_binary: str,
    openssl_owner_uid: int,
) -> dict[str, object]:
    state = bootstrap._OperationState()
    if os.geteuid() != required_euid:
        _fail("EXECUTION_IDENTITY_INVALID", state)
    _validate_read_capabilities(state)
    bootstrap._validate_git_provenance(repo_root, approved_source_sha, state)
    bootstrap._validate_openssl_binary(openssl_binary, openssl_owner_uid, state)

    directory_fd = bootstrap._open_safe_directory(directory_path, expected_uid, state)
    key_fd = -1
    try:
        bootstrap._require_absent(directory_fd, bootstrap.STAGING_FILENAME, "STAGING_EXISTS", state)
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            key_fd = os.open(bootstrap.PRIVATE_KEY_FILENAME, flags, dir_fd=directory_fd)
        except FileNotFoundError:
            _fail("TARGET_ABSENT", state)
        except OSError:
            _fail("TARGET_STATE_AMBIGUOUS", state)

        before = bootstrap._verify_key_file(
            key_fd,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            state=state,
        )
        _check_key_consistency(key_fd, openssl_binary, state)
        public_key = bootstrap._derive_public_key(key_fd, openssl_binary, state)
        after_fd = bootstrap._verify_key_file(
            key_fd,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            state=state,
        )
        try:
            after_path = os.stat(
                bootstrap.PRIVATE_KEY_FILENAME,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError:
            _fail("TARGET_STATE_AMBIGUOUS", state)
        if not _same_file_state(before, after_fd) or not _same_file_state(before, after_path):
            _fail("TARGET_CHANGED", state)
        if not stat.S_ISREG(after_path.st_mode):
            _fail("KEY_FILE_INVALID", state)
        bootstrap._require_absent(directory_fd, bootstrap.STAGING_FILENAME, "STAGING_EXISTS", state)
        return _receipt(status=STATUS_RECONCILED, public_key=public_key)
    finally:
        if key_fd >= 0:
            os.close(key_fd)
        os.close(directory_fd)


def reconcile_existing_credential(*, approved_source_sha: str) -> dict[str, object]:
    return _reconcile_at(
        directory_path=bootstrap.CREDSTORE_DIRECTORY,
        repo_root=REPOSITORY_ROOT,
        approved_source_sha=approved_source_sha,
        expected_uid=0,
        expected_gid=0,
        required_euid=0,
        openssl_binary=bootstrap.OPENSSL_BINARY,
        openssl_owner_uid=0,
    )
