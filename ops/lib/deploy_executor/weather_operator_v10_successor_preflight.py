from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

REQUEST_SCHEMA = "rozkalns.rpi5-main.weather-operator-v10-successor-preflight.request.v1"
RECEIPT_SCHEMA = "rozkalns.rpi5-main.weather-operator-v10-successor-preflight.receipt.v1"
FAILURE_SCHEMA = "rozkalns.rpi5-main.weather-operator-v10-successor-preflight.failure.v1"
OPERATION = "preflight"
REQUEST_MAX_BYTES = 512
RECEIPT_MAX_BYTES = 4096
ROOT_UID = 0
ROOT_GID = 0
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v9-host-capability-registration.v1"
ARTIFACT_KEYS = ("module_sha256", "broker_sha256", "socket_sha256", "service_sha256")
REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "capability_source_sha",
        "manager_checkout",
        "manager_uid",
        "manager_gid",
        "artifact_count",
        *ARTIFACT_KEYS,
    }
)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REGISTRATION = Path("/etc/rozkalns-weather-operator-v9-capability/registration.json")
STATE_DB = Path("/var/lib/rozkalns-weather-operator-v9-capability/state.sqlite3")
SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-operator-v9-capability")
MODULE_TARGET = SUPPORT_ROOT / "deploy_executor/weather_operator_upgrade_v9_host_capability.py"
BROKER_TARGET = Path("/usr/local/libexec/rozkalns-weather-operator-v9-privileged-broker")
SOCKET_TARGET = Path("/etc/systemd/system/rozkalns-weather-operator-v9-privileged-broker.socket")
SERVICE_TARGET = Path("/etc/systemd/system/rozkalns-weather-operator-v9-privileged-broker@.service")
BROKER_TEMP = BROKER_TARGET.with_name(".rozkalns-weather-operator-v9-privileged-broker.broker-refresh.tmp")
REGISTRATION_TEMP = REGISTRATION.with_name(".registration.json.broker-refresh.tmp")

PASS_FIELDS = frozenset(
    {
        "schema",
        "result",
        "capability_source_sha",
        "artifact_count",
        "artifact_hashes",
        "durable_state_db_valid",
        "staging_paths_absent",
        "host_mutation_started",
        "systemd_mutation_started",
        "network_access_required",
        "automatic_retry",
        "automatic_cleanup",
        "automatic_rollback",
    }
)
FAILURE_FIELDS = frozenset(
    {
        "schema",
        "result",
        "host_mutation_started",
        "systemd_mutation_started",
        "network_access_required",
        "automatic_retry",
        "automatic_cleanup",
        "automatic_rollback",
    }
)


class WeatherV10SuccessorPreflightError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise WeatherV10SuccessorPreflightError(message)


