from __future__ import annotations

import copy
import importlib.util
from importlib.machinery import SourceFileLoader
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
from deploy_executor import transport
from deploy_executor.control_center_postcanary_adapter import TARGET_REPOSITORY_ID

SOURCE_SHA = "f9b900a884bffda993197fc7fa9223c886e11a90"
NOW = datetime(2026, 8, 30, 21, 20, tzinfo=timezone.utc)
BASELINE_BIN = ROOT / "ops" / "bin" / "rozkalns-deploy-p9-control-baseline"
UPGRADE_OPERATOR = (
    ROOT / "scripts" / "install-deploy-executor-p9-gate-d-public-target-preauth-upgrade.py"
)
API_2026_UPGRADE_OPERATOR = (
    ROOT / "scripts" / "install-deploy-executor-p9-gate-d-api-2026-compat-upgrade.py"
)


@dataclass
class Response:
    value: object
    server_time: datetime | None = NOW
    etag: str | None = 'W/"public-etag"'


def target_payloads():
    pr = {
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
    }
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
        # GitHub REST 2026-03-10 deliberately omits merge_commit_sha here.
        "pr": pr,
        "merge": {
            "sha": collector.PINNED_EXPECTED_MERGE_SHA,
            "parents": [{"sha": collector.PINNED_EXPECTED_OLD_MAIN}],
        },
        "merge_pulls": [copy.deepcopy(pr)],
        "compare": {
            "status": "ahead",
            "merge_base_commit": {"sha": collector.PINNED_EXPECTED_MERGE_SHA},
        },
    }


class TargetClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls: list[str] = []

    def _response(self, key: str) -> Response:
        return Response(
            copy.deepcopy(self.payloads[key]),
            server_time=NOW,
            etag=f'W/"{key}-etag"',
        )

    def get_json(self, path):
        self.calls.append(path)
        if path == f"/repos/{producer.TARGET_REPOSITORY}":
            return self._response("repository")
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/issues/"
            f"{collector.PINNED_TARGET_ISSUE_NUMBER}"
        ):
            return self._response("issue")
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/pulls/"
            f"{collector.PINNED_TARGET_PR_NUMBER}"
        ):
            return self._response("pr")
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/commits/"
            f"{collector.PINNED_EXPECTED_MERGE_SHA}"
        ):
            return self._response("merge")
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/commits/"
            f"{collector.PINNED_EXPECTED_MERGE_SHA}/pulls"
        ):
            return self._response("merge_pulls")
        if path == (
            f"/repos/{producer.TARGET_REPOSITORY}/compare/"
            f"{collector.PINNED_EXPECTED_MERGE_SHA}...main"
        ):
            return self._response("compare")
        raise AssertionError(path)


def mutate_issue_object(payloads):
    payloads["issue"] = []


def mutate_issue_number(payloads):
    payloads["issue"]["number"] += 1


def mutate_issue_state(payloads):
    payloads["issue"]["state"] = "closed"


def mutate_issue_to_pr(payloads):
    payloads["issue"]["pull_request"] = {"url": "sanitized"}


def mutate_pr_object(payloads):
    payloads["pr"] = []


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


def mutate_merge_object(payloads):
    payloads["merge"] = []


def mutate_merge_sha(payloads):
    payloads["merge"]["sha"] = "0" * 40


def mutate_merge_parents_type(payloads):
    payloads["merge"]["parents"] = "invalid"


def mutate_merge_parent_count(payloads):
    payloads["merge"]["parents"] = []


def mutate_merge_parent_object(payloads):
    payloads["merge"]["parents"] = [[]]


def mutate_merge_parent_sha(payloads):
    payloads["merge"]["parents"][0]["sha"] = "0" * 40


def mutate_compare_object(payloads):
    payloads["compare"] = []


def mutate_compare_status(payloads):
    payloads["compare"]["status"] = "behind"


def mutate_compare_base(payloads):
    payloads["compare"]["merge_base_commit"]["sha"] = "0" * 40


def mutate_association_missing(payloads):
    payloads["merge_pulls"] = []


