from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v5.py"
ENTRYPOINT_SOURCE = ROOT / "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v5"
UPGRADE_CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v5.json"
CHECKOUT_CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v5-trusted-checkout-bootstrap.json"
MAKEFILE = ROOT / "Makefile"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_public_runtime_operator_upgrade_v5 as upgrade


def run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


class WeatherOperatorEntrypointUpgradeV5Tests(unittest.TestCase):
    def test_source_contract_is_fixed_zero_input_and_inactive(self) -> None:
        ready = upgrade.source_readiness()
        self.assertEqual(ready["issue"], 515)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(
            ready["trusted_upgrade_checkout"],
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v5-trusted",
        )
        self.assertEqual(ready["predecessor_sha"], upgrade.PREDECESSOR_SHA)
        self.assertEqual(ready["target_old_sha256"], upgrade.TARGET_OLD_SHA256)
        self.assertEqual(ready["target_new_sha256"], upgrade.TARGET_NEW_SHA256)
        self.assertEqual(ready["mutation_target_count"], 1)
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

        source = ENTRYPOINT_SOURCE.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn("if len(sys.argv) != 1:", source)
        self.assertIn(
            '_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v5-trusted"',
            source,
        )
        self.assertIn("execute_upgrade()", source)
        self.assertNotIn("upgrade v4", source)
        for forbidden in (
            "argparse",
            "--path",
            "--command",
            "--argv",
            "--env",
            "--source",
            "--destination",
            "shell=True",
            "os.system",
            "subprocess.Popen",
            "sudo",
        ):
            self.assertNotIn(forbidden, source)

    def test_upgrade_contract_pins_exact_transition(self) -> None:
        contract = json.loads(UPGRADE_CONTRACT.read_text(encoding="utf-8"))
        upgrade._validate_upgrade_contract(contract)
        self.assertEqual(contract["predecessor_sha"], "c99f6b9df47603703f7d1e67ddc7d88c77ed726a")
        self.assertEqual(contract["minimum_target_ancestor"], "6cbe0a87e4b1ac56d0e44fea4a2249d3ef4c0135")
        self.assertEqual(contract["old_blob"], "2be2a8128eca470fd4c233d88410c415e4c8d438")
        self.assertEqual(contract["new_blob"], "b0f7b7269b9462605e8ef9e608f3441baf0f6392")
        self.assertEqual(contract["old_sha256"], "f5eaeb395ac374f074e9bf60c8f899371738be7c7cca1208c475e189f7d27ee5")
        self.assertEqual(contract["new_sha256"], "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f")
        self.assertEqual(contract["allowed_changed_artifacts"], [upgrade.TARGET_SOURCE])
        self.assertEqual(contract["target_destination"], str(upgrade.CANONICAL_ENTRYPOINT))
        self.assertEqual(contract["required_mode"], "0755")
        self.assertEqual(contract["mutation_target_count"], 1)
        self.assertEqual(contract["caller_arguments"], [])
        self.assertTrue(contract["replacement"]["atomic_replace"])
        self.assertTrue(contract["replacement"]["same_directory"])
        self.assertTrue(contract["replacement"]["fsync_before_replace"])
        self.assertTrue(contract["replacement"]["parent_fsync_after_replace"])
        self.assertFalse(contract["replacement"]["automatic_retry"])
        self.assertFalse(contract["replacement"]["automatic_cleanup"])
        self.assertFalse(contract["replacement"]["automatic_rollback"])
        self.assertFalse(contract["safety"]["source_merge_authorizes_live"])

    def test_checkout_contract_uses_new_identity_and_preserves_v4(self) -> None:
        contract = json.loads(CHECKOUT_CONTRACT.read_text(encoding="utf-8"))
        target = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v5-trusted"
        auth_sha = "EXPLICIT_WEATHER_OPERATOR_UPGRADE_V5_LIVE_EXACT_RPI5_MAIN_SHA"
        self.assertTrue(contract["source_only"])
        self.assertEqual(contract["manager_checkout"]["origin"], upgrade.REVIEWED_ORIGIN)
        self.assertFalse(contract["manager_checkout"]["working_tree_content_mutation_allowed"])
        self.assertEqual(contract["trusted_checkout"]["derivation"], target)
        self.assertTrue(contract["trusted_checkout"]["must_be_absent_before_first_mutation"])
        self.assertEqual(contract["trusted_checkout"]["minimum_reviewed_ancestor"], upgrade.MINIMUM_TARGET_ANCESTOR)
        self.assertEqual(
            [item["argv"] for item in contract["allowed_git_mutations"]],
            [
                ["git", "fetch", "origin", "main"],
                ["git", "worktree", "add", "--detach", target, auth_sha],
            ],
        )
        historical = {item["derivation"]: item for item in contract["historical_checkouts"]}
        v4 = historical["RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v4-trusted"]
        self.assertFalse(v4["mutation_allowed"])
        self.assertFalse(v4["cleanup_allowed"])
        self.assertFalse(v4["authority_source"])
        self.assertFalse(contract["failure"]["automatic_retry"])
        self.assertFalse(contract["failure"]["automatic_cleanup"])
        self.assertFalse(contract["failure"]["automatic_rollback"])
        self.assertFalse(contract["failure"]["alternate_checkout_route"])

    def test_source_diff_guard_allows_exactly_entrypoint(self) -> None:
        artifacts = upgrade._install_artifacts(ROOT)
        source_sha = run_git(ROOT, "rev-parse", "HEAD")
        self.assertEqual(run_git(ROOT, "merge-base", "--is-ancestor", upgrade.MINIMUM_TARGET_ANCESTOR, source_sha), "")
        reviewed = upgrade._source_diff_guard(ROOT, source_sha, artifacts)
        self.assertEqual(hashlib.sha256(reviewed).hexdigest(), upgrade.TARGET_NEW_SHA256)

        original = upgrade._git_blob_sha_at
        non_target = next(source for source, _destination, _mode in artifacts if source != upgrade.TARGET_SOURCE)

        def injected(checkout: Path, commit: str, relative: str) -> str:
            value = original(checkout, commit, relative)
            if commit == source_sha and relative == non_target:
                return "f" * 40
            return value

        with mock.patch.object(upgrade, "_git_blob_sha_at", side_effect=injected):
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._source_diff_guard(ROOT, source_sha, artifacts)

    @contextmanager
    def installed_fixture(self):
        artifacts = upgrade._install_artifacts(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            libexec = base / "libexec"
            sbin = base / "sbin"
            support = libexec / "rozkalns-weather-public-runtime-operator"
            package = support / "deploy_executor"
            entrypoint = sbin / "rozkalns-weather-public-runtime-operator"
            for directory in (libexec, sbin, support, package):
                directory.mkdir(parents=True, exist_ok=True)
                directory.chmod(0o755)

            for source, destination, mode in artifacts:
                if source == upgrade.TARGET_SOURCE:
                    data = subprocess.run(
                        ["/usr/bin/git", "-C", str(ROOT), "show", f"{upgrade.PREDECESSOR_SHA}:{source}"],
                        check=True,
                        stdout=subprocess.PIPE,
                    ).stdout
                else:
                    data = (ROOT / source).read_bytes()
                canonical = Path(destination)
                actual = entrypoint if canonical == upgrade.CANONICAL_ENTRYPOINT else support / canonical.relative_to(upgrade.CANONICAL_SUPPORT_ROOT)
                actual.parent.mkdir(parents=True, exist_ok=True)
                actual.write_bytes(data)
                actual.chmod(mode)

            with (
                mock.patch.object(upgrade, "ROOT_UID", os.getuid()),
                mock.patch.object(upgrade, "ROOT_GID", os.getgid()),
                mock.patch.object(upgrade, "ENTRYPOINT", entrypoint),
                mock.patch.object(upgrade, "SUPPORT_ROOT", support),
                mock.patch.object(upgrade, "PACKAGE_ROOT", package),
            ):
                yield artifacts, entrypoint, support

    def test_exact_predecessor_closure_and_atomic_one_target_replace(self) -> None:
        with self.installed_fixture() as (artifacts, entrypoint, support):
            upgrade._validate_installed_closure(ROOT, artifacts)
            support_before = {
                path.relative_to(support).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in support.rglob("*")
                if path.is_file()
            }
            self.assertEqual(hashlib.sha256(entrypoint.read_bytes()).hexdigest(), upgrade.TARGET_OLD_SHA256)
            reviewed = (ROOT / upgrade.TARGET_SOURCE).read_bytes()
            state = {"mutation_started": False, "target_replaced": False}
            upgrade._replace_exact_target(reviewed, state)
            self.assertEqual(state, {"mutation_started": True, "target_replaced": True})
            self.assertEqual(hashlib.sha256(entrypoint.read_bytes()).hexdigest(), upgrade.TARGET_NEW_SHA256)
            support_after = {
                path.relative_to(support).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in support.rglob("*")
                if path.is_file()
            }
            self.assertEqual(support_after, support_before)
            self.assertFalse((entrypoint.parent / upgrade.TEMP_NAME).exists())

    def test_wrong_predecessor_fails_before_mutation(self) -> None:
        with self.installed_fixture() as (artifacts, entrypoint, _support):
            entrypoint.write_text("tampered predecessor\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)
            self.assertFalse((entrypoint.parent / upgrade.TEMP_NAME).exists())

    def test_source_has_fail_closed_primitives_and_validate_wiring(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('getattr(os, "O_NOFOLLOW", 0)', source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.fsync(temp_fd)", source)
        self.assertIn("os.replace(", source)
        self.assertIn("os.fsync(parent_fd)", source)
        self.assertLess(source.index('state["mutation_started"] = True'), source.index("os.open(TEMP_NAME"))
        for forbidden in ("shell=True", "os.system", "eval(", "exec(", "sudo", "git reset", "git rebase", "git clean"):
            self.assertNotIn(forbidden, source)
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("python3 ./tests/test-deploy-executor-weather-public-operator-upgrade-v5.py", makefile)

    def test_public_source_contains_no_concrete_home_path(self) -> None:
        for path in (MODULE, ENTRYPOINT_SOURCE, UPGRADE_CONTRACT, CHECKOUT_CONTRACT):
            self.assertNotIn("/home/", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
