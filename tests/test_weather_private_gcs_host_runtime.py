from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_gcs_host_bindings as bindings
from deploy_executor import weather_private_gcs_host_runtime as host
from deploy_executor.weather_private_gcs_contract import (
    CONTRACT_ID,
    READ_ONLY_PRIVATE_GCS,
)
from deploy_executor.weather_private_gcs_execution_bridge import (
    BRIDGE_OPERATION_ID,
    GCSStageReceipt,
)
from deploy_executor.weather_private_gcs_runtime_materialization import (
    RUNTIME_BASE,
    RUNTIME_MARKER_NAME,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
)

CONTRACT_PATH = ROOT / "ops/deploy/weather-private-gcs-host-runtime.json"
CLI_PATH = ROOT / "ops/bin/rpi5-weathernext-private-gcs-host"
BINDINGS_PATH = (
    ROOT / "ops/lib/deploy_executor/weather_private_gcs_host_bindings.py"
)

INIT = datetime(2026, 10, 1, 23, tzinfo=timezone.utc)


class Authorization:
    def __init__(self, **overrides: Any):
        values = dict(
            authorization_issue_number=1220,
            owner_authorized=True,
            operation_id=BRIDGE_OPERATION_ID,
            contract_id=CONTRACT_ID,
            target_alias="rpi5",
            rpi5_main_source_sha="1" * 40,
            weather_source_sha="2" * 40,
            selected_init_utc=INIT,
        )
        values.update(overrides)
        self.value = host.OwnerAuthorizationEvidence(**values)

    def load_owner_authorization(
        self, authorization_issue_number: int
    ) -> host.OwnerAuthorizationEvidence:
        return self.value


class Sources:
    def __init__(
        self,
        *,
        rpi_sha: str = "1" * 40,
        weather_sha: str = "2" * 40,
        ci: bool = True,
    ):
        self.rpi_sha = rpi_sha
        self.weather_sha = weather_sha
        self.ci = ci

    def load_exact_source(
        self, repository: str, repository_id: int
    ) -> host.ExactSourceEvidence:
        expected_id = {
            host.RPI5_MAIN_REPOSITORY: host.RPI5_MAIN_REPOSITORY_ID,
            host.WEATHER_REPOSITORY: host.WEATHER_REPOSITORY_ID,
        }[repository]
        if repository_id != expected_id:
            raise AssertionError("fixture repository identity mismatch")
        sha = (
            self.rpi_sha
            if repository == host.RPI5_MAIN_REPOSITORY
            else self.weather_sha
        )
        return host.ExactSourceEvidence(
            repository=repository,
            repository_id=repository_id,
            source_sha=sha,
            current_main_sha=sha,
            merged_reachable=True,
            required_ci_success=self.ci,
        )


class HostState:
    def __init__(self, **overrides: Any):
        values = dict(
            host_capability_installed=True,
            host_capability_source_sha="1" * 40,
            application_staged=True,
            application_source_sha="2" * 40,
            runtime_present=True,
            runtime_source_sha="1" * 40,
            runtime_closure_sha256=host.EXPECTED_GCS_RUNTIME_CLOSURE_SHA256,
            runtime_python_abi=TARGET_PYTHON_ABI,
            runtime_target_platform=TARGET_PIP_PLATFORM,
            host_glibc_compatible=True,
            auth_binding_state="ready",
            read_only_first_access_authorized=False,
            read_only_first_access_executed=False,
        )
        values.update(overrides)
        self.value = host.SanitizedGCSHostEvidence(**values)

    def load_sanitized_host_evidence(self) -> host.SanitizedGCSHostEvidence:
        return self.value


class Consumer:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def consume_once(
        self, authorization_issue_number: int, *, first_stage: str
    ) -> None:
        self.calls.append((authorization_issue_number, first_stage))


class RuntimeBindings:
    def __init__(self, consumer: Consumer):
        self.consumer = consumer
        self.calls: list[tuple[str, Any]] = []

    def stage_exact_weather_application(
        self, weather_source_sha: str
    ) -> GCSStageReceipt:
        raise AssertionError("execution-ready GCS composition must not stage application")

    def materialize_exact_gcs_runtime(
        self, rpi5_main_source_sha: str
    ) -> GCSStageReceipt:
        raise AssertionError("execution-ready GCS composition must not materialize runtime")

    def bind_google_auth_slot(self) -> GCSStageReceipt:
        raise AssertionError("execution-ready GCS composition must not bind credentials")

    def run_read_only_first_access(
        self, weather_source_sha: str, scope: Any
    ) -> GCSStageReceipt:
        if self.consumer.calls != [(1220, READ_ONLY_PRIVATE_GCS)]:
            raise AssertionError(
                "durable authorization must be consumed before protected GCS access"
            )
        self.calls.append(("first_access", (weather_source_sha, scope)))
        return GCSStageReceipt(
            stage=READ_ONLY_PRIVATE_GCS,
            status="completed",
            mutation_performed=False,
        )


