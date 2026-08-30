from __future__ import annotations

import copy
import importlib.util
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_control_postcanary_collector as collector
from deploy_executor import p9_control_postcanary_producer as producer
from deploy_executor.control_center_postcanary_adapter import (
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    TARGET_REPOSITORY_ID,
)

SOURCE_SHA = "f9b900a884bffda993197fc7fa9223c886e11a90"
CI_RUN_ID = 33302808439
NOW = datetime(2026, 8, 30, 21, 20, tzinfo=timezone.utc)
BASELINE_BIN = ROOT / "ops" / "bin" / "rozkalns-deploy-p9-control-baseline"
UPGRADE_OPERATOR = ROOT / "scripts" / "install-deploy-executor-p9-gate-d-failfast-upgrade.py"


@dataclass
class Response:
    value: object
    server_time: datetime | None = None


class SourceClient:
    def get_json(self, path):
        if path == f"/repos/{SOURCE_REPOSITORY}":
            return Response(
                {
                    "id": SOURCE_REPOSITORY_ID,
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
                            "conclusion": "success",
                        }
                    ]
                }
            )
        if path == (
            f"/repos/{SOURCE_REPOSITORY}/actions/runs/{CI_RUN_ID}/jobs"
            "?filter=latest&per_page=100"
        ):
            return Response(
                {"jobs": [{"status": "completed", "conclusion": "success"}]}
            )
        if path == (
            f"/repos/{SOURCE_REPOSITORY}/actions/runs/"
            f"{collector.PINNED_CANARY_RUN_ID}"
        ):
            return Response(
                {
                    "id": collector.PINNED_CANARY_RUN_ID,
                    "name": producer.CANARY_WORKFLOW_NAME,
                    "path": producer.CANARY_WORKFLOW_PATH,
                    "head_branch": "main",
                    "head_sha": collector.PINNED_CANARY_SOURCE_SHA,
                    "event": "workflow_dispatch",
                    "status": "completed",
                    "conclusion": "failure",
                    "run_attempt": 1,
                },
                server_time=NOW,
            )
        if path == (
            f"/repos/{SOURCE_REPOSITORY}/actions/runs/"
            f"{collector.PINNED_CANARY_RUN_ID}/jobs?filter=latest&per_page=100"
        ):
            return Response(
                {
                    "jobs": [
                        {
                            "name": producer.CANARY_JOB_NAME,
                            "status": "completed",
                            "conclusion": "failure",
                            "run_attempt": 1,
                        }
                    ]
                }
            )
        raise AssertionError(path)


def target_payloads():
    return {
        "repository": {
            "id": TARGET_REPOSITORY_ID,
            "full_name": producer.TARGET_REPOSITORY,
            "default_branch": "main",
        },
        "issue": {
            "number": collector.PINNED_TARGET_ISSUE_NUMBER,
            "state": "open",
        },
        "pr": {
            "number": collector.PINNED_TARGET_PR_NUMBER,
            "state": "closed",
            "merged_at": "2026-08-29T18:48:04Z",
            "draft": False,
            "head": {
                "sha": collector.PINNED_EXPECTED_PR_HEAD,
                "repo": {"full_name": producer.TARGET_REPOSITORY},
            },
            "base": {
                "ref": "main",
                "repo": {"full_name": producer.TARGET_REPOSITORY},
            },
            "merge_commit_sha": collector.PINNED_EXPECTED_MERGE_SHA,
        },
        "merge": {
            "sha": collector.PINNED_EXPECTED_MERGE_SHA,
            "parents": [{"sha": collector.PINNED_EXPECTED_OLD_MAIN}],
        },
        "compare": {
            "status": "ahead",
            "merge_base_commit": {"sha": collector.PINNED_EXPECTED_MERGE_SHA},
        },
    }


class TargetClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_json(self, path):
        if path == f"/repos/{producer.TARGET_REPOSITORY}":
            return Response(copy.deepcopy(self.payloads["repository"]))
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/issues/"
            f"{collector.PINNED_TARGET_ISSUE_NUMBER}"
        ):
            return Response(copy.deepcopy(self.payloads["issue"]))
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/pulls/"
            f"{collector.PINNED_TARGET_PR_NUMBER}"
        ):
            return Response(copy.deepcopy(self.payloads["pr"]))
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/commits/"
            f"{collector.PINNED_EXPECTED_MERGE_SHA}"
        ):
            return Response(copy.deepcopy(self.payloads["merge"]))
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/compare/"
            f"{collector.PINNED_EXPECTED_MERGE_SHA}...main"
        ):
            return Response(copy.deepcopy(self.payloads["compare"]))
        raise AssertionError(path)


class D1Client:
    def __init__(self):
        self.calls = []

    @staticmethod
    def _result(sql):
        return collector.D1SelectResult(
            sql=sql,
            rows=(),
            success=True,
            result_success=True,
            changed_db=False,
            rows_written=0,
            changes=0,
        )

    def select_pinned_request(self):
        self.calls.append("request")
        return self._result(collector.AUDIT_SQL)

    def select_pinned_target(self):
        self.calls.append("target")
        return self._result(collector.TARGET_SQL)


