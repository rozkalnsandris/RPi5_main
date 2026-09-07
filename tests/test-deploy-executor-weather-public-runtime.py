from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, prepare_operation
from deploy_executor.queue_normalizer import (
    QUEUE_REPOSITORY,
    QueueNormalizationError,
    normalize_ready_queue,
)
from deploy_executor.registry import load_registry
from deploy_executor.weather_public_runtime_adapter import (
    ADAPTER_ID,
    BASELINE_RESOLVER_ID,
    COMPOSE_PUBLIC_BLOB,
    COMPOSE_SERVICES,
    DATABASE_URL,
    HANDOFF_DESIGN_SOURCE_SHA,
    HANDOFF_DOC_BLOB,
    MUTATION_BUDGET,
    OPERATION_ID,
    PERSISTENT_VOLUME,
    PUBLIC_INGEST_SCHEDULE_BLOB,
    READINESS_ENDPOINT,
    REQUIRED_EXCLUSIONS,
    RUNTIME_DESCRIPTOR_BLOB,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_ALIAS,
    WeatherPublicRuntimeAdapter,
)
from deploy_executor.weather_public_runtime_baseline import (
    EVIDENCE_SCHEMA,
    resolve_public_runtime_baseline,
)

PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
QUEUE_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "deploy_executor"
    / "queue_issue_weather_public_runtime_ready.json"
)
ADAPTER_SOURCE = (
    ROOT / "ops" / "lib" / "deploy_executor" / "weather_public_runtime_adapter.py"
)
FIXTURE_SOURCE_SHA = "a" * 40


def _queue() -> dict:
    return json.loads(QUEUE_FIXTURE.read_text(encoding="utf-8"))


def _prepared():
    registry = load_registry(PRODUCTION_REGISTRY)
    normalized = normalize_ready_queue(
        _queue(), repository_full_name=QUEUE_REPOSITORY, registry=registry
    )
    return prepare_operation(normalized)


