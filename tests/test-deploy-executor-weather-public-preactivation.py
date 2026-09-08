from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.protocol import (
    END_MARKER,
    LIVE_AUTH_SCHEMA,
    OWNER_USER_ID,
    START_MARKER,
    ProtocolError,
)
from deploy_executor.queue_normalizer import QUEUE_REPOSITORY, normalize_ready_queue
from deploy_executor.registry import load_registry
from deploy_executor.weather_public_runtime_adapter import (
    BASELINE_RESOLVER_ID,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from deploy_executor.weather_public_runtime_bootstrap import (
    BASELINE_EVIDENCE_SCHEMA,
    BOOTSTRAP_CAPABILITY_ID,
    FORECAST_MODELS,
    PUBLIC_INGEST_CADENCE,
    RUN_HOURS,
    TRUTH_CHUNK_DAYS,
    TRUTH_PROVIDER,
    TRUTH_STATION_ID,
    CanonicalWeatherBootstrapEvidence,
    prepare_weather_bootstrap_dispatch,
)
from deploy_executor.weather_public_runtime_preactivation import (
    ENVELOPE_SCHEMA,
    RESULT,
    WeatherPreactivationError,
    prepare_weather_preactivation_envelope,
    source_readiness,
)

PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
QUEUE_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "deploy_executor"
    / "queue_issue_weather_public_runtime_ready.json"
)
SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "weather_public_runtime_preactivation.py"
AUTH_ISSUE_NUMBER = 9410
AUTH_ISSUE_ID = 99410
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
SOURCE_SHA = "a" * 40
NOW = datetime(2026, 9, 8, 18, 45, 0, tzinfo=timezone.utc)


def normalized_queue() -> dict[str, object]:
    registry = load_registry(PRODUCTION_REGISTRY)
    raw = json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))
    return normalize_ready_queue(
        raw,
        repository_full_name=QUEUE_REPOSITORY,
        registry=registry,
    ).as_protocol_queue()


def live_auth_payload(queue: dict[str, object] | None = None) -> dict[str, object]:
    value = queue or normalized_queue()
    return {
        "schema": LIVE_AUTH_SCHEMA,
        "request_id": REQUEST_ID,
        "queue_repository": value["repository"],
        "queue_issue": value["issue_number"],
        "source_repository": value["source_repository"],
        "source_sha": value["source_sha"],
        "target_alias": value["target_alias"],
        "operation_id": value["operation_id"],
        "expected_baseline": copy.deepcopy(value["expected_baseline"]),
        "mutation_budget": copy.deepcopy(value["mutation_budget"]),
        "rollback_policy": value["rollback_policy"],
        "exclusions": copy.deepcopy(value["exclusions"]),
        "dependencies": copy.deepcopy(value["dependencies"]),
    }


def auth_issue(payload: dict[str, object] | None = None) -> dict[str, object]:
    value = payload or live_auth_payload()
    body = (
        f"{START_MARKER}\n```json\n"
        + json.dumps(value, indent=2, sort_keys=True)
        + f"\n```\n{END_MARKER}"
    )
    return {
        "id": AUTH_ISSUE_ID,
        "number": AUTH_ISSUE_NUMBER,
        "state": "open",
        "created_at": "2026-09-08T18:44:00Z",
        "title": f"[LIVE-AUTH][PENDING] {TARGET_ALIAS}",
        "body": body,
        "user": {"id": OWNER_USER_ID, "type": "User"},
        "performed_via_github_app": None,
    }


