from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .p9_canary import BaselineEvidence, GovernanceEvidence

GOVERNANCE_SCHEMA = "rozkalns.deploy-executor-p9-governance-evidence.v1"
HERMES_BASELINE_SCHEMA = "rozkalns.deploy-executor-p9-hermes-origin-baseline.v1"
CONTROL_BASELINE_SCHEMA = "rozkalns.deploy-executor-p9-control-postcanary-baseline.v1"
AUTHORIZATION_REPOSITORY = "rozkalnsandris/ops-workflows"
AUTHORIZATION_REPOSITORY_ID = 1328835922
HERMES_OPERATION_ID = "hermes-deals.origin-path-audit.v1"
HERMES_SOURCE_REPOSITORY = "rozkalnsandris/hermes-deals"
HERMES_TARGET_ALIAS = "hermes-deals-origin-path-audit"
HERMES_BASELINE_RESOLVER = "hermes-deals.origin-path-registration.v1"
CONTROL_OPERATION_ID = "rozkalns-control-center.merge-postcanary-reconcile.v1"
CONTROL_SOURCE_REPOSITORY = "rozkalnsandris/rozkalns-control-center"
CONTROL_TARGET_ALIAS = "control-center-merge-postcanary-reconcile"
CONTROL_BASELINE_RESOLVER = "control-center.merge-postcanary-audit-row.v1"
MAX_EVIDENCE_AGE_SECONDS = 300
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)

GOVERNANCE_KEYS = frozenset(
    {
        "schema",
        "repository",
        "repository_id",
        "observed_at",
        "writer_set_sha256",
        "trusted",
    }
)
HERMES_BASELINE_KEYS = frozenset(
    {
        "schema",
        "resolver_id",
        "target_alias",
        "source_repository",
        "registered_commit_sha",
        "observed_at",
        "registration_identity_ok",
        "registered_source_match",
        "probe_identity_ok",
        "dispatcher_identity_ok",
        "workflow_identity_ok",
        "mutation_surface_read_only",
    }
)
CONTROL_BASELINE_KEYS = frozenset(
    {
        "schema",
        "resolver_id",
        "target_alias",
        "source_repository",
        "source_sha",
        "observed_at",
        "canary_run_terminal_failure_exact",
        "target_issue_exact",
        "target_pr_merge_evidence_exact",
        "target_merge_parent_exact",
        "target_main_descends_from_merge",
        "audit_row_exact",
        "target_audit_row_count_one",
        "d1_select_only_zero_write",
        "mutation_surface_read_only",
    }
)


class P9EvidenceError(ValueError):
    pass