def _lstat_optional(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WeatherV10SuccessorPreflightError("fixed runtime metadata cannot be read") from exc


def _safe_regular_bytes(path: Path, *, mode: int, max_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise WeatherV10SuccessorPreflightError("required fixed runtime artifact is unavailable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size < 1
        or before.st_size > max_bytes
    ):
        _fail("required fixed runtime artifact metadata drifted")
    try:
        data = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise WeatherV10SuccessorPreflightError("required fixed runtime artifact cannot be read") from exc
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
        _fail("required fixed runtime artifact changed while being read")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_registration(value: Any) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != REGISTRATION_FIELDS:
        _fail("installed registration fields drifted")
    if value.get("schema") != REGISTRATION_SCHEMA:
        _fail("installed registration schema drifted")
    source_sha = value.get("capability_source_sha")
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("installed registration source identity is invalid")
    manager = value.get("manager_checkout")
    if type(manager) is not str or not manager.startswith("/") or not manager.endswith("/RPi5_main"):
        _fail("installed registration manager identity drifted")
    for key in ("manager_uid", "manager_gid"):
        candidate = value.get(key)
        if type(candidate) is not int or candidate <= 0:
            _fail("installed registration manager identity drifted")
    if value.get("artifact_count") != 15:
        _fail("installed registration artifact count drifted")
    for key in ARTIFACT_KEYS:
        digest = value.get(key)
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            _fail("installed registration artifact identity is invalid")
    return dict(value)


def _load_registration() -> dict[str, Any]:
    raw = _safe_regular_bytes(REGISTRATION, mode=0o600, max_bytes=64 * 1024)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherV10SuccessorPreflightError("installed registration is malformed") from exc
    return _validate_registration(value)


def _installed_hashes() -> dict[str, str]:
    return {
        "module_sha256": _sha256(_safe_regular_bytes(MODULE_TARGET, mode=0o644, max_bytes=2 * 1024 * 1024)),
        "broker_sha256": _sha256(_safe_regular_bytes(BROKER_TARGET, mode=0o755, max_bytes=2 * 1024 * 1024)),
        "socket_sha256": _sha256(_safe_regular_bytes(SOCKET_TARGET, mode=0o644, max_bytes=256 * 1024)),
        "service_sha256": _sha256(_safe_regular_bytes(SERVICE_TARGET, mode=0o644, max_bytes=256 * 1024)),
    }


def _require_state_db() -> None:
    try:
        meta = STATE_DB.lstat()
    except OSError as exc:
        raise WeatherV10SuccessorPreflightError("durable replay state is unavailable") from exc
    if (
        not stat.S_ISREG(meta.st_mode)
        or stat.S_ISLNK(meta.st_mode)
        or meta.st_nlink != 1
        or meta.st_uid != ROOT_UID
        or meta.st_gid != ROOT_GID
        or stat.S_IMODE(meta.st_mode) != 0o600
    ):
        _fail("durable replay state metadata drifted")


def _require_staging_absent() -> None:
    if _lstat_optional(BROKER_TEMP) is not None or _lstat_optional(REGISTRATION_TEMP) is not None:
        _fail("successor broker refresh staging residue is present")


def _decode_request(raw: bytes) -> None:
    if not raw or len(raw) > REQUEST_MAX_BYTES:
        _fail("request size is invalid")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WeatherV10SuccessorPreflightError("request is malformed") from exc
    if type(value) is not dict or set(value) != {"schema", "operation"}:
        _fail("request fields drifted")
    if value.get("schema") != REQUEST_SCHEMA or value.get("operation") != OPERATION:
        _fail("request identity drifted")


def _failure_receipt() -> dict[str, object]:
    return {
        "schema": FAILURE_SCHEMA,
        "result": "FAIL_CLOSED",
        "host_mutation_started": False,
        "systemd_mutation_started": False,
        "network_access_required": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def execute_request(raw: bytes) -> dict[str, object]:
    _decode_request(raw)
    if os.geteuid() != ROOT_UID:
        _fail("root service identity is required")
    registration = _load_registration()
    installed = _installed_hashes()
    for key in ARTIFACT_KEYS:
        if installed[key] != registration[key]:
            _fail("installed artifact identity differs from root-owned registration")
    _require_state_db()
    _require_staging_absent()
    return {
        "schema": RECEIPT_SCHEMA,
        "result": "PASS",
        "capability_source_sha": registration["capability_source_sha"],
        "artifact_count": registration["artifact_count"],
        "artifact_hashes": installed,
        "durable_state_db_valid": True,
        "staging_paths_absent": True,
        "host_mutation_started": False,
        "systemd_mutation_started": False,
        "network_access_required": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("receipt is not an object")
    if value.get("result") == "FAIL_CLOSED":
        if frozenset(value) != FAILURE_FIELDS or value.get("schema") != FAILURE_SCHEMA:
            _fail("failure receipt fields drifted")
        for key in FAILURE_FIELDS - {"schema", "result"}:
            if value.get(key) is not False:
                _fail("failure receipt safety flag drifted")
        return dict(value)
    if frozenset(value) != PASS_FIELDS or value.get("schema") != RECEIPT_SCHEMA or value.get("result") != "PASS":
        _fail("success receipt fields drifted")
    source_sha = value.get("capability_source_sha")
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("success receipt source identity is invalid")
    if value.get("artifact_count") != 15:
        _fail("success receipt artifact count drifted")
    hashes = value.get("artifact_hashes")
    if type(hashes) is not dict or set(hashes) != set(ARTIFACT_KEYS):
        _fail("success receipt artifact fields drifted")
    for key in ARTIFACT_KEYS:
        digest = hashes.get(key)
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            _fail("success receipt artifact identity is invalid")
    if value.get("durable_state_db_valid") is not True or value.get("staging_paths_absent") is not True:
        _fail("success receipt durable-state flags drifted")
    for key in (
        "host_mutation_started",
        "systemd_mutation_started",
        "network_access_required",
        "automatic_retry",
        "automatic_cleanup",
        "automatic_rollback",
    ):
        if value.get(key) is not False:
            _fail("success receipt safety flag drifted")
    return dict(value)


def encode_receipt(value: Mapping[str, Any]) -> bytes:
    validated = validate_receipt(value)
    encoded = (json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > RECEIPT_MAX_BYTES:
        _fail("receipt exceeds fixed response bound")
    return encoded


def failure_receipt() -> dict[str, object]:
    return _failure_receipt()
