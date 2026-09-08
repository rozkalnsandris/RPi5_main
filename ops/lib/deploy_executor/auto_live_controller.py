from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from .registry import OperationRegistry, OperationSpec, load_registry

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DECISIONS = frozenset({"NO_DEPLOY", "AUTO_DEPLOY_SAFE", "OWNER_REQUIRED", "BLOCKED"})
DEPLOY_CLASSES = frozenset(
    {"NO_DEPLOY", "AUTO_DEPLOY_SAFE", "MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"}
)
MAX_COMPARE_FILES = 300


class AutoLiveControllerError(ValueError):
    pass


class GitHubReadClient(Protocol):
    def get_json(self, path_or_url: str) -> Any:
        ...


@dataclass(frozen=True)
class AutoLiveDecision:
    decision: str
    classification: str | None
    reason: str
    source_repository: str
    target_alias: str
    production_baseline_sha: str
    target_sha: str
    current_main_sha: str
    changed_paths: tuple[str, ...]
    required_ci_run_id: int | None
    required_ci_gate: str
    manifest_activation_state: str
    automatic_mutation_allowed: bool = False
    mutation_dispatch_enabled: bool = False
    production_mutation_started: bool = False


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutoLiveControllerError(f"{label} unreadable: {exc}") from exc
    if type(value) is not dict:
        raise AutoLiveControllerError(f"{label} must be a JSON object")
    return value


def _response_value(response: Any, label: str) -> Any:
    if not hasattr(response, "value"):
        raise AutoLiveControllerError(f"{label} response has no JSON value")
    value = response.value
    if value is None:
        raise AutoLiveControllerError(f"{label} returned no authoritative JSON value")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or SHA_RE.fullmatch(value) is None:
        raise AutoLiveControllerError(f"{label} must be an exact 40-character lowercase SHA")
    return value


def _operation_by_id(registry: OperationRegistry, operation_id: str) -> OperationSpec:
    matches = [operation for operation in registry.operations if operation.operation_id == operation_id]
    if len(matches) != 1:
        raise AutoLiveControllerError("manifest static_operation_id does not resolve exactly once")
    return matches[0]


def _classify_paths(manifest: Mapping[str, Any], paths: tuple[str, ...]) -> str:
    classifier = manifest.get("classifier")
    if type(classifier) is not dict:
        raise AutoLiveControllerError("manifest classifier is missing")
    rules = classifier.get("rules")
    precedence = classifier.get("precedence")
    if type(rules) is not dict or type(precedence) is not list:
        raise AutoLiveControllerError("manifest classifier schema is invalid")
    if not paths:
        return "BLOCKED"
    matched: list[str] = []
    for path in paths:
        path_classes: list[str] = []
        for class_name, rule in rules.items():
            if class_name not in DEPLOY_CLASSES or type(rule) is not dict:
                raise AutoLiveControllerError("manifest classifier contains an unsupported class")
            exact_paths = rule.get("exact_paths")
            prefixes = rule.get("path_prefixes")
            if type(exact_paths) is not list or type(prefixes) is not list:
                raise AutoLiveControllerError("manifest classifier rule schema is invalid")
            if path in exact_paths or any(type(prefix) is str and path.startswith(prefix) for prefix in prefixes):
                path_classes.append(class_name)
        if not path_classes:
            return "BLOCKED"
        matched.extend(path_classes)
    for class_name in precedence:
        if class_name in matched:
            return class_name
    return "BLOCKED"


def _blocked(
    *,
    reason: str,
    manifest: Mapping[str, Any],
    baseline: str,
    target: str,
    current_main: str,
    changed_paths: tuple[str, ...] = (),
    ci_run_id: int | None = None,
) -> AutoLiveDecision:
    required_ci = manifest["required_ci"]
    return AutoLiveDecision(
        decision="BLOCKED",
        classification=None,
        reason=reason,
        source_repository=manifest["source_repository"],
        target_alias=manifest["target_alias"],
        production_baseline_sha=baseline,
        target_sha=target,
        current_main_sha=current_main,
        changed_paths=changed_paths,
        required_ci_run_id=ci_run_id,
        required_ci_gate=required_ci["required_gate"],
        manifest_activation_state=manifest["activation"]["state"],
    )


