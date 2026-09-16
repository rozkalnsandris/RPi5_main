from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_host_runtime as host
from deploy_executor import weather_private_bigquery_host_bindings as bindings
from deploy_executor.weather_private_bigquery_contract import CONTRACT_ID, READ_ONLY_PRIVATE_BIGQUERY
from deploy_executor.weather_private_bigquery_execution_bridge import BRIDGE_OPERATION_ID, StageReceipt
from deploy_executor.weather_private_bigquery_runtime_materialization import (
    ARTIFACT_FORMAT,
    TARGET_ARCH,
    TARGET_OS,
    TARGET_PIP_PLATFORM,
    TARGET_PYTHON_ABI,
    TARGET_PYTHON_VERSION,
    RuntimeArtifactReceipt,
)

CONTRACT_PATH = ROOT / "ops/deploy/weather-private-bigquery-host-runtime.json"
CLI_PATH = ROOT / "ops/bin/rpi5-weathernext-private-host"


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
        )
        values.update(overrides)
        self.value = host.OwnerAuthorizationEvidence(**values)

    def load_owner_authorization(self, authorization_issue_number: int) -> host.OwnerAuthorizationEvidence:
        return self.value


class Sources:
    def __init__(self, *, rpi_sha: str = "1" * 40, weather_sha: str = "2" * 40, ci: bool = True):
        self.rpi_sha = rpi_sha
        self.weather_sha = weather_sha
        self.ci = ci

    def load_exact_source(self, repository: str, repository_id: int) -> host.ExactSourceEvidence:
        expected_id = {
            host.RPI5_MAIN_REPOSITORY: host.RPI5_MAIN_REPOSITORY_ID,
            host.WEATHER_REPOSITORY: host.WEATHER_REPOSITORY_ID,
        }[repository]
        if repository_id != expected_id:
            raise AssertionError("fixture repository identity mismatch")
        sha = self.rpi_sha if repository == host.RPI5_MAIN_REPOSITORY else self.weather_sha
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
            runtime_python_abi=TARGET_PYTHON_ABI,
            auth_binding_state="ready",
            project_binding_state="ready",
            linked_dataset_state="ready",
            read_only_first_access_authorized=False,
            read_only_first_access_executed=False,
        )
        values.update(overrides)
        self.value = host.SanitizedHostEvidence(**values)

    def load_sanitized_host_evidence(self) -> host.SanitizedHostEvidence:
        return self.value


class Consumer:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    def consume_once(self, authorization_issue_number: int, *, first_stage: str) -> None:
        self.calls.append((authorization_issue_number, first_stage))


class RuntimeBindings:
    def __init__(self):
        self.calls: list[tuple[str, Any]] = []

    def stage_exact_weather_application(self, weather_source_sha: str) -> StageReceipt:
        self.calls.append(("stage", weather_source_sha))
        return StageReceipt("weathernext_private_application_staging", "completed", True)

    def load_runtime_artifact_receipt(self, rpi5_main_source_sha: str) -> RuntimeArtifactReceipt:
        self.calls.append(("runtime_receipt", rpi5_main_source_sha))
        return RuntimeArtifactReceipt(
            source_sha=rpi5_main_source_sha,
            closure_sha256="a" * 64,
            artifact_sha256="b" * 64,
            artifact_size_bytes=123,
            artifact_format=ARTIFACT_FORMAT,
            target_os=TARGET_OS,
            target_architecture=TARGET_ARCH,
            target_python_version=TARGET_PYTHON_VERSION,
            target_python_abi=TARGET_PYTHON_ABI,
            target_platform=TARGET_PIP_PLATFORM,
        )

    def bind_google_auth_slot(self) -> StageReceipt:
        self.calls.append(("auth", None))
        return StageReceipt("google_auth_binding", "completed", True)

    def bind_google_project_slot(self) -> StageReceipt:
        self.calls.append(("project", None))
        return StageReceipt("google_project_binding", "completed", True)

    def ensure_analytics_hub_link_slot(self) -> StageReceipt:
        self.calls.append(("link", None))
        return StageReceipt("analytics_hub_link_create", "completed", True)

    def run_read_only_first_access(self, weather_source_sha: str, scope: Any) -> StageReceipt:
        self.calls.append(("first_access", (weather_source_sha, scope)))
        return StageReceipt(READ_ONLY_PRIVATE_BIGQUERY, "completed", False)


