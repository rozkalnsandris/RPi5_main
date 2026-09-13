from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Final

CONTRACT: Final = "CONTROL_PHASE5_OBSERVATION_CREDENTIAL_BOOTSTRAP_V1"
STATUS_PREFLIGHT_PASS: Final = "PREFLIGHT_PASS"
STATUS_CREATED: Final = "CREATED"
STATUS_FAIL_CLOSED: Final = "FAIL_CLOSED"
TARGET_CLASS: Final = "RPi5_SYSTEM_CREDENTIAL_STORE"
REPOSITORY_IDENTITY: Final = "rozkalnsandris/RPi5_main"
KEY_ID: Final = "rpi5-prod-2026-09"
CREDSTORE_DIRECTORY: Final = "/etc/credstore"
PRIVATE_KEY_FILENAME: Final = "control-phase5-observation-ed25519.pem"
STAGING_FILENAME: Final = ".control-phase5-observation-ed25519.pem.stage-v1"
OPENSSL_BINARY: Final = "/usr/bin/openssl"
GIT_BINARY: Final = "/usr/bin/git"
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
MAX_PRIVATE_KEY_BYTES: Final = 4096
MAX_COMMAND_OUTPUT_BYTES: Final = 1024 * 1024
ED25519_SPKI_PREFIX: Final = bytes.fromhex("302a300506032b6570032100")
SHA_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_ORIGIN_URLS: Final = {
    "https://github.com/rozkalnsandris/RPi5_main",
    "https://github.com/rozkalnsandris/RPi5_main.git",
    "git@github.com:rozkalnsandris/RPi5_main.git",
    "ssh://git@github.com/rozkalnsandris/RPi5_main.git",
}


@dataclass
class _OperationState:
    mutation_started: bool = False
    authorization_consumed: bool = False


class Phase5CredentialBootstrapError(RuntimeError):
    def __init__(self, code: str, *, mutation_started: bool, authorization_consumed: bool):
        super().__init__("phase5 credential bootstrap failed closed")
        self.code = code
        self.mutation_started = mutation_started
        self.authorization_consumed = authorization_consumed


def _fail(code: str, state: _OperationState) -> None:
    raise Phase5CredentialBootstrapError(
        code,
        mutation_started=state.mutation_started,
        authorization_consumed=state.authorization_consumed,
    )


def _receipt(
    *,
    status: str,
    state: _OperationState,
    public_key: bytes | None = None,
    error: str | None = None,
) -> dict[str, object]:
    public_key_text = None
    if public_key is not None:
        if type(public_key) is not bytes or len(public_key) != 32:
            _fail("PUBLIC_KEY_INVALID", state)
        public_key_text = base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("ascii")
    receipt: dict[str, object] = {
        "authorization_consumed": state.authorization_consumed,
        "contract": CONTRACT,
        "keyId": KEY_ID,
        "mutation_started": state.mutation_started,
        "publicKeyBase64url": public_key_text,
        "status": status,
        "targetClass": TARGET_CLASS,
    }
    if error is not None:
        receipt["error"] = error
    return receipt


def public_error_receipt(
    exc: BaseException,
    *,
    state: _OperationState | None = None,
) -> dict[str, object]:
    if isinstance(exc, Phase5CredentialBootstrapError):
        error_code = exc.code
        effective_state = _OperationState(exc.mutation_started, exc.authorization_consumed)
    else:
        error_code = "UNEXPECTED_ERROR"
        effective_state = state if state is not None else _OperationState()
    return _receipt(
        status=STATUS_FAIL_CLOSED,
        state=effective_state,
        error=error_code,
    )


