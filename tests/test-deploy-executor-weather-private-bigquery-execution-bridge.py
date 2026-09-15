from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_execution_bridge as bridge
from deploy_executor.weather_private_bigquery_contract import (
    ANALYTICS_HUB_LINK_CREATE,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    PRIVATE_RUNTIME_MATERIALIZATION,
    PUBLIC_RUNTIME_OPERATION_ID,
    READ_ONLY_PRIVATE_BIGQUERY,
)

CONTRACT_PATH = ROOT / "ops/deploy/weather-private-bigquery-execution-bridge.json"


def baseline(**overrides: bool) -> bridge.PrivateExecutionBaseline:
    values = dict(
        application_staged=False,
        runtime_present=False,
        auth_binding_present=False,
        project_binding_present=False,
        linked_dataset_present=False,
    )
    values.update(overrides)
    return bridge.PrivateExecutionBaseline(**values)


def envelope(**overrides: Any) -> bridge.PrivateExecutionEnvelope:
    values = dict(
        authorization_issue_number=700,
        rpi5_main_source_sha="1" * 40,
        weather_source_sha="2" * 40,
        baseline=baseline(),
    )
    values.update(overrides)
    return bridge.PrivateExecutionEnvelope(**values)


class Revalidator:
    def __init__(self, prepared: bridge.PrivateExecutionEnvelope):
        self.prepared = prepared

    def prepare_private_execution(self, authorization_issue_number: int) -> bridge.PrivateExecutionEnvelope:
        return self.prepared


class Consumer:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None:
        self.calls.append((authorization_issue_number, first_stage))


