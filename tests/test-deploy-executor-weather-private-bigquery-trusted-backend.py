from __future__ import annotations

import inspect
import json
import sys
import unittest
from dataclasses import fields
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_trusted_backend as trusted
from deploy_executor.weather_private_bigquery_contract import (
    ANALYTICS_HUB_LINK_CREATE,
    CONTRACT_ID,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    PRIVATE_RUNTIME_MATERIALIZATION,
    READ_ONLY_PRIVATE_BIGQUERY,
)
from deploy_executor.weather_private_bigquery_execution_bridge import (
    PRIVATE_APPLICATION_STAGING,
    StageReceipt,
)
from deploy_executor.weather_private_bigquery_runtime_materialization import (
    ARTIFACT_FORMAT,
    TARGET_ARCH,
    TARGET_OS,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
    TARGET_PYTHON_VERSION,
    RuntimeArtifactReceipt,
)

CONTRACT_PATH = ROOT / "ops/deploy/weather-private-bigquery-trusted-backend.json"


def canonical_facts(**overrides: Any) -> trusted.CanonicalPrivateFacts:
    values = dict(
        authorization_issue_number=900,
        owner_authorized=True,
        authorization_operation_id=trusted.BRIDGE_OPERATION_ID,
        authorization_contract_id=CONTRACT_ID,
        rpi5_main_source_sha="1" * 40,
        rpi5_main_ci_success=True,
        weather_source_sha="2" * 40,
        weather_ci_success=True,
        target_alias="rpi5",
        host_capability_installed=False,
        application_staged=False,
        runtime_present=False,
        runtime_python_abi=None,
        auth_binding_state="absent",
        project_binding_state="absent",
        linked_dataset_state="absent",
        read_only_first_access_authorized=False,
        read_only_first_access_executed=False,
    )
    values.update(overrides)
    return trusted.CanonicalPrivateFacts(**values)


class FactsProvider:
    def __init__(self, facts: trusted.CanonicalPrivateFacts):
        self.facts = facts
        self.calls: list[int] = []

    def load_private_facts(self, authorization_issue_number: int) -> trusted.CanonicalPrivateFacts:
        self.calls.append(authorization_issue_number)
        return self.facts


class Consumer:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None:
        self.calls.append((authorization_issue_number, first_stage))


class ApplicationStager:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]], fail: bool = False):
        self.calls = calls
        self.fail = fail

    def stage_exact_weather_source(self, **kwargs: Any) -> StageReceipt:
        self.calls.append((PRIVATE_APPLICATION_STAGING, kwargs))
        if self.fail:
            raise trusted.WeatherNextPrivateTrustedBackendError("fixture stage failure")
        return StageReceipt(PRIVATE_APPLICATION_STAGING, "completed", True)


class ReceiptProvider:
    def __init__(self, receipt: RuntimeArtifactReceipt, calls: list[tuple[str, dict[str, Any]]]):
        self.receipt = receipt
        self.calls = calls

    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt:
        self.calls.append(("runtime_receipt", {"source_sha": rpi5_main_source_sha}))
        return self.receipt


class AuthBinder:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]):
        self.calls = calls

    def bind_fixed_auth_slot(self, **kwargs: Any) -> StageReceipt:
        self.calls.append((GOOGLE_AUTH_BINDING, kwargs))
        return StageReceipt(GOOGLE_AUTH_BINDING, "completed", True)


class ProjectBinder:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]):
        self.calls = calls

    def bind_fixed_project_slot(self, **kwargs: Any) -> StageReceipt:
        self.calls.append((GOOGLE_PROJECT_BINDING, kwargs))
        return StageReceipt(GOOGLE_PROJECT_BINDING, "completed", True)


class AnalyticsBinder:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]):
        self.calls = calls

    def ensure_fixed_link_slot(self, **kwargs: Any) -> StageReceipt:
        self.calls.append((ANALYTICS_HUB_LINK_CREATE, kwargs))
        return StageReceipt(ANALYTICS_HUB_LINK_CREATE, "completed", True)


class FirstAccessRunner:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]):
        self.calls = calls

    def run_fixed_first_access(self, **kwargs: Any) -> StageReceipt:
        self.calls.append((READ_ONLY_PRIVATE_BIGQUERY, kwargs))
        return StageReceipt(READ_ONLY_PRIVATE_BIGQUERY, "completed", False)


def artifact_receipt() -> RuntimeArtifactReceipt:
    return RuntimeArtifactReceipt(
        source_sha="1" * 40,
        closure_sha256="a" * 64,
        artifact_sha256="b" * 64,
        artifact_size_bytes=1024,
        artifact_format=ARTIFACT_FORMAT,
        target_os=TARGET_OS,
        target_architecture=TARGET_ARCH,
        target_python_version=TARGET_PYTHON_VERSION,
        target_python_abi=TARGET_PYTHON_ABI,
        target_platform=TARGET_PIP_PLATFORM,
    )


