#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_runtime_materialization as materialization
from deploy_executor import weather_private_bigquery_runtime_transport as transport

DISPATCH_PATH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
WORKFLOW_PATH = ROOT / ".github/workflows/weathernext-private-runtime-source.yml"
CONTRACT_PATH = ROOT / "ops/deploy/weather-private-runtime-materialization.json"


def receipt() -> materialization.RuntimeArtifactReceipt:
    lock = materialization.load_runtime_lock()
    return materialization.RuntimeArtifactReceipt(
        source_sha="1" * 40,
        closure_sha256=lock["closure_sha256"],
        artifact_sha256="2" * 64,
        artifact_size_bytes=1024,
        artifact_format=materialization.ARTIFACT_FORMAT,
        target_os=materialization.TARGET_OS,
        target_architecture=materialization.TARGET_ARCH,
        target_python_version=materialization.TARGET_PYTHON_VERSION,
        target_python_abi=materialization.TARGET_PYTHON_ABI,
        target_platform=materialization.TARGET_PIP_PLATFORM,
    )


def actions_evidence(source_sha: str = "1" * 40) -> transport.RuntimeActionsEvidence:
    return transport.RuntimeActionsEvidence(
        source_sha=source_sha,
        run_id=123,
        artifact_id=456,
        artifact_name=f"weathernext-private-runtime-{source_sha}",
        artifact_digest="sha256:" + "3" * 64,
    )


