#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_producer as producer
from deploy_executor.p9_evidence import GOVERNANCE_KEYS, HERMES_BASELINE_KEYS

NOW = datetime(2026, 8, 28, 20, 15, tzinfo=timezone.utc)
SHA_A = "1" * 40
SHA_B = "2" * 40


def governance_observation(**changes):
    base = producer.GovernanceWriterSurfaceObservation(
        repository=producer.AUTHORIZATION_REPOSITORY,
        repository_id=producer.AUTHORIZATION_REPOSITORY_ID,
        observed_at=NOW,
        covered_surfaces=producer._REQUIRED_GOVERNANCE_SURFACES,
        human_writers=("user:277435981",),
        team_writers=(),
        app_writers=("app:1144995",),
        workflow_writers=(),
        token_writers=(),
        unknown_writers=(),
    )
    return replace(base, **changes)


def hermes_observation(**changes):
    base = producer.HermesOriginObservation(
        observed_at=NOW,
        resolver_id=producer.HERMES_BASELINE_RESOLVER,
        target_alias=producer.HERMES_TARGET_ALIAS,
        source_repository=producer.HERMES_SOURCE_REPOSITORY,
        registered_commit_sha=SHA_A,
        observed_source_commit_sha=SHA_A,
        registration_source_repository=producer.HERMES_SOURCE_REPOSITORY,
        installer_source_blob=producer.INSTALLER_SOURCE_BLOB,
        probe_source_blob=producer.PROBE_SOURCE_BLOB,
        dispatcher_source_blob=producer.DISPATCHER_SOURCE_BLOB,
        workflow_source_blob=producer.HERMES_WORKFLOW_SOURCE_BLOB,
        observed_mutation_classes=(),
    )
    return replace(base, **changes)


def expect_error(func, contains: str) -> None:
    try:
        func()
    except producer.P9ProducerError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected P9ProducerError containing {contains!r}")


def test_governance_fails_closed_without_source_pin() -> None:
    with mock.patch.object(producer, "APPROVED_GOVERNANCE_WRITER_SET_SHA256", None):
        expect_error(
            lambda: producer.build_governance_evidence(governance_observation()),
            "not source-pinned",
        )


def test_governance_requires_complete_writer_surface() -> None:
    incomplete = frozenset(set(producer._REQUIRED_GOVERNANCE_SURFACES) - {"teams"})
    expect_error(
        lambda: producer.governance_writer_set_sha256(
            governance_observation(covered_surfaces=incomplete)
        ),
        "complete writer surface",
    )


def test_governance_rejects_unknown_writer() -> None:
    expect_error(
        lambda: producer.governance_writer_set_sha256(
            governance_observation(unknown_writers=("unknown:writer",))
        ),
        "unknown writers",
    )


def test_governance_rejects_duplicate_or_uncanonical_identity() -> None:
    expect_error(
        lambda: producer.governance_writer_set_sha256(
            governance_observation(human_writers=("user:277435981", "user:277435981"))
        ),
        "duplicate",
    )
    expect_error(
        lambda: producer.governance_writer_set_sha256(
            governance_observation(human_writers=(" user:277435981",))
        ),
        "invalid identity",
    )


def test_governance_emits_trusted_only_for_source_approved_digest() -> None:
    observation = governance_observation()
    digest = producer.governance_writer_set_sha256(observation)
    with mock.patch.object(producer, "APPROVED_GOVERNANCE_WRITER_SET_SHA256", digest):
        evidence = producer.build_governance_evidence(observation)
    assert frozenset(evidence) == GOVERNANCE_KEYS
    assert evidence["writer_set_sha256"] == digest
    assert evidence["trusted"] is True
    assert evidence["observed_at"] == "2026-08-28T20:15:00Z"


def test_governance_rejects_writer_set_drift() -> None:
    approved = producer.governance_writer_set_sha256(governance_observation())
    drifted = governance_observation(app_writers=("app:different",))
    with mock.patch.object(producer, "APPROVED_GOVERNANCE_WRITER_SET_SHA256", approved):
        expect_error(
            lambda: producer.build_governance_evidence(drifted),
            "source-approved trust root",
        )


