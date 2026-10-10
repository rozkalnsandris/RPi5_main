#!/usr/bin/env python3
"""Synthetic adversarial regressions for the non-executable Hermes v4 preflight."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v4.py"
CONTRACT = ROOT / "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v4.json"
DOC = ROOT / "docs/SIMPLE_DEPLOY_HERMES_PREREQUISITE_MATERIALIZATION_V4.md"
MAKEFILE = ROOT / "Makefile"
spec = importlib.util.spec_from_file_location("hermes_v4_under_test", SCRIPT)
assert spec and spec.loader
v4 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v4
spec.loader.exec_module(v4)


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.uid = os.getuid()
        self.gid = os.getgid()
        checkout = self.home / "checkout"
        source_data = checkout / "data/raw"
        source_config = checkout / "config"
        source_env = checkout / ".env"
        etc_root = self.home / "etc"
        parent = etc_root / "private"
        state_parent = self.home / "state"
        for p in (source_data, source_config, parent, state_parent):
            p.mkdir(parents=True, exist_ok=True)
        for p in (checkout, checkout / "data", source_data, source_config, etc_root):
            os.chmod(p, 0o755)
        os.chmod(parent, 0o750)
        os.chmod(state_parent, 0o700)
        source_env.write_text("SYNTHETIC=ONLY\n", encoding="utf-8")
        os.chmod(source_env, 0o600)
        self.paths = v4.v2.MaterializationPaths(
            checkout=checkout, source_data=source_data, source_config=source_config,
            source_env=source_env, etc_root=etc_root, state_parent=state_parent,
            target_root=state_parent / "hermes-deals",
            target_data_parent=state_parent / "hermes-deals/data",
            target_data=state_parent / "hermes-deals/data/raw",
            target_config=state_parent / "hermes-deals/config",
            private_root=parent, target_env=parent / "hermes-deals-api.env",
            state_stage=state_parent / ".hermes-deals-prerequisites-v1.staged",
            env_stage=parent / ".hermes-deals-api.env.prerequisites-v1.staged",
        )

    def result(self, exclusive=True):
        with mock.patch.object(v4, "_exclusive_runtime_group", return_value=exclusive):
            return v4._classify(
                self.paths, source_uid=self.uid, source_gid=self.gid,
                runtime_uid=self.uid, runtime_gid=self.gid,
                root_uid=self.uid, root_gid=self.gid
            )

    def publish_synthetic_children(self):
        state = self.paths.target_root
        (state / "data/raw").mkdir(parents=True)
        (state / "config").mkdir()
        for p in (state, state / "data", state / "data/raw", state / "config"):
            os.chmod(p, 0o755)
        self.paths.target_env.write_text("SYNTHETIC=ONLY\n", encoding="utf-8")
        os.chmod(self.paths.target_env, 0o640)

    def close(self):
        self.temp.cleanup()


class HermesV4SourceTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def test_parent_preflight_is_default_deny_not_live(self):
        self.assertEqual(self.fx.result().status, v4.STATUS_ABSENT)
        response = v4._public_result(self.fx.result())
        for key in ("activation_eligible", "apply_available", "mutation_started",
                    "protected_content_read", "protected_values_emitted"):
            self.assertFalse(response[key], key)
        self.assertEqual(response["consumer_access"], "NOT_PROVEN")

    def test_parent_missing_mode_symlink_or_identity_drift(self):
        parent = self.fx.paths.private_root
        os.chmod(parent, 0o700)
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        os.chmod(parent, 0o750)
        parent.rmdir()
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        parent.symlink_to(self.fx.paths.etc_root, target_is_directory=True)
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        with mock.patch.object(v4, "_destination_reason", return_value=("gid changed", False)):
            self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)

    def test_permission_denial_is_not_absence(self):
        with mock.patch.object(v4.v2, "_probe", return_value="INACCESSIBLE"):
            self.assertEqual(self.fx.result().status, v4.STATUS_PRIVILEGED_METADATA_REQUIRED)
        with mock.patch.object(v4, "_destination_reason", return_value=(None, True)):
            self.assertEqual(self.fx.result().status, v4.STATUS_PRIVILEGED_METADATA_REQUIRED)

    def test_staging_partial_and_candidate_child_metadata(self):
        self.fx.paths.state_stage.mkdir()
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        self.fx.paths.state_stage.rmdir()
        self.fx.paths.target_env.write_text("SYNTHETIC=ONLY\n", encoding="utf-8")
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        self.fx.paths.target_env.unlink()
        self.fx.publish_synthetic_children()
        self.assertEqual(self.fx.result().status, v4.STATUS_EXACT_READY)
        os.chmod(self.fx.paths.target_env, 0o600)
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)
        os.chmod(self.fx.paths.target_env, 0o644)
        self.assertEqual(self.fx.result().status, v4.STATUS_PARTIAL_CONFLICT)

    def test_group_membership_privacy_boundaries(self):
        accounts = [SimpleNamespace(pw_name=v4.RUNTIME_NAME, pw_gid=45)]
        group = SimpleNamespace(gr_name=v4.RUNTIME_NAME, gr_mem=[], gr_gid=45)
        with mock.patch.object(v4.grp, "getgrgid", return_value=group), mock.patch.object(v4.pwd, "getpwall", return_value=accounts):
            self.assertTrue(v4._exclusive_runtime_group(v4.RUNTIME_NAME, 45))
            group.gr_mem.append("unrelated")
            self.assertFalse(v4._exclusive_runtime_group(v4.RUNTIME_NAME, 45))
            group.gr_mem.clear()
            accounts.append(SimpleNamespace(pw_name="other", pw_gid=45))
            self.assertFalse(v4._exclusive_runtime_group(v4.RUNTIME_NAME, 45))
        self.assertEqual(self.fx.result(exclusive=False).status, v4.STATUS_PARTIAL_CONFLICT)
        with mock.patch.object(v4.grp, "getgrgid", side_effect=KeyError):
            self.assertFalse(v4._exclusive_runtime_group(v4.RUNTIME_NAME, 45))

    def test_readiness_never_means_permission_to_apply(self):
        self.fx.publish_synthetic_children()
        data = v4._public_result(self.fx.result())
        self.assertEqual(data["status"], v4.STATUS_EXACT_READY)
        self.assertFalse(data["activation_eligible"])
        self.assertFalse(data["apply_available"])
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "SOURCE_ONLY_NO_APPLY_CONSUMER_ACCESS_UNPROVEN")
        self.assertTrue(all(value is False for value in contract["authority"].values()))
        self.assertEqual(contract["candidate_child"]["mode"], "0640")
        self.assertTrue(contract["candidate_child"]["candidate_not_authorized"])

    def test_no_apply_cli_or_protected_read_and_validate_contract(self):
        v4._validate_contract()
        parser = v4._build_parser()
        self.assertEqual(
            {option for action in parser._actions for option in action.option_strings},
            {"-h", "--help", "--expected-source-sha"},
        )
        with self.assertRaises(SystemExit):
            parser.parse_args(["--expected-source-sha", "f" * 40, "--apply"])
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("os.chmod(", "os.chown(", "v2._apply(", "legacy._prepare_protected(",
                          "shell=True", "os.remove(", "shutil.rmtree(", "docker compose"):
            self.assertNotIn(forbidden, source)
        self.assertIn("v3._require_source_checkout(expected_sha)", source)
        self.assertIn('v3._git_stdout_readonly("show",', source)
        self.assertIn('"GIT_OPTIONAL_LOCKS": "0"', (ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v3.py").read_text(encoding="utf-8"))
        self.assertIn("--no-optional-locks", (ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v3.py").read_text(encoding="utf-8"))

    def test_legacy_regressions_and_ci_are_integrated(self):
        make = MAKEFILE.read_text(encoding="utf-8")
        for filename in (
            "test-simple-deploy-hermes-prerequisite-materialization-v1.py",
            "test-simple-deploy-hermes-prerequisite-phase-b-parent-v2.py",
            "test-simple-deploy-hermes-prerequisite-recovery-v3.py",
            "test-simple-deploy-hermes-prerequisite-v4.py",
        ):
            self.assertEqual(make.count("python3 ./tests/" + filename), 1)
        self.assertIn("validate: test secret-scan public-safety", make)
        docs = DOC.read_text(encoding="utf-8")
        self.assertIn("BLOCKED_NO_START", docs)
        self.assertIn("Production deploy/change REQUIRED: NO", docs)


if __name__ == "__main__":
    unittest.main()
