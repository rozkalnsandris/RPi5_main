#!/usr/bin/env python3
"""Mock-only contract regressions for Stats Worker protected transport (#1038)."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_stats_worker_transport_v1.py"
spec = importlib.util.spec_from_file_location("stats_transport_1038", SOURCE)
tr = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(tr)
ACCOUNT = "a" * 32
ZONE_IDS = {"ausmalwiese.de": "b" * 32, "rozkalns.net": "c" * 32}
V1 = "12345678-1234-4234-a234-123456789abc"
V2 = "22345678-1234-4234-a234-123456789abc"
DEPLOY = "32345678-1234-4234-a234-123456789abc"


def versions(latest=V1):
    return [{"id": "42345678-1234-4234-a234-123456789abc", "number": 1},
            {"id": latest, "number": 2}]


def deployments(active=V1, percent=100):
    return [{"id": DEPLOY, "created_on": "2026-10-17T08:00:00Z",
             "versions": [{"version_id": active, "percentage": percent}]}]


def routes():
    return {zone: [
        {"pattern": path, "script": tr.WORKER}
        for path, owner in tr.ROUTES.items() if owner == zone
    ] + [{"pattern": "example.com/*", "script": "other-worker"}]
            for zone in tr.ZONES}


class StatsTransportTests(unittest.TestCase):
    def test_contract_cli_and_fixed_scope(self):
        self.assertEqual(tr.main(["--check-contract"]), 0)
        self.assertEqual(tr.main(["--apply"]), 2)
        self.assertEqual(tr.main(["--deploy"]), 2)
        self.assertEqual(tr.main([]), 2)
        c = json.loads(tr.CONTRACT.read_text("utf-8"))
        tr.check_contract(c)
        self.assertFalse(c["actions"]["live"])
        self.assertFalse(c["future_write_protocol"]["authorized"])
        self.assertEqual(len(c["bindings"]), 7)
        self.assertEqual(len(c["routes"]), 4)

    def test_no_checkout_auth_and_no_credentials(self):
        with self.assertRaisesRegex(tr.Blocked, "PROTECTED_INSTALL_REQUIRED"):
            tr.FixedHTTPS(ACCOUNT, "synthetic-sufficient-length-token", ZONE_IDS)
        code = SOURCE.read_text("utf-8")
        self.assertNotIn("os.environ", code)
        self.assertNotIn("wrangler", code.lower())
        self.assertNotIn("secret_file", code.lower())
        self.assertNotIn("CLOUDFLARE_API_TOKEN", code)
        self.assertNotIn("/.config/", code)

    def test_api_allowlist_no_generic_path_or_write(self):
        base = "/client/v4/accounts/" + ACCOUNT + "/workers/scripts/" + tr.WORKER
        good = [base + "/versions?page=1&per_page=100",
                base + "/deployments",
                base + "/versions/" + V1,
                "/client/v4/zones/" + ZONE_IDS["ausmalwiese.de"],
                "/client/v4/zones/" + ZONE_IDS["rozkalns.net"] + "/workers/routes"]
        for path in good:
            self.assertTrue(tr.allowlisted_get(ACCOUNT, path, ZONE_IDS))
        for path in (base + "/versions?page=2&per_page=100",
                     base + "/versions/" + V1 + "?force=true",
                     base + "/deployments/other",
                     "/client/v4/accounts/" + ACCOUNT + "/workers/scripts/report-worker/versions",
                     "/client/v4/zones/" + "d" * 32,
                     "/client/v4/accounts/" + ACCOUNT + "/tokens"):
            self.assertFalse(tr.allowlisted_get(ACCOUNT, path, ZONE_IDS))

    def test_protected_get_rechecked_even_on_constructor_bypass(self):
        obj=object.__new__(tr.FixedHTTPS)
        obj._account,obj._zones,obj._token,obj._calls=ACCOUNT,ZONE_IDS,"fixture-token-only",0
        base="/client/v4/accounts/"+ACCOUNT+"/workers/scripts/"+tr.WORKER+"/deployments"
        with self.assertRaisesRegex(tr.Blocked,"PROTECTED_INSTALL_REQUIRED"):
            obj.get(base)
        self.assertEqual(obj._calls,0)

    def test_synthetic_http_get_success_failure_and_no_retry(self):
        class Reply:
            def __init__(self,status=200,body=b'{"success":true,"errors":[],"result":{"items":[]}}',
                         typ="application/json",length=None,encoding="identity"):
                self.status,self.body=status,body
                self.headers={"Content-Type":typ,"Content-Encoding":encoding}
                if length is not None:self.headers["Content-Length"]=length
            def getheader(self,key,default=None):
                return self.headers.get(key,default)
            def read(self,max_bytes):
                return self.body[:max_bytes]
        class FakeConn:
            def __init__(self,reply,fail=False):
                self.reply,self.fail=reply,fail
                self.calls=[];self.closed=False
            def request(self,method,path,headers):
                self.calls.append((method,path,headers))
                if self.fail:raise RuntimeError("simulated sensitive transport error")
            def getresponse(self):return self.reply
            def close(self):self.closed=True
        path="/client/v4/accounts/"+ACCOUNT+"/workers/scripts/"+tr.WORKER+"/deployments"
        for case in (Reply(),Reply(status=302),Reply(status=401),
                     Reply(typ="text/html"),Reply(length="65537"),
                     Reply(encoding="gzip"),Reply(body=b'{"x":NaN}')):
            conn=FakeConn(case)
            obj=object.__new__(tr.FixedHTTPS)
            obj._account,obj._zones,obj._token,obj._calls=ACCOUNT,ZONE_IDS,"synthetic-not-real",0
            with mock.patch.object(tr,"verified_installed_release",return_value=None):
                with mock.patch.object(tr.http.client,"HTTPSConnection",return_value=conn) as make:
                    if case.status==200 and case.headers["Content-Type"]=="application/json" and case.headers["Content-Encoding"]=="identity" and case.getheader("Content-Length") is None and b'NaN' not in case.body:
                        result=obj.get(path)
                        self.assertEqual(result,{"items":[]})
                    else:
                        with self.assertRaises(tr.Blocked):
                            obj.get(path)
            make.assert_called_once()
            self.assertEqual(len(conn.calls),1)
            self.assertTrue(conn.closed)
            self.assertEqual(obj._calls,1)
            self.assertEqual(conn.calls[0][0],"GET")
            self.assertTrue(conn.calls[0][1].endswith("/deployments"))
        conn=FakeConn(Reply(),fail=True)
        obj=object.__new__(tr.FixedHTTPS)
        obj._account,obj._zones,obj._token,obj._calls=ACCOUNT,ZONE_IDS,"synthetic-not-real",0
        with mock.patch.object(tr,"verified_installed_release",return_value=None):
            with mock.patch.object(tr.http.client,"HTTPSConnection",return_value=conn) as make:
                with self.assertRaisesRegex(tr.Blocked,"READ_TRANSPORT_UNCERTAIN"):
                    obj.get(path)
        make.assert_called_once()
        self.assertEqual(len(conn.calls),1)
        self.assertEqual(obj._calls,1)

    def test_duplicate_json_and_nonfinite_fail(self):
        for body in (b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b''):
            with self.subTest(body=body):
                with self.assertRaises(tr.Blocked):
                    tr.strict_json(body)

    def test_upstream_status_malformed_and_pagination(self):
        good = {"success": True, "errors": [], "messages": [],
                "result": {"items": versions()}}
        self.assertEqual(tr.unwrap(good)["items"], versions())
        for obj in (dict(good, success=False), dict(good, errors=[{"code":1000}]),
                    dict(good, cookie="sensitive"),
                    dict(good, result_info={"page":1,"total_pages":2}),
                    dict(good, result_info={"page":2,"total_pages":2}),
                    dict(good, result_info={"page":1,"total_pages":1,"cursors":{"after":"x"}})):
            with self.subTest(obj=list(obj)):
                with self.assertRaises(tr.Blocked):
                    tr.unwrap(obj)

    def test_latest_uploaded_by_number_not_list_order(self):
        self.assertEqual(tr.versions_summary(versions())["latest_uploaded_version"], V1)
        self.assertEqual(tr.versions_summary(versions()[::-1])["latest_uploaded_version"], V1)
        for versions_bad in ([], versions() * 50,
                             [dict(versions()[0], number=2), dict(versions()[1], number=2)],
                             [{"id":"short","number":3}], [{"id":V1,"number":True}]):
            with self.assertRaises(tr.Blocked):
                tr.versions_summary(versions_bad)

    def test_deploy_splits_ambiguity_and_order(self):
        self.assertEqual(tr.deployment_summary(deployments())["active_version"], V1)
        newer={"id":"52345678-1234-4234-a234-123456789abc",
               "created_on":"2026-10-17T08:00:00.100Z",
               "versions":[{"version_id":V2,"percentage":100}]}
        self.assertEqual(
            tr.deployment_summary([newer]+deployments())["active_version"],V2)
        with self.assertRaisesRegex(tr.Blocked,"DEPLOYMENT_SHAPE"):
            tr.deployment_summary([dict(deployments()[0],created_on="2026-10-17T08:00:00+02:00")])
        for data in (
            deployments(percent=99),
            [{"id":DEPLOY,"created_on":"2026-10-17T08:00:00Z",
              "versions":[{"version_id":V1,"percentage":50},{"version_id":V2,"percentage":50}]}],
            deployments() * 2,
            [{"id":"bad", "created_on":"2026-10-17T08:00:00Z",
              "versions":[{"version_id":V1,"percentage":100}]}],
        ):
            with self.assertRaises(tr.Blocked):
                tr.deployment_summary(data)

    def test_zones_routes_exact_and_unrelated_ignored(self):
        for zone in tr.ZONES:
            tr.zone_summary({"id":ZONE_IDS[zone], "name":zone,"status":"active"},
                            zone,ZONE_IDS[zone])
        self.assertEqual(tr.routes_summary(routes(), ZONE_IDS), tr.ROUTES)
        for zone in tr.ZONES:
            with self.assertRaises(tr.Blocked):
                tr.zone_summary({"id":ZONE_IDS[zone],"name":"wrong","status":"active"},
                                zone,ZONE_IDS[zone])
        broken=routes()
        broken["ausmalwiese.de"][0]["pattern"] = "ausmalwiese.de/*"
        with self.assertRaises(tr.Blocked):
            tr.routes_summary(broken, ZONE_IDS)
        broken=routes()
        broken["ausmalwiese.de"].append({"pattern":"another.example/*","script":tr.WORKER})
        with self.assertRaises(tr.Blocked):
            tr.routes_summary(broken,ZONE_IDS)

    def test_binding_secret_metadata_never_returned(self):
        sample = {"bindings": []}
        for name,kind in tr.TYPES.items():
            row={"name":name,"type":kind}
            if kind != "secret_text":
                row["fingerprint"] = "e" * 64
            sample["bindings"].append(row)
        s=tr.metadata_safety(sample)
        self.assertEqual(len(s),7)
        self.assertIsNone(s["VISITOR_HMAC_KEY"])
        secret=next(x for x in sample["bindings"] if x["name"]=="VISITOR_HMAC_KEY")
        secret["text"]="private"
        with self.assertRaisesRegex(tr.Blocked,"SECRET_METADATA_UNSAFE"):
            tr.metadata_safety(sample)
        secret.pop("text")
        sample["bindings"][0]["type"]="plain_text" if sample["bindings"][0]["type"]!="plain_text" else "ratelimit"
        with self.assertRaises(tr.Blocked):
            tr.metadata_safety(sample)

    def test_version_active_latest_must_match(self):
        x=tr.compare_readonly(versions(), deployments(), routes(), ZONE_IDS)
        self.assertEqual(x["state"], "INVENTORY_ONLY_CODE_PROOF_BLOCKED")
        self.assertEqual(x["active_version"],V1)
        with self.assertRaisesRegex(tr.Blocked,"LATEST_NOT_DEPLOYED"):
            tr.compare_readonly(versions(latest=V2),deployments(),routes(),ZONE_IDS)

    def test_no_code_proof_from_etag_even_if_looks_like_sha256(self):
        with self.assertRaisesRegex(tr.Blocked, "VERSION_SPECIFIC_BYTES_PROOF_UNAVAILABLE"):
            tr.version_code_proof({"resources":{"script":{"etag":"a"*64}}},b"sample")
        with self.assertRaisesRegex(tr.Blocked, "VERSION_SPECIFIC_BYTES_PROOF_UNAVAILABLE"):
            tr.version_code_proof({},b"sample")
        for args in ((), ({"allow_upload":True},), ({"allow_upload":True},{"allow_deploy":True})):
            with self.assertRaisesRegex(tr.Blocked,"SOURCE_ONLY_NO_MUTATION_CODE_PROOF_UNAVAILABLE"):
                tr.plan_live_mutations(*args)

    def test_contract_source_cannot_be_widened(self):
        c=json.loads(tr.CONTRACT.read_text("utf-8"))
        for field, value in (("worker","wrong"),("git_blob_sha1","0"*40)):
            obj=copy.deepcopy(c)
            obj["target"][field]=value
            with self.assertRaises(tr.Blocked):
                tr.check_contract(obj)
        obj=copy.deepcopy(c)
        obj["routes"]["ausmalwiese.de/*"]="ausmalwiese.de"
        with self.assertRaises(tr.Blocked):
            tr.check_contract(obj)
        obj=copy.deepcopy(c)
        obj["actions"]["live"]=True
        with self.assertRaises(tr.Blocked):
            tr.check_contract(obj)

if __name__=="__main__":
    unittest.main()
