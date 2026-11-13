#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

projection_path = ROOT / "scripts" / "ausmalwiese_category_topic_public_projection_v1.py"
spec = importlib.util.spec_from_file_location("category_topic_projection_1464", projection_path)
projection = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(projection)

admin_path = ROOT / "ops" / "bin" / "coloring-pages-admin-publish"
loader = SourceFileLoader("admin_publish_1464", str(admin_path))
admin_spec = importlib.util.spec_from_loader(loader.name, loader)
admin = importlib.util.module_from_spec(admin_spec)
loader.exec_module(admin)


def categories_doc(extra=None):
    rows = [
        {"id": "tiere", "label": "Tiere"},
        {"id": "lernen", "label": "Lernen"},
        {"id": "jahreszeiten", "label": "Jahreszeiten & Feste"},
    ]
    if extra:
        rows.extend(extra)
    return {"schema": projection.CONSUMER.CATEGORY_SCHEMA, "revision": 2, "categories": rows}


def topics_doc(extra=None):
    rows = [
        {"id": "bauernhof", "label": "Bauernhof", "icon": "B", "kind": "evergreen", "legacy_terms": []},
        {
            "id": "weihnachten", "label": "Weihnachten", "icon": "W", "kind": "seasonal",
            "legacy_terms": [], "active_from": "11-01", "active_to": "01-10",
        },
    ]
    if extra:
        rows.extend(extra)
    return {"schema": projection.CONSUMER.TOPIC_SCHEMA, "revision": 3, "topics": rows}


def links_doc(rows=None, revision=4):
    return {
        "schema": projection.CONSUMER.LINK_SCHEMA,
        "revision": revision,
        "links": rows if rows is not None else [
            {"category": "jahreszeiten", "topic": "weihnachten"},
            {"category": "tiere", "topic": "bauernhof"},
        ],
    }


def raw(doc):
    return projection.CONSUMER.canonical_bytes(doc)


