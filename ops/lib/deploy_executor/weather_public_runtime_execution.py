from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .weather_public_runtime_adapter import OPERATION_ID, SOURCE_REPOSITORY, TARGET_ALIAS
from .weather_public_runtime_host_wiring import (
    WeatherHostHelperBinding,
    WeatherHostWiringPlan,
    expected_helper_bindings,
    validate_weather_host_wiring_plan,
)
from .weather_public_runtime_preactivation import WeatherPreactivationEnvelope

EXECUTION_PLAN_SCHEMA = "rozkalns-weather.public-runtime-execution-plan.v1"
RESULT = "WEATHER_PUBLIC_RUNTIME_EXECUTION_CAPABILITY_READY_SOURCE_ONLY"
HELPER_EXECUTABLE = "/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper"
ACTIVATION_FILE = "/etc/rozkalns-weather/public-runtime-helper-activation.json"
ACTIVATION_SCHEMA = "rozkalns-weather.public-runtime-helper-activation.v1"
COMPOSE_PROJECT = "rozkalns-weather-public"
RELEASE_ROOT = "/opt/rozkalns-weather/releases"
# The exact-source checkout is atomically published directly into RELEASE_ROOT.
# Keeping CANDIDATE_ROOT equal to RELEASE_ROOT preserves the older helper interface
# without introducing a second filesystem materialization class.
CANDIDATE_ROOT = RELEASE_ROOT
CALLER_AUTHORITY = ("authorization_issue_number",)
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WeatherExecutionPlanError(ValueError):
    pass


@dataclass(frozen=True)
class WeatherExecutableStage:
    stage_id: str
    helper_id: str
    capability_id: str
    mutation_class: str | None
    max_operations: int
    read_only: bool
    executable: str
    argument_names: tuple[str, ...]
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class WeatherExecutablePlan:
    schema: str
    result: str
    authorization_issue_number: int
    request_id: str
    source_repository: str
    source_sha: str
    target_alias: str
    release_operation_id: str
    preactivation_sha256: str
    bootstrap_baseline_token: str
    start_date: str
    end_date: str
    recovery_decision: str
    truth_station_id: str
    forecast_models: tuple[str, ...]
    run_hours: tuple[int, ...]
    stages: tuple[WeatherExecutableStage, ...]
    helper_executable: str = HELPER_EXECUTABLE
    activation_file: str = ACTIVATION_FILE
    activation_schema: str = ACTIVATION_SCHEMA
    compose_project: str = COMPOSE_PROJECT
    candidate_root: str = CANDIDATE_ROOT
    release_root: str = RELEASE_ROOT
    caller_authority: tuple[str, ...] = CALLER_AUTHORITY
    execution_capability_implemented: bool = True
    installable_helper_source_present: bool = True
    privileged_dispatch_enabled: bool = False
    host_wiring_enabled: bool = False
    helper_installation_enabled: bool = False
    helper_invocation_enabled: bool = False
    production_mutation_enabled: bool = False
    production_mutation_started: bool = False
    automatic_retry_cleanup_rollback: bool = False
    generic_shell_authority: bool = False
    caller_supplied_path_allowed: bool = False
    caller_supplied_argv_allowed: bool = False
    caller_supplied_environment_allowed: bool = False


def _fail(message: str) -> None:
    raise WeatherExecutionPlanError(message)


