#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v2.py"
CONTRACT = ROOT / "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v2.json"
WORKFLOW = ROOT / ".github/workflows/simple-deploy-hermes-prerequisite-phase-b-parent-source.yml"
GENERIC_INSTALLER = ROOT / "scripts/install-simple-deploy-v1.py"

spec = importlib.util.spec_from_file_location("simple_deploy_hermes_prerequisites_v2", MODULE_PATH)
assert spec and spec.loader
materialize = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = materialize
spec.loader.exec_module(materialize)


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.uid = os.getuid()
        self.gid = os.getgid()
        checkout = self.base / "home/andris/hermes-deals"
        source_data = checkout / "data/raw"
        source_config = checkout / "config"
        source_env = checkout / ".env"
        etc_root = self.base / "etc/rozkalns-simple-deployer"
        state_parent = self.base / "var/lib/rozkalns-simple-deployer"
        target_root = state_parent / "hermes-deals"
        private_root = etc_root / "private"

        source_data.mkdir(parents=True, mode=0o755)
        source_config.mkdir(parents=True, mode=0o755)
        etc_root.mkdir(parents=True, mode=0o755)
        state_parent.mkdir(parents=True, mode=0o700)
        for path in (checkout, checkout / "data", source_data, source_config, etc_root):
            os.chmod(path, 0o755)
        os.chmod(state_parent, 0o700)

        (source_data / "snapshot.json").write_text('{"ok":true}\n', encoding="utf-8")
        (source_config / "sources.json").write_text('{"sources":[]}\n', encoding="utf-8")
        os.chmod(source_data / "snapshot.json", 0o644)
        os.chmod(source_config / "sources.json", 0o644)
        source_env.write_text(
            "OTHER=ignored\nDATABASE_URL=postgresql://secret-value\nHTTP_USER_AGENT=Hermes Secret Agent\n",
            encoding="utf-8",
        )
        os.chmod(source_env, 0o600)

        self.paths = materialize.MaterializationPaths(
            checkout=checkout,
            source_data=source_data,
            source_config=source_config,
            source_env=source_env,
            etc_root=etc_root,
            state_parent=state_parent,
            target_root=target_root,
            target_data_parent=target_root / "data",
            target_data=target_root / "data/raw",
            target_config=target_root / "config",
            private_root=private_root,
            target_env=private_root / "hermes-deals-api.env",
            state_stage=state_parent / ".hermes-deals-prerequisites-v1.staged",
            env_stage=private_root / ".hermes-deals-api.env.prerequisites-v1.staged",
        )

    def classify(self) -> materialize.Classification:
        return materialize._public_preflight(
            self.paths,
            source_uid=self.uid,
            source_gid=self.gid,
            runtime_uid=self.uid,
            runtime_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def plan(self) -> materialize.ProtectedPlan:
        return materialize.legacy._prepare_protected(
            self.paths, source_uid=self.uid, source_gid=self.gid
        )

    def apply(self) -> materialize.Progress:
        return materialize._apply(
            self.paths,
            self.plan(),
            source_uid=self.uid,
            source_gid=self.gid,
            runtime_uid=self.uid,
            runtime_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def close(self) -> None:
        self.temp.cleanup()


class HermesPhaseBParentCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()

    def tearDown(self) -> None:
        self.fx.close()

    def test_phase_b_parent_is_required_as_runtime_owned_0700(self) -> None:
        self.assertEqual(self.fx.classify().status, materialize.STATUS_ABSENT)
        os.chmod(self.fx.paths.state_parent, 0o755)
        result = self.fx.classify()
        self.assertEqual(result.status, materialize.STATUS_PARTIAL_CONFLICT)
        self.assertIn("Phase-B state root", " ".join(result.reasons))

    def test_runtime_ids_are_used_symbolically_not_root_ids(self) -> None:
        original = materialize.legacy._destination_reason
        seen: dict[str, int] = {}

        def fake(path, *, kind, mode, uid, gid):
            if path == self.fx.paths.state_parent:
                seen.update(uid=uid, gid=gid, mode=mode)
                return None
            return original(path, kind=kind, mode=mode, uid=uid, gid=gid)

        with mock.patch.object(materialize.legacy, "_destination_reason", side_effect=fake):
            result = materialize._public_preflight(
                self.fx.paths,
                source_uid=self.fx.uid,
                source_gid=self.fx.gid,
                runtime_uid=4242,
                runtime_gid=4343,
                root_uid=self.fx.uid,
                root_gid=self.fx.gid,
            )
        self.assertEqual(result.status, materialize.STATUS_ABSENT)
        self.assertEqual(seen, {"uid": 4242, "gid": 4343, "mode": 0o700})

    def test_permission_denied_is_not_treated_as_absence(self) -> None:
        with mock.patch.object(materialize.os, "lstat", side_effect=PermissionError):
            self.assertEqual(materialize._probe(self.fx.paths.target_root), "INACCESSIBLE")

    def test_hidden_state_children_require_privileged_metadata_preflight(self) -> None:
        original_probe = materialize._probe

        def fake_probe(path):
            if path in (self.fx.paths.state_stage, self.fx.paths.target_root):
                return "INACCESSIBLE"
            return original_probe(path)

        with mock.patch.object(materialize, "_probe", side_effect=fake_probe):
            result = self.fx.classify()
        self.assertEqual(result.status, materialize.STATUS_PRIVILEGED_METADATA_REQUIRED)
        public = materialize._public_result(result)
        self.assertTrue(public["privileged_metadata_required"])
        self.assertFalse(public["protected_data_read"])
        self.assertFalse(public["protected_values_emitted"])

    def test_apply_preserves_existing_phase_b_parent_metadata(self) -> None:
        before = os.lstat(self.fx.paths.state_parent)
        progress = self.fx.apply()
        after = os.lstat(self.fx.paths.state_parent)
        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.published_targets, 2)
        self.assertEqual(progress.parent_directories_created, 1)
        self.assertEqual(before.st_uid, after.st_uid)
        self.assertEqual(before.st_gid, after.st_gid)
        self.assertEqual(after.st_mode & 0o777, 0o700)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_EXACT_READY)

    def test_apply_refuses_missing_phase_b_parent_before_mutation(self) -> None:
        self.fx.paths.state_parent.rmdir()
        plan = self.fx.plan()
        with self.assertRaisesRegex(materialize.MaterializationError, "ABSENT"):
            materialize._apply(
                self.fx.paths,
                plan,
                source_uid=self.fx.uid,
                source_gid=self.fx.gid,
                runtime_uid=self.fx.uid,
                runtime_gid=self.fx.gid,
                root_uid=self.fx.uid,
                root_gid=self.fx.gid,
            )
        self.assertFalse(self.fx.paths.private_root.exists())

    def test_post_mutation_failure_keeps_evidence(self) -> None:
        plan = self.fx.plan()
        with mock.patch.object(materialize.os, "link", side_effect=OSError("synthetic publish failure")):
            with self.assertRaises(materialize.ApplyFailure) as ctx:
                materialize._apply(
                    self.fx.paths,
                    plan,
                    source_uid=self.fx.uid,
                    source_gid=self.fx.gid,
                    runtime_uid=self.fx.uid,
                    runtime_gid=self.fx.gid,
                    root_uid=self.fx.uid,
                    root_gid=self.fx.gid,
                )
        self.assertTrue(ctx.exception.progress.mutation_started)
        self.assertEqual(ctx.exception.progress.published_targets, 1)
        self.assertTrue(self.fx.paths.target_root.exists())
        self.assertTrue(self.fx.paths.env_stage.exists())
        self.assertFalse(self.fx.paths.target_env.exists())

    def test_machine_contract_locks_phase_b_parent_and_non_success_status(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 713)
        self.assertEqual(contract["phase_b_state_parent"]["owner_user"], "rozkalns-simple-deployer")
        self.assertEqual(contract["phase_b_state_parent"]["owner_group"], "rozkalns-simple-deployer")
        self.assertEqual(contract["phase_b_state_parent"]["mode"], "0700")
        self.assertTrue(contract["phase_b_state_parent"]["must_preexist"])
        self.assertFalse(contract["phase_b_state_parent"]["materializer_may_create_or_reown"])
        self.assertIn(
            materialize.STATUS_PRIVILEGED_METADATA_REQUIRED,
            contract["classifier"]["statuses"],
        )
        self.assertTrue(contract["classifier"]["permission_denied_is_not_absence"])
        self.assertFalse(contract["authority"]["privileged_host_metadata_access"])

    def test_generic_phase_b_installer_boundary_is_unchanged_and_explicit(self) -> None:
        source = GENERIC_INSTALLER.read_text(encoding="utf-8")
        self.assertIn('RUNTIME_USER = "rozkalns-simple-deployer"', source)
        self.assertIn('PHASE_B_STATE_ROOT = Path("/var/lib/rozkalns-simple-deployer")', source)
        self.assertIn("os.mkdir(path, 0o700)", source)
        self.assertIn("os.chown(path, uid, gid)", source)
        self.assertIn("stat.S_IMODE(info.st_mode) != 0o700", source)

    def test_cli_and_ci_do_not_expand_live_authority(self) -> None:
        parser = materialize._build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(options, {"-h", "--help", "--expected-source-sha", "--apply"})
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("--apply", workflow)
        self.assertIn("test-simple-deploy-hermes-prerequisite-materialization-v1.py", workflow)
        self.assertIn("test-simple-deploy-hermes-prerequisite-phase-b-parent-v2.py", workflow)

    def test_public_source_has_no_numeric_runtime_identity_or_home_literal(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("983", source)
        self.assertNotIn("/home/andris", source)
        self.assertIn('RUNTIME_USER = "rozkalns-simple-deployer"', source)


if __name__ == "__main__":
    unittest.main()