class ProjectionContractTests(unittest.TestCase):
    def test_projection_is_deterministic_and_public_safe(self):
        doc, data = projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(links_doc()))
        self.assertEqual(doc["schema"], projection.PUBLIC_SCHEMA)
        self.assertEqual(doc["revision"], 4)
        self.assertEqual(doc["category_revision"], 2)
        self.assertEqual(doc["topic_revision"], 3)
        self.assertEqual(doc["links"], links_doc()["links"])
        self.assertEqual(data, projection.projection_bytes(doc))
        self.assertEqual(doc["category_sha256"], hashlib.sha256(raw(categories_doc())).hexdigest())
        self.assertEqual(doc["topic_sha256"], hashlib.sha256(raw(topics_doc())).hexdigest())
        self.assertEqual(doc["source_links_sha256"], hashlib.sha256(raw(links_doc())).hexdigest())
        serialized = data.decode("utf-8")
        for forbidden in ("legacy_terms", "active_from", "active_to", '"label"', '"icon"', "admin-publish", "/srv/"):
            self.assertNotIn(forbidden, serialized)

    def test_zero_links_and_one_topic_in_multiple_categories(self):
        empty, _ = projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(links_doc([], 1)))
        self.assertEqual(empty["links"], [])

        multi = links_doc([
            {"category": "lernen", "topic": "bauernhof"},
            {"category": "tiere", "topic": "bauernhof"},
        ], 5)
        doc, _ = projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(multi))
        self.assertEqual(len(doc["links"]), 2)
        self.assertEqual({row["topic"] for row in doc["links"]}, {"bauernhof"})

    def test_unknown_and_kind_incompatible_links_fail_closed(self):
        unknown = links_doc([{"category": "tiere", "topic": "missing"}])
        with self.assertRaises(projection.CONSUMER.Stop):
            projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(unknown))

        wrong_kind = links_doc([{"category": "tiere", "topic": "weihnachten"}])
        with self.assertRaises(projection.CONSUMER.Stop):
            projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(wrong_kind))

    def test_new_topic_and_registry_drift_change_projection_binding(self):
        base_doc, base_raw = projection.build_projection(raw(categories_doc()), raw(topics_doc()), raw(links_doc()))
        new_topic = {"id": "wald", "label": "Wald", "icon": "W", "kind": "evergreen", "legacy_terms": []}
        changed_topics = topics_doc([new_topic])
        changed_topics["revision"] = 4
        changed_links = links_doc([
            {"category": "jahreszeiten", "topic": "weihnachten"},
            {"category": "lernen", "topic": "wald"},
            {"category": "tiere", "topic": "bauernhof"},
        ], 5)
        changed_doc, changed_raw = projection.build_projection(
            raw(categories_doc()), raw(changed_topics), raw(changed_links)
        )
        self.assertNotEqual(base_doc["topic_sha256"], changed_doc["topic_sha256"])
        self.assertNotEqual(base_raw, changed_raw)

        renamed = categories_doc()
        renamed["categories"][0]["label"] = "Tiere & Natur"
        renamed["revision"] = 3
        drift_doc, drift_raw = projection.build_projection(raw(renamed), raw(topics_doc()), raw(links_doc()))
        self.assertNotEqual(base_doc["category_sha256"], drift_doc["category_sha256"])
        self.assertNotEqual(base_raw, drift_raw)

    def test_admin_builder_matches_materializer_contract(self):
        cats = categories_doc()
        topics = topics_doc()
        links = links_doc()
        expected_doc, expected_raw = projection.build_projection(raw(cats), raw(topics), raw(links))
        actual_doc, actual_raw = admin.public_links_projection_bytes(cats, topics, links)
        self.assertEqual(actual_doc, expected_doc)
        self.assertEqual(actual_raw, expected_raw)

    def test_plan_is_read_only_and_does_not_seed_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            categories = root / "categories.json"
            topics = root / "topics.json"
            links = root / "category-topic-links.json"
            public_projection = root / "category-topics.json"
            categories.write_bytes(raw(categories_doc())); categories.chmod(0o644)
            topics.write_bytes(raw(topics_doc())); topics.chmod(0o644)
            links.write_bytes(raw(links_doc())); links.chmod(0o600)
            with patch.object(projection, "CATEGORIES", categories), patch.object(
                projection, "TOPICS", topics
            ), patch.object(projection, "LINKS", links), patch.object(
                projection, "PROJECTION", public_projection
            ):
                result = projection.plan()
            self.assertEqual(result["status"], "ABSENT")
            self.assertFalse(public_projection.exists())

    def _runtime_files(self, root, cats, topics, links):
        categories = root / "categories.json"
        topics_path = root / "topics.json"
        links_path = root / "category-topic-links.json"
        public_projection = root / "category-topics.json"
        registry = admin.local_taxonomy_registry(cats, topics)
        categories.write_bytes(admin.managed_bytes(cats)); categories.chmod(0o644)
        topics_path.write_bytes(admin.topics_canonical_bytes(topics)); topics_path.chmod(0o644)
        links_data = admin.links_bytes(links, registry)
        links_path.write_bytes(links_data); links_path.chmod(0o600)
        _, projection_raw = admin.public_links_projection_bytes(cats, topics, links)
        public_projection.write_bytes(projection_raw); public_projection.chmod(0o644)
        return categories, topics_path, links_path, public_projection, registry, links_data

    def test_category_rename_refreshes_projection_binding(self):
        cats, topics, links = categories_doc(), topics_doc(), links_doc()
        with tempfile.TemporaryDirectory() as temp:
            paths = self._runtime_files(Path(temp), cats, topics, links)
            categories, topics_path, links_path, public_projection, registry, _ = paths
            category_sha = registry["category_sha256"]
            snapshot = {
                "enabled": True, "registry_sha256": category_sha,
                "counts": {row["id"]: {"catalog": 0, "archive": 0} for row in cats["categories"]},
            }
            patches = [
                patch.object(admin, "MANAGED_PATH", categories),
                patch.object(admin, "TOPICS_PATH", topics_path),
                patch.object(admin, "LINKS_PATH", links_path),
                patch.object(admin, "PUBLIC_LINKS_PATH", public_projection),
                patch.object(admin, "owner_ids", return_value=(os.geteuid(), os.getegid())),
                patch.object(admin, "managed_snapshot", return_value=snapshot),
                patch.object(admin, "active_jobs", return_value=[]),
                patch.object(admin, "managed_verified", return_value=True),
            ]
            for item in patches: item.start()
            try:
                _, new_sha = admin.change_managed(
                    {"action": "rename", "id": "tiere", "label": "Tiere & Natur"}, category_sha
                )
                projection_doc, _ = admin.read_public_links_projection()
                self.assertEqual(projection_doc["category_revision"], 3)
                self.assertEqual(projection_doc["category_sha256"], new_sha)
                self.assertNotEqual(projection_doc["category_sha256"], category_sha)
            finally:
                for item in reversed(patches): item.stop()

    def test_topic_create_refreshes_projection_binding(self):
        cats, topics, links = categories_doc(), topics_doc(), links_doc()
        with tempfile.TemporaryDirectory() as temp:
            paths = self._runtime_files(Path(temp), cats, topics, links)
            categories, topics_path, links_path, public_projection, registry, _ = paths
            topic_sha = registry["topic_sha256"]
            snapshot = {
                "enabled": True, "registry_sha256": topic_sha,
                "counts": {row["id"]: {"catalog": 0, "archive": 0} for row in topics["topics"]},
            }
            patches = [
                patch.object(admin, "MANAGED_PATH", categories),
                patch.object(admin, "TOPICS_PATH", topics_path),
                patch.object(admin, "LINKS_PATH", links_path),
                patch.object(admin, "PUBLIC_LINKS_PATH", public_projection),
                patch.object(admin, "owner_ids", return_value=(os.geteuid(), os.getegid())),
                patch.object(admin, "topics_snapshot", return_value=snapshot),
                patch.object(admin, "active_jobs", return_value=[]),
                patch.object(admin, "topics_runtime_verified", return_value=True),
            ]
            for item in patches: item.start()
            try:
                new_topic = {
                    "id": "wald", "label": "Wald", "icon": "W",
                    "kind": "evergreen", "legacy_terms": [],
                }
                _, new_sha = admin.change_topics({"action": "create", "topic": new_topic}, topic_sha)
                projection_doc, _ = admin.read_public_links_projection()
                self.assertEqual(projection_doc["topic_revision"], 4)
                self.assertEqual(projection_doc["topic_sha256"], new_sha)
                self.assertNotEqual(projection_doc["topic_sha256"], topic_sha)
            finally:
                for item in reversed(patches): item.stop()

    def test_admin_link_mutation_requires_seed_and_updates_projection(self):
        cats = categories_doc()
        topics = topics_doc()
        links = links_doc([{"category": "tiere", "topic": "bauernhof"}], 1)
        registry = admin.local_taxonomy_registry(cats, topics)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            categories = root / "categories.json"
            topics_path = root / "topics.json"
            links_path = root / "category-topic-links.json"
            public_projection = root / "category-topics.json"
            categories.write_bytes(admin.managed_bytes(cats)); categories.chmod(0o644)
            topics_path.write_bytes(admin.topics_canonical_bytes(topics)); topics_path.chmod(0o644)
            links_data = admin.links_bytes(links, registry)
            links_path.write_bytes(links_data); links_path.chmod(0o600)

            raw_request = {
                "action": "link", "category": "lernen", "topic": "bauernhof",
                "category_sha256": registry["category_sha256"],
                "topic_sha256": registry["topic_sha256"],
            }
            expected_sha = hashlib.sha256(links_data).hexdigest()
            common = [
                patch.object(admin, "MANAGED_PATH", categories),
                patch.object(admin, "TOPICS_PATH", topics_path),
                patch.object(admin, "LINKS_PATH", links_path),
                patch.object(admin, "PUBLIC_LINKS_PATH", public_projection),
                patch.object(admin, "owner_ids", return_value=(os.geteuid(), os.getegid())),
                patch.object(admin, "load_taxonomy", return_value=registry),
                patch.object(admin, "active_jobs", return_value=[]),
            ]
            for item in common:
                item.start()
            try:
                with self.assertRaisesRegex(admin.Stop, "projection"):
                    admin.change_links(raw_request, expected_sha)
                self.assertEqual(links_path.read_bytes(), links_data)

                seed_doc, seed_raw = admin.public_links_projection_bytes(cats, topics, links)
                public_projection.write_bytes(seed_raw); public_projection.chmod(0o644)
                updated, updated_sha = admin.change_links(raw_request, expected_sha)
                self.assertEqual(updated["revision"], 2)
                self.assertEqual(len(updated["links"]), 2)
                projection_doc, projection_raw = admin.read_public_links_projection()
                expected_doc, expected_raw = admin.public_links_projection_bytes(cats, topics, updated)
                self.assertEqual(projection_doc, expected_doc)
                self.assertEqual(projection_raw, expected_raw)
                self.assertEqual(updated_sha, hashlib.sha256(admin.links_bytes(updated, registry)).hexdigest())
                self.assertNotEqual(seed_doc, projection_doc)
            finally:
                for item in reversed(common):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