def _verify_source_contracts(
    *,
    root: Path,
    manifest_relative_path: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], OperationSpec]:
    controller = _read_json(root / "ops/deploy/auto-live-controller-v1.json", "A3 controller contract")
    if controller.get("schema_version") != 1 or controller.get("status") != "A3_SOURCE_ONLY_MUTATION_DISABLED":
        raise AutoLiveControllerError("A3 controller contract status is invalid")
    if controller.get("execution_enabled") is not False or controller.get("roadmap_issue") != 421:
        raise AutoLiveControllerError("A3 controller execution/roadmap contract is invalid")
    if set(controller.get("decisions", [])) != DECISIONS:
        raise AutoLiveControllerError("A3 controller decision set is invalid")
    github_reads = controller.get("github_reads")
    if type(github_reads) is not dict:
        raise AutoLiveControllerError("A3 GitHub read contract is missing")
    if github_reads.get("default_branch") != "main":
        raise AutoLiveControllerError("A3 controller must bind the main branch")
    if github_reads.get("full_range_compare_required") is not True:
        raise AutoLiveControllerError("A3 controller must require full-range comparison")
    if github_reads.get("compare_file_hard_limit") != MAX_COMPARE_FILES:
        raise AutoLiveControllerError("A3 compare hard limit drifted")
    if github_reads.get("incomplete_compare_result") != "BLOCKED":
        raise AutoLiveControllerError("A3 incomplete compare must fail closed")
    mutation = controller.get("mutation")
    if type(mutation) is not dict or any(mutation.get(key) is not False for key in (
        "automatic_mutation_allowed", "mutation_dispatch_enabled", "production_mutation_started"
    )):
        raise AutoLiveControllerError("A3 mutation flags must all remain false")

    index_path = root / controller["manifests_index"]
    index = _read_json(index_path, "A2 manifests index")
    if index.get("status") != "A2_SOURCE_ONLY_INACTIVE" or index.get("execution_enabled") is not False:
        raise AutoLiveControllerError("A2 manifests must remain source-only and inactive")
    if index.get("shared_policy", {}).get("commit_sha") != controller.get("shared_policy_commit_sha"):
        raise AutoLiveControllerError("shared policy exact SHA drifted")
    listed = [item for item in index.get("manifests", []) if item.get("path") == manifest_relative_path]
    if len(listed) != 1:
        raise AutoLiveControllerError("manifest is not listed exactly once in A2 index")

    manifest = _read_json(root / manifest_relative_path, "Auto-Live manifest")
    item = listed[0]
    for key in ("source_repository", "target_alias", "static_operation_id"):
        if manifest.get(key) != item.get(key):
            raise AutoLiveControllerError(f"manifest {key} does not match A2 index")
    if manifest.get("shared_policy_commit_sha") != controller.get("shared_policy_commit_sha"):
        raise AutoLiveControllerError("manifest shared policy exact SHA drifted")
    activation = manifest.get("activation")
    if type(activation) is not dict or activation.get("state") != "INACTIVE_SOURCE_ONLY":
        raise AutoLiveControllerError("A3 requires an inactive source-only manifest")
    if activation.get("automatic_mutation_enabled") is not False:
        raise AutoLiveControllerError("A3 manifest automatic mutation must remain disabled")
    classifier = manifest.get("classifier")
    if type(classifier) is not dict or classifier.get("range") != "FULL_PRODUCTION_BASELINE_TO_TARGET":
        raise AutoLiveControllerError("manifest must require full production baseline-to-target classification")
    if classifier.get("latest_commit_only") is not False or classifier.get("unmatched_path_result") != "BLOCKED":
        raise AutoLiveControllerError("manifest classifier must fail closed")
    required_ci = manifest.get("required_ci")
    if type(required_ci) is not dict or required_ci.get("exact_target_sha_required") is not True:
        raise AutoLiveControllerError("manifest must require exact target SHA CI")
    if required_ci.get("required_conclusion") != "success":
        raise AutoLiveControllerError("manifest CI conclusion policy must be success")
    if not manifest.get("health_postconditions"):
        raise AutoLiveControllerError("manifest must define deterministic health postconditions")

    registry = load_registry(root / controller["static_operation_registry"])
    operation = _operation_by_id(registry, manifest["static_operation_id"])
    if operation.source_repository != manifest["source_repository"]:
        raise AutoLiveControllerError("static operation source repository does not match manifest")
    if operation.target_alias != manifest["target_alias"]:
        raise AutoLiveControllerError("static operation target alias does not match manifest")
    if operation.baseline.resolver_id != manifest.get("baseline", {}).get("resolver_id"):
        raise AutoLiveControllerError("static operation baseline resolver does not match manifest")
    return controller, manifest, operation