def _run_command(
    argv: list[str],
    *,
    state: _OperationState,
    pass_fds: tuple[int, ...] = (),
    stdout_target: int | None = None,
    timeout: int = 5,
) -> subprocess.CompletedProcess[bytes]:
    stdout: int | object = subprocess.PIPE if stdout_target is None else stdout_target
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
            pass_fds=pass_fds,
            env={"LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        _fail("COMMAND_UNAVAILABLE", state)
    if stdout_target is None and len(result.stdout) > MAX_COMMAND_OUTPUT_BYTES:
        _fail("COMMAND_OUTPUT_OVERSIZED", state)
    return result


def _validate_approved_sha(approved_source_sha: str, state: _OperationState) -> str:
    if type(approved_source_sha) is not str or SHA_PATTERN.fullmatch(approved_source_sha) is None:
        _fail("SOURCE_SHA_INVALID", state)
    return approved_source_sha


def _validate_fixed_executable(
    path: str,
    *,
    expected_owner_uid: int,
    error_code: str,
    state: _OperationState,
) -> None:
    if not os.path.isabs(path):
        _fail(error_code, state)
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        _fail(error_code, state)
    if not stat.S_ISREG(info.st_mode):
        _fail(error_code, state)
    if info.st_uid != expected_owner_uid or info.st_mode & 0o022:
        _fail(error_code, state)
    if not os.access(path, os.X_OK):
        _fail(error_code, state)


def _validate_platform_capabilities(state: _OperationState) -> None:
    if not getattr(os, "O_NOFOLLOW", 0):
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    required_dir_fd = {os.open, os.stat, os.link, os.unlink}
    if not required_dir_fd.issubset(os.supports_dir_fd):
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    if os.link not in os.supports_follow_symlinks or os.stat not in os.supports_follow_symlinks:
        _fail("PLATFORM_CAPABILITY_MISSING", state)
    if not os.path.isdir("/proc/self/fd"):
        _fail("PLATFORM_CAPABILITY_MISSING", state)


def _run_git(repo_root: Path, args: list[str], state: _OperationState) -> bytes:
    result = _run_command(
        [GIT_BINARY, "-C", str(repo_root), *args],
        state=state,
    )
    if result.returncode != 0:
        _fail("SOURCE_PROVENANCE_INVALID", state)
    return result.stdout


def _validate_git_provenance(
    repo_root: Path,
    approved_source_sha: str,
    state: _OperationState,
) -> None:
    approved = _validate_approved_sha(approved_source_sha, state)
    _validate_fixed_executable(
        GIT_BINARY,
        expected_owner_uid=0,
        error_code="GIT_INVALID",
        state=state,
    )
    try:
        root = repo_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("SOURCE_PROVENANCE_INVALID", state)
    if not root.is_dir():
        _fail("SOURCE_PROVENANCE_INVALID", state)

    try:
        top_level = _run_git(root, ["rev-parse", "--show-toplevel"], state).decode(
            "utf-8", "strict"
        ).strip()
        origin = _run_git(root, ["remote", "get-url", "origin"], state).decode(
            "utf-8", "strict"
        ).strip()
        head = _run_git(root, ["rev-parse", "HEAD"], state).decode(
            "ascii", "strict"
        ).strip()
    except UnicodeDecodeError:
        _fail("SOURCE_PROVENANCE_INVALID", state)

    if top_level != str(root):
        _fail("SOURCE_PROVENANCE_INVALID", state)
    if origin not in ALLOWED_ORIGIN_URLS:
        _fail("SOURCE_REPOSITORY_MISMATCH", state)
    if head != approved:
        _fail("SOURCE_SHA_MISMATCH", state)

    tracked_status = _run_git(
        root,
        ["status", "--porcelain=v1", "--untracked-files=no"],
        state,
    )
    if tracked_status:
        _fail("SOURCE_WORKTREE_DIRTY", state)


def _validate_openssl_binary(
    openssl_binary: str,
    expected_owner_uid: int,
    state: _OperationState,
) -> None:
    _validate_fixed_executable(
        openssl_binary,
        expected_owner_uid=expected_owner_uid,
        error_code="OPENSSL_INVALID",
        state=state,
    )
    result = _run_command(
        [openssl_binary, "list", "-public-key-algorithms"],
        state=state,
    )
    if result.returncode != 0 or b"ED25519" not in result.stdout.upper():
        _fail("OPENSSL_ED25519_UNAVAILABLE", state)


def _open_safe_directory(path: str, expected_uid: int, state: _OperationState) -> int:
    if not os.path.isabs(path):
        _fail("CREDSTORE_INVALID", state)
    try:
        absolute = os.path.abspath(path)
        resolved = os.path.realpath(path, strict=True)
    except (OSError, RuntimeError):
        _fail("CREDSTORE_INVALID", state)
    if resolved != absolute:
        _fail("CREDSTORE_INVALID", state)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory_fd = os.open(path, flags)
    except OSError:
        _fail("CREDSTORE_INVALID", state)
    try:
        info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != expected_uid
            or info.st_mode & 0o022
        ):
            _fail("CREDSTORE_INVALID", state)
    except Exception:
        os.close(directory_fd)
        raise
    return directory_fd


