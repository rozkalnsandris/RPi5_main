"""Focused isolated tests for the source-only Coloring Pages sitemap publisher.

All files and locks are in TemporaryDirectory. Never touch LIVE RPi5 paths.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/bin/coloring-pages-sitemap-publish"
VENDOR_PATH = ROOT / "ops/vendor/coloring-pages-sitemap"
loader = importlib.machinery.SourceFileLoader("coloring_sitemap_operator", str(MODULE_PATH))
mod = loader.load_module()


def record(activity_id):
    path = "/media/" + activity_id
    return {
        "id": activity_id,
        "title": "Malvorlage",
        "thumb": path + "/thumb.webp",
        "preview": path + "/preview.webp",
        "print": path + "/print.png",
    }


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / "public"
        self.public.mkdir()
        self.ingest = self.root / "state/drive-ingest"
        self.ingest.mkdir(parents=True)
        self.lock = self.ingest / ".lock"
        self.lock.touch()
        self.lock.chmod(0o600)
        self.generator = self.root / "trusted-generator"
        shutil.copyfile(VENDOR_PATH, self.generator)
        self.generator.chmod(0o644)
        self.paths = mod.Paths(self.public, self.lock, self.generator)
        self.uid = os.getuid()
        self.gid = os.getgid()
        self.records = [record("1234567"), record("7654321")]
        self.write_catalogue()

    def write_catalogue(self, records=None):
        self.records = self.records if records is None else records
        self.paths.catalog.write_text(json.dumps(self.records), encoding="utf-8")
        self.paths.catalog.chmod(0o644)

    @property
    def catalog_sha(self):
        return hashlib.sha256(self.paths.catalog.read_bytes()).hexdigest()

    def run_check(self, **kwargs):
        return self.operate(False, **kwargs)

    def run_apply(self, **kwargs):
        return self.operate(True, **kwargs)

    def operate(self, apply, expected_catalog=None, expected_prior=None, verify_http=None):
        return mod.process(
            self.paths, apply=apply,
            expected_catalog=expected_catalog,
            expected_prior=expected_prior,
            uid=self.uid, gid=self.gid,
            generator_uid=self.uid, generator_gid=self.gid,
            generator_mode=0o644,
            verify_http=(lambda _: None) if verify_http is None else verify_http,
        )

    def test_pinned_vendor_blob_is_exact_upstream(self):
        data = VENDOR_PATH.read_bytes()
        self.assertEqual(mod.generator_blob(data), mod.GENERATOR_GIT_BLOB)
        self.assertEqual(mod.GENERATOR_GIT_BLOB,
                         "5644c8fd366c0c57f6339fddd163c5091ea134c5")

    def test_read_only_preflight_creates_nothing(self):
        result = self.run_check()
        self.assertEqual(result["result"], "CHECK_PASS")
        self.assertEqual(result["urls"], 4)
        self.assertEqual(result["previous_sha256"], "absent")
        self.assertFalse(result["mutation_started"])
        self.assertFalse(self.paths.sitemap.exists())
        self.assertFalse(self.paths.stage.exists())

    def test_exact_apply_generates_and_verifies_immutable_xml(self):
        called = []
        result = self.run_apply(expected_catalog=self.catalog_sha,
                                expected_prior="absent", verify_http=called.append)
        self.assertEqual(result["result"], "PUBLISH_PASS")
        self.assertEqual(result["urls"], 4)
        self.assertTrue(result["mutation_started"])
        self.assertEqual(called, [self.paths.sitemap.read_bytes()])
        self.assertEqual(stat.S_IMODE(self.paths.sitemap.stat().st_mode), 0o644)
        self.assertFalse(self.paths.stage.exists())
        self.assertIn(b"<urlset", self.paths.sitemap.read_bytes())

    def test_exact_current_is_noop_without_staging(self):
        first = self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent")
        second = self.run_apply(expected_catalog=self.catalog_sha,
                                expected_prior=first["sitemap_sha256"])
        self.assertEqual(second["result"], "NO_OP_CURRENT")
        self.assertFalse(second["mutation_started"])
        self.assertFalse(self.paths.stage.exists())

    def test_changed_catalog_can_update_with_bound_prior_sitemap(self):
        first = self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent")
        self.write_catalogue([record("7777777")])
        second = self.run_apply(expected_catalog=self.catalog_sha,
                                expected_prior=first["sitemap_sha256"])
        self.assertEqual(second["urls"], 3)
        self.assertNotEqual(second["sitemap_sha256"], first["sitemap_sha256"])
        self.assertIn(b"7777777", self.paths.sitemap.read_bytes())

    def test_apply_requires_exact_expected_values(self):
        with self.assertRaisesRegex(mod.Block, "apply requires"):
            self.run_apply()
        with self.assertRaisesRegex(mod.Block, "expected catalogue SHA-256 invalid"):
            self.run_apply(expected_catalog="bad", expected_prior="absent")
        with self.assertRaisesRegex(mod.Block, "expected prior sitemap SHA-256 invalid"):
            self.run_apply(expected_catalog=self.catalog_sha, expected_prior="unexpected")
        self.assertFalse(self.paths.stage.exists())

    def test_stale_catalogue_hash_blocks_before_mutation(self):
        with self.assertRaisesRegex(mod.Block, "catalogue snapshot drift"):
            self.run_apply(expected_catalog="0" * 64, expected_prior="absent")
        self.assertFalse(self.paths.stage.exists())

    def test_existing_target_requires_exact_previous_digest(self):
        self.paths.sitemap.write_bytes(b"older sitemap")
        self.paths.sitemap.chmod(0o644)
        with self.assertRaisesRegex(mod.Block, "prior sitemap state drift"):
            self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent")
        self.assertEqual(self.paths.sitemap.read_bytes(), b"older sitemap")
        self.assertFalse(self.paths.stage.exists())

    def test_external_process_lock_conflict_fails_before_mutation(self):
        fd = os.open(self.lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(mod.Block, "Drive ingest lock is busy"):
                self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent")
        finally:
            os.close(fd)
        self.assertFalse(self.paths.stage.exists())

    def test_existing_stage_requires_manual_review(self):
        self.paths.stage.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(mod.Block, "staged sitemap already exists"):
            self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent")
        self.assertEqual(self.paths.stage.read_text(), "unexpected")

    def test_symlink_catalogue_rejected(self):
        other = self.root / "external_catalogue"
        other.write_text(json.dumps(self.records), encoding="utf-8")
        self.paths.catalog.unlink()
        self.paths.catalog.symlink_to(other)
        with self.assertRaisesRegex(mod.Block, "metadata or type invalid"):
            self.run_check()

    def test_bad_catalogue_and_duplicate_ids_rejected(self):
        for broken in ([record("1234567"), record("1234567")],
                       [{"id": "bad&name", "title": "X"}], []):
            with self.subTest(broken=broken):
                self.write_catalogue(broken)
                with self.assertRaises(mod.Block):
                    self.run_check()
                self.assertFalse(self.paths.sitemap.exists())
        self.write_catalogue([record("1234567")])

    def test_tampered_generator_rejected(self):
        with self.generator.open("ab") as file:
            file.write(b"\n# changed")
        with self.assertRaisesRegex(mod.Block, "generator pinned Git blob mismatch"):
            self.run_check()

    def test_wrong_lock_mode_rejected(self):
        self.lock.chmod(0o644)
        with self.assertRaisesRegex(mod.Block, "metadata or type invalid"):
            self.run_check()

    def test_changed_catalogue_during_staging_preserves_old_target(self):
        old = b"old published sitemap"
        self.paths.sitemap.write_bytes(old)
        self.paths.sitemap.chmod(0o644)
        before = hashlib.sha256(old).hexdigest()
        original = mod.invoke_generator
        def tamper(generator, catalogue, digest, candidate=None):
            if candidate is not None:
                self.write_catalogue([record("3333333")])
            return original(generator, catalogue, digest, candidate)
        with mock.patch.object(mod, "invoke_generator", side_effect=tamper):
            with self.assertRaises(mod.Block):
                self.run_apply(expected_catalog=self.catalog_sha, expected_prior=before)
        self.assertEqual(self.paths.sitemap.read_bytes(), old)
        self.assertTrue(self.paths.stage.exists())

    def test_post_replace_http_failure_does_not_rollback(self):
        def bad_http(_):
            raise mod.Block("HTTP proof failed")
        with self.assertRaisesRegex(mod.Block, "HTTP proof failed"):
            self.run_apply(expected_catalog=self.catalog_sha, expected_prior="absent",
                           verify_http=bad_http)
        self.assertTrue(self.paths.sitemap.exists())
        self.assertFalse(self.paths.stage.exists())


if __name__ == "__main__":
    unittest.main()
