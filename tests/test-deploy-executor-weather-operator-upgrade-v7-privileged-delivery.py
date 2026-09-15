#!/usr/bin/env python3
from __future__ import annotations

import ast
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_upgrade_v7_privileged_delivery as delivery
from deploy_executor.dispatch_contract import DispatchContractError

DELIVERY_CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-privileged-delivery.json"
CHECKOUT_CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v7-trusted-checkout-bootstrap.json"
REGISTRY = ROOT / "ops/deploy/executor-operations.json"
DOC = ROOT / "docs/WEATHER_OPERATOR_V7_PRIVILEGED_DELIVERY.md"
MAKEFILE = ROOT / "Makefile"
MODULE = ROOT / "ops/lib/deploy_executor/weather_operator_upgrade_v7_privileged_delivery.py"
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
SOURCE_SHA = "a" * 40


def request_payload(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "rozkalns.deploy-dispatch-request.v1",
        "authorization_repository": "rozkalnsandris/ops-workflows",
        "authorization_repository_id": 1328835922,
        "authorization_issue_id": 9000001,
        "authorization_issue_number": 24,
        "request_id": REQUEST_ID,
    }
    payload.update(extra)
    return payload


def canonical_evidence(**overrides: object) -> delivery.CanonicalWeatherV7Evidence:
    evidence = delivery.CanonicalWeatherV7Evidence(
        authorization_issue_number=24,
        request_id=REQUEST_ID,
        source_repository=delivery.SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        current_main_sha=SOURCE_SHA,
        operation_id=delivery.OPERATION_ID,
        adapter_id=delivery.ADAPTER_ID,
        target_alias=delivery.TARGET_ALIAS,
        authorization_class=delivery.AUTHORIZATION_CLASS,
        rollback_policy=delivery.ROLLBACK_POLICY,
        mutation_budget=delivery.MUTATION_BUDGET,
        owner_verified=True,
        authorization_ttl_valid=True,
        authorization_body_unchanged=True,
        replay_available=True,
        queue_ready=True,
        queue_binding_valid=True,
        source_reachable_from_main=True,
        source_ci_success=True,
        registry_execution_enabled=False,
        p8_mutation_dispatch_enabled=False,
    )
    return replace(evidence, **overrides)


def host_evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "evidence_id": "sanitized-fixture-1",
        "host_capability_installed": False,
        "trusted_checkout_name": delivery.TRUSTED_CHECKOUT_NAME,
        "trusted_checkout_state": "ABSENT",
        "trusted_checkout_origin": delivery.REVIEWED_ORIGIN,
        "trusted_checkout_source_sha": "",
        "v6_checkout_preserved": True,
        "predecessor_sha256": delivery.OLD_SHA256,
        "predecessor_owner_uid": 0,
        "predecessor_owner_gid": 0,
        "predecessor_mode": "0755",
        "target_source_sha256": delivery.NEW_SHA256,
        "protected_values_included": False,
    }
    evidence.update(overrides)
    return evidence


class StaticRevalidator:
    def __init__(self, *evidence: delivery.CanonicalWeatherV7Evidence) -> None:
        self.evidence = evidence or (canonical_evidence(),)
        self.calls = 0

    def revalidate(self, authorization_issue_number: int) -> delivery.CanonicalWeatherV7Evidence:
        if authorization_issue_number != 24:
            raise AssertionError("unexpected authorization issue")
        index = min(self.calls, len(self.evidence) - 1)
        self.calls += 1
        return self.evidence[index]


class StaticHostResolver:
    def __init__(self, evidence: dict[str, object] | None = None) -> None:
        self.evidence = evidence or host_evidence()
        self.calls = 0

    def resolve(self, *, source_sha: str) -> dict[str, object]:
        self.calls += 1
        if source_sha != SOURCE_SHA:
            raise AssertionError("unexpected source SHA")
        return dict(self.evidence)