class HostRuntimeTests(unittest.TestCase):
    def facts(
        self,
        *,
        authorization: Any | None = None,
        sources: Any | None = None,
        state: Any | None = None,
    ) -> host.ConcreteCanonicalPrivateFactsProvider:
        return host.ConcreteCanonicalPrivateFactsProvider(
            authorization=authorization or Authorization(),
            sources=sources or Sources(),
            host=state or HostState(),
        )

    def test_canonical_facts_are_exact_and_sanitized(self) -> None:
        facts = self.facts().load_private_facts(1220)
        self.assertEqual(facts.authorization_operation_id, BRIDGE_OPERATION_ID)
        self.assertEqual(facts.authorization_contract_id, CONTRACT_ID)
        self.assertEqual(facts.rpi5_main_source_sha, "1" * 40)
        self.assertEqual(facts.weather_source_sha, "2" * 40)
        self.assertTrue(facts.host_capability_installed)
        self.assertEqual(facts.runtime_python_abi, "cp313")

    def test_authorization_operation_contract_target_and_source_drift_fail_closed(self) -> None:
        bad = [
            Authorization(operation_id="other"),
            Authorization(contract_id="other"),
            Authorization(target_alias="other"),
            Authorization(rpi5_main_source_sha="3" * 40),
            Authorization(weather_source_sha="4" * 40),
        ]
        for authorization in bad:
            with self.subTest(authorization=authorization.value):
                with self.assertRaises(host.WeatherNextPrivateHostRuntimeError):
                    self.facts(authorization=authorization).load_private_facts(1220)

    def test_source_ci_runtime_abi_and_installed_identity_drift_fail_closed(self) -> None:
        cases = [
            dict(sources=Sources(ci=False)),
            dict(state=HostState(runtime_python_abi="cp311")),
            dict(state=HostState(host_capability_source_sha="3" * 40)),
            dict(state=HostState(application_source_sha="4" * 40)),
            dict(state=HostState(runtime_source_sha="5" * 40)),
            dict(state=HostState(auth_binding_state="mismatch")),
            dict(state=HostState(project_binding_state="mismatch")),
            dict(state=HostState(linked_dataset_state="mismatch")),
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(host.WeatherNextPrivateHostRuntimeError):
                    self.facts(**kwargs).load_private_facts(1220)

    def test_absent_runtime_cannot_claim_system_python_311(self) -> None:
        with self.assertRaisesRegex(host.WeatherNextPrivateHostRuntimeError, "system Python"):
            self.facts(state=HostState(runtime_present=False, runtime_source_sha=None,
                                       runtime_python_abi="cp311")).load_private_facts(1220)

    def test_fixed_adapters_do_not_accept_private_selectors_and_slots_are_distinct(self) -> None:
        runtime_bindings = RuntimeBindings()
        capabilities = host.build_trusted_capabilities(runtime_bindings)
        self.assertEqual(
            tuple(inspect.signature(capabilities.google_auth.bind_fixed_auth_slot).parameters),
            ("slot_id", "mechanism"),
        )
        self.assertEqual(
            tuple(inspect.signature(capabilities.google_project.bind_fixed_project_slot).parameters),
            ("slot_id",),
        )
        self.assertEqual(
            tuple(inspect.signature(capabilities.analytics_hub.ensure_fixed_link_slot).parameters),
            ("slot_id",),
        )
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        slots = {
            contract["runtime_composition"]["fixed_google_auth_slot"],
            contract["runtime_composition"]["fixed_google_project_slot"],
            contract["runtime_composition"]["fixed_analytics_hub_link_slot"],
        }
        self.assertEqual(len(slots), 3)

    def test_runtime_composition_caller_controls_only_issue_identity(self) -> None:
        consumer = Consumer()
        runtime_bindings = RuntimeBindings()
        runtime = host.build_runtime_composition(
            authorization=Authorization(),
            sources=Sources(),
            host=HostState(),
            authorization_consumer=consumer,
            bindings=runtime_bindings,
        )
        receipt = runtime.execute(1220)
        self.assertEqual(consumer.calls, [(1220, READ_ONLY_PRIVATE_BIGQUERY)])
        self.assertEqual([name for name, _ in runtime_bindings.calls], ["first_access"])
        self.assertEqual(receipt["status"], "private_execution_sequence_completed")
        self.assertFalse(receipt["sqlite_write_performed"])
        self.assertFalse(receipt["home_scope_enabled"])

    def test_host_install_plan_is_fixed_bounded_and_conflict_fails(self) -> None:
        plan = host.build_host_install_plan(
            host.HostInstallObservation("ABSENT", "ABSENT", "ABSENT"),
            exact_rpi5_main_sha="1" * 40,
        )
        self.assertEqual(plan.decision, "INSTALL_REQUIRED")
        self.assertEqual(plan.mutations_required, tuple(item[0] for item in host.INSTALL_MUTATION_BUDGET))
        self.assertEqual(plan.rollback_policy, "NONE")
        self.assertEqual(plan.operator_mode, 0o755)
        self.assertEqual(plan.activation_marker_mode, 0o644)
        self.assertEqual((plan.owner_uid, plan.owner_gid), (0, 0))
        self.assertFalse(plan.automatic_retry)
        with self.assertRaises(host.WeatherNextPrivateHostRuntimeError):
            host.build_host_install_plan(
                host.HostInstallObservation("CONFLICT", "ABSENT", "ABSENT"),
                exact_rpi5_main_sha="1" * 40,
            )

    def test_contract_and_source_readiness_remain_execution_disabled(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        ready = host.source_readiness()
        self.assertEqual(value["schema"], ready["schema"])
        self.assertEqual(value["host_capability_id"], ready["host_capability_id"])
        self.assertEqual(
            value["install_mutation_budget"],
            [{"category": c, "max_operations": n} for c, n in host.INSTALL_MUTATION_BUDGET],
        )
        self.assertFalse(value["execution_enabled"])
        self.assertFalse(value["runtime_activation_enabled"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertEqual(value["install_package"]["operator_mode"], "0755")
        self.assertEqual(value["install_package"]["activation_marker_mode"], "0644")
        self.assertFalse(value["protected_runtime_binding_policy"]["ambient_adc_allowed"])
        self.assertTrue(value["protected_runtime_binding_policy"]["credential_reference_is_basename_only"])
        self.assertFalse(value["production_mutation_started"])
        self.assertFalse(value["shared_registry_modified"])
        self.assertFalse(ready["host_capability_installed"])
        self.assertFalse(ready["runtime_activation_enabled"])

    def test_cli_has_only_issue_number_caller_surface(self) -> None:
        source = CLI_PATH.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--issue-number"', source)
        for forbidden in (
            "--command", "--path", "--argv", "--environment", "--project",
            "--dataset", "--credential", "--account", "--query", "--sql",
            "--source-sha", "--target",
        ):
            self.assertNotIn(forbidden, source)

    def test_source_forbids_generic_execution_and_ambient_credential_substitution(self) -> None:
        runtime_source = Path(host.__file__).read_text(encoding="utf-8")
        bindings_source = Path(bindings.__file__).read_text(encoding="utf-8")
        combined = runtime_source + "\n" + bindings_source
        for forbidden in (
            "shell=True",
            "os.environ",
            "sudo ",
            "HOME_LAT",
            "HOME_LON",
            "SELECT *",
            "service_account_email",
            "private_key_id",
            "google.auth.default",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertNotIn("ops/deploy/executor-operations.json", combined)

    def test_private_values_are_not_part_of_sanitized_host_evidence(self) -> None:
        fields = set(host.SanitizedHostEvidence.__dataclass_fields__)
        for forbidden in (
            "project", "project_id", "dataset", "dataset_id", "credential",
            "credential_path", "account", "sql", "query",
        ):
            self.assertNotIn(forbidden, fields)


if __name__ == "__main__":
    unittest.main()
