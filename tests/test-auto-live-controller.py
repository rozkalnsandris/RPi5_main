from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.auto_live_controller import (
    MAX_COMPARE_FILES,
    _verify_source_contracts,
    reconcile_once,
)

DASHBOARD = "ops/deploy/auto-live-manifests/dashboard-rpi5.json"
WEATHER = "ops/deploy/auto-live-manifests/rozkalns-weather.json"
BASELINE = "a" * 40
TARGET = "b" * 40
OLDER_TARGET = "c" * 40


class FakeGitHub:
    def __init__(
        self,
        *,
        repository: str,
        workflow_path: str,
        workflow_name: str,
        required_gate: str,
        paths: list[str],
        current_main: str = TARGET,
        ci_success: bool = True,
        target_reachable: bool = True,
        compare_status: str = "ahead",
        compare_files: list[dict[str, object]] | None = None,
    ):
        self.repository = repository
        self.workflow_path = workflow_path
        self.workflow_name = workflow_name
        self.required_gate = required_gate
        self.paths = paths
        self.current_main = current_main
        self.ci_success = ci_success
        self.target_reachable = target_reachable
        self.compare_status = compare_status
        self.compare_files = compare_files
        self.calls: list[str] = []

    def get_json(self, path: str):
        self.calls.append(path)
        if path == f"/repos/{self.repository}":
            return SimpleNamespace(
                value={"full_name": self.repository, "default_branch": "main"}
            )
        if path == f"/repos/{self.repository}/branches/main":
            return SimpleNamespace(value={"commit": {"sha": self.current_main}})
        if "/compare/" in path:
            suffix = path.split("/compare/", 1)[1]
            if suffix.startswith(f"{OLDER_TARGET}...{self.current_main}"):
                status = "ahead" if self.target_reachable else "diverged"
                return SimpleNamespace(value={"status": status, "files": []})
            files = self.compare_files
            if files is None:
                files = [{"filename": item, "status": "modified"} for item in self.paths]
            return SimpleNamespace(
                value={
                    "status": self.compare_status,
                    "files": files,
                }
            )
        if "/actions/runs?" in path:
            rows = []
            if self.ci_success:
                rows.append(
                    {
                        "id": 9001,
                        "head_sha": TARGET,
                        "path": self.workflow_path,
                        "name": self.workflow_name,
                        "event": "push",
                        "head_branch": "main",
                        "conclusion": "success",
                    }
                )
            return SimpleNamespace(
                value={"total_count": len(rows), "workflow_runs": rows}
            )
        if path.endswith("/actions/runs/9001/jobs?per_page=100"):
            return SimpleNamespace(
                value={
                    "total_count": 1,
                    "jobs": [{"name": self.required_gate, "conclusion": "success"}],
                }
            )
        raise AssertionError(path)


def dashboard_github(paths: list[str], **kwargs) -> FakeGitHub:
    return FakeGitHub(
        repository="rozkalnsandris/dashboard_RPi5",
        workflow_path=".github/workflows/ci.yml",
        workflow_name="CI",
        required_gate="FAST-LANE Merge Gate",
        paths=paths,
        **kwargs,
    )


def weather_github(paths: list[str], **kwargs) -> FakeGitHub:
    return FakeGitHub(
        repository="rozkalnsandris/rozkalns_weather",
        workflow_path=".github/workflows/tests.yml",
        workflow_name="Backend tests",
        required_gate="pytest",
        paths=paths,
        **kwargs,
    )


