from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor.weather_private_gcs_contract import (
    GCS_RUNTIME_MATERIALIZATION,
    GOOGLE_AUTH_BINDING,
    PRIVATE_APPLICATION_STAGING,
    READ_ONLY_PRIVATE_GCS,
    WEATHER_ENTRYPOINT,
)
from deploy_executor.weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    GCSStageReceipt,
)
from deploy_executor.weather_private_gcs_trusted_backend import (
    CONTRACT_ID,
    SOURCE_STATUS,
    CanonicalGCSFacts,
    CanonicalWeatherNextGCSRevalidator,
    TrustedGCSCapabilitySet,
    TrustedGCSHostEntrypoint,
    TrustedWeatherNextGCSBackend,
    WeatherNextPrivateGCSTrustedBackendError,
    trusted_backend_source_contract,
    validate_canonical_gcs_facts,
)


INIT = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
RPI_SHA = "a" * 40
WEATHER_SHA = "b" * 40


class _Facts:
    def __init__(self, *, auth_state="ready"):
        self.auth_state = auth_state

    def load_gcs_facts(self, authorization_issue_number):
        return CanonicalGCSFacts(
            authorization_issue_number=authorization_issue_number,
            owner_authorized=True,
            authorization_operation_id=BRIDGE_OPERATION_ID,
            authorization_contract_id=CONTRACT_ID,
            rpi5_main_source_sha=RPI_SHA,
            rpi5_main_ci_success=True,
            weather_source_sha=WEATHER_SHA,
            weather_ci_success=True,
            selected_init_utc=INIT,
            target_alias="rpi5",
            application_staged=True,
            gcs_runtime_present=True,
            auth_binding_state=self.auth_state,
        )


class _Consumer:
    def __init__(self):
        self.first_stage = None

    def consume_once(self, authorization_issue_number, *, first_stage):
        self.first_stage = first_stage


class _App:
    def stage_exact_weather_source(self, *, weather_source_sha, stage_id, stage_root):
        return GCSStageReceipt(PRIVATE_APPLICATION_STAGING, "completed", True)


class _Runtime:
    def materialize_exact_gcs_runtime(self, *, rpi5_main_source_sha):
        return GCSStageReceipt(GCS_RUNTIME_MATERIALIZATION, "completed", True)


class _Auth:
    def bind_fixed_auth_slot(self, *, slot_id, mechanism):
        return GCSStageReceipt(GOOGLE_AUTH_BINDING, "completed", True)


class _Read:
    def __init__(self):
        self.entrypoint = None

    def run_fixed_gcs_first_access(
        self, *, weather_source_sha, entrypoint, scope
    ):
        self.entrypoint = entrypoint
        return GCSStageReceipt(READ_ONLY_PRIVATE_GCS, "completed", False)


class WeatherPrivateGCSTrustedBackendTests(unittest.TestCase):
    def test_canonical_gcs_facts_have_no_project_or_dataset_readiness(self):
        facts = _Facts().load_gcs_facts(825)
        validated = validate_canonical_gcs_facts(
            facts, requested_issue_number=825
        )
        self.assertEqual(validated["source_status"], SOURCE_STATUS)
        self.assertTrue(validated["auth_bound"])
        self.assertEqual(validated["scope"]["location_id"], "station_05480")
        self.assertNotIn("project_bound", validated)
        self.assertNotIn("linked_dataset_present", validated)

        with self.assertRaisesRegex(
            WeatherNextPrivateGCSTrustedBackendError,
            "Google auth binding mismatch",
        ):
            validate_canonical_gcs_facts(
                _Facts(auth_state="mismatch").load_gcs_facts(825),
                requested_issue_number=825,
            )

    def test_trusted_wrapper_uses_fixed_weather_gcs_entrypoint(self):
        read = _Read()
        backend = TrustedWeatherNextGCSBackend(
            TrustedGCSCapabilitySet(
                application_stager=_App(),
                runtime_materializer=_Runtime(),
                google_auth=_Auth(),
                first_access=read,
            )
        )
        consumer = _Consumer()
        wrapper = TrustedGCSHostEntrypoint(
            canonical_revalidator=CanonicalWeatherNextGCSRevalidator(_Facts()),
            authorization_consumer=consumer,
            backend=backend,
        )
        result = wrapper.dispatch(825)
        self.assertEqual(consumer.first_stage, READ_ONLY_PRIVATE_GCS)
        self.assertEqual(read.entrypoint, WEATHER_ENTRYPOINT)
        self.assertEqual(result["status"], "private_gcs_execution_sequence_completed")
        self.assertFalse(result["bigquery_performed"])

    def test_source_contract_exposes_runtime_materialization_as_next_prerequisite(self):
        source = trusted_backend_source_contract()
        self.assertEqual(source["source_status"], SOURCE_STATUS)
        self.assertTrue(source["canonical_revalidator_implemented"])
        self.assertTrue(source["source_wrapper_implemented"])
        self.assertFalse(source["gcs_runtime_materializer_implementation_present"])
        self.assertFalse(source["external_entrypoint_enabled"])
        self.assertFalse(source["credential_read_enabled"])
        self.assertFalse(source["read_only_gcs_execution_enabled"])
        self.assertFalse(source["project_binding_execution_enabled"])
        self.assertFalse(source["analytics_hub_execution_enabled"])
        self.assertFalse(source["bigquery_execution_enabled"])
        self.assertFalse(source["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
