#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, subprocess, sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
CONTRACT_PATH=ROOT/"ops/contracts/private-zone-verification-v1.json"
SCHEMA="rozkalns.rpi5-main.phase5-private-protected-evidence.v1"
ALLOWED={"PASS","FAIL","UNKNOWN"}
class ReceiptError(RuntimeError): pass

def _git(*args:str)->str:
    p=subprocess.run(["git","-C",str(ROOT),*args],check=False,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=10)
    if p.returncode!=0: raise ReceiptError("git_source_check_failed")
    return p.stdout.strip()

def verify_exact_source(expected_main:str)->None:
    if len(expected_main)!=40 or any(ch not in "0123456789abcdef" for ch in expected_main): raise ReceiptError("expected_main_invalid")
    if _git("rev-parse","HEAD")!=expected_main: raise ReceiptError("exact_main_mismatch")
    if _git("branch","--show-current")!="main": raise ReceiptError("main_branch_required")
    for args in (("diff","--quiet"),("diff","--cached","--quiet")):
        p=subprocess.run(["git","-C",str(ROOT),*args],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if p.returncode!=0: raise ReceiptError("tracked_source_dirty")

def projection()->dict[str,Any]:
    c=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if c.get("schema")!="rozkalns.rpi5-main.private-zone-verification.v1": raise ReceiptError("contract_invalid")
    p=c.get("service_projections")
    if not isinstance(p,list) or len(p)!=1: raise ReceiptError("projection_invalid")
    return p[0]

def validate_submission(payload:Any, projected:dict[str,Any], expected_main:str)->dict[str,str]:
    if not isinstance(payload,dict) or set(payload)!={"source_main_sha","service"}: raise ReceiptError("submission_top_level_fields_invalid")
    if payload["source_main_sha"]!=expected_main: raise ReceiptError("submission_source_sha_mismatch")
    item=payload["service"]
    if not isinstance(item,dict) or set(item)!={"service_id","hostname","authorized_private_result"}: raise ReceiptError("submission_service_fields_invalid")
    if item["service_id"]!=projected["service_id"] or item["hostname"]!=projected["hostname"]: raise ReceiptError("submission_service_projection_mismatch")
    result=item["authorized_private_result"]
    if result not in ALLOWED: raise ReceiptError("submission_result_invalid")
    return {"service_id":projected["service_id"],"hostname":projected["hostname"],"authorized_private_result":result,"result":result}

def build_report(expected_main:str,service:dict[str,str])->dict[str,Any]:
    return {"schema":SCHEMA,"observed_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),"source_main_sha":expected_main,"verification_class":"protected-authorized-private","result":service["authorized_private_result"],"mutation_performed":False,"services":[service],"privacy":{"identity_values_persisted":False,"session_material_persisted":False,"cookie_material_persisted":False,"credential_material_persisted":False,"token_material_persisted":False,"response_content_persisted":False,"browser_profile_read_by_operator":False}}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--expected-main",required=True); args=p.parse_args()
    try:
        verify_exact_source(args.expected_main)
        service=validate_submission(json.load(sys.stdin),projection(),args.expected_main)
        report=build_report(args.expected_main,service)
    except (ReceiptError,json.JSONDecodeError,OSError,subprocess.SubprocessError):
        print(json.dumps({"schema":SCHEMA,"source_main_sha":args.expected_main,"verification_class":"protected-authorized-private","result":"UNKNOWN","mutation_performed":False,"reason":"protected_receipt_validation_failed"},indent=2,sort_keys=True)); return 2
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["result"]=="PASS" else (3 if report["result"]=="FAIL" else 4)
if __name__=="__main__": raise SystemExit(main())