def mutate_issue_number(payloads):
    payloads["issue"]["number"] += 1


def mutate_issue_state(payloads):
    payloads["issue"]["state"] = "closed"


def mutate_issue_to_pr(payloads):
    payloads["issue"]["pull_request"] = {"url": "sanitized"}


def mutate_pr_number(payloads):
    payloads["pr"]["number"] += 1


def mutate_pr_state(payloads):
    payloads["pr"]["state"] = "open"


def mutate_pr_merged_at(payloads):
    payloads["pr"]["merged_at"] = None


def mutate_pr_draft(payloads):
    payloads["pr"]["draft"] = True


def mutate_pr_head(payloads):
    payloads["pr"]["head"]["sha"] = "0" * 40


def mutate_pr_head_repo(payloads):
    payloads["pr"]["head"]["repo"]["full_name"] = "other/repo"


def mutate_pr_base_ref(payloads):
    payloads["pr"]["base"]["ref"] = "other"


def mutate_pr_base_repo(payloads):
    payloads["pr"]["base"]["repo"]["full_name"] = "other/repo"


def mutate_pr_merge_sha(payloads):
    payloads["pr"]["merge_commit_sha"] = "0" * 40


def mutate_merge_sha(payloads):
    payloads["merge"]["sha"] = "0" * 40


def mutate_merge_parent_count(payloads):
    payloads["merge"]["parents"] = []


def mutate_merge_parent_sha(payloads):
    payloads["merge"]["parents"][0]["sha"] = "0" * 40


def mutate_compare_status(payloads):
    payloads["compare"]["status"] = "behind"


def mutate_compare_base(payloads):
    payloads["compare"]["merge_base_commit"]["sha"] = "0" * 40


FAILURE_CASES = (
    ("TARGET_ISSUE_NUMBER_MISMATCH", mutate_issue_number),
    ("TARGET_ISSUE_NOT_OPEN", mutate_issue_state),
    ("TARGET_ISSUE_IS_PULL_REQUEST", mutate_issue_to_pr),
    ("TARGET_PR_NUMBER_MISMATCH", mutate_pr_number),
    ("TARGET_PR_NOT_CLOSED", mutate_pr_state),
    ("TARGET_PR_MERGED_AT_INVALID", mutate_pr_merged_at),
    ("TARGET_PR_DRAFT_INVALID", mutate_pr_draft),
    ("TARGET_PR_HEAD_MISMATCH", mutate_pr_head),
    ("TARGET_PR_HEAD_REPO_MISMATCH", mutate_pr_head_repo),
    ("TARGET_PR_BASE_MISMATCH", mutate_pr_base_ref),
    ("TARGET_PR_BASE_MISMATCH", mutate_pr_base_repo),
    ("TARGET_PR_MERGE_SHA_MISMATCH", mutate_pr_merge_sha),
    ("TARGET_MERGE_SHA_MISMATCH", mutate_merge_sha),
    ("TARGET_MERGE_PARENT_COUNT_MISMATCH", mutate_merge_parent_count),
    ("TARGET_MERGE_PARENT_SHA_MISMATCH", mutate_merge_parent_sha),
    ("TARGET_MAIN_RELATION_MISMATCH", mutate_compare_status),
    ("TARGET_MERGE_BASE_MISMATCH", mutate_compare_base),
)