def _current_main(github: GitHubReadClient, repository: str) -> str:
    repo = _response_value(github.get_json(f"/repos/{repository}"), "repository")
    if type(repo) is not dict or repo.get("full_name") != repository or repo.get("default_branch") != "main":
        raise AutoLiveControllerError("repository identity/default branch mismatch")
    branch = _response_value(github.get_json(f"/repos/{repository}/branches/main"), "main branch")
    try:
        return _sha(branch["commit"]["sha"], "current main SHA")
    except (KeyError, TypeError):
        raise AutoLiveControllerError("main branch response schema is invalid") from None


def _compare(github: GitHubReadClient, repository: str, base: str, head: str) -> Mapping[str, Any]:
    response = _response_value(
        github.get_json(f"/repos/{repository}/compare/{quote(base, safe='')}...{quote(head, safe='')}"),
        "compare",
    )
    if type(response) is not dict:
        raise AutoLiveControllerError("compare response schema is invalid")
    return response


def _target_reachable(github: GitHubReadClient, repository: str, target: str, current_main: str) -> bool:
    if target == current_main:
        return True
    comparison = _compare(github, repository, target, current_main)
    return comparison.get("status") in {"ahead", "identical"}


def _changed_paths_from_range(
    github: GitHubReadClient, repository: str, baseline: str, target: str
) -> tuple[str, ...] | None:
    comparison = _compare(github, repository, baseline, target)
    if comparison.get("status") != "ahead":
        return None
    files = comparison.get("files")
    if type(files) is not list or not files or len(files) >= MAX_COMPARE_FILES:
        return None
    paths: list[str] = []
    for item in files:
        if type(item) is not dict or type(item.get("filename")) is not str or not item["filename"]:
            return None
        paths.append(item["filename"])
    return tuple(sorted(set(paths)))


