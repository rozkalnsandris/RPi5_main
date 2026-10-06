#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, socket, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from cloudflare_owner_browser_sso_preflight import collect_state
from cloudflare_zero_trust_reconcile import ACCOUNT_ID_RE, DEFAULT_API_BASE, AuditError, CloudflareGetClient, load_registry, resolve_application
from github_p1d04_exact_main_gate import GateError, fetch_and_validate_exact_main

AUDIT_NAME="phase5-private-external-getonly"
CANARY_ID="phase5-private-external-v1"
ISSUE_NUMBER=866
REPOSITORY="rozkalnsandris/RPi5_main"
CONTRACT_PATH=Path("ops/contracts/private-zone-verification-v1.json")
HOST_POLICY_PATH=Path("ops/contracts/cloudflare-hostname-policy.yaml")
REGISTRY_PATH=Path("ops/contracts/ingress-registry-v1.json")
SHA_RE=re.compile(r"^[0-9a-f]{40}$")
ACCESS_SUFFIX=".cloudflareaccess.com"
SELECTOR_CLASS_RE=re.compile(r"^[a-z][a-z0-9_]{0,63}$")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def _policy_action(policy:dict[str,Any])->str:
    value=policy.get("decision",policy.get("action"))
    return value.casefold() if isinstance(value,str) else "unknown"

def _bypass_policy_diagnostics(policies:list[dict[str,Any]])->tuple[str,list[str]]:
    bypass=[policy for policy in policies if isinstance(policy,dict) and _policy_action(policy)=="bypass"]
    if not bypass:
        return "absent",[]
    selector_classes:set[str]=set()
    unknown=False
    for policy in bypass:
        include=policy.get("include")
        if not isinstance(include,list) or not include:
            unknown=True
            continue
        for rule in include:
            if not isinstance(rule,dict) or not rule:
                unknown=True
                continue
            for raw_key in rule:
                key=raw_key.casefold() if isinstance(raw_key,str) else ""
                if SELECTOR_CLASS_RE.fullmatch(key):
                    selector_classes.add(key)
                else:
                    unknown=True
    if "everyone" in selector_classes:
        scope="public"
    elif unknown or not selector_classes:
        scope="unknown"
    else:
        scope="scoped"
    if unknown:
        selector_classes.add("unknown")
    return scope,sorted(selector_classes)

def _bypass_policy_scope_class(policies:list[dict[str,Any]])->str:
    return _bypass_policy_diagnostics(policies)[0]

def _application_domains(app:dict[str,Any])->list[str]:
    values=[]
    domain=app.get("domain")
    if isinstance(domain,str) and domain.strip(): values.append(domain.strip())
    destinations=app.get("destinations")
    if isinstance(destinations,list):
        for item in destinations:
            if isinstance(item,dict) and isinstance(item.get("uri"),str) and item["uri"].strip():
                values.append(item["uri"].strip())
    return list(dict.fromkeys(values))

def _split_domain(value:str)->tuple[str,str]:
    candidate=value.strip()
    if "://" not in candidate: candidate=f"https://{candidate}"
    parsed=urllib.parse.urlparse(candidate)
    return (parsed.hostname or "").casefold(), parsed.path or ""

def _root_path(path:str)->bool: return path in {"","/","/*"}

def _host_pattern_matches(pattern:str,hostname:str)->bool:
    labels=pattern.split(".")
    regex_labels=[re.escape(label).replace(r"\*",r"[^.]*") for label in labels]
    return re.fullmatch(r"^"+r"\.".join(regex_labels)+r"$",hostname,flags=re.IGNORECASE) is not None

def _broader_than_private(app:dict[str,Any], registry:dict[str,Any])->bool:
    for raw in _application_domains(app):
        pattern,path=_split_domain(raw)
        if not pattern or not _root_path(path): continue
        for hostname,item in registry.items():
            if item.trust_class=="FAMILY_PRIVATE": continue
            if _host_pattern_matches(pattern,hostname): return True
    return False

