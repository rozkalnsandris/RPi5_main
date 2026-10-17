#!/usr/bin/env python3
from __future__ import annotations
import copy, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OP=ROOT/"scripts/cloudflare_coloring_ingress.py"; BR=ROOT/"scripts/github_rpi5_841_bridge.py"; WF=ROOT/".github/workflows/coloring-public-ingress.yml"
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("coloring",OP); assert spec and spec.loader
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def sample(present=False):
    hosts=sorted(m.expected_present_hosts())
    rows=[{"hostname":h,"service":"http://127.0.0.1:8080"} for h in hosts]
    if present: rows.append({"hostname":m.HOSTNAME,"service":m.ORIGIN})
    rows.append({"service":"http_status:404"})
    return {"ingress":rows,"originRequest":{}}

def test_static():
    subprocess.run([sys.executable,"-m","py_compile",str(OP),str(BR)],check=True)
    t=OP.read_text(); w=WF.read_text()
    assert m.HOSTNAME=="coloring.rozkalns.net" and m.ORIGIN=="http://127.0.0.1:9191"
    for required in ('method="PUT"','method="POST"','deny_unmatched_requests','resolve_application','cfargotunnel.com'):
        assert required in t
    for forbidden in ("subprocess","os.system","shell=True","systemctl","docker ","ufw ","/etc/cloudflared"):
        assert forbidden not in t
    assert "issue_comment:" in w and "persist-credentials: false" in w
    assert "CLOUDFLARE_P1D03_READ_API_TOKEN" in w and "CLOUDFLARE_API_TOKEN" in w
    assert "self-hosted" not in w

def test_config_contract():
    m.validate_config(sample(False),target_present=False)
    m.validate_config(sample(True),target_present=True)
    bad=sample(False); bad["ingress"].insert(-1,{"hostname":"extra.rozkalns.net","service":"http://127.0.0.1:1"})
    try: m.validate_config(bad,target_present=False)
    except m.IngressError as e: assert str(e)=="tunnel_hostname_set_drift"
    else: raise AssertionError("extra route accepted")

def test_access_default_deny():
    saved=m.request
    try:
        m.request=lambda token,path,**kw: {"deny_unmatched_requests":True,"deny_unmatched_requests_exempted_zone_names":[]} if path.endswith("/access/organizations") else []
        try: m.access_preflight("a"*32,"x"*24)
        except m.IngressError as e: assert str(e)=="require_access_protection_conflict"
        else: raise AssertionError("default deny accepted")
    finally: m.request=saved

def test_apply_scope_and_order():
    original=sample(False); calls=[]; saved=(m.preflight,m.get_config,m.get_zone_and_dns,m.request,m.verify_state)
    try:
        m.preflight=lambda *a:(copy.deepcopy(original),7,"z"*32)
        m.get_config=lambda *a:(copy.deepcopy(original) if not calls else copy.deepcopy(calls[0][2]["config"]),7)
        m.get_zone_and_dns=lambda *a,**k:("z"*32,[])
        def req(token,path,**kw):
            calls.append((kw.get("method","GET"),path,copy.deepcopy(kw.get("body")))); return {}
        m.request=req; m.verify_state=lambda *a:None
        m.apply("a"*32,"00000000-0000-4000-8000-000000000000","w"*24,"r"*24)
        assert calls[0][0]=="PUT" and calls[1][0]=="POST"
        desired=calls[0][2]["config"]; m.validate_config(desired,target_present=True)
        proof=copy.deepcopy(desired); proof["ingress"].pop(-2); assert proof==original
    finally: m.preflight,m.get_config,m.get_zone_and_dns,m.request,m.verify_state=saved

def test_bridge_exact():
    event={"action":"created","issue":{"number":841},"comment":{"id":1,"body":"/rpi5-841 check HEAD="+"a"*40+" CANARY=coloring-public-ingress","author_association":"OWNER","user":{"login":"rozkalnsandris","id":277435981}},"sender":{"login":"rozkalnsandris","id":277435981}}
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"e"; o=Path(d)/"o"; p.write_text(json.dumps(event))
        env=os.environ.copy(); env.update({"GITHUB_REPOSITORY":"rozkalnsandris/RPi5_main","GITHUB_EVENT_PATH":str(p),"GITHUB_OUTPUT":str(o),"GITHUB_SHA":"a"*40})
        r=subprocess.run([sys.executable,str(BR)],env=env,check=False)
        assert r.returncode==0 and "operation=check" in o.read_text()

def main():
    for f in (test_static,test_config_contract,test_access_default_deny,test_apply_scope_and_order,test_bridge_exact):
        f(); print(f.__name__+": PASS")
if __name__=="__main__": main()
