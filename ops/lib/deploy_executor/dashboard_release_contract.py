from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

OPERATION_ID = "dashboard-rpi5.production-release.v1"
ADAPTER_ID = OPERATION_ID
SOURCE_REPOSITORY = "rozkalnsandris/dashboard_RPi5"
TARGET_ALIAS = "dashboard-rpi5-production-release"
BASELINE_KIND = "dashboard-release-plan.v1"
ROLLBACK_POLICY = "NONE"
PRODUCTION_ROOT = PurePosixPath("/opt/dashboard_RPi5")
CANDIDATE_ROOT = PurePosixPath("/var/lib/rozkalns-dashboard-release-candidates")
CONTROLLER_RELATIVE_PATH = PurePosixPath("tools/production-release-controller.mjs")
ACTIVATION_ACK = "I_AUTHORIZED_DASHBOARD_RPI5_PRODUCTION_RELEASE_ACTIVATION"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BASELINE_RE = re.compile(
    r"^current=(?P<current>none|[0-9a-f]{40});candidate=(?P<candidate>[0-9a-f]{64})$"
)
MUTATION_BUDGET = (
    ("filesystem.apply-lock-lifecycle", 1),
    ("filesystem.release-materialization", 1),
    ("filesystem.current-pointer-swap", 1),
)
REQUIRED_EXCLUSIONS = frozenset({
    "database writes",
    "credential or permission changes",
    "package/systemd/service/Docker/network/Cloudflare mutation",
    "release deletion",
    "automatic retry/cleanup/rollback",
    "candidate-checkout JavaScript executed as root",
    "arbitrary command/path/argv/environment authority",
})


@dataclass(frozen=True)
class DashboardReleaseBaseline:
    current: str | None
    candidate_sha256: str


@dataclass(frozen=True)
class DashboardReleasePaths:
    controller: str
    candidate_root: str
    manifest: str


def _sha(value: str, where: str) -> str:
    if type(value) is not str or SHA_RE.fullmatch(value) is None:
        raise AdapterError(f"{where} must be exact lowercase 40-character SHA")
    return value


def parse_baseline(value: str) -> DashboardReleaseBaseline:
    if type(value) is not str:
        raise AdapterError("dashboard release baseline must be a string")
    match = BASELINE_RE.fullmatch(value)
    if match is None:
        raise AdapterError("dashboard release baseline format mismatch")
    current_token = match.group("current")
    return DashboardReleaseBaseline(
        current=None if current_token == "none" else current_token,
        candidate_sha256=match.group("candidate"),
    )


def derive_paths(source_sha: str, current_sha: str | None) -> DashboardReleasePaths:
    source = _sha(source_sha, "source SHA")
    if current_sha is None:
        raise AdapterError("dashboard release requires an existing reviewed current controller")
    current = _sha(current_sha, "expected current SHA")
    candidate_base = CANDIDATE_ROOT / source
    return DashboardReleasePaths(
        controller=str(PRODUCTION_ROOT / "releases" / current / CONTROLLER_RELATIVE_PATH),
        candidate_root=str(candidate_base / "source"),
        manifest=str(candidate_base / "candidate-manifest.json"),
    )


def validate_prepared(prepared: PreparedOperation) -> tuple[DashboardReleaseBaseline, DashboardReleasePaths]:
    if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
        raise AdapterError("dashboard release operation/adapter identity mismatch")
    if prepared.source_repository != SOURCE_REPOSITORY or prepared.target_alias != TARGET_ALIAS:
        raise AdapterError("dashboard release source/target mismatch")
    source_sha = _sha(prepared.source_sha, "source SHA")
    if prepared.rollback_policy != ROLLBACK_POLICY:
        raise AdapterError("dashboard release rollback policy must remain NONE")
    if prepared.mutation_budget != MUTATION_BUDGET:
        raise AdapterError("dashboard release mutation budget drift")
    if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
        raise AdapterError("dashboard release exclusion contract drift")
    if prepared.expected_baseline_kind != BASELINE_KIND:
        raise AdapterError("dashboard release baseline kind mismatch")
    baseline = parse_baseline(prepared.expected_baseline_value)
    if baseline.current == source_sha:
        raise AdapterError(
            "already-current operations=[] candidate cannot satisfy the P10 first-live mutation canary"
        )
    paths = derive_paths(source_sha, baseline.current)
    return baseline, paths


class DashboardProductionReleaseAdapter:
    adapter_id = ADAPTER_ID

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        baseline, paths = validate_prepared(prepared)
        expected_current = baseline.current or "none"
        return {
            "operation_id": OPERATION_ID,
            "adapter_id": ADAPTER_ID,
            "execution_enabled": prepared.execution_enabled,
            "privileged_dispatch_ready": False,
            "requires_separate_live_authorization": True,
            "source_sha": prepared.source_sha,
            "expected_current": expected_current,
            "expected_candidate_sha256": baseline.candidate_sha256,
            "controller": paths.controller,
            "candidate_root": paths.candidate_root,
            "manifest": paths.manifest,
            "apply_argv": (
                "/usr/bin/node",
                paths.controller,
                "--candidate-root", paths.candidate_root,
                "--manifest", paths.manifest,
                "--sha", prepared.source_sha,
                "--expected-current", expected_current,
                "--expected-candidate", baseline.candidate_sha256,
                "--apply",
                "--ack", ACTIVATION_ACK,
            ),
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        validate_prepared(prepared)
        raise AdapterError(
            "dashboard production release execution remains source-disabled; separate LIVE gate required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        baseline, _ = validate_prepared(prepared)
        return {
            "exact_current_release": prepared.source_sha,
            "expected_candidate_sha256": baseline.candidate_sha256,
            "previous_release_retained": True,
            "apply_lock_absent_on_success": True,
            "release_deletions": 0,
            "automatic_retry_cleanup_rollback": False,
        }
