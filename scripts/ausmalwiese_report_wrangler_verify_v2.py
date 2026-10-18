#!/usr/bin/env python3
"""Source-only post-deploy provenance verifier for minimal Ausmalwiese reports (#1092)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"ops/contracts/ausmalwiese-report-wrangler-verifier-v2.json"
ISSUE=1092
WORKER="coloring-pages-report-v1"
WRANGLER_VERSION="4.135.0"
SOURCE_COMMIT="16c1ed5cccd43d28212b6a7aefbc04cae5195698"
WORKER_BLOB="4ef00f9963c68ab9a4ab5aeb4a44b8c99c76eda0"
CONFIG_BLOB="2765e88f4c5ee7a01a5380ef52e4ff8c0688c9e6"
DEPLOY_SOURCE="scripts/ausmalwiese_report_wrangler_deploy_v1.py"
DEPLOY_BLOB="06c1a2344657a4fdb14d87cadb5f0560b203daf0"
SETTINGS_METHOD="GET"
SETTINGS_PATH_TEMPLATE="/accounts/{account_id}/workers/scripts/"+WORKER+"/settings"
ANNOTATION_KEYS=("workers/message","workers/tag","workers/triggered_by")
STOP="STOP_REPORT_WRANGLER_VERIFY_V2_SOURCE_ONLY"
class Blocked(Exception): pass
def need(ok,reason):
    if not ok: raise Blocked(reason)
def expected_tag(): return "git:"+SOURCE_COMMIT
def expected_message(): return "source-commit:"+SOURCE_COMMIT+",source-blob:"+WORKER_BLOB+",config-blob:"+CONFIG_BLOB
def validate_annotations(annotations:Any)->dict[str,str]:
    need(type(annotations) is dict and set(annotations)==set(ANNOTATION_KEYS),"ANNOTATION_FIELDS")
    need(type(annotations["workers/tag"]) is str and annotations["workers/tag"]==expected_tag(),"ANNOTATION_TAG_PROVENANCE")
    need(type(annotations["workers/message"]) is str and annotations["workers/message"]==expected_message(),"ANNOTATION_MESSAGE_PROVENANCE")
    value=annotations["workers/triggered_by"]; need(type(value) is str and 1<=len(value)<=256 and all(32<=ord(ch)<127 for ch in value),"ANNOTATION_TRIGGERED_BY_INVALID")
    return annotations
def provenance_adapter(annotations:Any)->dict[str,str]:
    value=validate_annotations(annotations); return {"version_tag":value["workers/tag"],"version_message":value["workers/message"]}
def read_only_verification_plan(version_id:Any)->dict[str,Any]:
    need(type(version_id) is str and len(version_id)==36 and version_id.count("-")==4,"VERSION_ID_INVALID")
    prefix=["npx","--yes",f"wrangler@{WRANGLER_VERSION}"]; suffix=["--name",WORKER,"--config","cloudflare/wrangler.report.json"]
    return {"wrangler_commands":[prefix+["versions","list"]+suffix+["--json"],prefix+["deployments","list"]+suffix+["--json"],prefix+["versions","view",version_id]+suffix+["--json"]],"provider_reads":[{"method":SETTINGS_METHOD,"path_template":SETTINGS_PATH_TEMPLATE,"evidence":"script-and-version-settings.annotations","annotation_keys":list(ANNOTATION_KEYS)}]}
def expected_contract()->dict[str,Any]:
    return {"schema_version":2,"status":"SOURCE_ONLY_REPORT_WRANGLER_VERIFY_NO_NETWORK","issue":ISSUE,"repository":"rozkalnsandris/RPi5_main","worker":WORKER,"wrangler_version":WRANGLER_VERSION,"source_commit":SOURCE_COMMIT,"worker_blob":WORKER_BLOB,"config_blob":CONFIG_BLOB,"deploy_source":DEPLOY_SOURCE,"deploy_blob":DEPLOY_BLOB,"provenance":{"method":SETTINGS_METHOD,"path_template":SETTINGS_PATH_TEMPLATE,"source":"script-and-version-settings.annotations","required_annotation_keys":list(ANNOTATION_KEYS),"adapter_output_keys":["version_tag","version_message"]},"verification":{"wrangler_reads":["versions-list","deployments-list","versions-view"],"secret_inventory_required":False,"public_config_endpoint_required":False,"stats_snapshot_required":False},"actions":{"run_wrangler":False,"cloudflare_request":False,"credential_or_secret_access":False,"host_install":False,"merge":False,"live":False,"retry":False,"rollback":False,"cleanup":False}}
def check_contract(contract): need(type(contract) is dict and contract==expected_contract(),"CONTRACT_DRIFT")
def main(argv=None):
    args=[] if argv is None else argv
    if args!=["--check-contract"]: print(STOP); return 2
    try: check_contract(json.loads(CONTRACT.read_text("utf-8")))
    except (Blocked,OSError,UnicodeError,json.JSONDecodeError,TypeError): print(STOP); return 2
    print("REPORT_WRANGLER_VERIFY_V2_OK_SOURCE_ONLY_NO_NETWORK"); return 0
if __name__=="__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
