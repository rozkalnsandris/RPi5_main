#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_taxonomy_manifest_materialize_v1.py"
spec = importlib.util.spec_from_file_location("taxonomy_materialize_1434", SOURCE)
mat = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mat)


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def baseline_categories():
    return {
        "schema": mat.CONSUMER.CATEGORY_SCHEMA,
        "revision": 1,
        "categories": [
            {"id": "tiere", "label": "Tiere"},
            {"id": "fahrzeuge", "label": "Fahrzeuge"},
            {"id": "alphabet", "label": "Alphabet"},
            {"id": "lernen", "label": "Lernen"},
            {"id": "figuren", "label": "Figuren & Helden"},
            {"id": "jahreszeiten", "label": "Jahreszeiten & Feste"},
        ],
    }


def baseline_topics():
    return {
        "schema": mat.CONSUMER.TOPIC_SCHEMA,
        "revision": 1,
        "topics": [
            {"id":"winter","label":"Winter","icon":"❄️","kind":"seasonal","active_from":"12-01","active_to":"02-29","legacy_terms":["winter","schnee","schneemann","schneeflocke"]},
            {"id":"fasching","label":"Fasching","icon":"🎭","kind":"seasonal","active_from":"02-01","active_to":"03-15","legacy_terms":["fasching","karneval","clown","kostüm","kostuem"]},
            {"id":"fruehling","label":"Frühling","icon":"🌷","kind":"seasonal","active_from":"03-01","active_to":"05-31","legacy_terms":["frühling","fruehling","blüte","bluete","tulpe"]},
            {"id":"ostern","label":"Ostern","icon":"🐰","kind":"seasonal","active_from":"03-15","active_to":"04-30","legacy_terms":["ostern","osterhase","osterei","ostereier"]},
            {"id":"muttertag","label":"Muttertag","icon":"💐","kind":"seasonal","active_from":"05-01","active_to":"05-15","legacy_terms":["muttertag","mama","mutter"]},
            {"id":"sommer","label":"Sommer","icon":"☀️","kind":"seasonal","active_from":"06-01","active_to":"08-31","legacy_terms":["sommer","sonne","strand","urlaub"]},
            {"id":"halloween","label":"Halloween","icon":"🎃","kind":"seasonal","active_from":"09-15","active_to":"10-31","legacy_terms":["halloween","kürbis","kuerbis","gespenst","geist","hexe","fledermaus","spinne","monster"]},
            {"id":"herbst","label":"Herbst","icon":"🍂","kind":"seasonal","active_from":"09-01","active_to":"11-30","legacy_terms":["herbst","laub","blatt","blätter","blaetter","eichel","kastanie","füllhorn","fuellhorn","ernte"]},
            {"id":"sankt-martin","label":"Sankt Martin","icon":"🏮","kind":"seasonal","active_from":"10-15","active_to":"11-11","legacy_terms":["sankt martin","martinstag","martinsgans","laterne","laternenumzug"]},
            {"id":"advent","label":"Advent","icon":"🕯️","kind":"seasonal","active_from":"11-20","active_to":"12-24","legacy_terms":["advent","adventskranz","kerze","kerzen"]},
            {"id":"nikolaus","label":"Nikolaus","icon":"👢","kind":"seasonal","active_from":"11-20","active_to":"12-06","legacy_terms":["nikolaus","nikolausstiefel","stiefel"]},
            {"id":"weihnachten","label":"Weihnachten","icon":"🎄","kind":"seasonal","active_from":"11-20","active_to":"12-26","legacy_terms":["weihnacht","weihnachtsmann","weihnachtsbaum","tannenbaum","rentier"]},
            {"id":"obst","label":"Obst","icon":"🍎","kind":"evergreen","legacy_terms":["obst","frucht","früchte","fruechte","apfel","äpfel","aepfel","birne","banane","erdbeere","orange","zitrone","kirsche","traube","ananas","melone","pfirsich"]},
            {"id":"gemuese","label":"Gemüse","icon":"🥕","kind":"evergreen","legacy_terms":["gemüse","gemuese","karotte","möhre","moehre","tomate","gurke","paprika","brokkoli","blumenkohl","kartoffel","zwiebel","kürbis","kuerbis"]},
            {"id":"dinosaurier","label":"Dinosaurier","icon":"🦖","kind":"evergreen","legacy_terms":["dinosaurier","dino","t-rex","tyrannosaurus","triceratops","stegosaurus"]},
            {"id":"bauernhof","label":"Bauernhof","icon":"🚜","kind":"evergreen","legacy_terms":["bauernhof","traktor","scheune","kuh","schwein","huhn","hahn","schaf","ziege"]},
            {"id":"weltraum","label":"Weltraum","icon":"🚀","kind":"evergreen","legacy_terms":["weltraum","rakete","astronaut","planet","saturn","mond","ufo","raumfahrt"]},
            {"id":"blumen","label":"Blumen","icon":"🌸","kind":"evergreen","legacy_terms":["blume","blumen","rose","tulpe","sonnenblume","blüte","bluete"]},
            {"id":"meerestiere","label":"Meerestiere","icon":"🐠","kind":"evergreen","legacy_terms":["meer","ozean","fisch","delfin","wal","hai","krake","qualle","seestern","seepferd","meeresschildkröte","meeresschildkroete"]},
            {"id":"sport","label":"Sport","icon":"⚽","kind":"evergreen","legacy_terms":["sport","fußball","fussball","basketball","tennis","volleyball"]},
            {"id":"einhoerner","label":"Einhörner","icon":"🦄","kind":"evergreen","legacy_terms":["einhorn","einhörner","einhoerner"]},
        ],
    }


