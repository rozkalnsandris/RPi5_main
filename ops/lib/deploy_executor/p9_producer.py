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
from typing import Any, Iterable

from .hermes_deals_origin_adapter import (
    DISPATCHER_SOURCE_BLOB,
    INSTALLER_SOURCE_BLOB,
    PROBE_SOURCE_BLOB,
    SOURCE_REPOSITORY as HERMES_SOURCE_REPOSITORY,
    TARGET_ALIAS as HERMES_TARGET_ALIAS,
)
from .p9_evidence import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    GOVERNANCE_KEYS,
    GOVERNANCE_SCHEMA,
    HERMES_BASELINE_KEYS,
    HERMES_BASELINE_RESOLVER,
    HERMES_BASELINE_SCHEMA,
)
from .p9_provenance import (
    EVIDENCE_ROOT,
    GOVERNANCE_FILENAME,
    HERMES_ORIGIN_BASELINE_FILENAME,
    MAX_EVIDENCE_BYTES,
    SERVICE_GROUP,
)


class P9ProducerError(RuntimeError):
    pass


SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HERMES_WORKFLOW_SOURCE_BLOB = "99a18c5f669e7880a8a8288c3f964285df87ae22"

# Deliberately unset in this source gate. A later reviewed complete writer-surface
# audit must establish and source-pin the approved digest. Until then, governance
# evidence production fails closed and P9 cannot emit DRY_RUN_READY.
APPROVED_GOVERNANCE_WRITER_SET_SHA256: str | None = None

_ROOT_UID = 0
_DIRECTORY_MODE = 0o750
_FILE_MODE = 0o440
_REQUIRED_GOVERNANCE_SURFACES = frozenset(
    {
        "human-collaborators",
        "teams",
        "installed-apps-integrations",
        "workflow-github-token-permissions",
        "explicit-issues-write-or-write-all",
        "token-secret-issue-mutation-paths",
    }
)


@dataclass(frozen=True)
class GovernanceWriterSurfaceObservation:
    repository: str
    repository_id: int
    observed_at: datetime
    covered_surfaces: frozenset[str]
    human_writers: tuple[str, ...] = ()
    team_writers: tuple[str, ...] = ()
    app_writers: tuple[str, ...] = ()
    workflow_writers: tuple[str, ...] = ()
    token_writers: tuple[str, ...] = ()
    unknown_writers: tuple[str, ...] = ()


@dataclass(frozen=True)
class HermesOriginObservation:
    observed_at: datetime
    resolver_id: str
    target_alias: str
    source_repository: str
    registered_commit_sha: str
    observed_source_commit_sha: str
    registration_source_repository: str
    installer_source_blob: str
    probe_source_blob: str
    dispatcher_source_blob: str
    workflow_source_blob: str
    observed_mutation_classes: tuple[str, ...]


