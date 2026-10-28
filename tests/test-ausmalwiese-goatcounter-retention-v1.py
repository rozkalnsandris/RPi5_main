#!/usr/bin/env python3
"""Synthetic SQLite and mocked service tests; never contacts the installed DB."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/ausmalwiese_goatcounter_retention_v1.py'
spec = importlib.util.spec_from_file_location('retention', SOURCE)
ret = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ret)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'fixture.sqlite3'
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            con.execute('CREATE TABLE sites(site_id INTEGER PRIMARY KEY, cname TEXT, parent INTEGER, state TEXT, received_data INTEGER, settings TEXT)')
            con.execute('INSERT INTO sites VALUES(1,?,NULL,\'a\',0,?)',
                        (ret.HOST, json.dumps({'collect': 1, 'ignore_ips': '',
                                              'secret': 'synthetic-do-not-output',
                                              'other': {'keep': True}})))
            for table in ret.EMPTY_TABLES:
                con.execute('CREATE TABLE ' + table + '(site_id INTEGER)')
            con.execute('CREATE TABLE users(password TEXT)')
            con.execute('CREATE TABLE api_tokens(token TEXT)')

    def sql(self, query, args=()):
        with contextlib.closing(sqlite3.connect(self.db)) as con, con:
            return con.execute(query, args).fetchall()

    def settings(self):
        return json.loads(self.sql('SELECT settings FROM sites')[0][0])

    def change_settings(self, **changes):
        value = self.settings()
        value.update(changes)
        self.sql('UPDATE sites SET settings=?', (json.dumps(value),))

    def test_readonly_is_byte_identical_and_redacted(self):
        before = self.db.read_bytes()
        result = ret.configure(self.db)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(result['retention_days'], 0)
        self.assertFalse(result['changed'])
        self.assertNotIn('synthetic-do-not-output', json.dumps(result))

    def test_apply_preserves_all_other_settings_and_is_noop_when_set(self):
        before = self.settings()
        self.assertTrue(ret.configure(self.db, True)['changed'])
        self.assertEqual(self.settings(), {**before, 'data_retention': 365})
        self.assertFalse(ret.configure(self.db, True)['changed'])
        self.assertEqual(ret.configure(self.db)['retention_days'], 365)

    def test_explicit_zero_supported(self):
        self.change_settings(data_retention=0)
        self.assertTrue(ret.configure(self.db, True)['changed'])

    def test_custom_or_malformed_retention_rejected(self):
        for value in (-1, 31, 366, 365.0, True, None, '365'):
            with self.subTest(value=value):
                self.change_settings(data_retention=value)
                before = self.db.read_bytes()
                with self.assertRaises(ret.Stop):
                    ret.configure(self.db, True)
                self.assertEqual(before, self.db.read_bytes())

    def test_privacy_settings_drift_rejected(self):
        for collect, ips in [(0, ''), (257, ''), (True, ''), (1, '127.0.0.1'), (1, [])]:
            with self.subTest(collect=collect, ips=ips):
                self.change_settings(collect=collect, ignore_ips=ips)
                with self.assertRaises(ret.Stop):
                    ret.configure(self.db, True)

    def test_site_identity_or_state_drift_rejected(self):
        for field, value in [('cname', 'other.invalid'), ('parent', 1),
                             ('state', 'd'), ('received_data', 1)]:
            with self.subTest(field=field):
                original = self.sql('SELECT ' + field + ' FROM sites')[0][0]
                self.sql('UPDATE sites SET ' + field + '=?', (value,))
                with self.assertRaises(ret.Stop):
                    ret.configure(self.db, True)
                self.sql('UPDATE sites SET ' + field + '=?', (original,))

    def test_extra_site_rejected(self):
        self.sql("INSERT INTO sites VALUES(2,'other.invalid',NULL,'a',0,'{}')")
        with self.assertRaises(ret.Stop):
            ret.configure(self.db, True)

    def test_every_analytics_table_must_be_empty(self):
        for table in ret.EMPTY_TABLES:
            with self.subTest(table=table):
                self.sql('INSERT INTO ' + table + ' VALUES(1)')
                with self.assertRaises(ret.Stop):
                    ret.configure(self.db, True)
                self.sql('DELETE FROM ' + table)

    def test_missing_schema_table_rejected(self):
        self.sql('DROP TABLE hit_counts')
        with self.assertRaises(ret.Stop):
            ret.configure(self.db, True)

    def test_duplicate_json_keys_rejected(self):
        self.sql('UPDATE sites SET settings=?', ('{"collect":1,"collect":257,"ignore_ips":""}',))
        with self.assertRaises(ret.Stop):
            ret.configure(self.db, True)

    def test_invalid_json_rejected_without_change(self):
        self.sql('UPDATE sites SET settings=?', ('invalid',))
        before = self.db.read_bytes()
        with self.assertRaises((ret.Stop, sqlite3.DatabaseError)):
            ret.configure(self.db, True)
        self.assertEqual(before, self.db.read_bytes())

    def test_trigger_with_hidden_write_is_rejected(self):
        self.sql('CREATE TRIGGER surprise AFTER UPDATE ON sites BEGIN INSERT INTO hits VALUES(1); END')
        with self.assertRaises(ret.Stop):
            ret.configure(self.db, True)
        self.assertEqual(self.sql('SELECT count(*) FROM hits'), [(0,)])

    def test_no_database_creation(self):
        for apply in (False, True):
            missing = self.db.parent / 'missing.sqlite3'
            with self.assertRaises(sqlite3.OperationalError):
                ret.configure(missing, apply)
            self.assertFalse(missing.exists())

    def test_guard_failure_before_commit_discards_transaction(self):
        calls = []
        def guard():
            calls.append(True)
            if len(calls) == 2:
                raise ret.Stop()
        with self.assertRaises(ret.Stop):
            ret.configure(self.db, True, guard)
        self.assertNotIn('data_retention', self.settings())

    def test_no_reads_of_user_or_token_tables(self):
        real_connect = sqlite3.connect
        def connect(*args, **kwargs):
            con = real_connect(*args, **kwargs)
            def authorize(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_READ and table in ('users', 'api_tokens'):
                    self.fail('credential table accessed')
                return sqlite3.SQLITE_OK
            con.set_authorizer(authorize)
            return con
        with patch.object(ret.sqlite3, 'connect', side_effect=connect):
            self.assertTrue(ret.configure(self.db, True)['changed'])

    def test_services_require_loaded_inactive_dead_and_pid_zero(self):
        from types import SimpleNamespace
        good = 'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\n'
        with patch.object(ret.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=good)) as run:
            ret.services_stopped()
            self.assertEqual(run.call_count, 2)
        for output in (good.replace('inactive', 'active'), good.replace('MainPID=0', 'MainPID=5'), good.replace('loaded', 'not-found'), good + 'MainPID=0\n'):
            with patch.object(ret.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output)):
                with self.assertRaises(ret.Stop):
                    ret.services_stopped()

    def test_cli_catches_os_errors_without_disclosing_them(self):
        out = io.StringIO()
        with patch.object(ret.socket, 'gethostname', side_effect=OSError('private-error')), contextlib.redirect_stdout(out):
            self.assertEqual(ret.main(['--confirm-read', ret.READ]), 2)
        self.assertNotIn('private-error', out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['stage'], 'PREFLIGHT')

    def test_apply_needs_matching_confirmation_before_access(self):
        for args in (['--apply'], ['--confirm-apply', ret.APPLY]):
            with patch.object(ret.socket, 'gethostname') as hostname, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ret.main(['--confirm-read', ret.READ] + args), 2)
                hostname.assert_not_called()

    def test_filesystem_guards_reject_unsafe_files_and_sidecars(self):
        from types import SimpleNamespace
        uid = 12345
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=uid)
        root = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
        regular = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=uid,
                                  st_nlink=1, st_dev=1, st_ino=5)
        current = [regular]
        def metadata(path):
            if path == ret.DB:
                return current[0]
            return directory if path == ret.DB.parent else root
        with patch.object(Path, 'lstat', metadata), patch.object(Path, 'stat', metadata), patch.object(ret.os.path, 'lexists', return_value=False):
            self.assertEqual(ret.safe_path(ret.DB, uid), (1, 5))
            for overrides in ({'st_mode': stat.S_IFLNK | 0o777},
                              {'st_mode': stat.S_IFREG | 0o644},
                              {'st_nlink': 2}, {'st_uid': 0}):
                current[0] = SimpleNamespace(**{**vars(regular), **overrides})
                with self.assertRaises(ret.Stop):
                    ret.safe_path(ret.DB, uid)
            current[0] = regular
            with patch.object(ret.os.path, 'lexists', return_value=True):
                with self.assertRaises(ret.Stop):
                    ret.safe_path(ret.DB, uid)


if __name__ == '__main__':
    unittest.main()
