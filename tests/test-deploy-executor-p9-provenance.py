#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_provenance as provenance


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


def expect_error(root: Path, func, contains: str) -> None:
    try:
        load_with_test_identity(root, func)
    except provenance.ProvenanceError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected ProvenanceError containing {contains!r}")


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


def test_valid_baseline() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        data = payload(provenance.HERMES_ORIGIN_BASELINE_SCHEMA)
        make_file(root, provenance.HERMES_ORIGIN_BASELINE_FILENAME, data)
        result = load_with_test_identity(root, provenance.load_hermes_origin_baseline_evidence)
        assert result.payload["schema"] == provenance.HERMES_ORIGIN_BASELINE_SCHEMA


def test_reject_directory_mode() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        os.chmod(root, 0o770)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        expect_error(root, provenance.load_governance_evidence, "root mode")


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
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA), 0o640)
        expect_error(root, provenance.load_governance_evidence, "object mode")


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
        expect_error(root, provenance.load_governance_evidence, "unavailable")


def test_reject_hardlink() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        path = make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.GOVERNANCE_SCHEMA))
        os.link(path, root / "alias.json")
        expect_error(root, provenance.load_governance_evidence, "link count")


def test_reject_schema_swap() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, payload(provenance.HERMES_ORIGIN_BASELINE_SCHEMA))
        expect_error(root, provenance.load_governance_evidence, "schema mismatch")


def test_reject_oversize() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "evidence"
        make_root(root)
        make_file(root, provenance.GOVERNANCE_FILENAME, b"x" * (provenance.MAX_EVIDENCE_BYTES + 1))
        expect_error(root, provenance.load_governance_evidence, "size")


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
    from datetime import datetime, timezone
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
    import inspect
    assert list(inspect.signature(provenance.load_governance_evidence).parameters) == []
    assert list(inspect.signature(provenance.load_hermes_origin_baseline_evidence).parameters) == []


def main() -> None:
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
    print(f"P9_PROVENANCE_TESTS=PASS count={len(tests)}")


if __name__ == "__main__":
    main()
