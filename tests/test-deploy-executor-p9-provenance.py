#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_control_postcanary_producer as control_producer
from deploy_executor import p9_provenance as provenance
from deploy_executor.p9_evidence import (
    CONTROL_BASELINE_KEYS,
    CONTROL_BASELINE_RESOLVER,
    resolve_control_postcanary_baseline,
)

NOW = datetime(2026, 8, 30, 10, 29, tzinfo=timezone.utc)
SOURCE_SHA = "1" * 40
PR_HEAD = "2" * 40
OLD_MAIN = "3" * 40
MERGE_SHA = "4" * 40
REQUEST_ID = "request-merge-canary-1234"


def payload(schema: str) -> bytes:
    return json.dumps({"schema": schema, "value": "sanitized"}, separators=(",", ":")).encode()


def make_root(root: Path) -> None:
    root.mkdir(mode=0o750)
    os.chmod(root, 0o750)


def make_file(root: Path, name: str, data: bytes, mode: int = 0o440) -> Path:
    path = root / name
    path.write_bytes(data)
    os.chmod(path, mode)
    return path


def load_with_test_identity(root: Path, func):
    with mock.patch.object(provenance, "EVIDENCE_ROOT", root), \
         mock.patch.object(provenance, "_ROOT_UID", os.getuid()), \
         mock.patch.object(provenance, "_service_gid", return_value=os.getgid()):
        return func()


def expect_provenance_error(root: Path, func, contains: str) -> None:
    try:
        load_with_test_identity(root, func)
    except provenance.ProvenanceError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected ProvenanceError containing {contains!r}")


def expect_control_error(func, contains: str) -> None:
    try:
        func()
    except control_producer.ControlPostCanaryProducerError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(
            f"expected ControlPostCanaryProducerError containing {contains!r}"
        )


def control_observation(**changes):
    base = control_producer.ControlPostCanaryObservation(
        observed_at=NOW,
        resolver_id=CONTROL_BASELINE_RESOLVER,
        target_alias=control_producer.TARGET_ALIAS,
        source_repository=control_producer.SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        workflow_source_blob=control_producer.WORKFLOW_SOURCE_BLOB,
        canary_run_id=333,
        canary_run={
            "id": 333,
            "name": control_producer.CANARY_WORKFLOW_NAME,
            "path": control_producer.CANARY_WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": SOURCE_SHA,
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "failure",
            "run_attempt": 1,
        },
        canary_jobs=(
            {
                "name": control_producer.CANARY_JOB_NAME,
                "status": "completed",
                "conclusion": "failure",
                "run_attempt": 1,
            },
        ),
        target_issue_number=278,
        target_issue={"number": 278, "state": "open"},
        target_pr_number=491,
        target_pr={
            "number": 491,
            "state": "closed",
            "merged_at": "2026-08-30T08:56:24Z",
            "draft": False,
            "head": {
                "sha": PR_HEAD,
                "repo": {"full_name": control_producer.TARGET_REPOSITORY},
            },
            "base": {
                "ref": "main",
                "repo": {"full_name": control_producer.TARGET_REPOSITORY},
            },
            "merge_commit_sha": MERGE_SHA,
        },
        expected_pr_head=PR_HEAD,
        expected_old_main=OLD_MAIN,
        expected_merge_sha=MERGE_SHA,
        target_merge_commit={"sha": MERGE_SHA, "parents": [{"sha": OLD_MAIN}]},
        target_compare={
            "status": "ahead",
            "merge_base_commit": {"sha": MERGE_SHA},
        },
        request_id=REQUEST_ID,
        audit_rows=(
            {
                "request_id": REQUEST_ID,
                "repository": control_producer.TARGET_REPOSITORY,
                "project_id": control_producer.TARGET_PROJECT_ID,
                "issue_number": 278,
                "pull_number": 491,
                "merge_method": "squash",
                "expected_head_sha": PR_HEAD,
                "expected_main_sha": OLD_MAIN,
                "requested_at": "2026-08-30T08:54:00Z",
                "state": "SUCCEEDED",
                "outcome_code": None,
                "mutation_attempted": 1,
                "observed_head_sha": PR_HEAD,
                "observed_main_sha": OLD_MAIN,
                "observed_at": "2026-08-30T08:55:00Z",
                "merge_sha": MERGE_SHA,
                "completed_at": "2026-08-30T08:56:24Z",
            },
        ),
        target_audit_rows=(
            {
                "request_id": REQUEST_ID,
                "state": "SUCCEEDED",
                "merge_sha": MERGE_SHA,
            },
        ),
        d1_selects=(
            {
                "sql": "SELECT request_id FROM merge_decisions WHERE request_id = ? LIMIT 2",
                "success": True,
                "result_success": True,
                "changed_db": False,
                "rows_written": 0,
                "changes": 0,
            },
            {
                "sql": "SELECT request_id FROM merge_decisions WHERE repository = ? LIMIT 3",
                "success": True,
                "result_success": True,
                "changed_db": False,
                "rows_written": 0,
                "changes": 0,
            },
        ),
        observed_mutation_classes=(),
    )
    return replace(base, **changes)


