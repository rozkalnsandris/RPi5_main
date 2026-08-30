from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import grp
import hashlib
import json
import os
import re
import secrets
import stat
from typing import Any, Mapping

from .control_center_postcanary_adapter import (
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    WORKFLOW_SOURCE_BLOB,
)
from .p9_evidence import (
    CONTROL_BASELINE_KEYS,
    CONTROL_BASELINE_RESOLVER,
    CONTROL_BASELINE_SCHEMA,
)
from .p9_provenance import (
    CONTROL_POSTCANARY_BASELINE_FILENAME,
    EVIDENCE_ROOT,
    MAX_EVIDENCE_BYTES,
    SERVICE_GROUP,
)

TARGET_REPOSITORY = "rozkalnsandris/ops-workflows"
TARGET_PROJECT_ID = "ops-workflows"
CANARY_WORKFLOW_NAME = "Phase 3 Merge one-shot canary"
CANARY_WORKFLOW_PATH = ".github/workflows/phase3-merge-one-shot-canary.yml"
CANARY_JOB_NAME = "execute exact authorized one-shot Merge canary"

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_ROOT_UID = 0
_DIRECTORY_MODE = 0o750
_FILE_MODE = 0o440


class ControlPostCanaryProducerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ControlPostCanaryObservation:
    observed_at: datetime
    resolver_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    workflow_source_blob: str
    canary_run_id: int
    canary_run: Mapping[str, Any]
    canary_jobs: tuple[Mapping[str, Any], ...]
    target_issue_number: int
    target_issue: Mapping[str, Any]
    target_pr_number: int
    target_pr: Mapping[str, Any]
    expected_pr_head: str
    expected_old_main: str
    expected_merge_sha: str
    target_merge_commit: Mapping[str, Any]
    target_compare: Mapping[str, Any]
    request_id: str
    audit_rows: tuple[Mapping[str, Any], ...]
    target_audit_rows: tuple[Mapping[str, Any], ...]
    d1_selects: tuple[Mapping[str, Any], ...]
    observed_mutation_classes: tuple[str, ...] = ()


