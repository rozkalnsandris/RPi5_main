#!/usr/bin/env python3
"""Offline safety tests: never touch a credential file or Cloudflare network."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/ausmalwiese_worker_settings_executor.py'
CONTRACT = ROOT / 'ops/contracts/ausmalwiese-worker-settings-executor-v1.json'
spec = importlib.util.spec_from_file_location('aw_executor', SOURCE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
ACCOUNT = 'a' * 32
TOKEN = 'fixed-dummy-token-not-real-0123456789'


class FakeReply:
    def __init__(self, body=b'{"success":true,"result":{"logpush":false}}', status=200,
                 content_type='application/json', content_length=None, encoding='identity'):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type, 'Content-Encoding': encoding}
        if content_length is not None:
            self.headers['Content-Length'] = content_length

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, limit):
        return self.body[:limit]


class FakeConnection:
    def __init__(self, reply=None):
        self.reply = reply or FakeReply()
        self.calls = []
        self.closed = False

    def request(self, method, path, headers):
        self.calls.append((method, path, headers))

    def getresponse(self):
        return self.reply

    def close(self):
        self.closed = True


class ExecutorTests(unittest.TestCase):
    def test_source_contract_excludes_credentials_live_or_install(self):
        c = json.loads(CONTRACT.read_text('utf-8'))
        self.assertEqual(c['status'], 'SOURCE_ONLY_NOT_INSTALLED')
        self.assertEqual(c['source']['executor'], 'scripts/ausmalwiese_worker_settings_executor.py')
        self.assertFalse(c['actions']['install_authorized'])
        self.assertFalse(c['actions']['credential_access_authorized'])
        self.assertFalse(c['actions']['cloudflare_get_authorized'])
        self.assertFalse(c['actions']['merge_authorized'])

    def test_exact_endpoint_and_one_get(self):
        conn = FakeConnection()
        with mock.patch.object(mod.http.client, 'HTTPSConnection', return_value=conn) as http:
            result = mod.single_get(ACCOUNT, TOKEN)
        self.assertEqual(result['result']['logpush'], False)
        http.assert_called_once()
        self.assertEqual(http.call_args.args[0], 'api.cloudflare.com')
        self.assertEqual(http.call_args.kwargs['timeout'], 10)
        self.assertEqual(len(conn.calls), 1)
        method, path, headers = conn.calls[0]
        self.assertEqual(method, 'GET')
        self.assertEqual(path, '/client/v4/accounts/' + ACCOUNT + '/workers/scripts/coloring-pages-stats-v1/script-settings')
        self.assertEqual(headers['Accept-Encoding'], 'identity')
        self.assertTrue(conn.closed)

    def test_reject_non_200_including_redirect_without_second_call(self):
        for status in (301, 302, 307, 401, 403, 429, 500):
            with self.subTest(status=status):
                conn = FakeConnection(FakeReply(status=status))
                with mock.patch.object(mod.http.client, 'HTTPSConnection', return_value=conn):
                    with self.assertRaises(mod.Stop):
                        mod.single_get(ACCOUNT, TOKEN)
                self.assertEqual(len(conn.calls), 1)
                self.assertTrue(conn.closed)

    def test_bound_body_size_and_content_type(self):
        bad = [FakeReply(body=b'x' * 32769), FakeReply(content_length='32769'),
               FakeReply(content_length='abc'), FakeReply(content_type='text/html'),
               FakeReply(encoding='gzip')]
        for reply in bad:
            with self.subTest(reply=reply):
                conn = FakeConnection(reply)
                with mock.patch.object(mod.http.client, 'HTTPSConnection', return_value=conn):
                    with self.assertRaises(mod.Stop):
                        mod.single_get(ACCOUNT, TOKEN)
                self.assertEqual(len(conn.calls), 1)

    def test_bad_json_and_nan_fail_closed(self):
        for reply in (b'{not-json}', b'{"x":NaN}', b'\xff'):
            with self.subTest(reply=reply):
                with mock.patch.object(mod.http.client, 'HTTPSConnection', return_value=FakeConnection(FakeReply(body=reply))):
                    with self.assertRaises(mod.Stop):
                        mod.single_get(ACCOUNT, TOKEN)

    def test_invalid_account_never_connects(self):
        for account in ('x', 'A'*32, '../', None):
            with self.subTest(account=account):
                with mock.patch.object(mod.http.client, 'HTTPSConnection') as http:
                    with self.assertRaises(mod.Stop):
                        mod.single_get(account, TOKEN)
                http.assert_not_called()

    def test_secrets_never_in_error(self):
        with mock.patch.object(mod.http.client, 'HTTPSConnection', side_effect=RuntimeError('TOKEN=' + TOKEN)):
            with self.assertRaises(mod.Stop) as err:
                mod.single_get(ACCOUNT, TOKEN)
        self.assertEqual(str(err.exception), 'trusted_get_failed')
        self.assertNotIn(TOKEN, str(err.exception))

    def test_no_execution_from_repository_checkout(self):
        with mock.patch.object(mod.os, 'geteuid', return_value=0):
            with mock.patch.object(mod, 'guarded_bytes') as read:
                with self.assertRaises(mod.Stop) as exc:
                    mod.verified_install('b'*40)
                self.assertEqual(str(exc.exception), 'trusted_install_required')
                read.assert_not_called()

    def test_release_identity_preflight(self):
        sanitizer = b'\n'
        operator = b'operator-bytes'
        account_hash = hashlib.sha256(ACCOUNT.encode()).hexdigest()
        meta = { 'schema_version': 1, 'repository':'rozkalnsandris/RPi5_main',
                 'source_sha':'b'*40,'worker':mod.WORKER,
                 'executor_sha256':hashlib.sha256(operator).hexdigest(),
                 'sanitizer_sha256':hashlib.sha256(sanitizer).hexdigest(),
                 'account_sha256':account_hash }
        def fake_reader(path, mode, limit):
            return {mod.ENTRY:operator,mod.SANITIZER:sanitizer,mod.RELEASE:json.dumps(meta).encode()}[path]
        with mock.patch.object(mod.os,'geteuid',return_value=0),\
             mock.patch.object(mod,'__file__',str(mod.ENTRY)),\
             mock.patch.object(mod,'guarded_bytes',side_effect=fake_reader):
            data, pin = mod.verified_install('b'*40)
            self.assertEqual(data,sanitizer)
            self.assertEqual(pin,account_hash)
            with self.assertRaises(mod.Stop):
                mod.verified_install('c'*40)
            meta['executor_sha256']='0'*64
            with self.assertRaises(mod.Stop):
                mod.verified_install('b'*40)

    def test_credentials_fixed_worker_and_account(self):
        fingerprint=hashlib.sha256(ACCOUNT.encode()).hexdigest()
        fake={'worker':mod.WORKER,'account_id':ACCOUNT,'api_token':TOKEN}
        with mock.patch.object(mod,'guarded_bytes',return_value=json.dumps(fake).encode()):
            self.assertEqual(mod.checked_credential(fingerprint),(ACCOUNT,TOKEN))
            with self.assertRaises(mod.Stop):
                mod.checked_credential('0'*64)
            fake['worker']='other'
        with mock.patch.object(mod,'guarded_bytes',return_value=json.dumps(fake).encode()):
            with self.assertRaises(mod.Stop):
                mod.checked_credential(fingerprint)

    def test_run_once_sanitizes_before_output(self):
        payload={'success':True,'result':{'logpush':False,'secret':'DO_NOT_ECHO'}}
        sanitized_code=b"def sanitize_settings(payload):\n return {'verified_get':True,'logpush':payload['result']['logpush']}\n"
        with mock.patch.object(mod,'verified_install',return_value=(sanitized_code, '0'*64)),\
             mock.patch.object(mod,'checked_credential',return_value=(ACCOUNT,TOKEN)),\
             mock.patch.object(mod,'single_get',return_value=payload) as get:
            out=mod.run_once('b'*40)
        get.assert_called_once_with(ACCOUNT,TOKEN)
        self.assertEqual(out,{'verified_get':True,'logpush':False})
        self.assertNotIn('DO_NOT_ECHO',json.dumps(out))

    def test_cli_confirm_fails_before_trusted_access(self):
        with mock.patch.object(mod,'run_once') as run, mock.patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(mod.main(['--expected-main','b'*40,'--confirm','BAD']),2)
        run.assert_not_called()

    def test_existing_source_still_only_sanitizes(self):
        c = json.loads(CONTRACT.read_text('utf-8'))
        self.assertEqual(c['api']['method'], 'GET')
        self.assertEqual(c['api']['max_requests_per_invocation'], 1)
        self.assertEqual(c['api']['max_response_bytes'],mod.MAX_REPLY)
        self.assertEqual(c['api']['max_retries'], 0)


if __name__ == '__main__':
    unittest.main()
