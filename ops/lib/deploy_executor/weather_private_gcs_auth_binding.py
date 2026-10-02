from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping, Protocol

from .weather_private_application_staging import _rename_noreplace
from .weather_private_gcs_host_bindings import (
    AUTH_READY_MARKER,
    BINDING_ROOT,
    CREDENTIAL_ROOT,
    GCS_AUTH_PROVIDER_CLASS,
    GCS_AUTH_READY_SCHEMA,
    GCS_PRIVATE_BINDING_SCHEMA,
    PRIVATE_VALUES,
)
from .weather_private_gcs_trusted_backend import GOOGLE_AUTH_SLOT_ID

IMPLEMENTATION_ISSUE = 843
OPERATION_ID = "rpi5.weathernext-private-gcs-auth-binding.v1"
TARGET_ALIAS = "rpi5-weathernext-private-gcs-auth-binding"
ROLLBACK_POLICY = "NONE"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-gcs-auth-binding.fixed-state-v1"
ADAPTER_ID = "rpi5.weathernext-private-gcs-auth-binding.fixed-v1"

SOURCE_BINDING_ROOT = Path("/var/lib/rpi5-deploy/weather-private-bindings")
SOURCE_PRIVATE_VALUES = SOURCE_BINDING_ROOT / "first-access-private.json"
SOURCE_CREDENTIAL_ROOT = SOURCE_BINDING_ROOT / "credentials"
SOURCE_PRIVATE_SCHEMA = "rozkalns-weather.weathernext-private-first-access-binding.v1"

PARTIAL_ROOT = BINDING_ROOT.parent / ".weather-private-gcs-bindings.partial"
ROOT_UID = 0
ROOT_GID = 0
ROOT_MODE = 0o700
PRIVATE_MODE = 0o600
READY_MODE = 0o644
MAX_PRIVATE_BYTES = 16 * 1024
MAX_CREDENTIAL_BYTES = 64 * 1024
MUTATION_BUDGET = (
    ("filesystem.weathernext-private-gcs-auth-binding-partial-root-create", 1),
    ("filesystem.weathernext-private-gcs-auth-credential-copy", 1),
    ("filesystem.weathernext-private-gcs-auth-private-binding-write", 1),
    ("filesystem.weathernext-private-gcs-auth-ready-marker-write", 1),
    ("filesystem.weathernext-private-gcs-auth-binding-publish", 1),
)
REQUIRED_EXCLUSIONS = (
    "no caller-selected credential path basename project dataset account or scope",
    "no ambient ADC or Google API request",
    "no IAM quota project dataset Analytics Hub or billing-project mutation",
    "no application or runtime mutation",
    "no BigQuery access",
    "no SQLite corpus Docker systemd network or Cloudflare mutation",
    "no automatic retry cleanup rollback or credential substitution",
)


class WeatherNextPrivateGCSAuthBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class GCSAuthBindingObservation:
    state: str


@dataclass(frozen=True)
class CanonicalGCSAuthBindingEvidence:
    authorization_issue_number: int
    request_id: str
    operation_id: str
    target_alias: str
    rpi5_main_sha: str
    queue_issue_number: int
    queue_ready: bool = True
    owner_verified: bool = True
    app_authored: bool = False
    authorization_ttl_valid: bool = True
    authorization_body_unchanged: bool = True
    authorization_replay_available: bool = True
    source_exact_main: bool = True
    source_merged_reachable: bool = True
    source_ci_success: bool = True
    rollback_policy: str = ROLLBACK_POLICY


@dataclass(frozen=True)
class GCSAuthBindingReceipt:
    schema: str
    authorization_issue_number: int
    request_id: str
    operation_id: str
    target_alias: str
    authorization_consumed: bool
    auth_binding_state: str
    mutations_executed: tuple[str, ...]
    protected_source_read: bool
    credential_content_emitted: bool = False
    credential_path_emitted: bool = False
    project_dataset_emitted: bool = False
    google_request_performed: bool = False
    production_mutation_started: bool = True


class ReplayAuthority(Protocol):
    def consume(self, request_id: str) -> Any: ...


def _fail(message: str) -> None:
    raise WeatherNextPrivateGCSAuthBindingError(message)


