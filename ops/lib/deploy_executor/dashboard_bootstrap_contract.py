from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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
INSTALLED_PACKAGE_ROOT = INSTALLED_LIBRARY_ROOT / "deploy_executor"

APPLY_LOCK_NAME = ".dashboard-release-controller.lock"
MANIFEST_MARKER = ".dashboard-production-candidate.json"
CONTROLLER_RELATIVE_PATH = "tools/production-release-controller.mjs"
MANIFEST_SCHEMA = "dashboard-rpi5.production-candidate.v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_FILES = 512
MAX_TOTAL_BYTES = 512 * 1024 * 1024
COPY_BUFFER_BYTES = 64 * 1024
MAX_TRUSTED_MODULE_BYTES = 256 * 1024
ROOT_UID = 0
ROOT_GID = 0
RELEASE_DIRECTORY_MODE = 0o755
RELEASE_FILE_MODE = 0o644
MARKER_MODE = 0o600
PREVERIFY_FILE_MODE = 0o600
TRUSTED_DIRECTORY_MODE = 0o755
TRUSTED_MODULE_MODE = 0o644
TRUSTED_ENTRYPOINT_MODE = 0o755

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


def __getattr__(name: str):
    """Keep the dormant source adapter API lazy and outside the root import closure."""
    if name == "DashboardHardenedControllerBootstrapAdapter":
        from .dashboard_bootstrap_adapter import DashboardHardenedControllerBootstrapAdapter

        return DashboardHardenedControllerBootstrapAdapter
    raise AttributeError(name)