class WeatherNextPrivateRuntimeTransportTests(unittest.TestCase):
    def test_source_contract_is_fixed_and_non_authoritative(self) -> None:
        summary = transport.source_readiness()
        self.assertEqual(summary["implementation_issue"], 704)
        self.assertEqual(summary["operation_id"], materialization.OPERATION_ID)
        self.assertEqual(summary["source_repository"], "rozkalnsandris/RPi5_main")
        self.assertEqual(
            summary["mutation_budget"],
            (
                ("filesystem.weathernext-private-runtime-artifact-cache-publish", 1),
                ("filesystem.weathernext-private-runtime-materialization", 1),
            ),
        )
        self.assertTrue(summary["runtime_actions_metadata_evidence_required"])
        self.assertEqual(
            summary["incoming_actions_evidence"],
            str(transport.INCOMING_ACTIONS_EVIDENCE),
        )
        for key in (
            "actions_artifact_download_authority",
            "credential_acquisition_authority",
            "network_install_authority",
            "package_manager_authority",
            "google_action_allowed",
            "bigquery_action_allowed",
            "sqlite_write_allowed",
            "source_merge_authorizes_live",
            "production_mutation_started",
        ):
            self.assertFalse(summary[key], key)

    def test_registry_is_strict_issue_identity_only_and_execution_disabled(self) -> None:
        registry = transport._fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, materialization.OPERATION_ID)
        self.assertEqual(operation.target_alias, transport.TARGET_ALIAS)
        self.assertEqual(operation.source_repository, "rozkalnsandris/RPi5_main")
        self.assertEqual(operation.authorization_class, "STRICT")
        self.assertFalse(operation.ordinary_live_all_eligible)
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertEqual(
            tuple((m.category, m.max_operations) for m in operation.mutation_budget),
            transport.MUTATION_BUDGET,
        )

    def test_plan_rejects_conflict_and_never_selects_caller_paths(self) -> None:
        base = receipt()
        actions = actions_evidence(base.source_sha)
        with (
            mock.patch.object(transport, "_incoming_receipt", return_value=base),
            mock.patch.object(transport, "_cache_state", return_value="ABSENT"),
            mock.patch.object(transport, "_runtime_state", return_value="ABSENT"),
        ):
            plan = transport.build_transport_plan(base.source_sha, actions)
        self.assertEqual(
            plan.mutation_categories,
            (
                "filesystem.weathernext-private-runtime-artifact-cache-publish",
                "filesystem.weathernext-private-runtime-materialization",
            ),
        )
        public = transport.public_plan(plan)
        self.assertEqual(public["actions_run_id"], actions.run_id)
        self.assertEqual(public["actions_artifact_id"], actions.artifact_id)
        self.assertNotIn("incoming_path", public)
        self.assertNotIn("url", public)
        self.assertNotIn("argv", public)

        with (
            mock.patch.object(transport, "_incoming_receipt", return_value=base),
            mock.patch.object(transport, "_cache_state", return_value="CONFLICT"),
            mock.patch.object(transport, "_runtime_state", return_value="ABSENT"),
        ):
            with self.assertRaisesRegex(
                transport.WeatherNextPrivateRuntimeTransportError,
                "conflicts",
            ):
                transport.build_transport_plan(base.source_sha, actions)

    def test_exact_existing_transport_is_a_noop_plan(self) -> None:
        base = receipt()
        actions = actions_evidence(base.source_sha)
        with (
            mock.patch.object(transport, "_incoming_receipt", return_value=base),
            mock.patch.object(transport, "_cache_state", return_value="EXACT"),
            mock.patch.object(transport, "_runtime_state", return_value="EXACT"),
        ):
            plan = transport.build_transport_plan(base.source_sha, actions)
        self.assertEqual(plan.mutation_categories, ())

    def test_runtime_actions_evidence_is_exact_successful_main_artifact(self) -> None:
        source_sha = "1" * 40
        expected_name = f"weathernext-private-runtime-{source_sha}"
        client = transport.FixedPublicGitHubReadClient(sender=object())

        def get_json(path_or_url: str) -> SimpleNamespace:
            if "/workflows/" in path_or_url:
                return SimpleNamespace(
                    value={
                        "workflow_runs": [
                            {
                                "id": 123,
                                "head_sha": source_sha,
                                "head_branch": "main",
                                "event": "push",
                                "status": "completed",
                                "conclusion": "success",
                            }
                        ]
                    }
                )
            if "/actions/runs/123/artifacts" in path_or_url:
                return SimpleNamespace(
                    value={
                        "artifacts": [
                            {
                                "id": 456,
                                "name": expected_name,
                                "expired": False,
                                "digest": "sha256:" + "3" * 64,
                                "workflow_run": {
                                    "id": 123,
                                    "head_sha": source_sha,
                                },
                            }
                        ]
                    }
                )
            raise AssertionError(path_or_url)

        with mock.patch.object(client, "get_json", side_effect=get_json):
            observed = transport._runtime_actions_evidence(client, source_sha)
        self.assertEqual(observed, actions_evidence(source_sha))

    def test_runtime_actions_evidence_rejects_wrong_or_ambiguous_artifact(self) -> None:
        source_sha = "1" * 40
        client = transport.FixedPublicGitHubReadClient(sender=object())

        def get_json(path_or_url: str) -> SimpleNamespace:
            if "/workflows/" in path_or_url:
                return SimpleNamespace(
                    value={
                        "workflow_runs": [
                            {
                                "id": 123,
                                "head_sha": source_sha,
                                "head_branch": "main",
                                "event": "push",
                                "status": "completed",
                                "conclusion": "success",
                            }
                        ]
                    }
                )
            return SimpleNamespace(
                value={
                    "artifacts": [
                        {
                            "id": 456,
                            "name": "wrong",
                            "expired": False,
                            "digest": "sha256:" + "3" * 64,
                            "workflow_run": {"id": 123, "head_sha": source_sha},
                        }
                    ]
                }
            )

        with mock.patch.object(client, "get_json", side_effect=get_json):
            with self.assertRaisesRegex(
                transport.WeatherNextPrivateRuntimeTransportError,
                "unavailable or ambiguous",
            ):
                transport._runtime_actions_evidence(client, source_sha)

    def test_fixed_actions_handoff_must_equal_fresh_actions_identity(self) -> None:
        expected = actions_evidence()
        exact = {
            "schema": "rpi5.weathernext-private-runtime-actions-handoff.v1",
            "source_sha": expected.source_sha,
            "workflow": transport.RUNTIME_WORKFLOW,
            "run_id": expected.run_id,
            "artifact_id": expected.artifact_id,
            "artifact_name": expected.artifact_name,
            "artifact_digest": expected.artifact_digest,
        }
        with mock.patch.object(transport, "_read_json_regular", return_value=exact):
            transport._require_actions_handoff(expected)

        drifted = dict(exact)
        drifted["artifact_id"] = 999
        with mock.patch.object(transport, "_read_json_regular", return_value=drifted):
            with self.assertRaisesRegex(
                transport.WeatherNextPrivateRuntimeTransportError,
                "identity drifted",
            ):
                transport._require_actions_handoff(expected)

    def test_live_authority_requires_exact_mutation_budget_and_exclusions(self) -> None:
        class Accepted:
            payload = {
                "queue_repository": "rozkalnsandris/ops-workflows",
                "source_repository": "rozkalnsandris/RPi5_main",
                "target_alias": transport.TARGET_ALIAS,
                "operation_id": materialization.OPERATION_ID,
                "expected_baseline": {
                    "kind": "resolver",
                    "value": transport.BASELINE_RESOLVER_ID,
                },
                "mutation_budget": [
                    {"category": category, "max_operations": maximum}
                    for category, maximum in transport.MUTATION_BUDGET
                ],
                "rollback_policy": "NONE",
                "exclusions": list(transport.REQUIRED_EXCLUSIONS),
            }

        transport._require_live_authority(Accepted())
        bad = Accepted()
        bad.payload = dict(Accepted.payload)
        bad.payload["mutation_budget"] = []
        with self.assertRaisesRegex(
            transport.WeatherNextPrivateRuntimeTransportError,
            "mutation_budget",
        ):
            transport._require_live_authority(bad)

    def test_cache_partial_directory_mode_is_umask_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            partial = Path(temp) / "cache.partial"
            previous_umask = os.umask(0o077)
            try:
                transport._mkdir_cache_partial_exact(partial)
            finally:
                os.umask(previous_umask)
            self.assertEqual(
                stat.S_IMODE(partial.stat().st_mode),
                materialization.FIXED_DIRECTORY_MODE,
            )
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_transport.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_mkdir_cache_partial_exact(partial)", source)

    def test_no_generic_download_credential_or_shell_surface(self) -> None:
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_transport.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "subprocess",
            "Popen(",
            "shell=True",
            "requests.",
            "urllib",
            "archive_download_url",
            "/actions/artifacts/",
            "gh run",
            "gh api",
            "curl ",
            "Authorization:",
            "GITHUB_TOKEN",
            "os.environ",
            "pip install",
            "apt ",
            "GOOGLE_APPLICATION_CREDENTIALS",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_dispatcher_and_workflow_cover_runtime_transport(self) -> None:
        dispatch = DISPATCH_PATH.read_text(encoding="utf-8")
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("RUNTIME_MATERIALIZATION_OPERATION_ID", dispatch)
        self.assertIn("run_privileged_runtime_materialization", dispatch)
        self.assertIn("weather_private_bigquery_runtime_transport.py", workflow)
        self.assertIn(
            "test-deploy-executor-weather-private-runtime-transport.py",
            workflow,
        )

    def test_machine_contract_preserves_separate_acquisition_boundary(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["implementation_issue"], 704)
        self.assertEqual(contract["operation_id"], materialization.OPERATION_ID)
        self.assertFalse(contract["actions_artifact_download_authority"])
        self.assertFalse(contract["credential_acquisition_authority"])
        self.assertTrue(contract["runtime_actions_metadata_evidence_required"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertEqual(
            contract["artifact_handoff"]["incoming_root"],
            str(transport.INCOMING_ROOT),
        )
        self.assertEqual(
            contract["artifact_handoff"]["incoming_actions_evidence"],
            transport.INCOMING_ACTIONS_EVIDENCE.name,
        )
        self.assertEqual(
            contract["artifact_handoff"]["cache_root"],
            str(materialization.ARTIFACT_CACHE_ROOT),
        )


if __name__ == "__main__":
    unittest.main()
