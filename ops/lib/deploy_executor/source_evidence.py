from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

SOURCE_REPOSITORIES: Mapping[str, tuple[int, str]] = {
    "rozkalnsandris/RPi5_main": (1323383044, "validate.yml"),
    "rozkalnsandris/hermes-tech": (1323427708, "ci.yml"),
    "rozkalnsandris/rozkalns-cv": (1325237749, "ci.yml"),
    "rozkalnsandris/hermes-deals": (1317143994, "ci.yml"),
    "rozkalnsandris/rozkalns-control-center": (1329279953, "ci.yml"),
}


class SourceEvidenceError(RuntimeError):
    pass


class JSONResponseLike(Protocol):
    value: Any


class GitHubReader(Protocol):
    def get_json(self, path_or_url: str) -> JSONResponseLike: ...


@dataclass(frozen=True)
class SourceEvidence:
    repository: str
    repository_id: int
    source_sha: str
    current_main_sha: str
    workflow: str
    run_id: int


def _object(value: Any, where: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise SourceEvidenceError(f"{where} is not an object")
    return value


def _full_sha(value: Any, where: str) -> str:
    if type(value) is not str or SHA_RE.fullmatch(value) is None:
        raise SourceEvidenceError(f"{where} is not an exact lowercase SHA")
    return value


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise SourceEvidenceError(f"{where} is not a positive integer")
    return value


def verify_source_evidence(
    client: GitHubReader,
    *,
    source_repository: str,
    source_sha: str,
) -> SourceEvidence:
    try:
        expected_repository_id, workflow = SOURCE_REPOSITORIES[source_repository]
    except KeyError as exc:
        raise SourceEvidenceError("source repository is outside the reviewed Automation App allowlist") from exc
    _full_sha(source_sha, "source_sha")

    repository = _object(client.get_json(f"/repos/{source_repository}").value, "repository")
    if repository.get("id") != expected_repository_id:
        raise SourceEvidenceError("source repository numeric identity drifted")
    if repository.get("full_name") != source_repository:
        raise SourceEvidenceError("source repository full_name drifted")
    if repository.get("default_branch") != "main":
        raise SourceEvidenceError("source repository default branch is not main")

    branch = _object(client.get_json(f"/repos/{source_repository}/branches/main").value, "main branch")
    commit = _object(branch.get("commit"), "main branch commit")
    main_sha = _full_sha(commit.get("sha"), "main SHA")

    if source_sha != main_sha:
        compare = _object(
            client.get_json(f"/repos/{source_repository}/compare/{source_sha}...{main_sha}").value,
            "compare response",
        )
        merge_base = _object(compare.get("merge_base_commit"), "compare merge base")
        merge_base_sha = _full_sha(merge_base.get("sha"), "compare merge-base SHA")
        if merge_base_sha != source_sha:
            raise SourceEvidenceError("authorized source SHA is not the merge base of current main")
        if compare.get("behind_by") != 0:
            raise SourceEvidenceError("authorized source SHA is not an ancestor of current main")
        if compare.get("status") not in {"ahead", "identical"}:
            raise SourceEvidenceError("source compare status is not an accepted ancestor relationship")

    runs_path = (
        f"/repos/{source_repository}/actions/workflows/{workflow}/runs"
        f"?branch=main&head_sha={source_sha}&status=completed&per_page=100"
    )
    runs_payload = _object(client.get_json(runs_path).value, "workflow run response")
    runs = runs_payload.get("workflow_runs")
    if type(runs) is not list:
        raise SourceEvidenceError("workflow run list is malformed")
    successful: list[Mapping[str, Any]] = []
    for row in runs:
        if type(row) is not dict:
            continue
        if (
            row.get("head_sha") == source_sha
            and row.get("head_branch") == "main"
            and row.get("status") == "completed"
            and row.get("conclusion") == "success"
        ):
            successful.append(row)
    if not successful:
        raise SourceEvidenceError("authorized source SHA has no successful completed exact-main CI run")
    run_id = max(_positive_int(row.get("id"), "workflow run id") for row in successful)

    jobs_payload = _object(
        client.get_json(
            f"/repos/{source_repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
        ).value,
        "workflow jobs response",
    )
    jobs = jobs_payload.get("jobs")
    if type(jobs) is not list or not any(
        type(job) is dict
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs
    ):
        raise SourceEvidenceError("successful exact-SHA workflow has no successful job")

    return SourceEvidence(
        repository=source_repository,
        repository_id=expected_repository_id,
        source_sha=source_sha,
        current_main_sha=main_sha,
        workflow=workflow,
        run_id=run_id,
    )
