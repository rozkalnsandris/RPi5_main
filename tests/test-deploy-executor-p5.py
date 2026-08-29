from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterCatalog, AdapterError, prepare_operation
from deploy_executor.cv_adapter import (
    ADAPTER_ID,
    HELPER_BLOB,
    LIBRARY_BLOB,
    OPERATION_ID,
    CvExactShaAdapter,
)
from deploy_executor.dispatch_contract import (
    AUTHORIZATION_REPOSITORY_ID,
    DispatchContractError,
    parse_dispatch_request,
)
from deploy_executor.queue_normalizer import QUEUE_REPOSITORY, normalize_ready_queue
from deploy_executor.registry import load_registry

FIXTURES = ROOT / "tests" / "fixtures" / "deploy_executor"
PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
AUDIT_REGISTRY = FIXTURES / "operations_cv_p5_audit.json"
AUDIT = ROOT / "ops" / "deploy" / "executor-interface-audit.json"
CV_QUEUE = FIXTURES / "queue_issue_cv_ready_markup.json"
POLLER_UNIT = ROOT / "ops" / "systemd" / "rozkalns-deploy-executor.service"


class P5InterfaceSecurityTests(unittest.TestCase):
    def test_production_registry_remains_disabled_with_reviewed_strict_canary(self):
        registry = load_registry(PRODUCTION_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, "hermes-deals.origin-path-audit.v1")
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)

    def test_audit_registry_has_one_dormant_cv_operation(self):
        registry = load_registry(AUDIT_REGISTRY)
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, OPERATION_ID)
        self.assertEqual(operation.adapter_id, ADAPTER_ID)
        self.assertEqual(operation.rollback_policy, "BUILTIN_TRANSACTIONAL_V1")
        self.assertEqual(
            [(row.category, row.max_operations) for row in operation.mutation_budget],
            [("rozkalns-cv.transactional-release", 1)],
        )

    def test_cv_queue_normalizes_to_audited_operation_but_stays_disabled(self):
        registry = load_registry(AUDIT_REGISTRY)
        issue = json.loads(CV_QUEUE.read_text(encoding="utf-8"))
        normalized = normalize_ready_queue(
            issue, repository_full_name=QUEUE_REPOSITORY, registry=registry
        )
        prepared = prepare_operation(normalized)
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.operation_id, OPERATION_ID)
        self.assertEqual(prepared.adapter_id, ADAPTER_ID)
        self.assertEqual(prepared.source_sha, "d25730b20c41edff29a83927bff386751f053cd0")
        self.assertEqual(prepared.rollback_policy, "BUILTIN_TRANSACTIONAL_V1")
        self.assertEqual(
            prepared.mutation_budget, (("rozkalns-cv.transactional-release", 1),)
        )
        self.assertIn(f"helper-blob:{HELPER_BLOB}", prepared.dependencies)
        self.assertIn(f"deploy-library-blob:{LIBRARY_BLOB}", prepared.dependencies)

    def test_cv_adapter_contract_preflight_passes_but_apply_is_inert(self):
        registry = load_registry(AUDIT_REGISTRY)
        issue = json.loads(CV_QUEUE.read_text(encoding="utf-8"))
        prepared = prepare_operation(
            normalize_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY, registry=registry)
        )
        adapter = CvExactShaAdapter()
        self.assertIs(AdapterCatalog((adapter,)).require(ADAPTER_ID), adapter)
        preflight = adapter.preflight(prepared)
        self.assertEqual(preflight["result"], "P5_SOURCE_CONTRACT_PASS")
        self.assertFalse(preflight["mutation_enabled"])
        with self.assertRaisesRegex(AdapterError, "mutation-disabled"):
            adapter.apply(prepared)

    def test_cv_adapter_rejects_wrong_rollback_even_while_dormant(self):
        registry = load_registry(AUDIT_REGISTRY)
        issue = json.loads(CV_QUEUE.read_text(encoding="utf-8"))
        prepared = prepare_operation(
            normalize_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY, registry=registry)
        )
        bad = copy.copy(prepared)
        object.__setattr__(bad, "rollback_policy", "NONE")
        with self.assertRaisesRegex(AdapterError, "BUILTIN_TRANSACTIONAL_V1"):
            CvExactShaAdapter().preflight(bad)

    def test_dispatch_request_contains_identity_only(self):
        request = parse_dispatch_request(
            {
                "schema": "rozkalns.deploy-dispatch-request.v1",
                "authorization_repository": "rozkalnsandris/ops-workflows",
                "authorization_repository_id": AUTHORIZATION_REPOSITORY_ID,
                "authorization_issue_id": 123456789,
                "authorization_issue_number": 123,
                "request_id": "123e4567-e89b-42d3-a456-426614174000",
            }
        )
        self.assertEqual(request.authorization_issue_number, 123)
        self.assertFalse(hasattr(request, "source_sha"))
        self.assertFalse(hasattr(request, "operation_id"))

    def test_dispatch_request_rejects_sha_command_path_or_budget_authority(self):
        base = {
            "schema": "rozkalns.deploy-dispatch-request.v1",
            "authorization_repository": "rozkalnsandris/ops-workflows",
            "authorization_repository_id": AUTHORIZATION_REPOSITORY_ID,
            "authorization_issue_id": 123456789,
            "authorization_issue_number": 123,
            "request_id": "123e4567-e89b-42d3-a456-426614174000",
        }
        for forbidden in ("source_sha", "operation_id", "command", "path", "argv", "mutation_budget"):
            value = dict(base)
            value[forbidden] = "forbidden"
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(DispatchContractError, "extra"):
                    parse_dispatch_request(value)

    def test_audit_manifest_binds_current_cross_repo_contracts(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertFalse(audit["execution_enabled"])
        self.assertEqual(
            audit["baselines"]["authorization_surface"]["repository_id"], 1328835922
        )
        self.assertEqual(
            audit["baselines"]["first_target"]["sha"],
            "d25730b20c41edff29a83927bff386751f053cd0",
        )
        self.assertFalse(audit["first_target_interface"]["direct_existing_controller_as_adapter"])
        self.assertEqual(
            audit["first_target_interface"]["required_rollback_policy"],
            "BUILTIN_TRANSACTIONAL_V1",
        )
        self.assertFalse(audit["first_target_interface"]["p5_adapter_mutation_enabled"])
        self.assertFalse(audit["result_handoff"]["github_writer_enabled"])
        self.assertFalse(audit["live_gates"]["p7_github_app_or_permission_change_authorized"])

    def test_poller_unit_is_unprivileged_and_has_no_sudo_boundary(self):
        text = POLLER_UNIT.read_text(encoding="utf-8")
        required = (
            "User=rozkalns-deploy-executor",
            "Group=rozkalns-deploy-executor",
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "RestrictNamespaces=true",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
            "ReadWritePaths=/var/lib/rozkalns-deploy-executor",
            "SystemCallFilter=@system-service",
        )
        for marker in required:
            self.assertIn(marker, text)
        lowered = text.lower()
        non_comments = "\n".join(
            line for line in lowered.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("sudo", non_comments)
        self.assertNotIn("/var/run/docker.sock", lowered)
        self.assertNotIn("bash -c", lowered)
        self.assertNotIn("sh -c", lowered)

    def test_p5_files_expose_no_generic_execution_bridge(self):
        paths = (
            ROOT / "ops" / "lib" / "deploy_executor" / "cv_adapter.py",
            ROOT / "ops" / "lib" / "deploy_executor" / "dispatch_contract.py",
        )
        forbidden = ("subprocess", "os.system", "shell=true", "bash -c", "sh -c", "eval(")
        for path in paths:
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
