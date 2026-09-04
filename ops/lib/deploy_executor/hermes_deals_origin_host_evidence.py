from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from .hermes_deals_origin_adapter import (
    DISPATCHER_SOURCE_BLOB,
    OPERATION_ID,
    PROBE_SOURCE_BLOB,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_SOURCE_BLOB,
    WORKFLOW_SOURCE_BLOB,
)
from .hermes_deals_origin_privileged_broker import (
    BROKER_INSTALL_PATH,
    BROKER_SERVICE_UNIT,
    BROKER_SOCKET_PATH,
    BROKER_SOCKET_UNIT,
)
from .hermes_deals_origin_privileged_consumer import HOST_EVIDENCE_SCHEMA
from .hermes_deals_origin_privileged_dispatcher import INSTALLED_HELPER_PATH
from .hermes_deals_origin_source_auth import (
    SOURCE_CREDENTIAL_GROUP,
    SOURCE_CREDENTIAL_MODE,
    SOURCE_CREDENTIAL_OWNER,
    SOURCE_CREDENTIAL_PATH,
)

HOST_OBSERVATION_SCHEMA = "rozkalns.hermes-deals.origin-host-observation.v1"
HOST_OBSERVATION_MAX_BYTES = 8192
HOST_OBSERVATION_MAX_AGE_SECONDS = 300
REGISTRATION_PATH = "/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json"
REGISTRATION_NAME = "origin-path-audit"
PROBE_PATH = "/usr/local/libexec/hermes-deals-audits/origin-path-probe.py"
ROOT_OWNER = "root"
ROOT_GROUP = "root"
REGISTRATION_MODE = "0600"
BROKER_MODE = "0755"
PULL_HELPER_MODE = "0755"
EVIDENCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_|-----BEGIN|password|secret|private[_-]?key|token)",
    re.IGNORECASE,
)

_OBSERVATION_FIELDS = frozenset(
    {
        "schema",
        "evidence_id",
        "observed_at",
        "operation_id",
        "registered_source_sha",
        "registration_path",
        "registration_name",
        "registration_owner",
        "registration_group",
        "registration_mode",
        "broker_install_path",
        "broker_owner",
        "broker_group",
        "broker_mode",
        "socket_path",
        "socket_unit",
        "service_unit",
        "source_credential_path",
        "source_credential_owner",
        "source_credential_group",
        "source_credential_mode",
        "pull_helper_path",
        "pull_helper_owner",
        "pull_helper_group",
        "pull_helper_mode",
        "pull_helper_source_blob",
        "pull_helper_argument_names",
        "probe_path",
        "probe_source_blob",
        "dispatcher_source_blob",
        "workflow_source_blob",
        "evidence_read_only",
        "credential_content_read",
        "protected_values_included",
        "filesystem_mutation",
        "systemd_interaction",
        "authority_expanded",
        "production_mutation_started",
    }
)


class SanitizedHermesOriginHostEvidenceError(RuntimeError):
    pass


class HermesOriginHostObservationProvider(Protocol):
    """Future privileged adapter seam with no path, command or selector input."""

    def read(self) -> bytes: ...


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SanitizedHermesOriginHostEvidenceError(
                f"duplicate host-evidence field is forbidden: {key}"
            )
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise SanitizedHermesOriginHostEvidenceError(
        f"non-finite host-evidence number is forbidden: {value}"
    )