def _load_contract()->dict[str,Any]:
    value=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("schema")!="rozkalns.rpi5-main.private-zone-verification.v1": raise AuditError("private_contract_invalid")
    projections=value.get("service_projections")
    selection=value.get("private_service_selection")
    if not isinstance(projections,list) or len(projections)!=1 or not isinstance(selection,dict): raise AuditError("private_contract_shape_invalid")
    if selection.get("expected_hostnames")!=[projections[0].get("hostname")]: raise AuditError("private_projection_mismatch")
    return value

def _classify_http(status:int,location:str|None)->str:
    if status in {401,403}: return "denied"
    if status in {301,302,303,307,308} and isinstance(location,str):
        host=(urllib.parse.urlparse(location).hostname or "").casefold()
        if host=="cloudflareaccess.com" or host.endswith(ACCESS_SUFFIX): return "access-challenge"
    if 200<=status<500: return "public"
    return "unknown"

def _unauthenticated_class(hostname:str)->str:
    opener=urllib.request.build_opener(NoRedirect())
    request=urllib.request.Request(f"https://{hostname}/",method="GET",headers={"Accept":"text/html,application/xhtml+xml","User-Agent":"RPi5-Phase5-Unauthenticated-Check/1"})
    try:
        response=opener.open(request,timeout=8)
        try: return _classify_http(response.status,response.headers.get("Location"))
        finally: response.close()
    except urllib.error.HTTPError as exc:
        try: return _classify_http(exc.code,exc.headers.get("Location"))
        finally: exc.close()
    except (urllib.error.URLError,TimeoutError,socket.timeout,OSError):
        return "network-error"

def _recovery_ref_present(value:Any)->bool:
    if not isinstance(value,str) or not value or value.startswith("/"): return False
    path=Path(value)
    return ".." not in path.parts and path.is_file()

def build_report(contract:dict[str,Any], registry:dict[str,Any], registry_json:dict[str,Any], state:dict[str,Any], http_class:str)->dict[str,Any]:
    projected=contract["service_projections"][0]
    hostname=projected["hostname"]
    apps=state.get("apps"); policies_by_app=state.get("policies")
    if not isinstance(apps,list) or not isinstance(policies_by_app,dict): raise AuditError("cloudflare_state_shape_invalid")
    resolved=resolve_application(apps,hostname); selected=resolved.get("selected")
    bypass=False; overlap=False; scope="unknown"; bypass_scope="unknown"; bypass_selector_classes=["unknown"]
    if resolved.get("status")=="none":
        scope="missing"
    elif resolved.get("status")=="ambiguous" or not isinstance(selected,dict):
        scope="unknown"
    else:
        app_id=selected.get("id")
        policies=policies_by_app.get(app_id,[]) if isinstance(app_id,str) else []
        bypass_scope,bypass_selector_classes=_bypass_policy_diagnostics(policies)
        bypass=bypass_scope=="public"
        overlap=_broader_than_private(selected,registry)
        if overlap:
            scope="broader-than-private"
        elif resolved.get("status") in {"exact","wildcard"}:
            scope="exact-or-narrow-family"
    if resolved.get("status")=="none" or resolved.get("status")=="ambiguous" or not isinstance(selected,dict):
        bypass_scope="unknown"; bypass_selector_classes=["unknown"]

    registry_services=registry_json.get("services")
    current=next((x for x in registry_services if isinstance(x,dict) and x.get("service_id")==projected["service_id"]),None) if isinstance(registry_services,list) else None
    owner_matches=isinstance(current,dict) and current.get("runtime_owner")==REPOSITORY and projected.get("runtime_owner")==REPOSITORY
    recovery_present=_recovery_ref_present(projected.get("recovery_ref"))
    passed=(scope==projected["expected_access_application_scope"] and http_class in {"access-challenge","denied"} and bypass_scope=="absent" and overlap is False and owner_matches and recovery_present)
    if passed:
        result="PASS"
    elif scope=="unknown" or http_class in {"unknown","network-error"} or bypass_scope in {"scoped","unknown"}:
        result="UNKNOWN"
    else:
        result="FAIL"
    service={"service_id":projected["service_id"],"hostname":hostname,"access_scope_class":scope,"unauthenticated_external_class":http_class,"bypass_policy_scope_class":bypass_scope,"bypass_policy_selector_classes":bypass_selector_classes,"alternate_public_bypass_present":bypass,"admin_or_public_scope_overlap_present":overlap,"runtime_owner_matches":owner_matches,"recovery_ref_present":recovery_present,"result":result}
    return {"schema_version":1,"audit":AUDIT_NAME,"canonical_issue":ISSUE_NUMBER,"verification_class":"unauthenticated-external","result":"PASS" if result=="PASS" else "BLOCKED","mutation_performed":False,"services":[service],"privacy":{"response_body_read":False,"redirect_location_emitted":False,"account_id_emitted":False,"api_token_emitted":False,"app_or_policy_id_emitted":False,"identity_value_emitted":False,"bypass_selector_values_emitted":False,"aud_cookie_or_session_emitted":False,"raw_api_payload_emitted":False}}

