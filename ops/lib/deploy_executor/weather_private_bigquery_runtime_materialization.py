from __future__ import annotations

import ctypes
import errno
import hashlib
import io
import json
import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

OPERATION_ID = "rozkalns-weather.weathernext-private-runtime-materialization.v1"
PRIVATE_CONTRACT_ID = "rozkalns-weather.weathernext-private-bigquery-first-access.v1"
PUBLIC_RUNTIME_OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
MUTATION_CLASS = "weathernext_private_runtime_materialization"

TARGET_OS = "linux"
TARGET_ARCH = "aarch64"
TARGET_PYTHON_VERSION = "3.13"
TARGET_PYTHON_ABI = "cp313"
TARGET_PIP_PLATFORM = "manylinux2014_aarch64"
ARTIFACT_FORMAT = "normalized-wheelhouse-tar-v1"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024

LOCK_PATH = Path(__file__).with_name("weather_private_bigquery_runtime_lock.json")
ARTIFACT_CACHE_ROOT = Path("/var/lib/rpi5-deploy/weather-private-runtime/artifacts")
RUNTIME_BASE = Path("/var/lib/rpi5-deploy/weather-private-runtime/runtime")
RUNTIME_SITE_PACKAGES_NAME = "site-packages"
RUNTIME_MARKER_NAME = "runtime-materialization.json"
ARCHIVE_METADATA_NAME = "runtime-closure.json"

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class WeatherNextRuntimeMaterializationError(RuntimeError):
    """Raised when the private runtime capability cannot proceed safely."""


@dataclass(frozen=True)
class RuntimeArtifactReceipt:
    source_sha: str
    closure_sha256: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_format: str
    target_os: str
    target_architecture: str
    target_python_version: str
    target_python_abi: str
    target_platform: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RuntimeArtifactReceipt":
        required = {
            "source_sha",
            "closure_sha256",
            "artifact_sha256",
            "artifact_size_bytes",
            "artifact_format",
            "target_os",
            "target_architecture",
            "target_python_version",
            "target_python_abi",
            "target_platform",
        }
        if set(value) != required:
            raise WeatherNextRuntimeMaterializationError("artifact receipt keys mismatch")
        try:
            size = int(value["artifact_size_bytes"])
        except (TypeError, ValueError) as exc:
            raise WeatherNextRuntimeMaterializationError("artifact size must be an integer") from exc
        return cls(
            source_sha=str(value["source_sha"]),
            closure_sha256=str(value["closure_sha256"]),
            artifact_sha256=str(value["artifact_sha256"]),
            artifact_size_bytes=size,
            artifact_format=str(value["artifact_format"]),
            target_os=str(value["target_os"]),
            target_architecture=str(value["target_architecture"]),
            target_python_version=str(value["target_python_version"]),
            target_python_abi=str(value["target_python_abi"]),
            target_platform=str(value["target_platform"]),
        )


@dataclass(frozen=True)
class ObservedRuntimeIdentity:
    present: bool
    source_sha: str | None = None
    closure_sha256: str | None = None
    artifact_sha256: str | None = None
    target_python_abi: str | None = None
    target_platform: str | None = None


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_git_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _canonical_packages(packages: Sequence[Mapping[str, Any]]) -> bytes:
    projected = [
        {
            "name": str(item["name"]),
            "version": str(item["version"]),
            "filename": str(item["filename"]),
            "sha256": str(item["sha256"]),
        }
        for item in packages
    ]
    projected.sort(key=lambda item: item["name"])
    return json.dumps(projected, sort_keys=True, separators=(",", ":")).encode("utf-8")