def test_valid_governance() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        data = payload(provenance.GOVERNANCE_SCHEMA)
        make_file(root, provenance.GOVERNANCE_FILENAME, data)
        result = load_with_test_identity(root, provenance.load_governance_evidence)
        assert result.filename == provenance.GOVERNANCE_FILENAME
        assert result.payload["schema"] == provenance.GOVERNANCE_SCHEMA
        assert len(result.sha256) == 64
        assert type(result.payload) is dict


def test_valid_hermes_baseline() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        data = payload(provenance.HERMES_ORIGIN_BASELINE_SCHEMA)
        make_file(root, provenance.HERMES_ORIGIN_BASELINE_FILENAME, data)
        result = load_with_test_identity(
            root, provenance.load_hermes_origin_baseline_evidence
        )
        assert result.payload["schema"] == provenance.HERMES_ORIGIN_BASELINE_SCHEMA


def test_control_producer_derives_exact_semantic_evidence() -> None:
    evidence = control_producer.build_control_postcanary_baseline_evidence(
        control_observation()
    )
    assert frozenset(evidence) == CONTROL_BASELINE_KEYS
    assert evidence["source_sha"] == SOURCE_SHA
    assert evidence["observed_at"] == "2026-08-30T10:29:00Z"
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
        assert evidence[flag] is True


def test_control_producer_rejects_source_identity_drift() -> None:
    for observation in (
        control_observation(resolver_id="wrong.resolver"),
        control_observation(target_alias="wrong-target"),
        control_observation(source_repository="wrong/repo"),
        control_observation(workflow_source_blob="0" * 40),
    ):
        expect_control_error(
            lambda observation=observation:
                control_producer.build_control_postcanary_baseline_evidence(observation),
            "reviewed source identity",
        )


def test_control_producer_rejects_each_reviewed_predicate_drift() -> None:
    canary = dict(control_observation().canary_run)
    canary["conclusion"] = "success"

    issue = dict(control_observation().target_issue)
    issue["state"] = "closed"

    pr = dict(control_observation().target_pr)
    pr["draft"] = True

    merge_commit = {"sha": MERGE_SHA, "parents": [{"sha": "5" * 40}]}
    compare = {"status": "behind", "merge_base_commit": {"sha": MERGE_SHA}}

    audit = dict(control_observation().audit_rows[0])
    audit["state"] = "FAILED"

    d1 = [dict(item) for item in control_observation().d1_selects]
    d1[0]["changes"] = 1

    cases = (
        (control_observation(canary_run=canary), "canary_run_terminal_failure_exact"),
        (control_observation(target_issue=issue), "target_issue_exact"),
        (control_observation(target_pr=pr), "target_pr_merge_evidence_exact"),
        (control_observation(target_merge_commit=merge_commit), "target_merge_parent_exact"),
        (control_observation(target_compare=compare), "target_main_descends_from_merge"),
        (control_observation(audit_rows=(audit,)), "audit_row_exact"),
        (control_observation(target_audit_rows=()), "target_audit_row_count_one"),
        (control_observation(d1_selects=tuple(d1)), "d1_select_only_zero_write"),
        (
            control_observation(observed_mutation_classes=("github-write",)),
            "mutation_surface_read_only",
        ),
    )
    for observation, flag in cases:
        expect_control_error(
            lambda observation=observation:
                control_producer.build_control_postcanary_baseline_evidence(observation),
            flag,
        )