def test_hermes_derives_all_safety_assertions() -> None:
    evidence = producer.build_hermes_origin_baseline_evidence(hermes_observation())
    assert frozenset(evidence) == HERMES_BASELINE_KEYS
    assert evidence["registered_commit_sha"] == SHA_A
    for flag in (
        "registration_identity_ok",
        "registered_source_match",
        "probe_identity_ok",
        "dispatcher_identity_ok",
        "workflow_identity_ok",
        "mutation_surface_read_only",
    ):
        assert evidence[flag] is True


def test_hermes_rejects_reviewed_identity_drift() -> None:
    cases = (
        (replace(hermes_observation(), resolver_id="wrong.resolver"), "registration_identity_ok"),
        (replace(hermes_observation(), registration_source_repository="wrong/repo"), "registered_source_match"),
        (replace(hermes_observation(), installer_source_blob="0" * 40), "registration_identity_ok"),
        (replace(hermes_observation(), probe_source_blob="0" * 40), "probe_identity_ok"),
        (replace(hermes_observation(), dispatcher_source_blob="0" * 40), "dispatcher_identity_ok"),
        (replace(hermes_observation(), workflow_source_blob="0" * 40), "workflow_identity_ok"),
        (replace(hermes_observation(), observed_mutation_classes=("write",)), "mutation_surface_read_only"),
    )
    for observation, flag in cases:
        expect_error(
            lambda observation=observation: producer.build_hermes_origin_baseline_evidence(observation),
            flag,
        )


def test_hermes_registration_must_match_independent_source_sha() -> None:
    expect_error(
        lambda: producer.build_hermes_origin_baseline_evidence(
            hermes_observation(observed_source_commit_sha=SHA_B)
        ),
        "registered_source_match",
    )


def test_hermes_rejects_malformed_source_sha() -> None:
    expect_error(
        lambda: producer.build_hermes_origin_baseline_evidence(
            hermes_observation(registered_commit_sha="ABC")
        ),
        "registered Hermes source SHA",
    )
    expect_error(
        lambda: producer.build_hermes_origin_baseline_evidence(
            hermes_observation(observed_source_commit_sha="ABC")
        ),
        "observed Hermes source SHA",
    )


def test_atomic_publisher_writes_fixed_file_only() -> None:
    observation = governance_observation()
    approved = producer.governance_writer_set_sha256(observation)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        root.mkdir(mode=0o750)
        os.chmod(root, 0o750)
        with mock.patch.object(producer, "EVIDENCE_ROOT", root), \
             mock.patch.object(producer, "_ROOT_UID", os.getuid()), \
             mock.patch.object(producer, "_service_gid", return_value=os.getgid()), \
             mock.patch.object(producer, "APPROVED_GOVERNANCE_WRITER_SET_SHA256", approved):
            digest = producer.publish_governance_evidence(observation)
        target = root / producer.GOVERNANCE_FILENAME
        data = target.read_bytes()
        assert digest == hashlib.sha256(data).hexdigest()
        assert frozenset(json.loads(data)) == GOVERNANCE_KEYS
        assert stat.S_IMODE(target.stat().st_mode) == 0o440
        assert list(root.glob(f".{producer.GOVERNANCE_FILENAME}.tmp.*")) == []


def test_atomic_replace_failure_preserves_temp_evidence() -> None:
    observation = governance_observation()
    approved = producer.governance_writer_set_sha256(observation)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        root.mkdir(mode=0o750)
        os.chmod(root, 0o750)
        with mock.patch.object(producer, "EVIDENCE_ROOT", root), \
             mock.patch.object(producer, "_ROOT_UID", os.getuid()), \
             mock.patch.object(producer, "_service_gid", return_value=os.getgid()), \
             mock.patch.object(producer, "APPROVED_GOVERNANCE_WRITER_SET_SHA256", approved), \
             mock.patch.object(producer, "_require_platform_guards", return_value=None), \
             mock.patch.object(producer.os, "rename", side_effect=OSError("synthetic rename failure")):
            expect_error(
                lambda: producer.publish_governance_evidence(observation),
                "atomic evidence replacement failed",
            )
        assert not (root / producer.GOVERNANCE_FILENAME).exists()
        assert len(list(root.glob(f".{producer.GOVERNANCE_FILENAME}.tmp.*"))) == 1


def test_publisher_rejects_non_root_identity() -> None:
    with mock.patch.object(producer, "_ROOT_UID", os.geteuid() + 1):
        expect_error(producer._require_root, "requires root")


def main() -> None:
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
    print(f"P9_PRODUCER_TESTS=PASS count={len(tests)}")


if __name__ == "__main__":
    main()
