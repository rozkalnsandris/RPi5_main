#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v3.py"
CONTRACT = ROOT / "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v3.json"
WORKFLOW = ROOT / ".github/workflows/simple-deploy-hermes-prerequisite-recovery-v3-source.yml"

spec = importlib.util.spec_from_file_location("simple_deploy_hermes_prerequisites_v3", MODULE_PATH)
assert spec and spec.loader
materialize = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = materialize
spec.loader.exec_module(materialize)


def _env_text(assignments: tuple[tuple[str, str], ...]) -> str:
    return "".join(f"{key}={value}\n" for key, value in assignments)


def _env_bytes(assignments: tuple[tuple[str, str], ...]) -> bytes:
    return _env_text(assignments).encode("utf-8")


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.credential_value = "SyntheticCredential42"
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
            _env_text(
                (
                    ("OTHER", "ignored"),
                    ("POSTGRES_DB", "hermes_db"),
                    ("POSTGRES_USER", "hermes_user"),
                    ("POSTGRES_PASSWORD", self.credential_value),
                    ("HTTP_USER_AGENT", '"Mozilla/5.0 Synthetic Hermes Agent"'),
                )
            ),
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

    def plan(self) -> materialize.ProtectedPlan:
        return materialize._prepare_protected_v3(
            self.paths, source_uid=self.uid, source_gid=self.gid
        )

    def apply(self) -> materialize.Progress:
        return materialize.v2._apply(
            self.paths,
            self.plan(),
            source_uid=self.uid,
            source_gid=self.gid,
            runtime_uid=self.uid,
            runtime_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def classify(self) -> materialize.Classification:
        return materialize.v2._public_preflight(
            self.paths,
            source_uid=self.uid,
            source_gid=self.gid,
            runtime_uid=self.uid,
            runtime_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def close(self) -> None:
        self.temp.cleanup()


class HermesPrerequisiteRecoveryV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()

    def tearDown(self) -> None:
        self.fx.close()

    def test_legacy_four_key_source_projects_exact_two_key_destination(self) -> None:
        plan = self.fx.plan()
        expected = (
            "DATABASE_URL='postgresql+psycopg://"
            f"hermes_user:{self.fx.credential_value}@db:5432/hermes_db'\n"
            "HTTP_USER_AGENT='Mozilla/5.0 Synthetic Hermes Agent'\n"
        ).encode("utf-8")
        self.assertEqual(plan.env_bytes, expected)
        self.assertEqual(
            tuple(line.split(b"=", 1)[0].decode("ascii") for line in plan.env_bytes.splitlines()),
            materialize.DESTINATION_ENV_KEYS,
        )

    def test_missing_source_key_fails_without_value_disclosure(self) -> None:
        protected_fixture = "DoNotLeakSyntheticValue"
        raw = _env_bytes(
            (
                ("POSTGRES_USER", "synthetic-user"),
                ("POSTGRES_PASSWORD", protected_fixture),
                ("POSTGRES_DB", "synthetic-db"),
            )
        )
        with self.assertRaises(materialize.MaterializationError) as ctx:
            materialize._extract_source_env(raw)
        message = str(ctx.exception)
        self.assertIn("HTTP_USER_AGENT", message)
        self.assertNotIn(protected_fixture, message)

    def test_duplicate_required_source_key_fails_closed(self) -> None:
        raw = _env_bytes(
            (
                ("POSTGRES_USER", "one"),
                ("POSTGRES_USER", "two"),
                ("POSTGRES_PASSWORD", "fixture-value"),
                ("POSTGRES_DB", "db"),
                ("HTTP_USER_AGENT", "agent"),
            )
        )
        with self.assertRaisesRegex(materialize.MaterializationError, "duplicates required key POSTGRES_USER"):
            materialize._extract_source_env(raw)

    def test_unsupported_quote_fails_closed_without_echoing_value(self) -> None:
        protected_fixture = "synthetic'quote"
        raw = _env_bytes(
            (
                ("POSTGRES_USER", "user"),
                ("POSTGRES_PASSWORD", protected_fixture),
                ("POSTGRES_DB", "db"),
                ("HTTP_USER_AGENT", "agent"),
            )
        )
        with self.assertRaises(materialize.MaterializationError) as ctx:
            materialize._extract_source_env(raw)
        self.assertIn("POSTGRES_PASSWORD", str(ctx.exception))
        self.assertNotIn(protected_fixture, str(ctx.exception))

    def test_root_safe_git_invocation_disables_optional_locks(self) -> None:
        completed = subprocess.CompletedProcess(args=(), returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(materialize.subprocess, "run", return_value=completed) as run:
            materialize._git_readonly("rev-parse", "--verify", "HEAD")
        argv = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIn("--no-optional-locks", argv)
        self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
        self.assertFalse(kwargs["shell"])

    def test_source_cleanliness_does_not_use_git_status(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('("diff-files", "--quiet", "--")', source)
        self.assertIn('("diff-index", "--cached", "--quiet", "HEAD", "--")', source)
        self.assertIn('"ls-files", "--others", "--exclude-standard"', source)
        self.assertNotIn('_git_readonly("status"', source)
        self.assertNotIn('_git_stdout_readonly("status"', source)
        self.assertIn('"GIT_OPTIONAL_LOCKS": "0"', source)

    def test_apply_reuses_v2_phase_b_boundary_with_v3_plan(self) -> None:
        before = os.lstat(self.fx.paths.state_parent)
        plan = self.fx.plan()
        progress = materialize.v2._apply(
            self.fx.paths,
            plan,
            source_uid=self.fx.uid,
            source_gid=self.fx.gid,
            runtime_uid=self.fx.uid,
            runtime_gid=self.fx.gid,
            root_uid=self.fx.uid,
            root_gid=self.fx.gid,
        )
        after = os.lstat(self.fx.paths.state_parent)
        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.published_targets, 2)
        self.assertEqual((before.st_uid, before.st_gid), (after.st_uid, after.st_gid))
        self.assertEqual(after.st_mode & 0o777, 0o700)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_EXACT_READY)
        self.assertEqual(self.fx.paths.target_env.read_bytes(), plan.env_bytes)

    def test_machine_contract_locks_recovery_semantics(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 719)
        self.assertEqual(contract["supersedes"]["materialization_v2_issue"], 713)
        self.assertEqual(contract["supersedes"]["materialization_v2_pr"], 714)
        self.assertEqual(tuple(contract["private_env"]["source_required_keys"]), materialize.SOURCE_ENV_KEYS)
        self.assertEqual(tuple(contract["private_env"]["destination_keys"]), materialize.DESTINATION_ENV_KEYS)
        self.assertFalse(contract["source_verification"]["git_optional_locks"])
        self.assertFalse(contract["source_verification"]["git_status_allowed"])
        self.assertFalse(contract["preserved_failure_evidence"]["repair_or_cleanup_authorized"])
        self.assertFalse(contract["authority"]["merge_authorizes_recovery"])
        self.assertFalse(contract["authority"]["merge_authorizes_live"])

    def test_contract_validator_and_cli_remain_fixed(self) -> None:
        materialize._validate_machine_contract()
        parser = materialize._build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(options, {"-h", "--help", "--expected-source-sha", "--apply"})

    def test_ci_is_source_only_and_runs_v1_v2_v3_regressions(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("--apply", workflow)
        self.assertIn("test-simple-deploy-hermes-prerequisite-materialization-v1.py", workflow)
        self.assertIn("test-simple-deploy-hermes-prerequisite-phase-b-parent-v2.py", workflow)
        self.assertIn("test-simple-deploy-hermes-prerequisite-recovery-v3.py", workflow)
        self.assertIn("materialize-simple-deploy-hermes-prerequisites-v3.py", workflow)


if __name__ == "__main__":
    unittest.main()
