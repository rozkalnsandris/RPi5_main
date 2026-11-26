#!/usr/bin/env python3
"""Exercise the exact embedded successor snapshot with synthetic SQLite only."""
import os
import runpy
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "ops/bin/rpi5-backup"
GENERATOR = runpy.run_path(str(ROOT / "scripts/render-jobscanner-backup.py"))
TEMPLATE = (ROOT / "ops/backup/jobscanner-snapshot.sh.in").read_text(encoding="utf-8")
PRIVATE_FIXTURE = "/srv/fixture/jobscanner/data/jobs.db"
SOURCE = GENERATOR["render"](BASE.read_bytes(), TEMPLATE, PRIVATE_FIXTURE).decode("utf-8")
CODE = SOURCE.split("<<'JOBSCANNER_PY' > \"$dst\"\n", 1)[1].split("\nJOBSCANNER_PY\n", 1)[0]
NAMESPACE = {"__name__": "snapshot_test"}
exec(compile(CODE, "embedded_snapshot", "exec"), NAMESPACE)
snapshot = NAMESPACE["snapshot"]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "jobs.db"
        self.uid, self.gid = os.getuid(), os.getgid()

    def fixture(self, wal=False):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        if wal:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        db.executescript("""
            CREATE TABLE jobs(id TEXT PRIMARY KEY, dedupe_key TEXT, source TEXT,
              profile_id TEXT, review_state TEXT, review_updated_at TEXT,
              salary_note TEXT, source_page_url TEXT);
            CREATE TABLE runs(id INTEGER PRIMARY KEY, profile_id TEXT,
              started_at TEXT, finished_at TEXT);
            CREATE TABLE ui_preferences(key TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE stellenonline_budget(day TEXT PRIMARY KEY, attempts INTEGER);
            CREATE TABLE extra_table(value TEXT);
            INSERT INTO jobs VALUES('1','k','Notion','logistics','applied','t','n','p');
            INSERT INTO runs VALUES(1,'it','a','b');
            INSERT INTO ui_preferences VALUES('filters','{}');
            INSERT INTO stellenonline_budget VALUES('2026-11-26',3);
            INSERT INTO extra_table VALUES('preserve');
        """)
        db.commit()
        for path in self.root.iterdir():
            path.chmod(0o600)
        return db

    def check_copy(self, wal):
        db = self.fixture(wal)
        if wal:
            db.execute("INSERT INTO extra_table VALUES('committed WAL')")
            db.commit()
        old = self.path.read_bytes()
        expected = list(db.iterdump())
        data = snapshot(self.path, self.uid, self.gid)
        self.assertEqual(data[18:20], b"\x01\x01")
        restored = self.root / "restore.sqlite"
        restored.write_bytes(data)
        with closing(sqlite3.connect(restored.as_uri()+"?mode=ro&immutable=1", uri=True)) as copy:
            self.assertEqual(list(copy.iterdump()), expected)
            self.assertEqual(copy.execute("PRAGMA quick_check").fetchone(), ("ok",))
        self.assertEqual(self.path.read_bytes(), old)

    def test_rollback_journal(self):
        self.check_copy(False)

    def test_committed_wal(self):
        self.check_copy(True)

    def test_missing_source(self):
        with self.assertRaises((ValueError, OSError)):
            snapshot(self.path, self.uid, self.gid)

    def test_symlink_and_permissions(self):
        self.fixture()
        link = self.root / "alias.db"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            snapshot(link, self.uid, self.gid)
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            snapshot(self.path, self.uid, self.gid)

    def test_invalid_schema(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE unrelated(x)")
        self.path.chmod(0o600)
        with self.assertRaises(ValueError):
            snapshot(self.path, self.uid, self.gid)

    def test_unsafe_sidecar(self):
        self.fixture()
        (self.root / "jobs.db-wal").symlink_to(self.path)
        with self.assertRaises(ValueError):
            snapshot(self.path, self.uid, self.gid)

    def test_size_limit(self):
        db = self.fixture()
        db.execute("INSERT INTO extra_table VALUES(zeroblob(17000000))")
        db.commit()
        with self.assertRaises(ValueError):
            snapshot(self.path, self.uid, self.gid)

    def test_materializer_rejects_wrong_base_and_unsafe_binding(self):
        with self.assertRaises(ValueError):
            GENERATOR["render"](b"wrong", TEMPLATE, PRIVATE_FIXTURE)
        for path in ("relative/data/jobs.db", "/srv/../data/jobs.db", "/srv/fixture/data/other.db", "/srv/a b/data/jobs.db"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                GENERATOR["render"](BASE.read_bytes(), TEMPLATE, path)

    def test_exact_successor_delta(self):
        subprocess.run(["bash", "-n"], input=SOURCE, text=True, check=True)
        start = SOURCE.index("# Job Scanner: only the active SQLite DB")
        end = SOURCE.index('mkdir -p "$PAYLOAD/backup-metadata"', start)
        original = SOURCE[:start] + SOURCE[end:]
        original = original.replace("V13 (Job Scanner).", "V12.", 1)
        original = original.replace("backup_version=13", "backup_version=12", 1)
        member = GENERATOR["MEMBER"]
        self.assertEqual(original.count(member), 1)
        original = original.replace(member, "", 1)
        self.assertEqual(original, BASE.read_text(encoding="utf-8"))
        self.assertIn("readonly JOBSCANNER_DB=" + PRIVATE_FIXTURE, SOURCE)
        self.assertIn("os.setuid(1000)", CODE)
        self.assertIn("source.backup(target", CODE)
        self.assertLess(SOURCE.index("\njobscanner_snapshot\n"), SOURCE.index("tar --numeric-owner"))


if __name__ == "__main__":
    unittest.main()