def mutate_association_wrong_pr(payloads):
    payloads["merge_pulls"][0]["number"] = collector.PINNED_TARGET_PR_NUMBER + 1


FAILURE_CASES = (
    ("TARGET_ISSUE_OBJECT_INVALID", mutate_issue_object),
    ("TARGET_ISSUE_NUMBER_MISMATCH", mutate_issue_number),
    ("TARGET_ISSUE_NOT_OPEN", mutate_issue_state),
    ("TARGET_ISSUE_IS_PULL_REQUEST", mutate_issue_to_pr),
    ("TARGET_PR_OBJECT_INVALID", mutate_pr_object),
    ("TARGET_PR_NUMBER_MISMATCH", mutate_pr_number),
    ("TARGET_PR_NOT_CLOSED", mutate_pr_state),
    ("TARGET_PR_MERGED_AT_INVALID", mutate_pr_merged_at),
    ("TARGET_PR_DRAFT_INVALID", mutate_pr_draft),
    ("TARGET_PR_HEAD_MISMATCH", mutate_pr_head),
    ("TARGET_PR_HEAD_REPO_MISMATCH", mutate_pr_head_repo),
    ("TARGET_PR_BASE_MISMATCH", mutate_pr_base_ref),
    ("TARGET_PR_BASE_MISMATCH", mutate_pr_base_repo),
    ("TARGET_MERGE_COMMIT_OBJECT_INVALID", mutate_merge_object),
    ("TARGET_MERGE_SHA_MISMATCH", mutate_merge_sha),
    ("TARGET_MERGE_PARENTS_INVALID", mutate_merge_parents_type),
    ("TARGET_MERGE_PARENT_COUNT_MISMATCH", mutate_merge_parent_count),
    ("TARGET_MERGE_PARENT_OBJECT_INVALID", mutate_merge_parent_object),
    ("TARGET_MERGE_PARENT_SHA_MISMATCH", mutate_merge_parent_sha),
    ("TARGET_COMPARE_OBJECT_INVALID", mutate_compare_object),
    ("TARGET_MAIN_RELATION_MISMATCH", mutate_compare_status),
    ("TARGET_MERGE_BASE_MISMATCH", mutate_compare_base),
)

ASSOCIATION_FAILURE_CASES = (
    mutate_association_missing,
    mutate_association_wrong_pr,
)


