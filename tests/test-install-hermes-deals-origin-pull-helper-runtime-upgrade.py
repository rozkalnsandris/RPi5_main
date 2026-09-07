from __future__ import annotations

import importlib.util
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
SCRIPT = ROOT / 'scripts/install-hermes-deals-origin-pull-helper-runtime-upgrade.py'
MANIFEST = ROOT / 'ops/deploy/hermes-deals-origin-loopback-provenance-runtime-upgrade.json'
spec = importlib.util.spec_from_file_location('hermes_loopback_upgrade', SCRIPT)
assert spec is not None and spec.loader is not None
upgrade = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = upgrade
spec.loader.exec_module(upgrade)


def git_blob(path: Path) -> str:
    return subprocess.check_output(('git', 'hash-object', str(path)), cwd=ROOT, text=True).strip()


class HermesLoopbackProvenanceRuntimeUpgradeTests(unittest.TestCase):
    def test_exact_corrected_source_and_registration_identity(self) -> None:
        self.assertEqual(upgrade.HERMES_SOURCE_SHA, 'f6c48cc85c187d927575da6efef4b05b4d4c0e40')
        self.assertEqual(upgrade.HELPER_NEW_BLOB, '4ef95c3f02b810b6b25721aa1b1b53d43b8ca572')
        self.assertEqual(upgrade.HELPER_NEW_SHA256, '23b29ff5f800cc5ade9cc8e38607a4e37beae9f45c6c82111ea4b49f063e06cf')
        registration = upgrade._registration_bytes()
        self.assertEqual(len(registration), 338)
        self.assertEqual(upgrade._git_blob(registration), upgrade.REGISTRATION_NEW_BLOB)
        self.assertEqual(upgrade._sha256(registration), upgrade.REGISTRATION_NEW_SHA256)
        value = json.loads(registration)
        self.assertEqual(value['registered_source_sha'], upgrade.HERMES_SOURCE_SHA)
        self.assertEqual(value['helper_sha256'], upgrade.HELPER_NEW_SHA256)
        self.assertEqual(value['probe_sha256'], upgrade.PROBE_SHA256)

    def test_target_surface_is_exact_five_fixed_replacements(self) -> None:
        self.assertEqual(
            [item.name for item in upgrade.TARGETS],
            ['consumer_adapter', 'runtime_adapters', 'broker_runtime', 'helper', 'registration'],
        )
        self.assertEqual(len(upgrade.CONSUMER_TARGETS), 3)
        for item in upgrade.CONSUMER_TARGETS:
            assert item.source_path is not None
            self.assertEqual(git_blob(ROOT / item.source_path), item.new_blob)
        self.assertEqual(upgrade.HELPER_TARGET.old_blob, upgrade.HELPER_OLD_BLOB)
        self.assertEqual(upgrade.HELPER_TARGET.new_blob, upgrade.HELPER_NEW_BLOB)
        self.assertEqual(upgrade.REGISTRATION_TARGET.old_blob, upgrade.REGISTRATION_OLD_BLOB)
        self.assertEqual(upgrade.REGISTRATION_TARGET.new_blob, upgrade.REGISTRATION_NEW_BLOB)

    def test_manifest_binds_operator_targets_and_nonlive_policy(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest['operator']['source_blob'], git_blob(SCRIPT))
        self.assertEqual(manifest['hermes_source']['sha'], upgrade.HERMES_SOURCE_SHA)
        self.assertEqual(manifest['registration']['new_blob'], upgrade.REGISTRATION_NEW_BLOB)
        self.assertEqual(
            [(row['name'], row['target'], row['old_blob'], row['new_blob']) for row in manifest['runtime_targets']],
            [(t.name, str(t.path), t.old_blob, t.new_blob) for t in upgrade.TARGETS],
        )
        self.assertEqual(manifest['runtime_target_order'], [t.name for t in upgrade.TARGETS])
        self.assertFalse(manifest['immutable_prerequisite']['mutation_authorized'])
        for key in (
            'runtime_upgrade_preflight_proven', 'runtime_upgrade_applied',
            'new_ready_queue_prepared', 'new_live_authorization_present',
            'genuine_replacement_canary_authorized', 'runner_retirement_eligible',
            'production_mutation_started',
        ):
            self.assertFalse(manifest['source_gate_state'][key], key)

    def test_source_is_capability_specific_and_fail_closed(self) -> None:
        source = SCRIPT.read_text()
        self.assertEqual(source.count("reviewed = _preflight(args.expected_sha)"), 2)
        self.assertIn("f'safe.directory={repo}'", source)
        self.assertNotIn('safe.directory=*', source)
        self.assertNotIn('--global', source)
        self.assertNotIn('--system', source)
        self.assertNotIn('systemctl', source)
        self.assertNotIn('docker ', source.lower())
        self.assertNotIn('os.ftruncate', source)
        self.assertNotIn('os.unlink', source)
        self.assertNotIn('os.remove', source)
        self.assertIn("state['mutation_started'] = True", source)
        self.assertIn('os.O_EXCL', source)
        self.assertIn('os.fsync(temp_fd)', source)
        self.assertIn('os.replace(', source)
        self.assertIn('os.fsync(parent_fd)', source)
        self.assertIn("'automatic_retry': False", source)
        self.assertIn("'automatic_rollback': False", source)
        self.assertIn("'automatic_cleanup': False", source)

    def _temp_spec(self, parent: Path, old: bytes, new: bytes) -> object:
        return upgrade.TargetSpec(
            'helper', parent / 'helper', 0o755,
            upgrade._git_blob(old), upgrade._git_blob(new), '.helper.tmp',
            old_sha256=upgrade._sha256(old), new_sha256=upgrade._sha256(new),
        )

    def _patched_runtime(self, parent: Path):
        flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        return mock.patch.multiple(
            upgrade,
            ROOT_UID=os.getuid(), ROOT_GID=os.getgid(),
            _open_parent=mock.DEFAULT,
        ), flags

    def test_atomic_replace_accepts_only_exact_old_identity(self) -> None:
        old = b'reviewed-old-helper\n'
        new = b'corrected-loopback-helper\n'
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target = parent / 'helper'
            target.write_bytes(old)
            target.chmod(0o755)
            spec = self._temp_spec(parent, old, new)
            flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            state = {'mutation_started': False, 'helper_replaced': False}
            with mock.patch.object(upgrade, 'ROOT_UID', os.getuid()), \
                 mock.patch.object(upgrade, 'ROOT_GID', os.getgid()), \
                 mock.patch.object(upgrade, '_open_parent', side_effect=lambda _spec: os.open(parent, flags)):
                upgrade._replace_target(spec, new, state)
            self.assertEqual(target.read_bytes(), new)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)
            self.assertEqual(state, {'mutation_started': True, 'helper_replaced': True})
            self.assertFalse((parent / spec.temp_name).exists())

    def test_wrong_old_blob_fails_before_mutation(self) -> None:
        old = b'expected-old\n'
        wrong = b'wrong-old\n'
        new = b'new-reviewed\n'
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target = parent / 'helper'
            target.write_bytes(wrong)
            target.chmod(0o755)
            spec = self._temp_spec(parent, old, new)
            flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            state = {'mutation_started': False, 'helper_replaced': False}
            with mock.patch.object(upgrade, 'ROOT_UID', os.getuid()), \
                 mock.patch.object(upgrade, 'ROOT_GID', os.getgid()), \
                 mock.patch.object(upgrade, '_open_parent', side_effect=lambda _spec: os.open(parent, flags)):
                with self.assertRaises(upgrade.UpgradeError):
                    upgrade._replace_target(spec, new, state)
            self.assertEqual(state, {'mutation_started': False, 'helper_replaced': False})
            self.assertEqual(target.read_bytes(), wrong)
            self.assertFalse((parent / spec.temp_name).exists())

    def test_post_mutation_replace_failure_preserves_temp_and_old_target(self) -> None:
        old = b'reviewed-old\n'
        new = b'reviewed-new\n'
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target = parent / 'helper'
            target.write_bytes(old)
            target.chmod(0o755)
            spec = self._temp_spec(parent, old, new)
            flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            state = {'mutation_started': False, 'helper_replaced': False}
            with mock.patch.object(upgrade, 'ROOT_UID', os.getuid()), \
                 mock.patch.object(upgrade, 'ROOT_GID', os.getgid()), \
                 mock.patch.object(upgrade, '_open_parent', side_effect=lambda _spec: os.open(parent, flags)), \
                 mock.patch.object(os, 'replace', side_effect=OSError('synthetic replace failure')):
                with self.assertRaises(OSError):
                    upgrade._replace_target(spec, new, state)
            self.assertEqual(state, {'mutation_started': True, 'helper_replaced': False})
            self.assertEqual(target.read_bytes(), old)
            self.assertEqual((parent / spec.temp_name).read_bytes(), new)

    def test_apply_path_repeats_preflight_then_uses_fixed_order(self) -> None:
        reviewed = {spec.name: spec.name.encode() for spec in upgrade.TARGETS}
        events: list[str] = []
        with mock.patch.object(upgrade, '_preflight', side_effect=lambda _sha: events.append('preflight') or reviewed), \
             mock.patch.object(upgrade, '_replace_target', side_effect=lambda spec, _data, _state: events.append(spec.name)):
            rc = upgrade.main(['a' * 40, '--apply'])
        self.assertEqual(rc, 0)
        self.assertEqual(events, ['preflight', 'preflight', *[spec.name for spec in upgrade.TARGETS]])

    def test_default_cli_is_preflight_only(self) -> None:
        args = upgrade._parse_args(['a' * 40])
        self.assertEqual(args.expected_sha, 'a' * 40)
        self.assertFalse(args.apply)


if __name__ == '__main__':
    unittest.main()
