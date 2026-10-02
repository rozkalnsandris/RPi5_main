from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

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


class WeatherPrivateGCSExecutionBridgeTests(unittest.TestCase):
    def test_gcs_contract_is_fixed_and_excludes_bigquery_control_plane(self):
        scope = validate_first_access_scope(GCSFirstAccessScope(selected_init_utc=INIT))
        self.assertEqual(scope["location_id"], "station_05480")
        self.assertEqual(scope["forecast_hours"], 6)
        self.assertEqual(scope["bucket"], "weathernext3_statistics_spatial")
        self.assertEqual(
            scope["required_permissions"],
            ("storage.objects.list", "storage.objects.get"),
        )
        self.assertEqual(scope["materialized_scalar_ceiling"], 288)
        self.assertFalse(scope["requester_pays"])
        self.assertFalse(scope["billing_project_header_required"])
        self.assertFalse(scope["home_scope_enabled"])
        self.assertFalse(scope["sqlite_write_enabled"])

        summary = source_contract_summary()
        self.assertEqual(
            summary["authorized_stage_sequence"],
            (
                PRIVATE_APPLICATION_STAGING,
                GCS_RUNTIME_MATERIALIZATION,
                GOOGLE_AUTH_BINDING,
                READ_ONLY_PRIVATE_GCS,
            ),
        )
        self.assertFalse(summary["project_binding_required"])
        self.assertFalse(summary["dataset_binding_required"])
        self.assertFalse(summary["analytics_hub_link_required"])
        self.assertFalse(summary["bigquery_authorized"])
        self.assertFalse(summary["execution_enabled"])

    def test_bigquery_and_gcs_authorities_cannot_cross_dispatch(self):
        gcs = GCSExecutionEnvelope(
            authorization_issue_number=825,
            rpi5_main_source_sha=RPI_SHA,
            weather_source_sha=WEATHER_SHA,
            selected_init_utc=INIT,
            baseline=GCSExecutionBaseline(True, True, True),
            contract_id=BIGQUERY_CONTRACT_ID,
        )
        with self.assertRaisesRegex(
            WeatherNextPrivateGCSExecutionBridgeError,
            "BigQuery authority cannot dispatch GCS",
        ):
            validate_gcs_execution_envelope(gcs)

        bigquery = PrivateExecutionEnvelope(
            authorization_issue_number=825,
            rpi5_main_source_sha=RPI_SHA,
            weather_source_sha=WEATHER_SHA,
            baseline=PrivateExecutionBaseline(True, True, True, True, True),
            contract_id=CONTRACT_ID,
        )
        with self.assertRaisesRegex(
            WeatherNextPrivateExecutionBridgeError,
            "private WeatherNext contract identity mismatch",
        ):
            validate_private_execution_envelope(bigquery)

    def test_gcs_bridge_executes_only_fixed_stage_sequence(self):
        baseline = GCSExecutionBaseline(False, False, False)
        consumer = _Consumer()
        backend = _Backend()
        result = execute_private_gcs_for_authorization(
            825,
            canonical_revalidator=_Revalidator(baseline),
            authorization_consumer=consumer,
            backend=backend,
        )
        self.assertEqual(consumer.calls, [(825, PRIVATE_APPLICATION_STAGING)])
        self.assertEqual(backend.calls, list(AUTHORIZED_STAGE_SEQUENCE))
        self.assertEqual(
            [receipt.stage for receipt in result["stage_receipts"]],
            list(AUTHORIZED_STAGE_SEQUENCE),
        )
        self.assertFalse(result["google_project_binding_performed"])
        self.assertFalse(result["analytics_hub_link_performed"])
        self.assertFalse(result["bigquery_performed"])
        self.assertFalse(result["sqlite_write_performed"])
        self.assertFalse(result["automatic_retry_performed"])

    def test_ready_baseline_consumes_authority_at_read_only_gcs_stage(self):
        baseline = GCSExecutionBaseline(True, True, True)
        consumer = _Consumer()
        backend = _Backend()
        result = execute_private_gcs_for_authorization(
            825,
            canonical_revalidator=_Revalidator(baseline),
            authorization_consumer=consumer,
            backend=backend,
        )
        self.assertEqual(consumer.calls, [(825, READ_ONLY_PRIVATE_GCS)])
        self.assertEqual(backend.calls, [READ_ONLY_PRIVATE_GCS])
        receipts = result["stage_receipts"]
        self.assertEqual(
            [item.status for item in receipts[:3]],
            ["already_present", "already_present", "already_present"],
        )
        self.assertEqual(receipts[3].stage, READ_ONLY_PRIVATE_GCS)

    def test_source_readiness_tracks_runtime_source_but_keeps_execution_disabled(self):
        readiness = source_readiness()
        self.assertEqual(readiness["operation_id"], BRIDGE_OPERATION_ID)
        self.assertTrue(readiness["gcs_runtime_materializer_implemented"])
        self.assertFalse(readiness["read_only_gcs_execution_enabled"])
        self.assertFalse(readiness["google_project_binding_execution_enabled"])
        self.assertFalse(readiness["analytics_hub_link_execution_enabled"])
        self.assertFalse(readiness["bigquery_execution_enabled"])
        self.assertFalse(readiness["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
