#!/usr/bin/env python3
"""Adversarial, disconnected Cloudflare readback tests (#1356)."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import ausmalwiese_goatcounter_simple_cloudflare_readback_v1 as m

ACCOUNT="a"*32
ZONE="b"*32
TUNNEL="11111111-1111-4111-8111-111111111111"
P=f"/accounts/{ACCOUNT}"
C=f"{P}/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100"
T=f"{P}/cfd_tunnel/{TUNNEL}/configurations"
R=f"/zones/{ZONE}/workers/routes"
D=f"{P}/workers/domains?page=1&per_page=20"

def response(value,**fields):
    return {"success":True,"errors":[],"result":value,**fields}

def info(page,count,total):
    return {"page":page,"count":count,"per_page":20,"total_count":total,
            "total_pages":max(1,(total+19)//20)}

def domain(host="api.ausmalwiese.de",ident="c"*32,zone=ZONE,
           zone_name="ausmalwiese.de",active=True,preview=False):
    return {"id":ident,"hostname":host,"zone_id":zone,"zone_name":zone_name,
            "enabled":active,"previews_enabled":preview,"service":"worker-fixture"}

def fixture():
    return {
        f"/zones/{ZONE}":response({"id":ZONE,"name":"ausmalwiese.de",
             "status":"active","account":{"id":ACCOUNT}}),
        C:response([{"id":TUNNEL,"name":"rpi5-tunnel",
             "config_src":"cloudflare","deleted_at":None,"account_id":ACCOUNT}],
             result_info={"page":1,"total_pages":1,"count":1,"total_count":1}),
        T:response({"version":4,"account_id":ACCOUNT,"config":{"ingress":[
             {"hostname":"ausmalwiese.de","service":"http://127.0.0.1:9191"},
             {"hostname":"www.ausmalwiese.de","service":"http://127.0.0.1:9191"},
             {"service":"http_status:404"}]}}),
        R:response([{"id":"d"*32,"pattern":"ausmalwiese.de/api/*",
                     "script":"worker-fixture"}]),
        D:response([],result_info=info(1,0,0)),
    }

class Getter:
    def __init__(self,answers):
        self.answers=answers
        self.paths=[]
    def __call__(self,path):
        self.paths.append(path)
        if path not in self.answers:
            raise RuntimeError("canary secret upstream error")
        return self.answers[path]

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(m,"ACCOUNT_SHA256",hashlib.sha256(ACCOUNT.encode()).hexdigest())
        p.start()
        self.addCleanup(p.stop)

    def run_case(self,data=None,account=ACCOUNT,zone=ZONE):
        fake=Getter(fixture() if data is None else data)
        result=m.collect_once(trusted_get=fake,account_id=account,zone_id=zone)
        self.assertEqual(len(fake.paths),len(set(fake.paths)))
        self.assertLessEqual(len(fake.paths),12)
        self.assertNotIn("canary",str(result))
        self.assertNotIn(ACCOUNT,str(result))
        self.assertNotIn(ZONE,str(result))
        return result,fake

    def assert_stop(self,data,code):
        result,fake=self.run_case(data)
        self.assertEqual(result,(code,None))
        return fake

    def test_synthetic_pass_exposes_only_safe_constants(self):
        result,fake=self.run_case()
        self.assertEqual(result[0],"PASS_EDGE_SOURCE_ONLY")
        self.assertEqual(result[1],{
            "remote_tunnel":"verified_exact_config",
            "routes":{"ausmalwiese.de":"absent_safe_before_app_catchall",
                      "www.ausmalwiese.de":"absent_safe_before_app_catchall"},
            "worker_routes":"verified_no_count_interception",
            "worker_custom_domains":"verified_no_count_interception"})
        self.assertEqual(fake.paths,[f"/zones/{ZONE}",C,T,R,D])
        self.assertNotIn(TUNNEL,str(result))
        self.assertNotIn("worker-fixture",str(result))

    def test_bad_identity_stops_before_get(self):
        for account,zone in ((None,ZONE),(True,ZONE),("x"*32,ZONE),
                             (ACCOUNT,"invalid"),(ACCOUNT,True)):
            with self.subTest(account=account,zone=zone):
                result,fake=self.run_case(account=account,zone=zone)
                self.assertEqual(result,("STOP_IDENTITY",None))
                self.assertEqual(fake.paths,[])

    def test_zone_binding(self):
        for field,value in (("name","other.com"),("id","c"*32),
                            ("status","pending"),("account",{"id":"d"*32})):
            data=fixture()
            data[f"/zones/{ZONE}"]["result"][field]=value
            with self.subTest(field=field):
                self.assert_stop(data,"STOP_ZONE")

    def test_tunnel_and_route_fail_closed(self):
        for field,value in (("name","wrong"),("config_src","local"),
                            ("id","invalid"),("deleted_at","now"),
                            ("account_id","f"*32)):
            data=fixture()
            data[C]["result"][0][field]=value
            with self.subTest(field=field):
                self.assert_stop(data,"STOP_TUNNEL")
        data=fixture()
        data[C]["result_info"]["total_pages"]=2
        self.assert_stop(data,"STOP_TUNNEL_PAGINATION")
        data=fixture()
        data[T]["result"]["config"]["originRequest"]={"httpHostHeader":"canary"}
        self.assert_stop(data,"STOP_ROUTE")
        data=fixture()
        data[T]["result"]["config"]["ingress"].insert(0,{
            "hostname":"*.ausmalwiese.de","service":"http://127.0.0.1:9195"})
        self.assert_stop(data,"STOP_ROUTE")
        data=fixture()
        data[T]["result"]["config"]["ingress"].insert(0,{
            "hostname":"ausmalwiese.de","path":"^/count$",
            "service":"http://127.0.0.1:9194",
            "originRequest":{"httpHostHeader":"goatcounter.ausmalwiese.invalid"}})
        self.assert_stop(data,"STOP_ROUTE")
        data=fixture()
        data[T]["result"]["version"]=True
        self.assert_stop(data,"STOP_TUNNEL")

    def test_worker_routes_and_exclusion(self):
        for pat in ("ausmalwiese.de/count","ausmalwiese.de/count*",
                    "*.ausmalwiese.de/count","*ausmalwiese.de/*",
                    "www.ausmalwiese.de/*","ausmalwiese.de/*.jpg",
                    "ausmalwiese.de/count?x=y","*","ausmalwiese.de/COUNT"):
            with self.subTest(pattern=pat):
                data=fixture()
                data[R]["result"]=[{"id":"d"*32,"pattern":pat,"script":None}]
                self.assert_stop(data,"STOP_WORKER")
        data=fixture()
        data[R]["result_info"]={"page":1,"total_pages":2}
        self.assert_stop(data,"STOP_WORKER_PAGINATION")
        data=fixture()
        data[R]["result"][0]["token"]="canary"
        result,_=self.run_case(data)
        self.assertEqual(result[0],"PASS_EDGE_SOURCE_ONLY")
        data=fixture()
        data[R]["result"]*=2
        self.assert_stop(data,"STOP_WORKER")

    def test_domains_enabled_disabled_and_preview(self):
        for host,active,preview in (("ausmalwiese.de",True,False),
                ("www.ausmalwiese.de",False,True),
                ("ausmalwiese.de",False,False),
                ("www.ausmalwiese.de",True,True)):
            data=fixture()
            data[D]=response([domain(host,active=active,preview=preview)],
                             result_info=info(1,1,1))
            with self.subTest(host=host,active=active,preview=preview):
                self.assert_stop(data,"STOP_DOMAIN_INTERCEPTION")
        data=fixture()
        data[D]=response([domain()],result_info=info(1,1,1))
        result,_=self.run_case(data)
        self.assertEqual(result[0],"PASS_EDGE_SOURCE_ONLY")
        data=fixture()
        data[D]=response([domain("www.ausmalwiese.de",zone="e"*32)],
                         result_info=info(1,1,1))
        self.assert_stop(data,"STOP_DOMAIN_ZONE")

    def test_bounded_complete_pagination(self):
        data=fixture()
        more=f"{P}/workers/domains?page=2&per_page=20"
        entries=[domain(f"example{n}.org",ident=f"{n+1:032x}",
                        zone="f"*32,zone_name="example.org")
                 for n in range(21)]
        data[D]=response(entries[:20],result_info=info(1,20,21))
        data[more]=response(entries[20:],result_info=info(2,1,21))
        result,fake=self.run_case(data)
        self.assertEqual(result[0],"PASS_EDGE_SOURCE_ONLY")
        self.assertEqual(fake.paths[-1],more)
        data[more]["result_info"]["page"]=1
        self.assert_stop(data,"STOP_DOMAIN_PAGINATION")
        del data[more]
        fake=self.assert_stop(data,"STOP_TRANSPORT")
        self.assertEqual(fake.paths.count(more),1)

    def test_incomplete_and_invalid_pages(self):
        for change in ("missing","count","total","page","pages","per_page"):
            data=fixture()
            obj=data[D]
            if change=="missing":del obj["result_info"]
            if change=="count":obj["result_info"]["count"]=1
            if change=="total":obj["result_info"]["total_count"]=21
            if change=="page":obj["result_info"]["page"]=2
            if change=="pages":obj["result_info"]["total_pages"]=2
            if change=="per_page":obj["result_info"]["per_page"]=100
            with self.subTest(change=change):
                self.assert_stop(data,"STOP_DOMAIN_PAGINATION")
        data=fixture()
        data[D]["result"]=[{"raw-token":"canary"}]
        data[D]["result_info"]=info(1,1,1)
        self.assert_stop(data,"STOP_DOMAIN")

    def test_transport_injection_and_disabled_runtime(self):
        self.assertEqual(m.collect_once(trusted_get=None,account_id=ACCOUNT,zone_id=ZONE),
                         ("STOP_TRANSPORT",None))
        self.assertFalse(hasattr(m,"apply"))
        self.assertFalse(hasattr(m,"main"))

if __name__=="__main__":
    unittest.main()
