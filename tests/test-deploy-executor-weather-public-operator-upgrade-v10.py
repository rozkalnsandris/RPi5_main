from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_public_runtime_operator_upgrade_v10 as upgrade

BASE_SHA = "3a4a95bccf13892c4cc9f997ee934c02b134ccb7"
V9_FROZEN_PATHS = (
    "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v9.py",
    "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v9",
    "ops/deploy/weather-public-runtime-operator-upgrade-v9.json",
    "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v9-trusted-checkout-bootstrap.json",
    "tests/test-deploy-executor-weather-public-operator-upgrade-v9.py",
    "tests/test-weather-operator-v9-canonical-operation.py",
    "tests/test-weather-operator-v9-capability-module-refresh.py",
)


def git_text(*args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), *args],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


class WeatherOperatorUpgradeV10Tests(unittest.TestCase):
    def test_source_contract_is_fixed_and_inactive(self) -> None:
        ready = upgrade.source_readiness()
        self.assertEqual(ready["issue"], 641)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(
            ready["predecessor_sha"],
            "77482a16fb77338d87b92a39ff8c63a5b6ce142d",
        )
        self.assertEqual(
            ready["target_old_sha256"],
            "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb",
        )
        self.assertEqual(
            ready["target_new_blob"],
            "ca3e94935c9871d85eb4d8d13ab470ad3ad66b78",
        )
        self.assertEqual(
            ready["target_new_sha256"],
            hashlib.sha256((ROOT / upgrade.TARGET_SOURCE).read_bytes()).hexdigest(),
        )
        self.assertEqual(
            ready["target_new_sha256_binding"],
            "DERIVED_FROM_EXACT_TARGET_BLOB_PRE_MUTATION",
        )
        for key in (
            "runtime_live_authority",
            "operator_upgrade_enabled",
            "operator_invocation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
            "generic_shell_authority",
            "caller_supplied_path_allowed",
            "caller_supplied_argv_allowed",
            "caller_supplied_environment_allowed",
            "caller_supplied_repository_url_allowed",
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
        ):
            self.assertFalse(ready[key], key)

    def test_exact_target_blob_and_source_diff_guard_are_bound(self) -> None:
        head = git_text("rev-parse", "HEAD")
        target_blob = git_text("rev-parse", f"{head}:{upgrade.TARGET_SOURCE}")
        self.assertEqual(target_blob, upgrade.TARGET_NEW_BLOB)
        artifacts = upgrade._install_artifacts(ROOT)
        reviewed = upgrade._source_diff_guard(ROOT, head, artifacts)
        self.assertEqual(reviewed, (ROOT / upgrade.TARGET_SOURCE).read_bytes())
        self.assertEqual(hashlib.sha256(reviewed).hexdigest(), upgrade.TARGET_NEW_SHA256)

    def test_upgrade_contract_pins_one_file_transition_and_no_live_authority(self) -> None:
        contract = json.loads(
            (ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v10.json").read_text(
                encoding="utf-8"
            )
        )
        upgrade._validate_upgrade_contract(contract)
        self.assertEqual(contract["old_blob"], upgrade.TARGET_OLD_BLOB)
        self.assertEqual(contract["new_blob"], upgrade.TARGET_NEW_BLOB)
        self.assertEqual(contract["old_sha256"], upgrade.TARGET_OLD_SHA256)
        self.assertEqual(contract["mutation_target_count"], 1)
        self.assertEqual(contract["allowed_changed_artifacts"], [upgrade.TARGET_SOURCE])
        self.assertEqual(contract["required_mode"], "0644")
        self.assertFalse(contract["safety"]["source_merge_authorizes_live"])
        self.assertFalse(contract["safety"]["runtime_live_authority"])
        self.assertFalse(contract["replacement"]["automatic_retry"])
        self.assertFalse(contract["replacement"]["automatic_cleanup"])
        self.assertFalse(contract["replacement"]["automatic_rollback"])

    def test_checkout_contract_is_bounded_and_preserves_historical_evidence(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v10-trusted-checkout-bootstrap.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(contract["source_only"])
        self.assertFalse(contract["source_merge_enables_live"])
        self.assertEqual(
            contract["trusted_checkout"]["minimum_reviewed_ancestor"],
            upgrade.MINIMUM_TARGET_ANCESTOR,
        )
        mutations = contract["allowed_git_mutations"]
        self.assertEqual(len(mutations), 2)
        self.assertEqual([row["max_operations"] for row in mutations], [1, 1])
        self.assertEqual(mutations[0]["argv"], ["git", "fetch", "origin", "main"])
        self.assertEqual(mutations[1]["argv"][:4], ["git", "worktree", "add", "--detach"])
        for row in contract["historical_checkouts"]:
            self.assertFalse(row["mutation_allowed"])
            self.assertFalse(row["cleanup_allowed"])
            self.assertFalse(row["authority_source"])
        failure = contract["failure"]
        self.assertFalse(failure["automatic_retry"])
        self.assertFalse(failure["automatic_cleanup"])
        self.assertFalse(failure["automatic_rollback"])

    def test_v10_entrypoint_is_executable_fixed_root_no_args(self) -> None:
        path = "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v10"
        index = git_text("ls-files", "-s", "--", path).split()
        self.assertGreaterEqual(len(index), 4)
        self.assertEqual(index[0], "100755")
        source = (ROOT / path).read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn("len(sys.argv) != 1", source)
        self.assertIn("os.geteuid() != 0", source)
        self.assertIn("_CHECKOUT_NAME", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("sudo", source)

    def test_historical_v9_source_contract_and_tests_remain_frozen(self) -> None:
        for path in V9_FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertEqual(
                    git_bytes("HEAD", path),
                    git_bytes(BASE_SHA, path),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