class P9ControlBaselineFailFastTests(unittest.TestCase):
    def _collect(self, payloads, *, d1_client_factory=None):
        return collector.collect_control_postcanary_observation(
            collector.ControlPostCanaryCollectionRequest(source_sha=SOURCE_SHA),
            source_client=SourceClient(),
            target_client=TargetClient(payloads),
            d1_client_factory=d1_client_factory,
        )

    def test_every_reviewed_target_semantic_mismatch_stops_before_d1_factory(self):
        for code, mutate in FAILURE_CASES:
            with self.subTest(code=code, mutate=mutate.__name__):
                payloads = target_payloads()
                mutate(payloads)
                d1_factory = mock.Mock(
                    side_effect=AssertionError("D1 factory reached before target validation")
                )
                with self.assertRaisesRegex(
                    collector.ControlPostCanaryCollectorError, code
                ):
                    self._collect(payloads, d1_client_factory=d1_factory)
                d1_factory.assert_not_called()

    def test_every_reviewed_target_semantic_mismatch_stops_before_credential_read(self):
        for code, mutate in FAILURE_CASES:
            with self.subTest(code=code, mutate=mutate.__name__):
                payloads = target_payloads()
                mutate(payloads)
                with mock.patch.object(
                    collector,
                    "read_fixed_d1_token",
                    side_effect=AssertionError(
                        "D1 credential read reached before target validation"
                    ),
                ) as token_read, mock.patch.object(
                    collector,
                    "FixedD1ReadClient",
                    side_effect=AssertionError(
                        "D1 client constructed before target validation"
                    ),
                ) as d1_client:
                    with self.assertRaisesRegex(
                        collector.ControlPostCanaryCollectorError, code
                    ):
                        self._collect(payloads)
                token_read.assert_not_called()
                d1_client.assert_not_called()

    def test_valid_target_semantics_construct_d1_once_then_run_exact_two_selects(self):
        d1 = D1Client()
        d1_factory = mock.Mock(return_value=d1)
        observation = self._collect(
            target_payloads(), d1_client_factory=d1_factory
        )
        d1_factory.assert_called_once_with()
        self.assertEqual(d1.calls, ["request", "target"])
        self.assertEqual(len(observation.d1_selects), 2)
        self.assertTrue(
            all(item["changed_db"] is False for item in observation.d1_selects)
        )
        self.assertTrue(
            all(item["rows_written"] == 0 for item in observation.d1_selects)
        )
        self.assertTrue(all(item["changes"] == 0 for item in observation.d1_selects))

    def test_target_pr_diagnostics_preserve_all_existing_predicates(self):
        expected_codes = {
            "TARGET_PR_NUMBER_MISMATCH",
            "TARGET_PR_NOT_CLOSED",
            "TARGET_PR_MERGED_AT_INVALID",
            "TARGET_PR_DRAFT_INVALID",
            "TARGET_PR_HEAD_MISMATCH",
            "TARGET_PR_HEAD_REPO_MISMATCH",
            "TARGET_PR_BASE_MISMATCH",
            "TARGET_PR_MERGE_SHA_MISMATCH",
        }
        observed_codes = {
            code for code, _ in FAILURE_CASES if code.startswith("TARGET_PR_")
        }
        self.assertEqual(observed_codes, expected_codes)

    def test_baseline_cli_no_longer_reads_d1_credential_eagerly(self):
        source = BASELINE_BIN.read_text(encoding="utf-8")
        self.assertNotIn("read_fixed_d1_token", source)
        self.assertNotIn("FixedD1ReadClient", source)
        self.assertIn("collect_control_postcanary_observation", source)


class P9GateDFailFastUpgradeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "p9_gate_d_failfast_upgrade", UPGRADE_OPERATOR
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.source = UPGRADE_OPERATOR.read_text(encoding="utf-8")

    def test_upgrade_is_bound_to_exact_three_reviewed_installed_prestate_blobs(self):
        self.assertEqual(
            [
                (spec.source_path, str(spec.target_path), spec.old_blob_sha, spec.mode)
                for spec in self.module.TARGETS
            ],
            [
                (
                    "ops/lib/deploy_executor/p9_control_postcanary_producer.py",
                    "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_control_postcanary_producer.py",
                    "e534d97016cb43a3129cb6711527fdcea3cb178b",
                    0o644,
                ),
                (
                    "ops/lib/deploy_executor/p9_control_postcanary_collector.py",
                    "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_control_postcanary_collector.py",
                    "d61d2c992da709833425e82da1242b172e3cc5c1",
                    0o644,
                ),
                (
                    "ops/bin/rozkalns-deploy-p9-control-baseline",
                    "/usr/local/sbin/rozkalns-deploy-p9-control-baseline",
                    "4c406248875cd37963027f5b6fb950749ac5ad1e",
                    0o755,
                ),
            ],
        )

    def test_upgrade_preflight_is_non_mutating_and_apply_is_separately_gated(self):
        source = self.source
        marker = "Final duplicate gate before the first live mutation"
        preflight = source[: source.index(marker)]
        self.assertIn("_require_exact_source(expected_sha)", preflight)
        self.assertIn("_require_target_prestate(spec)", preflight)
        self.assertIn("if not args.apply:", preflight)
        self.assertIn("P9_GATE_D_FAILFAST_MUTATION=NO", preflight)
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_upgrade_has_no_network_credential_d1_baseline_or_execution_path(self):
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
            "ROLLBACK_PATH=NO",
            "RETRY_PATH=NO",
        ):
            self.assertIn(marker, source)

    def test_upgrade_revalidates_open_fd_before_first_truncate(self):
        source = self.source
        fn = source[source.index("def _replace_exact_target") : source.index("def _parse_args")]
        truncate_at = fn.index("os.ftruncate(fd, 0)")
        self.assertLess(fn.index("os.fstat(fd)"), truncate_at)
        self.assertLess(fn.index("_git_blob_sha(current)"), truncate_at)
        self.assertLess(
            fn.index("os.stat(spec.target_path, follow_symlinks=False)"), truncate_at
        )
        self.assertIn("os.O_NOFOLLOW", fn)
        self.assertGreater(fn.index("if _read_fd_all(fd) != reviewed_bytes"), truncate_at)


if __name__ == "__main__":
    unittest.main()