def _canonical_stage_arguments(
    plan: WeatherHostWiringPlan,
    helper: WeatherHostHelperBinding,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    common_names = (
        "helper_id",
        "source_sha",
        "preactivation_sha256",
        "start_date",
        "end_date",
        "recovery_decision",
    )
    common_values = (
        helper.helper_id,
        plan.source_sha,
        plan.preactivation_sha256,
        plan.start_date,
        plan.end_date,
        plan.recovery_decision,
    )
    if helper.stage_id == "bounded_deterministic_forecast_backfill" or helper.stage_id == "corpus_integrity_check":
        return (
            common_names + ("forecast_models", "run_hours"),
            common_values
            + (
                ",".join(plan.forecast_models),
                ",".join(f"{hour:02d}" for hour in plan.run_hours),
            ),
        )
    if helper.stage_id == "bounded_dwd_truth_backfill":
        return common_names + ("truth_station_id",), common_values + (plan.truth_station_id,)
    return common_names, common_values


def _validate_host_plan_surface(plan: WeatherHostWiringPlan) -> None:
    if plan.source_repository != SOURCE_REPOSITORY or plan.target_alias != TARGET_ALIAS:
        _fail("Weather host plan source/target identity drifted")
    if plan.release_operation_id != OPERATION_ID:
        _fail("Weather host plan operation identity drifted")
    if not _SHA40_RE.fullmatch(plan.source_sha):
        _fail("Weather source SHA is invalid")
    if not _SHA256_RE.fullmatch(plan.preactivation_sha256):
        _fail("Weather preactivation SHA-256 is invalid")
    if plan.helpers != expected_helper_bindings():
        _fail("Weather helper identity or budget mapping drifted")
    if any(
        (
            plan.privileged_dispatch_enabled,
            plan.host_wiring_enabled,
            plan.helper_installation_enabled,
            plan.helper_invocation_enabled,
            plan.production_mutation_enabled,
            plan.production_mutation_started,
            plan.process_launch_surface,
            plan.generic_shell_authority,
            plan.runtime_live_authority,
            plan.automatic_retry_cleanup_rollback,
            plan.weather_next_required,
            plan.home_coordinates_required,
        )
    ):
        _fail("unexpected LIVE/private authority entered Weather host plan")


def build_weather_executable_plan(
    plan: WeatherHostWiringPlan,
    envelope: WeatherPreactivationEnvelope,
) -> WeatherExecutablePlan:
    """Compile validated Weather host wiring into fixed helper invocations without executing them."""

    validate_weather_host_wiring_plan(plan, envelope)
    _validate_host_plan_surface(plan)
    stages: list[WeatherExecutableStage] = []
    for helper in plan.helpers:
        names, values = _canonical_stage_arguments(plan, helper)
        stages.append(
            WeatherExecutableStage(
                stage_id=helper.stage_id,
                helper_id=helper.helper_id,
                capability_id=helper.capability_id,
                mutation_class=helper.mutation_class,
                max_operations=helper.max_operations,
                read_only=helper.read_only,
                executable=HELPER_EXECUTABLE,
                argument_names=names,
                arguments=values,
            )
        )
    return WeatherExecutablePlan(
        schema=EXECUTION_PLAN_SCHEMA,
        result=RESULT,
        authorization_issue_number=plan.authorization_issue_number,
        request_id=plan.request_id,
        source_repository=plan.source_repository,
        source_sha=plan.source_sha,
        target_alias=plan.target_alias,
        release_operation_id=plan.release_operation_id,
        preactivation_sha256=plan.preactivation_sha256,
        bootstrap_baseline_token=plan.bootstrap_baseline_token,
        start_date=plan.start_date,
        end_date=plan.end_date,
        recovery_decision=plan.recovery_decision,
        truth_station_id=plan.truth_station_id,
        forecast_models=plan.forecast_models,
        run_hours=plan.run_hours,
        stages=tuple(stages),
    )


def validate_weather_executable_plan(
    executable_plan: WeatherExecutablePlan,
    host_plan: WeatherHostWiringPlan,
    envelope: WeatherPreactivationEnvelope,
) -> WeatherExecutablePlan:
    if type(executable_plan) is not WeatherExecutablePlan:
        _fail("Weather executable plan type is invalid")
    expected = build_weather_executable_plan(host_plan, envelope)
    if executable_plan != expected:
        _fail("Weather executable plan or canonical evidence drifted")
    return executable_plan


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": EXECUTION_PLAN_SCHEMA,
        "result": RESULT,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "helper_executable": HELPER_EXECUTABLE,
        "activation_file": ACTIVATION_FILE,
        "activation_schema": ACTIVATION_SCHEMA,
        "candidate_root": CANDIDATE_ROOT,
        "release_root": RELEASE_ROOT,
        "candidate_root_equals_release_root": True,
        "caller_authority": CALLER_AUTHORITY,
        "execution_capability_implemented": True,
        "installable_helper_source_present": True,
        "candidate_materialization_source_present": True,
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "helper_installation_enabled": False,
        "helper_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "automatic_retry_cleanup_rollback": False,
        "generic_shell_authority": False,
        "caller_supplied_path_allowed": False,
        "caller_supplied_argv_allowed": False,
        "caller_supplied_environment_allowed": False,
    }
