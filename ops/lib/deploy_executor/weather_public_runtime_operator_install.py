from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any, Sequence

from deploy_executor.weather_public_runtime_privileged_install import (
    _copy_exact,
    _path_absent,
    _rename_noreplace,
    _require_directory,
    _require_regular,
)

TRUSTED_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-install-trusted"
TRUSTED_CHECKOUT_DERIVATION = f"RPi5_CHECKOUT_PARENT/{TRUSTED_CHECKOUT_NAME}"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
CONTRACT_RELATIVE = Path("ops/deploy/weather-public-runtime-operator-install.json")
INSTALLER_ENTRYPOINT_RELATIVE = Path("ops/bin/rozkalns-weather-public-runtime-operator-install")
INSTALLER_MODULE_RELATIVE = Path("ops/lib/deploy_executor/weather_public_runtime_operator_install.py")
ENTRYPOINT = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator")
PACKAGE_ROOT = SUPPORT_ROOT / "deploy_executor"
ROOT_UID = 0
ROOT_GID = 0
ARTIFACT_COUNT = 23
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

_EXPECTED_ARTIFACTS = (
    ("ops/bin/rozkalns-weather-public-runtime-operator", "/usr/local/sbin/rozkalns-weather-public-runtime-operator", 0o755),
    ("ops/lib/deploy_executor/__init__.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/__init__.py", 0o644),
    ("ops/lib/deploy_executor/adapters.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/adapters.py", 0o644),
    ("ops/lib/deploy_executor/github_app_auth.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/github_app_auth.py", 0o644),
    ("ops/lib/deploy_executor/p9_canary.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/p9_canary.py", 0o644),
    ("ops/lib/deploy_executor/p9_isolated_auth_surface.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/p9_isolated_auth_surface.py", 0o644),
    ("ops/lib/deploy_executor/p9_runtime.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/p9_runtime.py", 0o644),
    ("ops/lib/deploy_executor/protocol.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/protocol.py", 0o644),
    ("ops/lib/deploy_executor/queue_normalizer.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/queue_normalizer.py", 0o644),
    ("ops/lib/deploy_executor/registry.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/registry.py", 0o644),
    ("ops/lib/deploy_executor/state.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/state.py", 0o644),
    ("ops/lib/deploy_executor/transport.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/transport.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_adapter.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_adapter.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_bootstrap.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_bootstrap.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_composite.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_composite.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_execution.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_execution.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_helper_launch.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_helper_launch.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_host_wiring.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_host_wiring.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_operator.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_operator.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_preactivation.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_preactivation.py", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_stage_helper.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_stage_helper.py", 0o644),
    ("ops/deploy/weather-public-runtime-operator-registry.json", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/executor-operations.json", 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_privileged_install.py", "/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_privileged_install.py", 0o644),
)


class WeatherOperatorInstallError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise WeatherOperatorInstallError(message)


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON field is forbidden: {key}")
        result[key] = value
    return result


def source_readiness() -> dict[str, Any]:
    return {
        "schema": "rozkalns-weather.public-runtime-operator-installer-source.v1",
        "issue": 462,
        "caller_authority": (),
        "trusted_install_checkout": TRUSTED_CHECKOUT_DERIVATION,
        "artifact_count": ARTIFACT_COUNT,
        "capability_specific_root_entrypoint_source_present": True,
        "runtime_live_authority": False,
        "operator_installation_enabled": False,
        "operator_invocation_enabled": False,
        "helper_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "generic_shell_authority": False,
        "caller_supplied_path_allowed": False,
        "caller_supplied_argv_allowed": False,
        "caller_supplied_environment_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def expected_install_artifacts() -> tuple[tuple[str, str, int], ...]:
    return _EXPECTED_ARTIFACTS


def _git(checkout: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/git", "--no-optional-locks", "-c", f"safe.directory={checkout}", "-C", str(checkout), *args],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            close_fds=True,
            env=_FIXED_ENV,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise WeatherOperatorInstallError("trusted checkout Git read failed to run") from exc
    if result.returncode != 0:
        _fail(f"trusted checkout Git read failed rc={result.returncode}")
    if len(result.stdout.encode("utf-8")) > MAX_GIT_OUTPUT or len(result.stderr.encode("utf-8")) > MAX_GIT_OUTPUT:
        _fail("trusted checkout Git read output exceeded limit")
    return result.stdout


def _validate_source_relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        _fail("source path escaped the fixed repository-relative surface")
    return Path(*pure.parts)


def _validate_trusted_checkout(checkout: Path) -> str:
    checkout = checkout.resolve()
    if checkout.name != TRUSTED_CHECKOUT_NAME or not checkout.is_dir():
        _fail("unexpected successor trusted checkout identity")
    top = Path(_git(checkout, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != checkout:
        _fail("successor trusted checkout top-level drifted")
    if _git(checkout, "config", "--get", "remote.origin.url").strip() != REVIEWED_ORIGIN:
        _fail("successor trusted checkout origin drifted")
    if _git(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip() != "HEAD":
        _fail("successor trusted checkout is not detached")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("successor trusted checkout is not clean")
    head = _git(checkout, "rev-parse", "HEAD").strip()
    origin_main = _git(checkout, "rev-parse", "refs/remotes/origin/main").strip()
    if _SHA40_RE.fullmatch(head) is None or _SHA40_RE.fullmatch(origin_main) is None or head != origin_main:
        _fail("successor trusted checkout is not exact origin/main")
    return head


def _load_contract(checkout: Path) -> dict[str, Any]:
    path = checkout / CONTRACT_RELATIVE
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > MAX_ARTIFACT_BYTES:
        _fail("operator install contract source shape drifted")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except WeatherOperatorInstallError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherOperatorInstallError("operator install contract is unreadable") from exc
    if type(value) is not dict:
        _fail("operator install contract must be an object")
    return value


def _validate_contract(value: dict[str, Any]) -> tuple[tuple[str, str, int], ...]:
    required = {
        "schema_version": 1,
        "contract": "rozkalns-weather.public-runtime-operator-install.v1",
        "status": "SOURCE_READY_INSTALL_DISABLED",
        "repository": "rozkalnsandris/RPi5_main",
        "issue": 454,
        "entrypoint": str(ENTRYPOINT),
        "support_root": str(SUPPORT_ROOT),
        "package_root": str(PACKAGE_ROOT),
        "artifact_count": ARTIFACT_COUNT,
        "required_owner_uid": ROOT_UID,
        "required_owner_gid": ROOT_GID,
        "entrypoint_mode": "0755",
        "module_mode": "0644",
        "contract_mode": "0644",
        "canonical_privileged_install_contract": "ops/deploy/weather-public-runtime-privileged-install-activation.json",
        "canonical_successor_checkout_contract": "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json",
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            _fail(f"operator install contract drifted: {key}")
    if value.get("activation") != {
        "source_merge_authorizes_install": False,
        "host_installed": False,
        "separate_explicit_live_authorization_required": True,
        "caller_selected_path": False,
        "caller_selected_argv": False,
        "caller_selected_environment": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }:
        _fail("operator install activation contract drifted")
    if value.get("installer_bridge") != {
        "issue": 462,
        "status": "SOURCE_ONLY_INSTALLER_BRIDGE_INACTIVE",
        "source_entrypoint": f"{TRUSTED_CHECKOUT_DERIVATION}/ops/bin/rozkalns-weather-public-runtime-operator-install",
        "source_module": f"{TRUSTED_CHECKOUT_DERIVATION}/ops/lib/deploy_executor/weather_public_runtime_operator_install.py",
        "caller_arguments": [],
        "requires_euid": 0,
        "requires_detached_clean_checkout": True,
        "requires_head_equals_origin_main": True,
        "publication_order": ["support_root", "entrypoint"],
        "partial_support_without_entrypoint_is_inert": True,
        "source_merge_enables_install": False,
        "generic_shell_authority": False,
        "caller_selected_path": False,
        "caller_selected_argv": False,
        "caller_selected_environment": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }:
        _fail("operator installer bridge contract drifted")
    artifacts = value.get("artifacts")
    if type(artifacts) is not list or len(artifacts) != ARTIFACT_COUNT:
        _fail("operator install artifact count drifted")
    observed = []
    for item in artifacts:
        if type(item) is not dict or set(item) != {"source", "destination", "kind", "mode"}:
            _fail("operator install artifact shape drifted")
        try:
            source = item["source"]
            destination = item["destination"]
            mode = int(item["mode"], 8)
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherOperatorInstallError("operator install artifact is invalid") from exc
        if type(source) is not str or type(destination) is not str or type(item["kind"]) is not str:
            _fail("operator install artifact types drifted")
        _validate_source_relative(source)
        observed.append((source, destination, mode))
    if tuple(observed) != _EXPECTED_ARTIFACTS:
        _fail("operator install artifact identities drifted")
    if len({destination for _, destination, _ in observed}) != ARTIFACT_COUNT:
        _fail("operator install destination identities are not unique")
    return tuple(observed)


def _git_blob_sha(checkout: Path, relative: str) -> str:
    raw = _git(checkout, "ls-tree", "-z", "HEAD", "--", relative)
    if not raw.endswith("\0") or raw.count("\0") != 1:
        _fail(f"tracked source identity missing or ambiguous: {relative}")
    try:
        metadata, path = raw[:-1].split("\t", 1)
        mode, object_type, object_sha = metadata.split(" ", 2)
    except ValueError as exc:
        raise WeatherOperatorInstallError("tracked source identity malformed") from exc
    if path != relative or object_type != "blob" or mode not in {"100644", "100755"} or _SHA40_RE.fullmatch(object_sha) is None:
        _fail(f"tracked source identity drifted: {relative}")
    return object_sha


def _read_bound_source(checkout: Path, relative_text: str) -> tuple[bytes, str]:
    relative = _validate_source_relative(relative_text)
    path = checkout / relative
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_ARTIFACT_BYTES:
        _fail(f"operator source shape drifted: {relative_text}")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            _fail(f"operator source changed before read: {relative_text}")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(fd, min(131072, remaining))
            if not chunk:
                _fail(f"operator source short read: {relative_text}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            _fail(f"operator source grew during read: {relative_text}")
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            _fail(f"operator source changed during read: {relative_text}")
        data = b"".join(chunks)
    finally:
        os.close(fd)
    git_hash = hashlib.sha1(usedforsecurity=False)
    git_hash.update(f"blob {len(data)}\0".encode("ascii"))
    git_hash.update(data)
    if git_hash.hexdigest() != _git_blob_sha(checkout, relative_text):
        _fail(f"operator source does not match trusted HEAD: {relative_text}")
    return data, hashlib.sha256(data).hexdigest()


def _support_relative(destination: str) -> Path:
    try:
        relative = Path(destination).relative_to(SUPPORT_ROOT)
    except ValueError as exc:
        raise WeatherOperatorInstallError("support destination escaped fixed root") from exc
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        _fail("support destination is invalid")
    return relative


def _secure_parent(path: Path) -> None:
    meta = _require_directory(path, uid=ROOT_UID, gid=ROOT_GID)
    if stat.S_IMODE(meta.st_mode) & 0o022:
        _fail(f"operator install parent is group/world writable: {path}")


def _stage_paths(source_sha: str) -> tuple[Path, Path]:
    if _SHA40_RE.fullmatch(source_sha) is None:
        _fail("operator install source SHA is invalid")
    return (
        SUPPORT_ROOT.parent / f".{SUPPORT_ROOT.name}.stage-{source_sha}",
        ENTRYPOINT.parent / f".{ENTRYPOINT.name}.stage-{source_sha}",
    )


def _verify_hash(path: Path, mode: int, expected_sha256: str) -> None:
    _require_regular(path, uid=ROOT_UID, gid=ROOT_GID, mode=mode)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        _fail(f"operator installed artifact hash drifted: {path}")


def _verify_support(root: Path, artifacts: tuple[tuple[str, str, int], ...], hashes: dict[str, str]) -> None:
    _require_directory(root, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
    expected = set()
    for source, destination, mode in artifacts:
        if destination == str(ENTRYPOINT):
            continue
        relative = _support_relative(destination)
        expected.add(relative.as_posix())
        _verify_hash(root / relative, mode, hashes[source])
    observed = set()
    for path in root.rglob("*"):
        meta = path.lstat()
        if stat.S_ISDIR(meta.st_mode):
            if meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID or stat.S_IMODE(meta.st_mode) != 0o755:
                _fail("operator support directory metadata drifted")
            continue
        if not stat.S_ISREG(meta.st_mode):
            _fail("operator support tree contains a non-regular entry")
        observed.add(path.relative_to(root).as_posix())
    if observed != expected:
        _fail("operator support tree membership drifted")


def _install_transaction(checkout: Path, source_sha: str, artifacts: tuple[tuple[str, str, int], ...]) -> dict[str, Any]:
    _secure_parent(SUPPORT_ROOT.parent)
    _secure_parent(ENTRYPOINT.parent)
    support_stage, entry_stage = _stage_paths(source_sha)
    for path, label in (
        (SUPPORT_ROOT, "operator support root"),
        (ENTRYPOINT, "operator entrypoint"),
        (support_stage, "operator support stage"),
        (entry_stage, "operator entrypoint stage"),
    ):
        _path_absent(path, label)

    os.mkdir(support_stage, 0o700)
    os.chown(support_stage, ROOT_UID, ROOT_GID)
    package_stage = support_stage / "deploy_executor"
    os.mkdir(package_stage, 0o755)
    os.chown(package_stage, ROOT_UID, ROOT_GID)

    hashes: dict[str, str] = {}
    entry_source = None
    for source, destination, mode in artifacts:
        _, digest = _read_bound_source(checkout, source)
        hashes[source] = digest
        if destination == str(ENTRYPOINT):
            entry_source = source
            _copy_exact(checkout / source, entry_stage, mode)
            _verify_hash(entry_stage, mode, digest)
            continue
        relative = _support_relative(destination)
        if relative.parent not in {Path("."), Path("deploy_executor")}:
            _fail("operator support destination introduced an unexpected directory")
        target_parent = support_stage if relative.parent == Path(".") else package_stage
        _copy_exact(checkout / source, target_parent / relative.name, mode)
        _verify_hash(target_parent / relative.name, mode, digest)

    if entry_source is None:
        _fail("operator entrypoint is absent from the fixed install allowlist")
    os.chmod(support_stage, 0o755)
    os.chown(support_stage, ROOT_UID, ROOT_GID)
    _verify_support(support_stage, artifacts, hashes)

    _rename_noreplace(support_stage, SUPPORT_ROOT)
    _verify_support(SUPPORT_ROOT, artifacts, hashes)
    _rename_noreplace(entry_stage, ENTRYPOINT)
    _verify_hash(ENTRYPOINT, 0o755, hashes[entry_source])
    _verify_support(SUPPORT_ROOT, artifacts, hashes)
    return {
        "status": "INSTALLED",
        "source_sha": source_sha,
        "artifact_count": ARTIFACT_COUNT,
        "support_root_published": True,
        "entrypoint_published": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def install_operator() -> dict[str, Any]:
    if os.geteuid() != 0:
        _fail("Weather operator installer must run as root")
    checkout = Path(__file__).resolve().parents[3]
    expected_module = checkout / INSTALLER_MODULE_RELATIVE
    if checkout.name != TRUSTED_CHECKOUT_NAME or Path(__file__).resolve() != expected_module.resolve():
        _fail("Weather operator installer module is not in the fixed successor checkout")
    source_sha = _validate_trusted_checkout(checkout)
    artifacts = _validate_contract(_load_contract(checkout))
    return _install_transaction(checkout, source_sha, artifacts)
