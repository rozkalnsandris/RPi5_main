#!/usr/bin/env python3
"""Synthetic SQLite WAL tests; no protected host/database access."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_collect_readback_v1 as m


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "goatcounter.sqlite3"
        self.writer = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.writer.close)
        self.assertEqual(self.writer.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        self.writer.execute("CREATE TABLE sites (cname TEXT, parent INTEGER, settings TEXT)")
        self.replace_settings('{"collect":1,"password":"CANARY_PRIVATE_SECRET"}')
        self.assertTrue(Path(str(self.path) + "-wal").exists())
        self.assertTrue(Path(str(self.path) + "-shm").exists())

    def replace_settings(self, s):
        self.writer.execute("DELETE FROM sites")
        self.writer.execute("INSERT INTO sites VALUES(?,NULL,?)", (m.VHOST, s))

    def test_disabled_and_candidate_status_only(self):
        before = self.writer.execute("SELECT settings FROM sites").fetchone()[0]
        self.assertEqual(m.read_once(self.path), "COLLECT_DISABLED_1")
        self.replace_settings('{"collect":130,"password":"CANARY_PRIVATE_SECRET"}')
        self.assertEqual(m.read_once(self.path), "COLLECT_CANDIDATE_130")
        self.assertNotIn("CANARY_PRIVATE_SECRET", m.read_once(self.path))
        self.assertEqual(before.count("CANARY_PRIVATE_SECRET"), 1)
        self.assertEqual(self.writer.execute("SELECT count(*) FROM sites").fetchone()[0], 1)

    def test_other_collect_masks_never_echoed(self):
        for value in [0, 2, 128, 257, 258, -1]:
            with self.subTest(value=value):
                self.replace_settings(json.dumps({"collect":value,"canary":"PRIVATE"}))
                self.assertEqual(m.read_once(self.path), "STOP_OTHER_COLLECT_MASK")

    def test_invalid_or_duplicate_collect_stops(self):
        for value in ['{"collect":null}', '{"collect":true}', '{"collect":"130"}',
                      '{"collect":130,"collect":1}', '{"collect":130.0}',
                      '{"other":1}', 'not-json']:
            with self.subTest(value=value):
                self.replace_settings(value)
                self.assertIn(m.read_once(self.path), {"STOP_COLLECT", "STOP_DB_READ"})

    def test_wrong_site_and_two_sites_stop(self):
        self.writer.execute("UPDATE sites SET cname='other.invalid'")
        self.assertEqual(m.read_once(self.path), "STOP_SITE")
        self.writer.execute("UPDATE sites SET cname=?", (m.VHOST,))
        self.writer.execute("INSERT INTO sites VALUES(?, NULL, ?)", (m.VHOST, '{"collect":1}'))
        self.assertEqual(m.read_once(self.path), "STOP_SITE")

    def test_missing_sidecar_or_journal_fails_before_connect(self):
        sidecar = Path(str(self.path) + "-shm")
        actual_lexists = os.path.lexists
        with patch.object(m.os.path, "lexists",
                          side_effect=lambda p: False if str(p) == str(sidecar) else actual_lexists(p)):
            with patch.object(m.sqlite3, "connect") as connect:
                self.assertEqual(m.read_once(self.path), "STOP_WAL_SIDECARS")
                connect.assert_not_called()
        with patch.object(m.os.path, "lexists",
                          side_effect=lambda p: True if p.endswith("-journal") else actual_lexists(p)):
            with patch.object(m.sqlite3, "connect") as connect:
                self.assertEqual(m.read_once(self.path), "STOP_WAL_SIDECARS")
                connect.assert_not_called()

    def test_never_create_database_or_follow_symlink(self):
        missing = self.path.parent / "missing" / "goatcounter.sqlite3"
        self.assertEqual(m.read_once(missing), "STOP_DB_READ")
        self.assertFalse(missing.exists())
        symlink_dir = self.path.parent / "other"
        symlink_dir.mkdir()
        symlink = symlink_dir / "goatcounter.sqlite3"
        symlink.symlink_to(self.path)
        with patch.object(m.sqlite3, "connect") as connect:
            self.assertEqual(m.read_once(symlink), "STOP_PATH")
            connect.assert_not_called()

    def test_reject_untrusted_sidecar_metadata(self):
        with patch.object(m, "_meta", side_effect=m.Stop("STOP_PATH")):
            with patch.object(m.sqlite3, "connect") as connect:
                self.assertEqual(m.read_once(self.path), "STOP_PATH")
                connect.assert_not_called()

    def test_connection_has_query_only_pragma(self):
        real = sqlite3.connect
        def connect(*args, **kwargs):
            self.assertIn("mode=ro", args[0])
            self.assertNotIn("immutable=1", args[0])
            return real(*args, **kwargs)
        with patch.object(m.sqlite3, "connect", side_effect=connect):
            self.assertEqual(m.read_once(self.path), "COLLECT_DISABLED_1")

    def test_failing_read_hides_provider_exception(self):
        with patch.object(m.sqlite3, "connect",
                          side_effect=sqlite3.OperationalError("PRIVATE_DB_PATH")):
            self.assertEqual(m.read_once(self.path), "STOP_DB_READ")


if __name__ == "__main__":
    unittest.main()
