#!/usr/bin/env python3
"""Source-only exact-pin and rollout gates for Ausmalwiese sitemap migration."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "ops/contracts/ausmalwiese-sitemap-cutover-v1.json").read_text())
OPERATOR = ROOT / "ops/bin/coloring-pages-sitemap-publish"
GENERATOR = ROOT / "ops/vendor/coloring-pages-sitemap"
INGEST = ROOT / "ops/bin/coloring-pages-drive-ingest"
INSTALLER = ROOT / "scripts/install-coloring-pages-sitemap-publisher-v1.py"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class AusmalwieseSitemapCutoverTests(unittest.TestCase):
    def test_new_origin_and_exact_release_blobs(self):
        c = POLICY["candidate_release"]
        self.assertEqual(POLICY["origin"], "https://ausmalwiese.de")
        self.assertEqual(git_blob(GENERATOR.read_bytes()), c["generator_git_blob"])
        self.assertEqual(git_blob(OPERATOR.read_bytes()), c["publisher_git_blob"])
        self.assertEqual(git_blob(INGEST.read_bytes()), c["drive_ingest_git_blob"])
        self.assertEqual(c["generator_git_blob"], "49c8ba34cf0a4c4ab100463df9adacc4c6e90c2c")
        self.assertNotEqual(c["publisher_git_blob"], POLICY["old_release"]["publisher_git_blob"])

    def test_generator_and_publisher_are_new_origin_only(self):
        generator = GENERATOR.read_text()
        operator = OPERATOR.read_text()
        self.assertIn('ORIGIN = "https://ausmalwiese.de"', generator)
        self.assertIn('ORIGIN = "https://ausmalwiese.de"', operator)
        self.assertNotIn('https://coloring.rozkalns.net', generator)
        self.assertNotIn('https://coloring.rozkalns.net', operator)
        self.assertIn(f'GENERATOR_GIT_BLOB = "{POLICY["candidate_release"]["generator_git_blob"]}"', operator)
        self.assertIn('LOCAL_SITEMAP = "http://127.0.0.1:9191/sitemap.xml"', operator)

    def test_first_install_only_guard_remains_and_is_pinned(self):
        src = INSTALLER.read_text()
        pins = POLICY["candidate_release"]
        self.assertIn("for path in (paths.vendor_dir, paths.generator, paths.operator):", src)
        self.assertIn("require_absent(path)", src)
        self.assertIn('raise InstallerError("install target already exists; first-install-only")', src)
        self.assertIn(f'OPERATOR_REL: "{pins["publisher_git_blob"]}"', src)
        self.assertIn(f'GENERATOR_REL: "{pins["generator_git_blob"]}"', src)

    def test_post_ingest_source_pin_is_aligned_but_activation_remains_gated(self):
        txt = INGEST.read_text()
        pins = POLICY["candidate_release"]
        self.assertIn(f'SITEMAP_OPERATOR_BLOB = "{pins["publisher_git_blob"]}"', txt)
        self.assertIn(f'SITEMAP_GENERATOR_BLOB = "{pins["generator_git_blob"]}"', txt)
        self.assertIn('SITEMAP_ENABLE_MARKER', txt)
        self.assertIn('post-publish-v1.enabled', txt)

    def test_upgrade_not_automatically_activated(self):
        self.assertEqual(POLICY["status"], "SOURCE_ONLY_NO_LIVE_AUTHORITY")
        settings = POLICY["installation_policy"]
        self.assertFalse(settings["upgrade_executor_available"])
        self.assertFalse(settings["auto_install"])
        self.assertEqual(settings["first_install_existing_targets"], "REJECT_ALWAYS_NO_OVERWRITE")
        self.assertTrue(settings["exact_old_release_preflight"])
        self.assertEqual(settings["failure"], "STOP_NO_RETRY_NO_ROLLBACK_NO_CLEANUP")
        self.assertIn("separate_owner_LIVE_sitemap_republication_with_catalogue_SHA_and_existing_sitemap_SHA", POLICY["rollout_gates"])
        for ban in ("LIVE", "MERGE", "Cloudflare", "automatic installed-binary upgrade"):
            self.assertIn(ban, POLICY["exclusions"])


if __name__ == "__main__":
    unittest.main()
