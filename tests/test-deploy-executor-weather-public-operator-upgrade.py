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
MODULE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator_upgrade.py"
ENTRYPOINT_SOURCE = ROOT / "ops/bin/rozkalns-weather-public-runtime-operator-upgrade"
UPGRADE_CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade.json"
CHECKOUT_CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-trusted-checkout-bootstrap.json"
INSTALL_CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-install.json"
DOC = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_EXECUTOR_SOURCE.md"
MAKEFILE = ROOT / "Makefile"
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_public_runtime_operator_upgrade as upgrade


def run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


class WeatherOperatorUpgradeSourceTests(unittest.TestCase):
    def test_source_readiness_is_zero_input_and_inactive(self) -> None:
        ready = upgrade.source_readiness()
        self.assertEqual(ready["issue"], 487)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(
            ready["trusted_upgrade_checkout"],
            "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-trusted",
        )
        self.assertEqual(ready["predecessor_sha"], upgrade.PREDECESSOR_SHA)
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

    def test_entrypoint_is_fixed_zero_argument_source(self) -> None:
        source = ENTRYPOINT_SOURCE.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn("if len(sys.argv) != 1:", source)
        self.assertIn(
            '_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-trusted"',
            source,
        )
        self.assertIn("Path(__file__).resolve().parents[2]", source)
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

    def test_upgrade_contract_pins_one_exact_transition(self) -> None:
        contract = json.loads(UPGRADE_CONTRACT.read_text(encoding="utf-8"))
        upgrade._validate_upgrade_contract(contract)
        self.assertEqual(contract["predecessor_sha"], upgrade.PREDECESSOR_SHA)
        self.assertEqual(contract["allowed_changed_artifacts"], [upgrade.TARGET_SOURCE])
        self.assertEqual(contract["old_blob"], upgrade.TARGET_OLD_BLOB)
        self.assertEqual(contract["new_blob"], upgrade.TARGET_NEW_BLOB)
        self.assertEqual(contract["old_sha256"], upgrade.TARGET_OLD_SHA256)
        self.assertEqual(contract["new_sha256"], upgrade.TARGET_NEW_SHA256)
        self.assertEqual(contract["mutation_target_count"], 1)
        self.assertEqual(contract["caller_arguments"], [])
        self.assertTrue(contract["replacement"]["atomic_replace"])
        self.assertTrue(contract["replacement"]["same_directory"])
        self.assertTrue(contract["replacement"]["fsync_before_replace"])
        self.assertTrue(contract["replacement"]["parent_fsync_after_replace"])
        self.assertFalse(contract["replacement"]["automatic_cleanup"])
        self.assertFalse(contract["safety"]["source_merge_authorizes_live"])

    def test_install_contract_links_inactive_upgrade_bridge(self) -> None:
        contract = json.loads(INSTALL_CONTRACT.read_text(encoding="utf-8"))
        bridge = contract["compatibility_upgrade_bridge"]
        self.assertEqual(bridge["issue"], 487)
        self.assertEqual(bridge["status"], "SOURCE_ONLY_UPGRADE_BRIDGE_INACTIVE")
        self.assertEqual(bridge["caller_arguments"], [])
        self.assertEqual(bridge["upgradable_artifact"], upgrade.TARGET_SOURCE)
        self.assertFalse(bridge["source_merge_enables_upgrade"])
        self.assertFalse(bridge["generic_shell_authority"])
        self.assertFalse(bridge["caller_selected_path"])
        self.assertFalse(bridge["caller_selected_argv"])
        self.assertFalse(bridge["caller_selected_environment"])

    def test_checkout_contract_is_fixed_and_bounded(self) -> None:
        contract = json.loads(CHECKOUT_CONTRACT.read_text(encoding="utf-8"))
        target = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-trusted"
        auth_sha = "EXPLICIT_WEATHER_OPERATOR_UPGRADE_LIVE_EXACT_RPI5_MAIN_SHA"
        self.assertEqual(
            contract["schema"],
            "rozkalns.rpi5-main.weather-public-runtime-operator-upgrade-trusted-checkout-bootstrap.v1",
        )
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
        self.assertFalse(contract["failure"]["manager_repair"])
        self.assertFalse(contract["failure"]["alternate_checkout_route"])

    def test_source_diff_guard_allows_exactly_operator_module(self) -> None:
        artifacts = upgrade._install_artifacts(ROOT)
        source_sha = run_git(ROOT, "rev-parse", "HEAD")
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

            with (
                mock.patch.object(upgrade, "ROOT_UID", os.getuid()),
                mock.patch.object(upgrade, "ROOT_GID", os.getgid()),
                mock.patch.object(upgrade, "ENTRYPOINT", entrypoint),
                mock.patch.object(upgrade, "SUPPORT_ROOT", support),
                mock.patch.object(upgrade, "PACKAGE_ROOT", package),
            ):
                yield artifacts, entrypoint, support, package

    def test_exact_predecessor_installed_closure_passes_pre_mutation_validation(self) -> None:
        with self.installed_fixture() as (artifacts, _entrypoint, _support, _package):
            upgrade._validate_installed_closure(ROOT, artifacts)

    def test_wrong_predecessor_hash_fails_before_mutation(self) -> None:
        with self.installed_fixture() as (artifacts, _entrypoint, _support, package):
            target = package / upgrade.TARGET_FILENAME
            target.write_text("tampered predecessor\n", encoding="utf-8")
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)
            self.assertFalse((package / upgrade.TEMP_NAME).exists())

    def test_non_target_installed_artifact_drift_fails_before_mutation(self) -> None:
        with self.installed_fixture() as (artifacts, entrypoint, _support, package):
            entrypoint.write_text("drift\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._validate_installed_closure(ROOT, artifacts)
            self.assertFalse((package / upgrade.TEMP_NAME).exists())

    def test_atomic_publish_replaces_exactly_one_fixed_destination(self) -> None:
        with self.installed_fixture() as (_artifacts, entrypoint, support, package):
            before = {
                path.relative_to(support).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in support.rglob("*")
                if path.is_file()
            }
            entry_before = hashlib.sha256(entrypoint.read_bytes()).hexdigest()
            reviewed = (ROOT / upgrade.TARGET_SOURCE).read_bytes()
            state = {"mutation_started": False, "target_replaced": False}
            upgrade._replace_exact_target(reviewed, state)
            self.assertEqual(state, {"mutation_started": True, "target_replaced": True})
            self.assertEqual(
                hashlib.sha256((package / upgrade.TARGET_FILENAME).read_bytes()).hexdigest(),
                upgrade.TARGET_NEW_SHA256,
            )
            after = {
                path.relative_to(support).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in support.rglob("*")
                if path.is_file()
            }
            changed = {name for name in before if before[name] != after[name]}
            self.assertEqual(changed, {f"deploy_executor/{upgrade.TARGET_FILENAME}"})
            self.assertEqual(hashlib.sha256(entrypoint.read_bytes()).hexdigest(), entry_before)
            self.assertFalse((package / upgrade.TEMP_NAME).exists())

    def test_failure_after_first_write_preserves_temp_and_old_target(self) -> None:
        with self.installed_fixture() as (_artifacts, _entrypoint, _support, package):
            target = package / upgrade.TARGET_FILENAME
            old = target.read_bytes()
            reviewed = (ROOT / upgrade.TARGET_SOURCE).read_bytes()
            state = {"mutation_started": False, "target_replaced": False}
            with mock.patch.object(os, "replace", side_effect=OSError("synthetic replace failure")):
                with self.assertRaises(OSError):
                    upgrade._replace_exact_target(reviewed, state)
            self.assertEqual(state, {"mutation_started": True, "target_replaced": False})
            self.assertEqual(target.read_bytes(), old)
            temp = package / upgrade.TEMP_NAME
            self.assertTrue(temp.exists())
            self.assertEqual(temp.read_bytes(), reviewed)

    @contextmanager
    def trusted_checkout_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / upgrade.TRUSTED_CHECKOUT_NAME
            checkout.mkdir()
            run_git(checkout, "init", "-q")
            run_git(checkout, "config", "user.name", "Weather Test")
            run_git(checkout, "config", "user.email", "fixture.invalid")
            seed = checkout / "seed.txt"
            seed.write_text("seed\n", encoding="utf-8")
            run_git(checkout, "add", "seed.txt")
            run_git(checkout, "commit", "-q", "-m", "seed")
            base = run_git(checkout, "rev-parse", "HEAD")
            for relative in (
                upgrade.install.CONTRACT_RELATIVE,
                upgrade.UPGRADE_CONTRACT_RELATIVE,
                upgrade.CHECKOUT_CONTRACT_RELATIVE,
                upgrade.UPGRADE_ENTRYPOINT_RELATIVE,
                upgrade.UPGRADE_MODULE_RELATIVE,
                Path(upgrade.TARGET_SOURCE),
            ):
                path = checkout / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{relative}\n", encoding="utf-8")
            run_git(checkout, "add", ".")
            run_git(checkout, "commit", "-q", "-m", "target")
            head = run_git(checkout, "rev-parse", "HEAD")
            run_git(checkout, "remote", "add", "origin", upgrade.REVIEWED_ORIGIN)
            run_git(checkout, "update-ref", "refs/remotes/origin/main", head)
            run_git(checkout, "checkout", "--detach", "-q", head)
            with mock.patch.object(upgrade, "MINIMUM_TARGET_ANCESTOR", base):
                yield checkout, base, head

    def test_trusted_checkout_exact_state_passes(self) -> None:
        with self.trusted_checkout_fixture() as (checkout, _base, head):
            self.assertEqual(upgrade._validate_trusted_checkout(checkout), head)

    def test_trusted_checkout_wrong_sha_dirty_attached_or_origin_fails(self) -> None:
        cases = ("wrong_sha", "dirty", "attached", "wrong_origin")
        for case in cases:
            with self.subTest(case=case):
                with self.trusted_checkout_fixture() as (checkout, base, _head):
                    if case == "wrong_sha":
                        run_git(checkout, "update-ref", "refs/remotes/origin/main", base)
                    elif case == "dirty":
                        (checkout / "seed.txt").write_text("dirty\n", encoding="utf-8")
                    elif case == "attached":
                        run_git(checkout, "switch", "-q", "-c", "attached")
                    elif case == "wrong_origin":
                        run_git(checkout, "remote", "set-url", "origin", "https://example.invalid/RPi5_main.git")
                    with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                        upgrade._validate_trusted_checkout(checkout)

    def test_source_has_no_generic_authority_or_automatic_recovery(self) -> None:
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

    def test_docs_and_validate_target_are_wired(self) -> None:
        doc = DOC.read_text(encoding="utf-8")
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("Issue #487", doc)
        self.assertIn("RPi5_main-weather-public-runtime-operator-upgrade-trusted", doc)
        self.assertIn("weather-public-runtime-operator-upgrade.json", doc)
        self.assertIn(
            "python3 ./tests/test-deploy-executor-weather-public-operator-install.py",
            makefile,
        )
        self.assertIn(
            "python3 ./tests/test-deploy-executor-weather-public-operator-upgrade.py",
            makefile,
        )

    def test_public_source_contains_no_concrete_home_path(self) -> None:
        for path in (MODULE, ENTRYPOINT_SOURCE, UPGRADE_CONTRACT, CHECKOUT_CONTRACT):
            self.assertNotIn("/home/", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
