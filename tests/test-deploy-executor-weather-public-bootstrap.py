from __future__ import annotations

from dataclasses import replace
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.weather_public_runtime_bootstrap import (
    BASELINE_EVIDENCE_SCHEMA,
    BOOTSTRAP_CAPABILITY_ID,
    DISPATCH_PLAN_SCHEMA,
    FORECAST_MODELS,
    MAX_BACKFILL_DAYS,
    OPERATION_ID,
    PUBLIC_INGEST_CADENCE,
    REQUEST_SCHEMA,
    RUN_HOURS,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    TRUTH_CHUNK_DAYS,
    TRUTH_PROVIDER,
    TRUTH_STATION_ID,
    CanonicalWeatherBootstrapEvidence,
    WeatherBootstrapError,
    consume_weather_bootstrap_request,
    parse_weather_bootstrap_baseline,
    parse_weather_bootstrap_request,
    prepare_weather_bootstrap_dispatch,
    source_readiness,
)

SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "weather_public_runtime_bootstrap.py"
SOURCE_SHA = "a" * 40


def request_payload() -> dict[str, object]:
    return {
        "schema": REQUEST_SCHEMA,
        "authorization_issue_number": 9410,
    }


def canonical_evidence(**changes) -> CanonicalWeatherBootstrapEvidence:
    value = CanonicalWeatherBootstrapEvidence(
        authorization_issue_number=9410,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        current_main_sha=SOURCE_SHA,
        target_alias=TARGET_ALIAS,
        operation_id=OPERATION_ID,
        capability_id=BOOTSTRAP_CAPABILITY_ID,
        runtime_class="public-only-rpi5",
        source_reachable_from_main=True,
        source_ci_success=True,
        handoff_identity_match=True,
        static_registry_contract_match=True,
        registry_execution_enabled=False,
        release_adapter_execution_enabled=False,
        public_only_private_inputs_absent=True,
        start_date="2026-04-02",
        end_date="2026-09-07",
        truth_provider=TRUTH_PROVIDER,
        truth_station_id=TRUTH_STATION_ID,
        forecast_models=FORECAST_MODELS,
        run_hours=RUN_HOURS,
        truth_chunk_days=TRUTH_CHUNK_DAYS,
        recovery_decision="owner-accepted-no-prewrite-backup",
        backup_restore_authorized=False,
        public_ingest_cadence=PUBLIC_INGEST_CADENCE,
    )
    return replace(value, **changes)


def baseline_payload(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": BASELINE_EVIDENCE_SCHEMA,
        "target_alias": TARGET_ALIAS,
        "deployment_state": "not_deployed",
        "current_source_sha": None,
        "persistent_volume_state": "absent",
        "schema_state": "absent",
        "schema_version": None,
        "public_ingest_schedule_state": "absent",
        "bootstrap_stage_state": "not_started",
        "privacy_safe": True,
    }
    value.update(changes)
    return value


class FakeRevalidator:
    def __init__(self, evidence: CanonicalWeatherBootstrapEvidence) -> None:
        self.evidence = evidence
        self.calls = 0

    def revalidate(self, authorization_issue_number: int) -> CanonicalWeatherBootstrapEvidence:
        self.calls += 1
        return self.evidence


class FakeBaselineResolver:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def resolve(self, *, source_sha: str, target_alias: str) -> dict[str, object]:
        self.calls += 1
        return dict(self.payload)


class WeatherBootstrapRequestTests(unittest.TestCase):
    def test_request_is_identity_only(self):
        parsed = parse_weather_bootstrap_request(request_payload())
        self.assertEqual(parsed.authorization_issue_number, 9410)
        for forbidden in ("command", "path", "argv", "environment", "source_sha", "target_alias"):
            payload = request_payload()
            payload[forbidden] = "forbidden"
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(WeatherBootstrapError, "identity-only"):
                    parse_weather_bootstrap_request(payload)

    def test_request_rejects_wrong_schema_and_issue_type(self):
        payload = request_payload()
        payload["schema"] = "wrong"
        with self.assertRaisesRegex(WeatherBootstrapError, "schema"):
            parse_weather_bootstrap_request(payload)
        payload = request_payload()
        payload["authorization_issue_number"] = "9410"
        with self.assertRaisesRegex(WeatherBootstrapError, "supported range"):
            parse_weather_bootstrap_request(payload)


class WeatherBootstrapBaselineTests(unittest.TestCase):
    def test_not_deployed_baseline_is_deterministic_and_sanitized(self):
        baseline = parse_weather_bootstrap_baseline(baseline_payload())
        self.assertEqual(
            baseline.canonical_token,
            "deployment=not_deployed;source=none;volume=absent;schema=absent:none;schedule=absent;stage=not_started",
        )
        rendered = baseline.canonical_json()
        self.assertNotIn("HOME_LAT", rendered)
        self.assertNotIn("credential", rendered.lower())

    def test_ready_schema_requires_reviewed_version(self):
        baseline = parse_weather_bootstrap_baseline(
            baseline_payload(
                deployment_state="deployed",
                current_source_sha=SOURCE_SHA,
                persistent_volume_state="present",
                schema_state="ready",
                schema_version=1,
                bootstrap_stage_state="schema_ready",
            )
        )
        self.assertEqual(baseline.schema_version, 1)
        with self.assertRaisesRegex(WeatherBootstrapError, "schema version"):
            parse_weather_bootstrap_baseline(
                baseline_payload(schema_state="ready", schema_version=2)
            )

    def test_baseline_rejects_private_or_unknown_fields(self):
        payload = baseline_payload()
        payload["HOME_LAT"] = "forbidden"
        with self.assertRaisesRegex(WeatherBootstrapError, "keys mismatch"):
            parse_weather_bootstrap_baseline(payload)
        with self.assertRaisesRegex(WeatherBootstrapError, "privacy-safe"):
            parse_weather_bootstrap_baseline(baseline_payload(privacy_safe=False))


