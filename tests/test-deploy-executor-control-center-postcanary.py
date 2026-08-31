from __future__ import annotations

import copy
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, prepare_operation
from deploy_executor.control_center_postcanary_adapter import (
    ADAPTER_ID,
    INVOCATION_BUDGET,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_ALIAS,
    WORKFLOW_PATH,
    WORKFLOW_SOURCE_BLOB,
    ControlCenterPostCanaryAdapter,
)
from deploy_executor.queue_normalizer import (
    QUEUE_REPOSITORY,
    QueueNormalizationError,
    normalize_ready_queue,
)
from deploy_executor.registry import load_registry
from deploy_executor.source_evidence import verify_source_evidence

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
CANARY_REGISTRY = FIXTURES / "operations_control_center_postcanary_canary.json"
CANARY_QUEUE = FIXTURES / "queue_issue_control_center_postcanary_ready_markup.json"
ADAPTER_SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "control_center_postcanary_adapter.py"
SOURCE_SHA = "f9b900a884bffda993197fc7fa9223c886e11a90"


def _prepared():
    registry = load_registry(PRODUCTION_REGISTRY)
    issue = json.loads(CANARY_QUEUE.read_text(encoding="utf-8"))
    normalized = normalize_ready_queue(
        issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
    )
    return prepare_operation(normalized)


@dataclass
class Response:
    value: object


class ControlSourceClient:
    def __init__(self, *, repository_id=SOURCE_REPOSITORY_ID, ci_success=True):
        self.repository_id = repository_id
        self.ci_success = ci_success
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path == f"/repos/{SOURCE_REPOSITORY}":
            return Response(
                {
                    "id": self.repository_id,
                    "full_name": SOURCE_REPOSITORY,
                    "default_branch": "main",
                }
            )
        if path == f"/repos/{SOURCE_REPOSITORY}/branches/main":
            return Response({"commit": {"sha": SOURCE_SHA}})
        if path == (
            f"/repos/{SOURCE_REPOSITORY}/actions/workflows/ci.yml/runs"
            f"?branch=main&head_sha={SOURCE_SHA}&status=completed&per_page=100"
        ):
            return Response(
                {
                    "workflow_runs": [
                        {
                            "id": 33302808439,
                            "head_sha": SOURCE_SHA,
                            "head_branch": "main",
                            "status": "completed",
                            "conclusion": "success" if self.ci_success else "failure",
                        }
                    ]
                }
            )
        if path == f"/repos/{SOURCE_REPOSITORY}/actions/runs/33302808439/jobs?filter=latest&per_page=100":
            return Response({"jobs": [{"status": "completed", "conclusion": "success"}]})
        raise AssertionError(path)


class ControlCenterPostCanaryTests(unittest.TestCase):
    def test_production_registry_matches_reviewed_control_fixture_and_is_dormant(self):
        raw = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
        reviewed = json.loads(CANARY_REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(raw, reviewed)
        registry = load_registry(PRODUCTION_REGISTRY)
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

    def test_exact_ready_fixture_selects_control_operation_without_enabling_execution(self):
        prepared = _prepared()
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.adapter_id, ADAPTER_ID)
        self.assertEqual(prepared.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(prepared.source_sha, SOURCE_SHA)
        self.assertEqual(prepared.target_alias, TARGET_ALIAS)
        self.assertEqual(prepared.rollback_policy, "NONE")
        self.assertEqual(prepared.mutation_budget, INVOCATION_BUDGET)
        self.assertIn(f"source-repository-id:{SOURCE_REPOSITORY_ID}", prepared.dependencies)
        self.assertIn(f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}", prepared.dependencies)
        self.assertIn("p9-trigger-dispatch:prohibited", prepared.dependencies)

    def test_adapter_preflight_is_local_read_only_and_apply_is_inert(self):
        prepared = _prepared()
        adapter = ControlCenterPostCanaryAdapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(prepared)
        self.assertEqual(preflight["result"], "SOURCE_CANARY_CONTRACT_PASS")
        self.assertEqual(preflight["workflow_path"], WORKFLOW_PATH)
        self.assertEqual(preflight["workflow_source_blob"], WORKFLOW_SOURCE_BLOB)
        self.assertTrue(preflight["read_only"])
        self.assertFalse(preflight["execution_enabled"])
        self.assertFalse(preflight["privileged_dispatch_ready"])
        self.assertFalse(preflight["mutation_enabled"])
        self.assertFalse(preflight["production_apply_authorized"])
        with self.assertRaisesRegex(AdapterError, "must not post"):
            adapter.apply(prepared)

    def test_adapter_rejects_execution_enablement_or_budget_widening(self):
        prepared = _prepared()
        enabled = copy.copy(prepared)
        object.__setattr__(enabled, "execution_enabled", True)
        with self.assertRaisesRegex(AdapterError, "execution-disabled"):
            ControlCenterPostCanaryAdapter().preflight(enabled)

        widened = copy.copy(prepared)
        object.__setattr__(
            widened,
            "mutation_budget",
            (("control-center.read-only-reconciliation-run", 2),),
        )
        with self.assertRaisesRegex(AdapterError, "budget mismatch"):
            ControlCenterPostCanaryAdapter().preflight(widened)

    def test_queue_cannot_select_unreviewed_workflow_entrypoint(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        issue = json.loads(CANARY_QUEUE.read_text(encoding="utf-8"))
        issue["body"] = issue["body"].replace(
            f"`{WORKFLOW_PATH}` fixed reviewed selector",
            "`.github/workflows/arbitrary.yml` attacker-selected path",
        )
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(
                issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
            )

    def test_control_source_identity_and_exact_main_ci_are_allowlisted(self):
        client = ControlSourceClient()
        evidence = verify_source_evidence(
            client,
            source_repository=SOURCE_REPOSITORY,
            source_sha=SOURCE_SHA,
        )
        self.assertEqual(evidence.repository_id, SOURCE_REPOSITORY_ID)
        self.assertEqual(evidence.source_sha, SOURCE_SHA)
        self.assertEqual(evidence.current_main_sha, SOURCE_SHA)
        self.assertEqual(evidence.workflow, "ci.yml")
        self.assertEqual(evidence.run_id, 33302808439)

    def test_control_adapter_exposes_no_command_or_trigger_execution_bridge(self):
        source = ADAPTER_SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "curl",
            "workflow_dispatch",
            "add_comment",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_postconditions_preserve_zero_mutation_flags(self):
        postconditions = ControlCenterPostCanaryAdapter().postconditions(_prepared())
        self.assertTrue(postconditions["read_only"])
        self.assertFalse(postconditions["execution_enabled"])
        self.assertFalse(postconditions["privileged_dispatch_ready"])
        self.assertEqual(
            set(postconditions["required_false_flags"]),
            {
                "MERGE_POST_SENT",
                "REMOTE_D1_MUTATION",
                "WORKER_MUTATION",
                "CLOUDFLARE_CONFIG_MUTATION",
                "GITHUB_DECISION_MUTATION",
                "GITHUB_APP_PERMISSION_MUTATION",
            },
        )


if __name__ == "__main__":
    unittest.main()
