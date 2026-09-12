from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Sequence

from deploy_executor import weather_public_runtime_operator_install as install

ISSUE = 487
TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-trusted"
TRUSTED_CHECKOUT_DERIVATION = f"RPi5_CHECKOUT_PARENT/{TRUSTED_CHECKOUT_NAME}"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
PREDECESSOR_SHA = "7b54434d296bcd7030464f3fc13e4a601acaa2d9"
MINIMUM_TARGET_ANCESTOR = "a432fb21d558d54f9f0eb1fb48e2f1a0670ed48f"
TARGET_SOURCE = "ops/lib/deploy_executor/weather_public_runtime_operator.py"
CANONICAL_ENTRYPOINT = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
CANONICAL_SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator")
ENTRYPOINT = CANONICAL_ENTRYPOINT
SUPPORT_ROOT = CANONICAL_SUPPORT_ROOT
PACKAGE_ROOT = SUPPORT_ROOT / "deploy_executor"
TARGET_FILENAME = "weather_public_runtime_operator.py"
TARGET_OLD_BLOB = "c72eec092d0c8669fa600b79d23b100f6273852a"
TARGET_NEW_BLOB = "e48494077fc37125bca46d02c6020a0e4c04cd2f"
TARGET_OLD_SHA256 = "878a50d49690fe90efb185534d4df81ca9303a0d21522102d3a0432a4ff6df23"
TARGET_NEW_SHA256 = "cc93baecce1cb594ce1ed23c837d144b467c2c27b8004d5f04069422dfc4af06"
UPGRADE_CONTRACT_RELATIVE = Path("ops/deploy/weather-public-runtime-operator-upgrade.json")
CHECKOUT_CONTRACT_RELATIVE = Path(
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-trusted-checkout-bootstrap.json"
)
UPGRADE_ENTRYPOINT_RELATIVE = Path("ops/bin/rozkalns-weather-public-runtime-operator-upgrade")
UPGRADE_MODULE_RELATIVE = Path("ops/lib/deploy_executor/weather_public_runtime_operator_upgrade.py")
TEMP_NAME = ".weather_public_runtime_operator.py.compatibility-upgrade.tmp"
ROOT_UID = 0
ROOT_GID = 0
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_GIT_OUTPUT = 65536
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_FIXED_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "HOME": "/nonexistent",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class WeatherOperatorUpgradeError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise WeatherOperatorUpgradeError(message)


