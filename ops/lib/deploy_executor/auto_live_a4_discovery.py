from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .auto_live_controller import (
    AutoLiveControllerError,
    GitHubReadClient,
    _changed_paths_from_range,
    _classify_paths,
    _current_main,
    _required_ci_run_id,
    _sha,
    _verify_source_contracts,
)
from .registry import RegistryError

DECISIONS = frozenset({
    "ELIGIBLE_CANARY",
    "NO_ELIGIBLE_CANARY",
    "NEEDS_FRESH_LIVE_PREFLIGHT",
    "OWNER_REQUIRED",
    "BLOCKED",
})
BASELINE_EVIDENCE_SCHEMA = "rozkalns.auto-live-production-baseline-evidence.v1"
BASELINE_EVIDENCE_KEYS = frozenset({
    "schema",
    "evidence_source",
    "source_repository",
    "target_alias",
    "resolver_id",
    "target_sha",
    "production_baseline_sha",
    "trusted",
    "fresh",
})
INDEX_PATH = "ops/deploy/auto-live-manifests.json"
MANIFEST_PREFIX = "ops/deploy/auto-live-manifests/"


class AutoLiveA4DiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateDecision:
    decision: str
    reason: str
    manifest_path: str
    source_repository: str
    target_alias: str
    static_operation_id: str
    target_sha: str | None
    classification: str | None
    required_ci_run_id: int | None
    changed_paths: tuple[str, ...]
    production_baseline_sha: str | None = None


@dataclass(frozen=True)
class DiscoveryDecision:
    decision: str
    reason: str
    selected_manifest_path: str | None
    selected_target_alias: str | None
    selected_target_sha: str | None
    candidates: tuple[CandidateDecision, ...]
    automatic_mutation_allowed: bool = False
    mutation_dispatch_enabled: bool = False
    production_mutation_started: bool = False


