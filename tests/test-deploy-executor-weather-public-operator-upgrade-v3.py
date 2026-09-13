from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade_v3.py"
ENTRYPOINT_SOURCE = ROOT / "ops/bin/rozkalns-weather-public-runtime-operator-upgrade-v3"
UPGRADE_CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v3.json"
CHECKOUT_CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v3-trusted-checkout-bootstrap.json"
MAKEFILE = ROOT / "Makefile"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_public_runtime_operator_upgrade_v3 as upgrade


def run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


class WeatherOperatorEntrypointUpgradeV3Tests(unittest.TestCase):
    def test_source_contract_is_fixed_zero_input_and_inactive(self) -> None:
        ready = upgrade.source_readiness()
        self.assertEqual(ready["issue"], 496)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(
            ready["trusted_upgrade_checkout"],
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v3-trusted",
        )
        self.assertEqual(ready["predecessor_sha"], upgrade.PREDECESSOR_SHA)
        self.assertEqual(ready["target_source"], "ops/bin/rozkalns-weather-public-runtime-operator")
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
            '_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v3-trusted"',
            source,
        )
        self.assertIn("execute_upgrade()", source)
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

    def test_upgrade_contract_pins_exact_entrypoint_transition(self) -> None:
        contract = json.loads(UPGRADE_CONTRACT.read_text(encoding="utf-8"))
        upgrade._validate_upgrade_contract(contract)
        self.assertEqual(contract["predecessor_sha"], upgrade.PREDECESSOR_SHA)
        self.assertEqual(contract["minimum_target_ancestor"], upgrade.MINIMUM_TARGET_ANCESTOR)
        self.assertEqual(contract["allowed_changed_artifacts"], [upgrade.TARGET_SOURCE])
        self.assertEqual(contract["target_destination"], str(upgrade.CANONICAL_ENTRYPOINT))
        self.assertEqual(contract["old_blob"], upgrade.TARGET_OLD_BLOB)
        self.assertEqual(contract["new_blob"], upgrade.TARGET_NEW_BLOB)
        self.assertEqual(contract["old_sha256"], upgrade.TARGET_OLD_SHA256)
        self.assertEqual(contract["new_sha256"], upgrade.TARGET_NEW_SHA256)
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

    def test_checkout_contract_is_fixed_and_bounded(self) -> None:
        contract = json.loads(CHECKOUT_CONTRACT.read_text(encoding="utf-8"))
        target = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v3-trusted"
        auth_sha = "EXPLICIT_WEATHER_OPERATOR_UPGRADE_V3_LIVE_EXACT_RPI5_MAIN_SHA"
        self.assertTrue(contract["source_only"])
        self.assertEqual(contract["manager_checkout"]["origin"], upgrade.REVIEWED_ORIGIN)
        self.assertFalse(contract["manager_checkout"]["working_tree_content_mutation_allowed"])
        self.assertEqual(contract["trusted_checkout"]["derivation"], target)
        self.assertTrue(contract["trusted_checkout"]["must_be_absent_before_first_mutation"])
        self.assertEqual(
            contract["trusted_checkout"]["minimum_reviewed_ancestor"],
            upgrade.MINIMUM_TARGET_ANCESTOR,
        )
        self.assertEqual(
            [item["argv"] for item in contract["allowed_git_mutations"]],
            [
                ["git", "fetch", "origin", "main"],
                ["git", "worktree", "add", "--detach", target, auth_sha],
            ],
        )
        forbidden = set(contract["forbidden_git_operations"])
        self.assertTrue(
            {
                "reset",
                "rebase",
                "clean",
                "checkout",
                "switch",
                "merge",
                "pull",
                "worktree remove",
                "worktree prune",
                "branch",
                "commit",
                "push",
                "force",
            }.issubset(forbidden)
        )
        self.assertFalse(contract["failure"]["automatic_retry"])
        self.assertFalse(contract["failure"]["automatic_cleanup"])
        self.assertFalse(contract["failure"]["automatic_rollback"])
        self.assertFalse(contract["failure"]["alternate_checkout_route"])

    def test_source_diff_guard_allows_exactly_entrypoint_and_rejects_non_target_drift(self) -> None:
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
            for directory, mode in (
                (libexec, 0o755),
                (sbin, 0o755),
                (support, 0o755),
                (package, 0o755),
            ):
                directory.mkdir(parents=True, exist_ok=True)
                directory.chmod(mode)

            actual_paths: dict[str, Path] = {}
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
                if canonical == upgrade.CANONICAL_ENTRYPOINT:
                    actual = entrypoint
                else:
                    actual = support / canonical.relative_to(upgrade.CANONICAL_SUPPORT_ROOT)
                actual.parent.mkdir(parents=True, exist_ok=True)
                actual.write_bytes(data)
                actual.chmod(mode)
                actual_paths[source] = actual

            with (
                mock.patch.object(upgrade, "ROOT_UID", os.getuid()),
                mock.patch.object(upgrade, "ROOT_GID", os.getgid()),
                mock.patch.object(upgrade, "ENTRYPOINT", entrypoint),
                mock.patch.object(upgrade, "SUPPORT_ROOT", support),
                mock.patch.object(upgrade, "PACKAGE_ROOT", package),
            ):
                yield artifacts, actual_paths, entrypoint, support

    def add_valid_runtime_pycache(self, support: Path) -> Path:
        package = support / "deploy_executor"
        cache = package / "__pycache__"
        cache.mkdir(mode=0o755)
        cached = cache / "weather_public_runtime_operator.cpython-311.pyc"
        cached.write_bytes(b"runtime cache fixture")
        cached.chmod(0o644)
        return cache

    def test_runtime_pycache_is_allowed_but_not_canonical_membership(self) -> None:
        with self.installed_fixture() as (artifacts, _actual_paths, _entrypoint, support):
            self.add_valid_runtime_pycache(support)
            upgrade._validate_installed_closure(ROOT, artifacts)
            observed = upgrade._observed_support_membership()
            self.assertFalse(any("__pycache__" in item for item in observed))

    def test_runtime_pycache_rejects_unknown_or_unsafe_entries(self) -> None:
        with self.installed_fixture() as (artifacts, _actual_paths, _entrypoint, support):
            cache = self.add_valid_runtime_pycache(support)
            unknown = cache / "unknown_module.cpython-311.pyc"
            unknown.write_bytes(b"stale cache")
            unknown.chmod(0o644)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)

        with self.installed_fixture() as (artifacts, _actual_paths, _entrypoint, support):
            cache = self.add_valid_runtime_pycache(support)
            nested = cache / "nested"
            nested.mkdir(mode=0o755)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)

        with self.installed_fixture() as (artifacts, _actual_paths, _entrypoint, support):
            cache = self.add_valid_runtime_pycache(support)
            target = cache / "weather_public_runtime_operator.cpython-311.pyc"
            link = cache / "weather_public_runtime_composite.cpython-311.pyc"
            link.symlink_to(target.name)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)

    def test_unexpected_package_directory_still_fails_closed(self) -> None:
        with self.installed_fixture() as (artifacts, _actual_paths, _entrypoint, support):
            extra = support / "deploy_executor" / "unexpected"
            extra.mkdir(mode=0o755)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)

    def test_exact_predecessor_closure_passes_and_wrong_entrypoint_hash_fails(self) -> None:
        with self.installed_fixture() as (artifacts, _actual_paths, entrypoint, _support):
            upgrade._validate_installed_closure(ROOT, artifacts)
            entrypoint.write_text("tampered predecessor\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)
            self.assertFalse((entrypoint.parent / upgrade.TEMP_NAME).exists())

    def test_non_target_installed_artifact_drift_fails_before_mutation(self) -> None:
        with self.installed_fixture() as (artifacts, actual_paths, entrypoint, _support):
            non_target = next(source for source, _destination, _mode in artifacts if source != upgrade.TARGET_SOURCE)
            target = actual_paths[non_target]
            target.write_text("drift\n", encoding="utf-8")
            target.chmod(next(mode for source, _destination, mode in artifacts if source == non_target))
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)
            self.assertFalse((entrypoint.parent / upgrade.TEMP_NAME).exists())

    def test_atomic_publish_changes_only_fixed_entrypoint(self) -> None:
        with self.installed_fixture() as (_artifacts, _actual_paths, entrypoint, support):
            support_before = {
                path.relative_to(support).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in support.rglob("*")
                if path.is_file()
            }
            old_entrypoint = hashlib.sha256(entrypoint.read_bytes()).hexdigest()
            self.assertEqual(old_entrypoint, upgrade.TARGET_OLD_SHA256)
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

    def test_failure_after_first_write_preserves_temp_and_old_target(self) -> None:
        with self.installed_fixture() as (_artifacts, _actual_paths, entrypoint, _support):
            old = entrypoint.read_bytes()
            reviewed = (ROOT / upgrade.TARGET_SOURCE).read_bytes()
            state = {"mutation_started": False, "target_replaced": False}
            with mock.patch.object(os, "replace", side_effect=OSError("synthetic replace failure")):
                with self.assertRaises(OSError):
                    upgrade._replace_exact_target(reviewed, state)
            self.assertEqual(state, {"mutation_started": True, "target_replaced": False})
            self.assertEqual(entrypoint.read_bytes(), old)
            temp = entrypoint.parent / upgrade.TEMP_NAME
            self.assertTrue(temp.exists())
            self.assertEqual(temp.read_bytes(), reviewed)

    def test_source_has_atomic_fail_closed_primitives_and_validate_wiring(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('getattr(os, "O_NOFOLLOW", 0)', source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.fsync(temp_fd)", source)
        self.assertIn("os.replace(", source)
        self.assertIn("src_dir_fd=parent_fd", source)
        self.assertIn("dst_dir_fd=parent_fd", source)
        self.assertIn("os.fsync(parent_fd)", source)
        self.assertLess(source.index('state["mutation_started"] = True'), source.index("os.open(TEMP_NAME"))
        self.assertLess(source.index("os.fsync(temp_fd)"), source.index("os.replace("))
        for forbidden in (
            "shell=True",
            "os.system",
            "eval(",
            "exec(",
            "shutil.copytree",
            "sudo",
            "git reset",
            "git rebase",
            "git clean",
            "worktree remove",
            "worktree prune",
        ):
            self.assertNotIn(forbidden, source)
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn(
            "python3 ./tests/test-deploy-executor-weather-public-operator-upgrade-v3.py",
            makefile,
        )

    def test_public_source_contains_no_concrete_home_path(self) -> None:
        for path in (MODULE, ENTRYPOINT_SOURCE, UPGRADE_CONTRACT, CHECKOUT_CONTRACT):
            self.assertNotIn("/home/", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