class AutoLiveControllerTests(unittest.TestCase):
    def reconcile_dashboard(self, paths: list[str], **kwargs):
        github = dashboard_github(paths, **kwargs)
        result = reconcile_once(
            github=github,
            root=ROOT,
            manifest_relative_path=DASHBOARD,
            production_baseline_sha=BASELINE,
        )
        return result, github

    def assert_read_only(self, result):
        self.assertFalse(result.automatic_mutation_allowed)
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.production_mutation_started)
        self.assertEqual(result.manifest_activation_state, "INACTIVE_SOURCE_ONLY")

    def test_source_contract_binds_a2_manifest_registry_and_shared_policy(self):
        controller, manifest, operation = _verify_source_contracts(
            root=ROOT,
            manifest_relative_path=DASHBOARD,
        )
        self.assertEqual(controller["status"], "A3_SOURCE_ONLY_MUTATION_DISABLED")
        self.assertFalse(controller["execution_enabled"])
        self.assertEqual(
            controller["shared_policy_commit_sha"],
            "f2aeb5152371a876268bb116bb98806cddbc8e15",
        )
        self.assertEqual(operation.operation_id, manifest["static_operation_id"])
        self.assertEqual(operation.source_repository, manifest["source_repository"])
        self.assertEqual(operation.target_alias, manifest["target_alias"])

    def test_dashboard_full_range_no_deploy(self):
        result, _github = self.reconcile_dashboard(["docs/OPERATIONS.md"])
        self.assertEqual(result.decision, "NO_DEPLOY")
        self.assertEqual(result.classification, "NO_DEPLOY")
        self.assert_read_only(result)

    def test_dashboard_full_range_auto_safe_is_decision_only(self):
        result, _github = self.reconcile_dashboard(["apps/web/src/example.tsx"])
        self.assertEqual(result.decision, "AUTO_DEPLOY_SAFE")
        self.assertEqual(result.classification, "AUTO_DEPLOY_SAFE")
        self.assertEqual(result.reason, "READ_ONLY_SAFE_DECISION")
        self.assert_read_only(result)

    def test_dashboard_manual_and_db_host_ranges_require_owner(self):
        for path, expected in (
            ("apps/server/src/example.ts", "MANUAL_ROLLOUT_REQUIRED"),
            ("ops/production/example.json", "DB_HOST_APPLY_REQUIRED"),
        ):
            with self.subTest(path=path):
                result, _github = self.reconcile_dashboard([path])
                self.assertEqual(result.decision, "OWNER_REQUIRED")
                self.assertEqual(result.classification, expected)
                self.assert_read_only(result)

    def test_mixed_range_uses_highest_precedence(self):
        result, _github = self.reconcile_dashboard(
            ["apps/web/src/example.tsx", "ops/production/example.json"]
        )
        self.assertEqual(result.decision, "OWNER_REQUIRED")
        self.assertEqual(result.classification, "DB_HOST_APPLY_REQUIRED")
        self.assert_read_only(result)

    def test_unknown_path_fails_closed_before_ci(self):
        result, github = self.reconcile_dashboard(["unclassified.future"])
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "UNMATCHED_OR_AMBIGUOUS_CHANGED_PATH")
        self.assertFalse(any("/actions/runs?" in call for call in github.calls))
        self.assert_read_only(result)

    def test_rename_classifies_previous_and_current_paths(self):
        result, _github = self.reconcile_dashboard(
            [],
            compare_files=[
                {
                    "filename": "docs/deploy.yml",
                    "previous_filename": ".github/workflows/deploy.yml",
                    "status": "renamed",
                }
            ],
        )
        self.assertEqual(result.decision, "OWNER_REQUIRED")
        self.assertEqual(result.classification, "DB_HOST_APPLY_REQUIRED")
        self.assertEqual(
            result.changed_paths,
            (".github/workflows/deploy.yml", "docs/deploy.yml"),
        )
        self.assert_read_only(result)

    def test_rename_without_previous_filename_fails_closed(self):
        result, _github = self.reconcile_dashboard(
            [],
            compare_files=[{"filename": "docs/deploy.yml", "status": "renamed"}],
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "FULL_RANGE_COMPARE_INCOMPLETE_OR_NOT_AHEAD")
        self.assert_read_only(result)

    def test_unknown_compare_file_status_fails_closed(self):
        result, _github = self.reconcile_dashboard(
            [],
            compare_files=[{"filename": "apps/web/src/example.tsx", "status": "unknown"}],
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "FULL_RANGE_COMPARE_INCOMPLETE_OR_NOT_AHEAD")
        self.assert_read_only(result)

    def test_required_ci_uses_documented_server_side_filters(self):
        result, github = self.reconcile_dashboard(["apps/web/src/example.tsx"])
        self.assertEqual(result.decision, "AUTO_DEPLOY_SAFE")
        run_calls = [call for call in github.calls if "/actions/runs?" in call]
        self.assertEqual(len(run_calls), 1)
        self.assertIn("branch=main", run_calls[0])
        self.assertIn("event=push", run_calls[0])
        self.assertIn(f"head_sha={TARGET}", run_calls[0])
        self.assertIn("status=completed", run_calls[0])

    def test_exact_target_sha_ci_failure_blocks(self):
        result, _github = self.reconcile_dashboard(
            ["apps/web/src/example.tsx"], ci_success=False
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "EXACT_TARGET_SHA_REQUIRED_CI_NOT_SUCCESSFUL")
        self.assert_read_only(result)

    def test_target_not_reachable_from_current_main_blocks(self):
        github = dashboard_github(
            ["apps/web/src/example.tsx"],
            current_main=TARGET,
            target_reachable=False,
        )
        result = reconcile_once(
            github=github,
            root=ROOT,
            manifest_relative_path=DASHBOARD,
            production_baseline_sha=BASELINE,
            target_sha=OLDER_TARGET,
        )
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "TARGET_NOT_REACHABLE_FROM_CURRENT_MAIN")
        self.assert_read_only(result)

    def test_compare_limit_fails_closed(self):
        paths = [f"apps/web/src/file-{index}.tsx" for index in range(MAX_COMPARE_FILES)]
        result, _github = self.reconcile_dashboard(paths)
        self.assertEqual(result.decision, "BLOCKED")
        self.assertEqual(result.reason, "FULL_RANGE_COMPARE_INCOMPLETE_OR_NOT_AHEAD")
        self.assert_read_only(result)

    def test_weather_runtime_change_is_owner_required(self):
        result = reconcile_once(
            github=weather_github(["src/rozkalns_weather/app.py"]),
            root=ROOT,
            manifest_relative_path=WEATHER,
            production_baseline_sha=BASELINE,
        )
        self.assertEqual(result.decision, "OWNER_REQUIRED")
        self.assertEqual(result.classification, "MANUAL_ROLLOUT_REQUIRED")
        self.assert_read_only(result)

    def test_controller_source_has_no_apply_or_dispatch_bridge(self):
        source = (
            ROOT / "ops/lib/deploy_executor/auto_live_controller.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            ".apply(",
            "AdapterCatalog",
            "prepare_operation(",
            "mutation_dispatch_enabled=True",
            "production_mutation_started=True",
            "subprocess",
            "systemctl",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_source_contract_rejects_mutation_flag_drift(self):
        import deploy_executor.auto_live_controller as controller_module

        original_read_json = controller_module._read_json
        for key in sorted(controller_module.MUTATION_KEYS):
            def drifted_read_json(path, label, *, key=key):
                value = original_read_json(path, label)
                if label == "A3 controller contract":
                    value = dict(value)
                    mutation = dict(value["mutation"])
                    mutation[key] = True
                    value["mutation"] = mutation
                return value

            with self.subTest(key=key), patch.object(
                controller_module, "_read_json", side_effect=drifted_read_json
            ):
                with self.assertRaisesRegex(
                    controller_module.AutoLiveControllerError,
                    "mutation flags must all remain false",
                ):
                    _verify_source_contracts(
                        root=ROOT,
                        manifest_relative_path=DASHBOARD,
                    )

    def test_machine_contract_keeps_every_mutation_surface_disabled(self):
        contract = json.loads(
            (ROOT / "ops/deploy/auto-live-controller-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["decisions"], [
            "NO_DEPLOY",
            "AUTO_DEPLOY_SAFE",
            "OWNER_REQUIRED",
            "BLOCKED",
        ])
        self.assertFalse(contract["execution_enabled"])
        self.assertEqual(
            set(contract["mutation"]),
            {
                "automatic_mutation_allowed",
                "mutation_dispatch_enabled",
                "production_mutation_started",
                "adapter_apply_invocation",
                "systemd_or_timer_mutation",
                "credential_or_permission_mutation",
                "production_deploy",
            },
        )
        self.assertTrue(all(value is False for value in contract["mutation"].values()))


if __name__ == "__main__":
    unittest.main()
