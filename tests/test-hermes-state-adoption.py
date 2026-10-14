#!/usr/bin/env python3
"""Hermetic synthetic filesystem tests. No host, protected config or network access."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('state_adoption', ROOT / 'scripts/prepare-hermes-state-adoption.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)



class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.uid, self.gid = os.getuid(), os.getgid()
        self.fds = {}
        for name in ('state', 'compose', 'etc', 'source'):
            p = self.base / name
            p.mkdir(mode=0o755)
            fd = os.open(p, m.DIR_FLAGS)
            self.fds[name] = fd
            self.addCleanup(os.close, fd)
        self.candidate = {p: (ROOT / p).read_bytes() for p in m.HASHES}
        self.original = self.base / 'etc/targets.json'
        self.original.write_bytes(self.candidate[m.BASE_REGISTRY])
        self.original.chmod(0o444)
        self.data = {'data': {'raw': {'synthetic.json': b'[{"test":true}]'}},
                     'config': {'sources.json': b'{"synthetic":true}', 'empty': {}}}
        self.receipt = m.new_receipt()

    def publish(self, revalidate=lambda: None):
        m.publish(self.fds['state'], self.fds['compose'], self.fds['etc'], self.data,
                  self.candidate, revalidate, self.receipt, uid=self.uid, gid=self.gid)

    def source_file(self, name='snapshot.json', value=b'{"synthetic":true}'):
        p = self.base / 'source' / name
        p.write_bytes(value)
        p.chmod(0o644)
        return p

    def tree(self, **kwargs):
        return m.tree(self.fds['source'], self.uid, self.gid, [0, 0], **kwargs)

    def test_contract_hashes_and_exact_registry_delta(self):
        self.assertEqual(json.loads((ROOT / m.CONTRACT).read_bytes()), m.contract())
        for p, expected in m.HASHES.items():
            self.assertEqual(m.digest((ROOT / p).read_bytes()), expected)
        self.assertEqual(
            (ROOT / m.NEW_REGISTRY).read_bytes(), self.candidate[m.NEW_REGISTRY]
        )
        m.registry_delta(self.candidate[m.BASE_REGISTRY], self.candidate[m.NEW_REGISTRY])
        changed = json.loads(self.candidate[m.NEW_REGISTRY])
        changed['targets'][0]['architecture'] = 'wrong'
        with self.assertRaises(m.Stop):
            m.registry_delta(self.candidate[m.BASE_REGISTRY], json.dumps(changed).encode())

    def test_success_copies_tree_and_preserves_neighbors(self):
        neighbor = self.base / 'state/other-target'
        neighbor.write_bytes(b'unchanged')
        identity = self.base / 'etc/identity.json'
        identity.write_bytes(b'unchanged-identity')
        before = m.fingerprint(identity.stat())
        self.publish()
        self.assertEqual((self.base / 'state/hermes-deals/data/raw/synthetic.json').read_bytes(),
                         self.data['data']['raw']['synthetic.json'])
        self.assertEqual(self.original.read_bytes(), self.candidate[m.NEW_REGISTRY])
        self.assertEqual((self.base / 'compose' / m.ADAPTER).read_bytes(), self.candidate[m.ADAPTER_SOURCE])
        self.assertEqual(neighbor.read_bytes(), b'unchanged')
        self.assertEqual(m.fingerprint(identity.stat()), before)
        for key in ('state_published', 'adapter_published', 'registry_published'):
            self.assertTrue(self.receipt[key])
        for parent, name in (('state', m.STATE_STAGE), ('compose', m.ADAPTER_STAGE), ('etc', m.REGISTRY_STAGE)):
            self.assertFalse((self.base / parent / name).exists())
        self.assertEqual(stat.S_IMODE((self.base / 'state/hermes-deals').stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((self.base / 'state/hermes-deals/config/sources.json').stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.original.stat().st_mode), 0o444)

    def test_baseline_is_exact_public_cv_transformation(self):
        # The extensionless operator needs an explicit source loader.
        from importlib.machinery import SourceFileLoader
        spec = importlib.util.spec_from_loader('cv_stats', SourceFileLoader(
            'cv_stats', str(ROOT / 'ops/bin/rozkalns-cv-live-stats-rollout-1000')))
        cv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cv)
        old = (ROOT / 'ops/deploy/baselines/simple-deploy-targets-weather-rebind-v1.json').read_bytes()
        self.assertEqual(cv.target_only_registry(old), self.candidate[m.BASE_REGISTRY])
        self.assertEqual(m.BASE, 'bcaa7c6db2d2404acb587d78a2dca7a0f7a1bb17')

    def test_full_apply_changes_only_hermes_registry_pair(self):
        before = json.loads(self.candidate[m.BASE_REGISTRY])
        expected = json.loads(self.candidate[m.BASE_REGISTRY])
        hermes = next(t for t in expected['targets'] if t['target_alias'] == 'hermes-deals')
        hermes['compose']['file'] = m.ADAPTER
        hermes['compose']['file_sha256'] = m.HASHES[m.ADAPTER_SOURCE]
        with self.execution_fixture():
            m.execute(m.BASE, True, self.receipt)
            after = json.loads(self.original.read_bytes())
        self.assertEqual(after, expected)
        for target in before['targets']:
            if target['target_alias'] != 'hermes-deals':
                self.assertIn(target, after['targets'])
        self.assertEqual(next(t for t in after['targets'] if t['target_alias'] == 'rozkalns-cv-rpi5')
                         ['compose']['file_sha256'],
                         '6f14d9cbe07b2c03c4e9e14172de4318c1e8d591b97dd595dd82aacb38b7f19c')

    def test_old_and_unrelated_registry_changes_stop_before_data_or_staging(self):
        old = (ROOT / 'ops/deploy/baselines/simple-deploy-targets-weather-rebind-v1.json').read_bytes()
        variants = [old, self.candidate[m.NEW_REGISTRY]]
        for field in ('execution_enabled', 'schema_version'):
            changed = json.loads(self.candidate[m.BASE_REGISTRY])
            changed[field] = False if field == 'execution_enabled' else 2
            variants.append(json.dumps(changed).encode())
        for target_index in range(5):
            changed = json.loads(self.candidate[m.BASE_REGISTRY])
            changed['targets'][target_index]['compose']['file_sha256'] = '0' * 64
            variants.append(json.dumps(changed).encode())
        # One synthetic execution fixture; each rejection must remain pre-mutation.
        with self.execution_fixture(), patch.object(m, 'tree') as tree, patch.object(m, 'publish') as publish:
            for raw in variants:
                with self.subTest(digest=m.digest(raw)):
                    self.original.chmod(0o644)
                    self.original.write_bytes(raw)
                    self.original.chmod(0o444)
                    receipt = m.new_receipt()
                    with self.assertRaises(m.Stop):
                        m.execute(m.BASE, True, receipt)
                    self.assertFalse(receipt['data_content_read'])
                    self.assertFalse(receipt['mutation_attempted'])
            tree.assert_not_called()
            publish.assert_not_called()
            self.assertEqual(list((self.base / 'state').iterdir()), [])

    def test_semantic_guard_preserves_cv_even_if_candidate_pin_is_updated(self):
        changed = json.loads(self.candidate[m.NEW_REGISTRY])
        cv = next(t for t in changed['targets'] if t['target_alias'] == 'rozkalns-cv-rpi5')
        cv['compose']['file_sha256'] = '0' * 64
        raw = (json.dumps(changed, indent=2) + '\n').encode()
        with patch.dict(m.HASHES, {m.NEW_REGISTRY: m.digest(raw)}), self.assertRaises(m.Stop):
            m.registry_delta(self.candidate[m.BASE_REGISTRY], raw)

    def test_existing_targets_or_stages_rejected_without_mutation(self):
        for parent, name in (('state', 'hermes-deals'), ('state', m.STATE_STAGE),
                             ('compose', m.ADAPTER), ('compose', m.ADAPTER_STAGE), ('etc', m.REGISTRY_STAGE)):
            with self.subTest(name=name):
                p = self.base / parent / name
                p.symlink_to('missing')
                try:
                    with self.assertRaises(m.Stop):
                        self.publish()
                    self.assertFalse(self.receipt['mutation_attempted'])
                finally:
                    p.unlink()

    def test_preflight_failure_creates_nothing(self):
        with self.assertRaises(m.Stop):
            self.publish(lambda: m.require(False))
        self.assertFalse(self.receipt['mutation_attempted'])
        self.assertEqual(list((self.base / 'state').iterdir()), [])

    def test_post_staging_failure_preserves_evidence_without_publication(self):
        calls = 0
        def validate():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise m.Stop()
        with self.assertRaises(m.Stop):
            self.publish(validate)
        self.assertTrue(self.receipt['mutation_attempted'])
        self.assertFalse(self.receipt['state_published'])
        self.assertTrue((self.base / 'state' / m.STATE_STAGE).is_dir())
        self.assertTrue((self.base / 'compose' / m.ADAPTER_STAGE).is_file())
        self.assertEqual(self.original.read_bytes(), self.candidate[m.BASE_REGISTRY])

    def test_failure_after_state_publish_does_not_publish_adapter_or_registry(self):
        def validate():
            m.require(not self.receipt['state_published'])
        with self.assertRaises(m.Stop):
            self.publish(validate)
        self.assertTrue(self.receipt['state_published'])
        self.assertFalse(self.receipt['adapter_published'])
        self.assertTrue((self.base / 'state/hermes-deals').exists())
        self.assertEqual(self.original.read_bytes(), self.candidate[m.BASE_REGISTRY])

    def test_registry_replace_failure_retains_state_adapter_and_stage(self):
        with patch.object(m.os, 'replace', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertTrue(self.receipt['adapter_published'])
        self.assertFalse(self.receipt['registry_published'])
        self.assertTrue((self.base / 'etc' / m.REGISTRY_STAGE).exists())
        self.assertEqual(self.original.read_bytes(), self.candidate[m.BASE_REGISTRY])

    def test_state_tamper_after_publish_blocks_registry(self):
        def validate():
            if self.receipt['state_published']:
                (self.base / 'state/hermes-deals/config/sources.json').write_bytes(b'changed')
        with self.assertRaises(m.Stop):
            self.publish(validate)
        self.assertFalse(self.receipt['adapter_published'])
        self.assertFalse(self.receipt['registry_published'])

    def test_noreplace_destination_race_preserves_existing_target(self):
        fd = self.fds['compose']
        (self.base / 'compose/stage').write_bytes(b'candidate')
        (self.base / 'compose/target').write_bytes(b'existing')
        with self.assertRaises(m.Stop):
            m.rename_new(fd, 'stage', 'target')
        self.assertEqual((self.base / 'compose/target').read_bytes(), b'existing')
        self.assertTrue((self.base / 'compose/stage').exists())

    def test_tree_supports_empty_dirs_and_stable_regular_files(self):
        self.source_file()
        (self.base / 'source/empty').mkdir(mode=0o755)
        value = self.tree()
        self.assertEqual(m.contents(value), {'empty': {}, 'snapshot.json': b'{"synthetic":true}'})
        self.assertEqual(value, self.tree())

    def test_source_symlink_hardlink_fifo_and_executable_rejected(self):
        p = self.source_file()
        for kind in ('symlink', 'hardlink', 'fifo', 'executable'):
            with self.subTest(kind=kind):
                bad = self.base / 'source/bad'
                if kind == 'symlink':
                    bad.symlink_to(p)
                elif kind == 'hardlink':
                    os.link(p, bad)
                elif kind == 'fifo':
                    os.mkfifo(bad)
                else:
                    bad.write_bytes(b'data')
                    bad.chmod(0o755)
                try:
                    with self.assertRaises(m.Stop):
                        self.tree()
                finally:
                    bad.unlink()

    def test_hidden_and_key_database_names_rejected(self):
        for name in ('.env', '.git', 'database.db', 'backup.sql', 'credential.pem'):
            with self.subTest(name=name), self.assertRaises(m.Stop):
                m.allowed_name(name)

    def test_tree_rejects_wrong_owner_group_writable_and_acl(self):
        p = self.source_file()
        with self.assertRaises(m.Stop):
            m.tree(self.fds['source'], self.uid + 1, self.gid, [0, 0])
        p.chmod(0o664)
        with self.assertRaises(m.Stop):
            self.tree()
        p.chmod(0o644)
        with patch.object(m.os, 'listxattr', return_value=['system.posix_acl_access']):
            with self.assertRaises(m.Stop):
                self.tree()

    def test_entry_byte_file_and_depth_limits(self):
        self.source_file(value=b'abc')
        for constant in ('MAX_ENTRIES', 'MAX_TOTAL', 'MAX_FILE'):
            with self.subTest(constant=constant), patch.object(m, constant, 0):
                with self.assertRaises(m.Stop):
                    self.tree()
        (self.base / 'source/nested').mkdir(mode=0o755)
        with patch.object(m, 'MAX_DEPTH', 0), self.assertRaises(m.Stop):
            self.tree()

    def test_file_changed_during_read_rejected(self):
        p = self.source_file()
        original_read = os.read
        def read(fd, size):
            value = original_read(fd, size)
            p.write_bytes(b'changed')
            return value
        with patch.object(m.os, 'read', side_effect=read), self.assertRaises(m.Stop):
            self.tree()

    def test_directory_replaced_during_walk_rejected(self):
        p = self.base / 'source/nested'
        p.mkdir(mode=0o755)
        (p / 'file').write_bytes(b'value')
        original_open = os.open
        def open_file(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if name == 'nested':
                p.rename(self.base / 'detached')
                p.mkdir(mode=0o755)
            return fd
        with patch.object(m.os, 'open', side_effect=open_file), self.assertRaises(m.Stop):
            self.tree()

    def test_static_read_rejects_oversize_multilink_symlink_and_mode(self):
        p = self.source_file(value=b'abc')
        with self.assertRaises(m.Stop):
            m.read_file(self.fds['source'], p.name, self.uid, self.gid, 0o644, 2)
        with self.assertRaises(m.Stop):
            m.read_file(self.fds['source'], p.name, self.uid, self.gid, 0o444, 10)
        os.link(p, self.base / 'source/link')
        with self.assertRaises(m.Stop):
            m.read_file(self.fds['source'], p.name, self.uid, self.gid, 0o644, 10)

    def test_identity_never_inferred_from_registry_and_accepts_json_formatting(self):
        value = {'schema': 'rozkalns.rpi5-main.simple-deploy.identity.v1',
                 'repository': 'rozkalnsandris/RPi5_main', 'source_sha': m.BASE}
        with patch.object(m, 'git', return_value=SimpleNamespace(returncode=0)) as check:
            m.identity_provenance(json.dumps(value, indent=2).encode())
            check.assert_called_once_with('merge-base', '--is-ancestor', m.BASE, m.BASE)
        with patch.object(m, 'git', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(m.Stop):
                m.identity_provenance(json.dumps(value).encode())
        for field, bad in (('schema', 'unknown'), ('repository', 'other/repo'), ('source_sha', 'bad')):
            changed = dict(value, **{field: bad})
            with self.subTest(field=field), self.assertRaises(m.Stop):
                m.identity_provenance(json.dumps(changed).encode())
        with self.assertRaises(m.Stop):
            m.identity_provenance(b'{"schema":1,"schema":2}')

    def test_quiescence_checks_only_fixed_units_and_properties(self):
        def show(argv, **kwargs):
            self.assertIn('--all', argv)
            unit = argv[2]
            values = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                      'UnitFileState': 'disabled' if unit.endswith('.timer') else 'static',
                      'Job': '', 'NeedDaemonReload': 'no'}
            return SimpleNamespace(returncode=0, stdout=''.join(f'{k}={v}\n' for k,v in values.items()).encode())
        with patch.object(m.subprocess, 'run', side_effect=show) as run:
            m.quiescent()
            self.assertEqual(run.call_count, 4)
            self.assertTrue(all(c.args[0][:2] == ['/usr/bin/systemctl', 'show'] for c in run.call_args_list))
        bad = show(['', '', 'x.timer', '--all'])
        bad.stdout = bad.stdout.replace(b'UnitFileState=disabled', b'UnitFileState=enabled')
        with patch.object(m.subprocess, 'run', return_value=bad), self.assertRaises(m.Stop):
            m.quiescent()

    def test_sanitized_error_receipt_and_no_retry(self):
        output = io.StringIO()
        with patch.object(m, 'execute', side_effect=OSError('DO_NOT_EMIT_SYNTHETIC_VALUE')) as execute:
            with contextlib.redirect_stdout(output):
                status = m.main(['--expected-source-sha', m.BASE])
        self.assertEqual(status, 2)
        self.assertEqual(execute.call_count, 1)
        self.assertNotIn('DO_NOT_EMIT', output.getvalue())
        self.assertEqual(json.loads(output.getvalue()), m.new_receipt())

    @contextlib.contextmanager
    def execution_fixture(self):
        etc, state = self.base / 'etc', self.base / 'state'
        private = etc / 'private'
        private.mkdir(mode=0o750)
        compose = etc / 'compose'
        compose.mkdir(mode=0o755)
        state.chmod(0o700)
        env = private / m.ENV
        env.write_bytes(b'SYNTHETIC_ENV_MUST_NOT_BE_READ')
        env.chmod(0o640)
        identity = etc / 'identity.json'
        identity.write_text(json.dumps({'schema': 'rozkalns.rpi5-main.simple-deploy.identity.v1',
                                       'repository': 'rozkalnsandris/RPi5_main', 'source_sha': m.BASE}))
        identity.chmod(0o444)
        weather = compose / 'rozkalns-weather-public.yml'
        weather.write_bytes(self.candidate[m.WEATHER_SOURCE])
        weather.chmod(0o444)
        exe_parent = self.base / 'executor'
        exe_parent.mkdir(mode=0o755)
        executor = exe_parent / 'simple_deploy_v1.py'
        executor.write_bytes(self.candidate[m.EXECUTOR_SOURCE])
        executor.chmod(0o444)
        checkout = self.base / 'hermes-deals'
        (checkout / 'data/raw').mkdir(parents=True, mode=0o755)
        (checkout / 'config').mkdir(mode=0o755)
        (checkout / 'data/raw/snapshot.json').write_bytes(b'{"synthetic":true}')
        (checkout / 'data/raw/snapshot.json').chmod(0o644)
        (checkout / 'config/sources.json').write_bytes(b'{}')
        (checkout / 'config/sources.json').chmod(0o644)
        account = SimpleNamespace(pw_uid=self.uid, pw_gid=self.gid, pw_dir=str(self.base))
        original_file_meta, original_directory_meta = m.file_meta, m.directory_meta
        original_publish, original_open = m.publish, m.os.open
        @contextlib.contextmanager
        def fixture_directory(path, owners):
            # Tests substitute only ancestor location/UID; leaf checks remain real.
            fd = original_open(path, m.DIR_FLAGS)
            try:
                yield fd
            finally:
                os.close(fd)
        def file_meta(st, uid, gid, mode):
            return original_file_meta(st, self.uid if uid == 0 else uid,
                                      self.gid if gid == 0 else gid, mode)
        def dir_meta(fd, uid, gid, mode):
            return original_directory_meta(fd, self.uid if uid == 0 else uid,
                                           self.gid if gid == 0 else gid, mode)
        def publish(*args, **kwargs):
            return original_publish(*args, **kwargs, uid=self.uid, gid=self.gid)
        def open_guard(name, flags, *args, **kwargs):
            if os.fspath(name) == m.ENV:
                self.assertTrue(flags & os.O_PATH, 'env must never be opened for content')
            return original_open(name, flags, *args, **kwargs)
        with contextlib.ExitStack() as stack:
            for name, value in (('ETC', etc), ('STATE', state), ('EXECUTOR', executor),
                                ('source_check', lambda sha: None), ('runtime_ids', lambda: (self.uid, self.gid)),
                                ('quiescent', lambda: None), ('directory', fixture_directory),
                                ('file_meta', file_meta), ('directory_meta', dir_meta), ('publish', publish)):
                stack.enter_context(patch.object(m, name, value))
            stack.enter_context(patch.object(m.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(m.os, 'open', side_effect=open_guard))
            stack.enter_context(patch.object(m.pwd, 'getpwnam', return_value=account))
            stack.enter_context(patch.object(m, 'git', return_value=SimpleNamespace(returncode=0)))
            yield env, identity, checkout

    def test_default_check_reads_no_data_or_env_and_creates_nothing(self):
        with self.execution_fixture() as (env, identity, checkout):
            before = m.fingerprint(env.stat()), m.fingerprint(identity.stat())
            with patch.object(m, 'tree', side_effect=AssertionError('default must not recurse')):
                m.execute(m.BASE, False, self.receipt)
            self.assertEqual(self.receipt['status'], 'BASELINE_CHECKED_DATA_UNREAD')
            self.assertFalse(self.receipt['mutation_attempted'])
            self.assertFalse(self.receipt['data_content_read'])
            self.assertEqual(list((self.base / 'state').iterdir()), [])
            self.assertEqual(before, (m.fingerprint(env.stat()), m.fingerprint(identity.stat())))

    def test_full_apply_preserves_env_identity_and_source(self):
        with self.execution_fixture() as (env, identity, checkout):
            before = m.fingerprint(env.stat()), m.fingerprint(identity.stat())
            source = checkout / 'data/raw/snapshot.json'
            source_fp = m.fingerprint(source.stat())
            m.execute(m.BASE, True, self.receipt)
            self.assertEqual(self.receipt['status'], 'PREPARED_NO_ACTIVATION')
            self.assertFalse(self.receipt['env_content_read'])
            self.assertEqual(before, (m.fingerprint(env.stat()), m.fingerprint(identity.stat())))
            self.assertEqual(m.fingerprint(source.stat()), source_fp)
            self.assertEqual((self.base / 'state/hermes-deals/data/raw/snapshot.json').read_bytes(), source.read_bytes())

    def test_execute_rejects_static_baseline_drift_before_data_read(self):
        with self.execution_fixture():
            self.original.chmod(0o644)
            self.original.write_bytes(b'drift')
            self.original.chmod(0o444)
            with self.assertRaises(m.Stop):
                m.execute(m.BASE, True, self.receipt)
            self.assertFalse(self.receipt['data_content_read'])
            self.assertFalse(self.receipt['mutation_attempted'])

    def test_source_changes_after_snapshot_prevent_first_stage(self):
        with self.execution_fixture() as (_, _, checkout):
            original_tree = m.tree
            calls = 0
            def tree(*args, **kwargs):
                nonlocal calls
                result = original_tree(*args, **kwargs)
                calls += 1
                if calls == 2:
                    (checkout / 'data/raw/snapshot.json').write_bytes(b'changed')
                return result
            with patch.object(m, 'tree', side_effect=tree), self.assertRaises(m.Stop):
                m.execute(m.BASE, True, self.receipt)
            self.assertTrue(self.receipt['data_content_read'])
            self.assertFalse(self.receipt['mutation_attempted'])
            self.assertEqual(list((self.base / 'state').iterdir()), [])

    def test_missing_sources_config_stops_before_first_write(self):
        with self.execution_fixture() as (_, _, checkout):
            (checkout / 'config/sources.json').unlink()
            with self.assertRaises(m.Stop):
                m.execute(m.BASE, True, self.receipt)
            self.assertFalse(self.receipt['mutation_attempted'])

    def test_quiescence_rejects_pending_job_or_missing_properties(self):
        good = b'LoadState=loaded\nActiveState=inactive\nSubState=dead\nUnitFileState=static\nJob=\nNeedDaemonReload=no\n'
        for raw in (good.replace(b'Job=\n', b'Job=123\n'), good.replace(b'Job=\n', b''),
                    good.replace(b'NeedDaemonReload=no', b'NeedDaemonReload=yes')):
            with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=raw)):
                with self.assertRaises(m.Stop):
                    m.quiescent()

    def test_quiescence_accepts_only_absent_instance_units(self):
        def show(argv, **kwargs):
            instance = '@' in argv[2]
            values = {'LoadState': 'not-found' if instance else 'loaded',
                      'ActiveState': 'inactive', 'SubState': 'dead',
                      'UnitFileState': '' if instance else ('disabled' if argv[2].endswith('.timer') else 'static'),
                      'Job': '', 'NeedDaemonReload': 'no'}
            return SimpleNamespace(returncode=0, stdout=''.join(f'{k}={v}\n' for k,v in values.items()).encode())
        with patch.object(m.subprocess, 'run', side_effect=show):
            m.quiescent()
        absent = show(['', '', 'x' + '@' + 'hermes-deals.timer'])
        with patch.object(m.subprocess, 'run', return_value=absent), self.assertRaises(m.Stop):
            m.quiescent()

    def test_git_is_readonly_and_does_not_accept_environment_overrides(self):
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            m.git('merge-base', '--is-ancestor', m.BASE, m.BASE)
        argv = run.call_args.args[0]
        self.assertIn('--no-optional-locks', argv)
        env = run.call_args.kwargs['env']
        self.assertEqual(env['GIT_OPTIONAL_LOCKS'], '0')
        self.assertEqual(env['GIT_NO_REPLACE_OBJECTS'], '1')
        self.assertNotIn('status', argv)


if __name__ == '__main__':
    unittest.main()
