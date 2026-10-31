#!/usr/bin/env python3
"""Source-only managed Topics v2 safety regressions (#1294)."""
import hashlib
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/"ops/bin/coloring-pages-admin-publish"
loader=SourceFileLoader("admin_topics_1294",str(TARGET))
spec=spec_from_loader(loader.name,loader)
admin=module_from_spec(spec)
spec.loader.exec_module(admin)


def seed():
    return {"schema":admin.TOPICS_SCHEMA,"revision":1,"topics":[
        {"id":"weihnachten","label":"Weihnachten","icon":"🎄","kind":"seasonal",
         "active_from":"12-01","active_to":"12-31","legacy_terms":["weihnacht"]},
        {"id":"bauernhof","label":"Bauernhof","icon":"🚜","kind":"evergreen",
         "legacy_terms":["hof"]}]}


class TopicTests(unittest.TestCase):
    def test_seed_canonical_sha_and_permissions(self):
        doc=seed();data=admin.topics_canonical_bytes(doc)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"topics.json";path.write_bytes(data)
            with patch.object(admin,"TOPICS_PATH",path),patch.object(
                admin,"owner_ids",return_value=(os.geteuid(),os.getegid())):
                self.assertEqual(admin.read_topics_registry(),(doc,hashlib.sha256(data).hexdigest()))
                path.chmod(0o666)
                with self.assertRaises(admin.Stop):admin.read_topics_registry()
                path.unlink()
                with self.assertRaises(admin.Stop):admin.read_topics_registry()
                path.symlink_to(Path(d)/"missing")
                with self.assertRaises(admin.Stop):admin.read_topics_registry()

    def test_invalid_schema_terms_duplicates_and_dates(self):
        doc=seed()
        invalid=[dict(doc,revision=True),dict(doc,topics=[]),dict(doc,schema="bad"),
            dict(doc,topics=doc["topics"]*2),
            dict(doc,topics=[dict(doc["topics"][0],id="../bad")]),
            dict(doc,topics=[dict(doc["topics"][0],label=" E\u0301 ")]),
            dict(doc,topics=[dict(doc["topics"][0],icon="<svg>")]),
            dict(doc,topics=[dict(doc["topics"][0],active_from="02-30")]),
            dict(doc,topics=[dict(doc["topics"][0],kind="other")]),
            dict(doc,topics=[dict(doc["topics"][0],legacy_terms=["x","x"])])]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(admin.Stop):
                admin.topics_canonical_bytes(item)

    def test_stale_and_referenced_changes_fail_before_write(self):
        doc=seed();counts={"weihnachten":{"catalog":1,"archive":2},
                           "bauernhof":{"catalog":0,"archive":0}}
        snap={"enabled":True,"registry_sha256":"a"*64,"counts":counts}
        with patch.object(admin,"topics_snapshot",return_value=snap),patch.object(
                admin,"read_topics_registry",return_value=(doc,"a"*64)),patch.object(
                admin,"active_jobs",return_value=[]):
            self.assertIsNone(admin.change_topics({"action":"delete","id":"bauernhof",
                                                     "confirm_id":"bauernhof"},"b"*64))
            with self.assertRaises(admin.Stop):
                admin.change_topics({"action":"delete","id":"weihnachten",
                                     "confirm_id":"weihnachten"},"a"*64)
            with self.assertRaises(admin.Stop):
                admin.change_topics({"action":"update","topic":dict(
                    doc["topics"][0],kind="evergreen")},"a"*64)
        self.assertEqual(admin.topic_refs({"topics":["weihnachten","bauernhof"]}),
                         ["weihnachten","bauernhof"])

    def test_pending_job_and_invalid_reference(self):
        doc=seed();snap={"enabled":True,"registry_sha256":"a"*64,
                         "counts":{x["id"]:{"catalog":0,"archive":0} for x in doc["topics"]}}
        with patch.object(admin,"topics_snapshot",return_value=snap),patch.object(
                admin,"active_jobs",return_value=[{"status":"queued"}]):
            with self.assertRaises(admin.Stop):
                admin.change_topics({"action":"create","topic":doc["topics"][0]},"a"*64)
        with self.assertRaises(admin.Stop):
            admin.topic_refs({"topics":["bauernhof","bauernhof"]})

    def test_ui_http_and_lock_contract(self):
        html=(ROOT/"ops/admin/coloring-pages/index.html").read_text()
        source=TARGET.read_text()
        for marker in ('href="#categories" data-nav="categories"','data-page="categories"',
                       'id="managedTopicsPanel"','refreshTaxonomyManagers()',
                       'id="topicsRows"','id="topicsCreate"','topicsDialog',
                       'loadManagedTopics()', 'await loadCategories();await loadCatalog();',
                       'If-Match','role="status" aria-live="polite"'):
            self.assertIn(marker,html)
        self.assertNotIn('data-nav="topics"',html)
        self.assertNotIn('data-page="topics"',html)
        for marker in ('path == "/api/topics/manage"','def handle_topics_manage(self):',
                       'self.headers.get("Origin")','self.headers.get("Sec-Fetch-Site")',
                       'with acquire_catalog_lock():','self.send_error_json(412, "topics changed',
                       '"--topics-sha256"','topics_runtime_ready(registry)',
                       'data != topics_canonical_bytes(registry)'):
            self.assertIn(marker,source)


if __name__=="__main__":
    unittest.main()
