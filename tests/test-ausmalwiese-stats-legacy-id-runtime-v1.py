#!/usr/bin/env python3
"""Offline tests for the #1417 Stats legacy-ID trusted runtime source."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_stats_legacy_id_runtime_v1.py"
spec=importlib.util.spec_from_file_location("stats_legacy_runtime_1417",SOURCE)
rt=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(rt)
planner=rt.load_planner(ROOT)
PAIRS=planner.load_aliases(planner.ALIASES.read_bytes())
CREDS={"account_id":"a"*32,"api_token":"t"*32}

def evidence(stage:str):
    tables={}
    for table,spec in planner.TABLES.items():
        metrics={m:i+1 for i,m in enumerate(spec["metrics"])}
        old=PAIRS[0][0]; new=PAIRS[0][1]
        tables[table]={
            "columns":copy.deepcopy(spec["columns"]),
            "legacy":[{"page_id":old,"row_count":1,"metrics":metrics}] if stage=="before" else [],
            "target":[] if stage=="before" else [{"page_id":new,"row_count":1,"metrics":metrics}],
            "unrelated_row_count":3,
        }
    return {
        "schema":planner.EVIDENCE_SCHEMA,"stage":stage,
        "database":planner.database_identity(),"source":planner.source_identity(),
        "alias":planner.alias_identity(),"tables":tables,
    }

def payload_from_evidence(ev):
    queries=planner.read_plan(PAIRS); result=[]
    for query in queries:
        table=ev["tables"][query["table"]]
        if query["kind"]=="schema":
            rows=[{"cid":i,"name":c[0],"type":c[1],"pk":c[2]} for i,c in enumerate(table["columns"])]
        elif query["kind"] in {"legacy","target"}:
            rows=[]
            for row in table[query["kind"]]:
                item={"page_id":row["page_id"],"row_count":row["row_count"],**row["metrics"]}
                rows.append(item)
        else:
            rows=[{"row_count":table["unrelated_row_count"]}]
        result.append({"success":True,"results":rows})
    return {"success":True,"result":result}

class Response:
    def __init__(self,payload,status=200):
        self.status=status; self.raw=json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self,n): return self.raw[:n]

class Opener:
    def __init__(self,payload=None,error=None):
        self.payload=payload; self.error=error; self.calls=[]
    def open(self,request,timeout):
        self.calls.append((request,timeout))
        if self.error is not None: raise self.error
        return Response(self.payload)

class RuntimeTests(unittest.TestCase):
    def test_contract_and_source_are_inert_and_provider_required(self):
        self.assertEqual(rt.source_check(),"STATS_LEGACY_ID_RUNTIME_SOURCE_OK_PROVIDER_REQUIRED_NO_LIVE")
        contract=rt.load_runtime_contract(ROOT)
        self.assertEqual(contract["credential_provider"]["status"],"REQUIRED_NOT_ESTABLISHED")
        self.assertTrue(all(value is False for value in contract["actions"].values()))
        with mock.patch.object(rt,"_provider_metadata") as meta:
            with self.assertRaisesRegex(rt.Blocked,"CREDENTIAL_PROVIDER_REQUIRED"):
                rt.provider_credentials(contract)
        meta.assert_not_called()

    def test_single_mapping_source_drives_all_30_and_six_statements(self):
        self.assertEqual(len(PAIRS),30)
        self.assertEqual(planner.git_blob_sha(planner.ALIASES.read_bytes()),rt.ALIASES_BLOB)
        op=planner.migration_operation(PAIRS,evidence("before"))
        body=rt.mutation_body(op,planner)
        self.assertEqual(len(body["batch"]),6)
        self.assertEqual([s["table"] for s in op["statements"]],list(planner.TABLES))
        self.assertTrue(all(len(item["params"])==60 for item in body["batch"]))

    def test_fixed_query_endpoint_and_batch_body(self):
        body={"batch":[{"sql":"UPDATE x SET y=?","params":["v"]} for _ in range(6)]}
        opener=Opener({"success":True,"result":[{"success":True} for _ in range(6)]})
        rt.api_request(CREDS,body,mutation=True,opener=opener)
        self.assertEqual(len(opener.calls),1)
        req,timeout=opener.calls[0]
        self.assertEqual(req.full_url,
            "https://api.cloudflare.com/client/v4/accounts/"+("a"*32)+
            "/d1/database/"+rt.DATABASE_ID+"/query")
        self.assertEqual(req.method,"POST"); self.assertEqual(timeout,12)
        sent=json.loads(req.data.decode())
        self.assertEqual(sent,body)
        self.assertNotIn(CREDS["api_token"],req.full_url)

    def test_mutation_transport_ambiguity_is_terminal_one_attempt(self):
        body={"batch":[{"sql":"UPDATE x SET y=?","params":["v"]} for _ in range(6)]}
        opener=Opener(error=TimeoutError())
        with self.assertRaisesRegex(rt.MutationUnknown,"MUTATION_TRANSPORT_UNKNOWN"):
            rt.api_request(CREDS,body,mutation=True,opener=opener)
        self.assertEqual(len(opener.calls),1)

    def test_read_parser_rejects_target_collision_and_schema_drift(self):
        before=evidence("before"); queries=planner.read_plan(PAIRS)
        parsed=rt.evidence_from_response(planner,queries,payload_from_evidence(before),"before")
        self.assertEqual(parsed,before)
        collision=copy.deepcopy(before)
        collision["tables"]["likes"]["target"]=[{"page_id":PAIRS[1][1],"row_count":1,"metrics":{}}]
        with self.assertRaisesRegex(planner.Blocked,"TARGET_COLLISION"):
            rt.evidence_from_response(planner,queries,payload_from_evidence(collision),"before")
        drift=copy.deepcopy(before); drift["tables"]["page_stats"]["columns"][0][2]=0
        with self.assertRaisesRegex(planner.Blocked,"TABLE_SHAPE"):
            rt.evidence_from_response(planner,queries,payload_from_evidence(drift),"before")

    def test_execute_once_performs_one_mutation_and_exact_post_verify(self):
        before=evidence("before"); after=evidence("after")
        sequence=[payload_from_evidence(before),
                  {"success":True,"result":[{"success":True} for _ in range(6)]},
                  payload_from_evidence(after)]
        calls=[]
        def requester(credentials,body,*,mutation):
            calls.append((mutation,copy.deepcopy(body)))
            return sequence.pop(0)
        def provider(_contract): return dict(CREDS)
        with mock.patch.object(rt,"load_runtime_contract",return_value=rt.expected_contract()), \
             mock.patch.object(rt,"load_planner",return_value=planner):
            result=rt.execute_once(
                "b"*40,rt.canonical_sha(before),
                source_validator=lambda _sha: ROOT,
                provider_loader=provider,requester=requester,
            )
        self.assertEqual(result["status"],"PASS")
        self.assertEqual([x[0] for x in calls],[False,True,False])
        self.assertEqual(len(calls[1][1]["batch"]),6)

    def test_post_verify_failure_after_dispatch_is_unknown_and_no_second_mutation(self):
        before=evidence("before")
        bad_after=evidence("after")
        bad_after["tables"]["daily_views"]["target"][0]["metrics"]["view_count"]+=1
        sequence=[payload_from_evidence(before),
                  {"success":True,"result":[{"success":True} for _ in range(6)]},
                  payload_from_evidence(bad_after)]
        calls=[]
        def requester(credentials,body,*,mutation):
            calls.append(mutation); return sequence.pop(0)
        with mock.patch.object(rt,"load_runtime_contract",return_value=rt.expected_contract()), \
             mock.patch.object(rt,"load_planner",return_value=planner):
            with self.assertRaisesRegex(rt.MutationUnknown,"POST_VERIFY_UNKNOWN"):
                rt.execute_once(
                    "b"*40,rt.canonical_sha(before),
                    source_validator=lambda _sha: ROOT,
                    provider_loader=lambda _contract:dict(CREDS),
                    requester=requester,
                )
        self.assertEqual(calls.count(True),1)

    def test_source_has_no_secret_output_or_retry_loop_surface(self):
        text=SOURCE.read_text("utf-8")
        for forbidden in ("CLOUDFLARE_API_TOKEN","/etc/rpi5-secrets","requests.",
                          "Retry(","sleep(","while True","shell=True"):
            self.assertNotIn(forbidden,text)
        self.assertNotIn("api_token",rt.source_check())
        self.assertEqual(rt.expected_contract()["transport"]["automatic_retries"],0)

if __name__=="__main__": unittest.main()