def test_control_producer_rejects_non_select_d1_and_malformed_sha() -> None:
    d1 = [dict(item) for item in control_observation().d1_selects]
    d1[1]["sql"] = "UPDATE merge_decisions SET state = ?"
    expect_control_error(
        lambda: control_producer.build_control_postcanary_baseline_evidence(
            control_observation(d1_selects=tuple(d1))
        ),
        "d1_select_only_zero_write",
    )
    expect_control_error(
        lambda: control_producer.build_control_postcanary_baseline_evidence(
            control_observation(source_sha="ABC")
        ),
        "source_sha",
    )


def test_control_atomic_publisher_and_provenance_loader() -> None:
    observation = control_observation()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        with mock.patch.object(control_producer, "EVIDENCE_ROOT", root), \
             mock.patch.object(control_producer, "_ROOT_UID", os.getuid()), \
             mock.patch.object(control_producer, "_service_gid", return_value=os.getgid()):
            digest = control_producer.publish_control_postcanary_baseline_evidence(
                observation
            )
        target = root / provenance.CONTROL_POSTCANARY_BASELINE_FILENAME
        data = target.read_bytes()
        assert digest == hashlib.sha256(data).hexdigest()
        assert frozenset(json.loads(data)) == CONTROL_BASELINE_KEYS
        assert list(
            root.glob(f".{provenance.CONTROL_POSTCANARY_BASELINE_FILENAME}.tmp.*")
        ) == []

        loaded = load_with_test_identity(
            root, provenance.load_control_postcanary_baseline_evidence
        )
        assert loaded.sha256 == digest
        assert loaded.payload["schema"] == provenance.CONTROL_POSTCANARY_BASELINE_SCHEMA