class WeatherV7PrivilegedDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(DELIVERY_CONTRACT.read_text(encoding="utf-8"))
        cls.checkout = json.loads(CHECKOUT_CONTRACT.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.makefile = MAKEFILE.read_text(encoding="utf-8")

    def prepare(
        self,
        *,
        canonical: delivery.CanonicalWeatherV7Evidence | None = None,
        host: dict[str, object] | None = None,
        consumed: frozenset[str] = frozenset(),
    ) -> delivery.WeatherV7PrivilegedDeliveryPlan:
        return delivery.prepare_privileged_delivery(
            request_payload(),
            canonical_revalidator=StaticRevalidator(canonical or canonical_evidence()),
            host_evidence_resolver=StaticHostResolver(host or host_evidence()),
            consumed_request_ids=consumed,
        )

    def test_source_readiness_is_strict_identity_only_and_inactive(self) -> None:
        ready = delivery.source_readiness()
        self.assertEqual(ready["result"], "SOURCE_READY")
        self.assertEqual(ready["operation_id"], delivery.OPERATION_ID)
        self.assertEqual(ready["authorization_class"], "STRICT")
        self.assertFalse(ready["ordinary_live_all_eligible"])
        self.assertEqual(
            ready["request_authority"],
            (
                "authorization_repository",
                "authorization_repository_id",
                "authorization_issue_id",
                "authorization_issue_number",
                "request_id",
            ),
        )
        for key in (
            "privileged_dispatch_enabled",
            "host_capability_installed",
            "p8_mutation_dispatch_enabled",
            "global_executor_execution_enabled",
            "source_merge_authorizes_live",
            "caller_command_allowed",
            "caller_path_allowed",
            "caller_argv_allowed",
            "caller_environment_allowed",
            "caller_source_sha_allowed",
            "caller_target_allowed",
            "caller_mutation_budget_allowed",
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
            "production_mutation_started",
        ):
            self.assertFalse(ready[key], key)

    def test_registry_operation_matches_frozen_contract_and_global_execution_stays_off(self) -> None:
        self.assertFalse(self.registry["execution_enabled"])
        operations = {item["operation_id"]: item for item in self.registry["operations"]}
        self.assertIn(delivery.OPERATION_ID, operations)
        self.assertEqual(operations[delivery.OPERATION_ID], self.contract["operation"])
        operation = operations[delivery.OPERATION_ID]
        self.assertEqual(operation["authorization_class"], "STRICT")
        self.assertFalse(operation["ordinary_live_all_eligible"])
        self.assertEqual(operation["rollback_policy"], "NONE")

    def test_mutation_budget_is_exactly_one_fetch_one_worktree_add_one_replace(self) -> None:
        expected = (
            ("git.weather-operator-upgrade-v7-checkout-fetch", 1),
            ("git.weather-operator-upgrade-v7-checkout-worktree-add", 1),
            ("filesystem.weather-operator-upgrade-v7-atomic-replace", 1),
        )
        self.assertEqual(delivery.MUTATION_BUDGET, expected)
        self.assertEqual(
            tuple((item["category"], item["max_operations"]) for item in self.contract["operation"]["mutation_budget"]),
            expected,
        )
        self.assertEqual(
            tuple((item["mutation_category"], item["max_operations"]) for item in self.checkout["allowed_git_mutations"]),
            expected[:2],
        )
        self.assertEqual(
            [item["argv"] for item in self.checkout["allowed_git_mutations"]],
            [
                ["git", "fetch", "origin", "main"],
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted",
                    "EXPLICIT_WEATHER_OPERATOR_UPGRADE_V7_LIVE_EXACT_RPI5_MAIN_SHA",
                ],
            ],
        )

    def test_v6_and_older_checkouts_are_immutable_evidence(self) -> None:
        historical = {item["derivation"]: item for item in self.checkout["historical_checkouts"]}
        v6 = historical["RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted"]
        self.assertFalse(v6["mutation_allowed"])
        self.assertFalse(v6["cleanup_allowed"])
        self.assertFalse(v6["authority_source"])
        self.assertFalse(self.contract["trusted_checkout"]["v6_mutation_allowed"])
        self.assertFalse(self.contract["trusted_checkout"]["v6_cleanup_allowed"])
        self.assertIn("worktree remove", self.checkout["forbidden_git_operations"])
        self.assertIn("worktree prune", self.checkout["forbidden_git_operations"])

    def test_p8_or_global_execution_enablement_is_rejected(self) -> None:
        for changed in (
            canonical_evidence(p8_mutation_dispatch_enabled=True),
            canonical_evidence(registry_execution_enabled=True),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
                    self.prepare(canonical=changed)

    def test_wrong_operation_target_or_source_binding_is_rejected(self) -> None:
        fixtures = (
            canonical_evidence(operation_id="other.operation"),
            canonical_evidence(target_alias="other-target"),
            canonical_evidence(source_sha="b" * 40, source_reachable_from_main=False),
        )
        for changed in fixtures:
            with self.subTest(changed=changed):
                with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
                    self.prepare(canonical=changed)

    def test_wrong_checkout_name_state_or_origin_is_rejected(self) -> None:
        fixtures = (
            host_evidence(trusted_checkout_name="other-checkout"),
            host_evidence(trusted_checkout_state="ATTACHED"),
            host_evidence(trusted_checkout_state="DIRTY"),
            host_evidence(trusted_checkout_origin="https://example.invalid/RPi5_main.git"),
        )
        for changed in fixtures:
            with self.subTest(changed=changed):
                with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
                    self.prepare(host=changed)

    def test_predecessor_metadata_or_target_source_hash_drift_is_rejected(self) -> None:
        fixtures = (
            host_evidence(predecessor_sha256="0" * 64),
            host_evidence(predecessor_owner_uid=1000),
            host_evidence(predecessor_owner_gid=1000),
            host_evidence(predecessor_mode="0777"),
            host_evidence(target_source_sha256="f" * 64),
        )
        for changed in fixtures:
            with self.subTest(changed=changed):
                with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
                    self.prepare(host=changed)

    def test_arbitrary_command_path_argv_env_and_source_fields_are_rejected(self) -> None:
        for key, value in (
            ("command", "id"),
            ("path", "/tmp/other"),
            ("argv", ["--force"]),
            ("environment", {"X": "Y"}),
            ("source_sha", SOURCE_SHA),
            ("target", "/tmp/other"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(DispatchContractError):
                    delivery.prepare_privileged_delivery(
                        request_payload(**{key: value}),
                        canonical_revalidator=StaticRevalidator(),
                        host_evidence_resolver=StaticHostResolver(),
                    )

    def test_duplicate_or_replayed_request_is_rejected(self) -> None:
        with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
            self.prepare(consumed=frozenset({REQUEST_ID}))

    def test_canonical_evidence_drift_between_double_revalidation_is_rejected(self) -> None:
        first = canonical_evidence()
        second = canonical_evidence(current_main_sha="b" * 40)
        with self.assertRaises(delivery.WeatherOperatorV7DeliveryError):
            delivery.prepare_privileged_delivery(
                request_payload(),
                canonical_revalidator=StaticRevalidator(first, second),
                host_evidence_resolver=StaticHostResolver(),
            )

    def test_source_ready_distinguishes_host_capability_and_checkout_states(self) -> None:
        self.assertEqual(self.prepare().result, "HOST_CAPABILITY_INSTALL_REQUIRED")
        self.assertEqual(
            self.prepare(host=host_evidence(host_capability_installed=True)).result,
            "FUTURE_LIVE_CHECKOUT_BOOTSTRAP_READY",
        )
        self.assertEqual(
            self.prepare(
                host=host_evidence(
                    host_capability_installed=True,
                    trusted_checkout_state="EXACT_SHA_DETACHED_CLEAN",
                    trusted_checkout_source_sha=SOURCE_SHA,
                )
            ).result,
            "FUTURE_LIVE_FIXED_OPERATOR_READY",
        )

    def test_delivery_module_has_no_generic_privileged_execution_surface(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertTrue({"os", "subprocess", "shutil", "pathlib"}.isdisjoint(imported))
        self.assertFalse(self.contract["host_capability"]["privileged_dispatch_enabled"])
        self.assertFalse(self.contract["host_capability"]["global_executor_execution_enabled"])
        self.assertFalse(self.contract["source_merge_authorizes_live"])
        self.assertFalse(self.contract["production_mutation_started"])

    def test_documented_owner_gate_order_and_validate_wiring_are_explicit(self) -> None:
        ordered = (
            "source merge + exact-main CI",
            "one-time privileged-boundary host install/upgrade",
            "sanitized capability verification",
            "fresh exact Weather v7 LIVE authorization",
            "installed-closure verification",
            "rozkalns_weather public rollout reconciliation",
        )
        positions = [self.doc.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("P8 remains mutation-disabled", self.doc)
        self.assertIn("Source merge does not authorize LIVE", self.doc)
        self.assertIn(
            "python3 ./tests/test-deploy-executor-weather-operator-upgrade-v7-privileged-delivery.py",
            self.makefile,
        )


if __name__ == "__main__":
    unittest.main()
