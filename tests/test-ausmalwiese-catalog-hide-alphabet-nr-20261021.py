#!/usr/bin/env python3
"""Offline exact N-R batch hide regression tests."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/ausmalwiese-catalog-hide-alphabet-nr-20261021"
loader = importlib.machinery.SourceFileLoader("hide_nr", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)


def rec(page_id: str, title: str = "Example", category: str = "lernen") -> dict:
    return {
        "id": page_id,
        "title": title,
        "category": category,
        "thumb": f"/media/{page_id}/thumb.webp",
        "preview": f"/media/{page_id}/preview.webp",
        "print": f"/media/{page_id}/print.png",
    }


def xml(ids: list[str], origin: str = "https://ausmalwiese.de") -> bytes:
    urls = [origin + "/", origin + "/kita"]
    urls += [origin + "/detail.html?id=" + item for item in sorted(ids)]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join("  <url><loc>" + url + "</loc></url>\n" for url in urls)
        + "</urlset>\n"
    ).encode()


class ExactBatchHideTests(unittest.TestCase):
    def setUp(self):
        self.other = rec("1111111")
        self.targets = [
            rec(page_id, title, category)
            for page_id, (title, category) in mod.TARGETS.items()
        ]
        self.records = [self.other, *self.targets]
        self.catalog = (json.dumps(self.records, ensure_ascii=False, indent=2) + "\n").encode()
        self.sitemap = xml([item["id"] for item in self.records])

    def test_plan_removes_exact_five_and_preserves_other_record(self):
        cat, site, report = mod.plan(self.catalog, self.sitemap)
        parsed = json.loads(cat)
        self.assertEqual(parsed, [self.other])
        for page_id in mod.TARGETS:
            self.assertNotIn(page_id.encode(), site)
        self.assertEqual(report["entry_count_before"], 6)
        self.assertEqual(report["entry_count_after"], 1)
        self.assertEqual(report["target_ids"], list(mod.TARGETS))
        self.assertEqual(mod.verify_index(site, ["1111111"]), "https://ausmalwiese.de")

    def test_exact_title_and_category_are_required(self):
        bad = list(self.records)
        bad[1] = dict(bad[1], title="Wrong")
        raw = (json.dumps(bad, ensure_ascii=False) + "\n").encode()
        with self.assertRaises(mod.Block):
            mod.plan(raw, self.sitemap)

        bad = list(self.records)
        bad[1] = dict(bad[1], category="lernen")
        raw = (json.dumps(bad, ensure_ascii=False) + "\n").encode()
        with self.assertRaises(mod.Block):
            mod.plan(raw, self.sitemap)

    def test_missing_target_or_sitemap_mismatch_fails(self):
        missing = [self.other, *self.targets[:-1]]
        raw = (json.dumps(missing, ensure_ascii=False) + "\n").encode()
        with self.assertRaises(mod.Block):
            mod.plan(raw, xml([item["id"] for item in missing]))

        broken_site = self.sitemap.replace(
            b"  <url><loc>https://ausmalwiese.de/detail.html?id=5008429</loc></url>\n",
            b"",
        )
        with self.assertRaises(mod.Block):
            mod.plan(self.catalog, broken_site)

    def test_legacy_origin_is_preserved(self):
        site = xml([item["id"] for item in self.records], "https://coloring.rozkalns.net")
        _, after, _ = mod.plan(self.catalog, site)
        self.assertIn(b"https://coloring.rozkalns.net/", after)
        self.assertNotIn(b"https://ausmalwiese.de", after)

    def test_process_check_is_read_only_and_apply_requires_exact_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "public"
            state = root / "state"
            public.mkdir(mode=0o755)
            state.mkdir(mode=0o755)
            lock = state / ".lock"
            lock.write_bytes(b"")
            lock.chmod(0o600)
            (public / "catalog.json").write_bytes(self.catalog)
            (public / "sitemap.xml").write_bytes(self.sitemap)
            (public / "catalog.json").chmod(0o644)
            (public / "sitemap.xml").chmod(0o644)
            uid, gid = os.getuid(), os.getgid()

            checked = mod.process(
                public,
                lock,
                apply=False,
                uid=uid,
                gid=gid,
                verify_http=lambda _c, _s: None,
            )
            self.assertFalse(checked["mutation_started"])
            with self.assertRaises(mod.Block):
                mod.process(
                    public,
                    lock,
                    apply=True,
                    expected_catalog="0" * 64,
                    expected_sitemap=checked["sitemap_sha256"],
                    uid=uid,
                    gid=gid,
                    verify_http=lambda _c, _s: None,
                )

            done = mod.process(
                public,
                lock,
                apply=True,
                expected_catalog=checked["catalog_sha256"],
                expected_sitemap=checked["sitemap_sha256"],
                uid=uid,
                gid=gid,
                verify_http=lambda _c, _s: None,
            )
            self.assertEqual(done["status"], "HIDE_PASS")
            self.assertTrue(done["mutation_started"])
            remaining = json.loads((public / "catalog.json").read_text())
            self.assertEqual(remaining, [self.other])


class InstallerSourceTests(unittest.TestCase):
    def test_installer_pins_exact_new_path_and_blob(self):
        src = (
            ROOT / "scripts/install-ausmalwiese-catalog-hide-alphabet-nr-20261021.py"
        ).read_text()
        self.assertIn(
            'SOURCE_REL = "ops/bin/ausmalwiese-catalog-hide-alphabet-nr-20261021"',
            src,
        )
        self.assertIn(
            'SOURCE_BLOB = "8f7dcc8c4ca9aac584d3775f4c33434c517c34e6"',
            src,
        )
        self.assertIn(
            'DESTINATION = Path("/usr/local/bin/ausmalwiese-catalog-hide-alphabet-nr-20261021")',
            src,
        )
        self.assertIn("O_EXCL", src)
        self.assertIn("no overwrite or repair", src)


if __name__ == "__main__":
    unittest.main()
