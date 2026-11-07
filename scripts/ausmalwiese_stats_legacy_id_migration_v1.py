#!/usr/bin/env python3
"""Inert source planner for Ausmalwiese Stats legacy-ID migration (#1412).

No Cloudflare request, credential access, D1 read/write, Worker deploy or RPi5
content mutation. The module validates a pinned alias artifact and sanitized
evidence, then emits one six-statement D1 batch operation as data only.
"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"ops/contracts/ausmalwiese-stats-legacy-id-migration-v1.json"
ALIASES=ROOT/"ops/vendor/coloring-pages/legacy-id-aliases-457.json"
ISSUE=1412
UPSTREAM_COMMIT="9c013bfbab8f3cc5eaaa905f57119c53abc8ab48"
ALIAS_BLOB="2e20a2a7a7e716274934a0eb662091150ef55e7f"
CATALOG_SHA="efa6a736839657f849606f665b09bd51dff1165a1c9c2038e9d5b7e720cc7ba9"
PLAN_SHA="80538dd2bda9755212c599d1b75a106673e1eb5c774cebc47f4192e0478fad9c"
ALIASES_SHA="24cf6ec46ba2ad2b1791c8aff8975937bb9b0e629076d0d34b828ee30d6308b5"
DATABASE_ID="f8ac8f1d-a230-4bc4-af13-557c1b91b273"
WORKER_BLOB="8790a8ddc3b83771088c4cceb16a3b57ce5d1c8b"
CONFIG_BLOB="3733263a391274f2b6b0f2023c8656565bde8e1a"
SCHEMA_BLOB="ead4cc5f497de6eeac0cf6b07c2ca13db986423a"
EVIDENCE_SCHEMA="ausmalwiese.stats-legacy-id-evidence.v1"
OP_SCHEMA="ausmalwiese.stats-legacy-id-operation.v1"
STOP="STOP_STATS_LEGACY_ID_MIGRATION_SOURCE_ONLY"
NEW_ID=re.compile(r"^[0-9]{7}$")
OLD_ID=re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

TABLES={
 "page_stats":{"columns":[["page_id","TEXT",1],["print_count","INTEGER",0],["like_count","INTEGER",0],["updated_at","TEXT",0]],"metrics":["print_count","like_count"]},
 "daily_prints":{"columns":[["page_id","TEXT",1],["day","TEXT",2],["print_count","INTEGER",0]],"metrics":["print_count"]},
 "likes":{"columns":[["page_id","TEXT",1],["visitor_hash","TEXT",2],["created_at","TEXT",0]],"metrics":[]},
 "daily_views":{"columns":[["page_id","TEXT",1],["day","TEXT",2],["view_count","INTEGER",0]],"metrics":["view_count"]},
 "daily_campaign_events":{"columns":[["campaign","TEXT",1],["event","TEXT",2],["page_id","TEXT",3],["day","TEXT",4],["event_count","INTEGER",0]],"metrics":["event_count"]},
 "archived_like_totals":{"columns":[["page_id","TEXT",1],["like_count","INTEGER",0]],"metrics":["like_count"]},
}
UNTOUCHED=["daily_print_qr_scans","like_cookie_sessions"]

class Blocked(ValueError): pass
def need(ok:bool, reason:str)->None:
    if not ok: raise Blocked(reason)

def git_blob_sha(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def canonical_sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def source_identity()->dict:
    return {"coloring_pages_commit":UPSTREAM_COMMIT,"alias_git_blob":ALIAS_BLOB,
            "worker_blob":WORKER_BLOB,"config_blob":CONFIG_BLOB,"schema_blob":SCHEMA_BLOB}

def database_identity()->dict:
    return {"binding":"DB","database_name":"coloring-pages-stats-v1","database_id":DATABASE_ID}

def alias_identity()->dict:
    return {"catalog_sha256":CATALOG_SHA,"plan_sha256":PLAN_SHA,
            "aliases_sha256":ALIASES_SHA,"alias_git_blob":ALIAS_BLOB,"alias_count":30}

def load_aliases(raw:bytes)->list[tuple[str,str]]:
    need(len(raw)<=256000 and git_blob_sha(raw)==ALIAS_BLOB,"ALIAS_BLOB")
    try: doc=json.loads(raw.decode("utf-8"))
    except (UnicodeError,json.JSONDecodeError) as exc: raise Blocked("ALIAS_JSON") from exc
    need(type(doc) is dict and set(doc)=={"schema","issue","source_catalog_sha256","source_catalog_count",
         "source_legacy_count","source_plan_manifest_sha256","aliases_sha256","aliases"},"ALIAS_FIELDS")
    need(doc["schema"]=="rozkalns.coloring-pages.legacy-id-aliases.v1" and doc["issue"]==457,"ALIAS_SCHEMA")
    need(doc["source_catalog_sha256"]==CATALOG_SHA and doc["source_catalog_count"]==477,"CATALOG_IDENTITY")
    need(doc["source_legacy_count"]==30 and doc["source_plan_manifest_sha256"]==PLAN_SHA
         and doc["aliases_sha256"]==ALIASES_SHA,"ALIAS_IDENTITY")
    pairs=[]; old_seen=set(); new_seen=set(); normalized=[]
    for item in doc["aliases"]:
        need(type(item) is dict and set(item)=={"old_id","new_id"},"ALIAS_ENTRY")
        old,new=item["old_id"],item["new_id"]
        need(type(old) is str and OLD_ID.fullmatch(old) and not NEW_ID.fullmatch(old),"OLD_ID")
        need(type(new) is str and NEW_ID.fullmatch(new),"NEW_ID")
        need(old not in old_seen and new not in new_seen,"ALIAS_DUPLICATE")
        old_seen.add(old); new_seen.add(new); pairs.append((old,new))
        normalized.append({"old_id":old,"new_id":new})
    need(len(pairs)==30,"ALIAS_COUNT")
    digest=hashlib.sha256(json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    need(digest==ALIASES_SHA,"ALIAS_DIGEST")
    return pairs

def validate_rows(table:str, rows:Any, allowed:set[str])->list[dict]:
    need(type(rows) is list,"ROWS")
    seen=set()
    for row in rows:
        need(type(row) is dict and set(row)=={"page_id","row_count","metrics"},"ROW_FIELDS")
        pid=row["page_id"]; count=row["row_count"]; metrics=row["metrics"]
        need(type(pid) is str and pid in allowed and pid not in seen,"ROW_ID")
        need(type(count) is int and count>0,"ROW_COUNT")
        need(type(metrics) is dict and set(metrics)==set(TABLES[table]["metrics"]),"ROW_METRICS")
        need(all(type(v) is int and v>=0 for v in metrics.values()),"ROW_METRIC_VALUE")
        seen.add(pid)
    return rows

def validate_evidence(snapshot:Any, stage:str, pairs:list[tuple[str,str]])->dict:
    need(stage in {"before","after"},"STAGE")
    need(type(snapshot) is dict and set(snapshot)=={"schema","stage","database","source","alias","tables"},"EVIDENCE_FIELDS")
    need(snapshot["schema"]==EVIDENCE_SCHEMA and snapshot["stage"]==stage,"EVIDENCE_SCHEMA")
    need(snapshot["database"]==database_identity() and snapshot["source"]==source_identity()
         and snapshot["alias"]==alias_identity(),"EVIDENCE_IDENTITY")
    need(type(snapshot["tables"]) is dict and set(snapshot["tables"])==set(TABLES),"TABLE_SET")
    old={a for a,_ in pairs}; new={b for _,b in pairs}
    for table,spec in TABLES.items():
        item=snapshot["tables"][table]
        need(type(item) is dict and set(item)=={"columns","legacy","target","unrelated_row_count"},"TABLE_FIELDS")
        need(item["columns"]==spec["columns"],"TABLE_SHAPE")
        need(type(item["unrelated_row_count"]) is int and item["unrelated_row_count"]>=0,"UNRELATED_COUNT")
        validate_rows(table,item["legacy"],old); validate_rows(table,item["target"],new)
        if stage=="before": need(item["target"]==[],"TARGET_COLLISION")
    return snapshot

def validate_post(before:Any, after:Any, pairs:list[tuple[str,str]])->dict:
    validate_evidence(before,"before",pairs); validate_evidence(after,"after",pairs)
    mapping=dict(pairs)
    for table in TABLES:
        b=before["tables"][table]; a=after["tables"][table]
        need(a["legacy"]==[],"LEGACY_REMAINS")
        expected=sorted([{"page_id":mapping[r["page_id"]],"row_count":r["row_count"],"metrics":r["metrics"]}
                         for r in b["legacy"]],key=lambda r:r["page_id"])
        need(sorted(a["target"],key=lambda r:r["page_id"])==expected,"TARGET_DATA_MISMATCH")
        need(a["unrelated_row_count"]==b["unrelated_row_count"],"UNRELATED_ROW_DRIFT")
    return after

def read_plan(pairs:list[tuple[str,str]])->list[dict]:
    old=[a for a,_ in pairs]; new=[b for _,b in pairs]; result=[]
    for table,spec in TABLES.items():
        result.append({"kind":"schema","table":table,"sql":f"PRAGMA table_info({table})","params":[]})
        for kind,ids in (("legacy",old),("target",new)):
            metrics="".join(f", SUM({m}) AS {m}" for m in spec["metrics"])
            marks=",".join("?" for _ in ids)
            result.append({"kind":kind,"table":table,
                "sql":f"SELECT page_id, COUNT(*) AS row_count{metrics} FROM {table} WHERE page_id IN ({marks}) GROUP BY page_id ORDER BY page_id",
                "params":ids})
        marks=",".join("?" for _ in old+new)
        result.append({"kind":"unrelated_count","table":table,
            "sql":f"SELECT COUNT(*) AS row_count FROM {table} WHERE page_id NOT IN ({marks})","params":old+new})
    return result

def migration_operation(pairs:list[tuple[str,str]], before:Any)->dict:
    validate_evidence(before,"before",pairs)
    values=",".join("(?,?)" for _ in pairs); params=[v for pair in pairs for v in pair]
    statements=[]
    for table in TABLES:
        sql=(f"WITH alias_map(old_id,new_id) AS (VALUES {values}) UPDATE {table} "
             f"SET page_id=(SELECT new_id FROM alias_map WHERE old_id={table}.page_id) "
             f"WHERE page_id IN (SELECT old_id FROM alias_map)")
        statements.append({"table":table,"sql":sql,"params":params})
    return {"schema":OP_SCHEMA,"issue":ISSUE,"database":database_identity(),"alias":alias_identity(),
            "transaction":"D1_DATABASE_BATCH","statement_count":6,"statements":statements,
            "preflight_sha256":canonical_sha(before),"runtime_authority":False,"execution":"NOT_PERFORMED"}

def check_contract(doc:Any)->None:
    need(type(doc) is dict and doc.get("schema_version")==1 and doc.get("issue")==ISSUE,"CONTRACT_IDENTITY")
    need(doc.get("status")=="SOURCE_ONLY_LEGACY_ID_STATS_MIGRATION_NO_LIVE","CONTRACT_STATUS")
    need(doc.get("upstream",{}).get("alias_git_blob")==ALIAS_BLOB and doc["upstream"].get("aliases_sha256")==ALIASES_SHA,"CONTRACT_ALIAS")
    need(doc.get("d1")=={"binding":"DB","database_name":"coloring-pages-stats-v1","database_id":DATABASE_ID,
         "worker_blob":WORKER_BLOB,"config_blob":CONFIG_BLOB,"schema_blob":SCHEMA_BLOB},"CONTRACT_D1")
    need(doc.get("page_id_tables")==list(TABLES) and doc.get("untouched_tables")==UNTOUCHED,"CONTRACT_TABLES")
    need(doc.get("transaction")=={"primitive":"D1_DATABASE_BATCH","statement_count":6,
         "one_remote_dispatch_required":True,"target_collision_policy":"STOP"},"CONTRACT_TRANSACTION")
    need(all(v is False for v in doc.get("actions",{}).values()),"CONTRACT_ACTIONS")

def main(argv=None)->int:
    args=sys.argv[1:] if argv is None else argv
    try:
        check_contract(json.loads(CONTRACT.read_text("utf-8")))
        pairs=load_aliases(ALIASES.read_bytes())
        if args==["--check-contract"]:
            print("STATS_LEGACY_ID_MIGRATION_OK_SOURCE_ONLY_NO_LIVE"); return 0
        if args==["--plan"]:
            print(json.dumps({"operation":"PLAN_ONLY_NO_WRITES","alias_count":len(pairs),
                "page_id_tables":list(TABLES),"transaction":"D1_DATABASE_BATCH","statement_count":6,
                "runtime_authority":False},sort_keys=True)); return 0
        raise Blocked("MODE")
    except (Blocked,OSError,UnicodeError,json.JSONDecodeError):
        print(STOP,file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
