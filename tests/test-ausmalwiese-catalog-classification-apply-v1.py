#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_catalog_classification_apply_v1.py"
spec=importlib.util.spec_from_file_location("catalog_apply_1396",SOURCE)
op=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(op)

def raw(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+"\n").encode()

def fixtures(tmp:Path):
    public=tmp/"public"; state=tmp/"state"/"admin-publish"; jobs=state/"jobs"
    public.mkdir(parents=True,exist_ok=True); jobs.mkdir(parents=True,exist_ok=True)
    cats={"schema":op.CATEGORY_SCHEMA,"revision":4,"categories":[
        {"id":"tiere","label":"Tiere"},{"id":"fahrzeuge","label":"Fahrzeuge"}]}
    topics={"schema":op.TOPIC_SCHEMA,"revision":7,"topics":[
        {"id":"hund","label":"Hund","icon":"x","kind":"evergreen","legacy_terms":[]},
        {"id":"autos","label":"Autos","icon":"x","kind":"evergreen","legacy_terms":[]}]}
    links={"schema":op.LINK_SCHEMA,"revision":9,"links":[
        {"category":"fahrzeuge","topic":"autos"},{"category":"tiere","topic":"hund"}]}
    catalog=[
        {"id":"1234567","title":"Hund","category":"tiere","categories":["tiere"],"topics":["hund"],"age":"3-6","difficulty":"easy"},
        {"id":"legacy-auto","title":"Auto","category":"tiere","categories":["tiere"],"topics":["hund"],"age":"3-6","difficulty":"easy"}]
    paths={
        "catalog":public/"catalog.json","categories":public/"categories.json","topics":public/"topics.json",
        "links":state/"category-topic-links.json","manifest":state/"classification-approved-v1.json",
        "lock":tmp/"state"/"drive-ingest"/".lock","jobs":jobs}
    paths["lock"].parent.mkdir(parents=True,exist_ok=True); paths["lock"].write_bytes(b"\0"); paths["lock"].chmod(0o600)
    paths["catalog"].write_bytes(raw(catalog)); paths["catalog"].chmod(0o644)
    paths["categories"].write_bytes(raw(cats)); paths["topics"].write_bytes(raw(topics)); paths["links"].write_bytes(raw(links))
    hashes={"catalog_sha256":op.sha256(paths["catalog"].read_bytes()),"category_sha256":op.sha256(paths["categories"].read_bytes()),
            "topic_sha256":op.sha256(paths["topics"].read_bytes()),"links_sha256":op.sha256(paths["links"].read_bytes())}
    rev={"category_revision":4,"topic_revision":7,"links_revision":9}
    decisions=[
        {"id":"1234567","decision":"approved","before":{"categories":["tiere"],"topics":["hund"]},
         "after":{"categories":["tiere"],"topics":["hund"]},"reason":"visual review","confidence":"manual"},
        {"id":"legacy-auto","decision":"approved","before":{"categories":["tiere"],"topics":["hund"]},
         "after":{"categories":["fahrzeuge"],"topics":["autos"]},"reason":"visual review","confidence":"manual"}]
    manifest={"schema":op.SCHEMA,"source_review_schema":op.REVIEW_SCHEMA,"mode":"APPROVED_APPLY",
              "hashes":hashes,"revisions":rev,"review_decisions":decisions}
    manifest["manifest_sha256"]=op.canonical_digest(manifest)
    paths["manifest"].write_bytes(raw(manifest))
    return paths,manifest,catalog