def baseline_links():
    pairs = []
    for topic in ("winter","fasching","fruehling","ostern","muttertag","sommer","halloween","herbst","sankt-martin","advent","nikolaus","weihnachten"):
        pairs.append({"category":"jahreszeiten","topic":topic})
    for topic in ("dinosaurier","bauernhof","meerestiere"):
        pairs.append({"category":"tiere","topic":topic})
    for topic in ("obst","gemuese","weltraum","blumen","sport"):
        pairs.append({"category":"lernen","topic":topic})
    pairs.append({"category":"figuren","topic":"einhoerner"})
    pairs.sort(key=lambda row: (row["category"], row["topic"]))
    return {"schema": mat.CONSUMER.LINK_SCHEMA, "revision": 2, "links": pairs}


def fixture(root: Path):
    public = root / "public"
    state = root / "state" / "admin-publish"
    jobs = state / "jobs"
    public.mkdir(parents=True)
    jobs.mkdir(parents=True)
    paths = {
        "categories": public / "categories.json",
        "topics": public / "topics.json",
        "links": state / "category-topic-links.json",
        "manifest": state / "taxonomy-expansion-approved-v1.json",
        "lock": root / "state" / "drive-ingest" / ".lock",
        "jobs": jobs,
    }
    paths["lock"].parent.mkdir(parents=True)
    paths["lock"].write_bytes(b"")
    paths["lock"].chmod(0o600)
    paths["categories"].write_bytes(raw(baseline_categories())); paths["categories"].chmod(0o644)
    paths["topics"].write_bytes(raw(baseline_topics())); paths["topics"].chmod(0o644)
    paths["links"].write_bytes(raw(baseline_links())); paths["links"].chmod(0o600)
    return paths


