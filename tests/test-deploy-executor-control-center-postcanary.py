from __future__ import annotations

import copy
import importlib.util
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
SOURCE_SHA = "f04601dfd47e5691c875c0935b36ff101680f4dd"
EXPECTED_WORKFLOW_SOURCE_BLOB = "48a55c05eae0daee72d87abf66e04ea5b872dd58"
STALE_WORKFLOW_SOURCE_BLOB = "84b060b364fb5e9d824cf0d43e4f81c8ec6ea449"
CI_RUN_ID = 33380350418


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
                            "id": CI_RUN_ID,
                            "head_sha": SOURCE_SHA,
                            "head_branch": "main",
                            "status": "completed",
                            "conclusion": "success" if self.ci_success else "failure",
                        }
                    ]
                }
            )
        if path == f"/repos/{SOURCE_REPOSITORY}/actions/runs/{CI_RUN_ID}/jobs?filter=latest&per_page=100":
            return Response({"jobs": [{"status": "completed", "conclusion": "success"}]})
        raise AssertionError(path)


class ControlCenterPostCanaryTests(unittest.TestCase):
    def test_production_registry_matches_reviewed_control_fixture_and_is_dormant(self):
        raw = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
        reviewed = json.loads(CANARY_REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], reviewed["schema_version"])
        self.assertEqual(raw["execution_enabled"], reviewed["execution_enabled"])
        control_raw = next(
            item for item in raw["operations"] if item["operation_id"] == OPERATION_ID
        )
        self.assertEqual(control_raw, reviewed["operations"][0])

        registry = load_registry(PRODUCTION_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        operations = {item.operation_id: item for item in registry.operations}
        self.assertIn(OPERATION_ID, operations)
        operation = operations[OPERATION_ID]
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
        self.assertNotIn(
            f"workflow-source-blob:{STALE_WORKFLOW_SOURCE_BLOB}", prepared.dependencies
        )
        self.assertIn("p9-trigger-dispatch:prohibited", prepared.dependencies)

    def test_workflow_provenance_accepts_only_reviewed_control_496_blob(self):
        self.assertEqual(WORKFLOW_SOURCE_BLOB, EXPECTED_WORKFLOW_SOURCE_BLOB)
        self.assertNotEqual(WORKFLOW_SOURCE_BLOB, STALE_WORKFLOW_SOURCE_BLOB)
        prepared = _prepared()
        for unreviewed in (STALE_WORKFLOW_SOURCE_BLOB, "0" * 40):
            with self.subTest(unreviewed=unreviewed):
                drifted = copy.copy(prepared)
                object.__setattr__(
                    drifted,
                    "dependencies",
                    tuple(
                        (
                            f"workflow-source-blob:{unreviewed}"
                            if item == f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}"
                            else item
                        )
                        for item in prepared.dependencies
                    ),
                )
                with self.assertRaisesRegex(
                    AdapterError, "source/interface dependency mismatch"
                ):
                    ControlCenterPostCanaryAdapter().preflight(drifted)

    def test_adapter_preflight_is_local_read_only_and_apply_is_inert(self):
        prepared = _prepared()
        adapter = ControlCenterPostCanaryAdapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(prepared)
        self.assertEqual(preflight["result"], "SOURCE_CANARY_CONTRACT_PASS")
        self.assertEqual(preflight["workflow_path"], WORKFLOW_PATH)
        self.assertEqual(preflight["workflow_source_blob"], EXPECTED_WORKFLOW_SOURCE_BLOB)
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
        self.assertEqual(evidence.run_id, CI_RUN_ID)

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

OPERATOR = (
    ROOT
    / "scripts"
    / "install-deploy-executor-p9-gate-d-control-workflow-provenance-upgrade.py"
)


