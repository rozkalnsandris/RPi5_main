#!/usr/bin/env python3
"""Offline #1291 managed taxonomy tests: no runtime or RPi5 calls."""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from importlib.machinery import SourceFileLoader

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "ops/bin/coloring-pages-admin-publish"
loader = SourceFileLoader("admin_categories_1291", str(TARGET))
spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


def seed():
    return {"schema": admin.MANAGED_SCHEMA, "revision": 1, "categories": [
        {"id":"tiere","label":"Tiere"}, {"id":"fahrzeuge","label":"Fahrzeuge"},
        {"id":"alphabet","label":"Alphabet"}, {"id":"lernen","label":"Lernen"},
        {"id":"figuren","label":"Figuren & Helden"},
        {"id":"jahreszeiten","label":"Jahreszeiten & Feste"}]}


class CategoriesTests(unittest.TestCase):
    def test_schema_hash_and_unsafe_file(self):
        data = admin.managed_bytes(seed())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "categories.json"
            path.write_bytes(data)
            path.chmod(0o644)
            with patch.object(admin, "MANAGED_PATH", path), patch.object(admin, "owner_ids", return_value=(os.geteuid(),os.getegid())):
                document,digest=admin.read_managed()
                self.assertEqual(document,seed())
                self.assertEqual(digest,hashlib.sha256(data).hexdigest())
                path.chmod(0o666)
                with self.assertRaises(admin.Stop):admin.read_managed()
                path.unlink()
                path.symlink_to(Path(d)/"bad")
                with self.assertRaises(admin.Stop):admin.read_managed()

    def test_invalid_schema_labels_slugs_and_core(self):
        doc=seed()
        bad=[
            dict(doc,revision=True),dict(doc,revision=0),
            dict(doc,categories=doc["categories"][:-1]),
            dict(doc,categories=doc["categories"]+[doc["categories"][0]]),
            dict(doc,categories=doc["categories"]+[{"id":"seasonal","label":"No"}]),
            dict(doc,categories=doc["categories"]+[{"id":"berufe","label":"\x00"}]),
            dict(doc,categories=doc["categories"]+[{"id":"berufe","label":" e\u0301 "}])
        ]
        for v in bad:
            with self.subTest(v=v),self.assertRaises(admin.Stop):admin.managed_bytes(v)

    def test_stale_core_and_pending_publications_fail_before_write(self):
        doc=seed()
        doc["categories"].append({"id":"berufe","label":"Berufe"})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"categories.json"
            data=admin.managed_bytes(doc)
            path.write_bytes(data);path.chmod(0o644)
            counts={row["id"]:{"catalog":0,"archive":0} for row in doc["categories"]}
            from contextlib import ExitStack
            with ExitStack() as stack:
                for ctx in (
                    patch.object(admin,"MANAGED_PATH",path),
                    patch.object(admin,"owner_ids",return_value=(os.geteuid(),os.getegid())),
                    patch.object(admin,"managed_verified",return_value=True),
                    patch.object(admin,"managed_counts",return_value=counts),
                    patch.object(admin,"active_jobs",return_value=[])
                ):stack.enter_context(ctx)
                _,digest=admin.read_managed()
                self.assertIsNone(admin.change_managed({"action":"create","id":"test","label":"Test"},"0"*64))
                with self.assertRaises(admin.Stop):
                    admin.change_managed({"action":"delete","id":"tiere","confirm_id":"tiere"},digest)
                with patch.object(admin,"active_jobs",return_value=[{"status":"queued"}]),self.assertRaises(admin.Stop):
                    admin.change_managed({"action":"delete","id":"berufe","confirm_id":"berufe"},digest)
                counts["berufe"]["archive"]=1
                with self.assertRaises(admin.Stop):
                    admin.change_managed({"action":"delete","id":"berufe","confirm_id":"berufe"},digest)
                self.assertEqual(path.read_bytes(),data)

    def test_screen_and_security_gates(self):
        html=(ROOT/"ops/admin/coloring-pages/index.html").read_text(encoding="utf-8")
        server=TARGET.read_text(encoding="utf-8")
        for marker in ('href="#categories" data-nav="categories"', 'data-page="categories"',
                       'id="categoriesStatus" class="categories-status" role="status"',
                       'id="categoriesRows" class="categories-list"',
                       'id="categoriesCreate" class="categories-add"',
                       'category-row', 'category-buttons',
                       'await loadCategories();await loadCatalog();await refreshTaxonomyManagers();',
                       'method:"POST"','If-Match'):
            self.assertIn(marker,html)
        for marker in ('if path == "/api/categories/manage":', 'with acquire_catalog_lock():',
                       'self.send_error_json(412, "categories changed', 'if not self.mutation_guard():'):
            self.assertIn(marker,server)


if __name__ == "__main__":
    unittest.main()