def _meta(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        _fail("GCS auth binding metadata read failed")


def _require_dir(path: Path, *, mode: int = ROOT_MODE) -> os.stat_result:
    st = _meta(path)
    if (
        st is None
        or not stat.S_ISDIR(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_uid != ROOT_UID
        or st.st_gid != ROOT_GID
        or stat.S_IMODE(st.st_mode) != mode
    ):
        _fail("GCS auth binding directory identity drifted")
    return st


def _read_regular(path: Path, *, mode: int, max_bytes: int) -> bytes:
    st = _meta(path)
    if (
        st is None
        or not stat.S_ISREG(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_nlink != 1
        or st.st_uid != ROOT_UID
        or st.st_gid != ROOT_GID
        or stat.S_IMODE(st.st_mode) != mode
        or st.st_size <= 0
        or st.st_size > max_bytes
    ):
        _fail("GCS auth binding protected file identity drifted")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        _fail("GCS auth binding protected file open failed")
    try:
        opened = os.fstat(fd)
        if (
            (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino)
            or opened.st_size != st.st_size
        ):
            _fail("GCS auth binding protected file changed before read")
        raw = b""
        while len(raw) <= max_bytes:
            block = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
            if not block:
                break
            raw += block
    finally:
        os.close(fd)
    if len(raw) != st.st_size or len(raw) > max_bytes:
        _fail("GCS auth binding protected file changed during read")
    return raw


def _read_json(path: Path, *, mode: int, max_bytes: int) -> Mapping[str, Any]:
    try:
        value = json.loads(_read_regular(path, mode=mode, max_bytes=max_bytes).decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        _fail("GCS auth binding protected JSON malformed")
    if type(value) is not dict:
        _fail("GCS auth binding protected JSON must be object")
    return value


def _write_exact(path: Path, raw: bytes, *, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        _fail("GCS auth binding no-overwrite write failed")
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0:
                _fail("GCS auth binding write failed closed")
            offset += written
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        _fail("GCS auth binding directory fsync open failed")
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ready_marker_exact() -> bool:
    try:
        value = _read_json(AUTH_READY_MARKER, mode=READY_MODE, max_bytes=MAX_PRIVATE_BYTES)
    except WeatherNextPrivateGCSAuthBindingError:
        return False
    return value == {
        "schema": GCS_AUTH_READY_SCHEMA,
        "slot_id": GOOGLE_AUTH_SLOT_ID,
        "provider_class": GCS_AUTH_PROVIDER_CLASS,
        "ready": True,
    }


def observe_target() -> GCSAuthBindingObservation:
    root = _meta(BINDING_ROOT)
    partial = _meta(PARTIAL_ROOT)
    if partial is not None:
        return GCSAuthBindingObservation("CONFLICT")
    if root is None:
        return GCSAuthBindingObservation("ABSENT")
    if not _ready_marker_exact():
        return GCSAuthBindingObservation("CONFLICT")
    return GCSAuthBindingObservation("READY")


def _source_credential_after_consume() -> tuple[str, bytes]:
    _require_dir(SOURCE_BINDING_ROOT)
    _require_dir(SOURCE_CREDENTIAL_ROOT)
    value = _read_json(SOURCE_PRIVATE_VALUES, mode=PRIVATE_MODE, max_bytes=MAX_PRIVATE_BYTES)
    if (
        set(value) != {"schema", "project", "dataset", "credential_file"}
        or value.get("schema") != SOURCE_PRIVATE_SCHEMA
    ):
        _fail("source WeatherNext private binding schema drifted")
    basename = value.get("credential_file")
    if (
        type(basename) is not str
        or not 1 <= len(basename) <= 128
        or basename in {".", ".."}
        or "/" in basename
        or "\\" in basename
        or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in basename)
    ):
        _fail("source WeatherNext credential basename invalid")
    credential = _read_regular(
        SOURCE_CREDENTIAL_ROOT / basename,
        mode=PRIVATE_MODE,
        max_bytes=MAX_CREDENTIAL_BYTES,
    )
    return basename, credential


def _verify_published(basename: str, source_credential: bytes) -> None:
    _require_dir(BINDING_ROOT)
    _require_dir(CREDENTIAL_ROOT)
    private = _read_json(PRIVATE_VALUES, mode=PRIVATE_MODE, max_bytes=MAX_PRIVATE_BYTES)
    if private != {"schema": GCS_PRIVATE_BINDING_SCHEMA, "credential_file": basename}:
        _fail("published GCS private binding drifted")
    ready = _read_json(AUTH_READY_MARKER, mode=READY_MODE, max_bytes=MAX_PRIVATE_BYTES)
    if ready != {
        "schema": GCS_AUTH_READY_SCHEMA,
        "slot_id": GOOGLE_AUTH_SLOT_ID,
        "provider_class": GCS_AUTH_PROVIDER_CLASS,
        "ready": True,
    }:
        _fail("published GCS auth ready marker drifted")
    copied = _read_regular(CREDENTIAL_ROOT / basename, mode=PRIVATE_MODE, max_bytes=MAX_CREDENTIAL_BYTES)
    if not hashlib.sha256(copied).digest() == hashlib.sha256(source_credential).digest():
        _fail("published GCS credential copy drifted")


def _validate_evidence(evidence: CanonicalGCSAuthBindingEvidence) -> None:
    if type(evidence) is not CanonicalGCSAuthBindingEvidence:
        raise TypeError("GCS auth binding requires canonical evidence")
    if evidence.operation_id != OPERATION_ID or evidence.target_alias != TARGET_ALIAS:
        _fail("GCS auth binding operation identity drifted")
    if (
        type(evidence.rpi5_main_sha) is not str
        or len(evidence.rpi5_main_sha) != 40
        or any(ch not in "0123456789abcdef" for ch in evidence.rpi5_main_sha)
    ):
        _fail("GCS auth binding source SHA invalid")
    if evidence.rollback_policy != ROLLBACK_POLICY:
        _fail("GCS auth binding rollback policy drifted")
    for field in (
        "queue_ready",
        "owner_verified",
        "authorization_ttl_valid",
        "authorization_body_unchanged",
        "authorization_replay_available",
        "source_exact_main",
        "source_merged_reachable",
        "source_ci_success",
    ):
        if getattr(evidence, field) is not True:
            _fail(f"GCS auth binding canonical proof failed: {field}")
    if evidence.app_authored is not False:
        _fail("app-authored GCS auth binding LIVE-AUTH is forbidden")


def apply_auth_binding(
    evidence: CanonicalGCSAuthBindingEvidence,
    *,
    replay: ReplayAuthority,
) -> GCSAuthBindingReceipt:
    _validate_evidence(evidence)
    observed = observe_target()
    if observed.state == "CONFLICT":
        _fail("GCS auth binding target or partial state conflicts with reviewed state")
    if observed.state == "READY":
        return GCSAuthBindingReceipt(
            schema="rozkalns-weather.weathernext-private-gcs-auth-binding-receipt.v1",
            authorization_issue_number=evidence.authorization_issue_number,
            request_id=evidence.request_id,
            operation_id=OPERATION_ID,
            target_alias=TARGET_ALIAS,
            authorization_consumed=False,
            auth_binding_state="ready",
            mutations_executed=(),
            protected_source_read=False,
            production_mutation_started=False,
        )

    replay.consume(evidence.request_id)
    basename, credential = _source_credential_after_consume()

    if _meta(BINDING_ROOT) is not None or _meta(PARTIAL_ROOT) is not None:
        _fail("GCS auth binding target changed after authorization consume")
    _require_dir(BINDING_ROOT.parent, mode=0o755)
    try:
        os.mkdir(PARTIAL_ROOT, ROOT_MODE)
        os.chown(PARTIAL_ROOT, ROOT_UID, ROOT_GID)
    except OSError:
        _fail("GCS auth binding partial root create failed")
    executed = [MUTATION_BUDGET[0][0]]

    cred_root = PARTIAL_ROOT / CREDENTIAL_ROOT.name
    try:
        os.mkdir(cred_root, ROOT_MODE)
        os.chown(cred_root, ROOT_UID, ROOT_GID)
    except OSError:
        _fail("GCS auth binding credential root create failed")
    _write_exact(cred_root / basename, credential, mode=PRIVATE_MODE)
    executed.append(MUTATION_BUDGET[1][0])

    private_raw = (
        json.dumps(
            {"schema": GCS_PRIVATE_BINDING_SCHEMA, "credential_file": basename},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    _write_exact(PARTIAL_ROOT / PRIVATE_VALUES.name, private_raw, mode=PRIVATE_MODE)
    executed.append(MUTATION_BUDGET[2][0])

    ready_raw = (
        json.dumps(
            {
                "schema": GCS_AUTH_READY_SCHEMA,
                "slot_id": GOOGLE_AUTH_SLOT_ID,
                "provider_class": GCS_AUTH_PROVIDER_CLASS,
                "ready": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    _write_exact(PARTIAL_ROOT / AUTH_READY_MARKER.name, ready_raw, mode=READY_MODE)
    executed.append(MUTATION_BUDGET[3][0])
    _fsync_dir(cred_root)
    _fsync_dir(PARTIAL_ROOT)
    _rename_noreplace(PARTIAL_ROOT, BINDING_ROOT)
    _fsync_dir(BINDING_ROOT.parent)
    executed.append(MUTATION_BUDGET[4][0])

    _verify_published(basename, credential)
    return GCSAuthBindingReceipt(
        schema="rozkalns-weather.weathernext-private-gcs-auth-binding-receipt.v1",
        authorization_issue_number=evidence.authorization_issue_number,
        request_id=evidence.request_id,
        operation_id=OPERATION_ID,
        target_alias=TARGET_ALIAS,
        authorization_consumed=True,
        auth_binding_state="ready",
        mutations_executed=tuple(executed),
        protected_source_read=True,
    )


def public_receipt(receipt: GCSAuthBindingReceipt) -> Mapping[str, Any]:
    if type(receipt) is not GCSAuthBindingReceipt:
        _fail("GCS auth binding receipt type invalid")
    return asdict(receipt)


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "baseline_resolver_id": BASELINE_RESOLVER_ID,
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "source_binding_root": str(SOURCE_BINDING_ROOT),
        "target_binding_root": str(BINDING_ROOT),
        "protected_source_read_before_consume": False,
        "credential_path_caller_controlled": False,
        "project_dataset_caller_controlled": False,
        "ambient_adc_allowed": False,
        "google_request_allowed": False,
        "bigquery_action_allowed": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
