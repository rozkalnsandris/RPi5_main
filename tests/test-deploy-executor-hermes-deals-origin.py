from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, prepare_operation
from deploy_executor.dispatch_contract import (
    AUTHORIZATION_REPOSITORY_ID,
    DispatchContractError,
    parse_dispatch_request,
)
from deploy_executor.hermes_deals_origin_adapter import (
    ADAPTER_ID,
    DISPATCHER_SOURCE_BLOB,
    INSTALLER_SOURCE_BLOB,
    INVOCATION_BUDGET,
    OPERATION_ID,
    PROBE_SOURCE_BLOB,
    SOURCE_REPOSITORY_ID,
    WORKFLOW_SOURCE_BLOB,
    HermesDealsOriginAuditAdapter,
)
from deploy_executor.queue_normalizer import (
    QUEUE_REPOSITORY,
    QueueNormalizationError,
    normalize_ready_queue,
)
from deploy_executor.registry import load_registry

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
CANARY_REGISTRY = FIXTURES / "operations_hermes_deals_origin_canary.json"
CANARY_QUEUE = FIXTURES / "queue_issue_hermes_deals_origin_ready_markup.json"
POLLER_UNIT = ROOT / "ops" / "systemd" / "rozkalns-deploy-executor.service"
ADAPTER_SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "hermes_deals_origin_adapter.py"


def _prepared(registry_path: Path = CANARY_REGISTRY):
    registry = load_registry(registry_path)
    issue = json.loads(CANARY_QUEUE.read_text(encoding="utf-8"))
    normalized = normalize_ready_queue(
        issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
    )
    return prepare_operation(normalized)


