#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_taxonomy_expansion_apply_v1.py"
spec = importlib.util.spec_from_file_location("taxonomy_expand_1426", SOURCE)
op = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(op)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def topic(ident, label, icon="x", terms=None, kind="evergreen"):
    out = {"id": ident, "label": label, "icon": icon, "kind": kind, "legacy_terms": terms or []}
    if kind == "seasonal":
        out |= {"active_from": "12-01", "active_to": "02-29"}
    return out


def fixtures(tmp: Path, additions=None, links=None, category_additions=None):
    public = tmp / "public"
    state = tmp / "state" / "admin-publish"
    jobs = state / "jobs"
    public.mkdir(parents=True, exist_ok=True)
    jobs.mkdir(parents=True, exist_ok=True)
    categories = {
        "schema": op.CATEGORY_SCHEMA,
        "revision": 4,
        "categories": [
            {"id": "tiere", "label": "Tiere"},
            {"id": "fahrzeuge", "label": "Fahrzeuge"},
            {"id": "jahreszeiten", "label": "Jahreszeiten & Feste"},
        ],
    }
    topics = {
        "schema": op.TOPIC_SCHEMA,
        "revision": 7,
        "topics": [
            topic("winter", "Winter", "❄️", ["winter"], "seasonal"),
            topic("bauernhof", "Bauernhof", "🚜", ["bauernhof"]),
        ],
    }
    link_doc = {
        "schema": op.LINK_SCHEMA,
        "revision": 9,
        "links": [
            {"category": "jahreszeiten", "topic": "winter"},
            {"category": "tiere", "topic": "bauernhof"},
        ],
    }
    paths = {
        "categories": public / "categories.json",
        "topics": public / "topics.json",
        "links": state / "category-topic-links.json",
        "manifest": state / "taxonomy-expansion-approved-v1.json",
        "lock": tmp / "state" / "drive-ingest" / ".lock",
        "jobs": jobs,
    }
    paths["lock"].parent.mkdir(parents=True, exist_ok=True)
    paths["lock"].write_bytes(b"")
    paths["lock"].chmod(0o600)
    paths["categories"].write_bytes(raw(categories)); paths["categories"].chmod(0o644)
    paths["topics"].write_bytes(raw(topics)); paths["topics"].chmod(0o644)
    paths["links"].write_bytes(raw(link_doc)); paths["links"].chmod(0o600)
    if additions is None:
        additions = [topic("haustiere", "Haustiere", "🐾", ["haustier", "hund", "katze"])]
    if links is None:
        links = [{"category": "tiere", "topic": "haustiere"}]
    if category_additions is None:
        category_additions = []
    hashes = {
        "category_sha256": op.sha256(paths["categories"].read_bytes()),
        "topic_sha256": op.sha256(paths["topics"].read_bytes()),
        "links_sha256": op.sha256(paths["links"].read_bytes()),
    }
    revisions = {"category_revision": 4, "topic_revision": 7, "links_revision": 9}
    manifest = {
        "schema": op.SCHEMA,
        "mode": "APPROVED_APPLY",
        "hashes": hashes,
        "revisions": revisions,
        "categories": category_additions,
        "topics": additions,
        "links": links,
    }
    manifest["manifest_sha256"] = op.canonical_digest(manifest)
    paths["manifest"].write_bytes(raw(manifest)); paths["manifest"].chmod(0o600)
    return paths, manifest, topics, link_doc