def _canonical_time(value: datetime, *, where: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise P9ProducerError(f"{where} must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_strings(values: Iterable[str], *, where: str) -> list[str]:
    result: list[str] = []
    for value in values:
        if type(value) is not str or not value or value.strip() != value:
            raise P9ProducerError(f"{where} contains an invalid identity")
        result.append(value)
    if len(set(result)) != len(result):
        raise P9ProducerError(f"{where} contains duplicate identities")
    return sorted(result)


def governance_writer_set_sha256(observation: GovernanceWriterSurfaceObservation) -> str:
    if observation.repository != AUTHORIZATION_REPOSITORY:
        raise P9ProducerError("governance observation repository mismatch")
    if observation.repository_id != AUTHORIZATION_REPOSITORY_ID:
        raise P9ProducerError("governance observation repository identity mismatch")
    if observation.covered_surfaces != _REQUIRED_GOVERNANCE_SURFACES:
        raise P9ProducerError("governance observation does not cover the complete writer surface")
    if observation.unknown_writers:
        raise P9ProducerError("governance observation contains unknown writers")

    canonical = {
        "repository": observation.repository,
        "repository_id": observation.repository_id,
        "human_writers": _canonical_strings(observation.human_writers, where="human_writers"),
        "team_writers": _canonical_strings(observation.team_writers, where="team_writers"),
        "app_writers": _canonical_strings(observation.app_writers, where="app_writers"),
        "workflow_writers": _canonical_strings(observation.workflow_writers, where="workflow_writers"),
        "token_writers": _canonical_strings(observation.token_writers, where="token_writers"),
    }
    raw = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_governance_evidence(
    observation: GovernanceWriterSurfaceObservation,
) -> dict[str, Any]:
    observed_at = _canonical_time(observation.observed_at, where="governance observed_at")
    digest = governance_writer_set_sha256(observation)

    approved = APPROVED_GOVERNANCE_WRITER_SET_SHA256
    if approved is None:
        raise P9ProducerError("approved governance writer-set digest is not source-pinned")
    if SHA256_RE.fullmatch(approved) is None:
        raise P9ProducerError("approved governance writer-set digest is malformed")
    if digest != approved:
        raise P9ProducerError(
            "governance writer set does not match the source-approved trust root"
        )

    return {
        "schema": GOVERNANCE_SCHEMA,
        "repository": AUTHORIZATION_REPOSITORY,
        "repository_id": AUTHORIZATION_REPOSITORY_ID,
        "observed_at": observed_at,
        "writer_set_sha256": digest,
        "trusted": True,
    }


def build_hermes_origin_baseline_evidence(
    observation: HermesOriginObservation,
) -> dict[str, Any]:
    observed_at = _canonical_time(
        observation.observed_at, where="Hermes baseline observed_at"
    )
    if SHA40_RE.fullmatch(observation.registered_commit_sha) is None:
        raise P9ProducerError("registered Hermes source SHA is malformed")
    if SHA40_RE.fullmatch(observation.observed_source_commit_sha) is None:
        raise P9ProducerError("observed Hermes source SHA is malformed")

    registration_identity_ok = (
        observation.resolver_id == HERMES_BASELINE_RESOLVER
        and observation.target_alias == HERMES_TARGET_ALIAS
        and observation.source_repository == HERMES_SOURCE_REPOSITORY
        and observation.installer_source_blob == INSTALLER_SOURCE_BLOB
    )
    registered_source_match = (
        observation.registration_source_repository == HERMES_SOURCE_REPOSITORY
        and observation.source_repository == HERMES_SOURCE_REPOSITORY
        and observation.registered_commit_sha == observation.observed_source_commit_sha
    )
    probe_identity_ok = observation.probe_source_blob == PROBE_SOURCE_BLOB
    dispatcher_identity_ok = observation.dispatcher_source_blob == DISPATCHER_SOURCE_BLOB
    workflow_identity_ok = observation.workflow_source_blob == HERMES_WORKFLOW_SOURCE_BLOB
    mutation_surface_read_only = observation.observed_mutation_classes == ()

    checks = {
        "registration_identity_ok": registration_identity_ok,
        "registered_source_match": registered_source_match,
        "probe_identity_ok": probe_identity_ok,
        "dispatcher_identity_ok": dispatcher_identity_ok,
        "workflow_identity_ok": workflow_identity_ok,
        "mutation_surface_read_only": mutation_surface_read_only,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise P9ProducerError(
            f"Hermes origin observation failed reviewed identity checks: {failed}"
        )

    return {
        "schema": HERMES_BASELINE_SCHEMA,
        "resolver_id": HERMES_BASELINE_RESOLVER,
        "target_alias": HERMES_TARGET_ALIAS,
        "source_repository": HERMES_SOURCE_REPOSITORY,
        "registered_commit_sha": observation.registered_commit_sha,
        "observed_at": observed_at,
        **{name: True for name in checks},
    }


def _service_gid() -> int:
    try:
        entry = grp.getgrnam(SERVICE_GROUP)
    except KeyError as exc:
        raise P9ProducerError("executor service group is missing") from exc
    if type(entry.gr_gid) is not int or entry.gr_gid < 0:
        raise P9ProducerError("executor service group id is invalid")
    return entry.gr_gid


def _require_platform_guards() -> None:
    for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC"):
        if type(getattr(os, name, None)) is not int:
            raise P9ProducerError("required atomic publisher guards are unavailable")
    if os.open not in getattr(os, "supports_dir_fd", set()):
        raise P9ProducerError("required dir_fd open guard is unavailable")
    if os.rename not in getattr(os, "supports_dir_fd", set()):
        raise P9ProducerError("required dir_fd atomic rename guard is unavailable")


def _require_root() -> None:
    if os.geteuid() != _ROOT_UID:
        raise P9ProducerError("trusted evidence publisher requires root")


def _require_root_directory(info: os.stat_result, *, gid: int) -> None:
    if not stat.S_ISDIR(info.st_mode):
        raise P9ProducerError("evidence root is not a directory")
    if info.st_uid != _ROOT_UID or info.st_gid != gid:
        raise P9ProducerError("evidence root ownership mismatch")
    if stat.S_IMODE(info.st_mode) != _DIRECTORY_MODE:
        raise P9ProducerError("evidence root mode mismatch")


def _canonical_payload_bytes(
    payload: dict[str, Any], *, expected_keys: frozenset[str], expected_schema: str
) -> bytes:
    if type(payload) is not dict or frozenset(payload) != expected_keys:
        raise P9ProducerError("producer payload keys do not match the frozen evidence schema")
    if payload.get("schema") != expected_schema:
        raise P9ProducerError("producer payload schema mismatch")
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise P9ProducerError("producer payload size is outside allowed bounds")
    return raw


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise P9ProducerError("evidence publisher made no forward progress")
        offset += written


def _publish_fixed(
    *,
    filename: str,
    payload: dict[str, Any],
    expected_keys: frozenset[str],
    expected_schema: str,
) -> str:
    if filename not in {GOVERNANCE_FILENAME, HERMES_ORIGIN_BASELINE_FILENAME}:
        raise P9ProducerError("evidence filename is not allowlisted")
    _require_platform_guards()
    _require_root()
    gid = _service_gid()
    data = _canonical_payload_bytes(
        payload, expected_keys=expected_keys, expected_schema=expected_schema
    )

    root_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_fd = os.open(EVIDENCE_ROOT, root_flags)
    except OSError as exc:
        raise P9ProducerError("evidence root is unavailable") from exc

    temp_name = f".{filename}.tmp.{os.getpid()}.{secrets.token_hex(8)}"
    try:
        _require_root_directory(os.fstat(root_fd), gid=gid)
        temp_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            temp_fd = os.open(temp_name, temp_flags, _FILE_MODE, dir_fd=root_fd)
        except OSError as exc:
            raise P9ProducerError("cannot create evidence temporary file") from exc
        try:
            os.fchown(temp_fd, _ROOT_UID, gid)
            os.fchmod(temp_fd, _FILE_MODE)
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)

        # On Linux/POSIX rename within the same directory is the atomic replacement.
        # A failure is intentionally not cleaned up automatically; later mutation
        # handling must preserve evidence and STOP rather than retry/cleanup.
        try:
            os.rename(temp_name, filename, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        except OSError as exc:
            raise P9ProducerError("atomic evidence replacement failed") from exc
        os.fsync(root_fd)
    finally:
        os.close(root_fd)

    return hashlib.sha256(data).hexdigest()


def publish_governance_evidence(
    observation: GovernanceWriterSurfaceObservation,
) -> str:
    return _publish_fixed(
        filename=GOVERNANCE_FILENAME,
        payload=build_governance_evidence(observation),
        expected_keys=GOVERNANCE_KEYS,
        expected_schema=GOVERNANCE_SCHEMA,
    )


def publish_hermes_origin_baseline_evidence(
    observation: HermesOriginObservation,
) -> str:
    return _publish_fixed(
        filename=HERMES_ORIGIN_BASELINE_FILENAME,
        payload=build_hermes_origin_baseline_evidence(observation),
        expected_keys=HERMES_BASELINE_KEYS,
        expected_schema=HERMES_BASELINE_SCHEMA,
    )