def emit_blocked(reason:str)->None:
    print(json.dumps({"schema_version":1,"audit":AUDIT_NAME,"canonical_issue":ISSUE_NUMBER,"result":"BLOCKED","mutation_performed":False,"reason":reason,"privacy":{"response_body_read":False,"account_id_emitted":False,"api_token_emitted":False,"identity_value_emitted":False}},indent=2,sort_keys=True))

def _validate_token(value:str)->None:
    if len(value)<20 or len(value)>4096 or any(ch.isspace() for ch in value): raise AuditError("missing_or_invalid_read_api_token")

def main()->int:
    if os.environ.get("GITHUB_ACTIONS")!="true": emit_blocked("github_actions_required"); return 2
    if os.environ.get("GITHUB_EVENT_NAME")!="issue_comment": emit_blocked("issue_comment_event_required"); return 2
    if os.environ.get("PHASE5_PRIVATE_CANARY")!=CANARY_ID: emit_blocked("canary_binding_mismatch"); return 2
    expected=os.environ.get("PHASE5_EXPECTED_SHA",""); github_sha=os.environ.get("GITHUB_SHA","")
    if not SHA_RE.fullmatch(expected) or github_sha!=expected: emit_blocked("exact_main_sha_binding_invalid"); return 2
    if os.environ.get("GITHUB_RUN_ATTEMPT")!="1": emit_blocked("workflow_rerun_forbidden"); return 2
    if os.environ.get("CLOUDFLARE_API_BASE"): emit_blocked("custom_cloudflare_api_base_forbidden"); return 2
    for name in ("CLOUDFLARE_ACCOUNT_ID","CLOUDFLARE_API_TOKEN","CLOUDFLARE_WRITE_API_TOKEN","CLOUDFLARE_P1D03_OWNER_EMAIL","CLOUDFLARE_P1D04_WRITE_API_TOKEN","CLOUDFLARE_TUNNEL_API_TOKEN"):
        if os.environ.get(name): emit_blocked("non_phase5_cloudflare_env_forbidden"); return 2
    github_token=os.environ.pop("GITHUB_TOKEN","")
    try:
        fetch_and_validate_exact_main(repository=os.environ.get("GITHUB_REPOSITORY",""),expected_sha=expected,github_sha=github_sha,run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT",""),github_token=github_token)
    except GateError:
        emit_blocked("exact_main_gate_failed"); return 2
    account_id=os.environ.pop("CLOUDFLARE_P1D03_ACCOUNT_ID",""); read_token=os.environ.pop("CLOUDFLARE_P1D03_READ_API_TOKEN","")
    try:
        if not ACCOUNT_ID_RE.fullmatch(account_id): raise AuditError("missing_or_invalid_account_id")
        _validate_token(read_token)
        contract=_load_contract(); registry=load_registry(HOST_POLICY_PATH); registry_json=json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        client=CloudflareGetClient(read_token,DEFAULT_API_BASE); state=collect_state(client,account_id)
        read_token=""; account_id=""
        hostname=contract["service_projections"][0]["hostname"]
        report=build_report(contract,registry,registry_json,state,_unauthenticated_class(hostname))
        print(json.dumps(report,indent=2,sort_keys=True))
        return 0 if report["result"]=="PASS" else 3
    except (AuditError,json.JSONDecodeError,OSError):
        emit_blocked("read_only_external_verification_failed"); return 2
if __name__=="__main__": raise SystemExit(main())