def load_baseline_cli():
    loader = SourceFileLoader("p9_control_baseline_cli", str(BASELINE_BIN))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicTargetPreauthTests(unittest.TestCase):
    def _assert_stops_before_protected_paths(self, payloads, code):
        cli = load_baseline_cli()
        source_factory = mock.Mock(
            side_effect=AssertionError("source-App reached before target preflight")
        )
        observation_collector = mock.Mock(
            side_effect=AssertionError("collector reached after failed target preflight")
        )
        with mock.patch.object(
            collector,
            "read_fixed_d1_token",
            side_effect=AssertionError("D1 credential read reached"),
        ) as token_read, mock.patch.object(
            collector,
            "FixedD1ReadClient",
            side_effect=AssertionError("D1 client constructed"),
        ) as d1_client:
            with self.assertRaisesRegex(collector.ControlPostCanaryCollectorError, code):
                cli.collect_once(
                    collector.ControlPostCanaryCollectionRequest(source_sha=SOURCE_SHA),
                    target_client_factory=lambda p=payloads: TargetClient(p),
                    source_client_factory=source_factory,
                    collector_fn=observation_collector,
                )
        source_factory.assert_not_called()
        observation_collector.assert_not_called()
        token_read.assert_not_called()
        d1_client.assert_not_called()

    def test_every_remaining_target_mismatch_stops_before_source_app_and_d1(self):
        for code, mutate in FAILURE_CASES:
            with self.subTest(code=code, mutate=mutate.__name__):
                payloads = target_payloads()
                mutate(payloads)
                self._assert_stops_before_protected_paths(payloads, code)

    def test_missing_or_wrong_merge_pr_association_stops_before_source_app_and_d1(self):
        for mutate in ASSOCIATION_FAILURE_CASES:
            with self.subTest(mutate=mutate.__name__):
                payloads = target_payloads()
                mutate(payloads)
                self._assert_stops_before_protected_paths(
                    payloads, "TARGET_MERGE_PR_ASSOCIATION_MISMATCH"
                )

    def test_merge_pr_association_mismatch_has_public_identity_time_and_etag_only(self):
        cli = load_baseline_cli()
        payloads = target_payloads()
        mutate_association_wrong_pr(payloads)
        with self.assertRaises(collector.ControlPostCanaryCollectorError) as raised:
            cli.collect_public_target_snapshot_api_2026(TargetClient(payloads))
        text = str(raised.exception)
        self.assertIn("TARGET_MERGE_PR_ASSOCIATION_MISMATCH", text)
        self.assertIn("endpoint=merge_pulls", text)
        self.assertIn(f"expected_pr={collector.PINNED_TARGET_PR_NUMBER}", text)
        self.assertIn(
            f"observed_prs={collector.PINNED_TARGET_PR_NUMBER + 1}", text
        )
        self.assertIn("server_time=2026-08-30T21:20:00Z", text)
        self.assertIn('etag=W/"merge_pulls-etag"', text)
        self.assertNotIn("Authorization", text)
        self.assertNotIn("private-key", text.lower())
        self.assertNotIn("d1", text.lower())

    def test_api_2026_fixture_omits_removed_merge_commit_sha(self):
        payloads = target_payloads()
        self.assertEqual(transport.API_VERSION, "2026-03-10")
        self.assertNotIn("merge_commit_sha", payloads["pr"])
        self.assertNotIn("merge_commit_sha", payloads["merge_pulls"][0])

    def test_successful_association_derives_legacy_merge_field_without_mutating_raw_pr(self):
        cli = load_baseline_cli()
        payloads = target_payloads()
        raw_pr = copy.deepcopy(payloads["pr"])
        snapshot = cli.collect_public_target_snapshot_api_2026(TargetClient(payloads))
        self.assertEqual(payloads["pr"], raw_pr)
        self.assertNotIn("merge_commit_sha", payloads["pr"])
        self.assertEqual(
            snapshot.pr.value["merge_commit_sha"], collector.PINNED_EXPECTED_MERGE_SHA
        )

    def test_public_preflight_reads_each_pinned_endpoint_once(self):
        cli = load_baseline_cli()
        client = TargetClient(target_payloads())
        snapshot = cli.collect_public_target_snapshot_api_2026(client)
        self.assertIsInstance(snapshot, collector.ControlPostCanaryTargetSnapshot)
        self.assertEqual(
            client.calls,
            [
                f"/repos/{producer.TARGET_REPOSITORY}",
                f"/repos/{producer.TARGET_REPOSITORY}/issues/{collector.PINNED_TARGET_ISSUE_NUMBER}",
                f"/repos/{producer.TARGET_REPOSITORY}/pulls/{collector.PINNED_TARGET_PR_NUMBER}",
                f"/repos/{producer.TARGET_REPOSITORY}/commits/{collector.PINNED_EXPECTED_MERGE_SHA}",
                f"/repos/{producer.TARGET_REPOSITORY}/commits/{collector.PINNED_EXPECTED_MERGE_SHA}/pulls",
                f"/repos/{producer.TARGET_REPOSITORY}/compare/{collector.PINNED_EXPECTED_MERGE_SHA}...main",
            ],
        )

    def test_cli_execution_order_uses_concrete_statements_not_parameter_names(self):
        source = BASELINE_BIN.read_text(encoding="utf-8")
        body = source[source.index("def collect_once(") : source.index("\ndef main()")]
        preflight_at = body.index(
            "target_snapshot = collect_public_target_snapshot_api_2026(target_client)"
        )
        source_build_at = body.index("source_client = build_source_client()")
        source_mint_at = body.index(
            "source_client.token_provider.get_installation_token()"
        )
        collect_at = body.index(
            "observation = collect_control_postcanary_observation("
        )
        self.assertLess(preflight_at, source_build_at)
        self.assertLess(source_build_at, source_mint_at)
        self.assertLess(source_mint_at, collect_at)

    def test_all_non_removed_pr_predicates_are_preserved(self):
        expected = {
            "TARGET_PR_OBJECT_INVALID",
            "TARGET_PR_NUMBER_MISMATCH",
            "TARGET_PR_NOT_CLOSED",
            "TARGET_PR_MERGED_AT_INVALID",
            "TARGET_PR_DRAFT_INVALID",
            "TARGET_PR_HEAD_MISMATCH",
            "TARGET_PR_HEAD_REPO_MISMATCH",
            "TARGET_PR_BASE_MISMATCH",
        }
        actual = {code for code, _ in FAILURE_CASES if code.startswith("TARGET_PR_")}
        self.assertEqual(actual, expected)
        # The frozen downstream compatibility check remains present, but its
        # value is derived only after the API-2026 commit->PR proof succeeds.
        self.assertIn(
            "TARGET_PR_MERGE_SHA_MISMATCH", producer._TARGET_PR_FAILURE_CODES
        )


class PublicTargetPreauthUpgradeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "p9_gate_d_public_target_preauth_upgrade", UPGRADE_OPERATOR
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.source = UPGRADE_OPERATOR.read_text(encoding="utf-8")

    def test_upgrade_is_bound_to_current_two_installed_prestate_blobs(self):
        self.assertEqual(
            [
                (spec.source_path, str(spec.target_path), spec.old_blob_sha, spec.mode)
                for spec in self.module.TARGETS
            ],
            [
                (
                    "ops/lib/deploy_executor/p9_control_postcanary_collector.py",
                    "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_control_postcanary_collector.py",
                    "744ecc5d262982d82689ff5cd8e798c454077f3e",
                    0o644,
                ),
                (
                    "ops/bin/rozkalns-deploy-p9-control-baseline",
                    "/usr/local/sbin/rozkalns-deploy-p9-control-baseline",
                    "3cfd1fad722944c0a69767850a748791d49f4c71",
                    0o755,
                ),
            ],
        )

    def test_upgrade_has_no_network_credential_d1_baseline_p9_or_retry_path(self):
        self.assertIn("TARGETS_REPLACED=2", self.source)
        for marker in (
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "ROLLBACK_PATH=NO",
            "RETRY_PATH=NO",
        ):
            self.assertIn(marker, self.source)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "curl",
            "wget",
            "control-d1-read-token",
            "github-app.pem",
            "systemctl",
            "StateStore",
            "cloudflare",
        ):
            self.assertNotIn(forbidden, self.source)


class Api2026CompatUpgradeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "p9_gate_d_api_2026_compat_upgrade", API_2026_UPGRADE_OPERATOR
        )
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.source = API_2026_UPGRADE_OPERATOR.read_text(encoding="utf-8")

    def test_upgrade_is_bound_to_exact_current_baseline_cli_prestate(self):
        self.assertEqual(
            [
                (spec.source_path, str(spec.target_path), spec.old_blob_sha, spec.mode)
                for spec in self.module.TARGETS
            ],
            [
                (
                    "ops/bin/rozkalns-deploy-p9-control-baseline",
                    "/usr/local/sbin/rozkalns-deploy-p9-control-baseline",
                    "af13d0d227bfe48b20430d76cfac8c9f5ac971bc",
                    0o755,
                )
            ],
        )

    def test_upgrade_has_no_network_credential_d1_baseline_p9_or_retry_path(self):
        self.assertIn("TARGETS_REPLACED=1", self.source)
        for marker in (
            "NETWORK_REQUEST=NO",
            "CREDENTIAL_READ=NO",
            "D1_REQUEST=NO",
            "BASELINE_COLLECTION=NO",
            "P9_EXECUTION=NO",
            "STATE_STORE_TOUCHED=NO",
            "ROLLBACK_PATH=NO",
            "RETRY_PATH=NO",
        ):
            self.assertIn(marker, self.source)
        for forbidden in (
            "urllib",
            "http.client",
            "requests",
            "curl",
            "wget",
            "control-d1-read-token",
            "github-app.pem",
            "systemctl",
            "StateStore",
            "cloudflare",
        ):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
