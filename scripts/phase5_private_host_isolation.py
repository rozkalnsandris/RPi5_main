#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, socket, subprocess
from pathlib import Path
from typing import Any

REPOSITORY="rozkalnsandris/RPi5_main"
ISSUE_NUMBER=866
CONTRACT_PATH=Path("ops/contracts/private-zone-verification-v1.json")
class VerifyError(RuntimeError): pass

def _run(args:list[str])->str:
    p=subprocess.run(args,check=False,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=10)
    if p.returncode!=0: raise VerifyError("read_only_command_failed")
    return p.stdout

def _verify_exact_source(expected_main:str)->None:
    if _run(["git","rev-parse","HEAD"]).strip()!=expected_main: raise VerifyError("exact_main_mismatch")
    for args in (["git","diff","--quiet"],["git","diff","--cached","--quiet"]):
        p=subprocess.run(args,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if p.returncode!=0: raise VerifyError("tracked_source_dirty")

def _primary_lan_address()->str:
    raw=_run(["ip","-j","-4","route","get","1.1.1.1"]); decoded=json.loads(raw)
    if not isinstance(decoded,list) or len(decoded)!=1 or not isinstance(decoded[0],dict): raise VerifyError("lan_route_shape_invalid")
    address=decoded[0].get("prefsrc") or decoded[0].get("src")
    if not isinstance(address,str) or not address: raise VerifyError("lan_address_unavailable")
    return address

def _split_endpoint(value:str)->tuple[str,int]|None:
    text=value.strip()
    if text.startswith("[") and "]:" in text: host,port=text[1:].rsplit("]:",1)
    elif ":" in text: host,port=text.rsplit(":",1)
    else: return None
    try: return host,int(port)
    except ValueError: return None

def _listeners(ss_text:str)->dict[int,set[str]]:
    result={}
    for line in ss_text.splitlines():
        parts=line.split()
        if len(parts)<4: continue
        endpoint=_split_endpoint(parts[3])
        if endpoint is None: continue
        host,port=endpoint; result.setdefault(port,set()).add(host)
    return result

def _bind_class(addresses:set[str],lan:str)->str:
    if not addresses: return "none"
    classes=set()
    for address in addresses:
        n=address.strip("[]")
        if n in {"127.0.0.1","::1"}: classes.add("loopback")
        elif n in {"0.0.0.0","::","*"}: classes.add("wildcard")
        elif n==lan: classes.add("lan")
        else: classes.add("other")
    return next(iter(classes)) if len(classes)==1 else "mixed"

def _lan_path(lan:str,port:int)->str:
    try:
        with socket.create_connection((lan,port),timeout=1.5): return "present"
    except (ConnectionRefusedError,TimeoutError,socket.timeout,OSError): return "absent"

def _recovery_present(value:Any)->bool:
    if not isinstance(value,str) or not value or value.startswith("/"): return False
    p=Path(value); return ".." not in p.parts and p.is_file()

def build_report(*,expected_main:str,contract:dict[str,Any],listeners:dict[int,set[str]],lan_address:str)->dict[str,Any]:
    if contract.get("schema")!="rozkalns.rpi5-main.private-zone-verification.v1": raise VerifyError("private_contract_invalid")
    projections=contract.get("service_projections"); host_cfg=contract.get("host_verifier")
    if not isinstance(projections,list) or len(projections)!=1 or not isinstance(host_cfg,dict): raise VerifyError("contract_shape_invalid")
    projected=projections[0]; port=host_cfg.get("probe_port")
    if not isinstance(port,int) or not 1<=port<=65535: raise VerifyError("probe_port_invalid")
    bind=_bind_class(listeners.get(port,set()),lan_address); lan_path=_lan_path(lan_address,port)
    owner_matches=projected.get("runtime_owner")==REPOSITORY; recovery=_recovery_present(projected.get("recovery_ref"))
    passed=(bind==host_cfg.get("expected_listener_bind_class") and lan_path==host_cfg.get("expected_lan_path_class") and owner_matches and recovery)
    service={"service_id":projected["service_id"],"hostname":projected["hostname"],"listener_bind_class":bind,"lan_path_class":lan_path,"runtime_owner_matches":owner_matches,"recovery_ref_present":recovery,"result":"PASS" if passed else "FAIL"}
    return {"schema_version":1,"audit":"phase5-private-host-isolation","canonical_issue":ISSUE_NUMBER,"verification_class":"host-isolation","observed_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),"source_main_sha":expected_main,"result":"PASS" if passed else "BLOCKED","mutation_performed":False,"services":[service],"privacy":{"lan_address_emitted":False,"listener_address_emitted":False,"port_emitted":False,"process_identity_emitted":False,"container_identity_emitted":False,"raw_command_output_emitted":False,"protected_runtime_content_read":False}}

def blocked(reason:str,expected_main:str)->dict[str,Any]:
    return {"schema_version":1,"audit":"phase5-private-host-isolation","canonical_issue":ISSUE_NUMBER,"source_main_sha":expected_main,"result":"BLOCKED","mutation_performed":False,"reason":reason}

def main()->int:
    args=argparse.ArgumentParser(); args.add_argument("--expected-main",required=True); ns=args.parse_args()
    expected=ns.expected_main
    if len(expected)!=40 or any(ch not in "0123456789abcdef" for ch in expected):
        print(json.dumps(blocked("expected_main_invalid",expected),indent=2,sort_keys=True)); return 2
    try:
        _verify_exact_source(expected)
        contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        lan=_primary_lan_address(); listeners=_listeners(_run(["ss","-H","-lnt"]))
        report=build_report(expected_main=expected,contract=contract,listeners=listeners,lan_address=lan)
        print(json.dumps(report,indent=2,sort_keys=True)); return 0 if report["result"]=="PASS" else 3
    except (VerifyError,json.JSONDecodeError,OSError,subprocess.SubprocessError):
        print(json.dumps(blocked("read_only_host_verification_failed",expected),indent=2,sort_keys=True)); return 2
if __name__=="__main__": raise SystemExit(main())
