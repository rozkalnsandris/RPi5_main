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

OPERATION_ID = "rozkalns-weather.weathernext-private-gcs-runtime-materialization.v1"
PRIVATE_CONTRACT_ID = "rozkalns-weather.weathernext-private-gcs-first-access.v1"
BIGQUERY_CONTRACT_ID = "rozkalns-weather.weathernext-private-bigquery-first-access.v1"
PUBLIC_RUNTIME_OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
MUTATION_CLASS = "weathernext_private_gcs_runtime_materialization"

WEATHER_SOURCE_SHA = "b7f04385ff33ab613a30e0ab89c734aa4ba444ca"
WEATHER_EXTRA = "weathernext-gcs"
UPSTREAM_REQUIREMENTS = (
    "obstore>=0.11.1,<0.12",
    "xarray>=2026.9,<2027",
    "zarr>=3.4,<4",
)
REQUIRED_ROOTS = ("obstore", "xarray", "zarr")

TARGET_OS = "linux"
TARGET_ARCH = "aarch64"
TARGET_PYTHON_VERSION = "3.13"
TARGET_PYTHON_ABI = "cp313"
TARGET_PIP_PLATFORM = "manylinux_2_28_aarch64"
ACCEPTED_ABI = ("cp313", "abi3", "none")
ACCEPTED_WHEEL_PLATFORMS = (
    "manylinux_2_28_aarch64",
    "manylinux_2_27_aarch64",
    "manylinux_2_26_aarch64",
    "manylinux_2_25_aarch64",
    "manylinux_2_24_aarch64",
    "manylinux_2_23_aarch64",
    "manylinux_2_22_aarch64",
    "manylinux_2_21_aarch64",
    "manylinux_2_20_aarch64",
    "manylinux_2_19_aarch64",
    "manylinux_2_18_aarch64",
    "manylinux_2_17_aarch64",
    "manylinux2014_aarch64",
)
ARTIFACT_FORMAT = "normalized-wheelhouse-tar-v1"
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
FIXED_DIRECTORY_MODE = 0o755

LOCK_PATH = Path(__file__).with_name("weather_private_gcs_runtime_lock.json")
ARTIFACT_CACHE_ROOT = Path("/var/lib/rpi5-deploy/weather-private-gcs-runtime/artifacts")
RUNTIME_BASE = Path("/var/lib/rpi5-deploy/weather-private-gcs-runtime/runtime")
RUNTIME_SITE_PACKAGES_NAME = "site-packages"
RUNTIME_MARKER_NAME = "runtime-materialization.json"
ARCHIVE_METADATA_NAME = "runtime-closure.json"

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class WeatherNextGCSRuntimeMaterializationError(RuntimeError):
    """Raised when the private GCS runtime capability cannot proceed safely."""


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
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime lock is unreadable") from exc
    if not isinstance(value, dict):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime lock must be a JSON object")
    validate_runtime_lock(value)
    return value