class Tests(unittest.TestCase):
    def bind(self, paths):
        return mock.patch.multiple(
            op,
            CATEGORIES=paths["categories"],
            TOPICS=paths["topics"],
            LINKS=paths["links"],
            MANIFEST=paths["manifest"],
            LOCK=paths["lock"],
            JOBS=paths["jobs"],
        )

    def rewrite_manifest(self, paths, doc):
        doc["manifest_sha256"] = op.canonical_digest({k: v for k, v in doc.items() if k != "manifest_sha256"})
        paths["manifest"].write_bytes(raw(doc))
        return doc

    def test_plan_is_deterministic_and_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            before_topics = paths["topics"].read_bytes(); before_links = paths["links"].read_bytes()
            with self.bind(paths):
                first = op.public_plan(manifest["manifest_sha256"])
                second = op.public_plan(manifest["manifest_sha256"])
            self.assertEqual(first, second)
            self.assertEqual(first["topic_ids"], ["haustiere"])
            self.assertEqual(first["links"], [["tiere", "haustiere"]])
            self.assertFalse(first["mutation_started"])
            self.assertEqual(paths["topics"].read_bytes(), before_topics)
            self.assertEqual(paths["links"].read_bytes(), before_links)

    def test_multi_topic_apply_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as td:
            additions = [
                topic("haustiere", "Haustiere", "🐾", ["haustier"]),
                topic("autos", "Autos", "🚗", ["auto"]),
            ]
            links = [
                {"category": "tiere", "topic": "haustiere"},
                {"category": "fahrzeuge", "topic": "autos"},
            ]
            paths, manifest, old_topics, old_links = fixtures(Path(td), additions, links)
            with self.bind(paths):
                result = op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["mutation_started"])
            new_topics = json.loads(paths["topics"].read_text())
            new_links = json.loads(paths["links"].read_text())
            self.assertEqual(new_topics["topics"][:len(old_topics["topics"])], old_topics["topics"])
            self.assertEqual(new_topics["revision"], 8)
            self.assertEqual(new_links["revision"], 10)
            for row in old_links["links"]:
                self.assertIn(row, new_links["links"])
            self.assertEqual(paths["topics"].stat().st_mode & 0o777, 0o644)
            self.assertEqual(paths["links"].stat().st_mode & 0o777, 0o600)

    def test_zero_change_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td), [], [], [])
            before_topics = paths["topics"].read_bytes(); before_links = paths["links"].read_bytes()
            with self.bind(paths):
                result = op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(result["status"], "UNCHANGED")
            self.assertFalse(result["mutation_started"])
            self.assertEqual(paths["topics"].read_bytes(), before_topics)
            self.assertEqual(paths["links"].read_bytes(), before_links)

    def test_duplicate_or_existing_topic_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td), [topic("bauernhof", "Duplicate")], [{"category": "tiere", "topic": "bauernhof"}])
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "already exists"):
                op.public_plan(doc["manifest_sha256"])

    def test_unknown_category_and_kind_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td))
            doc = json.loads(paths["manifest"].read_text())
            doc["links"] = [{"category": "unknown", "topic": "haustiere"}]
            doc = self.rewrite_manifest(paths, doc)
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "unknown taxonomy"):
                op.public_plan(doc["manifest_sha256"])
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td), [topic("schnee", "Schnee", "❄️", ["schnee"], "seasonal")], [{"category": "tiere", "topic": "schnee"}])
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "incompatible"):
                op.public_plan(doc["manifest_sha256"])

    def test_existing_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td), [], [{"category": "tiere", "topic": "bauernhof"}])
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "already exists"):
                op.public_plan(doc["manifest_sha256"])

    def test_stale_hash_or_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td))
            doc = json.loads(paths["manifest"].read_text())
            doc["revisions"]["topic_revision"] = 99
            doc = self.rewrite_manifest(paths, doc)
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "stale"):
                op.public_plan(doc["manifest_sha256"])

    def test_invalid_topic_and_duplicate_link_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td))
            doc = json.loads(paths["manifest"].read_text())
            doc["topics"][0].pop("icon")
            doc = self.rewrite_manifest(paths, doc)
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "fields"):
                op.public_plan(doc["manifest_sha256"])
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(Path(td))
            doc = json.loads(paths["manifest"].read_text())
            doc["links"].append(dict(doc["links"][0]))
            doc = self.rewrite_manifest(paths, doc)
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "duplicates"):
                op.public_plan(doc["manifest_sha256"])

    def test_active_job_and_interrupted_stage_block_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            job = paths["jobs"] / "job-a"; job.mkdir(); (job / "job.json").write_bytes(raw({"status": "running"}))
            before = paths["topics"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "active publication"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["topics"].read_bytes(), before)
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            (paths["topics"].parent / ".topics.taxonomy-expansion.orphan.tmp").write_bytes(b"x")
            before = paths["topics"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "interrupted taxonomy staging"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["topics"].read_bytes(), before)

    def test_unsafe_mode_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            paths["links"].chmod(0o644)
            before = paths["topics"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "links mode unsafe"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["topics"].read_bytes(), before)

    def test_third_stage_failure_leaves_evidence_for_manual_review(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            real_stage = op.stage
            calls = 0
            def fail_third(path, prefix, data, mode):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise op.Stop("synthetic third stage failure")
                return real_stage(path, prefix, data, mode)
            with self.bind(paths), mock.patch.object(op, "stage", side_effect=fail_third):
                with self.assertRaisesRegex(op.Stop, "synthetic third stage failure"):
                    op.execute_apply(manifest["manifest_sha256"])
            self.assertTrue(list(paths["categories"].parent.glob(".categories.taxonomy-expansion.*.tmp")))
            self.assertTrue(list(paths["topics"].parent.glob(".topics.taxonomy-expansion.*.tmp")))
            self.assertEqual(json.loads(paths["categories"].read_text())["revision"], 4)
            self.assertEqual(json.loads(paths["topics"].read_text())["revision"], 7)
            self.assertEqual(json.loads(paths["links"].read_text())["revision"], 9)

    def test_category_bundle_can_link_new_and_existing_topics(self):
        with tempfile.TemporaryDirectory() as td:
            additions = [topic("wetter", "Wetter", "🌦️", ["wetter"])]
            category_additions = [{"id": "natur", "label": "Natur & Essen"}]
            links = [
                {"category": "natur", "topic": "wetter"},
                {"category": "natur", "topic": "bauernhof"},
            ]
            paths, manifest, old_topics, old_links = fixtures(
                Path(td), additions, links, category_additions
            )
            old_categories = json.loads(paths["categories"].read_text())
            with self.bind(paths):
                plan = op.public_plan(manifest["manifest_sha256"])
                result = op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(plan["category_ids"], ["natur"])
            self.assertEqual(plan["topic_ids"], ["wetter"])
            self.assertEqual(plan["links"], [["natur", "wetter"], ["natur", "bauernhof"]])
            self.assertEqual(result["status"], "PASS")
            new_categories = json.loads(paths["categories"].read_text())
            new_topics = json.loads(paths["topics"].read_text())
            new_links = json.loads(paths["links"].read_text())
            self.assertEqual(new_categories["categories"][:-1], old_categories["categories"])
            self.assertEqual(new_categories["categories"][-1], {"id": "natur", "label": "Natur & Essen"})
            self.assertEqual(new_categories["revision"], 5)
            self.assertEqual(new_topics["topics"][:len(old_topics["topics"])], old_topics["topics"])
            for row in old_links["links"]:
                self.assertIn(row, new_links["links"])
            self.assertIn({"category": "natur", "topic": "bauernhof"}, new_links["links"])

    def test_existing_or_duplicate_category_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(
                Path(td), [], [], [{"id": "tiere", "label": "Duplicate"}]
            )
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "category already exists"):
                op.public_plan(doc["manifest_sha256"])
        with tempfile.TemporaryDirectory() as td:
            cats = [{"id": "natur", "label": "Natur & Essen"}, {"id": "natur", "label": "Natur"}]
            paths, _, _, _ = fixtures(Path(td), [], [], cats)
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "category already exists|duplicates"):
                op.public_plan(doc["manifest_sha256"])

    def test_existing_topic_link_is_allowed_only_when_new_category_participates(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(
                Path(td), [], [{"category": "natur", "topic": "bauernhof"}],
                [{"id": "natur", "label": "Natur & Essen"}]
            )
            with self.bind(paths):
                plan = op.public_plan(manifest["manifest_sha256"])
            self.assertEqual(plan["links"], [["natur", "bauernhof"]])
        with tempfile.TemporaryDirectory() as td:
            paths, _, _, _ = fixtures(
                Path(td), [], [{"category": "fahrzeuge", "topic": "bauernhof"}], []
            )
            doc = json.loads(paths["manifest"].read_text())
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "must involve"):
                op.public_plan(doc["manifest_sha256"])

    def test_unsafe_category_mode_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(
                Path(td), [], [{"category": "natur", "topic": "bauernhof"}],
                [{"id": "natur", "label": "Natur & Essen"}]
            )
            paths["categories"].chmod(0o600)
            before = paths["categories"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "categories mode unsafe"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["categories"].read_bytes(), before)

    def test_interrupted_category_stage_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths, manifest, _, _ = fixtures(Path(td))
            (paths["categories"].parent / ".categories.taxonomy-expansion.orphan.tmp").write_bytes(b"x")
            before = paths["categories"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop, "interrupted taxonomy staging"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["categories"].read_bytes(), before)

    def test_source_check_is_inert(self):
        with mock.patch("builtins.print") as printed:
            self.assertEqual(op.main(["--check-source"]), 0)
        printed.assert_called_once()
        self.assertNotIn("OWNER-AUTHORIZED", printed.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
