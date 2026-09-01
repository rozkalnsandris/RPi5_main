from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterError, prepare_operation
from deploy_executor.dashboard_release_contract import (
    ACTIVATION_ACK,
    ADAPTER_ID,
    BASELINE_KIND,
    DashboardProductionReleaseAdapter,
)
from deploy_executor.queue_normalizer import QUEUE_REPOSITORY, QueueNormalizationError, normalize_ready_queue
from deploy_executor.registry import load_registry

PRODUCTION_REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
SOURCE_SHA = "1" * 40
CURRENT_SHA = "2" * 40
CANDIDATE_SHA256 = "a" * 64


def queue_issue(*, source_sha: str = SOURCE_SHA, current_sha: str = CURRENT_SHA, candidate: str = CANDIDATE_SHA256) -> dict:
    baseline = f"current={current_sha};candidate={candidate}"
    return {
        "number": 3380,
        "state": "open",
        "title": "[DEPLOY-QUEUE][READY] future dashboard release fixture",
        "body": "\n".join(
            (
                "## Queue contract",
                "",
                "- **source_repository:** `rozkalnsandris/dashboard_RPi5`",
                f"- **exact_git_sha_or_waiting_merge:** `{source_sha}`",
                "- **source_pr_or_issue_if_applicable:** merged `dashboard_RPi5#999`",
                "- **target_alias:** `dashboard-rpi5-production-release`",
                "- **execution_location_class:** `trusted-home-host`",
                "- **repository_entrypoint:** `tools/production-release-controller.mjs` reviewed static selector only",
                f"- **expected_baseline_when_observable:** `{baseline}` from separately accepted trusted-controller PLAN",
                "- **read_only_preflight:** exact source SHA CI, trusted current controller, staged candidate and exact PLAN binding",
                "- **verification_and_reconciliation:** exact current release and candidate digest must match authorization",
                "- **allowed_mutation_categories_and_limits:** one lock lifecycle, one release materialization, one current swap maximum",
                "- **explicit_exclusions:** no release deletion, database, credentials, permissions, services, network, cleanup or automatic retry",
                "- **dependencies_if_any:** exact trusted PLAN and source-controlled candidate staging",
                "- **deploy_class_and_extra_owner_gate_requirement:** `AUTO_DEPLOY_SAFE`; READY remains eligibility only",
                "",
                "## Evidence",
                "",
                "Source-only fixture; no live authority.",
            )
        ),
    }


class DashboardReleaseQueueTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(PRODUCTION_REGISTRY)

    def test_dashboard_operation_is_registered_but_global_execution_stays_disabled(self):
        self.assertFalse(self.registry.execution_enabled)
        operation = next(op for op in self.registry.operations if op.operation_id == ADAPTER_ID)
        self.assertEqual(operation.baseline.kind, "queue_exact")
        self.assertEqual(operation.baseline.resolver_id, BASELINE_KIND)
        self.assertTrue(operation.ordinary_live_all_eligible)

    def test_exact_plan_baseline_is_normalized_and_carried_to_prepared_operation(self):
        normalized = normalize_ready_queue(
            queue_issue(), repository_full_name=QUEUE_REPOSITORY, registry=self.registry
        )
        queue = normalized.as_protocol_queue()
        token = f"current={CURRENT_SHA};candidate={CANDIDATE_SHA256}"
        self.assertEqual(queue["expected_baseline"], {"kind": BASELINE_KIND, "value": token})
        prepared = prepare_operation(normalized)
        self.assertFalse(prepared.execution_enabled)
        self.assertEqual(prepared.expected_baseline_kind, BASELINE_KIND)
        self.assertEqual(prepared.expected_baseline_value, token)

    def test_already_current_noop_candidate_is_rejected(self):
        with self.assertRaisesRegex(QueueNormalizationError, "QUEUE_NOOP_ALREADY_CURRENT"):
            normalize_ready_queue(
                queue_issue(current_sha=SOURCE_SHA),
                repository_full_name=QUEUE_REPOSITORY,
                registry=self.registry,
            )

    def test_malformed_or_unbound_plan_baseline_is_rejected(self):
        issue = queue_issue()
        issue["body"] = issue["body"].replace(
            f"`current={CURRENT_SHA};candidate={CANDIDATE_SHA256}`",
            "`current=latest;candidate=anything`",
        )
        with self.assertRaisesRegex(QueueNormalizationError, "QUEUE_BASELINE"):
            normalize_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY, registry=self.registry)

    def test_arbitrary_repository_entrypoint_cannot_select_dashboard_adapter(self):
        issue = queue_issue()
        issue["body"] = issue["body"].replace(
            "`tools/production-release-controller.mjs`", "`/tmp/operator-selected-controller.mjs`"
        )
        with self.assertRaisesRegex(QueueNormalizationError, "UNKNOWN_OPERATION"):
            normalize_ready_queue(issue, repository_full_name=QUEUE_REPOSITORY, registry=self.registry)

    def test_candidate_digest_drift_changes_normalized_authorization_binding(self):
        first = normalize_ready_queue(
            queue_issue(), repository_full_name=QUEUE_REPOSITORY, registry=self.registry
        )
        changed = normalize_ready_queue(
            queue_issue(candidate="b" * 64), repository_full_name=QUEUE_REPOSITORY, registry=self.registry
        )
        self.assertNotEqual(first.canonical_json, changed.canonical_json)
        self.assertNotEqual(
            first.as_protocol_queue()["expected_baseline"],
            changed.as_protocol_queue()["expected_baseline"],
        )


class DashboardReleaseAdapterTests(unittest.TestCase):
    def prepared(self):
        normalized = normalize_ready_queue(
            queue_issue(), repository_full_name=QUEUE_REPOSITORY, registry=load_registry(PRODUCTION_REGISTRY)
        )
        return prepare_operation(normalized)

    def test_preflight_derives_all_privileged_paths_and_argv_from_reviewed_source(self):
        result = DashboardProductionReleaseAdapter().preflight(self.prepared())
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["privileged_dispatch_ready"])
        self.assertTrue(result["requires_separate_live_authorization"])
        self.assertEqual(
            result["controller"],
            f"/opt/dashboard_RPi5/releases/{CURRENT_SHA}/tools/production-release-controller.mjs",
        )
        self.assertEqual(
            result["candidate_root"],
            f"/var/lib/rozkalns-dashboard-release-candidates/{SOURCE_SHA}/source",
        )
        self.assertEqual(
            result["manifest"],
            f"/var/lib/rozkalns-dashboard-release-candidates/{SOURCE_SHA}/candidate-manifest.json",
        )
        argv = result["apply_argv"]
        self.assertEqual(argv[0], "/usr/bin/node")
        self.assertIn("--expected-current", argv)
        self.assertIn(CURRENT_SHA, argv)
        self.assertIn("--expected-candidate", argv)
        self.assertIn(CANDIDATE_SHA256, argv)
        self.assertEqual(argv[-2:], ("--ack", ACTIVATION_ACK))

    def test_apply_remains_source_disabled(self):
        with self.assertRaisesRegex(AdapterError, "source-disabled; separate LIVE gate required"):
            DashboardProductionReleaseAdapter().apply(self.prepared())

    def test_adapter_rejects_source_target_or_budget_drift(self):
        prepared = self.prepared()
        forged = type(prepared)(
            **{
                **prepared.__dict__,
                "target_alias": "attacker-selected-target",
            }
        )
        with self.assertRaisesRegex(AdapterError, "source/target mismatch"):
            DashboardProductionReleaseAdapter().preflight(forged)

    def test_source_contains_no_generic_execution_surface(self):
        text = (ROOT / "ops" / "lib" / "deploy_executor" / "dashboard_release_contract.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "subprocess",
            "os.system",
            "shell=True",
            "bash -c",
            "sh -c",
            "eval(",
            "socket.",
            "requests",
            "urllib",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
