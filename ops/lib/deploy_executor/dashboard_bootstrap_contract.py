from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

OPERATION_ID = "dashboard-rpi5.hardened-controller-bootstrap.v1"
ADAPTER_ID = OPERATION_ID
SOURCE_REPOSITORY = "rozkalnsandris/dashboard_RPi5"
SOURCE_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
TARGET_ALIAS = "dashboard-rpi5-hardened-controller-bootstrap"
ROLLBACK_POLICY = "NONE"
HISTORICAL_CONTROLLER_BLOB = "c501bea57c0d5c35e7961ae1f1e5593a02268661"
HARDENED_CONTROLLER_BLOB = "c0566adb76e044632a4556dbefeb0f46839b4996"
BOOTSTRAP_ACK = "I_AUTHORIZED_DASHBOARD_RPI5_HARDENED_CONTROLLER_BOOTSTRAP"

PRODUCTION_ROOT = Path("/opt/dashboard_RPi5")
STAGING_ROOT = Path(f"/var/lib/rozkalns-deploy-executor/bootstrap/dashboard-rpi5/{SOURCE_SHA}")
CANDIDATE_ROOT = STAGING_ROOT / "source"
MANIFEST_PATH = STAGING_ROOT / "candidate-manifest.json"
INSTALLED_ENTRYPOINT = Path("/usr/local/sbin/rozkalns-dashboard-controller-bootstrap")
INSTALLED_LIBRARY_ROOT = Path("/usr/local/lib/rozkalns-deploy-executor")

APPLY_LOCK_NAME = ".dashboard-release-controller.lock"
MANIFEST_MARKER = ".dashboard-production-candidate.json"
CONTROLLER_RELATIVE_PATH = "tools/production-release-controller.mjs"
MANIFEST_SCHEMA = "dashboard-rpi5.production-candidate.v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_FILES = 512
MAX_TOTAL_BYTES = 512 * 1024 * 1024
COPY_BUFFER_BYTES = 64 * 1024
ROOT_UID = 0
ROOT_GID = 0
RELEASE_DIRECTORY_MODE = 0o755
RELEASE_FILE_MODE = 0o644
MARKER_MODE = 0o600
PREVERIFY_FILE_MODE = 0o600

MUTATION_BUDGET = (
    ("dashboard.bootstrap.apply-lock", 1),
    ("dashboard.bootstrap.release-materialization", 1),
    ("dashboard.bootstrap.current-pointer-swap", 1),
)
REQUIRED_EXCLUSIONS = frozenset(
    {
        "generic privileged shell",
        "arbitrary source path or argv authority",
        "candidate JavaScript execution as root",
        "in-place patch of current release",
        "package/service/systemd/Docker/network/credential mutation",
        "release deletion or automatic rollback",
        "automatic retry or cleanup after release mutation starts",
    }
)
REQUIRED_DEPENDENCIES = frozenset(
    {
        f"dashboard-candidate-sha:{SOURCE_SHA}",
        f"historical-controller-blob:{HISTORICAL_CONTROLLER_BLOB}",
        f"hardened-controller-blob:{HARDENED_CONTROLLER_BLOB}",
        "dashboard-candidate-manifest:v1",
        "bootstrap-live-root-authorization:separate",
        "bootstrap-source-installation:separate",
    }
)


class DashboardBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapPaths:
    production_root: Path = PRODUCTION_ROOT
    staging_root: Path = STAGING_ROOT
    candidate_root: Path = CANDIDATE_ROOT
    manifest_path: Path = MANIFEST_PATH


@dataclass(frozen=True)
class CandidateEntry:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class CandidateManifest:
    source_sha: str
    candidate_sha256: str
    total_bytes: int
    files: tuple[CandidateEntry, ...]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class BootstrapReceipt:
    status: str
    source_sha: str
    previous_release: str
    current_release: str
    candidate_sha256: str
    historical_controller_blob: str
    hardened_controller_blob: str
    releases_deleted: int
    p10_apply_executed: bool


class DashboardHardenedControllerBootstrapAdapter:
    """Dormant source contract; it never dispatches the root bootstrap helper."""

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("Dashboard bootstrap operation identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("Dashboard bootstrap source adapter must remain execution-disabled")
        if prepared.source_repository != SOURCE_REPOSITORY or prepared.source_sha != SOURCE_SHA:
            raise AdapterError("Dashboard bootstrap source identity mismatch")
        if prepared.target_alias != TARGET_ALIAS or prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("Dashboard bootstrap target/rollback mismatch")
        if prepared.mutation_budget != MUTATION_BUDGET:
            raise AdapterError("Dashboard bootstrap mutation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("Dashboard bootstrap required exclusions are missing")
        if not REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("Dashboard bootstrap dependency binding mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": ADAPTER_ID,
            "source_sha": SOURCE_SHA,
            "target_alias": TARGET_ALIAS,
            "historical_controller_blob": HISTORICAL_CONTROLLER_BLOB,
            "hardened_controller_blob": HARDENED_CONTROLLER_BLOB,
            "candidate_root": str(CANDIDATE_ROOT),
            "manifest_path": str(MANIFEST_PATH),
            "installed_entrypoint": str(INSTALLED_ENTRYPOINT),
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "live_authorized": False,
            "result": "SOURCE_BOOTSTRAP_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Dashboard bootstrap adapter is source-only and execution-disabled; a separate LIVE/root gate is required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "execution_enabled": False,
            "required_current_controller_blob": HARDENED_CONTROLLER_BLOB,
            "required_current_source_sha": SOURCE_SHA,
            "releases_deleted": 0,
            "p10_apply_executed": False,
        }
