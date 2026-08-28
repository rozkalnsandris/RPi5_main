from __future__ import annotations

from dataclasses import dataclass
import grp
import hashlib
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Any, Mapping


class ProvenanceError(RuntimeError):
    pass


EVIDENCE_ROOT = Path("/run/rozkalns-deploy-executor-evidence")
SERVICE_GROUP = "rozkalns-deploy-executor"
GOVERNANCE_FILENAME = "governance.json"
HERMES_ORIGIN_BASELINE_FILENAME = "hermes-origin-baseline.json"
GOVERNANCE_SCHEMA = "rozkalns.deploy-executor-p9-governance-evidence.v1"
HERMES_ORIGIN_BASELINE_SCHEMA = "rozkalns.deploy-executor-p9-hermes-origin-baseline.v1"
MAX_EVIDENCE_BYTES = 64 * 1024
_ROOT_UID = 0
_DIRECTORY_MODE = 0o750
_FILE_MODE = 0o440


@dataclass(frozen=True)
class TrustedEvidence:
    payload: Mapping[str, Any]
    sha256: str
    filename: str


def _service_gid() -> int:
    try:
        entry = grp.getgrnam(SERVICE_GROUP)
    except KeyError as exc:
        raise ProvenanceError("executor service group is missing") from exc
    if type(entry.gr_gid) is not int or entry.gr_gid < 0:
        raise ProvenanceError("executor service group id is invalid")
    return entry.gr_gid


def _mode_bits(mode: int) -> int:
    return stat.S_IMODE(mode)


def _require_directory(info: os.stat_result, *, gid: int) -> None:
    if not stat.S_ISDIR(info.st_mode):
        raise ProvenanceError("evidence root is not a directory")
    if info.st_uid != _ROOT_UID or info.st_gid != gid:
        raise ProvenanceError("evidence root ownership mismatch")
    if _mode_bits(info.st_mode) != _DIRECTORY_MODE:
        raise ProvenanceError("evidence root mode mismatch")


def _require_file(info: os.stat_result, *, gid: int) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise ProvenanceError("evidence object is not a regular file")
    if info.st_uid != _ROOT_UID or info.st_gid != gid:
        raise ProvenanceError("evidence object ownership mismatch")
    if _mode_bits(info.st_mode) != _FILE_MODE:
        raise ProvenanceError("evidence object mode mismatch")
    if info.st_nlink != 1:
        raise ProvenanceError("evidence object link count mismatch")
    if info.st_size <= 0 or info.st_size > MAX_EVIDENCE_BYTES:
        raise ProvenanceError("evidence object size is outside allowed bounds")


def _read_all(fd: int, expected_size: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(8192, MAX_EVIDENCE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_EVIDENCE_BYTES:
            raise ProvenanceError("evidence object exceeds size limit")
    data = b"".join(chunks)
    if len(data) != expected_size:
        raise ProvenanceError("evidence object changed while being read")
    return data


def _load_fixed(filename: str, expected_schema: str) -> TrustedEvidence:
    if filename not in {GOVERNANCE_FILENAME, HERMES_ORIGIN_BASELINE_FILENAME}:
        raise ProvenanceError("evidence filename is not allowlisted")
    gid = _service_gid()
    root_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        root_flags |= os.O_NOFOLLOW
    try:
        root_fd = os.open(EVIDENCE_ROOT, root_flags)
    except OSError as exc:
        raise ProvenanceError("evidence root is unavailable") from exc
    try:
        _require_directory(os.fstat(root_fd), gid=gid)
        file_flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        try:
            evidence_fd = os.open(filename, file_flags, dir_fd=root_fd)
        except OSError as exc:
            raise ProvenanceError("evidence object is unavailable") from exc
        try:
            before = os.fstat(evidence_fd)
            _require_file(before, gid=gid)
            data = _read_all(evidence_fd, before.st_size)
            after = os.fstat(evidence_fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ProvenanceError("evidence object changed while being read")
        finally:
            os.close(evidence_fd)
    finally:
        os.close(root_fd)

    try:
        decoded = data.decode("utf-8", "strict")
        payload = json.loads(decoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError("evidence object is not valid UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise ProvenanceError("evidence object must be a JSON object")
    if payload.get("schema") != expected_schema:
        raise ProvenanceError("evidence object schema mismatch")
    digest = hashlib.sha256(data).hexdigest()
    return TrustedEvidence(payload=MappingProxyType(payload), sha256=digest, filename=filename)


def load_governance_evidence() -> TrustedEvidence:
    return _load_fixed(GOVERNANCE_FILENAME, GOVERNANCE_SCHEMA)


def load_hermes_origin_baseline_evidence() -> TrustedEvidence:
    return _load_fixed(HERMES_ORIGIN_BASELINE_FILENAME, HERMES_ORIGIN_BASELINE_SCHEMA)
