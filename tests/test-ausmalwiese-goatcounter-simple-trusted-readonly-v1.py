#!/usr/bin/env python3
"""Offline-only source tests. No real DB, Cloudflare, root, install or creds."""
import contextlib
import hashlib
import importlib.util
import io
import json
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
                i.install_once(self.package)
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
                             client=CANARY, account_id=CANARY,
                             zone_id=CANARY), 'STOP_CLOUDFLARE')
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
            self.assertEqual(o.collect_once(expected_source_sha=SHA),'STOP_COLLECT')
            self.assertGreater(vfs.call_count,0)

    def test_authorization_missing_grant_fails_closed(self):
        with patch.object(o,'load_json',side_effect=OSError(CANARY)):
            with self.assertRaises(OSError):
                o.approved('COLLECT',SHA)
        for scope in ('ALL','WRITE','COLLECT+GET'):
            with patch.object(o,'load_json') as loader:
                with self.assertRaises(o.Stop):
                    o.approved(scope,SHA)
                loader.assert_not_called()

    def test_no_secret_in_public_status(self):
        with patch.object(o,'verify_release',side_effect=OSError(CANARY)):
            a=o.offline_status(SHA)
        self.assertEqual(a,'STOP_RELEASE')
        self.assertNotIn(CANARY,a)


if __name__ == '__main__':
    unittest.main()