def source_readiness() -> dict[str, Any]:
    return {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-source.v1",
        "issue": ISSUE,
        "caller_authority": (),
        "trusted_upgrade_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "predecessor_sha": PREDECESSOR_SHA,
        "target_source": TARGET_SOURCE,
        "target_old_sha256": TARGET_OLD_SHA256,
        "target_new_sha256": TARGET_NEW_SHA256,
        "mutation_target_count": 1,
        "runtime_live_authority": False,
        "operator_upgrade_enabled": False,
        "operator_invocation_enabled": False,
        "helper_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "generic_shell_authority": False,
        "caller_supplied_path_allowed": False,
        "caller_supplied_argv_allowed": False,
        "caller_supplied_environment_allowed": False,
        "caller_supplied_repository_url_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def _run_git(checkout: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-c",
                f"safe.directory={checkout}",
                "-C",
                str(checkout),
                *args,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            env=_FIXED_ENV,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise WeatherOperatorUpgradeError("trusted upgrade checkout Git read failed to run") from exc
    if len(result.stdout) > MAX_GIT_OUTPUT or len(result.stderr) > MAX_GIT_OUTPUT:
        _fail("trusted upgrade checkout Git read output exceeded limit")
    return result


def _git_bytes(checkout: Path, *args: str) -> bytes:
    result = _run_git(checkout, *args)
    if result.returncode != 0:
        _fail(f"trusted upgrade checkout Git read failed rc={result.returncode}")
    return result.stdout


def _git_text(checkout: Path, *args: str) -> str:
    try:
        return _git_bytes(checkout, *args).decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise WeatherOperatorUpgradeError("trusted upgrade checkout Git output is not UTF-8") from exc


def _git_blob_sha_at(checkout: Path, commit: str, relative: str) -> str:
    blob = _git_text(checkout, "rev-parse", f"{commit}:{relative}").strip()
    if _SHA40_RE.fullmatch(blob) is None:
        _fail(f"reviewed Git blob identity is invalid: {relative}")
    return blob


def _git_show_bytes(checkout: Path, commit: str, relative: str) -> bytes:
    return _git_bytes(checkout, "show", f"{commit}:{relative}")


def _validate_trusted_checkout(checkout: Path) -> str:
    try:
        source_meta = checkout.lstat()
    except OSError as exc:
        raise WeatherOperatorUpgradeError("trusted upgrade checkout is unavailable") from exc
    if not stat.S_ISDIR(source_meta.st_mode) or stat.S_ISLNK(source_meta.st_mode):
        _fail("trusted upgrade checkout is not a real directory")
    checkout = checkout.resolve()
    if checkout.name != TRUSTED_CHECKOUT_NAME:
        _fail("unexpected trusted upgrade checkout identity")
    top = Path(_git_text(checkout, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != checkout:
        _fail("trusted upgrade checkout top-level drifted")
    if _git_text(checkout, "config", "--get", "remote.origin.url").strip() != REVIEWED_ORIGIN:
        _fail("trusted upgrade checkout origin drifted")
    if _git_text(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip() != "HEAD":
        _fail("trusted upgrade checkout is not detached")
    if _git_text(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("trusted upgrade checkout is not clean")
    head = _git_text(checkout, "rev-parse", "HEAD").strip()
    origin_main = _git_text(checkout, "rev-parse", "refs/remotes/origin/main").strip()
    if _SHA40_RE.fullmatch(head) is None or head != origin_main:
        _fail("trusted upgrade checkout is not exact fetched origin/main")
    if _run_git(checkout, "merge-base", "--is-ancestor", MINIMUM_TARGET_ANCESTOR, head).returncode != 0:
        _fail("trusted upgrade checkout does not descend from the reviewed minimum target ancestor")
    for relative in (
        install.CONTRACT_RELATIVE,
        UPGRADE_CONTRACT_RELATIVE,
        CHECKOUT_CONTRACT_RELATIVE,
        UPGRADE_ENTRYPOINT_RELATIVE,
        UPGRADE_MODULE_RELATIVE,
        Path(TARGET_SOURCE),
    ):
        path = checkout / relative
        try:
            meta = path.lstat()
        except OSError as exc:
            raise WeatherOperatorUpgradeError(f"required upgrade source is unavailable: {relative}") from exc
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
            _fail(f"required upgrade source identity drifted: {relative}")
    return head


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON field is forbidden: {key}")
        value[key] = item
    return value


def _load_upgrade_contract(checkout: Path) -> dict[str, Any]:
    path = checkout / UPGRADE_CONTRACT_RELATIVE
    try:
        meta = path.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > MAX_ARTIFACT_BYTES:
            _fail("operator upgrade contract source shape drifted")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except WeatherOperatorUpgradeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherOperatorUpgradeError("operator upgrade contract is unreadable") from exc
    if type(value) is not dict:
        _fail("operator upgrade contract must be an object")
    return value


def _validate_upgrade_contract(value: dict[str, Any]) -> None:
    expected = {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade.v1",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": ISSUE,
        "status": "SOURCE_ONLY_UPGRADE_BRIDGE_INACTIVE",
        "predecessor_sha": PREDECESSOR_SHA,
        "minimum_target_ancestor": MINIMUM_TARGET_ANCESTOR,
        "operator_install_manifest": str(install.CONTRACT_RELATIVE),
        "trusted_upgrade_checkout_contract": str(CHECKOUT_CONTRACT_RELATIVE),
        "trusted_upgrade_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "target_source": TARGET_SOURCE,
        "target_destination": str(CANONICAL_SUPPORT_ROOT / "deploy_executor" / TARGET_FILENAME),
        "old_blob": TARGET_OLD_BLOB,
        "new_blob": TARGET_NEW_BLOB,
        "old_sha256": TARGET_OLD_SHA256,
        "new_sha256": TARGET_NEW_SHA256,
        "required_owner_uid": ROOT_UID,
        "required_owner_gid": ROOT_GID,
        "required_mode": "0644",
        "mutation_target_count": 1,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            _fail(f"operator upgrade contract drifted: {key}")
    if value.get("caller_arguments") != []:
        _fail("operator upgrade caller argument contract drifted")
    if value.get("allowed_changed_artifacts") != [TARGET_SOURCE]:
        _fail("operator upgrade changed-artifact allowlist drifted")
    replacement = value.get("replacement")
    if replacement != {
        "temporary_name": TEMP_NAME,
        "same_directory": True,
        "no_follow": True,
        "exclusive_create": True,
        "fsync_before_replace": True,
        "atomic_replace": True,
        "parent_fsync_after_replace": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "backup_restore": False,
    }:
        _fail("operator upgrade replacement contract drifted")
    safety = value.get("safety")
    if safety != {
        "source_merge_authorizes_live": False,
        "runtime_live_authority": False,
        "generic_shell_authority": False,
        "caller_selected_path": False,
        "caller_selected_argv": False,
        "caller_selected_environment": False,
        "caller_selected_repository_url": False,
        "trusted_checkout_repair": False,
        "docker_mutation": False,
        "systemd_mutation": False,
        "sqlite_or_corpus_mutation": False,
        "network_or_secret_mutation": False,
    }:
        _fail("operator upgrade safety contract drifted")


def _install_artifacts(checkout: Path) -> tuple[tuple[str, str, int], ...]:
    try:
        return install._validate_contract(install._load_contract(checkout))
    except install.WeatherOperatorInstallError as exc:
        raise WeatherOperatorUpgradeError("canonical operator install contract drifted") from exc


def _read_bound_source(checkout: Path, relative: str) -> tuple[bytes, str]:
    try:
        return install._read_bound_source(checkout, relative)
    except install.WeatherOperatorInstallError as exc:
        raise WeatherOperatorUpgradeError(f"reviewed operator source drifted: {relative}") from exc


def _source_diff_guard(
    checkout: Path,
    source_sha: str,
    artifacts: tuple[tuple[str, str, int], ...],
) -> bytes:
    if _run_git(checkout, "merge-base", "--is-ancestor", PREDECESSOR_SHA, source_sha).returncode != 0:
        _fail("reviewed predecessor is not an ancestor of the target source")
    changed: list[str] = []
    for source, _destination, _mode in artifacts:
        old_blob = _git_blob_sha_at(checkout, PREDECESSOR_SHA, source)
        new_blob = _git_blob_sha_at(checkout, source_sha, source)
        if old_blob != new_blob:
            changed.append(source)
    if changed != [TARGET_SOURCE]:
        _fail("operator closure source diff is not exactly the reviewed one-module upgrade")
    if _git_blob_sha_at(checkout, PREDECESSOR_SHA, TARGET_SOURCE) != TARGET_OLD_BLOB:
        _fail("reviewed predecessor operator module blob drifted")
    if _git_blob_sha_at(checkout, source_sha, TARGET_SOURCE) != TARGET_NEW_BLOB:
        _fail("reviewed target operator module blob drifted")
    old_bytes = _git_show_bytes(checkout, PREDECESSOR_SHA, TARGET_SOURCE)
    new_bytes, new_sha256 = _read_bound_source(checkout, TARGET_SOURCE)
    if hashlib.sha256(old_bytes).hexdigest() != TARGET_OLD_SHA256:
        _fail("reviewed predecessor operator module SHA-256 drifted")
    if hashlib.sha256(new_bytes).hexdigest() != TARGET_NEW_SHA256 or new_sha256 != TARGET_NEW_SHA256:
        _fail("reviewed target operator module SHA-256 drifted")
    return new_bytes


def _require_directory(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise WeatherOperatorUpgradeError(f"required directory is unavailable: {path}") from exc
    if not stat.S_ISDIR(meta.st_mode) or stat.S_ISLNK(meta.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID:
        _fail(f"required directory owner/group drifted: {path}")
    mode = stat.S_IMODE(meta.st_mode)
    if exact_mode is not None:
        if mode != exact_mode:
            _fail(f"required directory mode drifted: {path}")
    elif mode & 0o022:
        _fail(f"required directory is group/world writable: {path}")
    return meta


def _read_regular_exact(path: Path, *, mode: int, sha256: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise WeatherOperatorUpgradeError(f"installed operator artifact is unavailable: {path}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size > MAX_ARTIFACT_BYTES
    ):
        _fail(f"installed operator artifact metadata drifted: {path}")
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise WeatherOperatorUpgradeError(f"installed operator artifact cannot be opened safely: {path}") from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            _fail(f"installed operator artifact changed before read: {path}")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(fd, min(131072, remaining))
            if not chunk:
                _fail(f"installed operator artifact short read: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            _fail(f"installed operator artifact grew during read: {path}")
        after = os.fstat(fd)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            _fail(f"installed operator artifact changed during read: {path}")
        data = b"".join(chunks)
    finally:
        os.close(fd)
    now = path.lstat()
    if (now.st_dev, now.st_ino) != (before.st_dev, before.st_ino):
        _fail(f"installed operator artifact path changed during read: {path}")
    if hashlib.sha256(data).hexdigest() != sha256:
        _fail(f"installed operator artifact content drifted: {path}")
    return data


def _actual_artifact_path(destination: str) -> Path:
    canonical = Path(destination)
    if canonical == CANONICAL_ENTRYPOINT:
        return ENTRYPOINT
    try:
        relative = canonical.relative_to(CANONICAL_SUPPORT_ROOT)
    except ValueError as exc:
        raise WeatherOperatorUpgradeError("operator artifact escaped the fixed support root") from exc
    return SUPPORT_ROOT / relative


def _observed_support_membership() -> set[str]:
    observed: set[str] = set()
    for item in SUPPORT_ROOT.iterdir():
        if item.name == "deploy_executor":
            _require_directory(item, exact_mode=0o755)
            for child in item.iterdir():
                meta = child.lstat()
                if not stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode):
                    _fail("operator deploy_executor package contains a non-regular entry")
                observed.add(f"deploy_executor/{child.name}")
            continue
        meta = item.lstat()
        if not stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode):
            _fail("operator support root contains an unexpected non-regular entry")
        observed.add(item.name)
    return observed


def _validate_installed_closure(
    checkout: Path,
    artifacts: tuple[tuple[str, str, int], ...],
) -> None:
    _require_directory(SUPPORT_ROOT.parent)
    _require_directory(ENTRYPOINT.parent)
    _require_directory(SUPPORT_ROOT, exact_mode=0o755)
    _require_directory(PACKAGE_ROOT, exact_mode=0o755)
    expected_membership: set[str] = set()
    current_hashes: dict[str, str] = {}
    for source, destination, mode in artifacts:
        _data, digest = _read_bound_source(checkout, source)
        current_hashes[source] = digest
        actual = _actual_artifact_path(destination)
        if actual != ENTRYPOINT:
            expected_membership.add(actual.relative_to(SUPPORT_ROOT).as_posix())
        expected = TARGET_OLD_SHA256 if source == TARGET_SOURCE else digest
        _read_regular_exact(actual, mode=mode, sha256=expected)
    if _observed_support_membership() != expected_membership:
        _fail("installed operator support tree membership drifted")
    if current_hashes[TARGET_SOURCE] != TARGET_NEW_SHA256:
        _fail("current operator source hash drifted")


def _open_package_fd() -> int:
    _require_directory(PACKAGE_ROOT, exact_mode=0o755)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(PACKAGE_ROOT, flags)
    except OSError as exc:
        raise WeatherOperatorUpgradeError("unable to open fixed operator package directory") from exc
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != ROOT_UID
        or opened.st_gid != ROOT_GID
        or stat.S_IMODE(opened.st_mode) != 0o755
    ):
        os.close(fd)
        _fail("opened operator package directory metadata drifted")
    return fd


def _require_temp_absent(parent_fd: int) -> None:
    try:
        os.stat(TEMP_NAME, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    _fail("fixed operator upgrade temporary target already exists")


def _open_target_fd(parent_fd: int) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(TARGET_FILENAME, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise WeatherOperatorUpgradeError("unable to open fixed installed operator module") from exc


def _read_fd_all(fd: int) -> bytes:
    opened = os.fstat(fd)
    if opened.st_size > MAX_ARTIFACT_BYTES:
        _fail("operator module exceeds reviewed size bound")
    chunks: list[bytes] = []
    os.lseek(fd, 0, os.SEEK_SET)
    remaining = opened.st_size
    while remaining:
        chunk = os.read(fd, min(131072, remaining))
        if not chunk:
            _fail("operator module short read")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(fd, 1):
        _fail("operator module grew during read")
    return b"".join(chunks)


def _require_old_target(parent_fd: int, fd: int) -> os.stat_result:
    opened = os.fstat(fd)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or opened.st_uid != ROOT_UID
        or opened.st_gid != ROOT_GID
        or stat.S_IMODE(opened.st_mode) != 0o644
    ):
        _fail("installed operator module metadata drifted")
    if hashlib.sha256(_read_fd_all(fd)).hexdigest() != TARGET_OLD_SHA256:
        _fail("installed operator module is not the reviewed predecessor")
    current = os.stat(TARGET_FILENAME, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
        _fail("installed operator module path is no longer a regular file")
    if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
        _fail("installed operator module path changed during validation")
    return opened


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        count = os.write(fd, view[offset:])
        if count <= 0:
            _fail("short write while preparing operator module replacement")
        offset += count


def _replace_exact_target(reviewed: bytes, state: dict[str, bool]) -> None:
    parent_fd = _open_package_fd()
    target_fd = -1
    temp_fd = -1
    try:
        target_fd = _open_target_fd(parent_fd)
        opened = _require_old_target(parent_fd, target_fd)
        _require_temp_absent(parent_fd)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
        state["mutation_started"] = True
        try:
            temp_fd = os.open(TEMP_NAME, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise WeatherOperatorUpgradeError("unable to create fixed operator replacement target") from exc
        temp_meta = os.fstat(temp_fd)
        if not stat.S_ISREG(temp_meta.st_mode) or temp_meta.st_nlink != 1:
            _fail("created operator replacement target is not a single-link regular file")
        _write_all(temp_fd, reviewed)
        if (temp_meta.st_uid, temp_meta.st_gid) != (ROOT_UID, ROOT_GID):
            os.fchown(temp_fd, ROOT_UID, ROOT_GID)
        os.fchmod(temp_fd, 0o644)
        os.fsync(temp_fd)
        prepared = os.fstat(temp_fd)
        if (
            prepared.st_uid != ROOT_UID
            or prepared.st_gid != ROOT_GID
            or stat.S_IMODE(prepared.st_mode) != 0o644
            or hashlib.sha256(_read_fd_all(temp_fd)).hexdigest() != TARGET_NEW_SHA256
        ):
            _fail("prepared operator module replacement verification failed")
        current = _require_old_target(parent_fd, target_fd)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            _fail("installed operator module inode changed before replacement")
        os.replace(TEMP_NAME, TARGET_FILENAME, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        state["target_replaced"] = True
        os.fsync(parent_fd)
        verified_fd = _open_target_fd(parent_fd)
        try:
            verified = os.fstat(verified_fd)
            if (
                not stat.S_ISREG(verified.st_mode)
                or verified.st_nlink != 1
                or verified.st_uid != ROOT_UID
                or verified.st_gid != ROOT_GID
                or stat.S_IMODE(verified.st_mode) != 0o644
                or hashlib.sha256(_read_fd_all(verified_fd)).hexdigest() != TARGET_NEW_SHA256
            ):
                _fail("post-replace operator module verification failed")
        finally:
            os.close(verified_fd)
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if target_fd >= 0:
            os.close(target_fd)
        os.close(parent_fd)


def _derive_checkout() -> Path:
    checkout = Path(__file__).resolve().parents[3]
    expected = checkout / UPGRADE_MODULE_RELATIVE
    if checkout.name != TRUSTED_CHECKOUT_NAME or Path(__file__).resolve() != expected.resolve():
        _fail("Weather operator upgrade module is not in the fixed trusted upgrade checkout")
    return checkout


def _preflight(checkout: Path) -> tuple[str, bytes]:
    source_sha = _validate_trusted_checkout(checkout)
    _validate_upgrade_contract(_load_upgrade_contract(checkout))
    artifacts = _install_artifacts(checkout)
    reviewed = _source_diff_guard(checkout, source_sha, artifacts)
    if os.geteuid() != 0:
        _fail("Weather operator compatibility upgrade must run as root")
    _validate_installed_closure(checkout, artifacts)
    parent_fd = _open_package_fd()
    try:
        _require_temp_absent(parent_fd)
    finally:
        os.close(parent_fd)
    return source_sha, reviewed


def _receipt(
    *,
    result: str,
    source_sha: str | None,
    state: dict[str, bool],
    reason: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-receipt.v1",
        "result": result,
        "source_sha": source_sha,
        "predecessor_sha": PREDECESSOR_SHA,
        "old_sha256": TARGET_OLD_SHA256,
        "new_sha256": TARGET_NEW_SHA256,
        "mutation_started": state["mutation_started"],
        "target_replaced": state["target_replaced"],
        "mutation_target_count": 1,
        "operator_invoked": False,
        "helper_invoked": False,
        "docker_mutation": False,
        "systemd_mutation": False,
        "sqlite_or_corpus_mutation": False,
        "network_or_secret_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def execute_upgrade() -> dict[str, Any]:
    state = {"mutation_started": False, "target_replaced": False}
    source_sha: str | None = None
    try:
        checkout = _derive_checkout()
        source_sha, reviewed = _preflight(checkout)
        source_sha_again, reviewed_again = _preflight(checkout)
        if source_sha_again != source_sha or reviewed_again != reviewed:
            _fail("operator upgrade preflight drifted before mutation")
        _replace_exact_target(reviewed, state)
    except (WeatherOperatorUpgradeError, install.WeatherOperatorInstallError, OSError) as exc:
        return _receipt(
            result="FAIL_CLOSED",
            source_sha=source_sha,
            state=state,
            reason=str(exc),
        )
    return _receipt(result="PASS", source_sha=source_sha, state=state)
