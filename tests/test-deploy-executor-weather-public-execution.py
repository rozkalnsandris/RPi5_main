from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.weather_public_runtime_adapter import BASELINE_RESOLVER_ID, OPERATION_ID, SOURCE_REPOSITORY, TARGET_ALIAS
from deploy_executor.weather_public_runtime_candidate_materializer import (
    FETCH_IDENTITY,
    PUBLIC_REPOSITORY_URL,
    WeatherCandidateMaterializerError,
    build_candidate_materialization_plan,
    source_readiness as candidate_source_readiness,
)
from deploy_executor.weather_public_runtime_execution import (
    ACTIVATION_FILE,
    ACTIVATION_SCHEMA,
    CANDIDATE_ROOT,
    HELPER_EXECUTABLE,
    RELEASE_ROOT,
    RESULT,
    WeatherExecutionPlanError,
    build_weather_executable_plan,
    source_readiness as execution_source_readiness,
    validate_weather_executable_plan,
)
from deploy_executor.weather_public_runtime_helper_launch import (
    HelperProcessResult,
    WeatherHelperLaunchError,
    WeatherOneShotStageLauncher,
    source_readiness as launch_source_readiness,
)
from deploy_executor.weather_public_runtime_host_wiring import (
    build_weather_host_wiring_plan,
    expected_helper_bindings,
)
from deploy_executor.weather_public_runtime_preactivation import (
    ENVELOPE_SCHEMA,
    RESULT as PREACTIVATION_RESULT,
    WeatherPreactivationEnvelope,
    WeatherPreactivationStageBinding,
)
from deploy_executor.weather_public_runtime_stage_helper import (
    MODELS,
    RUN_HOURS,
    TRUTH_STATION_ID,
    WeatherStageHelperError,
    _validate_request,
    parse_activation,
)

CONTRACT = ROOT / "ops/deploy/weather-public-runtime-execution.json"
REGISTRY = ROOT / "ops/deploy/executor-operations.json"
ENTRYPOINT = ROOT / "ops/bin/rozkalns-weather-public-runtime-stage-helper"
STAGE_SOURCE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_stage_helper.py"
LAUNCH_SOURCE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_helper_launch.py"
MATERIALIZER_SOURCE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_candidate_materializer.py"
SOURCE_SHA = "a" * 40
HASH_A = "1" * 64
HASH_B = "2" * 64
HASH_C = "3" * 64


def envelope(**changes) -> WeatherPreactivationEnvelope:
    bindings = tuple(
        WeatherPreactivationStageBinding(
            item.stage_id,
            item.capability_id,
            item.mutation_class,
            item.max_operations,
            item.read_only,
        )
        for item in expected_helper_bindings()
    )
    value = WeatherPreactivationEnvelope(
        schema=ENVELOPE_SCHEMA,
        result=PREACTIVATION_RESULT,
        authorization_issue_number=9410,
        authorization_issue_id=99410,
        request_id="123e4567-e89b-42d3-a456-426614174000",
        authorization_payload_sha256=HASH_A,
        authorization_raw_body_sha256=HASH_B,
        queue_repository="rozkalnsandris/ops-workflows",
        queue_issue_number=777,
        queue_contract_sha256=HASH_C,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        target_alias=TARGET_ALIAS,
        release_operation_id=OPERATION_ID,
        release_baseline_resolver_id=BASELINE_RESOLVER_ID,
        bootstrap_baseline_token="deployment=not_deployed;source=none;volume=absent;schema=absent:none;schedule=absent;stage=not_started",
        start_date="2026-04-02",
        end_date="2026-09-07",
        recovery_decision="owner-accepted-no-prewrite-backup",
        truth_station_id=TRUTH_STATION_ID,
        forecast_models=MODELS,
        run_hours=tuple(int(hour) for hour in RUN_HOURS),
        stages=bindings,
    )
    return replace(value, **changes)


def activation_value(**changes):
    value = {
        "schema": ACTIVATION_SCHEMA,
        "enabled": True,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "source_sha": SOURCE_SHA,
        "preactivation_sha256": None,
        "start_date": "2026-04-02",
        "end_date": "2026-09-07",
        "recovery_decision": "owner-accepted-no-prewrite-backup",
        "allowed_helper_ids": [item.helper_id for item in expected_helper_bindings()],
    }
    value.update(changes)
    return value