def canonical_evidence(**changes) -> CanonicalWeatherBootstrapEvidence:
    value = CanonicalWeatherBootstrapEvidence(
        authorization_issue_number=AUTH_ISSUE_NUMBER,
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


def baseline_payload() -> dict[str, object]:
    return {
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


class SequenceAuthorizationResolver:
    def __init__(self, *issues: dict[str, object]) -> None:
        self.issues = list(issues)
        self.calls = 0

    def resolve(self, issue_number: int) -> dict[str, object]:
        self.calls += 1
        self.asserted_issue_number = issue_number
        index = min(self.calls - 1, len(self.issues) - 1)
        return copy.deepcopy(self.issues[index])


class SequenceQueueResolver:
    def __init__(self, *queues: dict[str, object]) -> None:
        self.queues = list(queues)
        self.calls = 0

    def resolve(self, *, repository_full_name: str, issue_number: int) -> dict[str, object]:
        self.calls += 1
        self.repository_full_name = repository_full_name
        self.issue_number = issue_number
        index = min(self.calls - 1, len(self.queues) - 1)
        return copy.deepcopy(self.queues[index])


class ReplayGuard:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def assert_unconsumed(self, *, issue_id: int, request_id: str) -> None:
        self.calls += 1
        if self.fail:
            raise WeatherPreactivationError("authorization already consumed or replay state uncertain")
        if issue_id != AUTH_ISSUE_ID or request_id != REQUEST_ID:
            raise AssertionError("unexpected replay identity")


class FakeRevalidator:
    def __init__(self, evidence: CanonicalWeatherBootstrapEvidence) -> None:
        self.evidence = evidence

    def revalidate(self, authorization_issue_number: int) -> CanonicalWeatherBootstrapEvidence:
        if authorization_issue_number != AUTH_ISSUE_NUMBER:
            raise AssertionError("unexpected bootstrap authorization issue")
        return self.evidence


class FakeBaselineResolver:
    def resolve(self, *, source_sha: str, target_alias: str) -> dict[str, object]:
        if target_alias != TARGET_ALIAS:
            raise AssertionError("unexpected target")
        return baseline_payload()


def prepare(**changes):
    issue_resolver = changes.pop("authorization_resolver", SequenceAuthorizationResolver(auth_issue()))
    queue_resolver = changes.pop("queue_resolver", SequenceQueueResolver(normalized_queue()))
    replay_guard = changes.pop("replay_guard", ReplayGuard())
    revalidator = changes.pop("canonical_revalidator", FakeRevalidator(canonical_evidence()))
    envelope = prepare_weather_preactivation_envelope(
        AUTH_ISSUE_NUMBER,
        server_time=NOW,
        governance_ok=True,
        authorization_resolver=issue_resolver,
        queue_resolver=queue_resolver,
        replay_guard=replay_guard,
        canonical_revalidator=revalidator,
        baseline_resolver=FakeBaselineResolver(),
        **changes,
    )
    return envelope, issue_resolver, queue_resolver, replay_guard


class WeatherPreactivationContractTests(unittest.TestCase):
    def test_valid_envelope_is_exact_identity_only_and_execution_disabled(self):
        envelope, issue_resolver, queue_resolver, replay_guard = prepare()
        self.assertEqual(envelope.schema, ENVELOPE_SCHEMA)
        self.assertEqual(envelope.result, RESULT)
        self.assertEqual(envelope.authorization_issue_number, AUTH_ISSUE_NUMBER)
        self.assertEqual(envelope.request_id, REQUEST_ID)
        self.assertEqual(envelope.source_sha, SOURCE_SHA)
        self.assertEqual(envelope.target_alias, TARGET_ALIAS)
        self.assertEqual(envelope.release_operation_id, OPERATION_ID)
        self.assertEqual(envelope.release_baseline_resolver_id, BASELINE_RESOLVER_ID)
        self.assertEqual(envelope.caller_authority, ("authorization_issue_number",))
        self.assertFalse(envelope.privileged_dispatch_enabled)
        self.assertFalse(envelope.host_wiring_enabled)
        self.assertFalse(envelope.production_mutation_enabled)
        self.assertFalse(envelope.production_mutation_started)
        self.assertFalse(envelope.process_launch_surface)
        self.assertTrue(envelope.separate_mutation_gates_required)
        self.assertFalse(envelope.automatic_retry_cleanup_rollback)
        self.assertFalse(envelope.weather_next_required)
        self.assertFalse(envelope.home_coordinates_required)
        self.assertGreaterEqual(issue_resolver.calls, 3)
        self.assertEqual(queue_resolver.calls, 2)
        self.assertEqual(replay_guard.calls, 2)

    def test_stage_mapping_is_fixed_and_preserves_separate_mutation_classes(self):
        envelope, *_ = prepare()
        observed = tuple((row.stage_id, row.mutation_class) for row in envelope.stages)
        self.assertEqual(
            observed,
            (
                ("application_release", "application-release"),
                ("persistent_volume_ensure", "docker.named-volume-ensure"),
                ("explicit_schema_init", "sqlite.schema-init"),
                ("readiness_schema_privacy", None),
                ("public_smoke_read_only", None),
                ("bounded_dwd_truth_backfill", "sqlite.corpus-truth-backfill"),
                ("bounded_deterministic_forecast_backfill", "sqlite.corpus-forecast-backfill"),
                ("corpus_integrity_check", None),
                (
                    "recurring_public_ingest_schedule",
                    "systemd.public-ingest-schedule-install-or-update",
                ),
            ),
        )
        self.assertEqual(envelope.truth_station_id, "10416")
        self.assertEqual(envelope.forecast_models, ("icon_d2", "ecmwf_ifs", "ecmwf_aifs"))
        self.assertEqual(envelope.run_hours, (0, 6, 12, 18))

    def test_owner_authorization_body_drift_fails_closed(self):
        current = auth_issue()
        drifted = copy.deepcopy(current)
        drifted["body"] += "\n"
        resolver = SequenceAuthorizationResolver(current, drifted)
        with self.assertRaisesRegex(ProtocolError, "RAW_BODY_DRIFT"):
            prepare(authorization_resolver=resolver)

    def test_ready_queue_drift_fails_closed(self):
        current = normalized_queue()
        drifted = copy.deepcopy(current)
        drifted["state"] = "BLOCKED"
        resolver = SequenceQueueResolver(current, drifted)
        with self.assertRaisesRegex(ProtocolError, "QUEUE_NOT_READY"):
            prepare(queue_resolver=resolver)

    def test_replay_or_consumption_uncertainty_fails_closed(self):
        with self.assertRaisesRegex(WeatherPreactivationError, "consumed|replay"):
            prepare(replay_guard=ReplayGuard(fail=True))

    def test_bootstrap_source_must_match_accepted_live_auth(self):
        revalidator = FakeRevalidator(canonical_evidence(source_sha="b" * 40, current_main_sha="b" * 40))
        with self.assertRaisesRegex(WeatherPreactivationError, "source SHA"):
            prepare(canonical_revalidator=revalidator)

    def test_wrong_weather_operation_or_baseline_is_rejected(self):
        for field, value, pattern in (
            ("operation_id", "attacker.operation.v1", "operation"),
            (
                "expected_baseline",
                {"kind": "resolver", "value": "attacker.baseline.v1"},
                "baseline",
            ),
        ):
            payload = live_auth_payload()
            payload[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(WeatherPreactivationError, pattern):
                    prepare(authorization_resolver=SequenceAuthorizationResolver(auth_issue(payload)))

    def test_stage_drift_is_rejected(self):
        real_plan = prepare_weather_bootstrap_dispatch(
            {"schema": "rozkalns-weather.public-runtime-bootstrap-request.v1", "authorization_issue_number": AUTH_ISSUE_NUMBER},
            canonical_revalidator=FakeRevalidator(canonical_evidence()),
            baseline_resolver=FakeBaselineResolver(),
        )
        drifted = replace(real_plan, stages=tuple(reversed(real_plan.stages)))
        with patch(
            "deploy_executor.weather_public_runtime_preactivation.prepare_weather_bootstrap_dispatch",
            return_value=drifted,
        ):
            with self.assertRaisesRegex(WeatherPreactivationError, "stage/capability"):
                prepare()

    def test_source_has_no_process_shell_network_or_private_authority(self):
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
            "requests",
            "urllib",
            "socket.",
            "home_lat",
            "home_lon",
        ):
            self.assertNotIn(forbidden, source)
        readiness = source_readiness()
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["production_mutation_enabled"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertFalse(readiness["process_launch_surface"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
