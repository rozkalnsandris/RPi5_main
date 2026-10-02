from datetime import datetime, timezone

import pytest

from deploy_executor.weather_private_bigquery_contract import CONTRACT_ID as BIGQUERY_CONTRACT_ID
from deploy_executor.weather_private_bigquery_execution_bridge import (
    PrivateExecutionBaseline,
    PrivateExecutionEnvelope,
    WeatherNextPrivateExecutionBridgeError,
    validate_private_execution_envelope,
)
from deploy_executor.weather_private_gcs_contract import (
    AUTHORIZED_STAGE_SEQUENCE,
    CONTRACT_ID,
    GCS_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    PRIVATE_APPLICATION_STAGING,
    READ_ONLY_PRIVATE_GCS,
    GCSFirstAccessScope,
    source_contract_summary,
    validate_first_access_scope,
)
from deploy_executor.weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    GCSExecutionBaseline,
    GCSExecutionEnvelope,
    GCSStageReceipt,
    WeatherNextPrivateGCSExecutionBridgeError,
    execute_private_gcs_for_authorization,
    source_readiness,
    validate_gcs_execution_envelope,
)


INIT = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
RPI_SHA = "1" * 40
WEATHER_SHA = "2" * 40


def test_gcs_contract_is_fixed_and_excludes_bigquery_control_plane() -> None:
    scope = validate_first_access_scope(GCSFirstAccessScope(selected_init_utc=INIT))
    assert scope["location_id"] == "station_05480"
    assert scope["forecast_hours"] == 6
    assert scope["bucket"] == "weathernext3_statistics_spatial"
    assert scope["required_permissions"] == (
        "storage.objects.list",
        "storage.objects.get",
    )
    assert scope["materialized_scalar_ceiling"] == 288
    assert scope["requester_pays"] is False
    assert scope["billing_project_header_required"] is False
    assert scope["home_scope_enabled"] is False
    assert scope["sqlite_write_enabled"] is False

    summary = source_contract_summary()
    assert summary["authorized_stage_sequence"] == (
        PRIVATE_APPLICATION_STAGING,
        GCS_RUNTIME_MATERIALIZATION,
        GOOGLE_AUTH_BINDING,
        READ_ONLY_PRIVATE_GCS,
    )
    assert summary["project_binding_required"] is False
    assert summary["dataset_binding_required"] is False
    assert summary["analytics_hub_link_required"] is False
    assert summary["bigquery_authorized"] is False
    assert summary["execution_enabled"] is False


def test_bigquery_and_gcs_authorities_cannot_cross_dispatch() -> None:
    gcs = GCSExecutionEnvelope(
        authorization_issue_number=825,
        rpi5_main_source_sha=RPI_SHA,
        weather_source_sha=WEATHER_SHA,
        selected_init_utc=INIT,
        baseline=GCSExecutionBaseline(True, True, True),
        contract_id=BIGQUERY_CONTRACT_ID,
    )
    with pytest.raises(
        WeatherNextPrivateGCSExecutionBridgeError,
        match="BigQuery authority cannot dispatch GCS",
    ):
        validate_gcs_execution_envelope(gcs)

    bigquery = PrivateExecutionEnvelope(
        authorization_issue_number=825,
        rpi5_main_source_sha=RPI_SHA,
        weather_source_sha=WEATHER_SHA,
        baseline=PrivateExecutionBaseline(True, True, True, True, True),
        contract_id=CONTRACT_ID,
    )
    with pytest.raises(
        WeatherNextPrivateExecutionBridgeError,
        match="private WeatherNext contract identity mismatch",
    ):
        validate_private_execution_envelope(bigquery)


class _Revalidator:
    def __init__(self, baseline):
        self.baseline = baseline

    def prepare_private_gcs_execution(self, authorization_issue_number):
        return GCSExecutionEnvelope(
            authorization_issue_number=authorization_issue_number,
            rpi5_main_source_sha=RPI_SHA,
            weather_source_sha=WEATHER_SHA,
            selected_init_utc=INIT,
            baseline=self.baseline,
        )


class _Consumer:
    def __init__(self):
        self.calls = []

    def consume_once(self, authorization_issue_number, *, first_stage):
        self.calls.append((authorization_issue_number, first_stage))


class _Backend:
    def __init__(self):
        self.calls = []

    def stage_application(self, envelope):
        self.calls.append(PRIVATE_APPLICATION_STAGING)
        return GCSStageReceipt(PRIVATE_APPLICATION_STAGING, "completed", True)

    def materialize_gcs_runtime(self, envelope):
        self.calls.append(GCS_RUNTIME_MATERIALIZATION)
        return GCSStageReceipt(GCS_RUNTIME_MATERIALIZATION, "completed", True)

    def bind_google_auth(self, envelope):
        self.calls.append(GOOGLE_AUTH_BINDING)
        return GCSStageReceipt(GOOGLE_AUTH_BINDING, "completed", True)

    def run_read_only_first_access(self, envelope):
        self.calls.append(READ_ONLY_PRIVATE_GCS)
        return GCSStageReceipt(READ_ONLY_PRIVATE_GCS, "completed", False)


def test_gcs_bridge_executes_only_fixed_stage_sequence() -> None:
    baseline = GCSExecutionBaseline(False, False, False)
    consumer = _Consumer()
    backend = _Backend()

    result = execute_private_gcs_for_authorization(
        825,
        canonical_revalidator=_Revalidator(baseline),
        authorization_consumer=consumer,
        backend=backend,
    )

    assert consumer.calls == [(825, PRIVATE_APPLICATION_STAGING)]
    assert backend.calls == list(AUTHORIZED_STAGE_SEQUENCE)
    assert [receipt.stage for receipt in result["stage_receipts"]] == list(
        AUTHORIZED_STAGE_SEQUENCE
    )
    assert result["google_project_binding_performed"] is False
    assert result["analytics_hub_link_performed"] is False
    assert result["bigquery_performed"] is False
    assert result["sqlite_write_performed"] is False
    assert result["automatic_retry_performed"] is False


def test_ready_baseline_consumes_authority_at_read_only_gcs_stage() -> None:
    baseline = GCSExecutionBaseline(True, True, True)
    consumer = _Consumer()
    backend = _Backend()

    result = execute_private_gcs_for_authorization(
        825,
        canonical_revalidator=_Revalidator(baseline),
        authorization_consumer=consumer,
        backend=backend,
    )

    assert consumer.calls == [(825, READ_ONLY_PRIVATE_GCS)]
    assert backend.calls == [READ_ONLY_PRIVATE_GCS]
    receipts = result["stage_receipts"]
    assert [item.status for item in receipts[:3]] == [
        "already_present",
        "already_present",
        "already_present",
    ]
    assert receipts[3].stage == READ_ONLY_PRIVATE_GCS


def test_source_readiness_keeps_execution_disabled_until_gcs_runtime_exists() -> None:
    readiness = source_readiness()
    assert readiness["operation_id"] == BRIDGE_OPERATION_ID
    assert readiness["gcs_runtime_materializer_implemented"] is False
    assert readiness["read_only_gcs_execution_enabled"] is False
    assert readiness["google_project_binding_execution_enabled"] is False
    assert readiness["analytics_hub_link_execution_enabled"] is False
    assert readiness["bigquery_execution_enabled"] is False
    assert readiness["source_merge_authorizes_live"] is False
