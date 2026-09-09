from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.weather_public_runtime_adapter import (
    BASELINE_RESOLVER_ID,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from deploy_executor.weather_public_runtime_host_wiring import (
    AUTHORIZATION_CLASS,
    HOST_WIRING_SCHEMA,
    RESULT,
    WeatherHostWiringError,
    build_weather_host_wiring_plan,
    canonical_preactivation_sha256,
    expected_helper_bindings,
    source_readiness,
    validate_weather_host_wiring_plan,
)
from deploy_executor.weather_public_runtime_preactivation import (
    ENVELOPE_SCHEMA as PREACTIVATION_SCHEMA,
    RESULT as PREACTIVATION_RESULT,
    WeatherPreactivationEnvelope,
    WeatherPreactivationStageBinding,
)

SOURCE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_host_wiring.py"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-host-wiring.json"
REGISTRY = ROOT / "ops/deploy/executor-operations.json"
DOC = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_EXECUTOR_SOURCE.md"

SOURCE_SHA = "a" * 40
HASH_A = "1" * 64
HASH_B = "2" * 64
HASH_C = "3" * 64

_STAGE_ROWS = (
    ("application_release", OPERATION_ID, "application-release", 1, False),
    (
        "persistent_volume_ensure",
        "rozkalns-weather.public-runtime-volume.v1",
        "docker.named-volume-ensure",
        1,
        False,
    ),
    (
        "explicit_schema_init",
        "rozkalns-weather.public-runtime-schema-init.v1",
        "sqlite.schema-init",
        1,
        False,
    ),
    (
        "readiness_schema_privacy",
        "rozkalns-weather.public-runtime-readiness.v1",
        None,
        1,
        True,
    ),
    (
        "public_smoke_read_only",
        "rozkalns-weather.public-runtime-smoke.v1",
        None,
        1,
        True,
    ),
    (
        "bounded_dwd_truth_backfill",
        "rozkalns-weather.public-runtime-truth-backfill.v1",
        "sqlite.corpus-truth-backfill",
        1,
        False,
    ),
    (
        "bounded_deterministic_forecast_backfill",
        "rozkalns-weather.public-runtime-forecast-backfill.v1",
        "sqlite.corpus-forecast-backfill",
        3,
        False,
    ),
    (
        "corpus_integrity_check",
        "rozkalns-weather.public-runtime-integrity.v1",
        None,
        3,
        True,
    ),
    (
        "recurring_public_ingest_schedule",
        "rozkalns-weather.public-runtime-ingest-schedule.v1",
        "systemd.public-ingest-schedule-install-or-update",
        1,
        False,
    ),
)


def preactivation_envelope(**changes) -> WeatherPreactivationEnvelope:
    value = WeatherPreactivationEnvelope(
        schema=PREACTIVATION_SCHEMA,
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
        bootstrap_baseline_token=(
            "deployment=not_deployed;source=none;volume=absent;schema=absent:none;"
            "schedule=absent;stage=not_started"
        ),
        start_date="2026-04-02",
        end_date="2026-09-07",
        recovery_decision="owner-accepted-no-prewrite-backup",
        truth_station_id="10416",
        forecast_models=("icon_d2", "ecmwf_ifs", "ecmwf_aifs"),
        run_hours=(0, 6, 12, 18),
        stages=tuple(WeatherPreactivationStageBinding(*row) for row in _STAGE_ROWS),
    )
    return replace(value, **changes)


class WeatherPublicHostWiringTests(unittest.TestCase):
    def test_valid_plan_binds_whole_preactivation_and_keeps_execution_disabled(self):
        envelope = preactivation_envelope()
        plan = build_weather_host_wiring_plan(envelope)

        self.assertEqual(plan.schema, HOST_WIRING_SCHEMA)
        self.assertEqual(plan.result, RESULT)
        self.assertEqual(plan.preactivation_sha256, canonical_preactivation_sha256(envelope))
        self.assertEqual(len(plan.preactivation_sha256), 64)
        self.assertEqual(plan.authorization_class, "STRICT")
        self.assertFalse(plan.ordinary_live_all_eligible)
        self.assertTrue(plan.helper_interface_source_present)
        self.assertFalse(plan.privileged_dispatch_enabled)
        self.assertFalse(plan.host_wiring_enabled)
        self.assertFalse(plan.helper_installation_enabled)
        self.assertFalse(plan.helper_invocation_enabled)
        self.assertFalse(plan.production_mutation_enabled)
        self.assertFalse(plan.production_mutation_started)
        self.assertFalse(plan.process_launch_surface)
        self.assertFalse(plan.generic_shell_authority)
        self.assertFalse(plan.runtime_live_authority)
        self.assertFalse(plan.automatic_retry_cleanup_rollback)
        self.assertFalse(plan.weather_next_required)
        self.assertFalse(plan.home_coordinates_required)
        self.assertEqual(validate_weather_host_wiring_plan(plan, envelope), plan)

    def test_stage_to_helper_mapping_is_fixed_and_preserves_budgets(self):
        plan = build_weather_host_wiring_plan(preactivation_envelope())
        self.assertEqual(plan.helpers, expected_helper_bindings())
        self.assertEqual(
            tuple(
                (
                    binding.stage_id,
                    binding.capability_id,
                    binding.mutation_class,
                    binding.max_operations,
                    binding.read_only,
                )
                for binding in plan.helpers
            ),
            _STAGE_ROWS,
        )
        self.assertEqual(len({binding.helper_id for binding in plan.helpers}), 9)

    def test_whole_envelope_hash_detects_later_preactivation_edit(self):
        envelope = preactivation_envelope()
        plan = build_weather_host_wiring_plan(envelope)
        edited = replace(envelope, end_date="2026-09-06")

        self.assertNotEqual(
            plan.preactivation_sha256,
            canonical_preactivation_sha256(edited),
        )
        with self.assertRaisesRegex(WeatherHostWiringError, "drifted"):
            validate_weather_host_wiring_plan(plan, edited)

    def test_stage_reorder_and_helper_budget_drift_fail_closed(self):
        envelope = preactivation_envelope()
        reordered = replace(envelope, stages=tuple(reversed(envelope.stages)))
        with self.assertRaisesRegex(WeatherHostWiringError, "stage/capability"):
            build_weather_host_wiring_plan(reordered)

        plan = build_weather_host_wiring_plan(envelope)
        changed_helper = replace(plan.helpers[0], max_operations=2)
        changed_plan = replace(plan, helpers=(changed_helper,) + plan.helpers[1:])
        with self.assertRaisesRegex(WeatherHostWiringError, "drifted"):
            validate_weather_host_wiring_plan(changed_plan, envelope)

    def test_source_target_and_private_or_execution_expansion_fail_closed(self):
        invalid_cases = (
            (replace(preactivation_envelope(), source_sha="A" * 40), "source SHA"),
            (replace(preactivation_envelope(), target_alias="attacker-target"), "target alias"),
            (
                replace(
                    preactivation_envelope(),
                    release_baseline_resolver_id="attacker.baseline.v1",
                ),
                "baseline resolver",
            ),
            (replace(preactivation_envelope(), home_coordinates_required=True), "private inputs"),
            (replace(preactivation_envelope(), weather_next_required=True), "private inputs"),
            (replace(preactivation_envelope(), privileged_dispatch_enabled=True), "execution"),
            (replace(preactivation_envelope(), host_wiring_enabled=True), "execution"),
            (replace(preactivation_envelope(), production_mutation_enabled=True), "production mutation"),
            (replace(preactivation_envelope(), process_launch_surface=True), "process launch"),
        )
        for envelope, pattern in invalid_cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(WeatherHostWiringError, pattern):
                    build_weather_host_wiring_plan(envelope)

    def test_machine_contract_matches_source_and_registry_stays_strict_disabled(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        readiness = source_readiness()

        self.assertEqual(contract["contract"], HOST_WIRING_SCHEMA)
        self.assertEqual(contract["authorization_class"], AUTHORIZATION_CLASS)
        self.assertFalse(contract["ordinary_live_all_eligible"])
        for flag in (
            "privileged_dispatch_enabled",
            "host_wiring_enabled",
            "helper_installation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
            "process_launch_surface",
            "generic_shell_authority",
            "runtime_live_authority",
            "automatic_retry_cleanup_rollback",
        ):
            self.assertFalse(contract[flag])
            self.assertFalse(readiness[flag])

        self.assertEqual(
            contract["helpers"],
            [asdict(binding) for binding in expected_helper_bindings()],
        )
        self.assertFalse(registry["execution_enabled"])
        weather_operation = next(
            operation
            for operation in registry["operations"]
            if operation["operation_id"] == OPERATION_ID
        )
        self.assertEqual(weather_operation["authorization_class"], "STRICT")
        self.assertFalse(weather_operation["ordinary_live_all_eligible"])

    def test_source_contains_no_host_io_process_or_generic_execution_primitive(self):
        source = SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import subprocess",
            "subprocess.",
            "os.system(",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "exec(",
            "sudo ",
            "docker.sock",
            "requests.",
            "urllib.",
            "socket.",
            "paramiko",
            "pathlib",
            "open(",
        ):
            self.assertNotIn(forbidden, source)

    def test_canonical_doc_states_source_present_but_host_disabled(self):
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("Issue #435", doc)
        self.assertIn("host-wiring interface is implemented in source but remains disabled on the host", doc)
        self.assertIn("weather-public-runtime-host-wiring.json", doc)
        self.assertIn("separate exact LIVE authorization", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