class GCSHostRuntimeTests(unittest.TestCase):
    def facts(
        self,
        *,
        authorization: Any | None = None,
        sources: Any | None = None,
        state: Any | None = None,
    ) -> host.ConcreteCanonicalGCSFactsProvider:
        return host.ConcreteCanonicalGCSFactsProvider(
            authorization=authorization or Authorization(),
            sources=sources or Sources(),
            host=state or HostState(),
        )

    def test_canonical_facts_are_exact_and_gcs_only(self) -> None:
        facts = self.facts().load_gcs_facts(1220)
        self.assertEqual(facts.authorization_operation_id, BRIDGE_OPERATION_ID)
        self.assertEqual(facts.authorization_contract_id, CONTRACT_ID)
        self.assertEqual(facts.rpi5_main_source_sha, "1" * 40)
        self.assertEqual(facts.weather_source_sha, "2" * 40)
        self.assertEqual(facts.selected_init_utc, INIT)
        self.assertTrue(facts.host_capability_installed)
        self.assertTrue(facts.gcs_runtime_present)
        self.assertEqual(facts.auth_binding_state, "ready")

    def test_authority_source_runtime_and_glibc_drift_fail_closed(self) -> None:
        bad = [
            dict(authorization=Authorization(operation_id="other")),
            dict(authorization=Authorization(contract_id="other")),
            dict(authorization=Authorization(target_alias="other")),
            dict(sources=Sources(rpi_sha="3" * 40)),
            dict(sources=Sources(weather_sha="4" * 40)),
            dict(sources=Sources(ci=False)),
            dict(state=HostState(host_capability_source_sha="3" * 40)),
            dict(state=HostState(application_source_sha="4" * 40)),
            dict(state=HostState(runtime_source_sha="5" * 40)),
            dict(state=HostState(runtime_closure_sha256="a" * 64)),
            dict(state=HostState(runtime_python_abi="cp312")),
            dict(state=HostState(runtime_target_platform="manylinux2014_aarch64")),
            dict(state=HostState(host_glibc_compatible=False)),
            dict(state=HostState(auth_binding_state="mismatch")),
        ]
        for values in bad:
            with self.subTest(values=values):
                with self.assertRaises(
                    host.WeatherNextPrivateGCSHostRuntimeError
                ):
                    self.facts(**values).load_gcs_facts(1220)

    def test_execution_ready_path_consumes_before_first_access(self) -> None:
        consumer = Consumer()
        runtime_bindings = RuntimeBindings(consumer)
        runtime = host.build_runtime_composition(
            authorization=Authorization(),
            sources=Sources(),
            host=HostState(),
            authorization_consumer=consumer,
            bindings=runtime_bindings,
        )
        receipt = runtime.execute(1220)
        self.assertEqual(consumer.calls, [(1220, READ_ONLY_PRIVATE_GCS)])
        self.assertEqual(len(runtime_bindings.calls), 1)
        self.assertEqual(runtime_bindings.calls[0][0], "first_access")
        self.assertEqual(
            receipt["status"],
            "private_gcs_execution_sequence_completed",
        )

    def test_host_install_plan_is_separate_from_bigquery_paths(self) -> None:
        plan = host.build_host_install_plan(
            host.HostInstallObservation(
                trusted_checkout_state="ABSENT",
                operator_state="ABSENT",
                activation_marker_state="ABSENT",
            ),
            exact_rpi5_main_sha="1" * 40,
        )
        self.assertEqual(plan.decision, "INSTALL_REQUIRED")
        self.assertIn("private-gcs", plan.trusted_checkout)
        self.assertIn("private-gcs", plan.operator_destination)
        self.assertIn("private-gcs-host", plan.activation_marker)
        self.assertTrue(
            all(
                "private-gcs-host" in row["category"]
                for row in plan.mutation_budget
            )
        )

    def test_source_contract_and_manifest_remain_execution_disabled(self) -> None:
        ready = host.source_readiness()
        self.assertEqual(ready["implementation_issue"], 835)
        self.assertEqual(
            ready["expected_runtime_closure_sha256"],
            host.EXPECTED_GCS_RUNTIME_CLOSURE_SHA256,
        )
        for key in (
            "host_capability_installed",
            "runtime_activation_enabled",
            "global_executor_execution_enabled",
            "credential_binding_execution_enabled",
            "read_only_gcs_execution_enabled",
            "project_binding_execution_enabled",
            "analytics_hub_execution_enabled",
            "bigquery_execution_enabled",
            "sqlite_write_execution_enabled",
            "source_merge_authorizes_live",
            "production_mutation_started",
        ):
            self.assertIs(ready[key], False)

        manifest = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["implementation_issue"], 835)
        self.assertEqual(
            manifest["runtime_identity"]["weather_source_sha"],
            "1fc7ea70efde88cb826c2e4a0baf26925078375c",
        )
        self.assertEqual(
            manifest["runtime_identity"]["runtime_closure_sha256"],
            host.EXPECTED_GCS_RUNTIME_CLOSURE_SHA256,
        )
        self.assertFalse(manifest["shared_bigquery_runtime_modified"])
        self.assertFalse(manifest["source_merge_authorizes_live"])
        self.assertEqual(
            manifest["next_gate_after_merge"],
            "COMPOSITE_STRICT_LIVE_GCS_PREREQUISITE_ROLLOUT",
        )

    def test_sanitized_observer_exposes_only_reviewed_identity(self) -> None:
        activation = {
            "schema": host.ACTIVATION_MARKER_SCHEMA,
            "host_capability_id": "rpi5.weathernext-private-gcs-backend.v1",
            "operation_id": host.INSTALL_OPERATION_ID,
            "target_alias": "rpi5",
            "rpi5_main_source_sha": "1" * 40,
            "trusted_checkout": str(host.TRUSTED_CHECKOUT),
            "operator_destination": str(host.OPERATOR_DESTINATION),
            "execution_enabled": True,
        }
        application = {
            "schema": "rozkalns-weather.weathernext-private-application-stage.v1",
            "source_repository": host.WEATHER_REPOSITORY,
            "source_sha": "2" * 40,
            "staged": True,
        }
        runtime = {
            "schema": "rozkalns-weather.weathernext-private-gcs-runtime-installed.v1",
            "operation_id": "rozkalns-weather.weathernext-private-gcs-runtime-materialization.v1",
            "source_sha": "1" * 40,
            "closure_sha256": host.EXPECTED_GCS_RUNTIME_CLOSURE_SHA256,
            "artifact_sha256": "a" * 64,
            "target_python_abi": TARGET_PYTHON_ABI,
            "target_platform": TARGET_PIP_PLATFORM,
            "package_count": 25,
            "credential_binding": False,
            "google_gcs_access": False,
            "project_binding": False,
            "analytics_hub_link": False,
            "bigquery_access": False,
            "sqlite_write": False,
        }
        auth = {
            "schema": bindings.GCS_AUTH_READY_SCHEMA,
            "slot_id": "weathernext-private-google-auth-v1",
            "provider_class": bindings.GCS_AUTH_PROVIDER_CLASS,
            "ready": True,
        }
        values = {
            host.ACTIVATION_MARKER: activation,
            bindings.APPLICATION_MARKER: application,
            Path(RUNTIME_BASE) / RUNTIME_MARKER_NAME: runtime,
            bindings.AUTH_READY_MARKER: auth,
        }

        def reader(
            path: Path,
            *,
            required: bool = True,
            mode: int | None = None,
        ) -> Any:
            return values.get(path)

        observer = bindings.PosixSanitizedGCSHostEvidenceProvider(
            json_reader=reader,
            libc_provider=lambda: ("glibc", "2.36"),
        )
        evidence = observer.load_sanitized_host_evidence()
        self.assertTrue(evidence.host_capability_installed)
        self.assertTrue(evidence.application_staged)
        self.assertTrue(evidence.runtime_present)
        self.assertTrue(evidence.host_glibc_compatible)
        self.assertEqual(evidence.auth_binding_state, "ready")
        fields = set(host.SanitizedGCSHostEvidence.__dataclass_fields__)
        self.assertEqual(
            fields,
            {
                "host_capability_installed",
                "host_capability_source_sha",
                "application_staged",
                "application_source_sha",
                "runtime_present",
                "runtime_source_sha",
                "runtime_closure_sha256",
                "runtime_python_abi",
                "runtime_target_platform",
                "host_glibc_compatible",
                "auth_binding_state",
                "read_only_first_access_authorized",
                "read_only_first_access_executed",
            },
        )

    def test_glibc_floor_is_exactly_2_28(self) -> None:
        self.assertFalse(bindings._glibc_compatible("glibc", "2.27"))
        self.assertTrue(bindings._glibc_compatible("glibc", "2.28"))
        self.assertTrue(bindings._glibc_compatible("glibc", "2.36"))
        self.assertFalse(bindings._glibc_compatible("musl", "1.2"))

    def test_gcs_source_excludes_bigquery_project_and_ambient_adc(self) -> None:
        source = BINDINGS_PATH.read_text(encoding="utf-8")
        for token in (
            "google.cloud.bigquery",
            "google.auth.default",
            "PROJECT_READY_MARKER",
            "LINK_READY_MARKER",
            "analytics_hub_link_slot",
            "bind_google_project_slot",
        ):
            self.assertNotIn(token, source)
        self.assertIn("GoogleCredentialProvider", source)
        self.assertIn("load_credentials_from_file", source)
        self.assertIn(
            "GCS auth binding requires its separate protected LIVE gate",
            source,
        )

    def test_cli_is_gcs_specific_and_has_no_generic_command_surface(self) -> None:
        source = CLI_PATH.read_text(encoding="utf-8")
        self.assertIn("weather_private_gcs_host_bindings", source)
        self.assertNotIn("weather_private_bigquery_host_bindings", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertIn("--issue-number", source)


if __name__ == "__main__":
    unittest.main()
