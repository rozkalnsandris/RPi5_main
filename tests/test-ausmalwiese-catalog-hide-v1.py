#!/usr/bin/env python3
"""Offline one-ID hide regression tests; temp files only, no LIVE connection."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/ausmalwiese-catalog-hide"
loader = importlib.machinery.SourceFileLoader("catalog_hide_v1", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
loader.exec_module(mod)


def rec(id, title="Example", category="lernen"):
    return dict(id=id, title=title, category=category,
                thumb="/media/"+id+"/thumb.webp", preview="/media/"+id+"/preview.webp",
                print="/media/"+id+"/print.png")


def xml(ids, origin="https://ausmalwiese.de"):
    urls = [origin + "/", origin + "/kita"] + [origin + "/detail.html?id="+i for i in sorted(ids)]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join("  <url><loc>" + u + "</loc></url>\n" for u in urls)
            + "</urlset>\n").encode()


class OneIdHide(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.public = self.root / "public"
        self.public.mkdir(mode=0o755)
        state = self.root / "state"
        state.mkdir(mode=0o755)
        self.lock = state / ".lock"
        self.lock.write_bytes(b"")
        self.lock.chmod(0o600)
        self.ids = ["1111111", "9444491", "2222222"]
        self.entries = [rec("1111111"), rec(mod.TARGET, mod.TITLE), rec("2222222")]
        self.cpath = self.public / "catalog.json"
        self.spath = self.public / "sitemap.xml"
        self.write_catalog(self.entries)
        self.spath.write_bytes(xml(self.ids))
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.media = self.public / "media" / mod.TARGET
        self.media.mkdir(parents=True)
        (self.media / "print.png").write_bytes(b"must-not-change")

    def write_catalog(self, items):
        self.cpath.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        self.cpath.chmod(0o644)

    def run_op(self, apply=False, ec=None, es=None, http=None):
        return mod.process(self.public, self.lock, apply=apply,
                           expected_catalog=ec, expected_sitemap=es,
                           uid=self.uid, gid=self.gid,
                           verify_http=(lambda _c, _s: None) if http is None else http)

    def test_check_has_zero_mutations_and_pins_one_identity(self):
        old_c, old_s = self.cpath.read_bytes(), self.spath.read_bytes()
        result = self.run_op()
        self.assertEqual(result["status"], "CHECK_PASS")
        self.assertEqual((result["entry_count_before"], result["entry_count_after"]), (3, 2))
        self.assertFalse(result["mutation_started"])
        self.assertEqual((self.cpath.read_bytes(), self.spath.read_bytes()), (old_c, old_s))
        self.assertFalse((self.public / mod.CATALOG_STAGE).exists())
        self.assertFalse((self.public / mod.SITEMAP_STAGE).exists())

    def test_apply_is_exact_one_id_and_keeps_all_other_bytes_in_sitemap(self):
        pre = self.run_op()
        old_sitemap = self.spath.read_bytes()
        old_media = (self.media / "print.png").read_bytes()
        proof = []
        done = self.run_op(True, pre["catalog_sha256"], pre["sitemap_sha256"],
                           lambda c, s: proof.append((c, s)))
        self.assertEqual(done["status"], "HIDE_PASS")
        self.assertTrue(done["mutation_started"])
        self.assertEqual(len(proof), 1)
        self.assertEqual(proof[0], (self.cpath.read_bytes(), self.spath.read_bytes()))
        remaining = json.loads(self.cpath.read_text(encoding="utf-8"))
        self.assertEqual(remaining, [self.entries[0], self.entries[2]])
        self.assertNotIn(b"9444491", self.spath.read_bytes())
        self.assertEqual(old_sitemap.count(b"9444491"), 1)
        self.assertEqual((self.media / "print.png").read_bytes(), old_media)
        self.assertFalse((self.public / mod.CATALOG_STAGE).exists())
        self.assertFalse((self.public / mod.SITEMAP_STAGE).exists())
        with self.assertRaises(mod.Block):
            self.run_op()

    def test_restrictive_umask_preserves_expected_public_mode(self):
        checked = self.run_op()
        prior = os.umask(0o077)
        try:
            self.run_op(True, checked["catalog_sha256"], checked["sitemap_sha256"])
        finally:
            os.umask(prior)
        self.assertEqual(self.cpath.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.spath.stat().st_mode & 0o777, 0o644)

    def test_legacy_canonical_origin_preserved(self):
        self.spath.write_bytes(xml(self.ids, "https://coloring.rozkalns.net"))
        _, after, _ = mod.plan(self.cpath.read_bytes(), self.spath.read_bytes())
        self.assertIn(b"coloring.rozkalns.net/", after)
        self.assertNotIn(b"ausmalwiese.de", after)

    def test_stale_baselines_and_missing_guards_stop_before_mutation(self):
        old = (self.cpath.read_bytes(), self.spath.read_bytes())
        for ec, es in [(None, None), ("0"*64, mod.digest(old[1])), (mod.digest(old[0]), "f"*64)]:
            with self.subTest(ec=ec, es=es), self.assertRaises(mod.Block):
                self.run_op(True, ec, es)
        self.assertEqual((self.cpath.read_bytes(), self.spath.read_bytes()), old)
        self.assertFalse((self.public / mod.CATALOG_STAGE).exists())

    def test_bad_identity_duplicate_and_invalid_catalog_stop(self):
        for records in ([rec(mod.TARGET, "Wrong title"), rec("1111111")],
                        [rec(mod.TARGET, mod.TITLE), rec(mod.TARGET, mod.TITLE)],
                        [rec("1111111"), rec("2222222")],
                        [rec(mod.TARGET, mod.TITLE, "tiere"), rec("2222222")]):
            with self.subTest(records=records):
                self.write_catalog(records)
                with self.assertRaises(mod.Block):
                    self.run_op()
        self.write_catalog(self.entries)

    def test_unexpected_sitemap_origin_or_extra_url_stop(self):
        for candidate in (xml(self.ids, "https://evil.example"),
                          xml(["1111111", "9444491"]),
                          self.spath.read_bytes().replace(b"</urlset>", b"  <url><loc>https://ausmalwiese.de/x</loc></url>\n</urlset>"),
                          b"<bad />"):
            with self.subTest(candidate=candidate[:30]):
                self.spath.write_bytes(candidate)
                with self.assertRaises(mod.Block):
                    self.run_op()
        self.spath.write_bytes(xml(self.ids))

    def test_existing_stage_lock_conflict_and_symlinks_fail_closed(self):
        check = self.run_op()
        stage = self.public / mod.SITEMAP_STAGE
        stage.write_bytes(b"previous attempt")
        with self.assertRaises(mod.Block):
            self.run_op(True, check["catalog_sha256"], check["sitemap_sha256"])
        self.assertEqual(stage.read_bytes(), b"previous attempt")
        stage.unlink()
        fd = os.open(self.lock, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(mod.Block):
                self.run_op()
        finally:
            os.close(fd)
        old = self.cpath.read_bytes()
        self.cpath.unlink()
        other = self.root / "other"
        other.write_bytes(old)
        self.cpath.symlink_to(other)
        with self.assertRaises(mod.Block):
            self.run_op()

    def test_first_replace_success_second_failure_is_stop_no_rollback(self):
        check = self.run_op()
        old_catalog = self.cpath.read_bytes()
        real_replace = mod.os.replace
        calls = []
        def fail_second(source, target):
            calls.append((source, target))
            if len(calls) == 2:
                raise OSError("injected second replace failure")
            return real_replace(source, target)
        with mock.patch.object(mod.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.run_op(True, check["catalog_sha256"], check["sitemap_sha256"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.cpath.read_bytes(), old_catalog)
        self.assertNotIn(b"9444491", self.spath.read_bytes())
        self.assertTrue((self.public / mod.CATALOG_STAGE).exists())

    def test_postwrite_http_failure_does_not_rollback(self):
        check = self.run_op()
        def fail(_c, _s):
            raise mod.Block("HTTP mismatch")
        with self.assertRaisesRegex(mod.Block, "HTTP mismatch"):
            self.run_op(True, check["catalog_sha256"], check["sitemap_sha256"], fail)
        self.assertNotIn(mod.TARGET, self.cpath.read_text())
        self.assertNotIn(mod.TARGET, self.spath.read_text())


if __name__ == "__main__":
    unittest.main()
