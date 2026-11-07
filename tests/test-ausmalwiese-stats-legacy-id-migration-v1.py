#!/usr/bin/env python3
"""Offline safety regressions for #1412 Stats legacy-ID migration planner."""
from __future__ import annotations
import copy, importlib.util, json, sqlite3, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/ausmalwiese_stats_legacy_id_migration_v1.py"
spec=importlib.util.spec_from_file_location("stats_legacy_1412",SOURCE)
plan=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(plan)

def pairs(): return plan.load_aliases(plan.ALIASES.read_bytes())
def ev(stage):
    ps=pairs(); tables={}
    for table,spec in plan.TABLES.items():
        metrics={m:i+1 for i,m in enumerate(spec["metrics"])}
        legacy=[]; target=[]
        if stage=="before": legacy=[{"page_id":ps[0][0],"row_count":1,"metrics":metrics}]
        else: target=[{"page_id":ps[0][1],"row_count":1,"metrics":metrics}]
        tables[table]={"columns":spec["columns"],"legacy":legacy,"target":target,"unrelated_row_count":3}
    return {"schema":plan.EVIDENCE_SCHEMA,"stage":stage,"database":plan.database_identity(),
            "source":plan.source_identity(),"alias":plan.alias_identity(),"tables":tables}

SCHEMA="""
CREATE TABLE page_stats(page_id TEXT PRIMARY KEY,print_count INTEGER,like_count INTEGER,updated_at TEXT);
CREATE TABLE daily_prints(page_id TEXT,day TEXT,print_count INTEGER,PRIMARY KEY(page_id,day));
CREATE TABLE likes(page_id TEXT,visitor_hash TEXT,created_at TEXT,PRIMARY KEY(page_id,visitor_hash));
CREATE TABLE daily_views(page_id TEXT,day TEXT,view_count INTEGER,PRIMARY KEY(page_id,day));
CREATE TABLE daily_campaign_events(campaign TEXT,event TEXT,page_id TEXT,day TEXT,event_count INTEGER,PRIMARY KEY(campaign,event,page_id,day));
CREATE TABLE archived_like_totals(page_id TEXT PRIMARY KEY,like_count INTEGER);
CREATE TABLE daily_print_qr_scans(day TEXT PRIMARY KEY,scan_count INTEGER);
CREATE TABLE like_cookie_sessions(cookie_hash TEXT PRIMARY KEY,consent_notice_version INTEGER,consent_recorded_at TEXT,expires_at INTEGER);
"""
def fixture():
    db=sqlite3.connect(":memory:"); db.executescript(SCHEMA)
    for i,(old,_) in enumerate(pairs(),1):
        day=f"2026-11-{i%28+1:02d}"
        db.execute("INSERT INTO page_stats VALUES (?,?,?,?)",(old,i,i+1,f"u{i}"))
        db.execute("INSERT INTO daily_prints VALUES (?,?,?)",(old,day,i))
        db.execute("INSERT INTO likes VALUES (?,?,?)",(old,f"visitor-{i}",f"c{i}"))
        db.execute("INSERT INTO daily_views VALUES (?,?,?)",(old,day,i+2))
        db.execute("INSERT INTO daily_campaign_events VALUES (?,?,?,?,?)",("dortmund-01","detail",old,day,i+3))
        db.execute("INSERT INTO archived_like_totals VALUES (?,?)",(old,i+4))
    db.executescript("""INSERT INTO page_stats VALUES ('keep-1',9,8,'keep');
INSERT INTO daily_prints VALUES ('keep-1','2026-11-01',7);
INSERT INTO likes VALUES ('keep-1','visitor-keep','keep');
INSERT INTO daily_views VALUES ('keep-1','2026-11-01',6);
INSERT INTO daily_campaign_events VALUES ('dortmund-01','detail','keep-1','2026-11-01',5);
INSERT INTO archived_like_totals VALUES ('keep-1',4);
INSERT INTO daily_print_qr_scans VALUES ('2026-11-01',3);
INSERT INTO like_cookie_sessions VALUES ('cookie',1,'keep',123);""")
    db.commit(); return db
def rows(db,table):
    order={"page_stats":"page_id","daily_prints":"page_id,day","likes":"page_id,visitor_hash",
           "daily_views":"page_id,day","daily_campaign_events":"campaign,event,page_id,day",
           "archived_like_totals":"page_id"}[table]
    return db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()

