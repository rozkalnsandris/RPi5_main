from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_application_staging as stage
from deploy_executor import weather_private_application_staging_runtime as runtime
from deploy_executor import weather_private_bigquery_host_bindings as bindings

CONTRACT_PATH = ROOT / "ops/deploy/weather-private-application-stage.json"
ENTRYPOINT_PATH = ROOT / "ops/bin/rpi5-weathernext-private-host-privileged-install"
DISPATCH_PATH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"


class WeatherNextPrivateApplicationStageTests(unittest.TestCase):
    def evidence(self, **overrides: object) -> stage.ApplicationStageEvidence:
        values: dict[str, object] = dict(
            exact_weather_source_sha="2" * 40,
            current_weather_main_sha="2" * 40,
            exact_main_ci_success=True,
            stage_present=False,
            partial_present=False,
        )
        values.update(overrides)
        return stage.ApplicationStageEvidence(**values)

    def test_absent_stage_builds_exact_bounded_plan(self) -> None:
        plan = stage.build_stage_plan(self.evidence())
        self.assertEqual(plan.prior_state, "ABSENT")
        self.assertEqual(plan.operation_id, stage.OPERATION_ID)
        self.assertEqual(plan.target_alias, stage.TARGET_ALIAS)
        self.assertEqual(plan.source_repository, "rozkalnsandris/rozkalns_weather")
        self.assertEqual(plan.reviewed_origin, stage.REVIEWED_ORIGIN)
        self.assertEqual(plan.stage_root, str(stage.STAGE_ROOT))
        self.assertEqual(plan.marker, str(stage.MARKER))
        self.assertEqual(
            tuple((item.category, item.maximum) for item in plan.steps),
            stage.MUTATION_BUDGET,
        )
        self.assertEqual(plan.rollback_policy, "NONE")
        self.assertFalse(plan.automatic_retry)
        self.assertFalse(plan.automatic_cleanup)
        self.assertFalse(plan.automatic_rollback)
        self.assertFalse(plan.runtime_materialization_allowed)
        self.assertFalse(plan.google_action_allowed)
        self.assertFalse(plan.bigquery_action_allowed)
        self.assertFalse(plan.sqlite_write_allowed)

    def test_exact_stage_is_noop_and_conflict_fails_closed(self) -> None:
        exact = self.evidence(
            stage_present=True,
            stage_uid=0,
            stage_gid=0,
            stage_mode=0o755,
            marker_exact=True,
            git_origin=stage.REVIEWED_ORIGIN,
            git_head_sha="2" * 40,
            git_detached=True,
            tracked_clean=True,
        )
        plan = stage.build_stage_plan(exact)
        self.assertEqual(plan.prior_state, "EXACT")
        self.assertEqual(plan.steps, ())
        conflicts = [
            self.evidence(partial_present=True),
            self.evidence(stage_present=True),
            self.evidence(
                stage_present=True,
                stage_uid=0,
                stage_gid=0,
                stage_mode=0o755,
                marker_exact=True,
                git_origin="https://example.invalid/wrong.git",
                git_head_sha="2" * 40,
                git_detached=True,
                tracked_clean=True,
            ),
        ]
        for evidence in conflicts:
            with self.subTest(evidence=evidence):
                with self.assertRaises(stage.WeatherNextPrivateApplicationStageError):
                    stage.build_stage_plan(evidence)

    def test_source_head_and_ci_drift_fail_before_plan(self) -> None:
        cases = [
            self.evidence(current_weather_main_sha="3" * 40),
            self.evidence(exact_main_ci_success=False),
            self.evidence(exact_weather_source_sha="not-a-sha"),
        ]
        for evidence in cases:
            with self.subTest(evidence=evidence):
                with self.assertRaises(stage.WeatherNextPrivateApplicationStageError):
                    stage.build_stage_plan(evidence)

    def test_marker_contract_matches_installed_backend_observer(self) -> None:
        source_sha = "2" * 40
        self.assertEqual(stage.MARKER, bindings.APPLICATION_MARKER)
        self.assertEqual(
            stage.marker_value(source_sha),
            {
                "schema": "rozkalns-weather.weathernext-private-application-stage.v1",
                "source_repository": bindings.WEATHER_REPOSITORY,
                "source_sha": source_sha,
                "staged": True,
            },
        )

    def test_runtime_registry_is_fixed_and_execution_disabled(self) -> None:
        registry = runtime._fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, stage.OPERATION_ID)
        self.assertEqual(operation.source_repository, stage.SOURCE_REPOSITORY)
        self.assertEqual(operation.target_alias, stage.TARGET_ALIAS)
        self.assertEqual(
            tuple((item.category, item.max_operations) for item in operation.mutation_budget),
            stage.MUTATION_BUDGET,
        )
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.dependencies, runtime.DEPENDENCIES)

    def test_source_contract_matches_runtime_and_grants_no_live(self) -> None:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        ready = runtime.source_readiness()
        self.assertEqual(value["operation_id"], stage.OPERATION_ID)
        self.assertEqual(value["target_alias"], stage.TARGET_ALIAS)
        self.assertEqual(value["source_repository"], stage.SOURCE_REPOSITORY)
        self.assertEqual(value["stage_root"], str(stage.STAGE_ROOT))
        self.assertEqual(value["marker"], str(stage.MARKER))
        self.assertEqual(value["rollback_policy"], ready["rollback_policy"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertFalse(value["production_mutation_started"])
        for field in (
            "private_runtime_materialization_allowed",
            "google_action_allowed",
            "bigquery_action_allowed",
            "sqlite_write_allowed",
        ):
            self.assertFalse(value[field])

    def test_privileged_caller_surface_remains_issue_identity_only(self) -> None:
        source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--issue-number"', source)
        for forbidden in (
            "--operation", "--command", "--path", "--argv", "--environment",
            "--source-sha", "--repository", "--target", "--project", "--dataset",
            "--credential", "--query", "--sql",
        ):
            self.assertNotIn(forbidden, source)
        parameters = tuple(inspect.signature(runtime.run_privileged_application_stage).parameters)
        self.assertEqual(parameters, ("authorization_issue_number",))

    def test_dispatch_is_fixed_allowlist_not_generic_execution(self) -> None:
        source = DISPATCH_PATH.read_text(encoding="utf-8")
        self.assertIn("INSTALL_OPERATION_ID", source)
        self.assertIn("APPLICATION_STAGE_OPERATION_ID", source)
        for forbidden in (
            "shell=True", "os.system", "eval(", "exec(", "--operation", "subprocess",
        ):
            self.assertNotIn(forbidden, source)

    def test_application_stage_source_has_no_later_private_actions(self) -> None:
        source = Path(stage.__file__).read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("sudo ", source)
        self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", source)
        self.assertNotIn("google.cloud", source)
        self.assertNotIn("bigquery.Client", source)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("docker ", source)
        fields = set(stage.ApplicationStageEvidence.__dataclass_fields__)
        for forbidden in (
            "project", "dataset", "credential", "account", "sql", "query",
            "home_lat", "home_lon",
        ):
            self.assertNotIn(forbidden, fields)


if __name__ == "__main__":
    unittest.main()