def _utc_timestamp(value: Any, where: str) -> datetime:
    if type(value) is not str:
        raise SanitizedHermesOriginHostEvidenceError(
            f"{where} must be canonical RFC3339 UTC"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise SanitizedHermesOriginHostEvidenceError(
            f"{where} must be canonical RFC3339 UTC"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise SanitizedHermesOriginHostEvidenceError(
            f"{where} must be canonical RFC3339 UTC"
        )
    return parsed


def _require_exact(value: Mapping[str, Any], field: str, expected: Any) -> None:
    if value[field] != expected or type(value[field]) is not type(expected):
        raise SanitizedHermesOriginHostEvidenceError(
            f"sanitized host {field} identity drifted"
        )


def _parse_observation(
    raw: bytes,
    *,
    expected_source_sha: str,
    github_server_time: str,
) -> Mapping[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > HOST_OBSERVATION_MAX_BYTES:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation size is invalid"
        )
    if b"\x00" in raw:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation contains a NUL byte"
        )
    try:
        decoded = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation is not UTF-8"
        ) from exc
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except SanitizedHermesOriginHostEvidenceError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation is not strict JSON"
        ) from exc
    if type(value) is not dict:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation must be an object"
        )
    actual = frozenset(value)
    if actual != _OBSERVATION_FIELDS:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation fields are not the fixed Hermes evidence schema"
        )

    if type(expected_source_sha) is not str or SHA_RE.fullmatch(expected_source_sha) is None:
        raise SanitizedHermesOriginHostEvidenceError(
            "expected Hermes source SHA is malformed"
        )
    _require_exact(value, "schema", HOST_OBSERVATION_SCHEMA)
    evidence_id = value["evidence_id"]
    if (
        type(evidence_id) is not str
        or EVIDENCE_ID_RE.fullmatch(evidence_id) is None
        or SECRET_LIKE_RE.search(evidence_id) is not None
    ):
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation evidence_id is invalid or secret-like"
        )
    observed_at = _utc_timestamp(value["observed_at"], "host observed_at")
    trusted_now = _utc_timestamp(github_server_time, "GitHub server time")
    age = (trusted_now - observed_at).total_seconds()
    if age < 0 or age > HOST_OBSERVATION_MAX_AGE_SECONDS:
        raise SanitizedHermesOriginHostEvidenceError(
            "host observation is stale or from the future"
        )

    exact_values = {
        "operation_id": OPERATION_ID,
        "registered_source_sha": expected_source_sha,
        "registration_path": REGISTRATION_PATH,
        "registration_name": REGISTRATION_NAME,
        "registration_owner": ROOT_OWNER,
        "registration_group": ROOT_GROUP,
        "registration_mode": REGISTRATION_MODE,
        "broker_install_path": BROKER_INSTALL_PATH,
        "broker_owner": ROOT_OWNER,
        "broker_group": ROOT_GROUP,
        "broker_mode": BROKER_MODE,
        "socket_path": BROKER_SOCKET_PATH,
        "socket_unit": BROKER_SOCKET_UNIT,
        "service_unit": BROKER_SERVICE_UNIT,
        "source_credential_path": SOURCE_CREDENTIAL_PATH,
        "source_credential_owner": SOURCE_CREDENTIAL_OWNER,
        "source_credential_group": SOURCE_CREDENTIAL_GROUP,
        "source_credential_mode": SOURCE_CREDENTIAL_MODE,
        "pull_helper_path": INSTALLED_HELPER_PATH,
        "pull_helper_owner": ROOT_OWNER,
        "pull_helper_group": ROOT_GROUP,
        "pull_helper_mode": PULL_HELPER_MODE,
        "pull_helper_source_blob": PULL_HELPER_SOURCE_BLOB,
        "pull_helper_argument_names": list(PULL_HELPER_ARGUMENTS),
        "probe_path": PROBE_PATH,
        "probe_source_blob": PROBE_SOURCE_BLOB,
        "dispatcher_source_blob": DISPATCHER_SOURCE_BLOB,
        "workflow_source_blob": WORKFLOW_SOURCE_BLOB,
        "evidence_read_only": True,
        "credential_content_read": False,
        "protected_values_included": False,
        "filesystem_mutation": False,
        "systemd_interaction": False,
        "authority_expanded": False,
        "production_mutation_started": False,
    }
    for field, expected in exact_values.items():
        _require_exact(value, field, expected)
    return value


class ConcreteSanitizedHermesOriginHostEvidenceResolver:
    """Validate one fixed, public-safe host observation without inspecting a host."""

    def __init__(self, *, observation_provider: HermesOriginHostObservationProvider):
        if not callable(getattr(observation_provider, "read", None)):
            raise SanitizedHermesOriginHostEvidenceError(
                "Hermes host observation provider is missing"
            )
        self._observation_provider = observation_provider

    def resolve(
        self,
        *,
        source_sha: str,
        github_server_time: str,
    ) -> Mapping[str, Any]:
        try:
            observation = _parse_observation(
                self._observation_provider.read(),
                expected_source_sha=source_sha,
                github_server_time=github_server_time,
            )
        except SanitizedHermesOriginHostEvidenceError:
            raise
        except Exception:
            raise SanitizedHermesOriginHostEvidenceError(
                "Hermes host observation provider failed closed"
            ) from None
        return {
            "schema": HOST_EVIDENCE_SCHEMA,
            "evidence_id": observation["evidence_id"],
            "operation_id": OPERATION_ID,
            "registered_source_sha": source_sha,
            "registration_name": REGISTRATION_NAME,
            "registration_owner_root": True,
            "registration_mode_0600": True,
            "dispatcher_identity_match": True,
            "probe_identity_match": True,
            "workflow_identity_match": True,
            "pull_helper_identity_match": True,
            "pull_helper_interface_match": True,
            "evidence_read_only": True,
            "evidence_fresh": True,
            "protected_values_included": False,
        }


def evidence_field_rationale() -> Mapping[str, str]:
    return {
        "schema/evidence_id/observed_at": "version, correlate and freshness-check one observation",
        "operation_id/registered_source_sha": "bind evidence to the canonical Hermes authorization",
        "registration identity": "prove the fixed root-owned 0600 registration contract",
        "broker/socket/service identity": "prove the reviewed capability-specific broker boundary",
        "source credential location metadata": "prove only the public path/owner/group/mode contract without reading credential content",
        "pull helper identity/interface": "prove the fixed helper blob, path and two canonical arguments",
        "probe/dispatcher/workflow blobs": "bind the complete reviewed origin-audit source chain",
        "negative safety flags": "prove collection exposed no secret, mutation, systemd or authority-expansion surface",
    }


def source_readiness() -> Mapping[str, object]:
    return {
        "sanitized_host_evidence_resolver_implemented": True,
        "observation_schema": HOST_OBSERVATION_SCHEMA,
        "output_schema": HOST_EVIDENCE_SCHEMA,
        "observation_max_bytes": HOST_OBSERVATION_MAX_BYTES,
        "observation_max_age_seconds": HOST_OBSERVATION_MAX_AGE_SECONDS,
        "provider_arguments": (),
        "resolver_arguments": ("source_sha", "github_server_time"),
        "filesystem_inspection_implemented": False,
        "filesystem_mutation_implemented": False,
        "subprocess_implemented": False,
        "systemd_interaction_implemented": False,
        "credential_content_read_implemented": False,
        "host_wiring_enabled": False,
        "production_mutation_started": False,
    }