class Backend:
    def __init__(self, *, fail_stage: str | None = None, already_stage: str | None = None):
        self.calls: list[str] = []
        self.fail_stage = fail_stage
        self.already_stage = already_stage

    def _run(self, stage: str) -> bridge.StageReceipt:
        self.calls.append(stage)
        if stage == self.fail_stage:
            raise bridge.WeatherNextPrivateExecutionBridgeError("fixture failure")
        if stage == self.already_stage:
            return bridge.StageReceipt(stage=stage, status="already_present", mutation_performed=False)
        return bridge.StageReceipt(
            stage=stage,
            status="completed",
            mutation_performed=stage != READ_ONLY_PRIVATE_BIGQUERY,
        )

    def stage_application(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(bridge.PRIVATE_APPLICATION_STAGING)

    def materialize_runtime(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(PRIVATE_RUNTIME_MATERIALIZATION)

    def bind_google_auth(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(GOOGLE_AUTH_BINDING)

    def bind_google_project(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(GOOGLE_PROJECT_BINDING)

    def create_analytics_hub_link(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(ANALYTICS_HUB_LINK_CREATE)

    def run_read_only_first_access(self, prepared: bridge.PrivateExecutionEnvelope) -> bridge.StageReceipt:
        return self._run(READ_ONLY_PRIVATE_BIGQUERY)


class WeatherNextPrivateExecutionBridgeTests(unittest.TestCase):
    def test_source_contract_json_matches_bridge_identity_and_safety(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "rozkalns-weather.weathernext-private-execution-bridge-source.v1")
        self.assertEqual(contract["operation_id"], bridge.BRIDGE_OPERATION_ID)
        self.assertEqual(contract["target_alias"], bridge.TARGET_ALIAS)
        self.assertEqual(tuple(contract["authorized_stage_sequence"]), bridge.AUTHORIZED_STAGE_SEQUENCE)
        self.assertEqual(contract["request_authority"], ["authorization_issue_number"])
        self.assertEqual(contract["authorization_class"], "STRICT")
        self.assertFalse(contract["execution_enabled"])
        self.assertFalse(contract["ordinary_live_all_eligible"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertEqual(contract["separate_later_gate"], "production_sqlite_forecast_snapshot_write")
        self.assertTrue(contract["first_access"]["dry_run_required"])
        self.assertEqual(contract["first_access"]["forecast_hours"], 6)
        self.assertEqual(contract["first_access"]["location_id"], "station_10416")
        self.assertFalse(contract["first_access"]["home_scope_enabled"])
        self.assertFalse(contract["first_access"]["sqlite_write_enabled"])
        self.assertTrue(all(value is False for value in contract["caller_controls"].values()))
        self.assertFalse(contract["failure_semantics"]["automatic_retry"])
        self.assertFalse(contract["failure_semantics"]["automatic_cleanup"])
        self.assertFalse(contract["failure_semantics"]["automatic_rollback"])

    def test_exact_order_and_read_only_receipt_is_non_mutating(self) -> None:
        consumer = Consumer()
        backend = Backend()
        result = bridge.execute_private_execution_for_authorization(
            700,
            canonical_revalidator=Revalidator(envelope()),
            authorization_consumer=consumer,
            backend=backend,
        )
        self.assertEqual(tuple(backend.calls), bridge.AUTHORIZED_STAGE_SEQUENCE)
        self.assertEqual(consumer.calls, [(700, bridge.PRIVATE_APPLICATION_STAGING)])
        self.assertFalse(result["stage_receipts"][-1].mutation_performed)
        self.assertFalse(result["sqlite_write_performed"])

    def test_present_prerequisites_are_skipped_only_from_canonical_baseline(self) -> None:
        prepared = envelope(
            baseline=baseline(
                application_staged=True,
                runtime_present=True,
                auth_binding_present=True,
                project_binding_present=True,
                linked_dataset_present=True,
            )
        )
        consumer = Consumer()
        backend = Backend()
        result = bridge.execute_private_execution_for_authorization(
            700,
            canonical_revalidator=Revalidator(prepared),
            authorization_consumer=consumer,
            backend=backend,
        )
        self.assertEqual(backend.calls, [READ_ONLY_PRIVATE_BIGQUERY])
        self.assertEqual(consumer.calls, [(700, READ_ONLY_PRIVATE_BIGQUERY)])
        self.assertTrue(all(receipt.status == "already_present" for receipt in result["stage_receipts"][:5]))

    def test_invalid_identity_scope_or_sequence_is_rejected(self) -> None:
        prepared = envelope()
        invalid = (
            replace(prepared, operation_id="other.operation"),
            replace(prepared, contract_id=PUBLIC_RUNTIME_OPERATION_ID),
            replace(prepared, target_alias="other"),
            replace(prepared, rpi5_main_source_sha="bad"),
            replace(prepared, weather_source_sha="bad"),
            replace(prepared, forecast_hours=7),
            replace(prepared, home_scope_enabled=True),
            replace(prepared, sqlite_write_enabled=True),
            replace(prepared, authorized_stages=tuple(reversed(bridge.AUTHORIZED_STAGE_SEQUENCE))),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(Exception):
                    bridge.validate_private_execution_envelope(candidate)

    def test_required_stage_cannot_claim_already_present_after_baseline(self) -> None:
        consumer = Consumer()
        backend = Backend(already_stage=GOOGLE_AUTH_BINDING)
        with self.assertRaisesRegex(
            bridge.WeatherNextPrivateExecutionBridgeError,
            "cannot skip a stage",
        ):
            bridge.execute_private_execution_for_authorization(
                700,
                canonical_revalidator=Revalidator(envelope()),
                authorization_consumer=consumer,
                backend=backend,
            )
        self.assertEqual(
            backend.calls,
            [
                bridge.PRIVATE_APPLICATION_STAGING,
                PRIVATE_RUNTIME_MATERIALIZATION,
                GOOGLE_AUTH_BINDING,
            ],
        )
        self.assertEqual(len(consumer.calls), 1)

    def test_failure_stops_later_stages_without_retry_or_cleanup(self) -> None:
        backend = Backend(fail_stage=GOOGLE_PROJECT_BINDING)
        consumer = Consumer()
        with self.assertRaises(bridge.WeatherNextPrivateExecutionBridgeError):
            bridge.execute_private_execution_for_authorization(
                700,
                canonical_revalidator=Revalidator(envelope()),
                authorization_consumer=consumer,
                backend=backend,
            )
        self.assertEqual(
            backend.calls,
            [
                bridge.PRIVATE_APPLICATION_STAGING,
                PRIVATE_RUNTIME_MATERIALIZATION,
                GOOGLE_AUTH_BINDING,
                GOOGLE_PROJECT_BINDING,
            ],
        )
        self.assertEqual(len(consumer.calls), 1)

    def test_validation_evidence_has_no_private_binding_identifiers(self) -> None:
        evidence = bridge.validate_private_execution_envelope(envelope())

        def collect_keys(value: Any) -> set[str]:
            keys: set[str] = set()
            if isinstance(value, dict):
                for key, item in value.items():
                    keys.add(str(key))
                    keys.update(collect_keys(item))
            elif isinstance(value, (tuple, list)):
                for item in value:
                    keys.update(collect_keys(item))
            return keys

        forbidden_keys = {
            "project_id",
            "dataset_id",
            "account_email",
            "credential_material",
            "credential_path",
            "home_lat",
            "home_lon",
            "raw_provider_value",
        }
        self.assertTrue(forbidden_keys.isdisjoint(collect_keys(evidence)))

    def test_source_surface_has_no_generic_execution_or_secret_authority(self) -> None:
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_execution_bridge.py"
        ).read_text(encoding="utf-8")
        for token in (
            "subprocess",
            "os.environ",
            "Popen(",
            "shell=True",
            "sudo ",
            "pip install",
            "apt ",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "HOME_LAT",
            "HOME_LON",
            ".env",
        ):
            self.assertNotIn(token, source)
        readiness = bridge.source_readiness()
        self.assertTrue(readiness["bridge_source_implemented"])
        self.assertFalse(readiness["external_entrypoint_enabled"])
        self.assertFalse(readiness["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
