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

ISSUE = 515
TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v5-trusted"
TRUSTED_CHECKOUT_DERIVATION = f"RPi5_CHECKOUT_PARENT/{TRUSTED_CHECKOUT_NAME}"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
PREDECESSOR_SHA = "c99f6b9df47603703f7d1e67ddc7d88c77ed726a"
MINIMUM_TARGET_ANCESTOR = "6cbe0a87e4b1ac56d0e44fea4a2249d3ef4c0135"
TARGET_SOURCE = "ops/bin/rozkalns-weather-public-runtime-operator"
CANONICAL_ENTRYPOINT = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
CANONICAL_SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator")
ENTRYPOINT = CANONICAL_ENTRYPOINT
SUPPORT_ROOT = CANONICAL_SUPPORT_ROOT
PACKAGE_ROOT = SUPPORT_ROOT / "deploy_executor"
TARGET_FILENAME = "rozkalns-weather-public-runtime-operator"
TARGET_OLD_BLOB = "2be2a8128eca470fd4c233d88410c415e4c8d438"
TARGET_NEW_BLOB = "b0f7b7269b9462605e8ef9e608f3441baf0f6392"
TARGET_OLD_SHA256 = "f5eaeb395ac374f074e9bf60c8f899371738be7c7cca1208c475e189f7d27ee5"
TARGET_NEW_SHA256 = "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f"
UPGRADE_CONTRACT_RELATIVE = Path("ops/deploy/weather-public-runtime-operator-upgrade-v5.json")
CHECKOUT_CONTRACT_RELATIVE = Path(
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v5-trusted-checkout-bootstrap.json"
)
UPGRADE_ENTRYPOINT_RELATIVE = Path("ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v5")
UPGRADE_MODULE_RELATIVE = Path("ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v5.py")
TEMP_NAME = ".rozkalns-weather-public-runtime-operator.compatibility-upgrade-v5.tmp"
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
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-v5-source.v1",
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
        "schema": "rozkalns-weather.public-runtime-operator-upgrade-v5.v1",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": ISSUE,
        "status": "SOURCE_ONLY_UPGRADE_BRIDGE_INACTIVE",
        "predecessor_sha": PREDECESSOR_SHA,
        "minimum_target_ancestor": MINIMUM_TARGET_ANCESTOR,
        "operator_install_manifest": str(install.CONTRACT_RELATIVE),
        "trusted_upgrade_checkout_contract": str(CHECKOUT_CONTRACT_RELATIVE),
        "trusted_upgrade_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "target_source": TARGET_SOURCE,
        "target_destination": str(CANONICAL_ENTRYPOINT),
        "old_blob": TARGET_OLD_BLOB,
        "new_blob": TARGET_NEW_BLOB,
        "old_sha256": TARGET_OLD_SHA256,
        "new_sha256": TARGET_NEW_SHA256,
        "required_owner_uid": ROOT_UID,
        "required_owner_gid": ROOT_GID,
        "required_mode": "0755",
        "mutation_target_count": 1,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            _fail(f"operator upgrade contract drifted: {key}")
    if value.get("caller_arguments") != []:
        _fail("operator upgrade caller argument contract drifted")
    if value.get("allowed_changed_artifacts") != [TARGET_SOURCE]:
        _fail("operator upgrade changed-artifact allowlist drifted")
    if value.get("replacement") != {
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
    if value.get("safety") != {
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
        _fail("operator closure source diff is not exactly the reviewed entrypoint upgrade")
    if _git_blob_sha_at(checkout, PREDECESSOR_SHA, TARGET_SOURCE) != TARGET_OLD_BLOB:
        _fail("reviewed predecessor operator entrypoint blob drifted")
    if _git_blob_sha_at(checkout, source_sha, TARGET_SOURCE) != TARGET_NEW_BLOB:
        _fail("reviewed target operator entrypoint blob drifted")
    old_bytes = _git_show_bytes(checkout, PREDECESSOR_SHA, TARGET_SOURCE)
    new_bytes, new_sha256 = _read_bound_source(checkout, TARGET_SOURCE)
    if hashlib.sha256(old_bytes).hexdigest() != TARGET_OLD_SHA256:
        _fail("reviewed predecessor operator entrypoint SHA-256 drifted")
    if hashlib.sha256(new_bytes).hexdigest() != TARGET_NEW_SHA256 or new_sha256 != TARGET_NEW_SHA256:
        _fail("reviewed target operator entrypoint SHA-256 drifted")
    return new_bytes


def _require_directory(path: Path, *, exact_mode: int | None = None) -> os.stat_result:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise WeatherOperatorUpgradeError(f"required directory is unavailable: {path}") from exc
    if not stat.S_ISDIR(meta.st_mode) or stat.S_ISLNK(meta.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID or stat.S_IMODE(meta.st_mode) != 0o755):
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
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino,