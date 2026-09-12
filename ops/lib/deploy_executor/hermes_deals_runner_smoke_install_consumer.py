from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Protocol

from .hermes_deals_runner_smoke_install import (
    HELPER_SHA256,
    INSTALL_TARGET_ALIAS,
    LIVE_ENVELOPE_SCHEMA,
    LIVE_GATE_ID,
    OPERATION_ID,
    OWNER_NUMERIC_ID,
    REGISTRATION_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    SOURCE_SHA,
    validate_live_envelope,
)

MAX_AUTHORIZATION_AGE_SECONDS = 600
MAX_REVALIDATION_TIME_DRIFT_SECONDS = 30
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RunnerSmokeInstallConsumerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalRunnerSmokeInstallEvidence:
    authorization_issue_number: int
    authorization_created_at: str
    github_server_time: str
    owner_numeric_id: int
    owner_type: str
    app_authored: bool
    operation_id: str
    live_gate_id: str
    target_alias: str
    source_repository: str
    source_repository_id: int
    source_sha: str
    rpi5_main_sha: str
    rpi5_main_merged_reachable: bool
    rpi5_main_ci_success: bool
    hermes_source_merged_reachable: bool
    hermes_source_ci_success: bool
    helper_sha256: str
    registration_sha256: str
    request_body_sha256: str
    identical_body_refetch: bool
    ttl_valid: bool
    replay_available: bool
    live_authorized: bool
    rollback_policy: str


class CanonicalRunnerSmokeInstallRevalidator(Protocol):
    def revalidate(
        self,
        authorization_issue_number: int,
    ) -> CanonicalRunnerSmokeInstallEvidence: ...


def _fail(message: str) -> None:
    raise RunnerSmokeInstallConsumerError(message)


def _positive_issue_number(value: Any) -> int:
    if type(value) is not int or value <= 0:
        _fail("authorization_issue_number must be a positive integer")
    return value


