from __future__ import annotations

from typing import Any, Mapping

from deploy_executor import weather_operator_v9_capability_broker_refresh as _base

PREDECESSOR_SOURCE_SHA = "80261255b3be2aa7dd40986254d4ea478b4e2e1b"
REGISTRATION_SCHEMA = _base.REGISTRATION_SCHEMA
ARTIFACT_KEYS = _base.ARTIFACT_KEYS
UNCHANGED_ARTIFACT_KEYS = _base.UNCHANGED_ARTIFACT_KEYS
MUTATION_BUDGET = (
    ("filesystem.weather-operator-v9-capability-broker-refresh-post83-stage", 2),
    ("filesystem.weather-operator-v9-capability-broker-refresh-post83-atomic-replace", 2),
)
SHA40_RE = _base.SHA40_RE
SHA256_RE = _base.SHA256_RE
REGISTRATION_FIELDS = _base.REGISTRATION_FIELDS
WeatherV9CapabilityBrokerRefreshError = _base.WeatherV9CapabilityBrokerRefreshError
RefreshPlan = _base.RefreshPlan
validate_registration = _base.validate_registration
registration_bytes = _base.registration_bytes
sha256 = _base.sha256


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
        _fail("target source must be newer than the post-#83 predecessor binding")
    current = validate_registration(registration)
    if current["capability_source_sha"] != PREDECESSOR_SOURCE_SHA:
        _fail("installed registration is not bound to the expected post-#83 predecessor source")

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
        _fail("target privileged broker is unchanged from the post-#83 predecessor")
    if not state_db_present:
        _fail("durable replay/state database is absent")
    if not temp_paths_absent:
        _fail("fixed post-#83 broker-refresh staging path already exists")

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