def _read_index(root: Path) -> list[Mapping[str, Any]]:
    try:
        value = json.loads((root / INDEX_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutoLiveA4DiscoveryError(f"A2 manifest index unreadable: {exc}") from exc
    if type(value) is not dict:
        raise AutoLiveA4DiscoveryError("A2 manifest index must be an object")
    if value.get("schema_version") != 1 or value.get("status") != "A2_SOURCE_ONLY_INACTIVE":
        raise AutoLiveA4DiscoveryError("A2 manifest index contract is unsupported")
    if value.get("execution_enabled") is not False:
        raise AutoLiveA4DiscoveryError("A2 execution must remain disabled")
    rows = value.get("manifests")
    if type(rows) is not list or not rows:
        raise AutoLiveA4DiscoveryError("A2 manifest index must contain candidates")
    required = {"path", "source_repository", "target_alias", "static_operation_id"}
    seen_paths: set[str] = set()
    seen_targets: set[str] = set()
    out: list[Mapping[str, Any]] = []
    for row in rows:
        if type(row) is not dict or set(row) != required:
            raise AutoLiveA4DiscoveryError("A2 manifest index candidate shape is invalid")
        path = row["path"]
        target = row["target_alias"]
        if type(path) is not str or not path.startswith(MANIFEST_PREFIX) or not path.endswith(".json"):
            raise AutoLiveA4DiscoveryError("candidate manifest path is outside the declared A2 directory")
        if path in seen_paths or target in seen_targets:
            raise AutoLiveA4DiscoveryError("candidate manifest path/target must be unique")
        seen_paths.add(path)
        seen_targets.add(target)
        out.append(row)
    return sorted(out, key=lambda row: (row["target_alias"], row["path"]))


def _candidate_contract(root: Path, row: Mapping[str, Any]):
    try:
        _controller, manifest, operation = _verify_source_contracts(
            root=root, manifest_relative_path=row["path"]
        )
    except AutoLiveControllerError as exc:
        raise AutoLiveA4DiscoveryError(f"candidate source contract invalid: {exc}") from exc
    for key in ("source_repository", "target_alias", "static_operation_id"):
        if manifest.get(key) != row[key]:
            raise AutoLiveA4DiscoveryError(f"candidate {key} drifted from A2 index")
    classifier = manifest.get("classifier", {})
    if classifier.get("kind") != "ORDERED_PATH_RULES_V1":
        raise AutoLiveA4DiscoveryError("candidate classifier kind is unsupported")
    eligible = manifest.get("automatic_eligibility", {}).get("eligible_classes")
    if type(eligible) is not list or any(item != "AUTO_DEPLOY_SAFE" for item in eligible):
        raise AutoLiveA4DiscoveryError("candidate automatic eligibility widened beyond AUTO_DEPLOY_SAFE")
    failure = manifest.get("failure_policy")
    if type(failure) is not dict or failure.get("rollback_policy") != "NONE":
        raise AutoLiveA4DiscoveryError("candidate failure policy is unsupported")
    for key in (
        "automatic_retry_after_mutation_start",
        "automatic_cleanup_after_mutation_start",
        "automatic_rollback_after_mutation_start",
        "alternate_mutation_path_after_mutation_start",
    ):
        if failure.get(key) is not False:
            raise AutoLiveA4DiscoveryError("candidate failure policy must fail closed")
    if not manifest.get("health_postconditions") or not manifest.get("sensitive_exclusions"):
        raise AutoLiveA4DiscoveryError("candidate health/sensitive exclusion contract is incomplete")
    return manifest, operation


def _tip_parent_and_paths(
    github: GitHubReadClient,
    repository: str,
    target_sha: str,
) -> tuple[str, tuple[str, ...] | None]:
    response = github.get_json(f"/repos/{repository}/commits/{target_sha}")
    if not hasattr(response, "value") or type(response.value) is not dict:
        raise AutoLiveA4DiscoveryError("current target commit response is invalid")
    value = response.value
    if value.get("sha") != target_sha:
        raise AutoLiveA4DiscoveryError("current target commit identity drifted")
    parents = value.get("parents")
    if type(parents) is not list or len(parents) != 1 or type(parents[0]) is not dict:
        raise AutoLiveA4DiscoveryError("current target must have exactly one parent for tip classification")
    try:
        parent = _sha(parents[0].get("sha"), "current target parent SHA")
    except AutoLiveControllerError as exc:
        raise AutoLiveA4DiscoveryError(str(exc)) from exc
    return parent, _changed_paths_from_range(github, repository, parent, target_sha)


def _baseline_for(
    evidence_by_target: Mapping[str, Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    target_sha: str,
) -> tuple[str | None, str | None]:
    target_alias = manifest["target_alias"]
    evidence = evidence_by_target.get(target_alias)
    if evidence is None:
        return None, "MISSING_FRESH_TRUSTED_PRODUCTION_BASELINE"
    if type(evidence) is not dict or set(evidence) != BASELINE_EVIDENCE_KEYS:
        return None, "PRODUCTION_BASELINE_EVIDENCE_SHAPE_INVALID"
    expected = {
        "schema": BASELINE_EVIDENCE_SCHEMA,
        "evidence_source": "TRUSTED_RPI5_READ_ONLY_PREFLIGHT",
        "source_repository": manifest["source_repository"],
        "target_alias": target_alias,
        "resolver_id": manifest["baseline"]["resolver_id"],
        "target_sha": target_sha,
        "trusted": True,
        "fresh": True,
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        return None, "PRODUCTION_BASELINE_EVIDENCE_STALE_OR_UNTRUSTED"
    baseline = evidence.get("production_baseline_sha")
    if type(baseline) is not str or len(baseline) != 40 or any(ch not in "0123456789abcdef" for ch in baseline):
        return None, "PRODUCTION_BASELINE_SHA_INVALID"
    return baseline, None


def _evaluate_candidate(
    github: GitHubReadClient,
    root: Path,
    row: Mapping[str, Any],
    evidence_by_target: Mapping[str, Mapping[str, Any]],
) -> CandidateDecision:
    manifest, operation = _candidate_contract(root, row)
    common = dict(
        manifest_path=row["path"],
        source_repository=manifest["source_repository"],
        target_alias=manifest["target_alias"],
        static_operation_id=manifest["static_operation_id"],
    )
    eligible = manifest["automatic_eligibility"]["eligible_classes"]
    if "AUTO_DEPLOY_SAFE" not in eligible:
        return CandidateDecision(
            decision="NO_ELIGIBLE_CANARY", reason="MANIFEST_HAS_NO_AUTOMATIC_ELIGIBLE_CLASS",
            target_sha=None, classification=None, required_ci_run_id=None, changed_paths=(), **common
        )
    static_auto = (
        operation.authorization_class == "ORDINARY"
        and operation.ordinary_live_all_eligible
        and operation.queue_match.deploy_class == "AUTO_DEPLOY_SAFE"
    )
    if not static_auto:
        return CandidateDecision(
            decision="BLOCKED", reason="STATIC_OPERATION_NOT_AUTO_LIVE_ELIGIBLE",
            target_sha=None, classification=None, required_ci_run_id=None, changed_paths=(), **common
        )
    target = _current_main(github, manifest["source_repository"])
    ci_run_id = _required_ci_run_id(github, manifest["source_repository"], target, manifest["required_ci"])
    if ci_run_id is None:
        return CandidateDecision(
            decision="BLOCKED", reason="EXACT_TARGET_SHA_REQUIRED_CI_NOT_SUCCESSFUL",
            target_sha=target, classification=None, required_ci_run_id=None, changed_paths=(), **common
        )
    parent, tip_paths = _tip_parent_and_paths(github, manifest["source_repository"], target)
    if tip_paths is None:
        return CandidateDecision(
            decision="BLOCKED", reason="CURRENT_TIP_COMPARE_INCOMPLETE_OR_NOT_AHEAD",
            target_sha=target, classification=None, required_ci_run_id=ci_run_id, changed_paths=(), **common
        )
    tip_class = _classify_paths(manifest, tip_paths)
    if tip_class == "BLOCKED":
        return CandidateDecision(
            decision="BLOCKED", reason="CURRENT_TIP_UNMATCHED_OR_AMBIGUOUS",
            target_sha=target, classification=None, required_ci_run_id=ci_run_id, changed_paths=tip_paths, **common
        )
    if tip_class in {"MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"}:
        return CandidateDecision(
            decision="OWNER_REQUIRED", reason=f"CURRENT_TIP_{tip_class}",
            target_sha=target, classification=tip_class, required_ci_run_id=ci_run_id, changed_paths=tip_paths, **common
        )
    baseline, baseline_error = _baseline_for(evidence_by_target, manifest=manifest, target_sha=target)
    if baseline_error == "MISSING_FRESH_TRUSTED_PRODUCTION_BASELINE":
        return CandidateDecision(
            decision="NEEDS_FRESH_LIVE_PREFLIGHT", reason=baseline_error,
            target_sha=target, classification=tip_class, required_ci_run_id=ci_run_id, changed_paths=tip_paths, **common
        )
    if baseline_error is not None or baseline is None:
        return CandidateDecision(
            decision="BLOCKED", reason=baseline_error or "PRODUCTION_BASELINE_EVIDENCE_INVALID",
            target_sha=target, classification=tip_class, required_ci_run_id=ci_run_id, changed_paths=tip_paths, **common
        )
    if baseline == target:
        return CandidateDecision(
            decision="NO_ELIGIBLE_CANARY", reason="PRODUCTION_ALREADY_AT_TARGET",
            target_sha=target, classification="NO_DEPLOY", required_ci_run_id=ci_run_id,
            changed_paths=(), production_baseline_sha=baseline, **common
        )
    full_paths = _changed_paths_from_range(github, manifest["source_repository"], baseline, target)
    if full_paths is None:
        return CandidateDecision(
            decision="BLOCKED", reason="FULL_RANGE_COMPARE_INCOMPLETE_OR_NOT_AHEAD",
            target_sha=target, classification=None, required_ci_run_id=ci_run_id,
            changed_paths=(), production_baseline_sha=baseline, **common
        )
    full_class = _classify_paths(manifest, full_paths)
    if full_class == "AUTO_DEPLOY_SAFE":
        decision, reason = "ELIGIBLE_CANARY", "FULL_RANGE_AUTO_DEPLOY_SAFE"
    elif full_class in {"MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"}:
        decision, reason = "OWNER_REQUIRED", f"FULL_RANGE_{full_class}"
    elif full_class == "NO_DEPLOY":
        decision, reason = "NO_ELIGIBLE_CANARY", "FULL_RANGE_NO_DEPLOY"
    else:
        decision, reason = "BLOCKED", "FULL_RANGE_UNMATCHED_OR_AMBIGUOUS"
    return CandidateDecision(
        decision=decision, reason=reason, target_sha=target, classification=full_class,
        required_ci_run_id=ci_run_id, changed_paths=full_paths,
        production_baseline_sha=baseline, **common
    )


def _aggregate(candidates: tuple[CandidateDecision, ...]) -> DiscoveryDecision:
    if not candidates:
        return DiscoveryDecision("BLOCKED", "NO_DECLARED_CANDIDATES", None, None, None, candidates)
    eligible = sorted(
        (item for item in candidates if item.decision == "ELIGIBLE_CANARY"),
        key=lambda item: (item.target_alias, item.manifest_path),
    )
    if eligible:
        selected = eligible[0]
        return DiscoveryDecision(
            "ELIGIBLE_CANARY", "STABLE_TIE_BREAK_FIRST_FULLY_ELIGIBLE", selected.manifest_path,
            selected.target_alias, selected.target_sha, candidates
        )
    precedence = (
        ("BLOCKED", "AT_LEAST_ONE_AUTOMATIC_CANDIDATE_BLOCKED"),
        ("NEEDS_FRESH_LIVE_PREFLIGHT", "FRESH_TRUSTED_PRODUCTION_BASELINE_REQUIRED"),
        ("OWNER_REQUIRED", "AUTOMATIC_CANDIDATE_REQUIRES_OWNER"),
        ("NO_ELIGIBLE_CANARY", "NO_FULLY_ELIGIBLE_CANARY"),
    )
    for decision, reason in precedence:
        if any(item.decision == decision for item in candidates):
            return DiscoveryDecision(decision, reason, None, None, None, candidates)
    return DiscoveryDecision("BLOCKED", "UNSUPPORTED_CANDIDATE_DECISION", None, None, None, candidates)


def discover_once(
    *,
    github: GitHubReadClient,
    root: str | Path,
    production_baselines: Mapping[str, Mapping[str, Any]] | None = None,
) -> DiscoveryDecision:
    root_path = Path(root)
    evidence = production_baselines or {}
    try:
        if type(evidence) is not dict:
            raise AutoLiveA4DiscoveryError("production_baselines must be a mapping")
        rows = _read_index(root_path)
        candidates = tuple(_evaluate_candidate(github, root_path, row, evidence) for row in rows)
    except (AutoLiveA4DiscoveryError, AutoLiveControllerError, RegistryError) as exc:
        return DiscoveryDecision(
            "BLOCKED", f"SOURCE_OR_EVIDENCE_INVALID:{exc}", None, None, None, ()
        )
    result = _aggregate(candidates)
    if result.decision not in DECISIONS:
        return DiscoveryDecision("BLOCKED", "UNSUPPORTED_AGGREGATE_DECISION", None, None, None, candidates)
    return result