class WeatherPublicRuntimeRegistryTests(unittest.TestCase):
    def test_operation_is_static_strict_and_globally_disabled(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        operation = next(op for op in registry.operations if op.operation_id == OPERATION_ID)
        self.assertEqual(operation.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(operation.target_alias, TARGET_ALIAS)
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.baseline.kind, "resolver")
        self.assertEqual(operation.baseline.resolver_id, BASELINE_RESOLVER_ID)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertEqual(
            tuple((row.category, row.max_operations) for row in operation.mutation_budget),
            MUTATION_BUDGET,
        )

    def test_exact_queue_selector_normalizes_without_consuming_queue_prose_as_authority(self):
        prepared = _prepared()
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.source_sha, FIXTURE_SOURCE_SHA)
        self.assertNotEqual(prepared.source_sha, HANDOFF_DESIGN_SOURCE_SHA)
        self.assertEqual(prepared.expected_baseline_kind, "resolver")
        self.assertEqual(prepared.expected_baseline_value, BASELINE_RESOLVER_ID)
        self.assertEqual(prepared.mutation_budget, MUTATION_BUDGET)
        self.assertIn(f"source-repository-id:{SOURCE_REPOSITORY_ID}", prepared.dependencies)
        self.assertIn(f"runtime-descriptor-blob:{RUNTIME_DESCRIPTOR_BLOB}", prepared.dependencies)
        self.assertIn(f"compose-public-blob:{COMPOSE_PUBLIC_BLOB}", prepared.dependencies)
        self.assertIn(
            f"public-ingest-schedule-blob:{PUBLIC_INGEST_SCHEDULE_BLOB}",
            prepared.dependencies,
        )
        self.assertIn(f"handoff-doc-blob:{HANDOFF_DOC_BLOB}", prepared.dependencies)

    def test_unreviewed_entrypoint_cannot_select_weather_operation(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        issue = _queue()
        issue["body"] = issue["body"].replace(
            "`deploy/runtime-descriptor.json`", "`/tmp/attacker-selected.sh`"
        )
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(
                issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
            )


class WeatherPublicRuntimeAdapterTests(unittest.TestCase):
    def test_adapter_catalog_preflight_binds_fixed_public_contract(self):
        adapter = WeatherPublicRuntimeAdapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(_prepared())
        self.assertEqual(preflight["result"], "WEATHER_PUBLIC_RUNTIME_SOURCE_CONTRACT_PASS")
        self.assertFalse(preflight["execution_enabled"])
        self.assertFalse(preflight["privileged_dispatch_ready"])
        self.assertTrue(preflight["requires_separate_live_authorization"])
        self.assertEqual(preflight["compose_services"], COMPOSE_SERVICES)
        self.assertEqual(preflight["persistent_volume"], PERSISTENT_VOLUME)
        self.assertEqual(preflight["database_url"], DATABASE_URL)
        self.assertEqual(preflight["readiness_endpoint"], READINESS_ENDPOINT)
        self.assertFalse(preflight["weathernext_required"])
        self.assertFalse(preflight["home_coordinates_required"])
        for forbidden in ("command", "path", "argv", "environment", "HOME_LAT", "HOME_LON"):
            self.assertNotIn(forbidden, preflight)

    def test_apply_is_always_source_disabled(self):
        with self.assertRaisesRegex(AdapterError, "execution-disabled"):
            WeatherPublicRuntimeAdapter().apply(_prepared())

    def test_adapter_rejects_identity_baseline_budget_and_exclusion_drift(self):
        prepared = _prepared()
        cases = (
            ("source_repository", "attacker/repo", "source repository"),
            ("source_sha", "not-a-sha", "source SHA"),
            ("target_alias", "attacker-target", "target alias"),
            ("expected_baseline_kind", "queue_exact", "baseline kind"),
            ("expected_baseline_value", "attacker-resolver", "baseline resolver"),
            ("mutation_budget", (("filesystem.release-materialization", 99),), "budget"),
        )
        for field, value, pattern in cases:
            bad = copy.copy(prepared)
            object.__setattr__(bad, field, value)
            with self.subTest(field=field):
                with self.assertRaisesRegex(AdapterError, pattern):
                    WeatherPublicRuntimeAdapter().preflight(bad)

        bad = copy.copy(prepared)
        exclusions = tuple(x for x in bad.exclusions if x != next(iter(REQUIRED_EXCLUSIONS)))
        object.__setattr__(bad, "exclusions", exclusions)
        with self.assertRaisesRegex(AdapterError, "exclusions"):
            WeatherPublicRuntimeAdapter().preflight(bad)

    def test_adapter_rejects_missing_handoff_dependency(self):
        prepared = _prepared()
        dependency = f"runtime-descriptor-blob:{RUNTIME_DESCRIPTOR_BLOB}"
        bad = copy.copy(prepared)
        object.__setattr__(
            bad,
            "dependencies",
            tuple(item for item in prepared.dependencies if item != dependency),
        )
        with self.assertRaisesRegex(AdapterError, "dependency mismatch"):
            WeatherPublicRuntimeAdapter().preflight(bad)

    def test_postconditions_never_claim_database_recovery_or_live_execution(self):
        post = WeatherPublicRuntimeAdapter().postconditions(_prepared())
        self.assertEqual(post["exact_application_source_sha"], FIXTURE_SOURCE_SHA)
        self.assertTrue(post["persistent_volume_retained"])
        self.assertFalse(post["sqlite_rollback_delete_restore"])
        self.assertFalse(post["automatic_retry_cleanup_rollback"])
        self.assertFalse(post["execution_enabled"])

    def test_source_has_no_execution_bridge(self):
        source = ADAPTER_SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "requests",
            "urllib",
            "socket.",
        ):
            self.assertNotIn(forbidden, source)


class WeatherPublicRuntimeBaselineTests(unittest.TestCase):
    def _evidence(self, **changes):
        value = {
            "schema": EVIDENCE_SCHEMA,
            "target_alias": TARGET_ALIAS,
            "deployment_state": "not_deployed",
            "current_source_sha": None,
            "persistent_volume_state": "absent",
            "public_ingest_schedule_state": "absent",
        }
        value.update(changes)
        return value

    def test_not_deployed_is_deterministic_and_privacy_safe(self):
        baseline = resolve_public_runtime_baseline(self._evidence())
        self.assertEqual(
            baseline.canonical_token,
            "state=not_deployed;current=none;volume=absent;schedule=absent",
        )
        self.assertNotIn("HOME_LAT", baseline.canonical_json())
        self.assertNotIn("credential", baseline.canonical_json().lower())

    def test_deployed_requires_exact_source_sha(self):
        baseline = resolve_public_runtime_baseline(
            self._evidence(
                deployment_state="deployed",
                current_source_sha="b" * 40,
                persistent_volume_state="present",
                public_ingest_schedule_state="present",
            )
        )
        self.assertEqual(baseline.current_source_sha, "b" * 40)
        with self.assertRaisesRegex(AdapterError, "40-character"):
            resolve_public_runtime_baseline(
                self._evidence(deployment_state="deployed", current_source_sha="latest")
            )

    def test_baseline_rejects_private_or_unreviewed_extra_fields(self):
        evidence = self._evidence()
        evidence["HOME_LAT"] = "forbidden"
        with self.assertRaisesRegex(AdapterError, "keys mismatch"):
            resolve_public_runtime_baseline(evidence)


if __name__ == "__main__":
    unittest.main(verbosity=2)