def test_control_loaded_evidence_matches_strict_semantic_resolver() -> None:
    evidence = control_producer.build_control_postcanary_baseline_evidence(
        control_observation()
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(
            root,
            provenance.CONTROL_POSTCANARY_BASELINE_FILENAME,
            (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        )
        loaded = load_with_test_identity(
            root, provenance.load_control_postcanary_baseline_evidence
        )
    operation = SimpleNamespace(
        operation_id="rozkalns-control-center.merge-postcanary-reconcile.v1",
        source_repository=control_producer.SOURCE_REPOSITORY,
        target_alias=control_producer.TARGET_ALIAS,
        baseline=SimpleNamespace(
            kind="resolver",
            resolver_id=CONTROL_BASELINE_RESOLVER,
        ),
    )
    parsed = resolve_control_postcanary_baseline(
        operation,
        {"kind": "resolver", "value": CONTROL_BASELINE_RESOLVER},
        evidence=loaded.payload,
        source_sha=SOURCE_SHA,
        server_time=NOW,
    )
    assert parsed.matched is True
    assert parsed.target_alias == control_producer.TARGET_ALIAS


def test_reject_directory_mode() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        os.chmod(root, 0o770)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        expect_provenance_error(root, provenance.load_governance_evidence, "root mode")


def test_reject_directory_ownership() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        with mock.patch.object(provenance, "EVIDENCE_ROOT", root), \
             mock.patch.object(provenance, "_ROOT_UID", os.getuid() + 1), \
             mock.patch.object(provenance, "_service_gid", return_value=os.getgid()):
            try:
                provenance.load_governance_evidence()
            except provenance.ProvenanceError as exc:
                assert "root ownership" in str(exc)
            else:
                raise AssertionError("expected directory ownership rejection")


def test_reject_file_mode() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(
            root,
            provenance.GOVERNANCE_FILENAME,
            payload(provenance.GOVERNANCE_SCHEMA),
            0o640,
        )
        expect_provenance_error(root, provenance.load_governance_evidence, "object mode")


def test_reject_file_group() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        with mock.patch.object(provenance, "EVIDENCE_ROOT", root), \
             mock.patch.object(provenance, "_ROOT_UID", os.getuid()), \
             mock.patch.object(provenance, "_service_gid", return_value=os.getgid() + 1):
            try:
                provenance.load_governance_evidence()
            except provenance.ProvenanceError as exc:
                assert "root ownership" in str(exc) or "object ownership" in str(exc)
            else:
                raise AssertionError("expected ownership rejection")


def test_reject_symlink() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        target = root / "real.json"
        target.write_bytes(payload(provenance.GOVERNANCE_SCHEMA))
        os.chmod(target, 0o440)
        (root / provenance.GOVERNANCE_FILENAME).symlink_to(target.name)
        expect_provenance_error(root, provenance.load_governance_evidence, "unavailable")


def test_reject_hardlink() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        path = make_file(
            root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA)
        )
        os.link(path, root / "alias.json")
        expect_provenance_error(root, provenance.load_governance_evidence, "link count")


def test_reject_schema_swap() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(
            root,
            provenance.CONTROL_POSTCANARY_BASELINE_FILENAME,
            payload(provenance.HERMES_ORIGIN_BASELINE_SCHEMA),
        )
        expect_provenance_error(
            root,
            provenance.load_control_postcanary_baseline_evidence,
            "schema mismatch",
        )


def test_reject_oversize() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(
            root,
            provenance.GOVERNANCE_FILENAME,
            b"x" * (provenance.MAX_EVIDENCE_BYTES + 1),
        )
        expect_provenance_error(root, provenance.load_governance_evidence, "size")


def test_reject_missing_no_follow_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        with mock.patch.object(provenance, "EVIDENCE_ROOT", root), \
             mock.patch.object(provenance.os, "O_NOFOLLOW", None):
            try:
                provenance.load_governance_evidence()
            except provenance.ProvenanceError as exc:
                assert "guards" in str(exc)
            else:
                raise AssertionError("expected missing O_NOFOLLOW guard rejection")


def test_reject_missing_dir_fd_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        with mock.patch.object(provenance, "EVIDENCE_ROOT", root), \
             mock.patch.object(provenance.os, "supports_dir_fd", set()):
            try:
                provenance.load_governance_evidence()
            except provenance.ProvenanceError as exc:
                assert "dir_fd" in str(exc)
            else:
                raise AssertionError("expected missing dir_fd guard rejection")


def test_payload_remains_compatible_with_strict_semantic_parser() -> None:
    from deploy_executor.p9_evidence import parse_governance_evidence

    evidence = {
        "schema": provenance.GOVERNANCE_SCHEMA,
        "repository": "rozkalnsandris/ops-workflows",
        "repository_id": 1328835922,
        "observed_at": "2026-08-28T19:14:30Z",
        "writer_set_sha256": "b" * 64,
        "trusted": True,
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(
            root,
            provenance.GOVERNANCE_FILENAME,
            json.dumps(evidence, separators=(",", ":")).encode(),
        )
        loaded = load_with_test_identity(root, provenance.load_governance_evidence)
        parsed = parse_governance_evidence(
            loaded.payload,
            server_time=datetime(2026, 8, 28, 19, 15, tzinfo=timezone.utc),
        )
        assert parsed.writer_set_sha256 == "b" * 64


def test_no_path_argument_surface() -> None:
    assert list(inspect.signature(provenance.load_governance_evidence).parameters) == []
    assert list(
        inspect.signature(provenance.load_hermes_origin_baseline_evidence).parameters
    ) == []
    assert list(
        inspect.signature(provenance.load_control_postcanary_baseline_evidence).parameters
    ) == []
    assert list(
        inspect.signature(
            control_producer.publish_control_postcanary_baseline_evidence
        ).parameters
    ) == ["observation"]


def main() -> None:
    tests = [
        value
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    ]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
    print(f"P9_PROVENANCE_TESTS=PASS count={len(tests)}")


if __name__ == "__main__":
    main()