def capabilities(
    calls: list[tuple[str, dict[str, Any]]],
    *,
    fail_application: bool = False,
) -> trusted.TrustedCapabilitySet:
    return trusted.TrustedCapabilitySet(
        application_stager=ApplicationStager(calls, fail=fail_application),
        runtime_receipts=ReceiptProvider(artifact_receipt(), calls),
        google_auth=AuthBinder(calls),
        google_project=ProjectBinder(calls),
        analytics_hub=AnalyticsBinder(calls),
        first_access=FirstAccessRunner(calls),
    )


class WeatherNextPrivateTrustedBackendTests(unittest.TestCase):
    def test_contract_json_matches_fixed_source_surface(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        source = trusted.trusted_backend_source_contract()
        self.assertEqual(contract["schema"], "rozkalns-weather.weathernext-private-trusted-backend-source.v1")
        self.assertEqual(contract["operation_id"], source["operation_id"])
        self.assertEqual(contract["bridge_operation_id"], source["bridge_operation_id"])
        self.assertEqual(contract["host_capability_id"], source["host_capability_id"])
        self.assertEqual(contract["target_alias"], "rpi5")
        self.assertEqual(contract["request_authority"], ["authorization_issue_number"])
        self.assertEqual(contract["authorization_class"], "STRICT")
        self.assertEqual(contract["status"], trusted.SOURCE_STATUS)
        self.assertFalse(contract["execution_enabled"])
        self.assertFalse(contract["ordinary_live_all_eligible"])
        self.assertTrue(contract["host_capability_install_required"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertEqual(contract["first_access"]["gate_issue"], 122)
        self.assertEqual(contract["first_access"]["entrypoint"], trusted.FIRST_ACCESS_ENTRYPOINT)
        self.assertEqual(contract["first_access"]["location_id"], "station_10416")
        self.assertEqual(contract["first_access"]["forecast_hours"], 6)
        self.assertTrue(contract["first_access"]["dry_run_required"])
        self.assertFalse(contract["first_access"]["home_scope_enabled"])
        self.assertFalse(contract["first_access"]["sqlite_write_enabled"])
        self.assertTrue(all(value is False for value in contract["caller_controls"].values()))

    def test_revalidator_derives_existing_bridge_envelope_from_canonical_facts(self) -> None:
        provider = FactsProvider(canonical_facts())
        revalidator = trusted.CanonicalWeatherNextPrivateRevalidator(provider)
        envelope = revalidator.prepare_private_execution(900)
        self.assertEqual(provider.calls, [900])
        self.assertEqual(envelope.authorization_issue_number, 900)
        self.assertEqual(envelope.rpi5_main_source_sha, "1" * 40)
        self.assertEqual(envelope.weather_source_sha, "2" * 40)
        self.assertFalse(envelope.baseline.application_staged)
        self.assertFalse(envelope.baseline.runtime_present)
        self.assertFalse(envelope.baseline.auth_binding_present)
        self.assertFalse(envelope.baseline.project_binding_present)
        self.assertFalse(envelope.baseline.linked_dataset_present)

    def test_revalidator_fails_closed_on_identity_source_ci_or_target_drift(self) -> None:
        invalid = (
            canonical_facts(authorization_issue_number=901),
            canonical_facts(owner_authorized=False),
            canonical_facts(authorization_operation_id="other.operation"),
            canonical_facts(authorization_contract_id="other.contract"),
            canonical_facts(rpi5_main_source_sha="bad"),
            canonical_facts(rpi5_main_ci_success=False),
            canonical_facts(weather_source_sha="bad"),
            canonical_facts(weather_ci_success=False),
            canonical_facts(target_alias="other"),
        )
        for facts in invalid:
            with self.subTest(facts=facts):
                with self.assertRaises(trusted.WeatherNextPrivateTrustedBackendError):
                    trusted.CanonicalWeatherNextPrivateRevalidator(
                        FactsProvider(facts)
                    ).prepare_private_execution(900)

    def test_system_python_cannot_substitute_for_cp313_private_runtime(self) -> None:
        with self.assertRaisesRegex(
            trusted.WeatherNextPrivateTrustedBackendError,
            "system Python cannot substitute",
        ):
            trusted.validate_canonical_private_facts(
                canonical_facts(runtime_present=False, runtime_python_abi="cp311"),
                requested_issue_number=900,
            )
        with self.assertRaisesRegex(
            trusted.WeatherNextPrivateTrustedBackendError,
            "cp313",
        ):
            trusted.validate_canonical_private_facts(
                canonical_facts(runtime_present=True, runtime_python_abi="cp311"),
                requested_issue_number=900,
            )

    def test_auth_project_and_link_mismatch_fail_independently(self) -> None:
        for key in ("auth_binding_state", "project_binding_state", "linked_dataset_state"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(
                    trusted.WeatherNextPrivateTrustedBackendError,
                    "mismatch",
                ):
                    trusted.validate_canonical_private_facts(
                        canonical_facts(**{key: "mismatch"}),
                        requested_issue_number=900,
                    )

    def test_sanitized_fact_and_readiness_schemas_exclude_private_identifiers(self) -> None:
        fact_names = {field.name for field in fields(trusted.CanonicalPrivateFacts)}
        readiness = trusted.validate_canonical_private_facts(
            canonical_facts(),
            requested_issue_number=900,
        )
        forbidden = {
            "account_email",
            "project_id",
            "dataset_id",
            "credential_material",
            "credential_path",
            "query",
            "sql",
            "home_lat",
            "home_lon",
            "raw_provider_value",
        }
        self.assertTrue(forbidden.isdisjoint(fact_names))
        self.assertTrue(forbidden.isdisjoint(readiness))
        self.assertEqual(tuple(readiness), trusted.SANITIZED_READINESS_KEYS)

    def test_trusted_entrypoint_exposes_only_authorization_issue_identity(self) -> None:
        parameters = tuple(inspect.signature(trusted.TrustedPrivateHostEntrypoint.dispatch).parameters)
        self.assertEqual(parameters, ("self", "authorization_issue_number"))

    @patch(
        "deploy_executor.weather_private_bigquery_trusted_backend.materialize_reviewed_runtime",
        return_value={"status": "fixture"},
    )
    def test_fixed_adapters_reuse_reviewed_materializer_and_first_access_contract(
        self,
        materialize_mock: Any,
    ) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        provider = FactsProvider(canonical_facts())
        consumer = Consumer()
        entrypoint = trusted.TrustedPrivateHostEntrypoint(
            canonical_revalidator=trusted.CanonicalWeatherNextPrivateRevalidator(provider),
            authorization_consumer=consumer,
            backend=trusted.TrustedWeatherNextPrivateBackend(capabilities(calls)),
        )
        result = entrypoint.dispatch(900)
        self.assertEqual(consumer.calls, [(900, PRIVATE_APPLICATION_STAGING)])
        materialize_mock.assert_called_once()
        args, kwargs = materialize_mock.call_args
        self.assertEqual(args[0], CONTRACT_ID)
        self.assertEqual(kwargs["expected_source_sha"], "1" * 40)
        called_stages = [name for name, _ in calls if name != "runtime_receipt"]
        self.assertEqual(
            called_stages,
            [
                PRIVATE_APPLICATION_STAGING,
                GOOGLE_AUTH_BINDING,
                GOOGLE_PROJECT_BINDING,
                ANALYTICS_HUB_LINK_CREATE,
                READ_ONLY_PRIVATE_BIGQUERY,
            ],
        )
        app_kwargs = calls[0][1]
        self.assertEqual(app_kwargs["stage_id"], trusted.APPLICATION_STAGE_ID)
        self.assertEqual(app_kwargs["stage_root"], trusted.APPLICATION_STAGE_ROOT)
        first_access_kwargs = calls[-1][1]
        self.assertEqual(first_access_kwargs["entrypoint"], trusted.FIRST_ACCESS_ENTRYPOINT)
        self.assertEqual(first_access_kwargs["scope"].location_id, "station_10416")
        self.assertEqual(first_access_kwargs["scope"].forecast_hours, 6)
        self.assertTrue(first_access_kwargs["scope"].dry_run_required)
        self.assertFalse(first_access_kwargs["scope"].home_scope_enabled)
        self.assertFalse(first_access_kwargs["scope"].sqlite_write_enabled)
        self.assertFalse(result["sqlite_write_performed"])

    @patch(
        "deploy_executor.weather_private_bigquery_trusted_backend.materialize_reviewed_runtime",
        return_value={"status": "fixture"},
    )
    def test_stage_failure_prevents_all_later_capabilities_without_retry(
        self,
        materialize_mock: Any,
    ) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        consumer = Consumer()
        entrypoint = trusted.TrustedPrivateHostEntrypoint(
            canonical_revalidator=trusted.CanonicalWeatherNextPrivateRevalidator(
                FactsProvider(canonical_facts())
            ),
            authorization_consumer=consumer,
            backend=trusted.TrustedWeatherNextPrivateBackend(
                capabilities(calls, fail_application=True)
            ),
        )
        with self.assertRaises(trusted.WeatherNextPrivateTrustedBackendError):
            entrypoint.dispatch(900)
        materialize_mock.assert_not_called()
        self.assertEqual([name for name, _ in calls], [PRIVATE_APPLICATION_STAGING])
        self.assertEqual(len(consumer.calls), 1)

    def test_source_has_no_generic_execution_secret_or_query_surface(self) -> None:
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_trusted_backend.py"
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
            "SELECT ",
            "query_text",
            "project_id",
            "dataset_id",
            "account_email",
            "credential_path",
        ):
            self.assertNotIn(token, source)
        readiness = trusted.trusted_backend_source_contract()
        self.assertFalse(readiness["host_capability_installed"])
        self.assertFalse(readiness["external_entrypoint_enabled"])
        self.assertFalse(readiness["global_executor_execution_enabled"])
        self.assertFalse(readiness["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
