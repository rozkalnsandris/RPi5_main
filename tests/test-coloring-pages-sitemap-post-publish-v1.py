#!/usr/bin/env python3
"""Isolated post-PUBLISH sitemap tests. No LIVE paths are read or changed."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import inspect
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops/bin/coloring-pages-drive-ingest"
loader = importlib.machinery.SourceFileLoader("coloring_post_publish_under_test", str(OPERATOR))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CATALOG = "a" * 64
OLD = "b" * 64
NEW = "c" * 64


def response(result="CHECK_PASS", *, previous=OLD, digest=NEW, catalog=CATALOG,
             urls=137, mutation=False, code=0):
    payload = dict(result=result, previous_sha256=previous, sitemap_sha256=digest,
                   catalog_sha256=catalog, urls=urls, mutation_started=mutation)
    return subprocess.CompletedProcess([], code, "COLORING_SITEMAP " + json.dumps(payload) + "\n", "")


class PostPublishTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.gate = self.root / "post-publish-v1.enabled"
        self.entry = self.root / "publisher"
        self.vendor = self.root / "generator"
        self.stack = mock.patch.multiple(mod, SITEMAP_ENABLE_MARKER=self.gate,
                                         SITEMAP_PUBLISHER=self.entry,
                                         SITEMAP_GENERATOR=self.vendor,
                                         SITEMAP_ROOT_DIRS=())
        self.stack.start()
        self.addCleanup(self.stack.stop)
        ids = mock.patch.object(mod, "_root_ids", return_value=(os.getuid(), os.getgid()))
        ids.start()
        self.addCleanup(ids.stop)
        self.gate.write_bytes(mod.SITEMAP_GATE_BYTES)
        self.gate.chmod(0o444)
        self.entry.write_bytes(b"publisher fixture\n")
        self.entry.chmod(0o755)
        self.vendor.write_bytes(b"generator fixture\n")
        self.vendor.chmod(0o444)
        self.blobs = mock.patch.multiple(
            mod,
            SITEMAP_OPERATOR_BLOB=self.blob(b"publisher fixture\n"),
            SITEMAP_GENERATOR_BLOB=self.blob(b"generator fixture\n"),
        )
        self.blobs.start()
        self.addCleanup(self.blobs.stop)

    @staticmethod
    def blob(raw):
        import hashlib
        return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

    def test_default_disabled_is_inert(self):
        self.gate.unlink()
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("DISABLED", None))
            run.assert_not_called()

    def test_successful_new_ingest_refresh_once_with_exact_guards(self):
        with mock.patch.object(mod.subprocess, "run", side_effect=[
            response(), response("PUBLISH_PASS", mutation=True),
        ]) as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("REFRESHED", None))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], [str(self.entry), "--check"])
        self.assertEqual(run.call_args_list[1].args[0], [
            str(self.entry), "--apply",
            "--expected-catalog-sha256=" + CATALOG,
            "--expected-current-sitemap-sha256=" + OLD,
        ])

    def test_current_sitemap_is_noop(self):
        with mock.patch.object(mod.subprocess, "run", return_value=response(previous=NEW)) as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("CURRENT", None))
            run.assert_called_once()

    def test_already_processed_branch_skips_refresh(self):
        source = inspect.getsource(mod.main)
        self.assertIn('COLORING_PAGES_DRIVE_INGEST=ALREADY_PROCESSED', source)
        early = source.index('COLORING_PAGES_DRIVE_INGEST=ALREADY_PROCESSED')
        refresh = source.index('refresh_sitemap_after_new_ingest()')
        success = source.index('COLORING_PAGES_DRIVE_INGEST=PASS')
        self.assertLess(early, success)
        self.assertLess(success, refresh)
        self.assertIn('return 0', source[early:success])
        self.assertLess(source.index('with acquire_lock():'), refresh)
        self.assertIn('atomic_move_no_replace(receipt_partial, receipt_final)', source[:refresh])

    def test_lock_conflict_is_stale_without_retry(self):
        with mock.patch.object(mod.subprocess, "run", return_value=response(code=2)) as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "CHECK"))
            run.assert_called_once()

    def test_missing_or_untrusted_operator_never_executes(self):
        self.entry.unlink()
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "TRUST"))
            run.assert_not_called()
        self.entry.write_bytes(b"tampered")
        self.entry.chmod(0o755)
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "TRUST"))
            run.assert_not_called()

    def test_unsafe_gate_and_symlink_are_fail_closed(self):
        self.gate.chmod(0o666)
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "GATE"))
            run.assert_not_called()
        self.gate.chmod(0o444)
        self.vendor.unlink()
        self.vendor.symlink_to(self.entry)
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "TRUST"))
            run.assert_not_called()

    def test_invalid_marker_bytes_cannot_enable(self):
        self.gate.write_bytes(b"yes\n")
        with mock.patch.object(mod.subprocess, "run") as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "GATE"))
            run.assert_not_called()

    def test_catalog_and_prior_drift_fail_without_apply(self):
        for bad in [response(catalog="bad"), response(previous="x")]:
            with self.subTest(bad=bad.stdout), mock.patch.object(mod.subprocess, "run", return_value=bad) as run:
                self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "CHECK"))
                run.assert_called_once()

    def test_post_mutation_failure_preserves_ingest_and_does_not_retry(self):
        with mock.patch.object(mod.subprocess, "run", side_effect=[
            response(), response("PUBLISH_PASS", mutation=True, code=2),
        ]) as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "APPLY"))
            self.assertEqual(run.call_count, 2)

    def test_apply_result_drift_is_stale_no_extra_invocation(self):
        with mock.patch.object(mod.subprocess, "run", side_effect=[
            response(), response("PUBLISH_PASS", digest="d"*64, mutation=True),
        ]) as run:
            self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("STALE", "APPLY"))
            self.assertEqual(run.call_count, 2)

    def test_plain_publish_approval_is_not_activation(self):
        self.gate.unlink()
        self.assertNotIn("post-publish-v1.enabled", inspect.getsource(mod.main))
        self.assertEqual(mod.refresh_sitemap_after_new_ingest(), ("DISABLED", None))
        source = OPERATOR.read_text(encoding="utf-8")
        self.assertNotIn("SITEMAP_ENABLE_MARKER.write", source)
        self.assertNotIn("SITEMAP_ENABLE_MARKER.touch", source)
        self.assertNotIn("SITEMAP_ENABLE_MARKER.mkdir", source)

    def test_no_timer_or_background_worker_added(self):
        source = OPERATOR.read_text(encoding="utf-8")
        self.assertNotIn("systemctl", source)
        self.assertNotIn("crontab", source)


if __name__ == "__main__":
    unittest.main()