class Tests(unittest.TestCase):
    def bind(self,paths):
        return mock.patch.multiple(op,CATALOG=paths["catalog"],CATEGORIES=paths["categories"],TOPICS=paths["topics"],
                                   LINKS=paths["links"],MANIFEST=paths["manifest"],LOCK=paths["lock"],JOBS=paths["jobs"])

    def test_plan_is_read_only_and_legacy_id_is_supported(self):
        with tempfile.TemporaryDirectory() as td:
            paths,manifest,_=fixtures(Path(td))
            before=paths["catalog"].read_bytes()
            with self.bind(paths):
                result=op.public_plan(manifest["manifest_sha256"])
            self.assertEqual(result["changed_ids"],["legacy-auto"])
            self.assertEqual(result["changed_count"],1)
            self.assertEqual(paths["catalog"].read_bytes(),before)

    def test_pending_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths,_,_=fixtures(Path(td))
            doc=json.loads(paths["manifest"].read_text())
            doc["review_decisions"][1]["decision"]="pending"
            doc["manifest_sha256"]=op.canonical_digest({k:v for k,v in doc.items() if k!="manifest_sha256"})
            paths["manifest"].write_bytes(raw(doc))
            with self.bind(paths), self.assertRaisesRegex(op.Stop,"pending"):
                op.public_plan(doc["manifest_sha256"])

    def test_registry_hash_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths,manifest,_=fixtures(Path(td))
            paths["categories"].write_bytes(paths["categories"].read_bytes()+b" ")
            with self.bind(paths), self.assertRaisesRegex(op.Stop,"stale"):
                op.public_plan(manifest["manifest_sha256"])

    def test_missing_topic_before_can_be_approved_to_valid_topic(self):
        with tempfile.TemporaryDirectory() as td:
            paths,_,_=fixtures(Path(td))
            catalog=json.loads(paths["catalog"].read_text())
            catalog[1]["topics"]=[]
            paths["catalog"].write_bytes(raw(catalog))
            doc=json.loads(paths["manifest"].read_text())
            doc["hashes"]["catalog_sha256"]=op.sha256(paths["catalog"].read_bytes())
            doc["review_decisions"][1]["before"]={"categories":["tiere"],"topics":[]}
            doc["review_decisions"][1]["after"]={"categories":["fahrzeuge"],"topics":["autos"]}
            doc["manifest_sha256"]=op.canonical_digest({k:v for k,v in doc.items() if k!="manifest_sha256"})
            paths["manifest"].write_bytes(raw(doc))
            with self.bind(paths):
                result=op.public_plan(doc["manifest_sha256"])
            self.assertEqual(result["changed_ids"],["legacy-auto"])

    def test_invalid_topic_link_fails(self):
        with tempfile.TemporaryDirectory() as td:
            paths,_,_=fixtures(Path(td))
            doc=json.loads(paths["manifest"].read_text())
            doc["review_decisions"][1]["after"]={"categories":["tiere"],"topics":["autos"]}
            doc["manifest_sha256"]=op.canonical_digest({k:v for k,v in doc.items() if k!="manifest_sha256"})
            paths["manifest"].write_bytes(raw(doc))
            with self.bind(paths), self.assertRaisesRegex(op.Stop,"not linked"):
                op.public_plan(doc["manifest_sha256"])

    def test_before_state_must_match_current_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            paths,_,_=fixtures(Path(td))
            doc=json.loads(paths["manifest"].read_text())
            doc["review_decisions"][0]["before"]={"categories":["fahrzeuge"],"topics":["autos"]}
            doc["manifest_sha256"]=op.canonical_digest({k:v for k,v in doc.items() if k!="manifest_sha256"})
            paths["manifest"].write_bytes(raw(doc))
            with self.bind(paths), self.assertRaisesRegex(op.Stop,"before-state"):
                op.public_plan(doc["manifest_sha256"])

    def test_apply_is_one_atomic_catalog_replacement_and_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as td:
            paths,manifest,old=fixtures(Path(td))
            with self.bind(paths):
                result=op.execute_apply(manifest["manifest_sha256"])
            self.assertTrue(result["mutation_started"])
            new=json.loads(paths["catalog"].read_text())
            self.assertEqual([x["id"] for x in new],[x["id"] for x in old])
            self.assertEqual(new[1]["category"],"fahrzeuge")
            self.assertEqual(new[1]["categories"],["fahrzeuge"])
            self.assertEqual(new[1]["topics"],["autos"])
            for key in ("title","age","difficulty"):
                self.assertEqual(new[1][key],old[1][key])
            self.assertFalse(list(paths["catalog"].parent.glob(".catalog.classification.*.tmp")))

    def test_active_job_blocks_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            paths,manifest,_=fixtures(Path(td))
            jobdir=paths["jobs"]/"a"; jobdir.mkdir()
            (jobdir/"job.json").write_bytes(raw({"status":"running"}))
            before=paths["catalog"].read_bytes()
            with self.bind(paths), self.assertRaisesRegex(op.Stop,"active publication"):
                op.execute_apply(manifest["manifest_sha256"])
            self.assertEqual(paths["catalog"].read_bytes(),before)

    def test_zero_change_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            paths,_,_=fixtures(Path(td))
            doc=json.loads(paths["manifest"].read_text())
            doc["review_decisions"][1]["decision"]="deferred"
            doc["manifest_sha256"]=op.canonical_digest({k:v for k,v in doc.items() if k!="manifest_sha256"})
            paths["manifest"].write_bytes(raw(doc))
            before=paths["catalog"].read_bytes()
            with self.bind(paths):
                result=op.execute_apply(doc["manifest_sha256"])
            self.assertEqual(result["status"],"UNCHANGED")
            self.assertFalse(result["mutation_started"])
            self.assertEqual(paths["catalog"].read_bytes(),before)

    def test_source_check_is_inert(self):
        with mock.patch("builtins.print") as p:
            self.assertEqual(op.main(["--check-source"]),0)
        p.assert_called_once()
        self.assertNotIn("OWNER-AUTHORIZED",p.call_args.args[0])

if __name__=="__main__":
    unittest.main()
