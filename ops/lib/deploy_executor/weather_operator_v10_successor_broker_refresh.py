from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from deploy_executor import weather_operator_v9_capability_broker_refresh as _base

MINIMUM_PREDECESSOR_ANCESTOR = "80261255b3be2aa7dd40986254d4ea478b4e2e1b"
REGISTRATION_SCHEMA = _base.REGISTRATION_SCHEMA
ARTIFACT_KEYS = _base.ARTIFACT_KEYS
UNCHANGED_ARTIFACT_KEYS = _base.UNCHANGED_ARTIFACT_KEYS
SHA40_RE = _base.SHA40_RE
SHA256_RE = _base.SHA256_RE
REGISTRATION_FIELDS = _base.REGISTRATION_FIELDS
validate_registration = _base.validate_registration
registration_bytes = _base.registration_bytes
sha256 = _base.sha256
MUTATION_BUDGET = (
    ("filesystem.weather-operator-v10-successor-broker-refresh-stage", 2),
    ("filesystem.weather-operator-v10-successor-broker-refresh-atomic-replace", 2),
)


class WeatherV10SuccessorBrokerRefreshError(RuntimeError):
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
    raise WeatherV10SuccessorBrokerRefreshError(message)


def _require_hashes(value: Mapping[str, Any], where: str) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(ARTIFACT_KEYS):
        _fail(f"{where} artifact identity set drifted")
    result: dict[str, str] = {}
    for key in ARTIFACT_KEYS:
        digest = value.get(key)
        if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
            _fail(f"{where} {key} is invalid")
        result[key] = digest
    return result


def build_refresh_plan(
    *,
    source_sha: str,
    predecessor_source_sha: str,
    registration: Mapping[str, Any],
    predecessor_hashes: Mapping[str, Any],
    installed_hashes: Mapping[str, Any],
    target_hashes: Mapping[str, Any],
    state_db_present: bool,
    temp_paths_absent: bool,
) -> RefreshPlan:
    if type(source_sha) is not str or SHA40_RE.fullmatch(source_sha) is None:
        _fail("target source SHA is invalid")
    if type(predecessor_source_sha) is not str or SHA40_RE.fullmatch(predecessor_source_sha) is None:
        _fail("predecessor source SHA is invalid")
    if source_sha == predecessor_source_sha:
        _fail("target source must differ from the installed predecessor source")
    current = validate_registration(registration)
    if current["capability_source_sha"] != predecessor_source_sha:
        _fail("registration predecessor source binding drifted")

    predecessor = _require_hashes(predecessor_hashes, "predecessor")
    installed = _require_hashes(installed_hashes, "installed")
    target = _require_hashes(target_hashes, "target")
    for key in ARTIFACT_KEYS:
        if current[key] != predecessor[key]:
            _fail(f"registration predecessor identity drifted: {key}")
        if installed[key] != predecessor[key]:
            _fail(f"installed predecessor identity drifted: {key}")
    for key in UNCHANGED_ARTIFACT_KEYS:
        if target[key] != predecessor[key]:
            _fail(f"successor refresh would widen beyond broker + registration: {key}")
    if target["broker_sha256"] == predecessor["broker_sha256"]:
        _fail("successor privileged broker is unchanged")
    if not state_db_present:
        _fail("durable replay/state database is absent")
    if not temp_paths_absent:
        _fail("fixed successor broker-refresh staging path already exists")

    rebound = dict(current)
    rebound["capability_source_sha"] = source_sha
    for key in ARTIFACT_KEYS:
        rebound[key] = target[key]
    return RefreshPlan(
        source_sha=source_sha,
        predecessor_source_sha=predecessor_source_sha,
        new_registration=rebound,
        mutation_budget=MUTATION_BUDGET,
    )