def _canonical_time(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ControlPostCanaryProducerError("observed_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_sha(value: Any, where: str) -> str:
    if type(value) is not str or SHA40_RE.fullmatch(value) is None:
        raise ControlPostCanaryProducerError(f"{where} must be a lowercase 40-character SHA")
    return value


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise ControlPostCanaryProducerError(f"{where} must be a positive integer")
    return value


def _nonempty_string(value: Any) -> bool:
    return type(value) is str and bool(value)


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if type(current) is not dict:
            return None
        current = current.get(key)
    return current


def _canary_exact(observation: ControlPostCanaryObservation) -> bool:
    run = observation.canary_run
    if type(run) is not dict:
        return False
    run_ok = (
        run.get("id") == observation.canary_run_id
        and run.get("name") == CANARY_WORKFLOW_NAME
        and run.get("path") == CANARY_WORKFLOW_PATH
        and run.get("head_branch") == "main"
        and run.get("head_sha") == observation.source_sha
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("conclusion") == "failure"
        and type(run.get("run_attempt")) is int
        and run.get("run_attempt") == 1
    )
    matching_jobs = [
        row
        for row in observation.canary_jobs
        if type(row) is dict
        and row.get("name") == CANARY_JOB_NAME
        and row.get("status") == "completed"
        and row.get("conclusion") == "failure"
        and type(row.get("run_attempt")) is int
        and row.get("run_attempt") == 1
    ]
    return run_ok and len(matching_jobs) == 1


def _target_issue_exact(observation: ControlPostCanaryObservation) -> bool:
    issue = observation.target_issue
    return (
        type(issue) is dict
        and issue.get("number") == observation.target_issue_number
        and issue.get("state") == "open"
        and "pull_request" not in issue
    )


def _target_pr_exact(observation: ControlPostCanaryObservation) -> bool:
    pr = observation.target_pr
    return (
        type(pr) is dict
        and pr.get("number") == observation.target_pr_number
        and pr.get("state") == "closed"
        and _nonempty_string(pr.get("merged_at"))
        and pr.get("draft") is False
        and _nested(pr, "head", "sha") == observation.expected_pr_head
        and _nested(pr, "head", "repo", "full_name") == TARGET_REPOSITORY
        and _nested(pr, "base", "ref") == "main"
        and _nested(pr, "base", "repo", "full_name") == TARGET_REPOSITORY
        and pr.get("merge_commit_sha") == observation.expected_merge_sha
    )


def _merge_parent_exact(observation: ControlPostCanaryObservation) -> bool:
    commit = observation.target_merge_commit
    parents = commit.get("parents") if type(commit) is dict else None
    return (
        type(commit) is dict
        and commit.get("sha") == observation.expected_merge_sha
        and type(parents) is list
        and len(parents) == 1
        and type(parents[0]) is dict
        and parents[0].get("sha") == observation.expected_old_main
    )


def _main_descends_from_merge(observation: ControlPostCanaryObservation) -> bool:
    compare = observation.target_compare
    return (
        type(compare) is dict
        and compare.get("status") in {"identical", "ahead"}
        and _nested(compare, "merge_base_commit", "sha") == observation.expected_merge_sha
    )


def _audit_row_exact(observation: ControlPostCanaryObservation) -> bool:
    if len(observation.audit_rows) != 1 or type(observation.audit_rows[0]) is not dict:
        return False
    row = observation.audit_rows[0]
    return (
        row.get("request_id") == observation.request_id
        and row.get("repository") == TARGET_REPOSITORY
        and row.get("project_id") == TARGET_PROJECT_ID
        and row.get("issue_number") == observation.target_issue_number
        and row.get("pull_number") == observation.target_pr_number
        and row.get("merge_method") == "squash"
        and row.get("expected_head_sha") == observation.expected_pr_head
        and row.get("expected_main_sha") == observation.expected_old_main
        and _nonempty_string(row.get("requested_at"))
        and row.get("state") == "SUCCEEDED"
        and row.get("outcome_code") is None
        and type(row.get("mutation_attempted")) is int
        and row.get("mutation_attempted") == 1
        and row.get("observed_head_sha") == observation.expected_pr_head
        and row.get("observed_main_sha") == observation.expected_old_main
        and _nonempty_string(row.get("observed_at"))
        and row.get("merge_sha") == observation.expected_merge_sha
        and _nonempty_string(row.get("completed_at"))
    )


def _target_audit_exactly_one(observation: ControlPostCanaryObservation) -> bool:
    if len(observation.target_audit_rows) != 1 or type(observation.target_audit_rows[0]) is not dict:
        return False
    row = observation.target_audit_rows[0]
    return (
        row.get("request_id") == observation.request_id
        and row.get("state") == "SUCCEEDED"
        and row.get("merge_sha") == observation.expected_merge_sha
    )


def _d1_select_only_zero_write(observation: ControlPostCanaryObservation) -> bool:
    if len(observation.d1_selects) != 2:
        return False
    for item in observation.d1_selects:
        if type(item) is not dict:
            return False
        sql = item.get("sql")
        if type(sql) is not str or not sql.startswith("SELECT "):
            return False
        if item.get("success") is not True or item.get("result_success") is not True:
            return False
        if item.get("changed_db") is not False:
            return False
        if type(item.get("rows_written")) is not int or item.get("rows_written") != 0:
            return False
        if type(item.get("changes")) is not int or item.get("changes") != 0:
            return False
    return True


def build_control_postcanary_baseline_evidence(
    observation: ControlPostCanaryObservation,
) -> dict[str, Any]:
    observed_at = _canonical_time(observation.observed_at)
    _positive_int(observation.canary_run_id, "canary_run_id")
    _positive_int(observation.target_issue_number, "target_issue_number")
    _positive_int(observation.target_pr_number, "target_pr_number")
    _require_sha(observation.source_sha, "source_sha")
    _require_sha(observation.expected_pr_head, "expected_pr_head")
    _require_sha(observation.expected_old_main, "expected_old_main")
    _require_sha(observation.expected_merge_sha, "expected_merge_sha")
    if type(observation.request_id) is not str or not observation.request_id:
        raise ControlPostCanaryProducerError("request_id must be a non-empty string")

    identity_ok = (
        observation.resolver_id == CONTROL_BASELINE_RESOLVER
        and observation.target_alias == TARGET_ALIAS
        and observation.source_repository == SOURCE_REPOSITORY
        and observation.workflow_source_blob == WORKFLOW_SOURCE_BLOB
    )
    if not identity_ok:
        raise ControlPostCanaryProducerError(
            "Control post-canary observation does not match the reviewed source identity"
        )

    checks = {
        "canary_run_terminal_failure_exact": _canary_exact(observation),
        "target_issue_exact": _target_issue_exact(observation),
        "target_pr_merge_evidence_exact": _target_pr_exact(observation),
        "target_merge_parent_exact": _merge_parent_exact(observation),
        "target_main_descends_from_merge": _main_descends_from_merge(observation),
        "audit_row_exact": _audit_row_exact(observation),
        "target_audit_row_count_one": _target_audit_exactly_one(observation),
        "d1_select_only_zero_write": _d1_select_only_zero_write(observation),
        "mutation_surface_read_only": (
            observation.workflow_source_blob == WORKFLOW_SOURCE_BLOB
            and observation.observed_mutation_classes == ()
        ),
    }
    failed = sorted(name for name, passed in checks.items() if passed is not True)
    if failed:
        raise ControlPostCanaryProducerError(
            f"Control post-canary observation failed reviewed checks: {failed}"
        )

    evidence = {
        "schema": CONTROL_BASELINE_SCHEMA,
        "resolver_id": CONTROL_BASELINE_RESOLVER,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "source_sha": observation.source_sha,
        "observed_at": observed_at,
        **{name: True for name in checks},
    }
    if frozenset(evidence) != CONTROL_BASELINE_KEYS:
        raise ControlPostCanaryProducerError(
            "Control baseline evidence keys drifted from the semantic resolver"
        )
    return evidence


def _service_gid() -> int:
    try:
        entry = grp.getgrnam(SERVICE_GROUP)
    except KeyError as exc:
        raise ControlPostCanaryProducerError("executor service group is missing") from exc
    if type(entry.gr_gid) is not int or entry.gr_gid < 0:
        raise ControlPostCanaryProducerError("executor service group id is invalid")
    return entry.gr_gid


def _require_platform_guards() -> None:
    for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC"):
        if type(getattr(os, name, None)) is not int:
            raise ControlPostCanaryProducerError(
                "required atomic publisher guards are unavailable"
            )
    if os.open not in getattr(os, "supports_dir_fd", set()):
        raise ControlPostCanaryProducerError("required dir_fd open guard is unavailable")
    if os.rename not in getattr(os, "supports_dir_fd", set()):
        raise ControlPostCanaryProducerError(
            "required dir_fd atomic rename guard is unavailable"
        )


def _require_root() -> None:
    if os.geteuid() != _ROOT_UID:
        raise ControlPostCanaryProducerError(
            "trusted Control evidence publisher requires root"
        )


def _require_root_directory(info: os.stat_result, *, gid: int) -> None:
    if not stat.S_ISDIR(info.st_mode):
        raise ControlPostCanaryProducerError("evidence root is not a directory")
    if info.st_uid != _ROOT_UID or info.st_gid != gid:
        raise ControlPostCanaryProducerError("evidence root ownership mismatch")
    if stat.S_IMODE(info.st_mode) != _DIRECTORY_MODE:
        raise ControlPostCanaryProducerError("evidence root mode mismatch")


def _canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    if type(payload) is not dict or frozenset(payload) != CONTROL_BASELINE_KEYS:
        raise ControlPostCanaryProducerError(
            "Control producer payload keys do not match the frozen evidence schema"
        )
    if payload.get("schema") != CONTROL_BASELINE_SCHEMA:
        raise ControlPostCanaryProducerError("Control producer payload schema mismatch")
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise ControlPostCanaryProducerError(
            "Control producer payload size is outside allowed bounds"
        )
    return raw


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise ControlPostCanaryProducerError(
                "Control evidence publisher made no forward progress"
            )
        offset += written


def publish_control_postcanary_baseline_evidence(
    observation: ControlPostCanaryObservation,
) -> str:
    _require_platform_guards()
    _require_root()
    gid = _service_gid()
    data = _canonical_payload_bytes(
        build_control_postcanary_baseline_evidence(observation)
    )
    root_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_fd = os.open(EVIDENCE_ROOT, root_flags)
    except OSError as exc:
        raise ControlPostCanaryProducerError("evidence root is unavailable") from exc

    temp_name = (
        f".{CONTROL_POSTCANARY_BASELINE_FILENAME}.tmp."
        f"{os.getpid()}.{secrets.token_hex(8)}"
    )
    try:
        _require_root_directory(os.fstat(root_fd), gid=gid)
        temp_flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        )
        try:
            temp_fd = os.open(
                temp_name, temp_flags, _FILE_MODE, dir_fd=root_fd
            )
        except OSError as exc:
            raise ControlPostCanaryProducerError(
                "cannot create Control evidence temporary file"
            ) from exc
        try:
            os.fchown(temp_fd, _ROOT_UID, gid)
            os.fchmod(temp_fd, _FILE_MODE)
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)

        try:
            os.rename(
                temp_name,
                CONTROL_POSTCANARY_BASELINE_FILENAME,
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
            )
        except OSError as exc:
            raise ControlPostCanaryProducerError(
                "atomic Control evidence replacement failed"
            ) from exc
        os.fsync(root_fd)
    finally:
        os.close(root_fd)

    return hashlib.sha256(data).hexdigest()