def _object(value: Any, *, keys: frozenset[str], where: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P9EvidenceError(f"{where} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise P9EvidenceError(
            f"{where} keys mismatch; missing={sorted(keys-actual)}, extra={sorted(actual-keys)}"
        )
    return value


def _timestamp(value: Any, *, where: str) -> datetime:
    if type(value) is not str or RFC3339_UTC_RE.fullmatch(value) is None:
        raise P9EvidenceError(
            f"{where} must be canonical RFC3339 UTC YYYY-MM-DDTHH:MM:SS[.fraction]Z"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise P9EvidenceError(f"{where} is malformed") from exc
    return parsed.astimezone(timezone.utc)


def _fresh(observed_at: datetime, *, server_time: datetime, where: str) -> None:
    if not isinstance(server_time, datetime) or server_time.tzinfo is None:
        raise P9EvidenceError("server_time must be timezone-aware")
    age = (server_time.astimezone(timezone.utc) - observed_at).total_seconds()
    if age < 0 or age > MAX_EVIDENCE_AGE_SECONDS:
        raise P9EvidenceError(f"{where} is stale or from the future")


def parse_governance_evidence(value: Any, *, server_time: datetime) -> GovernanceEvidence:
    evidence = _object(value, keys=GOVERNANCE_KEYS, where="governance evidence")
    if evidence["schema"] != GOVERNANCE_SCHEMA:
        raise P9EvidenceError("governance evidence schema mismatch")
    if evidence["repository"] != AUTHORIZATION_REPOSITORY:
        raise P9EvidenceError("governance evidence repository mismatch")
    if evidence["repository_id"] != AUTHORIZATION_REPOSITORY_ID:
        raise P9EvidenceError("governance evidence repository identity mismatch")
    if evidence["trusted"] is not True:
        raise P9EvidenceError("governance evidence must explicitly assert trusted=true")
    digest = evidence["writer_set_sha256"]
    if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
        raise P9EvidenceError("governance writer-set digest is malformed")
    observed_at = _timestamp(evidence["observed_at"], where="governance observed_at")
    _fresh(observed_at, server_time=server_time, where="governance evidence")
    result = GovernanceEvidence(
        repository=AUTHORIZATION_REPOSITORY,
        repository_id=AUTHORIZATION_REPOSITORY_ID,
        observed_at=observed_at,
        writer_set_sha256=digest,
        trusted=True,
    )
    result.require_current(server_time=server_time)
    return result


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def resolve_hermes_origin_baseline(
    operation: Any,
    expected_baseline: Mapping[str, Any],
    *,
    evidence: Any,
    source_sha: str,
    server_time: datetime,
) -> BaselineEvidence:
    if getattr(operation, "operation_id", None) != HERMES_OPERATION_ID:
        raise P9EvidenceError("Hermes baseline resolver received the wrong operation")
    if getattr(operation, "source_repository", None) != HERMES_SOURCE_REPOSITORY:
        raise P9EvidenceError("Hermes baseline resolver source repository mismatch")
    if getattr(operation, "target_alias", None) != HERMES_TARGET_ALIAS:
        raise P9EvidenceError("Hermes baseline resolver target alias mismatch")
    baseline_contract = getattr(operation, "baseline", None)
    if (
        getattr(baseline_contract, "kind", None) != "resolver"
        or getattr(baseline_contract, "resolver_id", None) != HERMES_BASELINE_RESOLVER
    ):
        raise P9EvidenceError("Hermes operation baseline contract mismatch")
    if type(expected_baseline) is not dict or expected_baseline != {
        "kind": "resolver",
        "value": HERMES_BASELINE_RESOLVER,
    }:
        raise P9EvidenceError(
            "LIVE-AUTH expected_baseline does not bind the reviewed Hermes resolver"
        )
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        raise P9EvidenceError("authorized Hermes source SHA is malformed")

    payload = _object(
        evidence, keys=HERMES_BASELINE_KEYS, where="Hermes baseline evidence"
    )
    if payload["schema"] != HERMES_BASELINE_SCHEMA:
        raise P9EvidenceError("Hermes baseline evidence schema mismatch")
    if payload["resolver_id"] != HERMES_BASELINE_RESOLVER:
        raise P9EvidenceError("Hermes baseline evidence resolver mismatch")
    if payload["target_alias"] != HERMES_TARGET_ALIAS:
        raise P9EvidenceError("Hermes baseline evidence target alias mismatch")
    if payload["source_repository"] != HERMES_SOURCE_REPOSITORY:
        raise P9EvidenceError("Hermes baseline evidence source repository mismatch")
    if payload["registered_commit_sha"] != source_sha:
        raise P9EvidenceError(
            "Hermes baseline evidence is not bound to the authorized source SHA"
        )
    for flag in (
        "registration_identity_ok",
        "registered_source_match",
        "probe_identity_ok",
        "dispatcher_identity_ok",
        "workflow_identity_ok",
        "mutation_surface_read_only",
    ):
        if payload[flag] is not True:
            raise P9EvidenceError(
                f"Hermes baseline evidence must explicitly assert {flag}=true"
            )
    observed_at = _timestamp(
        payload["observed_at"], where="Hermes baseline observed_at"
    )
    _fresh(observed_at, server_time=server_time, where="Hermes baseline evidence")

    return BaselineEvidence(
        resolver_id=HERMES_BASELINE_RESOLVER,
        target_alias=HERMES_TARGET_ALIAS,
        matched=True,
        evidence_id=f"sha256:{_canonical_sha256(payload)}",
    )


def resolve_control_postcanary_baseline(
    operation: Any,
    expected_baseline: Mapping[str, Any],
    *,
    evidence: Any,
    source_sha: str,
    server_time: datetime,
) -> BaselineEvidence:
    if getattr(operation, "operation_id", None) != CONTROL_OPERATION_ID:
        raise P9EvidenceError("Control baseline resolver received the wrong operation")
    if getattr(operation, "source_repository", None) != CONTROL_SOURCE_REPOSITORY:
        raise P9EvidenceError("Control baseline resolver source repository mismatch")
    if getattr(operation, "target_alias", None) != CONTROL_TARGET_ALIAS:
        raise P9EvidenceError("Control baseline resolver target alias mismatch")
    baseline_contract = getattr(operation, "baseline", None)
    if (
        getattr(baseline_contract, "kind", None) != "resolver"
        or getattr(baseline_contract, "resolver_id", None) != CONTROL_BASELINE_RESOLVER
    ):
        raise P9EvidenceError("Control operation baseline contract mismatch")
    if type(expected_baseline) is not dict or expected_baseline != {
        "kind": "resolver",
        "value": CONTROL_BASELINE_RESOLVER,
    }:
        raise P9EvidenceError(
            "LIVE-AUTH expected_baseline does not bind the reviewed Control resolver"
        )
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        raise P9EvidenceError("authorized Control source SHA is malformed")

    payload = _object(
        evidence, keys=CONTROL_BASELINE_KEYS, where="Control baseline evidence"
    )
    if payload["schema"] != CONTROL_BASELINE_SCHEMA:
        raise P9EvidenceError("Control baseline evidence schema mismatch")
    if payload["resolver_id"] != CONTROL_BASELINE_RESOLVER:
        raise P9EvidenceError("Control baseline evidence resolver mismatch")
    if payload["target_alias"] != CONTROL_TARGET_ALIAS:
        raise P9EvidenceError("Control baseline evidence target alias mismatch")
    if payload["source_repository"] != CONTROL_SOURCE_REPOSITORY:
        raise P9EvidenceError("Control baseline evidence source repository mismatch")
    if payload["source_sha"] != source_sha:
        raise P9EvidenceError(
            "Control baseline evidence is not bound to the authorized source SHA"
        )
    for flag in (
        "canary_run_terminal_failure_exact",
        "target_issue_exact",
        "target_pr_merge_evidence_exact",
        "target_merge_parent_exact",
        "target_main_descends_from_merge",
        "audit_row_exact",
        "target_audit_row_count_one",
        "d1_select_only_zero_write",
        "mutation_surface_read_only",
    ):
        if payload[flag] is not True:
            raise P9EvidenceError(
                f"Control baseline evidence must explicitly assert {flag}=true"
            )
    observed_at = _timestamp(
        payload["observed_at"], where="Control baseline observed_at"
    )
    _fresh(observed_at, server_time=server_time, where="Control baseline evidence")

    return BaselineEvidence(
        resolver_id=CONTROL_BASELINE_RESOLVER,
        target_alias=CONTROL_TARGET_ALIAS,
        matched=True,
        evidence_id=f"sha256:{_canonical_sha256(payload)}",
    )


def resolve_p9_baseline(
    operation: Any,
    expected_baseline: Mapping[str, Any],
    *,
    evidence: Any,
    source_sha: str,
    server_time: datetime,
) -> BaselineEvidence:
    baseline_contract = getattr(operation, "baseline", None)
    if getattr(baseline_contract, "kind", None) != "resolver":
        raise P9EvidenceError("P9 operation does not declare a resolver baseline")
    resolver_id = getattr(baseline_contract, "resolver_id", None)
    if resolver_id == HERMES_BASELINE_RESOLVER:
        return resolve_hermes_origin_baseline(
            operation,
            expected_baseline,
            evidence=evidence,
            source_sha=source_sha,
            server_time=server_time,
        )
    if resolver_id == CONTROL_BASELINE_RESOLVER:
        return resolve_control_postcanary_baseline(
            operation,
            expected_baseline,
            evidence=evidence,
            source_sha=source_sha,
            server_time=server_time,
        )
    raise P9EvidenceError("P9 operation baseline resolver is not allowlisted")