def _load_operator():
    spec = importlib.util.spec_from_file_location(
        "p9_gate_d_control_workflow_provenance_upgrade", OPERATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class P9GateDControlWorkflowProvenanceUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_operator()
        cls.source = OPERATOR.read_text(encoding="utf-8")

    def test_exact_one_target_contract_uses_current_adapter_as_expected_prestate(self):
        target = self.module.TARGET
        self.assertEqual(
            (
                target.source_path,
                str(target.target_path),
                target.old_blob_sha,
                target.mode,
            ),
            (
                "ops/lib/deploy_executor/control_center_postcanary_adapter.py",
                "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/control_center_postcanary_adapter.py",
                "2a92f7fc0994b37f9625cb1c1178be98215e83e5",
                0o644,
            ),
        )
        self.assertNotIn("rozkalns-deploy-p9-control-baseline", self.source)
        self.assertNotIn("p9_control_postcanary_collector.py", self.source)

    def test_operator_preflight_proves_exact_source_and_old_adapter_before_apply(self):
        source = self.source
        marker = "Final duplicate gate before the first live mutation"
        preflight = source[: source.index(marker)]
        self.assertIn("_require_exact_source(expected_sha)", preflight)
        self.assertIn("_require_target_prestate()", preflight)
        self.assertIn("_require_parent_chain_safe(TARGET.target_path)", preflight)
        self.assertIn(
            '_run_git("show", f"{expected_sha}:{TARGET.source_path}", capture=True)',
            preflight,
        )
        self.assertIn("if not args.apply:", preflight)
        self.assertIn(
            "P9_GATE_D_CONTROL_WORKFLOW_PROVENANCE_MUTATION=NO", preflight
        )
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_operator_mutation_is_one_target_in_place_and_non_retrying(self):
        source = self.source
        marker = "A separately owner-authorized one-target live mutation begins here"
        mutation = source[source.index(marker):]
        for operation in (
            "os.ftruncate(fd, 0)",
            "_write_fd_all(fd, reviewed_bytes)",
            "os.fchmod(fd, TARGET.mode)",
            "os.fchown(fd, 0, 0)",
            "os.fsync(fd)",
        ):
            self.assertIn(operation, mutation)
        for forbidden in (
            "os.replace",
            "os.rename",
            "os.unlink",
            "shutil",
            "tempfile",
            "mkstemp",
            "for attempt",
            "while attempt",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("TARGETS_REPLACED=1", source)
        self.assertIn("ROLLBACK_PATH=NO", source)
        self.assertIn("RETRY_PATH=NO", source)

    def test_operator_has_no_network_credential_baseline_or_config_path(self):
        source = self.source
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "curl",
            "wget",
            "gh ",
            "Authorization:",
            "control-d1-read-token",
            "github-app.pem",
            "systemctl",
            "StateStore",
            "executor-operations.json",
            "cloudflare",
        ):
            self.assertNotIn(forbidden, source)
        for marker in (
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "SYSTEMD_MUTATION=NO",
            "CONFIG_REGISTRY_MUTATION=NO",
            "BASELINE_CLI_TOUCHED=NO",
            "COLLECTOR_TOUCHED=NO",
        ):
            self.assertIn(marker, source)

    def test_operator_revalidates_open_inode_before_first_truncate(self):
        source = self.source
        fn = source[
            source.index("def _replace_exact_target") :
            source.index("def _parse_args")
        ]
        truncate_at = fn.index("os.ftruncate(fd, 0)")
        self.assertLess(fn.index("os.fstat(fd)"), truncate_at)
        self.assertLess(fn.index("_git_blob_sha(current)"), truncate_at)
        self.assertLess(
            fn.index("os.stat(TARGET.target_path, follow_symlinks=False)"),
            truncate_at,
        )
        self.assertIn("os.O_NOFOLLOW", fn)
        self.assertGreater(
            fn.index("if _read_fd_all(fd) != reviewed_bytes"),
            truncate_at,
        )


if __name__ == "__main__":
    unittest.main()
