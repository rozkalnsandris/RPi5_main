#!/usr/bin/env python3
"""Offline-only source tests. No real DB, Cloudflare, root, install or creds."""
import contextlib
import hashlib
import importlib.util
import io
import json
import stat
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / 'scripts'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


i = load('goatcounter_installer', 'install-ausmalwiese-goatcounter-simple-trusted-readonly-v1.py')
o = load('goatcounter_runner', 'ausmalwiese_goatcounter_simple_trusted_runner_v1.py')
SHA = 'f' * 40
CANARY = 'DO_NOT_LEAK_PRIVATE_CREDENTIAL_OR_IP'


def sources():
    return {name: (name + '\nmock source bytes').encode()
            for name in i.SOURCE}


class Tests(unittest.TestCase):
    def setUp(self):
        self.blobs = sources()
        self.package = i.build_package(SHA, self.blobs)

    def test_package_exact_legacy_and_full_hashes(self):
        self.assertEqual(set(self.package), set(i.SOURCE) | {
            'release.json', 'trusted-release.json'})
        for meta_name, expected in [('release.json', i.LEGACY_FILES),
                                    ('trusted-release.json', o.FILES)]:
            meta = json.loads(self.package[meta_name])
            self.assertEqual(set(meta['sha256']), set(expected))
            self.assertEqual(meta['source_sha'], SHA)
            for name in expected:
                self.assertEqual(meta['sha256'][name],
                                 hashlib.sha256(self.blobs[name]).hexdigest())
        self.assertEqual(self.package, i.build_package(SHA, dict(reversed(
            list(self.blobs.items())))))

    def test_reject_missing_extra_or_modified_sources(self):
        variants = [{}, {**self.blobs, 'extra': b'x'},
                    {k:v for k,v in self.blobs.items() if k != 'operator.py'},
                    {**self.blobs, 'operator.py': ''},
                    {**self.blobs, 'operator.py': b''},
                    {**self.blobs, 'operator.py': b'x' * 196609}]
        for v in variants:
            with self.subTest(keys=len(v)):
                with self.assertRaises(i.Stop):
                    i.build_package(SHA, v)

    def test_bad_sha_rejected(self):
        for value in (None, '', 'F'*40, 'e'*39, CANARY):
            with self.subTest(value=value):
                with self.assertRaises(i.Stop):
                    i.build_package(value,self.blobs)

    def test_package_never_uses_installer_or_network(self):
        with patch.object(i.os, 'mkdir', side_effect=AssertionError('WRITE')), \
             patch.object(i, 'git', side_effect=AssertionError('GIT')):
            self.assertEqual(len(i.build_package(SHA,self.blobs)), 11)

    def test_install_requires_root_and_exact_host_before_mutation(self):
        for euid, host in [(1000,'rpi5'),(0,'not-rpi5')]:
            with patch.object(i.os, 'geteuid', return_value=euid), \
                 patch.object(i.socket, 'gethostname', return_value=host), \
                 patch.object(i,'load_checkout') as load, \
                 patch.object(i.os,'mkdir') as mkdir, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(i.main(['--expected-main', SHA,
                                        '--apply', '--confirm-install', i.CONFIRM]),2)
                load.assert_not_called()
                mkdir.assert_not_called()

    def test_invalid_confirmation_no_read_or_write(self):
        with patch.object(i,'load_checkout') as load, \
             patch.object(i.os,'mkdir') as mkdir, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(i.main(['--expected-main',SHA,'--apply']),2)
            load.assert_not_called()
            mkdir.assert_not_called()

    def test_existing_target_rejects_prior_to_mkdir(self):
        with patch.object(i, '_root_safe'), \
             patch.object(i.os.path, 'lexists', return_value=True), \
             patch.object(i.os, 'mkdir') as mkdir:
            with self.assertRaises(i.Stop):
                i.install_once(SHA, self.package)
            mkdir.assert_not_called()

    def test_versioned_target_matches_exact_sha_and_preserves_legacy(self):
        target = i.versioned_root(SHA)
        self.assertEqual(target, i.ROOT.with_name(i.ROOT.name + '-' + SHA))
        self.assertNotEqual(target, i.ROOT)
        self.assertEqual(target.parent, i.ROOT.parent)
        for bad in ('', 'F' * 40, '../', 'f' * 39, None):
            with self.subTest(bad=bad):
                with self.assertRaises(i.Stop):
                    i.versioned_root(bad)

    def test_versioned_installer_never_writes_legacy_directory(self):
        target = i.versioned_root(SHA)
        with patch.object(i, '_root_safe'), \
             patch.object(i.os.path, 'lexists', return_value=False) as exists, \
             patch.object(i.os, 'mkdir', side_effect=i.Stop()) as mkdir, \
             patch.object(i.os, 'open') as opening:
            with self.assertRaises(i.Stop):
                i.install_once(SHA, self.package)
            exists.assert_called_once_with(target)
            mkdir.assert_called_once_with(target, 0o700)
            opening.assert_not_called()

    def test_manifest_source_sha_mismatch_stops_before_any_install(self):
        other = 'e' * 40
        with patch.object(i, '_root_safe') as parent, \
             patch.object(i.os.path, 'lexists') as exists, \
             patch.object(i.os, 'mkdir') as mkdir:
            with self.assertRaises(i.Stop):
                i.install_once(other, self.package)
            parent.assert_not_called()
            exists.assert_not_called()
            mkdir.assert_not_called()

    def test_versioned_runner_rejects_other_release_before_protected_io(self):
        wrong = i.versioned_root('e' * 40)
        with patch.object(o, 'ROOT', wrong), \
             patch.object(o, 'load_json') as loader:
            with self.assertRaises(o.Stop):
                o.verify_release(SHA)
            loader.assert_not_called()
        with patch.object(o, 'ROOT', i.ROOT), \
             patch.object(o, 'load_json') as loader:
            with self.assertRaises(o.Stop):
                o.verify_release(SHA)
            loader.assert_not_called()

    def git_identity(self, *, sudo='1000', euid=0, repo_uid=1000,
                     git_uid=1000, source_uid=1000,
                     repo_mode=stat.S_IFDIR | 0o755,
                     git_mode=stat.S_IFDIR | 0o755,
                     source_mode=stat.S_IFREG | 0o644,
                     expect_success=True):
        repo = Path('/synthetic/verified-checkout')
        entry = Path(i.__file__).absolute()
        original = Path.lstat

        def metadata(p):
            if p == entry:
                return SimpleNamespace(st_uid=source_uid, st_mode=source_mode,
                                       st_nlink=1)
            if p == repo:
                return SimpleNamespace(st_uid=repo_uid, st_mode=repo_mode)
            if p == repo / '.git':
                return SimpleNamespace(st_uid=git_uid, st_mode=git_mode)
            return original(p)

        env = {} if sudo is None else {'SUDO_UID': sudo}
        env.update({'GIT_CONFIG_COUNT': '9', 'GIT_TRACE': 'private-canary'})
        with patch.object(i, 'REPO', repo), \
             patch.object(i.os, 'geteuid', return_value=euid), \
             patch.object(Path, 'lstat', new=metadata), \
             patch.dict(i.os.environ, env, clear=True), \
             patch.object(i.subprocess, 'run') as run, \
             patch.object(i.os, 'mkdir') as mkdir:
            if expect_success:
                self.assertEqual(i.verified_git_owner(), repo_uid)
            else:
                with self.assertRaises(i.GitTrustStop):
                    i.verified_git_owner()
            run.assert_not_called()
            mkdir.assert_not_called()

    def test_root_sudo_checkout_identity_exact_pass(self):
        self.git_identity()

    def test_non_root_checkout_owner_pass_and_sudo_ignored(self):
        self.git_identity(euid=1000, sudo='9999')

    def test_missing_bad_or_spoofed_sudo_uid_fails_before_git(self):
        for value in (None, '', '0', '0001', '1000 ', '+1000', '-1000',
                      '1000\n', 'not-a-number', '1001', '4294967295',
                      '99999999999'):
            with self.subTest(sudo=value):
                self.git_identity(sudo=value, expect_success=False)

    def test_misowned_checkout_gitdir_and_entry_fail_before_git(self):
        for details in ({'repo_uid': 0}, {'git_uid': 0},
                        {'source_uid': 0}, {'repo_uid': 1001},
                        {'git_uid': 1001}):
            with self.subTest(details=details):
                self.git_identity(**details, expect_success=False)

    def test_symlink_gitdir_checkout_and_source_are_denied(self):
        for details in ({'repo_mode': stat.S_IFLNK | 0o777},
                        {'git_mode': stat.S_IFLNK | 0o777},
                        {'source_mode': stat.S_IFLNK | 0o777}):
            with self.subTest(details=details):
                self.git_identity(**details, expect_success=False)

    def test_group_writable_metadata_is_denied(self):
        for details in ({'repo_mode': stat.S_IFDIR | 0o775},
                        {'git_mode': stat.S_IFDIR | 0o775},
                        {'source_mode': stat.S_IFREG | 0o666}):
            with self.subTest(details=details):
                self.git_identity(**details, expect_success=False)

    def test_root_git_env_is_sudo_owner_only_and_no_config_inheritance(self):
        with patch.object(i, 'verified_git_owner', return_value=1000), \
             patch.object(i.os, 'geteuid', return_value=0), \
             patch.dict(i.os.environ, {
                 'SUDO_UID': '1000', 'HOME': '/private-canary',
                 'GIT_CONFIG_GLOBAL': '/private-canary',
                 'GIT_CONFIG_COUNT': '1', 'GIT_TRACE': 'private-canary',
                 'GIT_EXEC_PATH': '/private-canary',
             }, clear=True), \
             patch.object(i.subprocess, 'run', return_value=SimpleNamespace(
                 returncode=0, stdout=b'synthetic sha\n')) as run, \
             patch.object(i.os, 'mkdir') as mkdir:
            self.assertEqual(i.git('rev-parse', 'HEAD'), b'synthetic sha\n')
            args, kw = run.call_args
            self.assertEqual(args[0][0], '/usr/bin/git')
            self.assertIn('core.fsmonitor=false', args[0])
            self.assertIn('core.hooksPath=/dev/null', args[0])
            self.assertEqual(args[0][-2:], ['rev-parse', 'HEAD'])
            self.assertEqual(kw['env'], {
                'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                'GIT_CONFIG_NOSYSTEM': '1',
                'GIT_CONFIG_GLOBAL': '/dev/null',
                'GIT_OPTIONAL_LOCKS': '0',
                'GIT_TERMINAL_PROMPT': '0',
                'SUDO_UID': '1000',
            })
            self.assertIs(kw['stderr'], i.subprocess.DEVNULL)
            mkdir.assert_not_called()

    def test_unprivileged_git_env_never_forwards_sudo_or_git_values(self):
        with patch.object(i, 'verified_git_owner', return_value=1000), \
             patch.object(i.os, 'geteuid', return_value=1000), \
             patch.dict(i.os.environ, {'SUDO_UID': '7777',
                                       'GIT_TRACE': 'private-canary'}, clear=True), \
             patch.object(i.subprocess, 'run', return_value=SimpleNamespace(
                 returncode=0, stdout=b'')) as run:
            i.git('status', '--porcelain=v1')
            self.assertNotIn('SUDO_UID', run.call_args.kwargs['env'])
            self.assertNotIn('GIT_TRACE', run.call_args.kwargs['env'])

    def test_rejected_git_trust_never_runs_git_or_installs(self):
        with patch.object(i, 'verified_git_owner',
                          side_effect=i.GitTrustStop()), \
             patch.object(i.subprocess, 'run') as run, \
             patch.object(i.os, 'mkdir') as mkdir:
            with self.assertRaises(i.GitTrustStop):
                i.git('rev-parse', 'HEAD')
            run.assert_not_called()
            mkdir.assert_not_called()

    def test_git_safe_directory_failure_is_fixed_status(self):
        with patch.object(i, 'verified_git_owner', return_value=1000), \
             patch.object(i.os, 'geteuid', return_value=0), \
             patch.object(i.subprocess, 'run', return_value=SimpleNamespace(
                 returncode=128, stdout=b'')), \
             patch.object(i.os, 'mkdir') as mkdir:
            with self.assertRaises(i.GitTrustStop):
                i.git('rev-parse', 'HEAD')
            mkdir.assert_not_called()
        with patch.object(i.os, 'geteuid', return_value=0), \
             patch.object(i.socket, 'gethostname', return_value='rpi5'), \
             patch.object(i, 'load_checkout',
                          side_effect=i.GitTrustStop()), \
             patch.object(i.os, 'mkdir') as mkdir, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(i.main(['--expected-main', SHA, '--apply',
                                     '--confirm-install', i.CONFIRM]), 2)
            self.assertEqual(output.getvalue().strip(), 'STOP_GIT_TRUST')
            mkdir.assert_not_called()

    def test_source_verify_trusted_mode_never_proves_live(self):
        self.assertEqual(o.offline_status(SHA), 'STOP_RELEASE')
        self.assertNotEqual(o.offline_status(SHA), 'PASS_LIVE')

    def test_no_protected_dispatch_before_provenance(self):
        with patch.object(o, 'verify_release', side_effect=o.Stop()), \
             patch.object(o, 'approved') as approve, \
             patch.object(o.os, 'statvfs') as statvfs:
            self.assertEqual(o.collect_once(expected_source_sha=SHA), 'STOP_COLLECT')
            approve.assert_not_called()
            statvfs.assert_not_called()
        with patch.object(o, 'verify_release', side_effect=o.Stop()), \
             patch.object(o, 'approved') as approve:
            self.assertEqual(o.cloudflare_once(expected_source_sha=SHA,
                             client_factory=lambda typ: CANARY,
                             account_id=CANARY, zone_id=CANARY),
                             'STOP_CLOUDFLARE')
            approve.assert_not_called()

    def test_no_protected_dispatch_without_owner_grant(self):
        with patch.object(o, 'verify_release', return_value=True), \
             patch.object(o, 'approved', side_effect=o.Stop()), \
             patch.object(o.os, 'statvfs') as statvfs:
            self.assertEqual(o.collect_once(expected_source_sha=SHA), 'STOP_COLLECT')
            statvfs.assert_not_called()

    def test_grant_requires_exact_identity_scope_boolean(self):
        valid={'schema':1,'repository':o.REPOSITORY,'source_sha':SHA,
               'scope':'COLLECT','owner_approved':True,'one_shot':True}
        self.assertTrue(o.grant_ok(valid,scope='COLLECT',source_sha=SHA))
        for item in [{**valid,'one_shot':1},{**valid,'owner_approved':'yes'},
                     {**valid,'source_sha':'c'*40},{**valid,'scope':'CLOUDFLARE_GET'},
                     {**valid,'more':CANARY},{k:v for k,v in valid.items()
                                            if k!='scope'},None]:
            with self.subTest(item=str(type(item))):
                self.assertFalse(o.grant_ok(item,scope='COLLECT',source_sha=SHA))

    def test_read_only_mount_required_for_wal(self):
        actual_stat = Path.stat
        def stub_stat(p, *a, **kw):
            if p in (o.DB, o.DB.parent):
                return SimpleNamespace(st_dev=1)
            return actual_stat(p, *a, **kw)
        with patch.object(o,'verify_release',return_value=True), \
             patch.object(o,'approved',return_value=None), \
             patch.object(Path, 'stat', new=stub_stat), \
             patch.object(o.os, 'statvfs') as vfs:
            vfs.return_value.f_flag=0
            self.assertEqual(o.collect_once(expected_source_sha=SHA,
                              readonly_proof=lambda paths: True),
                              'STOP_COLLECT')
            self.assertGreater(vfs.call_count,0)

    def test_authorization_missing_grant_fails_closed(self):
        with patch.object(o,'load_json',side_effect=OSError(CANARY)):
            with self.assertRaises(OSError):
                o.approved('COLLECT',SHA,owner_gate=lambda scope, sha: True)
        for scope in ('ALL','WRITE','COLLECT+GET'):
            with patch.object(o,'load_json') as loader:
                with self.assertRaises(o.Stop):
                    o.approved(scope,SHA)
                loader.assert_not_called()

    def test_reject_foreign_preloaded_dependency(self):
        foreign = SimpleNamespace(__file__='/tmp/checkout-cloudflare.py')
        with patch.dict(o.sys.modules, {'cloudflare_rdc_operator': foreign}):
            with self.assertRaises(o.Stop):
                o.verified_import_path()

    def test_runtime_owner_identity_gate_precedes_release_access(self):
        with patch.object(o.os, 'geteuid', return_value=1000), \
             patch.object(o, 'load_json') as read:
            with self.assertRaises(o.Stop):
                o.verify_release(SHA)
            read.assert_not_called()

    def test_one_shot_consumed_before_protected_call(self):
        grant = {'schema': 1, 'repository': o.REPOSITORY,
                 'source_sha': SHA, 'scope': 'COLLECT',
                 'owner_approved': True, 'one_shot': True}
        with patch.object(o, '_PROTECTED_CALL_CONSUMED', False), \
             patch.object(o, 'load_json', return_value=grant) as reader:
            o.approved('COLLECT', SHA,owner_gate=lambda scope, sha: True)
            with self.assertRaises(o.Stop):
                o.approved('COLLECT', SHA,owner_gate=lambda scope, sha: True)
            reader.assert_called_once()

    def test_independent_owner_gate_required_before_grant_or_client(self):
        with patch.object(o, '_PROTECTED_CALL_CONSUMED', False), \
             patch.object(o, 'load_json') as grant, \
             patch.object(o, 'verified_import_path') as imports:
            with self.assertRaises(o.Stop):
                o.approved('CLOUDFLARE_GET', SHA)
            grant.assert_not_called()
            self.assertEqual(o.cloudflare_once(
                expected_source_sha=SHA, client_factory=lambda typ: CANARY,
                owner_gate=None), 'STOP_CLOUDFLARE')
            imports.assert_not_called()

    def test_denied_owner_gate_consumes_once_with_no_protected_call(self):
        grant={'schema':1,'repository':o.REPOSITORY,'source_sha':SHA,
               'scope':'CLOUDFLARE_GET','owner_approved':True,'one_shot':True}
        calls=[]
        def rejected(scope, sha):
            calls.append((scope,sha))
            return False
        with patch.object(o, '_PROTECTED_CALL_CONSUMED', False), \
             patch.object(o, 'load_json', return_value=grant) as read:
            with self.assertRaises(o.Stop):
                o.approved('CLOUDFLARE_GET',SHA,owner_gate=rejected)
            with self.assertRaises(o.Stop):
                o.approved('CLOUDFLARE_GET',SHA,owner_gate=rejected)
            self.assertEqual(calls,[('CLOUDFLARE_GET',SHA)])
            read.assert_called_once()

    def test_collect_without_independent_readonly_mount_proof_no_db_open(self):
        with patch.object(o, 'verify_release', return_value=True), \
             patch.object(o, 'approved', return_value=None), \
             patch.object(o.os, 'statvfs') as vfs, \
             patch.object(o, 'release_import') as imports:
            self.assertEqual(o.collect_once(
                expected_source_sha=SHA, owner_gate=lambda s,h:True),
                'STOP_COLLECT')
            vfs.assert_not_called()
            imports.assert_not_called()

    def test_no_protected_import_without_isolated_nobytecode_mode(self):
        for isolated, nobytecode in ((0,1),(1,0),(0,0)):
            with self.subTest(isolated=isolated,bytecode=nobytecode), \
                 patch.object(o.sys,'flags',SimpleNamespace(
                     isolated=isolated,dont_write_bytecode=nobytecode)), \
                 patch.object(o.sys,'path',list(o.sys.path)):
                prior=list(o.sys.path)
                with self.assertRaises(o.Stop):
                    o.verified_import_path()
                self.assertEqual(prior,o.sys.path)

    def test_stdlib_operator_cannot_be_shadowed_by_release(self):
        fake=SimpleNamespace(__file__=str(o.ROOT/'operator.py'))
        with patch.object(o.sys,'flags',SimpleNamespace(
                 isolated=1,dont_write_bytecode=1)), \
             patch.object(o.sys,'path',list(o.sys.path)), \
             patch.dict(o.sys.modules, {'operator': fake}):
            with self.assertRaises(o.Stop):
                o.verified_import_path()
            self.assertNotIn(str(o.ROOT),o.sys.path)

    def test_safe_isolated_mode_can_import_after_stdlib_operator_pin(self):
        with patch.object(o.sys,'flags',SimpleNamespace(
                 isolated=1,dont_write_bytecode=1)), \
             patch.object(o.sys,'path',list(o.sys.path)):
            self.assertNotIn(str(o.ROOT),o.sys.path)
            o.verified_import_path()
            self.assertEqual(o.sys.path[0],str(o.ROOT))

    def test_one_shot_cloudflare_synthetic_injected_factory(self):
        class FakeClient:
            pass
        fake_run = SimpleNamespace(run_guarded=lambda **kwargs: (
            'PASS_EDGE_SOURCE_ONLY', {'raw': CANARY}))
        with patch.object(o,'verify_release',return_value=True), \
             patch.object(o,'approved',return_value=None) as approve, \
             patch.object(o,'verified_import_path') as imports, \
             patch.object(o,'release_import') as release_import, \
             patch.object(o.importlib.util,'spec_from_file_location') as spec, \
             patch.object(o.importlib.util,'module_from_spec',
                          return_value=fake_run), \
             patch.object(o.sys,'path',list(o.sys.path)), \
             patch.dict(o.sys.modules, {
                 'cloudflare_rdc_operator': SimpleNamespace(
                     CloudflareClient=FakeClient)}):
            result=o.cloudflare_once(
                expected_source_sha=SHA, owner_gate=lambda s,h: True,
                account_id='a'*32, zone_id='b'*32,
                client_factory=lambda trusted: trusted())
            self.assertEqual(result,'PASS_EDGE_SOURCE_ONLY')
            self.assertNotIn(CANARY,result)
            self.assertEqual(release_import.call_count,6)
            approve.assert_called_once_with(
                'CLOUDFLARE_GET',SHA,
                owner_gate=unittest.mock.ANY)
            imports.assert_called_once()
            spec.return_value.loader.exec_module.assert_called_once_with(fake_run)

    def test_cloudflare_client_factory_must_return_exact_trusted_type(self):
        class FakeClient:
            pass
        with patch.object(o,'verify_release',return_value=True), \
             patch.object(o,'approved',return_value=None), \
             patch.object(o,'verified_import_path'), \
             patch.object(o,'release_import'), \
             patch.object(o.importlib.util,'spec_from_file_location') as spec, \
             patch.object(o.sys,'path',list(o.sys.path)), \
             patch.dict(o.sys.modules, {
                 'cloudflare_rdc_operator': SimpleNamespace(
                     CloudflareClient=FakeClient)}):
            result=o.cloudflare_once(
                expected_source_sha=SHA, owner_gate=lambda s,h:True,
                client_factory=lambda trusted: object())
            self.assertEqual(result,'STOP_CLOUDFLARE')
            spec.assert_not_called()

    def test_no_secret_in_public_status(self):
        with patch.object(o,'verify_release',side_effect=OSError(CANARY)):
            a=o.offline_status(SHA)
        self.assertEqual(a,'STOP_RELEASE')
        self.assertNotIn(CANARY,a)


if __name__ == '__main__':
    unittest.main()