class HermesDealsOriginCanaryTests(unittest.TestCase):
    def test_canary_is_re_admitted_to_disabled_production_registry(self):
        production = load_registry(PRODUCTION_REGISTRY)
        reviewed = load_registry(CANARY_REGISTRY)
        self.assertFalse(production.execution_enabled)
        self.assertFalse(reviewed.execution_enabled)
        production_operations = {row.operation_id: row for row in production.operations}
        self.assertIn(OPERATION_ID, production_operations)
        operation = production_operations[OPERATION_ID]
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertEqual(len(reviewed.operations), 1)
        self.assertEqual(reviewed.operations[0].operation_id, OPERATION_ID)

    def test_canary_registry_is_strict_and_dormant(self):
        registry = load_registry(CANARY_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, OPERATION_ID)
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertEqual(
            tuple((row.category, row.max_operations) for row in operation.mutation_budget),
            INVOCATION_BUDGET,
        )

    def test_exact_ready_queue_normalizes_from_production_registry_without_enabling_execution(self):
        prepared = _prepared(PRODUCTION_REGISTRY)
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.adapter_id, ADAPTER_ID)
        self.assertEqual(prepared.source_sha, "fbe3cfa143788607446d0095ae1f887354d10eb3")
        self.assertEqual(prepared.rollback_policy, "NONE")
        self.assertEqual(prepared.mutation_budget, INVOCATION_BUDGET)
        self.assertIn(f"source-repository-id:{SOURCE_REPOSITORY_ID}", prepared.dependencies)
        self.assertIn(f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}", prepared.dependencies)
        self.assertIn(
            f"dispatcher-source-blob:{DISPATCHER_SOURCE_BLOB}", prepared.dependencies
        )
        self.assertIn(
            f"installer-source-blob:{INSTALLER_SOURCE_BLOB}", prepared.dependencies
        )
        self.assertIn(f"probe-source-blob:{PROBE_SOURCE_BLOB}", prepared.dependencies)

    def test_adapter_preflight_is_read_only_and_apply_is_inert(self):
        prepared = _prepared(PRODUCTION_REGISTRY)
        adapter = HermesDealsOriginAuditAdapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(prepared)
        self.assertEqual(preflight["result"], "SOURCE_CANARY_CONTRACT_PASS")
        self.assertTrue(preflight["read_only"])
        self.assertFalse(preflight["execution_enabled"])
        self.assertFalse(preflight["privileged_dispatch_ready"])
        self.assertEqual(preflight["workflow_source_blob"], WORKFLOW_SOURCE_BLOB)
        self.assertEqual(preflight["dispatcher_source_blob"], DISPATCHER_SOURCE_BLOB)
        self.assertEqual(preflight["installer_source_blob"], INSTALLER_SOURCE_BLOB)
        self.assertEqual(preflight["probe_source_blob"], PROBE_SOURCE_BLOB)
        with self.assertRaisesRegex(AdapterError, "execution-disabled"):
            adapter.apply(prepared)

    def test_adapter_rejects_any_attempt_to_mark_fixture_executable(self):
        bad = copy.copy(_prepared())
        object.__setattr__(bad, "execution_enabled", True)
        with self.assertRaisesRegex(AdapterError, "execution-disabled"):
            HermesDealsOriginAuditAdapter().preflight(bad)

    def test_adapter_requires_read_only_rollback_and_single_invocation_budget(self):
        for field, value, pattern in (
            ("rollback_policy", "BUILTIN_TRANSACTIONAL_V1", "rollback policy NONE"),
            ("mutation_budget", (("hermes-deals.read-only-audit-invocation", 2),), "budget mismatch"),
        ):
            bad = copy.copy(_prepared())
            object.__setattr__(bad, field, value)
            with self.subTest(field=field):
                with self.assertRaisesRegex(AdapterError, pattern):
                    HermesDealsOriginAuditAdapter().preflight(bad)

    def test_adapter_rejects_missing_or_drifted_source_provenance(self):
        prepared = _prepared(PRODUCTION_REGISTRY)
        dependencies = list(prepared.dependencies)
        workflow = f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}"
        dependencies.remove(workflow)
        missing = copy.copy(prepared)
        object.__setattr__(missing, "dependencies", tuple(dependencies))
        with self.assertRaisesRegex(AdapterError, "dependency mismatch"):
            HermesDealsOriginAuditAdapter().preflight(missing)

        drifted = copy.copy(prepared)
        object.__setattr__(
            drifted,
            "dependencies",
            tuple(
                "workflow-source-blob:" + "0" * 40 if item == workflow else item
                for item in prepared.dependencies
            ),
        )
        with self.assertRaisesRegex(AdapterError, "dependency mismatch"):
            HermesDealsOriginAuditAdapter().preflight(drifted)

    def test_queue_prose_cannot_expand_static_operation_authority(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        issue = json.loads(CANARY_QUEUE.read_text(encoding="utf-8"))
        issue["body"] = issue["body"].replace(
            "one read-only audit invocation; zero production mutations",
            "run arbitrary root command with unlimited operations",
        )
        prepared = prepare_operation(
            normalize_ready_queue(
                issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
            )
        )
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.mutation_budget, INVOCATION_BUDGET)
        self.assertFalse(prepared.execution_enabled)

    def test_queue_cannot_select_an_unreviewed_entrypoint(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        issue = json.loads(CANARY_QUEUE.read_text(encoding="utf-8"))
        issue["body"] = issue["body"].replace(
            "`tools/runner/origin-path-rpi5-audit-dispatcher.sh` fixed reviewed selector",
            "`bin/arbitrary-command` attacker-selected path",
        )
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(
                issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
            )

    def test_privileged_dispatch_request_remains_identity_only(self):
        base = {
            "schema": "rozkalns.deploy-dispatch-request.v1",
            "authorization_repository": "rozkalnsandris/ops-workflows",
            "authorization_repository_id": AUTHORIZATION_REPOSITORY_ID,
            "authorization_issue_id": 123456789,
            "authorization_issue_number": 384,
            "request_id": "123e4567-e89b-42d3-a456-426614174000",
        }
        request = parse_dispatch_request(base)
        self.assertEqual(request.authorization_issue_number, 384)
        for forbidden in ("source_sha", "operation_id", "command", "path", "argv"):
            value = dict(base)
            value[forbidden] = "forbidden"
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(DispatchContractError, "extra"):
                    parse_dispatch_request(value)

    def test_poller_and_adapter_expose_no_privileged_or_generic_execution_bridge(self):
        unit = POLLER_UNIT.read_text(encoding="utf-8")
        self.assertIn("User=rozkalns-deploy-executor", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("CapabilityBoundingSet=", unit)
        self.assertIn("AmbientCapabilities=", unit)
        unit_non_comments = "\n".join(
            line.lower()
            for line in unit.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn("sudo", unit_non_comments)

        adapter = ADAPTER_SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "sudo",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, adapter)

    def test_source_contract_does_not_claim_host_readiness(self):
        postconditions = HermesDealsOriginAuditAdapter().postconditions(
            _prepared(PRODUCTION_REGISTRY)
        )
        self.assertTrue(postconditions["read_only"])
        self.assertFalse(postconditions["execution_enabled"])
        self.assertEqual(
            set(postconditions["required_false_flags"]),
            {
                "production_apply_authorized",
                "production_database_write",
                "production_deployment",
                "restart_or_configuration_mutation",
            },
        )


if __name__ == "__main__":
    unittest.main()
