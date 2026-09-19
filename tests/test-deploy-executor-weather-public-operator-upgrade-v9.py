from __future__ import annotations

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
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_public_runtime_operator as operator
from deploy_executor import weather_public_runtime_operator_upgrade_v9 as upgrade


class WeatherImageIdCanonicalizationTests(unittest.TestCase):
    def test_full_sha256_prefixed_and_bare_compare_equal(self) -> None:
        digest = "a" * 64
        self.assertEqual(operator._canonical_image_id(digest, "bare"), f"sha256:{digest}")
        self.assertEqual(operator._canonical_image_id(f"sha256:{digest}", "prefixed"), f"sha256:{digest}")

    def test_different_full_digests_remain_different(self) -> None:
        left = operator._canonical_image_id("a" * 64, "left")
        right = operator._canonical_image_id("b" * 64, "right")
        self.assertNotEqual(left, right)

    def test_ambiguous_or_malformed_image_ids_fail_closed(self) -> None:
        invalid = (
            "",
            "a" * 12,
            "A" * 64,
            f"sha512:{'a' * 64}",
            f"sha256:{'a' * 63}",
            f"sha256:{'a' * 64}\nextra",
            f" {'a' * 64}",
            f"{'a' * 64} ",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    operator._canonical_image_id(value, "test")


class WeatherOperatorUpgradeV9Tests(unittest.TestCase):
    def test_source_contract_is_fixed_and_inactive(self) -> None:
        ready = upgrade.source_readiness()
        self.assertEqual(ready["issue"], 601)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(ready["predecessor_sha"], "77482a16fb77338d87b92a39ff8c63a5b6ce142d")
        self.assertEqual(ready["target_old_sha256"], "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb")
        self.assertEqual(ready["target_new_sha256"], "542412bc15123e6dc8c3f6505983676ba5c9622793ea7611693aacf13fb36974")
        for key in (
            "runtime_live_authority",
            "operator_upgrade_enabled",
            "operator_invocation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "generic_shell_authority",
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
        ):
            self.assertFalse(ready[key], key)

    def test_upgrade_contract_pins_exact_module_transition(self) -> None:
        path = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v9.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        upgrade._validate_upgrade_contract(contract)
        self.assertEqual(contract["old_blob"], "c7f089f4535779e3ef507af4564b3fbadb2bbd2a")
        self.assertEqual(contract["new_blob"], "185bfeecbc5707bccaae1eefea3791948a906331")
        self.assertEqual(
            hashlib.sha256((ROOT / upgrade.TARGET_SOURCE).read_bytes()).hexdigest(),
            upgrade.TARGET_NEW_SHA256,
        )
        self.assertEqual(contract["required_mode"], "0644")
        self.assertEqual(contract["allowed_changed_artifacts"], [upgrade.TARGET_SOURCE])
        self.assertFalse(contract["safety"]["source_merge_authorizes_live"])

    def test_source_diff_guard_allows_exactly_operator_module(self) -> None:
        artifacts = upgrade._install_artifacts(ROOT)
        source_sha = subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        reviewed = upgrade._source_diff_guard(ROOT, source_sha, artifacts)
        self.assertEqual(reviewed, (ROOT / upgrade.TARGET_SOURCE).read_bytes())

    def test_checkout_contract_preserves_v8_and_bounds_v9(self) -> None:
        path = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-operator-upgrade-v9-trusted-checkout-bootstrap.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(contract["source_only"])
        self.assertFalse(contract["source_merge_enables_live"])
        self.assertEqual(contract["trusted_checkout"]["minimum_reviewed_ancestor"], upgrade.MINIMUM_TARGET_ANCESTOR)
        self.assertEqual(len(contract["allowed_git_mutations"]), 2)
        historical = contract["historical_checkouts"]
        self.assertEqual(historical[0]["derivation"], "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-v8-trusted")
        self.assertFalse(historical[0]["mutation_allowed"])
        self.assertFalse(historical[0]["cleanup_allowed"])

    def membership_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        support = Path(tmp.name) / "support"
        package = support / "deploy_executor"
        package.mkdir(parents=True)
        support.chmod(0o755)
        package.chmod(0o755)
        registry = support / "executor-operations.json"
        registry.write_text("{}\n", encoding="utf-8")
        registry.chmod(0o644)
        module = package / "module.py"
        module.write_text("VALUE = 1\n", encoding="utf-8")
        module.chmod(0o644)
        return tmp, support, package

    def membership_patches(self, support: Path):
        return (
            mock.patch.object(upgrade._engine, "ROOT_UID", os.getuid()),
            mock.patch.object(upgrade._engine, "ROOT_GID", os.getgid()),
            mock.patch.object(upgrade._engine, "SUPPORT_ROOT", support),
        )

    def test_support_membership_allows_bounded_python_cache(self) -> None:
        tmp, support, package = self.membership_fixture()
        self.addCleanup(tmp.cleanup)
        cache = package / "__pycache__"
        cache.mkdir()
        cache.chmod(0o755)
        pyc = cache / "module.cpython-311.pyc"
        pyc.write_bytes(b"bounded bytecode cache")
        pyc.chmod(0o644)
        uid_patch, gid_patch, support_patch = self.membership_patches(support)
        with uid_patch, gid_patch, support_patch:
            observed = upgrade._observed_support_membership()
        self.assertEqual(observed, {"executor-operations.json", "deploy_executor/module.py"})

    def test_support_membership_rejects_unexpected_directory(self) -> None:
        tmp, support, package = self.membership_fixture()
        self.addCleanup(tmp.cleanup)
        unexpected = package / "unexpected"
        unexpected.mkdir()
        unexpected.chmod(0o755)
        uid_patch, gid_patch, support_patch = self.membership_patches(support)
        with uid_patch, gid_patch, support_patch:
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._observed_support_membership()

    def test_support_membership_rejects_malformed_python_cache(self) -> None:
        tmp, support, package = self.membership_fixture()
        self.addCleanup(tmp.cleanup)
        cache = package / "__pycache__"
        cache.mkdir()
        cache.chmod(0o755)
        invalid = cache / "unexpected.txt"
        invalid.write_text("not bytecode\n", encoding="utf-8")
        invalid.chmod(0o644)
        uid_patch, gid_patch, support_patch = self.membership_patches(support)
        with uid_patch, gid_patch, support_patch:
            with self.assertRaises(upgrade.WeatherOperatorUpgradeError):
                upgrade._observed_support_membership()


if __name__ == "__main__":
    unittest.main(verbosity=2)