def _required_ci_run_id(
    github: GitHubReadClient,
    repository: str,
    target: str,
    required_ci: Mapping[str, Any],
) -> int | None:
    runs = _response_value(
        github.get_json(
            f"/repos/{repository}/actions/runs?head_sha={quote(target, safe='')}&status=completed&per_page=100"
        ),
        "workflow runs",
    )
    if type(runs) is not dict or type(runs.get("workflow_runs")) is not list:
        raise AutoLiveControllerError("workflow runs response schema is invalid")
    rows = runs["workflow_runs"]
    total = runs.get("total_count")
    if type(total) is not int or total > len(rows):
        return None
    candidates = [
        row for row in rows
        if type(row) is dict
        and row.get("head_sha") == target
        and row.get("path") == required_ci["workflow_path"]
        and row.get("name") == required_ci["workflow_name"]
        and row.get("event") == "push"
        and row.get("head_branch") == "main"
        and row.get("conclusion") == required_ci["required_conclusion"]
        and type(row.get("id")) is int
    ]
    for row in sorted(candidates, key=lambda item: item["id"], reverse=True):
        run_id = row["id"]
        jobs = _response_value(
            github.get_json(f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"),
            "workflow jobs",
        )
        if type(jobs) is not dict or type(jobs.get("jobs")) is not list:
            raise AutoLiveControllerError("workflow jobs response schema is invalid")
        job_rows = jobs["jobs"]
        job_total = jobs.get("total_count")
        if type(job_total) is not int or job_total > len(job_rows):
            continue
        if any(
            type(job) is dict
            and job.get("name") == required_ci["required_gate"]
            and job.get("conclusion") == required_ci["required_conclusion"]
            for job in job_rows
        ):
            return run_id
    return None


def reconcile_once(
    *,
    github: GitHubReadClient,
    root: str | Path,
    manifest_relative_path: str,
    production_baseline_sha: str,
    target_sha: str | None = None,
) -> AutoLiveDecision:
    root_path = Path(root)
    _controller, manifest, operation = _verify_source_contracts(
        root=root_path,
        manifest_relative_path=manifest_relative_path,
    )
    baseline = _sha(production_baseline_sha, "production baseline SHA")
    repository = manifest["source_repository"]
    current_main = _current_main(github, repository)
    target = current_main if target_sha is None else _sha(target_sha, "target SHA")

    if not _target_reachable(github, repository, target, current_main):
        return _blocked(
            reason="TARGET_NOT_REACHABLE_FROM_CURRENT_MAIN",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
        )
    if baseline == target:
        return _blocked(
            reason="NO_PRODUCTION_RANGE_TO_CLASSIFY",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
        )

    changed_paths = _changed_paths_from_range(github, repository, baseline, target)
    if changed_paths is None:
        return _blocked(
            reason="FULL_RANGE_COMPARE_INCOMPLETE_OR_NOT_AHEAD",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
        )
    classification = _classify_paths(manifest, changed_paths)
    if classification == "BLOCKED":
        return _blocked(
            reason="UNMATCHED_OR_AMBIGUOUS_CHANGED_PATH",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
            changed_paths=changed_paths,
        )

    ci_run_id = _required_ci_run_id(github, repository, target, manifest["required_ci"])
    if ci_run_id is None:
        return _blocked(
            reason="EXACT_TARGET_SHA_REQUIRED_CI_NOT_SUCCESSFUL",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
            changed_paths=changed_paths,
        )

    if classification in {"MANUAL_ROLLOUT_REQUIRED", "DB_HOST_APPLY_REQUIRED"}:
        decision = "OWNER_REQUIRED"
        reason = classification
    elif classification == "NO_DEPLOY":
        decision = "NO_DEPLOY"
        reason = "FULL_RANGE_NO_DEPLOY"
    elif classification == "AUTO_DEPLOY_SAFE":
        eligible = manifest.get("automatic_eligibility", {}).get("eligible_classes", [])
        static_auto = (
            operation.authorization_class == "ORDINARY"
            and operation.ordinary_live_all_eligible
            and operation.queue_match.deploy_class == "AUTO_DEPLOY_SAFE"
        )
        if "AUTO_DEPLOY_SAFE" not in eligible:
            decision = "OWNER_REQUIRED"
            reason = "MANIFEST_DOES_NOT_AUTO_ELIGIBLE_SAFE_CLASS"
        elif not static_auto:
            return _blocked(
                reason="STATIC_OPERATION_NOT_AUTO_LIVE_ELIGIBLE",
                manifest=manifest,
                baseline=baseline,
                target=target,
                current_main=current_main,
                changed_paths=changed_paths,
                ci_run_id=ci_run_id,
            )
        else:
            decision = "AUTO_DEPLOY_SAFE"
            reason = "READ_ONLY_SAFE_DECISION"
    else:
        return _blocked(
            reason="UNSUPPORTED_CLASSIFICATION",
            manifest=manifest,
            baseline=baseline,
            target=target,
            current_main=current_main,
            changed_paths=changed_paths,
            ci_run_id=ci_run_id,
        )

    return AutoLiveDecision(
        decision=decision,
        classification=classification,
        reason=reason,
        source_repository=repository,
        target_alias=manifest["target_alias"],
        production_baseline_sha=baseline,
        target_sha=target,
        current_main_sha=current_main,
        changed_paths=changed_paths,
        required_ci_run_id=ci_run_id,
        required_ci_gate=manifest["required_ci"]["required_gate"],
        manifest_activation_state=manifest["activation"]["state"],
        automatic_mutation_allowed=False,
        mutation_dispatch_enabled=False,
        production_mutation_started=False,
    )
