from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ops/lib/deploy_executor/weather_public_runtime_operator_install.py"
ENTRYPOINT = ROOT / "ops/bin/rozkalns-weather-public-runtime-operator-install"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-install.json"
TRUSTED_DERIVATION = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted"
sys.path.insert(0, str(ROOT / "ops/lib"))

import deploy_executor.weather_public_runtime_operator_install as bridge


class WeatherOperatorInstallerSourceTests(unittest.TestCase):
    def test_source_readiness_is_zero_input_and_inactive(self) -> None:
        ready = bridge.source_readiness()
        self.assertEqual(ready["issue"], 462)
        self.assertEqual(ready["caller_authority"], ())
        self.assertEqual(ready["trusted_install_checkout"], TRUSTED_DERIVATION)
        self.assertEqual(ready["artifact_count"], 23)
        self.assertTrue(ready["capability_specific_root_entrypoint_source_present"])
        for key in (
            "runtime_live_authority",
            "operator_installation_enabled",
            "operator_invocation_enabled",
            "helper_invocation_enabled",
            "production_mutation_enabled",
            "production_mutation_started",
            "generic_shell_authority",
            "caller_supplied_path_allowed",
            "caller_supplied_argv_allowed",
            "caller_supplied_environment_allowed",
            "automatic_retry",
            "automatic_cleanup",
            "automatic_rollback",
        ):
            self.assertFalse(ready[key], key)

    def test_entrypoint_is_isolated_zero_argument_source(self) -> None:
        source = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn("if len(sys.argv) != 1:", source)
        self.assertIn('_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-install-trusted"', source)
        self.assertIn("Path(__file__).resolve().parents[2]", source)
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
        ):
            self.assertNotIn(forbidden, source)

    def test_contract_is_exact_23_artifact_allowlist(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        artifacts = bridge._validate_contract(contract)
        self.assertEqual(artifacts, bridge.expected_install_artifacts())
        self.assertEqual(len(artifacts), 23)
        installer = contract["installer_bridge"]
        self.assertEqual(installer["issue"], 462)
        self.assertEqual(installer["status"], "SOURCE_ONLY_INSTALLER_BRIDGE_INACTIVE")
        self.assertEqual(installer["caller_arguments"], [])
        self.assertEqual(installer["publication_order"], ["support_root", "entrypoint"])
        self.assertTrue(installer["partial_support_without_entrypoint_is_inert"])
        self.assertFalse(installer["source_merge_enables_install"])
        self.assertEqual(
            installer["source_entrypoint"],
            f"{TRUSTED_DERIVATION}/ops/bin/rozkalns-weather-public-runtime-operator-install",
        )

    def test_contract_destination_drift_fails_closed(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        changed = copy.deepcopy(contract)
        changed["artifacts"][0]["destination"] = "/usr/local/sbin/not-weather"
        with self.assertRaises(bridge.WeatherOperatorInstallError):
            bridge._validate_contract(changed)

    def test_tracked_source_must_match_head_blob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["/usr/bin/git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["/usr/bin/git", "config", "user.name", "Weather Test"], cwd=repo, check=True)
            subprocess.run(["/usr/bin/git", "config", "user.email", "fixture.invalid"], cwd=repo, check=True)
            source = repo / "ops/example.txt"
            source.parent.mkdir(parents=True)
            source.write_text("reviewed\n", encoding="utf-8")
            subprocess.run(["/usr/bin/git", "add", "ops/example.txt"], cwd=repo, check=True)
            subprocess.run(["/usr/bin/git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True)
            data, digest = bridge._read_bound_source(repo, "ops/example.txt")
            self.assertEqual(data, b"reviewed\n")
            self.assertEqual(len(digest), 64)
            source.write_text("drifted\n", encoding="utf-8")
            with self.assertRaises(bridge.WeatherOperatorInstallError):
                bridge._read_bound_source(repo, "ops/example.txt")

    def test_support_publication_precedes_entrypoint_and_is_no_replace(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        support_publish = "_rename_noreplace(support_stage, SUPPORT_ROOT)"
        entry_publish = "_rename_noreplace(entry_stage, ENTRYPOINT)"
        self.assertIn(support_publish, source)
        self.assertIn(entry_publish, source)
        self.assertLess(source.index(support_publish), source.index(entry_publish))
        self.assertIn("_path_absent(path, label)", source)
        self.assertIn("_verify_support(SUPPORT_ROOT, artifacts, hashes)", source)
        for forbidden in (
            "shell=True",
            "os.system",
            "eval(",
            "exec(",
            "shutil.copytree",
            "sudo",
            "PYTHONPATH",
        ):
            self.assertNotIn(forbidden, source)

    def test_public_source_contains_no_concrete_home_path(self) -> None:
        for path in (MODULE, ENTRYPOINT, CONTRACT):
            self.assertNotIn("/home/", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
