from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .adapters import AdapterError

BASELINE_RESOLVER_ID = "rozkalns-weather.public-runtime-baseline.v1"
EVIDENCE_SCHEMA = "rozkalns-weather.public-runtime-baseline-evidence.v1"
TARGET_ALIAS = "rozkalns-weather-public-rpi5"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_KEYS = frozenset(
    {
        "schema",
        "target_alias",
        "deployment_state",
        "current_source_sha",
        "persistent_volume_state",
        "public_ingest_schedule_state",
    }
)
VOLUME_STATES = frozenset({"absent", "present", "unknown"})
SCHEDULE_STATES = frozenset({"absent", "present", "unknown"})


@dataclass(frozen=True)
class WeatherPublicRuntimeBaseline:
    deployment_state: str
    current_source_sha: str | None
    persistent_volume_state: str
    public_ingest_schedule_state: str

    @property
    def canonical_token(self) -> str:
        current = self.current_source_sha or "none"
        return ";".join(
            (
                f"state={self.deployment_state}",
                f"current={current}",
                f"volume={self.persistent_volume_state}",
                f"schedule={self.public_ingest_schedule_state}",
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "resolver_id": BASELINE_RESOLVER_ID,
            "deployment_state": self.deployment_state,
            "current_source_sha": self.current_source_sha,
            "persistent_volume_state": self.persistent_volume_state,
            "public_ingest_schedule_state": self.public_ingest_schedule_state,
            "canonical_token": self.canonical_token,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def resolve_public_runtime_baseline(
    evidence: Mapping[str, Any],
) -> WeatherPublicRuntimeBaseline:
    """Resolve sanitized read-only evidence into a deterministic baseline.

    The caller is responsible for collecting host evidence under the separately
    approved read-only trust boundary. This function performs no filesystem,
    Docker, systemd, network, credential or database access.
    """

    if type(evidence) is not dict:
        raise AdapterError("weather baseline evidence must be an object")
    if frozenset(evidence) != EVIDENCE_KEYS:
        raise AdapterError("weather baseline evidence keys mismatch")
    if evidence["schema"] != EVIDENCE_SCHEMA:
        raise AdapterError("weather baseline evidence schema mismatch")
    if evidence["target_alias"] != TARGET_ALIAS:
        raise AdapterError("weather baseline target alias mismatch")

    deployment_state = evidence["deployment_state"]
    current_source_sha = evidence["current_source_sha"]
    if deployment_state == "not_deployed":
        if current_source_sha is not None:
            raise AdapterError("not_deployed weather baseline must not claim a current source SHA")
    elif deployment_state == "deployed":
        if type(current_source_sha) is not str or SHA_RE.fullmatch(current_source_sha) is None:
            raise AdapterError("deployed weather baseline requires exact lowercase 40-character source SHA")
    else:
        raise AdapterError("weather deployment_state must be not_deployed or deployed")

    volume_state = evidence["persistent_volume_state"]
    if volume_state not in VOLUME_STATES:
        raise AdapterError("weather persistent volume state is invalid")
    schedule_state = evidence["public_ingest_schedule_state"]
    if schedule_state not in SCHEDULE_STATES:
        raise AdapterError("weather public ingest schedule state is invalid")

    return WeatherPublicRuntimeBaseline(
        deployment_state=deployment_state,
        current_source_sha=current_source_sha,
        persistent_volume_state=volume_state,
        public_ingest_schedule_state=schedule_state,
    )
