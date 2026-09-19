from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

PREDECESSOR_SOURCE_SHA = "dd0230aa1387a553db81bf59a02e4358f6432a1f"
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v9-host-capability-registration.v1"
ARTIFACT_KEYS = ("module_sha256", "broker_sha256", "socket_sha256", "service_sha256")
UNCHANGED_ARTIFACT_KEYS = ("module_sha256", "socket_sha256", "service_sha256")
MUTATION_BUDGET = (
    ("filesystem.weather-operator-v9-capability-broker-refresh-stage", 2),
    ("filesystem.weather-operator-v9-capability-broker-refresh-atomic-replace", 2),
)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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


class WeatherV9CapabilityBrokerRefreshError(RuntimeError):
    pass


@dataclass(frozen=True)
class RefreshPlan:
    source_sha: str
    predecessor_source_sha: str
    new_registration: Mapping[str, Any]
    mutation_budget: tuple[tuple[str, int], ...]
    state_db_policy: str = "PRESERVE_EXISTING_UNCHANGED"
    systemd_mutation: bool = False
    queue_or_live_auth_created: bool = False


def _fail(message: str) -> None:
    raise WeatherV9CapabilityBrokerRefreshError(message)


def _require_sha256_map(value: Mapping[str, Any], where: str) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(ARTIFACT_KEYS):
        _fail(f"{where} artifact identity set drifted")
    result: dict[str, str] = {}
    for key in ARTIFACT_KEYS:
        digest = value.get(key)
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            _fail(f"{where} {key} is invalid")
        result[key] = digest
    return result


def validate_registration(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or frozenset(value) != REGISTRATION_FIELDS:
        _fail("registration fields drifted")
    if value.get("schema") != REGISTRATION_SCHEMA:
        _fail("registration schema drifted")
    source_sha = value.get("capability_source_sha")
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("registration source SHA is invalid")
    manager = value.get("manager_checkout")
    if type(manager) is not str or not manager.startswith("/") or not manager.endswith("/RPi5_main"):
        _fail("registration manager checkout drifted")
    for key in ("manager_uid", "manager_gid"):
        candidate = value.get(key)
        if type(candidate) is not int or candidate <= 0:
            _fail(f"registration {key} drifted")
    if value.get("artifact_count") != 15:
        _fail("registration artifact count drifted")
    _require_sha256_map({key: value[key] for key in ARTIFACT_KEYS}, "registration")
    return dict(value)


def build_refresh_plan(
    *,
    source_sha: str,
    registration: Mapping[str, Any],
    predecessor_hashes: Mapping[str, Any],
    installed_hashes: Mapping[str, Any],
    target_hashes: Mapping[str, Any],
    state_db_present: bool,
    temp_paths_absent: bool,
) -> RefreshPlan:
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("target source SHA is invalid")
    if source_sha == PREDECESSOR_SOURCE_SHA:
        _fail("target source must be newer than the predecessor binding")
    current = validate_registration(registration)
    if current["capability_source_sha"] != PREDECESSOR_SOURCE_SHA:
        _fail("installed registration is not bound to the expected predecessor source")

    predecessor = _require_sha256_map(predecessor_hashes, "predecessor")
    installed = _require_sha256_map(installed_hashes, "installed")
    target = _require_sha256_map(target_hashes, "target")

    for key in ARTIFACT_KEYS:
        if current[key] != predecessor[key]:
            _fail(f"registration predecessor identity drifted: {key}")
        if installed[key] != predecessor[key]:
            _fail(f"installed predecessor identity drifted: {key}")
    for key in UNCHANGED_ARTIFACT_KEYS:
        if target[key] != predecessor[key]:
            _fail(f"broker refresh would widen beyond broker + registration: {key}")
    if target["broker_sha256"] == predecessor["broker_sha256"]:
        _fail("target privileged broker is unchanged from the spent-#76 predecessor")
    if not state_db_present:
        _fail("durable replay/state database is absent")
    if not temp_paths_absent:
        _fail("fixed broker-refresh staging path already exists")

    new_registration = dict(current)
    new_registration["capability_source_sha"] = source_sha
    for key in ARTIFACT_KEYS:
        new_registration[key] = target[key]

    return RefreshPlan(
        source_sha=source_sha,
        predecessor_source_sha=PREDECESSOR_SOURCE_SHA,
        new_registration=new_registration,
        mutation_budget=MUTATION_BUDGET,
    )


def registration_bytes(value: Mapping[str, Any]) -> bytes:
    validated = validate_registration(value)
    return json.dumps(validated, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