class Tests(unittest.TestCase):
    def test_exact_vendored_alias_and_inert_contract(self):
        raw=plan.ALIASES.read_bytes(); self.assertEqual(plan.git_blob_sha(raw),plan.ALIAS_BLOB)
        ps=pairs(); self.assertEqual(len(ps),30); self.assertEqual(len(set(ps)),30)
        self.assertIn(("kuerbis-gesicht-001","0921115"),ps)
        plan.check_contract(json.loads(plan.CONTRACT.read_text()))
        self.assertEqual(plan.main(["--check-contract"]),0); self.assertEqual(plan.main(["--plan"]),0)
        self.assertEqual(plan.main(["--apply"]),2)

    def test_alias_byte_edit_fails_closed(self):
        raw=bytearray(plan.ALIASES.read_bytes()); raw[-2]=32
        with self.assertRaisesRegex(plan.Blocked,"ALIAS_BLOB"): plan.load_aliases(bytes(raw))

    def test_preflight_refuses_shape_drift_and_target_collision(self):
        ps=pairs(); before=ev("before"); plan.validate_evidence(before,"before",ps)
        bad=copy.deepcopy(before); bad["tables"]["page_stats"]["columns"][0][2]=0
        with self.assertRaisesRegex(plan.Blocked,"TABLE_SHAPE"): plan.validate_evidence(bad,"before",ps)
        bad=copy.deepcopy(before); bad["tables"]["likes"]["target"]=[{"page_id":ps[1][1],"row_count":1,"metrics":{}}]
        with self.assertRaisesRegex(plan.Blocked,"TARGET_COLLISION"): plan.validate_evidence(bad,"before",ps)

    def test_post_requires_exact_mapped_aggregates_and_unrelated_count(self):
        ps=pairs(); before=ev("before"); after=ev("after"); plan.validate_post(before,after,ps)
        bad=copy.deepcopy(after); bad["tables"]["daily_views"]["target"][0]["metrics"]["view_count"]+=1
        with self.assertRaisesRegex(plan.Blocked,"TARGET_DATA_MISMATCH"): plan.validate_post(before,bad,ps)
        bad=copy.deepcopy(after); bad["tables"]["likes"]["unrelated_row_count"]+=1
        with self.assertRaisesRegex(plan.Blocked,"UNRELATED_ROW_DRIFT"): plan.validate_post(before,bad,ps)

    def test_operation_is_one_six_statement_batch(self):
        op=plan.migration_operation(pairs(),ev("before"))
        self.assertEqual((op["transaction"],op["statement_count"],op["execution"]),("D1_DATABASE_BATCH",6,"NOT_PERFORMED"))
        self.assertFalse(op["runtime_authority"]); self.assertEqual([s["table"] for s in op["statements"]],list(plan.TABLES))
        for s in op["statements"]:
            self.assertEqual(len(s["params"]),60); self.assertNotIn("DELETE",s["sql"].upper()); self.assertNotIn("INSERT",s["sql"].upper())

    def test_all_30_preserve_non_id_columns_and_untouched_tables(self):
        ps=pairs(); db=fixture(); before={t:rows(db,t) for t in plan.TABLES}; op=plan.migration_operation(ps,ev("before"))
        db.execute("BEGIN")
        for s in op["statements"]: db.execute(s["sql"],s["params"])
        db.commit(); mapping=dict(ps)
        for table in plan.TABLES:
            after=rows(db,table); cols=[c[1] for c in db.execute(f"PRAGMA table_info({table})")]; idx=cols.index("page_id")
            expected=[]
            for original in before[table]:
                row=list(original)
                if row[idx] in mapping: row[idx]=mapping[row[idx]]
                expected.append(tuple(row))
            self.assertEqual(sorted(after),sorted(expected))
        self.assertEqual(db.execute("SELECT * FROM daily_print_qr_scans").fetchall(),[("2026-11-01",3)])
        self.assertEqual(db.execute("SELECT * FROM like_cookie_sessions").fetchall(),[("cookie",1,"keep",123)])

    def test_injected_mid_batch_failure_rolls_back(self):
        db=fixture(); before={t:rows(db,t) for t in plan.TABLES}; op=plan.migration_operation(pairs(),ev("before"))
        db.execute("BEGIN")
        with self.assertRaises(sqlite3.OperationalError):
            try:
                db.execute(op["statements"][0]["sql"],op["statements"][0]["params"])
                db.execute("UPDATE missing_table SET page_id='x'")
            except Exception:
                db.rollback(); raise
        for table in plan.TABLES: self.assertEqual(rows(db,table),before[table])

    def test_read_plan_is_bounded_and_sanitized(self):
        queries=plan.read_plan(pairs()); self.assertEqual(len(queries),24)
        for q in queries:
            sql=q["sql"].lower()
            for forbidden in ("visitor_hash","created_at","select *","delete ","update "): self.assertNotIn(forbidden,sql)

    def test_source_has_no_executor_or_credential_access(self):
        text=SOURCE.read_text()
        for forbidden in ("subprocess","requests","urllib.request","http.client","os.environ",
                          "Authorization: Bearer","api.cloudflare.com","/etc/rpi5-secrets"):
            self.assertNotIn(forbidden,text)

if __name__=="__main__": unittest.main()