class Tests(unittest.TestCase):
    def bind(self, paths, bundle=None):
        values = {
            "CATEGORIES": paths["categories"],
            "TOPICS": paths["topics"],
            "LINKS": paths["links"],
            "MANIFEST": paths["manifest"],
            "LOCK": paths["lock"],
            "JOBS": paths["jobs"],
        }
        if bundle is not None:
            values["BUNDLE_PATH"] = bundle
        return mock.patch.multiple(mat, **values)

    def test_exact_approved_bundle_and_baseline_plan(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            self.assertEqual(mat.sha256(paths["categories"].read_bytes()), "fe76364e6245b772d21fb080d982dcbb90de420dd2f2a1056c7a1248d7cab635")
            self.assertEqual(mat.sha256(paths["topics"].read_bytes()), "a13d970821e96e86ae8a574417610ae2239178c363bbf83c014c7d8b61d1201a")
            self.assertEqual(mat.sha256(paths["links"].read_bytes()), "7b6320b9ac46d33d28319648769f20bf0f59a11a64aaeadadf4007e8d6f3abc6")
            with self.bind(paths):
                summary = mat.plan()
            self.assertFalse(paths["manifest"].exists())
            self.assertEqual(summary["manifest_sha256"], "6cb9bd42f89ba925239deccf9ce4cec164f386bdca78afe39d0d9942381e5bb6")
            self.assertEqual(summary["category_ids"], ["natur"])
            self.assertEqual(len(summary["topic_ids"]), 12)
            self.assertEqual(len(summary["links"]), 15)
            self.assertEqual(summary["category_after_sha256"], "94d64efc25727ad4d3591be1586485709eca2b350ce5e7b1546d9aea11c0ae16")
            self.assertEqual(summary["topic_after_sha256"], "804869a4dc44c9761280dc3653524014dcabf74131cfa59805048a275fcf96c4")
            self.assertEqual(summary["links_after_sha256"], "8c90863b9dbcd35a76b474712d76ebc50935805dbda785800a713a5496fe7289")
            self.assertEqual((summary["category_after_revision"], summary["topic_after_revision"], summary["links_after_revision"]), (2,2,3))

    def test_stale_registry_rebinds_manifest_without_plan_write(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            doc = json.loads(paths["categories"].read_text())
            doc["categories"][0]["label"] = "Tiere aktuell"
            paths["categories"].write_bytes(raw(doc))
            with self.bind(paths):
                summary = mat.plan()
            self.assertNotEqual(summary["manifest_sha256"], "6cb9bd42f89ba925239deccf9ce4cec164f386bdca78afe39d0d9942381e5bb6")
            self.assertFalse(paths["manifest"].exists())

    def test_edited_source_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); paths = fixture(root)
            bundle = root / "bundle.json"
            doc = json.loads(mat.BUNDLE_PATH.read_text())
            doc["categories"][0]["label"] = "Changed"
            bundle.write_bytes(raw(doc))
            with self.bind(paths, bundle), self.assertRaisesRegex(mat.Stop, "raw digest mismatch"):
                mat.plan()

    def test_existing_taxonomy_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            doc = json.loads(paths["categories"].read_text())
            doc["categories"].append({"id":"natur","label":"Natur & Essen"})
            paths["categories"].write_bytes(raw(doc))
            with self.bind(paths), self.assertRaisesRegex(mat.CONSUMER.Stop, "category already exists"):
                mat.plan()

    def test_materialize_success_and_identical_noop(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            with self.bind(paths):
                first = mat.materialize()
                first_bytes = paths["manifest"].read_bytes()
                second = mat.materialize()
            self.assertEqual(first["status"], "PASS")
            self.assertTrue(first["mutation_started"])
            self.assertEqual(second["status"], "UNCHANGED")
            self.assertFalse(second["mutation_started"])
            self.assertEqual(paths["manifest"].read_bytes(), first_bytes)
            self.assertEqual(paths["manifest"].stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(first_bytes)["manifest_sha256"], "6cb9bd42f89ba925239deccf9ce4cec164f386bdca78afe39d0d9942381e5bb6")

    def test_existing_different_or_unsafe_manifest_stops(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            paths["manifest"].write_bytes(b"{}\n"); paths["manifest"].chmod(0o600)
            with self.bind(paths), self.assertRaisesRegex(mat.Stop, "existing manifest differs"):
                mat.materialize()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); paths = fixture(root)
            other=root/"other"; other.write_bytes(b"x")
            paths["manifest"].symlink_to(other)
            with self.bind(paths), self.assertRaisesRegex(mat.Stop, "symlink unsafe"):
                mat.materialize()

    def test_active_job_and_busy_lock_stop_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            job = paths["jobs"]/"job-a"; job.mkdir(); (job/"job.json").write_bytes(raw({"status":"running"}))
            with self.bind(paths), self.assertRaisesRegex(mat.Stop, "active publication job"):
                mat.materialize()
            self.assertFalse(paths["manifest"].exists())
        with tempfile.TemporaryDirectory() as td:
            paths = fixture(Path(td))
            handle=paths["lock"].open("r+b", buffering=0)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with self.bind(paths), self.assertRaisesRegex(mat.Stop, "lock busy"):
                    mat.materialize()
            finally:
                handle.close()
            self.assertFalse(paths["manifest"].exists())

    def test_interrupted_staging_stops(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            orphan=paths["manifest"].parent/".taxonomy-expansion-approved.materialize.orphan.tmp"
            orphan.write_bytes(b"x")
            with self.bind(paths), self.assertRaisesRegex(mat.Stop, "interrupted taxonomy staging"):
                mat.materialize()
            self.assertFalse(paths["manifest"].exists())

    def test_replace_failure_leaves_stage_and_does_not_retry_or_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(Path(td))
            real_replace=os.replace
            calls=0
            def fail_once(src,dst):
                nonlocal calls
                calls += 1
                raise OSError("synthetic replace failure")
            with self.bind(paths), mock.patch.object(mat.os, "replace", side_effect=fail_once):
                with self.assertRaisesRegex(OSError, "synthetic replace failure"):
                    mat.materialize()
            self.assertEqual(calls, 1)
            self.assertFalse(paths["manifest"].exists())
            self.assertEqual(len(list(paths["manifest"].parent.glob(".taxonomy-expansion-approved.materialize.*.tmp"))), 1)

    def test_source_check_is_inert(self):
        with mock.patch("builtins.print") as printed:
            self.assertEqual(mat.main(["--check-source"]), 0)
        printed.assert_called_once()
        self.assertIn("issue=1434", printed.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
