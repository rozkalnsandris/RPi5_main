from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import p9_control_postcanary_producer as producer

OPERATOR = (
    ROOT
    / "scripts"
    / "install-deploy-executor-p9-gate-d-final-lifecycle-producer-upgrade.py"
)


def _target_evidence(issue: object) -> producer.ControlPostCanaryTargetEvidence:
    return producer.ControlPostCanaryTargetEvidence(
        target_issue_number=25,
        target_issue=issue,  # type: ignore[arg-type]
        target_pr_number=24,
        target_pr={},
        expected_pr_head="0" * 40,
        expected_old_main="1" * 40,
        expected_merge_sha="2" * 40,
        target_merge_commit={},
        target_compare={},
    )


def _load_operator():
    spec = importlib.util.spec_from_file_location(
        "p9_gate_d_final_lifecycle_producer_upgrade", OPERATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FinalLifecyclePredicateTests(unittest.TestCase):
    def test_existing_open_issue_contract_remains_accepted(self):
        issue = {"number": 25, "state": "open"}
        self.assertTrue(producer._target_issue_lifecycle_exact(issue))
        self.assertIsNone(producer._target_issue_failure_code(_target_evidence(issue)))

    def test_completed_closed_issue_is_accepted(self):
        issue = {
            "number": 25,
            "state": "closed",
            "state_reason": "completed",
            "closed_at": "2026-08-31T12:46:03Z",
        }
        self.assertTrue(producer._target_issue_lifecycle_exact(issue))
        self.assertIsNone(producer._target_issue_failure_code(_target_evidence(issue)))

    def test_closed_issue_requires_completed_reason_and_closed_at(self):
        invalid = (
            {
                "number": 25,
                "state": "closed",
                "state_reason": "not_planned",
                "closed_at": "2026-08-31T12:46:03Z",
            },
            {"number": 25, "state": "closed", "state_reason": "completed"},
            {
                "number": 25,
                "state": "closed",
                "state_reason": "completed",
                "closed_at": "",
            },
            {"number": 25, "state": "closed"},
        )
        for issue in invalid:
            with self.subTest(issue=issue):
                self.assertFalse(producer._target_issue_lifecycle_exact(issue))
                self.assertEqual(
                    producer._target_issue_failure_code(_target_evidence(issue)),
                    "TARGET_ISSUE_NOT_OPEN",
                )

    def test_issue_identity_and_non_pr_guards_still_apply_after_completion(self):
        completed = {
            "number": 25,
            "state": "closed",
            "state_reason": "completed",
            "closed_at": "2026-08-31T12:46:03Z",
        }
        wrong_number = dict(completed, number=26)
        self.assertEqual(
            producer._target_issue_failure_code(_target_evidence(wrong_number)),
            "TARGET_ISSUE_NUMBER_MISMATCH",
        )
        as_pr = dict(completed, pull_request={"url": "sanitized"})
        self.assertEqual(
            producer._target_issue_failure_code(_target_evidence(as_pr)),
            "TARGET_ISSUE_IS_PULL_REQUEST",
        )


class FinalLifecycleProducerUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_operator()
        cls.source = OPERATOR.read_text(encoding="utf-8")

    def test_exact_one_target_contract_binds_current_installed_producer_prestate(self):
        target = self.module.TARGET
        self.assertEqual(
            (
                target.source_path,
                str(target.target_path),
                target.old_blob_sha,
                target.mode,
            ),
            (
                "ops/lib/deploy_executor/p9_control_postcanary_producer.py",
                "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/"
                "p9_control_postcanary_producer.py",
                "d9c6601b55c11942335648ba2f4795ec9713143f",
                0o644,
            ),
        )

    def test_operator_preflight_is_exact_and_non_mutating_without_apply(self):
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
        self.assertIn("P9_GATE_D_FINAL_LIFECYCLE_PRODUCER_MUTATION=NO", preflight)
        self.assertGreaterEqual(source.count("_preflight(args.expected_sha)"), 2)

    def test_operator_is_one_target_in_place_without_retry_or_rollback(self):
        source = self.source
        mutation = source[
            source.index("A separately owner-authorized one-target live mutation begins here") :
        ]
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

    def test_operator_has_no_unrelated_live_surface(self):
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
            "control_center_postcanary_adapter.py",
            "p9_control_postcanary_collector.py",
            "rozkalns-deploy-p9-control-baseline",
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
            "ADAPTER_TOUCHED=NO",
            "PRODUCER_TOUCHED=YES",
            "COLLECTOR_TOUCHED=NO",
            "BASELINE_CLI_TOUCHED=NO",
        ):
            self.assertIn(marker, source)

    def test_operator_revalidates_inode_before_first_truncate(self):
        source = self.source
        fn = source[
            source.index("def _replace_exact_target") : source.index("def _parse_args")
        ]
        truncate_at = fn.index("os.ftruncate(fd, 0)")
        self.assertLess(fn.index("os.fstat(fd)"), truncate_at)
        self.assertLess(fn.index("_git_blob_sha(current)"), truncate_at)
        self.assertLess(
            fn.index("os.stat(TARGET.target_path, follow_symlinks=False)"),
            truncate_at,
        )
        self.assertIn("os.O_NOFOLLOW", fn)
        self.assertGreater(fn.index("if _read_fd_all(fd) != reviewed_bytes"), truncate_at)


if __name__ == "__main__":
    unittest.main()