def _require_absent(
    directory_fd: int,
    name: str,
    code: str,
    state: _OperationState,
) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        _fail("TARGET_STATE_AMBIGUOUS", state)
    _fail(code, state)


def _validate_preconditions_at(
    *,
    directory_path: str,
    repo_root: Path,
    approved_source_sha: str,
    expected_uid: int,
    expected_gid: int,
    required_euid: int,
    openssl_binary: str,
    openssl_owner_uid: int,
    state: _OperationState,
) -> int:
    if os.geteuid() != required_euid:
        _fail("EXECUTION_IDENTITY_INVALID", state)
    _validate_platform_capabilities(state)
    _validate_git_provenance(repo_root, approved_source_sha, state)
    _validate_openssl_binary(openssl_binary, openssl_owner_uid, state)
    directory_fd = _open_safe_directory(directory_path, expected_uid, state)
    try:
        _require_absent(directory_fd, PRIVATE_KEY_FILENAME, "TARGET_EXISTS", state)
        _require_absent(directory_fd, STAGING_FILENAME, "STAGING_EXISTS", state)
    except Exception:
        os.close(directory_fd)
        raise
    return directory_fd


def _derive_public_key(
    key_fd: int,
    openssl_binary: str,
    state: _OperationState,
) -> bytes:
    try:
        os.lseek(key_fd, 0, os.SEEK_SET)
    except OSError:
        _fail("KEY_VALIDATION_FAILED", state)
    result = _run_command(
        [
            openssl_binary,
            "pkey",
            "-in",
            f"/proc/self/fd/{key_fd}",
            "-passin",
            "pass:",
            "-pubout",
            "-outform",
            "DER",
        ],
        state=state,
        pass_fds=(key_fd,),
    )
    if result.returncode != 0:
        _fail("KEY_VALIDATION_FAILED", state)
    expected_length = len(ED25519_SPKI_PREFIX) + 32
    if (
        len(result.stdout) != expected_length
        or not result.stdout.startswith(ED25519_SPKI_PREFIX)
    ):
        _fail("KEY_TYPE_INVALID", state)
    return result.stdout[len(ED25519_SPKI_PREFIX) :]


def _verify_key_file(
    key_fd: int,
    *,
    expected_uid: int,
    expected_gid: int,
    state: _OperationState,
) -> os.stat_result:
    try:
        info = os.fstat(key_fd)
    except OSError:
        _fail("KEY_VALIDATION_FAILED", state)
    if not stat.S_ISREG(info.st_mode):
        _fail("KEY_FILE_INVALID", state)
    if stat.S_IMODE(info.st_mode) != 0o600:
        _fail("KEY_FILE_INVALID", state)
    if info.st_uid != expected_uid or info.st_gid != expected_gid:
        _fail("KEY_FILE_INVALID", state)
    if info.st_nlink != 1:
        _fail("KEY_FILE_INVALID", state)
    if info.st_size <= 0 or info.st_size > MAX_PRIVATE_KEY_BYTES:
        _fail("KEY_FILE_INVALID", state)
    return info