def _github_time(value: Any, field: str) -> datetime:
    if type(value) is not str:
        _fail(f"{field} must be canonical GitHub UTC RFC3339")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise RunnerSmokeInstallConsumerError(
            f"{field} must be canonical GitHub UTC RFC3339"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{field} must be canonical GitHub UTC RFC3339")
    return parsed


def _validate_evidence(
    authorization_issue_number: int,
    evidence: CanonicalRunnerSmokeInstallEvidence,
) -> None:
    if not isinstance(evidence, CanonicalRunnerSmokeInstallEvidence):
        _fail("canonical revalidator returned unsupported evidence")
    if evidence.authorization_issue_number != authorization_issue_number:
        _fail("canonical authorization issue identity drifted")

    authorization_time = _github_time(
        evidence.authorization_created_at,
        "authorization_created_at",
    )
    github_time = _github_time(evidence.github_server_time, "github_server_time")
    age = (github_time - authorization_time).total_seconds()
    if age < -30 or age > MAX_AUTHORIZATION_AGE_SECONDS:
        _fail("canonical authorization TTL is outside the allowed window")

    exact = {
        "owner_numeric_id": (evidence.owner_numeric_id, OWNER_NUMERIC_ID),
        "owner_type": (evidence.owner_type, "User"),
        "operation_id": (evidence.operation_id, OPERATION_ID),
        "live_gate_id": (evidence.live_gate_id, LIVE_GATE_ID),
        "target_alias": (evidence.target_alias, INSTALL_TARGET_ALIAS),
        "source_repository": (evidence.source_repository, SOURCE_REPOSITORY),
        "source_repository_id": (evidence.source_repository_id, SOURCE_REPOSITORY_ID),
        "source_sha": (evidence.source_sha, SOURCE_SHA),
        "helper_sha256": (evidence.helper_sha256, HELPER_SHA256),
        "registration_sha256": (evidence.registration_sha256, REGISTRATION_SHA256),
        "rollback_policy": (evidence.rollback_policy, "NONE"),
    }
    for field, (actual, expected) in exact.items():
        if actual != expected:
            _fail(f"canonical {field} drifted")

    if evidence.app_authored is not False:
        _fail("canonical authorization must not be app-authored")
    if type(evidence.rpi5_main_sha) is not str or _SHA40_RE.fullmatch(evidence.rpi5_main_sha) is None:
        _fail("canonical RPi5_main SHA is invalid")
    if type(evidence.request_body_sha256) is not str or _SHA256_RE.fullmatch(evidence.request_body_sha256) is None:
        _fail("canonical request body SHA-256 is invalid")

    for field in (
        "rpi5_main_merged_reachable",
        "rpi5_main_ci_success",
        "hermes_source_merged_reachable",
        "hermes_source_ci_success",
        "identical_body_refetch",
        "ttl_valid",
        "replay_available",
        "live_authorized",
    ):
        if getattr(evidence, field) is not True:
            _fail(f"canonical required proof failed: {field}")


def _envelope(evidence: CanonicalRunnerSmokeInstallEvidence) -> dict[str, Any]:
    value = {
        "schema": LIVE_ENVELOPE_SCHEMA,
        "authorization_issue_number": evidence.authorization_issue_number,
        "owner_numeric_id": evidence.owner_numeric_id,
        "operation_id": evidence.operation_id,
        "live_gate_id": evidence.live_gate_id,
        "target_alias": evidence.target_alias,
        "source_repository": evidence.source_repository,
        "source_repository_id": evidence.source_repository_id,
        "source_sha": evidence.source_sha,
        "rpi5_main_sha": evidence.rpi5_main_sha,
        "rpi5_main_merged_reachable": evidence.rpi5_main_merged_reachable,
        "rpi5_main_ci_success": evidence.rpi5_main_ci_success,
        "hermes_source_merged_reachable": evidence.hermes_source_merged_reachable,
        "hermes_source_ci_success": evidence.hermes_source_ci_success,
        "helper_sha256": evidence.helper_sha256,
        "registration_sha256": evidence.registration_sha256,
        "request_body_sha256": evidence.request_body_sha256,
        "identical_body_refetch": evidence.identical_body_refetch,
        "ttl_valid": evidence.ttl_valid,
        "replay_available": evidence.replay_available,
        "live_authorized": evidence.live_authorized,
        "rollback_policy": evidence.rollback_policy,
    }
    validate_live_envelope(value)
    return value


def prepare_install_live_envelope(
    authorization_issue_number: int,
    *,
    canonical_revalidator: CanonicalRunnerSmokeInstallRevalidator,
) -> Mapping[str, Any]:
    """Re-derive one canonical install envelope without executing or consuming it."""

    issue_number = _positive_issue_number(authorization_issue_number)
    first = canonical_revalidator.revalidate(issue_number)
    _validate_evidence(issue_number, first)

    final = canonical_revalidator.revalidate(issue_number)
    _validate_evidence(issue_number, final)

    stable_fields = tuple(
        field.name
        for field in fields(CanonicalRunnerSmokeInstallEvidence)
        if field.name != "github_server_time"
    )
    if any(getattr(first, name) != getattr(final, name) for name in stable_fields):
        _fail("canonical evidence drifted during install-envelope revalidation")

    first_time = _github_time(first.github_server_time, "github_server_time")
    final_time = _github_time(final.github_server_time, "github_server_time")
    drift = (final_time - first_time).total_seconds()
    if not 0 <= drift <= MAX_REVALIDATION_TIME_DRIFT_SECONDS:
        _fail("canonical GitHub time drifted during install-envelope revalidation")

    return _envelope(final)


def source_readiness() -> Mapping[str, Any]:
    return {
        "consumer_implemented": True,
        "implementation_issue": 481,
        "request_authority": ("authorization_issue_number",),
        "canonical_live_envelope_schema": LIVE_ENVELOPE_SCHEMA,
        "max_authorization_age_seconds": MAX_AUTHORIZATION_AGE_SECONDS,
        "max_revalidation_time_drift_seconds": MAX_REVALIDATION_TIME_DRIFT_SECONDS,
        "mutation_boundary": "hermes_deals_runner_smoke_install.apply_install",
        "external_apply_entrypoint_enabled": False,
        "runtime_activation_enabled": False,
        "global_executor_execution_enabled": False,
        "authorization_consumed": False,
        "production_mutation_started": False,
    }