def validate_runtime_lock(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if value.get("schema") != "rozkalns-weather.weathernext-private-gcs-runtime-lock.v1":
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime lock schema mismatch")
    if value.get("operation_id") != OPERATION_ID:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime lock operation mismatch")
    if value.get("weather_source_sha") != WEATHER_SOURCE_SHA:
        raise WeatherNextGCSRuntimeMaterializationError("Weather source prerequisite changed")
    if value.get("weather_extra") != WEATHER_EXTRA:
        raise WeatherNextGCSRuntimeMaterializationError("Weather GCS optional extra changed")
    if tuple(value.get("upstream_requirements") or ()) != UPSTREAM_REQUIREMENTS:
        raise WeatherNextGCSRuntimeMaterializationError("Weather GCS root requirements changed")
    if value.get("live_network_install_allowed") is not False:
        raise WeatherNextGCSRuntimeMaterializationError("live network install must remain disabled")
    if value.get("live_package_manager_install_allowed") is not False:
        raise WeatherNextGCSRuntimeMaterializationError("live package-manager install must remain disabled")
    if value.get("credential_material_in_lock") is not False:
        raise WeatherNextGCSRuntimeMaterializationError("credential material is forbidden in GCS runtime lock")
    if value.get("private_google_identity_in_lock") is not False:
        raise WeatherNextGCSRuntimeMaterializationError("private Google identity is forbidden in GCS runtime lock")

    target = value.get("target")
    expected_target = {
        "os": TARGET_OS,
        "architecture": TARGET_ARCH,
        "python_version": TARGET_PYTHON_VERSION,
        "python_abi": TARGET_PYTHON_ABI,
        "pip_platform": TARGET_PIP_PLATFORM,
        "accepted_abi": list(ACCEPTED_ABI),
        "accepted_wheel_platforms": list(ACCEPTED_WHEEL_PLATFORMS),
    }
    if target != expected_target:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime target mismatch")

    packages = value.get("packages")
    if not isinstance(packages, list) or not packages:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package set missing")
    if value.get("package_count") != len(packages):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package count mismatch")

    names: list[str] = []
    filenames: set[str] = set()
    versions: dict[str, str] = {}
    for item in packages:
        if not isinstance(item, dict) or set(item) != {"name", "version", "filename", "sha256"}:
            raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package entry keys mismatch")
        name = str(item["name"])
        version = str(item["version"])
        filename = str(item["filename"])
        digest = str(item["sha256"])
        if not name or any(token in version for token in ("<", ">", "=", "*", "~", " ")):
            raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package versions must be exact")
        if not filename.endswith(".whl") or "/" in filename or "\\" in filename:
            raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package filename must be a basename wheel")
        if not _is_sha256(digest):
            raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package SHA-256 invalid")
        if filename in filenames:
            raise WeatherNextGCSRuntimeMaterializationError("duplicate GCS runtime wheel filename")
        names.append(name)
        versions[name] = version
        filenames.add(filename)
    if names != sorted(names) or len(set(names)) != len(names):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime package names must be sorted and unique")
    if any(root not in versions for root in REQUIRED_ROOTS):
        raise WeatherNextGCSRuntimeMaterializationError("required GCS runtime root package missing")
    if "google-cloud-bigquery" in versions:
        raise WeatherNextGCSRuntimeMaterializationError("BigQuery package is forbidden in GCS runtime closure")
    if value.get("resolved_roots") != {root: versions[root] for root in REQUIRED_ROOTS}:
        raise WeatherNextGCSRuntimeMaterializationError("resolved GCS root versions mismatch")

    calculated = closure_digest(packages)
    if value.get("closure_sha256") != calculated or not _is_sha256(calculated):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime closure digest mismatch")
    return value


def validate_artifact_receipt(
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
    lock: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if not _is_git_sha(expected_source_sha) or receipt.source_sha != expected_source_sha:
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact source SHA mismatch")
    lock = lock or load_runtime_lock()
    if receipt.closure_sha256 != lock["closure_sha256"]:
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact closure digest mismatch")
    if not _is_sha256(receipt.artifact_sha256):
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact SHA-256 invalid")
    if receipt.artifact_size_bytes <= 0 or receipt.artifact_size_bytes > MAX_ARTIFACT_BYTES:
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact size outside bounded limit")
    if receipt.artifact_format != ARTIFACT_FORMAT:
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact format mismatch")
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
        raise WeatherNextGCSRuntimeMaterializationError("GCS artifact platform or Python target mismatch")
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
        return "gcs_runtime_materialization_required"
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
        return "gcs_runtime_identity_mismatch"
    return "gcs_runtime_materialization_source_ready"


def build_materialization_plan(
    authority_id: str,
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
) -> Mapping[str, Any]:
    if authority_id == PUBLIC_RUNTIME_OPERATION_ID:
        raise WeatherNextGCSRuntimeMaterializationError("public Weather authority cannot dispatch private GCS runtime")
    if authority_id == BIGQUERY_CONTRACT_ID:
        raise WeatherNextGCSRuntimeMaterializationError("BigQuery authority cannot dispatch private GCS runtime")
    if authority_id != PRIVATE_CONTRACT_ID:
        raise WeatherNextGCSRuntimeMaterializationError("private GCS WeatherNext authority mismatch")
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
        "google_gcs_access": False,
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
        raise WeatherNextGCSRuntimeMaterializationError("GCS archive member path rejected")
    return pure.parts


def _wheel_target(parts: tuple[str, ...]) -> tuple[str, ...]:
    for index, part in enumerate(parts):
        if part.endswith(".data"):
            if index + 1 >= len(parts) or parts[index + 1] not in {"purelib", "platlib"}:
                raise WeatherNextGCSRuntimeMaterializationError("GCS wheel .data target outside site-packages")
            mapped = parts[index + 2 :]
            if not mapped:
                raise WeatherNextGCSRuntimeMaterializationError("empty GCS wheel .data payload")
            return mapped
    return parts


def _chmod_directory_exact(path: Path) -> None:
    try:
        st = path.lstat()
    except OSError as exc:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime directory is unavailable") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime directory must be real")
    os.chmod(path, FIXED_DIRECTORY_MODE)


def _mkdir_directory_exact(path: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
    path.mkdir(parents=parents, mode=FIXED_DIRECTORY_MODE, exist_ok=exist_ok)
    _chmod_directory_exact(path)


def _mkdir_beneath_exact(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime directory escaped site-packages") from exc
    _chmod_directory_exact(root)
    current = root
    for part in relative.parts:
        current = current / part
        _mkdir_directory_exact(current, exist_ok=True)


def _extract_wheel_bytes(data: bytes, site_packages: Path, occupied: set[Path]) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), mode="r")
    except zipfile.BadZipFile as exc:
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime wheel is not a valid ZIP archive") from exc
    with archive:
        for info in archive.infolist():
            parts = _safe_posix_parts(info.filename)
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(unix_mode):
                raise WeatherNextGCSRuntimeMaterializationError("GCS wheel symlinks are forbidden")
            mapped = _wheel_target(parts)
            target = site_packages.joinpath(*mapped)
            if info.is_dir():
                _mkdir_beneath_exact(site_packages, target)
                continue
            if target in occupied:
                raise WeatherNextGCSRuntimeMaterializationError("duplicate GCS runtime wheel target")
            occupied.add(target)
            _mkdir_beneath_exact(site_packages, target.parent)
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
        raise WeatherNextGCSRuntimeMaterializationError("renameat2 is required for fail-closed GCS activation")
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
            raise WeatherNextGCSRuntimeMaterializationError("GCS runtime target already exists")
        raise WeatherNextGCSRuntimeMaterializationError(
            f"atomic GCS runtime activation failed: errno={error_number}"
        )


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
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact tar is unreadable") from exc
    with archive:
        for member in archive.getmembers():
            parts = _safe_posix_parts(member.name)
            if member.issym() or member.islnk() or not member.isfile():
                raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact contains non-regular entries")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact member unreadable")
            if parts == (ARCHIVE_METADATA_NAME,):
                if member.size > MAX_METADATA_BYTES or metadata is not None:
                    raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact metadata invalid")
                try:
                    value = json.loads(extracted.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact metadata malformed") from exc
                if not isinstance(value, dict):
                    raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact metadata must be an object")
                metadata = value
                continue
            if len(parts) != 2 or parts[0] != "wheelhouse":
                raise WeatherNextGCSRuntimeMaterializationError("unexpected GCS runtime artifact member")
            filename = parts[1]
            package = expected_files.get(filename)
            if package is None or filename in wheels:
                raise WeatherNextGCSRuntimeMaterializationError("unexpected or duplicate GCS runtime wheel")
            if member.size <= 0 or member.size > MAX_ARTIFACT_BYTES:
                raise WeatherNextGCSRuntimeMaterializationError("GCS runtime wheel size invalid")
            data = extracted.read()
            if hashlib.sha256(data).hexdigest() != package["sha256"]:
                raise WeatherNextGCSRuntimeMaterializationError("GCS runtime wheel digest mismatch")
            wheels[filename] = data
    if metadata is None or set(wheels) != set(expected_files):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact closure incomplete")
    expected_metadata = {
        "schema": "rozkalns-weather.weathernext-private-gcs-runtime-artifact.v1",
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
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime artifact metadata mismatch")
    return metadata, wheels


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def materialize_reviewed_runtime(
    authority_id: str,
    receipt: RuntimeArtifactReceipt,
    *,
    expected_source_sha: str,
) -> Mapping[str, Any]:
    """Materialize only the reviewed offline GCS wheelhouse; not wired into LIVE execution."""

    plan = build_materialization_plan(
        authority_id,
        receipt,
        expected_source_sha=expected_source_sha,
    )
    lock = load_runtime_lock()
    artifact_path = Path(plan["artifact_path"])
    runtime_path = Path(plan["runtime_path"])
    staging_path = Path(plan["staging_path"])

    try:
        artifact_stat = artifact_path.lstat()
    except FileNotFoundError as exc:
        raise WeatherNextGCSRuntimeMaterializationError("reviewed GCS runtime artifact is absent") from exc
    if stat.S_ISLNK(artifact_stat.st_mode) or not stat.S_ISREG(artifact_stat.st_mode):
        raise WeatherNextGCSRuntimeMaterializationError("reviewed GCS runtime artifact must be regular")
    if artifact_stat.st_size != receipt.artifact_size_bytes or artifact_stat.st_size > MAX_ARTIFACT_BYTES:
        raise WeatherNextGCSRuntimeMaterializationError("reviewed GCS runtime artifact size mismatch")
    if _hash_file(artifact_path) != receipt.artifact_sha256:
        raise WeatherNextGCSRuntimeMaterializationError("reviewed GCS runtime artifact digest mismatch")
    if _present(runtime_path) or _present(staging_path):
        raise WeatherNextGCSRuntimeMaterializationError("GCS runtime target or prior partial staging already exists")

    _metadata, wheels = _load_archive_payload(artifact_path, lock, receipt)
    _mkdir_directory_exact(runtime_path.parent, parents=True, exist_ok=True)
    _mkdir_directory_exact(staging_path)
    site_packages = staging_path / RUNTIME_SITE_PACKAGES_NAME
    _mkdir_directory_exact(site_packages)
    occupied: set[Path] = set()
    for package in lock["packages"]:
        _extract_wheel_bytes(wheels[package["filename"]], site_packages, occupied)

    marker = {
        "schema": "rozkalns-weather.weathernext-private-gcs-runtime-installed.v1",
        "operation_id": OPERATION_ID,
        "source_sha": receipt.source_sha,
        "closure_sha256": receipt.closure_sha256,
        "artifact_sha256": receipt.artifact_sha256,
        "target_python_abi": TARGET_PYTHON_ABI,
        "target_platform": TARGET_PIP_PLATFORM,
        "package_count": len(lock["packages"]),
        "credential_binding": False,
        "google_gcs_access": False,
        "project_binding": False,
        "analytics_hub_link": False,
        "bigquery_access": False,
        "sqlite_write": False,
    }
    marker_path = staging_path / RUNTIME_MARKER_NAME
    marker_path.write_text(
        json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(marker_path, 0o644)
    _rename_noreplace(staging_path, runtime_path)
    return {
        "status": "gcs_runtime_materialized",
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
        "google_gcs_access_performed": False,
        "bigquery_access_performed": False,
        "sqlite_write_performed": False,
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
        "resolved_roots": dict(lock["resolved_roots"]),
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
        "bigquery_authority_reusable": False,
        "credential_binding_authorized": False,
        "google_gcs_access_authorized": False,
        "project_binding_authorized": False,
        "analytics_hub_link_authorized": False,
        "read_only_bigquery_authorized": False,
        "sqlite_write_authorized": False,
        "host_wiring_enabled": False,
    }