def _preflight_at(
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
    state = _OperationState()
    directory_fd = _validate_preconditions_at(
        directory_path=directory_path,
        repo_root=repo_root,
        approved_source_sha=approved_source_sha,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        required_euid=required_euid,
        openssl_binary=openssl_binary,
        openssl_owner_uid=openssl_owner_uid,
        state=state,
    )
    os.close(directory_fd)
    return _receipt(status=STATUS_PREFLIGHT_PASS, state=state)


def _apply_at(
    *,
    directory_path: str,
    repo_root: Path,
    approved_source_sha: str,
    expected_uid: int,
    expected_gid: int,
    required_euid: int,
    openssl_binary: str,
    openssl_owner_uid: int,
    state: _OperationState | None = None,
) -> dict[str, object]:
    operation_state = state if state is not None else _OperationState()
    directory_fd = _validate_preconditions_at(
        directory_path=directory_path,
        repo_root=repo_root,
        approved_source_sha=approved_source_sha,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        required_euid=required_euid,
        openssl_binary=openssl_binary,
        openssl_owner_uid=openssl_owner_uid,
        state=operation_state,
    )
    key_fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            key_fd = os.open(STAGING_FILENAME, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            _fail("STAGING_EXISTS", operation_state)
        except OSError:
            _fail("STAGING_CREATE_FAILED", operation_state)

        operation_state.mutation_started = True
        operation_state.authorization_consumed = True

        try:
            os.fchown(key_fd, expected_uid, expected_gid)
            os.fchmod(key_fd, 0o600)
        except OSError:
            _fail("KEY_METADATA_FAILED", operation_state)

        result = _run_command(
            [openssl_binary, "genpkey", "-algorithm", "ED25519"],
            state=operation_state,
            stdout_target=key_fd,
        )
        if result.returncode != 0:
            _fail("KEY_GENERATION_FAILED", operation_state)
        try:
            os.fsync(key_fd)
        except OSError:
            _fail("KEY_SYNC_FAILED", operation_state)

        staging_info = _verify_key_file(
            key_fd,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            state=operation_state,
        )
        public_key = _derive_public_key(key_fd, openssl_binary, operation_state)

        _require_absent(
            directory_fd,
            PRIVATE_KEY_FILENAME,
            "TARGET_EXISTS",
            operation_state,
        )
        try:
            os.link(
                STAGING_FILENAME,
                PRIVATE_KEY_FILENAME,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            _fail("TARGET_EXISTS", operation_state)
        except OSError:
            _fail("ATOMIC_PUBLISH_FAILED", operation_state)

        try:
            os.fsync(directory_fd)
        except OSError:
            _fail("DIRECTORY_SYNC_FAILED", operation_state)

        try:
            published_info = os.stat(
                PRIVATE_KEY_FILENAME,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError:
            _fail("PUBLISHED_KEY_INVALID", operation_state)
        if (
            not stat.S_ISREG(published_info.st_mode)
            or published_info.st_dev != staging_info.st_dev
            or published_info.st_ino != staging_info.st_ino
            or published_info.st_nlink != 2
            or stat.S_IMODE(published_info.st_mode) != 0o600
            or published_info.st_uid != expected_uid
            or published_info.st_gid != expected_gid
            or published_info.st_size != staging_info.st_size
        ):
            _fail("PUBLISHED_KEY_INVALID", operation_state)

        try:
            os.unlink(STAGING_FILENAME, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError:
            _fail("STAGING_RETIRE_FAILED", operation_state)

        try:
            final_info = os.stat(
                PRIVATE_KEY_FILENAME,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except OSError:
            _fail("PUBLISHED_KEY_INVALID", operation_state)
        if (
            not stat.S_ISREG(final_info.st_mode)
            or final_info.st_nlink != 1
            or stat.S_IMODE(final_info.st_mode) != 0o600
            or final_info.st_uid != expected_uid
            or final_info.st_gid != expected_gid
            or final_info.st_size != staging_info.st_size
        ):
            _fail("PUBLISHED_KEY_INVALID", operation_state)

        return _receipt(
            status=STATUS_CREATED,
            state=operation_state,
            public_key=public_key,
        )
    finally:
        if key_fd is not None:
            try:
                os.close(key_fd)
            except OSError:
                pass
        try:
            os.close(directory_fd)
        except OSError:
            pass


def preflight_credential_bootstrap(*, approved_source_sha: str) -> dict[str, object]:
    return _preflight_at(
        directory_path=CREDSTORE_DIRECTORY,
        repo_root=REPOSITORY_ROOT,
        approved_source_sha=approved_source_sha,
        expected_uid=0,
        expected_gid=0,
        required_euid=0,
        openssl_binary=OPENSSL_BINARY,
        openssl_owner_uid=0,
    )


def apply_credential_bootstrap(
    *,
    approved_source_sha: str,
    state: _OperationState | None = None,
) -> dict[str, object]:
    return _apply_at(
        directory_path=CREDSTORE_DIRECTORY,
        repo_root=REPOSITORY_ROOT,
        approved_source_sha=approved_source_sha,
        expected_uid=0,
        expected_gid=0,
        required_euid=0,
        openssl_binary=OPENSSL_BINARY,
        openssl_owner_uid=0,
        state=state,
    )
