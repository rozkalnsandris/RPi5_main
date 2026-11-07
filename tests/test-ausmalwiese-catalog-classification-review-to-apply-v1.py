#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_catalog_classification_review_to_apply_v1.py"
spec=importlib.util.spec_from_file_location("review_to_apply_1396",SOURCE)
mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

def sha(ch:str)->str: return ch*64

def review():
    decisions=[
        {"id":"1234567","decision":"approved",
         "before":{"categories":["tiere"],"topics":["hund"]},
         "after":{"categories":["tiere"],"topics":["hund"]},
         "reason":"visual review","confidence":"manual"},
        {"id":"legacy-auto","decision":"approved",
         "before":{"categories":["tiere"],"topics":[]},
         "after":{"categories":["fahrzeuge"],"topics":["autos"]},
         "reason":"visual review","confidence":"manual"},
        {"id":"7654321","decision":"deferred",
         "before":{"categories":["lernen"],"topics":[]},
         "after":{"categories":["lernen"],"topics":[]},
         "reason":"needs taxonomy decision","confidence":"manual"},
    ]
    return {
        "schema":mod.REVIEW_SCHEMA,
        "mode":"DRY_RUN_ONLY",
        "complete_review":True,
        "hashes":{
            "catalog_sha256":sha("a"),"taxonomy_sha256":sha("b"),
            "category_sha256":sha("c"),"topic_sha256":sha("d"),"links_sha256":sha("e")},
        "revisions":{"category_revision":4,"topic_revision":7,"links_revision":9},
        "totals":{"published":3,"missingTopic":2,"proposed":1,"needsReview":1,
                  "approved":2,"rejected":0,"deferred":1,"pending":0,
                  "reviewed":3,"unmatched":1},
        "unmatched_title_terms":[],
        "approved_changes":[copy.deepcopy(decisions[1])],
        "review_decisions":decisions,
    }

class Tests(unittest.TestCase):
    def test_complete_review_converts_deterministically(self):
        source=review()
        one=mod.convert(copy.deepcopy(source))
        two=mod.convert(copy.deepcopy(source))
        self.assertEqual(one,two)
        self.assertEqual(one["schema"],mod.APPLY_SCHEMA)
        self.assertEqual(one["source_review_schema"],mod.REVIEW_SCHEMA)
        self.assertEqual(one["mode"],"APPROVED_APPLY")
        self.assertEqual(one["revisions"],source["revisions"])
        self.assertEqual(one["review_decisions"][1]["id"],"legacy-auto")
        self.assertEqual(one["hashes"],{
            "catalog_sha256":sha("a"),"category_sha256":sha("c"),
            "topic_sha256":sha("d"),"links_sha256":sha("e")})
        digest=one.pop("manifest_sha256")
        self.assertEqual(digest,mod.canonical_digest(one))

    def test_incomplete_review_is_rejected(self):
        source=review(); source["complete_review"]=False
        with self.assertRaisesRegex(mod.Stop,"not complete"):
            mod.convert(source)
        source=review(); source["totals"]["pending"]=1; source["totals"]["reviewed"]=2
        with self.assertRaisesRegex(mod.Stop,"complete review"):
            mod.convert(source)

    def test_pending_decision_is_rejected(self):
        source=review()
        source["review_decisions"][2]["decision"]="pending"
        source["totals"]["deferred"]=0; source["totals"]["pending"]=1; source["totals"]["reviewed"]=2
        with self.assertRaises(mod.Stop):
            mod.convert(source)

    def test_missing_or_invalid_revision_is_rejected(self):
        source=review(); del source["revisions"]["links_revision"]
        with self.assertRaisesRegex(mod.Stop,"revisions"):
            mod.convert(source)
        source=review(); source["revisions"]["topic_revision"]=0
        with self.assertRaisesRegex(mod.Stop,"revision value"):
            mod.convert(source)

    def test_approved_changes_must_match_decisions_exactly(self):
        source=review(); source["approved_changes"]=[]
        with self.assertRaisesRegex(mod.Stop,"approved_changes"):
            mod.convert(source)
        source=review(); source["approved_changes"][0]["reason"]="different"
        with self.assertRaisesRegex(mod.Stop,"approved_changes"):
            mod.convert(source)

    def test_approved_change_requires_topic(self):
        source=review()
        source["review_decisions"][1]["after"]["topics"]=[]
        source["approved_changes"][0]["after"]["topics"]=[]
        with self.assertRaisesRegex(mod.Stop,"assignment invalid"):
            mod.convert(source)

    def test_duplicate_ids_are_rejected(self):
        source=review(); source["review_decisions"][2]["id"]="legacy-auto"
        with self.assertRaisesRegex(mod.Stop,"duplicate"):
            mod.convert(source)

    def test_cli_reads_one_file_and_only_prints_manifest(self):
        source=review()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"review.json"; path.write_text(json.dumps(source),encoding="utf-8")
            with mock.patch("builtins.print") as p:
                self.assertEqual(mod.main(["--review",str(path)]),0)
            payload=json.loads(p.call_args.args[0])
            self.assertEqual(payload["schema"],mod.APPLY_SCHEMA)
            self.assertEqual(payload["review_decisions"][1]["id"],"legacy-auto")

    def test_source_check_is_inert(self):
        with mock.patch("builtins.print") as p:
            self.assertEqual(mod.main(["--check-source"]),0)
        self.assertIn("live=false",p.call_args.args[0])

if __name__=="__main__":
    unittest.main()