class WeatherBootstrapConsumerTests(unittest.TestCase):
    def _consume(self, evidence=None, baseline=None):
        revalidator = FakeRevalidator(evidence or canonical_evidence())
        resolver = FakeBaselineResolver(baseline or baseline_payload())
        ready = consume_weather_bootstrap_request(
            request_payload(),
            canonical_revalidator=revalidator,
            baseline_resolver=resolver,
        )
        return ready, revalidator, resolver

    def test_consumer_revalidates_and_remains_execution_disabled(self):
        ready, revalidator, resolver = self._consume()
        self.assertEqual(revalidator.calls, 2)
        self.assertEqual(resolver.calls, 1)
        self.assertEqual(ready.source_sha, SOURCE_SHA)
        self.assertFalse(ready.privileged_dispatch_enabled)
        self.assertFalse(ready.host_wiring_enabled)
        self.assertFalse(ready.production_mutation_started)

    def test_consumer_rejects_identity_and_trust_drift(self):
        cases = (
            ("source_repository", "attacker/repo", "source repository"),
            ("source_sha", "latest", "source_sha"),
            ("target_alias", "attacker-target", "target alias"),
            ("capability_id", "generic-shell", "capability"),
            ("runtime_class", "private", "runtime class"),
            ("source_reachable_from_main", False, "reachable"),
            ("source_ci_success", False, "source_ci_success"),
            ("registry_execution_enabled", True, "registry_execution_enabled"),
            ("release_adapter_execution_enabled", True, "release_adapter_execution_enabled"),
            ("public_only_private_inputs_absent", False, "private_inputs"),
            ("backup_restore_authorized", True, "backup_restore_authorized"),
        )
        for field, value, pattern in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(WeatherBootstrapError, pattern):
                    self._consume(canonical_evidence(**{field: value}))

    def test_consumer_requires_exact_bounded_public_backfill_scope(self):
        cases = (
            ("truth_provider", "nearest-station", "truth provider"),
            ("truth_station_id", "00000", "truth station"),
            ("forecast_models", ("icon_d2",), "model scope"),
            ("run_hours", (0,), "run-hour"),
            ("truth_chunk_days", 31, "truth chunk"),
            ("recovery_decision", "automatic-restore", "recovery decision"),
            ("public_ingest_cadence", "PT1M", "cadence"),
        )
        for field, value, pattern in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(WeatherBootstrapError, pattern):
                    self._consume(canonical_evidence(**{field: value}))

        with self.assertRaisesRegex(WeatherBootstrapError, "exceeds maximum"):
            self._consume(
                canonical_evidence(start_date="2026-01-01", end_date="2026-09-07")
            )
        self.assertEqual(MAX_BACKFILL_DAYS, 180)


class WeatherBootstrapDispatcherTests(unittest.TestCase):
    def test_dispatch_plan_preserves_ordered_distinct_capabilities(self):
        plan = prepare_weather_bootstrap_dispatch(
            request_payload(),
            canonical_revalidator=FakeRevalidator(canonical_evidence()),
            baseline_resolver=FakeBaselineResolver(baseline_payload()),
        )
        self.assertEqual(plan.schema, DISPATCH_PLAN_SCHEMA)
        self.assertEqual(plan.result, "WEATHER_BOOTSTRAP_SOURCE_READY")
        self.assertEqual(
            tuple(stage.stage_id for stage in plan.stages),
            (
                "application_release",
                "persistent_volume_ensure",
                "explicit_schema_init",
                "readiness_schema_privacy",
                "public_smoke_read_only",
                "bounded_dwd_truth_backfill",
                "bounded_deterministic_forecast_backfill",
                "corpus_integrity_check",
                "recurring_public_ingest_schedule",
            ),
        )
        mutation_classes = tuple(
            stage.mutation_class for stage in plan.stages if stage.mutation_class is not None
        )
        self.assertEqual(len(mutation_classes), len(set(mutation_classes)))
        self.assertIn("application-release", mutation_classes)
        self.assertIn("sqlite.schema-init", mutation_classes)
        self.assertIn("sqlite.corpus-truth-backfill", mutation_classes)
        self.assertIn("sqlite.corpus-forecast-backfill", mutation_classes)
        self.assertIn("systemd.public-ingest-schedule-install-or-update", mutation_classes)
        self.assertEqual(
            next(stage for stage in plan.stages if stage.stage_id == "bounded_deterministic_forecast_backfill").max_operations,
            len(FORECAST_MODELS),
        )

    def test_dispatch_plan_is_source_only_and_preserves_corpus(self):
        plan = prepare_weather_bootstrap_dispatch(
            request_payload(),
            canonical_revalidator=FakeRevalidator(canonical_evidence()),
            baseline_resolver=FakeBaselineResolver(baseline_payload()),
        )
        self.assertFalse(plan.privileged_dispatch_enabled)
        self.assertFalse(plan.host_wiring_enabled)
        self.assertFalse(plan.production_mutation_started)
        self.assertFalse(plan.weather_next_required)
        self.assertFalse(plan.home_coordinates_required)
        self.assertFalse(plan.automatic_retry_cleanup_rollback)
        self.assertFalse(plan.sqlite_rollback_delete_restore)
        self.assertEqual(plan.persistent_volume, "weather_data")
        self.assertEqual(plan.readiness_endpoint, "/ready")

    def test_source_has_no_process_launch_or_generic_shell_bridge(self):
        source = SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "sudo ",
            "docker.sock",
        ):
            self.assertNotIn(forbidden, source)
        readiness = source_readiness()
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertFalse(readiness["process_launch_surface"])
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