def closure_digest(packages: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(_canonical_packages(packages)).hexdigest()


def load_runtime_lock(path: Path | None = None) -> Mapping[str, Any]:
    path = path or LOCK_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeatherNextRuntimeMaterializationError("runtime lock is unreadable") from exc
    if not isinstance(value, dict):
        raise WeatherNextRuntimeMaterializationError("runtime lock must be a JSON object")
    validate_runtime_lock(value)
    return value


def validate_runtime_lock(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if value.get("schema") != "rozkalns-weather.weathernext-private-runtime-lock.v1":
        raise WeatherNextRuntimeMaterializationError("runtime lock schema mismatch")
    if value.get("operation_id") != OPERATION_ID:
        raise WeatherNextRuntimeMaterializationError("runtime lock operation mismatch")
    if value.get("upstream_requirement") != "google-cloud-bigquery>=3.36,<4":
        raise WeatherNextRuntimeMaterializationError("upstream BigQuery requirement changed")
    if value.get("resolved_root") != "google-cloud-bigquery==3.42.1":
        raise WeatherNextRuntimeMaterializationError("reviewed BigQuery root version changed")
    if value.get("live_network_install_allowed") is not False:
        raise WeatherNextRuntimeMaterializationError("live network install must remain disabled")
    if value.get("live_package_manager_install_allowed") is not False:
        raise WeatherNextRuntimeMaterializationError("live package-manager install must remain disabled")
    if value.get("credential_material_in_lock") is not False:
        raise WeatherNextRuntimeMaterializationError("credential material is forbidden in runtime lock")
    if value.get("private_google_identity_in_lock") is not False:
        raise WeatherNextRuntimeMaterializationError("private Google identity is forbidden in runtime lock")

    target = value.get("target")
    expected_target = {
        "os": TARGET_OS,
        "architecture": TARGET_ARCH,
        "python_version": TARGET_PYTHON_VERSION,
        "python_abi": TARGET_PYTHON_ABI,
        "pip_platform": TARGET_PIP_PLATFORM,
        "accepted_abi": ["cp313", "abi3", "none"],
    }
    if target != expected_target:
        raise WeatherNextRuntimeMaterializationError("runtime target mismatch")

    packages = value.get("packages")
    if not isinstance(packages, list) or not packages:
        raise WeatherNextRuntimeMaterializationError("runtime lock package set missing")
    if value.get("package_count") != len(packages):
        raise WeatherNextRuntimeMaterializationError("runtime lock package count mismatch")

    names: list[str] = []
    filenames: set[str] = set()
    for item in packages:
        if not isinstance(item, dict) or set(item) != {"name", "version", "filename", "sha256"}:
            raise WeatherNextRuntimeMaterializationError("runtime package entry keys mismatch")
        name = str(item["name"])
        version = str(item["version"])
        filename = str(item["filename"])
        digest = str(item["sha256"])
        if not name or any(token in version for token in ("<", ">", "=", "*", "~", " ")):
            raise WeatherNextRuntimeMaterializationError("runtime package versions must be exact")
        if not filename.endswith(".whl") or "/" in filename or "\\" in filename:
            raise WeatherNextRuntimeMaterializationError("runtime package filename must be a basename wheel")
        if not _is_sha256(digest):
            raise WeatherNextRuntimeMaterializationError("runtime package SHA-256 invalid")
        if filename in filenames:
            raise WeatherNextRuntimeMaterializationError("duplicate runtime wheel filename")
        names.append(name)
        filenames.add(filename)
    if names != sorted(names) or len(set(names)) != len(names):
        raise WeatherNextRuntimeMaterializationError("runtime package names must be sorted and unique")
    if "google-cloud-bigquery" not in names:
        raise WeatherNextRuntimeMaterializationError("google-cloud-bigquery missing from runtime closure")

    calculated = closure_digest(packages)
    if value.get("closure_sha256") != calculated or not _is_sha256(calculated):
        raise WeatherNextRuntimeMaterializationError("runtime closure digest mismatch")
    return value


def validate_artifact_receipt(
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
    lock: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if not _is_git_sha(expected_source_sha) or receipt.source_sha != expected_source_sha:
        raise WeatherNextRuntimeMaterializationError("artifact source SHA mismatch")
    lock = lock or load_runtime_lock()
    if receipt.closure_sha256 != lock["closure_sha256"]:
        raise WeatherNextRuntimeMaterializationError("artifact closure digest mismatch")
    if not _is_sha256(receipt.artifact_sha256):
        raise WeatherNextRuntimeMaterializationError("artifact SHA-256 invalid")
    if receipt.artifact_size_bytes <= 0 or receipt.artifact_size_bytes > MAX_ARTIFACT_BYTES:
        raise WeatherNextRuntimeMaterializationError("artifact size outside bounded limit")
    if receipt.artifact_format != ARTIFACT_FORMAT:
        raise WeatherNextRuntimeMaterializationError("artifact format mismatch")
    expected = (
        TARGET_OS,
        TARGET_ARCH,
        TARGET_PYTHON_VERSION,
        TARGET_PYTHON_ABI,
        TARGET_PIP_PLATFORM,
    )
    observed = (
        receipt.target_os,
        receipt.target_architecture,
        receipt.target_python_version,
        receipt.target_python_abi,
        receipt.target_platform,
    )
    if observed != expected:
        raise WeatherNextRuntimeMaterializationError("artifact platform or Python target mismatch")
    return {
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "artifact_size_bytes": receipt.artifact_size_bytes,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "artifact_identity_accepted": True,
    }


def classify_runtime_identity(
    observed: ObservedRuntimeIdentity,
    *,
    receipt: RuntimeArtifactReceipt,
) -> str:
    if not observed.present:
        return "runtime_materialization_required"
    expected = (
        receipt.source_sha,
        receipt.closure_sha256,
        receipt.artifact_sha256,
        receipt.target_python_abi,
        receipt.target_platform,
    )
    actual = (
        observed.source_sha,
        observed.closure_sha256,
        observed.artifact_sha256,
        observed.target_python_abi,
        observed.target_platform,
    )
    if actual != expected:
        return "runtime_identity_mismatch"
    return "runtime_materialization_source_ready"


def build_materialization_plan(
    authority_id: str,
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
) -> Mapping[str, Any]:
    if authority_id == PUBLIC_RUNTIME_OPERATION_ID:
        raise WeatherNextRuntimeMaterializationError("public Weather authority cannot dispatch private runtime materialization")
    if authority_id != PRIVATE_CONTRACT_ID:
        raise WeatherNextRuntimeMaterializationError("private WeatherNext authority mismatch")
    validated = validate_artifact_receipt(receipt, expected_source_sha=expected_source_sha)
    artifact_path = ARTIFACT_CACHE_ROOT / f"{receipt.artifact_sha256}.tar"
    staging_path = RUNTIME_BASE.parent / f".{RUNTIME_BASE.name}.{receipt.artifact_sha256}.partial"
    return {
        "operation_id": OPERATION_ID,
        "mutation_class": MUTATION_CLASS,
        "artifact_path": str(artifact_path),
        "runtime_path": str(RUNTIME_BASE),
        "staging_path": str(staging_path),
        "source_sha": validated["source_sha"],
        "closure_sha256": validated["closure_sha256"],
        "artifact_sha256": validated["artifact_sha256"],
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "network_access": False,
        "package_manager": False,
        "credential_binding": False,
        "project_binding": False,
        "analytics_hub_link": False,
        "bigquery_access": False,
        "sqlite_write": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_posix_parts(name: str) -> tuple[str, ...]:
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise WeatherNextRuntimeMaterializationError("archive member path rejected")
    return pure.parts


def _wheel_target(parts: tuple[str, ...]) -> tuple[str, ...]:
    for index, part in enumerate(parts):
        if part.endswith(".data"):
            if index + 1 >= len(parts) or parts[index + 1] not in {"purelib", "platlib"}:
                raise WeatherNextRuntimeMaterializationError("wheel .data target outside site-packages")
            mapped = parts[index + 2 :]
            if not mapped:
                raise WeatherNextRuntimeMaterializationError("empty wheel .data payload")
            return mapped
    return parts


def _extract_wheel_bytes(data: bytes, site_packages: Path, occupied: set[Path]) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), mode="r")
    except zipfile.BadZipFile as exc:
        raise WeatherNextRuntimeMaterializationError("runtime wheel is not a valid ZIP archive") from exc
    with archive:
        for info in archive.infolist():
            parts = _safe_posix_parts(info.filename)
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(unix_mode):
                raise WeatherNextRuntimeMaterializationError("wheel symlinks are forbidden")
            mapped = _wheel_target(parts)
            target = site_packages.joinpath(*mapped)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target in occupied:
                raise WeatherNextRuntimeMaterializationError("duplicate runtime wheel target")
            occupied.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("xb") as destination:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    destination.write(block)
            os.chmod(target, 0o644)


def _rename_noreplace(source: Path, target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise WeatherNextRuntimeMaterializationError("renameat2 is required for fail-closed activation")
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(target),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise WeatherNextRuntimeMaterializationError("runtime target already exists")
        raise WeatherNextRuntimeMaterializationError(f"atomic runtime activation failed: errno={error_number}")


def _load_archive_payload(
    artifact_path: Path,
    lock: Mapping[str, Any],
    receipt: RuntimeArtifactReceipt,
) -> tuple[Mapping[str, Any], dict[str, bytes]]:
    expected_files = {item["filename"]: item for item in lock["packages"]}
    wheels: dict[str, bytes] = {}
    metadata: Mapping[str, Any] | None = None
    try:
        archive = tarfile.open(artifact_path, mode="r:")
    except (tarfile.TarError, OSError) as exc:
        raise WeatherNextRuntimeMaterializationError("runtime artifact tar is unreadable") from exc
    with archive:
        for member in archive.getmembers():
            parts = _safe_posix_parts(member.name)
            if member.issym() or member.islnk() or not member.isfile():
                raise WeatherNextRuntimeMaterializationError("runtime artifact contains non-regular entries")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise WeatherNextRuntimeMaterializationError("runtime artifact member unreadable")
            if parts == (ARCHIVE_METADATA_NAME,):
                if member.size > MAX_METADATA_BYTES or metadata is not None:
                    raise WeatherNextRuntimeMaterializationError("runtime artifact metadata invalid")
                try:
                    value = json.loads(extracted.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise WeatherNextRuntimeMaterializationError("runtime artifact metadata malformed") from exc
                if not isinstance(value, dict):
                    raise WeatherNextRuntimeMaterializationError("runtime artifact metadata must be an object")
                metadata = value
                continue
            if len(parts) != 2 or parts[0] != "wheelhouse":
                raise WeatherNextRuntimeMaterializationError("unexpected runtime artifact member")
            filename = parts[1]
            package = expected_files.get(filename)
            if package is None or filename in wheels:
                raise WeatherNextRuntimeMaterializationError("unexpected or duplicate runtime wheel")
            if member.size <= 0 or member.size > MAX_ARTIFACT_BYTES:
                raise WeatherNextRuntimeMaterializationError("runtime wheel size invalid")
            data = extracted.read()
            if hashlib.sha256(data).hexdigest() != package["sha256"]:
                raise WeatherNextRuntimeMaterializationError("runtime wheel digest mismatch")
            wheels[filename] = data
    if metadata is None or set(wheels) != set(expected_files):
        raise WeatherNextRuntimeMaterializationError("runtime artifact closure incomplete")
    expected_metadata = {
        "schema": "rozkalns-weather.weathernext-private-runtime-artifact.v1",
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "target_os": TARGET_OS,
        "target_architecture": TARGET_ARCH,
        "target_python_version": TARGET_PYTHON_VERSION,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "package_count": len(lock["packages"]),
    }
    if metadata != expected_metadata:
        raise WeatherNextRuntimeMaterializationError("runtime artifact metadata mismatch")
    return metadata, wheels


def materialize_reviewed_runtime(
    authority_id: str,
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
) -> Mapping[str, Any]:
    """Materialize only the reviewed offline wheelhouse. This function is not wired into LIVE execution."""
    plan = build_materialization_plan(authority_id, receipt, expected_source_sha=expected_source_sha)
    lock = load_runtime_lock()
    artifact_path = Path(plan["artifact_path"])
    runtime_path = Path(plan["runtime_path"])
    staging_path = Path(plan["staging_path"])

    try:
        artifact_stat = artifact_path.lstat()
    except FileNotFoundError as exc:
        raise WeatherNextRuntimeMaterializationError("reviewed runtime artifact is absent") from exc
    if stat.S_ISLNK(artifact_stat.st_mode) or not stat.S_ISREG(artifact_stat.st_mode):
        raise WeatherNextRuntimeMaterializationError("reviewed runtime artifact must be a regular file")
    if artifact_stat.st_size != receipt.artifact_size_bytes or artifact_stat.st_size > MAX_ARTIFACT_BYTES:
        raise WeatherNextRuntimeMaterializationError("reviewed runtime artifact size mismatch")
    if _hash_file(artifact_path) != receipt.artifact_sha256:
        raise WeatherNextRuntimeMaterializationError("reviewed runtime artifact digest mismatch")
    if runtime_path.exists() or staging_path.exists():
        raise WeatherNextRuntimeMaterializationError("runtime target or prior partial staging already exists")

    _metadata, wheels = _load_archive_payload(artifact_path, lock, receipt)

    runtime_path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    staging_path.mkdir(mode=0o755)
    site_packages = staging_path / RUNTIME_SITE_PACKAGES_NAME
    site_packages.mkdir(mode=0o755)
    occupied: set[Path] = set()
    for package in lock["packages"]:
        _extract_wheel_bytes(wheels[package["filename"]], site_packages, occupied)

    marker = {
        "schema": "rozkalns-weather.weathernext-private-runtime-installed.v1",
        "operation_id": OPERATION_ID,
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "package_count": len(lock["packages"]),
        "credential_binding": False,
        "project_binding": False,
        "analytics_hub_link": False,
        "bigquery_access": False,
        "sqlite_write": False,
    }
    marker_path = staging_path / RUNTIME_MARKER_NAME
    marker_path.write_text(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(marker_path, 0o644)
    _rename_noreplace(staging_path, runtime_path)
    return {
        "status": "runtime_materialized",
        "operation_id": OPERATION_ID,
        "mutation_class": MUTATION_CLASS,
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "later_credential_binding_required": True,
        "network_access_performed": False,
        "package_manager_performed": False,
        "automatic_cleanup_performed": False,
        "automatic_rollback_performed": False,
    }


def source_capability_summary() -> Mapping[str, Any]:
    lock = load_runtime_lock()
    return {
        "operation_id": OPERATION_ID,
        "private_contract_id": PRIVATE_CONTRACT_ID,
        "mutation_class": MUTATION_CLASS,
        "closure_sha256": lock["closure_sha256"],
        "package_count": lock["package_count"],
        "resolved_root": lock["resolved_root"],
        "target_os": TARGET_OS,
        "target_architecture": TARGET_ARCH,
        "target_python_version": TARGET_PYTHON_VERSION,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "artifact_format": ARTIFACT_FORMAT,
        "artifact_digest_required": True,
        "exact_source_sha_required": True,
        "offline_artifact_required": True,
        "network_install_authority": False,
        "package_manager_authority": False,
        "public_runtime_authority_reusable": False,
        "credential_binding_authorized": False,
        "project_binding_authorized": False,
        "analytics_hub_link_authorized": False,
        "read_only_bigquery_authorized": False,
        "sqlite_write_authorized": False,
        "host_wiring_enabled": False,
    }
