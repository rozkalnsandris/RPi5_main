#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_taxonomy_manifest_materialize_1437_v1.py"
spec = importlib.util.spec_from_file_location("taxonomy_materialize_1437", SOURCE)
mat = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mat)

oldspec = importlib.util.spec_from_file_location(
    "taxonomy_materialize_old_fixture", ROOT / "tests/test-ausmalwiese-taxonomy-manifest-materialize-v1.py"
)
old = importlib.util.module_from_spec(oldspec); assert oldspec and oldspec.loader; oldspec.loader.exec_module(old)

def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()

def current_taxonomy():
    cats = old.baseline_categories()
    topics = old.baseline_topics()
    links = old.baseline_links()
    bundle = json.loads((ROOT / "ops/admin/coloring-pages/taxonomy-approved-1395-v1.json").read_text())
    cats = {"schema":cats["schema"],"revision":2,"categories":cats["categories"]+bundle["categories"]}
    topics = {"schema":topics["schema"],"revision":2,"topics":topics["topics"]+bundle["topics"]}
    links = {"schema":links["schema"],"revision":3,"links":sorted(links["links"]+bundle["links"],key=lambda r:(r["category"],r["topic"]))}
    return cats, topics, links

def predecessor_bytes():
    cats = old.baseline_categories()
    topics = old.baseline_topics()
    links = old.baseline_links()
    bundle = json.loads((ROOT / "ops/admin/coloring-pages/taxonomy-approved-1395-v1.json").read_text())
    manifest = {
        "schema": mat.CONSUMER.SCHEMA,
        "mode": "APPROVED_APPLY",
        "hashes": {
            "category_sha256": hashlib.sha256(raw(cats)).hexdigest(),
            "topic_sha256": hashlib.sha256(raw(topics)).hexdigest(),
            "links_sha256": hashlib.sha256(raw(links)).hexdigest(),
        },
        "revisions": {
            "category_revision": cats["revision"],
            "topic_revision": topics["revision"],
            "links_revision": links["revision"],
        },
        "categories": bundle["categories"],
        "topics": bundle["topics"],
        "links": bundle["links"],
    }
    manifest["manifest_sha256"] = mat.CONSUMER.canonical_digest(manifest)
    return raw(manifest)


def fixture(root: Path):
    public=root/"public"; state=root/"state"/"admin-publish"; jobs=state/"jobs"
    public.mkdir(parents=True); jobs.mkdir(parents=True)
    paths={
      "categories":public/"categories.json",
      "topics":public/"topics.json",
      "links":state/"category-topic-links.json",
      "manifest":state/"taxonomy-expansion-approved-v1.json",
      "lock":root/"state"/"drive-ingest"/".lock",
      "jobs":jobs,
    }
    paths["lock"].parent.mkdir(parents=True)
    paths["lock"].write_bytes(b""); paths["lock"].chmod(0o600)
    cats,topics,links=current_taxonomy()
    paths["categories"].write_bytes(raw(cats)); paths["categories"].chmod(0o644)
    paths["topics"].write_bytes(raw(topics)); paths["topics"].chmod(0o644)
    paths["links"].write_bytes(raw(links)); paths["links"].chmod(0o600)
    return paths

