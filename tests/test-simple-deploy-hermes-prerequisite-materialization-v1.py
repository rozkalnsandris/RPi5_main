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
MODULE_PATH = ROOT / 'scripts/materialize-simple-deploy-hermes-prerequisites-v1.py'
CONTRACT = ROOT / 'ops/contracts/simple-deploy-hermes-prerequisite-materialization-v1.json'
WORKFLOW = ROOT / '.github/workflows/simple-deploy-hermes-prerequisite-materialization-source.yml'
ADOPTION = ROOT / 'scripts/adopt-simple-deploy-hermes-v1.py'

spec = importlib.util.spec_from_file_location('simple_deploy_hermes_prerequisites_v1', MODULE_PATH)
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
        checkout = self.base / 'home/andris/hermes-deals'
        source_data = checkout / 'data/raw'
        source_config = checkout / 'config'
        source_env = checkout / '.env'
        etc_root = self.base / 'etc/rozkalns-simple-deployer'
        state_parent = self.base / 'var/lib/rozkalns-simple-deployer'
        target_root = state_parent / 'hermes-deals'
        private_root = etc_root / 'private'
        source_data.mkdir(parents=True, mode=0o755)
        source_config.mkdir(parents=True, mode=0o755)
        etc_root.mkdir(parents=True, mode=0o755)
        (self.base / 'var/lib').mkdir(parents=True, mode=0o755)
        for path in (checkout, checkout / 'data', source_data, source_config, etc_root):
            os.chmod(path, 0o755)
        (source_data / 'snapshot.json').write_text('{"ok":true}\n', encoding='utf-8')
        (source_config / 'sources.json').write_text('{"sources":[]}\n', encoding='utf-8')
        os.chmod(source_data / 'snapshot.json', 0o644)
        os.chmod(source_config / 'sources.json', 0o644)
        source_env.write_text(
            'OTHER=ignored\nDATABASE_URL=postgresql://secret-value\nHTTP_USER_AGENT=Hermes Secret Agent\n',
            encoding='utf-8',
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
            target_data_parent=target_root / 'data',
            target_data=target_root / 'data/raw',
            target_config=target_root / 'config',
            private_root=private_root,
            target_env=private_root / 'hermes-deals-api.env',
            state_stage=state_parent / '.hermes-deals-prerequisites-v1.staged',
            env_stage=private_root / '.hermes-deals-api.env.prerequisites-v1.staged',
        )

    def classify(self) -> materialize.Classification:
        return materialize._public_preflight(
            self.paths,
            source_uid=self.uid,
            source_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def plan(self) -> materialize.ProtectedPlan:
        return materialize._prepare_protected(self.paths, source_uid=self.uid, source_gid=self.gid)

    def apply(self) -> materialize.Progress:
        return materialize._apply(
            self.paths,
            self.plan(),
            source_uid=self.uid,
            source_gid=self.gid,
            root_uid=self.uid,
            root_gid=self.gid,
        )

    def close(self) -> None:
        self.temp.cleanup()


class HermesPrerequisiteMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()

    def tearDown(self) -> None:
        self.fx.close()

    def test_absent_public_preflight_reads_no_protected_values(self) -> None:
        classification = self.fx.classify()
        self.assertEqual(classification.status, materialize.STATUS_ABSENT)
        result = json.dumps(materialize._public_result(classification), sort_keys=True)
        self.assertNotIn('secret-value', result)
        self.assertNotIn('Hermes Secret Agent', result)
        self.assertFalse(materialize._public_result(classification)['protected_data_read'])

    def test_apply_materializes_exact_normalized_projection(self) -> None:
        progress = self.fx.apply()
        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.published_targets, 2)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_EXACT_READY)
        self.assertEqual(
            self.fx.paths.target_env.read_text(encoding='utf-8'),
            'DATABASE_URL=postgresql://secret-value\nHTTP_USER_AGENT=Hermes Secret Agent\n',
        )
        self.assertEqual(self.fx.paths.target_data.joinpath('snapshot.json').read_text(), '{"ok":true}\n')
        self.assertEqual(self.fx.paths.target_config.joinpath('sources.json').read_text(), '{"sources":[]}\n')
        self.assertEqual(self.fx.paths.target_env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.fx.paths.target_data.joinpath('snapshot.json').stat().st_mode & 0o777, 0o644)
        self.assertFalse(self.fx.paths.state_stage.exists())
        self.assertFalse(self.fx.paths.env_stage.exists())

    def test_partial_destination_fails_closed(self) -> None:
        self.fx.paths.state_parent.mkdir(parents=True, mode=0o755)
        self.fx.paths.target_root.mkdir(mode=0o755)
        os.chmod(self.fx.paths.state_parent, 0o755)
        os.chmod(self.fx.paths.target_root, 0o755)
        result = self.fx.classify()
        self.assertEqual(result.status, materialize.STATUS_PARTIAL_CONFLICT)
        self.assertIn('only part', ' '.join(result.reasons))

    def test_wrong_destination_mode_and_unexpected_entry_fail_closed(self) -> None:
        self.fx.apply()
        os.chmod(self.fx.paths.target_env, 0o644)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_PARTIAL_CONFLICT)
        os.chmod(self.fx.paths.target_env, 0o600)
        (self.fx.paths.target_root / 'unexpected').mkdir(mode=0o755)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_PARTIAL_CONFLICT)

    def test_source_and_protected_tree_symlinks_fail_closed(self) -> None:
        (self.fx.paths.source_config / 'sources.json').unlink()
        self.fx.paths.source_config.rmdir()
        self.fx.paths.source_config.symlink_to(self.fx.paths.source_data, target_is_directory=True)
        self.assertEqual(self.fx.classify().status, materialize.STATUS_PARTIAL_CONFLICT)
        self.fx.paths.source_config.unlink()
        self.fx.paths.source_config.mkdir(mode=0o755)
        os.chmod(self.fx.paths.source_config, 0o755)
        (self.fx.paths.source_config / 'sources.json').write_text('{}\n', encoding='utf-8')
        os.chmod(self.fx.paths.source_config / 'sources.json', 0o644)
        (self.fx.paths.source_config / 'link').symlink_to(self.fx.paths.source_data / 'snapshot.json')
        with self.assertRaisesRegex(materialize.MaterializationError, 'symlink'):
            self.fx.plan()

    def test_env_projection_is_exact_and_diagnostics_redact_values(self) -> None:
        projected = materialize._extract_required_env(
            b'IGNORED=x\nHTTP_USER_AGENT=ua-secret\nDATABASE_URL=db-secret\n'
        )
        self.assertEqual(projected, b'DATABASE_URL=db-secret\nHTTP_USER_AGENT=ua-secret\n')
        for bad in (
            b'DATABASE_URL=db-secret\n',
            b'DATABASE_URL=db-secret\nDATABASE_URL=other-secret\nHTTP_USER_AGENT=ua-secret\n',
            b'not-an-assignment\nDATABASE_URL=db-secret\nHTTP_USER_AGENT=ua-secret\n',
        ):
            with self.assertRaises(materialize.MaterializationError) as ctx:
                materialize._extract_required_env(bad)
            message = str(ctx.exception)
            for secret in ('db-secret', 'other-secret', 'ua-secret'):
                self.assertNotIn(secret, message)

    def test_protected_tree_rejects_unsafe_mode(self) -> None:
        os.chmod(self.fx.paths.source_data / 'snapshot.json', 0o666)
        with self.assertRaisesRegex(materialize.MaterializationError, 'mode is unsafe'):
            self.fx.plan()

    def test_apply_refuses_existing_destination_without_mutation(self) -> None:
        self.fx.paths.state_parent.mkdir(parents=True, mode=0o755)
        os.chmod(self.fx.paths.state_parent, 0o755)
        self.fx.paths.target_root.mkdir(mode=0o755)
        os.chmod(self.fx.paths.target_root, 0o755)
        with self.assertRaisesRegex(materialize.MaterializationError, 'ABSENT'):
            materialize._apply(
                self.fx.paths,
                self.fx.plan(),
                source_uid=self.fx.uid,
                source_gid=self.fx.gid,
                root_uid=self.fx.uid,
                root_gid=self.fx.gid,
            )
        self.assertFalse(self.fx.paths.private_root.exists())

    def test_post_mutation_publish_failure_keeps_evidence_and_does_not_cleanup(self) -> None:
        plan = self.fx.plan()
        with mock.patch.object(materialize.os, 'link', side_effect=OSError('synthetic publish failure')):
            with self.assertRaises(materialize.ApplyFailure) as ctx:
                materialize._apply(
                    self.fx.paths,
                    plan,
                    source_uid=self.fx.uid,
                    source_gid=self.fx.gid,
                    root_uid=self.fx.uid,
                    root_gid=self.fx.gid,
                )
        self.assertTrue(ctx.exception.progress.mutation_started)
        self.assertEqual(ctx.exception.progress.published_targets, 1)
        self.assertTrue(self.fx.paths.target_root.exists())
        self.assertTrue(self.fx.paths.env_stage.exists())
        self.assertFalse(self.fx.paths.target_env.exists())
        self.assertEqual(self.fx.classify().status, materialize.STATUS_PARTIAL_CONFLICT)

    def test_cli_exposes_no_dynamic_runtime_authority(self) -> None:
        parser = materialize._build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(options, {'-h', '--help', '--expected-source-sha', '--apply'})
        source = MODULE_PATH.read_text(encoding='utf-8')
        for forbidden in (
            '--path', '--env-file', '--key', '--command', '--target', '--repository',
            'shell=True', 'docker ', 'systemctl',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_machine_contract_freezes_paths_authority_and_operation_separation(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
        self.assertEqual(contract['issue'], 711)
        self.assertEqual(contract['classifier']['statuses'], ['ABSENT', 'EXACT_READY', 'PARTIAL_CONFLICT'])
        self.assertEqual(contract['private_env']['required_keys'], ['DATABASE_URL', 'HTTP_USER_AGENT'])
        self.assertEqual(contract['cli']['options'], ['--expected-source-sha', '--apply'])
        self.assertTrue(contract['separation']['prerequisites_and_target_adoption_are_distinct_operations'])
        self.assertEqual(contract['separation']['hermes_adoption_entrypoint'], 'scripts/adopt-simple-deploy-hermes-v1.py')
        self.assertFalse(contract['authority']['host_filesystem_or_application_data'])
        self.assertFalse(contract['authority']['protected_config_or_secret_access'])
        self.assertFalse(contract['authority']['target_adoption'])
        self.assertFalse(contract['authority']['docker'])
        self.assertFalse(contract['authority']['systemd'])

    def test_ci_never_invokes_apply_and_existing_adoption_stays_separate(self) -> None:
        workflow = WORKFLOW.read_text(encoding='utf-8')
        self.assertNotIn('--apply', workflow)
        self.assertIn('test-simple-deploy-hermes-adoption-v1.py', workflow)
        self.assertIn('test-simple-deploy-hermes-adoption-phase-b-identity.py', workflow)
        adoption = ADOPTION.read_text(encoding='utf-8')
        self.assertNotIn('materialize-simple-deploy-hermes-prerequisites-v1', adoption)


if __name__ == '__main__':
    unittest.main()
