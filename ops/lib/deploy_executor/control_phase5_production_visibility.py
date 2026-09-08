from __future__ import annotations
from datetime import datetime, timezone
import re
from typing import Any, Mapping
CONTROL_CONSUMER_REPOSITORY="rozkalnsandris/rozkalns-control-center"
CONTROL_CONSUMER_MAIN_SHA="d481e210aea0f2838547622c7471c381dcbdd467"
CONTROL_CONSUMER_PATH="src/shared/production-visibility.ts"
CONTROL_CONSUMER_BLOB_SHA="5546c0fb37072c5903d6e7c6aa02a9eea7baf43d"
FIELDS=("projectId","repository","mainSha","productionSha","deployImpact","runtime","health","rollback","blockerCodes","observedAt")
PROJECTS={"hermes-tech":"rozkalnsandris/hermes-tech","hermes-deals":"rozkalnsandris/hermes-deals","rozkalns-cv":"rozkalnsandris/rozkalns-cv","rpi5-main":"rozkalnsandris/RPi5_main"}
DEPLOY={"NO_DEPLOY","AUTO_DEPLOY_SAFE","MANUAL_ROLLOUT_REQUIRED","DB_HOST_APPLY_REQUIRED","UNKNOWN"}
RUNTIME={"HEALTHY","DEGRADED","UNREACHABLE","UNKNOWN"}; HEALTH={"PASS","FAIL","UNKNOWN"}; ROLLBACK={"AVAILABLE","UNAVAILABLE","UNKNOWN"}
SHA=re.compile(r"^[0-9a-f]{40}$"); IDENT=re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,127}$"); BLOCKER=re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$"); ISO=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
class ProductionVisibilityContractError(RuntimeError):
 def __init__(self,code:str): super().__init__("production visibility source contract failed closed"); self.code=code

def fail(code:str): raise ProductionVisibilityContractError(code)
def parse_time(v:Any)->datetime:
 if type(v) is not str or ISO.fullmatch(v) is None: fail("INVALID_INPUT")
 try: return datetime.strptime(v,"%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
 except ValueError: fail("INVALID_INPUT")
def validate_provenance(p:Mapping[str,Any])->None:
 expected={"consumer_repository":CONTROL_CONSUMER_REPOSITORY,"consumer_main_sha":CONTROL_CONSUMER_MAIN_SHA,"consumer_path":CONTROL_CONSUMER_PATH,"consumer_blob_sha":CONTROL_CONSUMER_BLOB_SHA,"contract_mode":"SOURCE_ONLY_NO_OBSERVATION_AUTHORITY"}
 if type(p) is not dict or p != expected: fail("PROVENANCE_MISMATCH")
def normalize_production_visibility(value:Mapping[str,Any],*,expected_project_id:str,expected_repository:str,expected_main_sha:str,now_iso:str,provenance:Mapping[str,Any])->dict[str,Any]:
 validate_provenance(provenance)
 if type(value) is not dict: fail("INVALID_INPUT")
 if set(value) != set(FIELDS): fail("UNEXPECTED_FIELD" if set(value)-set(FIELDS) else "INVALID_INPUT")
 if type(expected_project_id) is not str or IDENT.fullmatch(expected_project_id) is None or type(expected_repository) is not str or type(expected_main_sha) is not str or SHA.fullmatch(expected_main_sha) is None: fail("INVALID_EXPECTATION")
 if PROJECTS.get(expected_project_id) != expected_repository: fail("INVALID_EXPECTATION")
 if value["projectId"] != expected_project_id or value["repository"] != expected_repository: fail("IDENTITY_MISMATCH")
 if value["mainSha"] != expected_main_sha: fail("MAIN_SHA_MISMATCH")
 if any(type(value[k]) is not str or SHA.fullmatch(value[k]) is None for k in ("mainSha","productionSha")): fail("INVALID_INPUT")
 if value["deployImpact"] not in DEPLOY or value["runtime"] not in RUNTIME or value["health"] not in HEALTH or value["rollback"] not in ROLLBACK: fail("INVALID_INPUT")
 observed=parse_time(value["observedAt"]); now=parse_time(now_iso); age=(now-observed).total_seconds()
 if age < 0 or age > 300: fail("STALE_EVIDENCE")
 blockers=value["blockerCodes"]
 if type(blockers) is not list: fail("INVALID_INPUT")
 if len(blockers)>20: fail("TOO_MANY_BLOCKERS")
 if len(blockers)!=len(set(blockers)): fail("DUPLICATE_BLOCKER")
 if any(type(x) is not str or BLOCKER.fullmatch(x) is None for x in blockers): fail("INVALID_INPUT")
 if value["runtime"]=="UNREACHABLE" and value["health"]=="PASS": fail("CONTRADICTORY_EVIDENCE")
 return {k:(list(value[k]) if k=="blockerCodes" else value[k]) for k in FIELDS}