class Tests(unittest.TestCase):
    def bind(self, paths, source=None):
        values={
          "CATEGORIES":paths["categories"],"TOPICS":paths["topics"],"LINKS":paths["links"],
          "MANIFEST":paths["manifest"],"LOCK":paths["lock"],"JOBS":paths["jobs"],
        }
        if source is not None:
            values["SOURCE_MANIFEST"]=source
        return mock.patch.multiple(mat, **values)

    def test_exact_plan(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            with self.bind(paths):
                result=mat.plan()
            self.assertEqual(result["manifest_sha256"], mat.EXPECTED_MANIFEST_SHA256)
            self.assertEqual(result["category_ids"], ["orte"])
            self.assertEqual(len(result["topic_ids"]), 12)
            self.assertEqual(len(result["links"]), 16)
            self.assertEqual(result["category_after_sha256"], "01b7f951152c9bcd6ce27a8a29390f2c09025d587d8b7a08476fc1acf96d5468")
            self.assertEqual(result["topic_after_sha256"], "67c28647b3e2417e505326e89abb167469f55556c162350c32dc8fc17cbada1f")
            self.assertEqual(result["links_after_sha256"], "9e4b03fa1567fe56112d27a0bb59fe1d9c2f73cfc2b4dae41a89df61cd7c3109")
            self.assertEqual((result["category_after_revision"],result["topic_after_revision"],result["links_after_revision"]),(3,3,4))
            self.assertFalse(paths["manifest"].exists())

    def test_exact_replaceable_predecessor_identity(self):
        predecessor = predecessor_bytes()
        doc = json.loads(predecessor)
        self.assertEqual(
            hashlib.sha256(predecessor).hexdigest(),
            mat.REPLACEABLE_PREDECESSOR_RAW_SHA256,
        )
        self.assertEqual(
            doc["manifest_sha256"],
            mat.REPLACEABLE_PREDECESSOR_MANIFEST_SHA256,
        )
        self.assertEqual(doc["hashes"], mat.REPLACEABLE_PREDECESSOR_HASHES)
        self.assertEqual(doc["revisions"], mat.REPLACEABLE_PREDECESSOR_REVISIONS)

    def test_exact_predecessor_is_replaced_with_1437_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            paths["manifest"].write_bytes(predecessor_bytes())
            paths["manifest"].chmod(0o600)
            with self.bind(paths):
                state = mat.inspect_existing(mat.canonical_bytes(
                    json.loads(mat.SOURCE_MANIFEST.read_text())
                ))
                result = mat.materialize()
            self.assertEqual(state, "REPLACEABLE_PREDECESSOR")
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["mutation_started"])
            final = json.loads(paths["manifest"].read_text())
            self.assertEqual(final["manifest_sha256"], mat.EXPECTED_MANIFEST_SHA256)
            self.assertEqual(paths["manifest"].stat().st_mode & 0o777, 0o600)

    def test_predecessor_semantic_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            doc=json.loads(predecessor_bytes())
            doc["revisions"]["links_revision"]=99
            paths["manifest"].write_bytes(raw(doc))
            paths["manifest"].chmod(0o600)
            with self.bind(paths), self.assertRaisesRegex(mat.Stop,"existing manifest differs"):
                mat.materialize()

    def test_materialize_and_identical_noop(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            with self.bind(paths):
                first=mat.materialize()
                first_bytes=paths["manifest"].read_bytes()
                second=mat.materialize()
            self.assertEqual(first["status"],"PASS")
            self.assertTrue(first["mutation_started"])
            self.assertEqual(second["status"],"UNCHANGED")
            self.assertFalse(second["mutation_started"])
            self.assertEqual(paths["manifest"].read_bytes(), first_bytes)
            self.assertEqual(paths["manifest"].stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(first_bytes)["manifest_sha256"], mat.EXPECTED_MANIFEST_SHA256)

    def test_edited_source_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); paths=fixture(root)
            source=root/"source.json"
            doc=json.loads(mat.SOURCE_MANIFEST.read_text())
            doc["topics"][0]["label"]="Changed"
            source.write_bytes(raw(doc))
            with self.bind(paths,source), self.assertRaisesRegex(mat.CONSUMER.Stop,"digest mismatch"):
                mat.plan()

    def test_stale_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            doc=json.loads(paths["categories"].read_text()); doc["revision"]=99
            paths["categories"].write_bytes(raw(doc))
            with self.bind(paths), self.assertRaisesRegex(mat.CONSUMER.Stop,"source hashes/revisions stale"):
                mat.plan()

    def test_existing_different_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            paths["manifest"].write_bytes(b"{}\n"); paths["manifest"].chmod(0o600)
            with self.bind(paths), self.assertRaisesRegex(mat.Stop,"existing manifest differs"):
                mat.materialize()

    def test_active_job_and_busy_lock_stop(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            job=paths["jobs"]/"job-a"; job.mkdir(); (job/"job.json").write_bytes(raw({"status":"running"}))
            with self.bind(paths), self.assertRaisesRegex(mat.Stop,"active publication job"):
                mat.materialize()
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td)); handle=paths["lock"].open("r+b",buffering=0)
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                with self.bind(paths), self.assertRaisesRegex(mat.Stop,"lock busy"):
                    mat.materialize()
            finally:
                handle.close()

if __name__ == "__main__":
    unittest.main()
