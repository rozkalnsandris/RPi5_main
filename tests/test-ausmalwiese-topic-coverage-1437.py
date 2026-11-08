#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TAX_MANIFEST = ROOT / "ops/admin/coloring-pages/taxonomy-apply-1437-v1.json"
CLASS_MANIFEST = ROOT / "ops/admin/coloring-pages/classification-apply-1437-v1.json"

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod

taxop = load_module("taxop_1437", ROOT / "scripts/ausmalwiese_taxonomy_expansion_apply_v1.py")
classop = load_module("classop_1437", ROOT / "scripts/ausmalwiese_catalog_classification_apply_v1.py")
oldtest = load_module("oldtax_fixture_1437", ROOT / "tests/test-ausmalwiese-taxonomy-manifest-materialize-v1.py")

class TopicCoverage1437(unittest.TestCase):
    def setUp(self):
        self.tax = json.loads(TAX_MANIFEST.read_text())
        self.cls = json.loads(CLASS_MANIFEST.read_text())

    def current_taxonomy(self):
        cats = oldtest.baseline_categories()
        topics = oldtest.baseline_topics()
        links = oldtest.baseline_links()
        old_bundle = json.loads((ROOT / "ops/admin/coloring-pages/taxonomy-approved-1395-v1.json").read_text())
        cats = {"schema": cats["schema"], "revision": 2, "categories": cats["categories"] + old_bundle["categories"]}
        topics = {"schema": topics["schema"], "revision": 2, "topics": topics["topics"] + old_bundle["topics"]}
        links = {"schema": links["schema"], "revision": 3, "links": sorted(links["links"] + old_bundle["links"], key=lambda r:(r["category"],r["topic"]))}
        return cats, topics, links

    def test_exact_baseline_and_taxonomy_plan(self):
        cats, topics, links = self.current_taxonomy()
        cr, tr, lr = taxop.canonical_bytes(cats), taxop.canonical_bytes(topics), taxop.canonical_bytes(links)
        self.assertEqual(taxop.sha256(cr), "94d64efc25727ad4d3591be1586485709eca2b350ce5e7b1546d9aea11c0ae16")
        self.assertEqual(taxop.sha256(tr), "804869a4dc44c9761280dc3653524014dcabf74131cfa59805048a275fcf96c4")
        self.assertEqual(taxop.sha256(lr), "8c90863b9dbcd35a76b474712d76ebc50935805dbda785800a713a5496fe7289")
        _, _, catids = taxop.validate_categories(cr)
        _, _, topicidx = taxop.validate_topics(tr)
        _, _, linkpairs = taxop.validate_links(lr, catids, topicidx)
        additions = taxop.validate_manifest(
            self.tax,
            hashes=self.tax["hashes"], revisions=self.tax["revisions"],
            category_ids=catids, topic_index=topicidx, link_pairs=linkpairs,
        )
        self.assertEqual((len(additions[0]),len(additions[1]),len(additions[2])), (1,12,16))
        self.assertIn({"category":"fahrzeuge","topic":"bauernhof"}, additions[2])
        state={"categories":cats,"topics":topics,"links":links,"hashes":self.tax["hashes"],
               "revisions":self.tax["revisions"],"manifest":self.tax,
               "category_additions":additions[0],"topic_additions":additions[1],
               "requested_links":additions[2],"category_ids":catids}
        plan=taxop.build_plan(state)
        self.assertEqual(plan["category_after_sha256"], "01b7f951152c9bcd6ce27a8a29390f2c09025d587d8b7a08476fc1acf96d5468")
        self.assertEqual(plan["topic_after_sha256"], "67c28647b3e2417e505326e89abb167469f55556c162350c32dc8fc17cbada1f")
        self.assertEqual(plan["links_after_sha256"], "9e4b03fa1567fe56112d27a0bb59fe1d9c2f73cfc2b4dae41a89df61cd7c3109")
        self.assertEqual((plan["category_after_revision"],plan["topic_after_revision"],plan["links_after_revision"]), (3,3,4))

    def test_classification_accounts_for_477_and_changes_exactly_86(self):
        decisions=self.cls["review_decisions"]
        self.assertEqual(len(decisions),477)
        self.assertEqual(len({r["id"] for r in decisions}),477)
        changed=[r for r in decisions if r["before"] != r["after"]]
        self.assertEqual(len(changed),86)
        self.assertTrue(all(r["decision"]=="approved" for r in decisions))
        self.assertTrue(all(r["after"]["topics"] for r in decisions))
        self.assertTrue(all(r["before"]["topics"]==[] for r in changed))
        primary={}
        for r in changed:
            primary[r["before"]["categories"][0]]=primary.get(r["before"]["categories"][0],0)+1
        self.assertEqual(primary, {"alphabet":35,"figuren":40,"lernen":8,"fahrzeuge":2,"jahreszeiten":1})
        forbidden={"zuordnen","ausschneiden-kleben","malen-nach-zahlen","labyrinth","muster-fortsetzen","schreibuebung"}
        self.assertFalse(forbidden & {t for r in decisions for t in r["after"]["topics"]})

    def test_classification_is_valid_against_planned_taxonomy(self):
        cats, topics, links = self.current_taxonomy()
        cats["revision"]=3; cats["categories"] += self.tax["categories"]
        topics["revision"]=3; topics["topics"] += self.tax["topics"]
        links["revision"]=4; links["links"]=sorted(links["links"]+self.tax["links"],key=lambda r:(r["category"],r["topic"]))
        cat_ids={r["id"] for r in cats["categories"]}
        topic_ids={r["id"] for r in topics["topics"]}
        pairs={(r["category"],r["topic"]) for r in links["links"]}
        synthetic=[]
        for r in self.cls["review_decisions"]:
            before=r["before"]
            synthetic.append({"id":r["id"],"category":before["categories"][0],"categories":before["categories"],"topics":before["topics"]})
        normalized=classop.validate_manifest(
            self.cls, synthetic, self.cls["hashes"], self.cls["revisions"], cat_ids, topic_ids, pairs
        )
        self.assertEqual(len(normalized),477)
        self.assertEqual(sum(r["before"] != r["after"] for r in normalized),86)
        self.assertEqual(self.cls["hashes"]["category_sha256"], "01b7f951152c9bcd6ce27a8a29390f2c09025d587d8b7a08476fc1acf96d5468")
        self.assertEqual(self.cls["hashes"]["topic_sha256"], "67c28647b3e2417e505326e89abb167469f55556c162350c32dc8fc17cbada1f")
        self.assertEqual(self.cls["hashes"]["links_sha256"], "9e4b03fa1567fe56112d27a0bb59fe1d9c2f73cfc2b4dae41a89df61cd7c3109")
        self.assertEqual(classop.canonical_digest(classop.manifest_digest_payload(self.cls)), "6009c1d8e6798cf3387af2d6f20fcf1dd4f347ea629bc89cb7d1f16d118e08d7")

    def test_exact_corrections_and_subject_topics(self):
        by={r["id"]:r for r in self.cls["review_decisions"]}
        self.assertEqual(by["4683994"]["after"], {"categories":["orte"],"topics":["gebaeude"]})
        self.assertEqual(by["8203063"]["after"]["topics"], ["bauernhof"])
        self.assertEqual(by["3401749"]["after"]["topics"], ["bauernhof"])
        self.assertEqual(by["7924201"]["after"], {"categories":["figuren","orte"],"topics":["maerchen","gebaeude"]})
        self.assertEqual(by["cp-000007"]["after"]["topics"], ["blockwelt"])
        self.assertEqual(by["verkehrsmittel-wege-zuordnen-001"]["after"]["topics"], ["verkehr"])

if __name__ == "__main__":
    unittest.main()