class WeatherExecutableCapabilityTests(unittest.TestCase):
    def plan(self):
        env = envelope()
        host = build_weather_host_wiring_plan(env)
        return env, host, build_weather_executable_plan(host, env)

    def test_executable_plan_is_fixed_and_inactive(self):
        env, host, plan = self.plan()
        self.assertEqual(plan.result, RESULT)
        self.assertEqual(validate_weather_executable_plan(plan, host, env), plan)
        self.assertEqual(tuple(stage.helper_id for stage in plan.stages), tuple(item.helper_id for item in expected_helper_bindings()))
        self.assertTrue(plan.execution_capability_implemented)
        self.assertTrue(plan.installable_helper_source_present)
        self.assertEqual(plan.helper_executable, HELPER_EXECUTABLE)
        self.assertEqual(plan.activation_file, ACTIVATION_FILE)
        self.assertEqual(plan.candidate_root, RELEASE_ROOT)
        self.assertEqual(plan.release_root, RELEASE_ROOT)
        self.assertEqual(CANDIDATE_ROOT, RELEASE_ROOT)
        for flag in (
            "privileged_dispatch_enabled",
            "host_wiring_enabled",
            "helper_installation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
            "automatic_retry_cleanup_rollback",
            "generic_shell_authority",
            "caller_supplied_path_allowed",
            "caller_supplied_argv_allowed",
            "caller_supplied_environment_allowed",
        ):
            self.assertFalse(getattr(plan, flag))

    def test_canonical_arguments_carry_only_validated_evidence(self):
        _env, _host, plan = self.plan()
        for stage in plan.stages:
            self.assertEqual(stage.executable, HELPER_EXECUTABLE)
            self.assertEqual(stage.arguments[0], stage.helper_id)
            self.assertEqual(stage.arguments[1], SOURCE_SHA)
            self.assertEqual(stage.arguments[2], plan.preactivation_sha256)
            self.assertNotIn("command", stage.argument_names)
            self.assertNotIn("path", stage.argument_names)
            self.assertNotIn("environment", stage.argument_names)
        forecast = next(stage for stage in plan.stages if stage.stage_id == "bounded_deterministic_forecast_backfill")
        self.assertEqual(forecast.arguments[-2:], (",".join(MODELS), ",".join(RUN_HOURS)))
        truth = next(stage for stage in plan.stages if stage.stage_id == "bounded_dwd_truth_backfill")
        self.assertEqual(truth.arguments[-1], TRUTH_STATION_ID)

    def test_evidence_or_plan_drift_fails_closed(self):
        env, host, plan = self.plan()
        with self.assertRaisesRegex(WeatherExecutionPlanError, "drifted"):
            validate_weather_executable_plan(replace(plan, source_sha="b" * 40), host, env)
        with self.assertRaises(Exception):
            build_weather_executable_plan(host, replace(env, end_date="2026-09-06"))

    def test_activation_is_exact_root_contract_not_github_prose(self):
        _env, host, _plan = self.plan()
        value = activation_value(preactivation_sha256=host.preactivation_sha256)
        activation = parse_activation(value)
        self.assertEqual(activation.source_sha, SOURCE_SHA)
        self.assertEqual(activation.allowed_helper_ids, tuple(item.helper_id for item in expected_helper_bindings()))
        invalid = (
            {**value, "enabled": False},
            {**value, "source_sha": "not-a-sha"},
            {**value, "allowed_helper_ids": value["allowed_helper_ids"][:-1]},
            {**value, "command": "bash -c whoami"},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(WeatherStageHelperError):
                    parse_activation(candidate)

    def test_stage_helper_rejects_scope_injection(self):
        _env, host, plan = self.plan()
        activation = parse_activation(activation_value(preactivation_sha256=host.preactivation_sha256))
        stage = next(item for item in plan.stages if item.stage_id == "bounded_deterministic_forecast_backfill")
        parsed = _validate_request(stage.arguments, activation)
        self.assertEqual(parsed[0], stage.helper_id)
        with self.assertRaises(WeatherStageHelperError):
            _validate_request(stage.arguments + ("/tmp/attacker",), activation)
        with self.assertRaises(WeatherStageHelperError):
            _validate_request(("attacker.helper",) + stage.arguments[1:], activation)

    def test_candidate_materializer_is_single_release_materialization_and_nonroot(self):
        plan = build_candidate_materialization_plan(SOURCE_SHA)
        self.assertEqual(plan.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(plan.public_repository_url, PUBLIC_REPOSITORY_URL)
        self.assertEqual(plan.fetch_identity, FETCH_IDENTITY)
        self.assertEqual(plan.release_root, f"{RELEASE_ROOT}/{SOURCE_SHA}")
        self.assertEqual(plan.partial_root, f"{RELEASE_ROOT}/.{SOURCE_SHA}.release-materializer-partial")
        self.assertEqual(plan.clone_argv[:4], ("/usr/sbin/runuser", "-u", FETCH_IDENTITY, "--"))
        self.assertIn("/usr/bin/env", plan.clone_argv)
        self.assertIn("-i", plan.clone_argv)
        self.assertIn(PUBLIC_REPOSITORY_URL, plan.clone_argv)
        self.assertIn(SOURCE_SHA, plan.ancestry_argv)
        self.assertIn(SOURCE_SHA, plan.checkout_argv)
        readiness = candidate_source_readiness()
        self.assertEqual(readiness["release_root"], RELEASE_ROOT)
        self.assertEqual(readiness["filesystem_release_materializations"], 1)
        self.assertFalse(readiness["network_fetch_runs_as_root"])
        self.assertFalse(readiness["credentialed_fetch_required"])
        self.assertFalse(readiness["caller_supplied_repository_url"])
        self.assertFalse(readiness["caller_supplied_path"])
        self.assertFalse(readiness["caller_supplied_argv"])
        self.assertFalse(readiness["caller_supplied_environment"])
        self.assertEqual(readiness["atomic_publish"], "renameat2-RENAME_NOREPLACE")
        with self.assertRaises(WeatherCandidateMaterializerError):
            build_candidate_materialization_plan("../../attacker")

    def test_launcher_revalidates_and_has_no_retry(self):
        env, host, plan = self.plan()
        stage = next(item for item in plan.stages if item.stage_id == "readiness_schema_privacy")
        calls = []

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            payload = {
                "schema": "rozkalns-weather.public-runtime-helper-receipt.v1",
                "stage_id": stage.stage_id,
                "helper_id": stage.helper_id,
                "source_sha": plan.source_sha,
                "preactivation_sha256": plan.preactivation_sha256,
                "operations_performed": 0,
                "production_mutation_started": False,
            }
            return HelperProcessResult(0, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(), b"")

        launcher = WeatherOneShotStageLauncher(runner=runner)
        receipt = launcher.launch_stage(plan, host, env, stage.stage_id)
        self.assertTrue(receipt.output_validated)
        self.assertFalse(receipt.production_mutation_started)
        self.assertEqual(calls[0][0], (HELPER_EXECUTABLE,) + stage.arguments)
        with self.assertRaisesRegex(WeatherHelperLaunchError, "already consumed"):
            launcher.launch_stage(plan, host, env, stage.stage_id)
        self.assertEqual(len(calls), 1)

    def test_machine_contract_and_registry_remain_inactive(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        execution = execution_source_readiness()
        launch = launch_source_readiness()
        materializer = candidate_source_readiness()
        self.assertEqual(contract["status"], "SOURCE_IMPLEMENTED_HOST_INACTIVE")
        self.assertTrue(contract["execution_capability_implemented"])
        self.assertTrue(contract["installable_helper_source_present"])
        self.assertTrue(contract["candidate_materialization_source_present"])
        self.assertEqual(contract["release_materialization"]["release_root"], RELEASE_ROOT)
        self.assertEqual(contract["release_materialization"]["filesystem_release_materializations"], 1)
        self.assertFalse(contract["release_materialization"]["application_stage_performs_second_filesystem_copy"])
        self.assertFalse(contract["release_materialization"]["network_fetch_runs_as_root"])
        self.assertFalse(contract["release_materialization"]["credentialed_fetch_required"])
        self.assertFalse(contract["helper_process_launch_wired"])
        self.assertFalse(registry["execution_enabled"])
        self.assertFalse(execution["helper_invocation_enabled"])
        self.assertFalse(launch["helper_process_launch_wired"])
        self.assertTrue(execution["candidate_root_equals_release_root"])
        self.assertEqual(materializer["release_root"], RELEASE_ROOT)
        self.assertEqual(materializer["filesystem_release_materializations"], 1)
        self.assertTrue(ENTRYPOINT.is_file())
        self.assertTrue(MATERIALIZER_SOURCE.is_file())

    def test_process_surfaces_are_fixed_and_shell_false(self):
        launch_source = LAUNCH_SOURCE.read_text(encoding="utf-8")
        stage_source = STAGE_SOURCE.read_text(encoding="utf-8")
        materializer_source = MATERIALIZER_SOURCE.read_text(encoding="utf-8")
        entrypoint_source = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("shell=False", launch_source)
        self.assertIn("shell=False", stage_source)
        self.assertIn("ACTIVATION_FILE", stage_source)
        self.assertIn('"/usr/sbin/runuser"', materializer_source)
        self.assertIn('"/usr/bin/env"', materializer_source)
        self.assertIn('"GIT_TERMINAL_PROMPT=0"', materializer_source)
        self.assertIn("RENAME_NOREPLACE", materializer_source)
        self.assertIn("candidate != release", stage_source)
        self.assertNotIn("shutil.copytree", stage_source)
        self.assertLess(entrypoint_source.index("_validate_request(args, activation)"), entrypoint_source.index("materialize_candidate(source_sha"))
        self.assertIn("--no-optional-locks", entrypoint_source)
        for source in (launch_source, stage_source, materializer_source, entrypoint_source):
            for forbidden in ("bash -c", "sh -c", "eval(", "exec(", "os.system(", "shell=True"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)