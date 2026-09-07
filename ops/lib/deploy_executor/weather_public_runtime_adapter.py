from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

OPERATION_ID = "rozkalns-weather.public-runtime-release.v1"
ADAPTER_ID = OPERATION_ID
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns_weather"
SOURCE_REPOSITORY_ID = 1359499204
TARGET_ALIAS = "rozkalns-weather-public-rpi5"
BASELINE_RESOLVER_ID = "rozkalns-weather.public-runtime-baseline.v1"
ROLLBACK_POLICY = "NONE"
HANDOFF_DESIGN_SOURCE_SHA = "6296556e783967c0897abc4e27368295a1158c7e"
RUNTIME_DESCRIPTOR_BLOB = "dde970523486123e2809388bff9ed8b643cb6940"
COMPOSE_PUBLIC_BLOB = "41b40d614907acd7f257c2fd4eea368de47fb1ea"
PUBLIC_INGEST_SCHEDULE_BLOB = "d67dd0bb606f6d25922972729a4ff1ad33a68224"
HANDOFF_DOC_BLOB = "8004da2243aa3bb3e1fb9917bc8819134f117cf8"
COMPOSE_SERVICES = ("schema-init", "weather", "public-ingest", "readiness")
PERSISTENT_VOLUME = "weather_data"
DATABASE_URL = "sqlite:///data/weather.db"
READINESS_ENDPOINT = "/ready"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

MUTATION_BUDGET = (
    ("filesystem.release-materialization", 1),
    ("docker.named-volume-ensure", 1),
    ("docker.compose-build", 1),
    ("docker.compose-application-apply", 1),
    ("systemd.public-ingest-schedule-install-or-update", 1),
)

REQUIRED_EXCLUSIONS = frozenset(
    {
        "arbitrary command/path/argv/environment authority",
        "credentials, HOME_LAT, HOME_LON or exact home coordinates",
        "Google Cloud, BigQuery or WeatherNext private access",
        "Cloudflare, network or firewall mutation",
        "SQLite schema initialization or historical corpus backfill",
        "corpus delete, restore, backup or destructive rollback",
        "package install or generic sudo/root authority",
        "repository settings, rulesets, permissions or secrets changes",
        "automatic retry, cleanup or rollback",
    }
)

REQUIRED_DEPENDENCIES = frozenset(
    {
        f"source-repository-id:{SOURCE_REPOSITORY_ID}",
        f"handoff-design-source-sha:{HANDOFF_DESIGN_SOURCE_SHA}",
        f"runtime-descriptor-blob:{RUNTIME_DESCRIPTOR_BLOB}",
        f"compose-public-blob:{COMPOSE_PUBLIC_BLOB}",
        f"public-ingest-schedule-blob:{PUBLIC_INGEST_SCHEDULE_BLOB}",
        f"handoff-doc-blob:{HANDOFF_DOC_BLOB}",
        "runtime-class:public-only-rpi5",
        "compose-services:schema-init,weather,public-ingest,readiness",
        f"persistent-volume:{PERSISTENT_VOLUME}",
        f"database-url:{DATABASE_URL}",
        f"readiness-endpoint:{READINESS_ENDPOINT}",
        "weathernext-required:false",
        "home-coordinates-required:false",
    }
)


class WeatherPublicRuntimeAdapter:
    """Static source contract for the public-only weather runtime.

    This adapter deliberately has no execution bridge. It validates the reviewed
    weather handoff and a future exact source identity while the production
    registry remains globally disabled. Host execution requires a separately
    reviewed LIVE capability that does not exist in this issue.
    """

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("weather operation/adapter identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("weather public runtime adapter must remain execution-disabled")
        if prepared.source_repository != SOURCE_REPOSITORY:
            raise AdapterError("weather source repository mismatch")
        if SHA_RE.fullmatch(prepared.source_sha) is None:
            raise AdapterError("weather source SHA must be exact lowercase 40-character SHA")
        if prepared.target_alias != TARGET_ALIAS:
            raise AdapterError("weather target alias mismatch")
        if prepared.expected_baseline_kind != "resolver":
            raise AdapterError("weather baseline kind must remain resolver")
        if prepared.expected_baseline_value != BASELINE_RESOLVER_ID:
            raise AdapterError("weather baseline resolver identity mismatch")
        if prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("weather application release rollback policy must remain NONE")
        if prepared.mutation_budget != MUTATION_BUDGET:
            raise AdapterError("weather mutation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("weather required exclusions are missing")
        if not REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("weather handoff dependency mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "operation_id": OPERATION_ID,
            "adapter_id": ADAPTER_ID,
            "source_repository_id": SOURCE_REPOSITORY_ID,
            "source_sha": prepared.source_sha,
            "target_alias": TARGET_ALIAS,
            "baseline_resolver_id": BASELINE_RESOLVER_ID,
            "runtime_descriptor_blob": RUNTIME_DESCRIPTOR_BLOB,
            "compose_public_blob": COMPOSE_PUBLIC_BLOB,
            "public_ingest_schedule_blob": PUBLIC_INGEST_SCHEDULE_BLOB,
            "handoff_doc_blob": HANDOFF_DOC_BLOB,
            "compose_services": COMPOSE_SERVICES,
            "persistent_volume": PERSISTENT_VOLUME,
            "database_url": DATABASE_URL,
            "readiness_endpoint": READINESS_ENDPOINT,
            "weathernext_required": False,
            "home_coordinates_required": False,
            "read_only_contract": True,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "requires_separate_live_authorization": True,
            "result": "WEATHER_PUBLIC_RUNTIME_SOURCE_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "weather public runtime execution-disabled; separate LIVE capability and authorization required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "exact_application_source_sha": prepared.source_sha,
            "readiness_endpoint": READINESS_ENDPOINT,
            "readiness_privacy_safe": True,
            "persistent_volume": PERSISTENT_VOLUME,
            "persistent_volume_retained": True,
            "weathernext_required": False,
            "public_ingest_independent_from_weathernext": True,
            "sqlite_rollback_delete_restore": False,
            "automatic_retry_cleanup_rollback": False,
            "execution_enabled": False,
        }
