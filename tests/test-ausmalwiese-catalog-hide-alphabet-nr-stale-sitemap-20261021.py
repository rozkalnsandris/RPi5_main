#!/usr/bin/env python3
"""Offline tests for stale-sitemap-safe N-R catalog-only hide."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021"
loader = importlib.machinery.SourceFileLoader("hide_nr_v2", str(SCRIPT))
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


def sitemap(detail_ids: list[str], origin: str = "https://ausmalwiese.de") -> bytes:
    static = [
        origin + "/",
        origin + "/kita",
        *(origin + "/" + route for route in mod.CATEGORY_ROUTES),
    ]
    urls = [*static, *(origin + "/detail.html?id=" + x for x in sorted(detail_ids))]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join("  <url><loc>" + url + "</loc></url>\n" for url in urls)
        + "</urlset>\n"
    ).encode()


class StaleSitemapHideTests(unittest.TestCase):
    def setUp(self):
        self.other = [rec("1111111"), rec("2222222"), rec("3333333")]
        self.targets = [
            rec(page_id, title, category)
            for page_id, (title, category) in mod.TARGETS.items()
        ]
        self.records = [*self.other, *self.targets]
        self.catalog = (
            json.dumps(self.records, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        # Deliberately stale: only a subset of non-target catalog IDs is indexed.
        self.sitemap = sitemap(["1111111", "3333333"])

    def test_plan_removes_exact_five_and_never_changes_sitemap(self):
        cat, site, report = mod.plan(self.catalog, self.sitemap)
        parsed = json.loads(cat)
        self.assertEqual(parsed, self.other)
        self.assertEqual(site, self.sitemap)
        self.assertFalse(report["sitemap_changed"])
        self.assertEqual(report["sitemap_detail_count"], 2)
        self.assertEqual(report["entry_count_before"], 8)
        self.assertEqual(report["entry_count_after"], 3)
        self.assertEqual(report["next_sitemap_sha256"], report["sitemap_sha256"])
        for page_id in mod.TARGETS:
            self.assertNotIn(page_id.encode(), site)

    def test_exact_title_and_category_are_required(self):
        bad = [dict(x) for x in self.records]
        bad[3]["title"] = "Wrong"
        with self.assertRaises(mod.Block):
            mod.plan(
                (json.dumps(bad, ensure_ascii=False) + "\n").encode(),
                self.sitemap,
            )

        bad = [dict(x) for x in self.records]
        bad[3]["category"] = "lernen"
        with self.assertRaises(mod.Block):
            mod.plan(
                (json.dumps(bad, ensure_ascii=False) + "\n").encode(),
                self.sitemap,
            )

    def test_stale_subset_is_allowed_but_target_in_sitemap_is_blocked(self):
        origin, detail_ids = mod.verify_stale_sitemap(
            self.sitemap,
            [x["id"] for x in self.records],
        )
        self.assertEqual(origin, "https://ausmalwiese.de")
        self.assertEqual(detail_ids, ["1111111", "3333333"])

        with self.assertRaisesRegex(mod.Block, "target unexpectedly present"):
            mod.plan(self.catalog, sitemap(["1111111", "5008429"]))

    def test_static_routes_and_catalog_subset_are_fail_closed(self):
        wrong_static = self.sitemap.replace(
            b"https://ausmalwiese.de/alphabet",
            b"https://ausmalwiese.de/wrong",
            1,
        )
        with self.assertRaisesRegex(mod.Block, "static routes mismatch"):
            mod.plan(self.catalog, wrong_static)

        with self.assertRaisesRegex(mod.Block, "absent from catalog"):
            mod.plan(self.catalog, sitemap(["1111111", "9999999"]))

    def test_detail_order_and_duplicates_are_rejected(self):
        raw = sitemap(["1111111", "3333333"])
        raw = raw.replace(
            b"detail.html?id=1111111</loc></url>\n  <url><loc>https://ausmalwiese.de/detail.html?id=3333333",
            b"detail.html?id=3333333</loc></url>\n  <url><loc>https://ausmalwiese.de/detail.html?id=1111111",
            1,
        )
        with self.assertRaisesRegex(mod.Block, "not sorted"):
            mod.plan(self.catalog, raw)

        duplicate = sitemap(["1111111"])
        needle = b"  <url><loc>https://ausmalwiese.de/detail.html?id=1111111</loc></url>\n"
        duplicate = duplicate.replace(b"</urlset>", needle + b"</urlset>")
        with self.assertRaisesRegex(mod.Block, "duplicate"):
            mod.plan(self.catalog, duplicate)

    def test_legacy_origin_with_current_static_routes_is_supported(self):
        legacy = sitemap(["1111111"], "https://coloring.rozkalns.net")
        cat, site, report = mod.plan(self.catalog, legacy)
        self.assertEqual(site, legacy)
        self.assertEqual(report["sitemap_origin"], "https://coloring.rozkalns.net")
        self.assertEqual(json.loads(cat), self.other)

    def test_process_mutates_catalog_only_and_requires_both_exact_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "public"
            state = root / "state"
            public.mkdir(mode=0o755)
            state.mkdir(mode=0o755)
            lock = state / ".lock"
            lock.write_bytes(b"")
            lock.chmod(0o600)
            cpath = public / "catalog.json"
            spath = public / "sitemap.xml"
            cpath.write_bytes(self.catalog)
            spath.write_bytes(self.sitemap)
            cpath.chmod(0o644)
            spath.chmod(0o644)
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
            before_sitemap = spath.read_bytes()

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

            proof = []
            done = mod.process(
                public,
                lock,
                apply=True,
                expected_catalog=checked["catalog_sha256"],
                expected_sitemap=checked["sitemap_sha256"],
                uid=uid,
                gid=gid,
                verify_http=lambda c, s: proof.append((c, s)),
            )
            self.assertEqual(done["status"], "HIDE_PASS")
            self.assertTrue(done["mutation_started"])
            self.assertEqual(spath.read_bytes(), before_sitemap)
            self.assertEqual(proof, [(cpath.read_bytes(), before_sitemap)])
            self.assertEqual(json.loads(cpath.read_text()), self.other)
            self.assertFalse((public / mod.CATALOG_STAGE).exists())


class InstallerSourceTests(unittest.TestCase):
    def test_installer_pins_new_operator_and_new_destination(self):
        src = (
            ROOT
            / "scripts/install-ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021.py"
        ).read_text()
        self.assertIn(
            'SOURCE_REL = "ops/bin/ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021"',
            src,
        )
        self.assertIn(
            'SOURCE_BLOB = "568a9a0bd244c0adf44f3957bb76eb68a3e61007"',
            src,
        )
        self.assertIn(
            'DESTINATION = Path("/usr/local/bin/ausmalwiese-catalog-hide-alphabet-nr-stale-sitemap-20261021")',
            src,
        )
        self.assertIn("O_EXCL", src)
        self.assertIn("no overwrite or repair", src)


if __name__ == "__main__":
    unittest.main()
