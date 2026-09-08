#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / ".github" / "auto-run-lane-policy-v1.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUIRED = frozenset({"repository","issue_number","lane_class","state","conflict_keys","explicit_dependencies","activation_receipt_issue","runtime_live_authority","head_sha","merge_ready","program_order_blocked"})
class LanePolicyError(RuntimeError): pass

def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("source_worker_limit") != 4: raise LanePolicyError("unsupported lane policy")
    return value

def normalize_lane(value: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != REQUIRED: raise LanePolicyError("lane record shape is incomplete or widened")
    out=dict(value)
    if type(out["repository"]) is not str or REPO.fullmatch(out["repository"]) is None: raise LanePolicyError("repository invalid")
    if type(out["issue_number"]) is not int or out["issue_number"] < 1: raise LanePolicyError("issue invalid")
    if out["lane_class"] not in policy["lane_classes"]: raise LanePolicyError("lane class unknown")
    valid_states=set().union(*policy["states"].values())
    if out["state"] not in valid_states: raise LanePolicyError("lane state unknown")
    for key in ("conflict_keys","explicit_dependencies"):
        v=out[key]
        if type(v) is not list or any(type(x) is not str or not x for x in v) or len(v)!=len(set(v)): raise LanePolicyError(f"{key} invalid")
        out[key]=sorted(v)
    if out["lane_class"] in {"SOURCE_INDEPENDENT","SOURCE_EXCLUSIVE"} and not out["conflict_keys"]: raise LanePolicyError("source conflict evidence required")
    if out["activation_receipt_issue"] != out["issue_number"]: raise LanePolicyError("activation receipt cannot authorize another issue")
    if type(out["runtime_live_authority"]) is not bool or type(out["merge_ready"]) is not bool or type(out["program_order_blocked"]) is not bool: raise LanePolicyError("boolean field invalid")
    if type(out["head_sha"]) is not str or SHA40.fullmatch(out["head_sha"]) is None: raise LanePolicyError("head SHA invalid")
    if out["lane_class"] == "LIVE_EXCLUSIVE" and not out["runtime_live_authority"]: raise LanePolicyError("LIVE_EXCLUSIVE requires frozen LIVE authority")
    if out["lane_class"] != "LIVE_EXCLUSIVE" and out["runtime_live_authority"]: raise LanePolicyError("source/waiting lane cannot inherit LIVE authority")
    if out["lane_class"] in {"WAITING_EXTERNAL","WAITING_OWNER"} and out["state"] != out["lane_class"]: raise LanePolicyError("waiting lane/state mismatch")
    return out

def identity(lane: Mapping[str, Any]) -> str: return f'{lane["repository"]}#{lane["issue_number"]}'
def reconstruct_active_lanes(records: Sequence[Mapping[str, Any]], policy: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
    policy=policy or load_policy(); terminal=set(policy["states"]["terminal"]); seen=set(); out=[]
    for raw in records:
        lane=normalize_lane(raw,policy); key=identity(lane)
        if key in seen: raise LanePolicyError("duplicate issue-local lane state")
        seen.add(key)
        if lane["state"] not in terminal: out.append(lane)
    return sorted(out,key=lambda x:(x["repository"],x["issue_number"]))

def classify(candidate: Mapping[str, Any], active: Sequence[Mapping[str, Any]], policy: Mapping[str, Any] | None=None) -> dict[str, Any]:
    policy=policy or load_policy(); cand=normalize_lane(candidate,policy); lanes=reconstruct_active_lanes(active,policy)
    if cand["program_order_blocked"]: return {"decision":"QUEUED_PROGRAM_ORDER","blockers":["explicit-program-order"]}
    cid=identity(cand)
    if any(identity(x)==cid for x in lanes): return {"decision":"QUEUED_DUPLICATE","blockers":[cid]}
    unresolved=set(cand["explicit_dependencies"]) & {identity(x) for x in lanes}
    if unresolved: return {"decision":"QUEUED_DEPENDENCY","blockers":sorted(unresolved)}
    shared=[]
    for lane in lanes:
        overlap=set(cand["conflict_keys"]) & set(lane["conflict_keys"])
        if overlap: shared.extend(f'{identity(lane)}:{key}' for key in sorted(overlap))
    if shared: return {"decision":"QUEUED_CONFLICT","blockers":sorted(shared)}
    if cand["lane_class"] == "LIVE_EXCLUSIVE":
        live=[identity(x) for x in lanes if x["lane_class"] == "LIVE_EXCLUSIVE"]
        if live: return {"decision":"QUEUED_LIVE_EXCLUSIVE","blockers":sorted(live)}
        return {"decision":"ELIGIBLE","blockers":[]}
    if cand["lane_class"] in {"WAITING_EXTERNAL","WAITING_OWNER"}: return {"decision":"DURABLE_WAIT","blockers":[]}
    runnable=set(policy["states"]["runnable_source"])
    used=sum(1 for x in lanes if x["lane_class"] in {"SOURCE_INDEPENDENT","SOURCE_EXCLUSIVE"} and x["state"] in runnable)
    if used >= policy["source_worker_limit"]: return {"decision":"QUEUED_CAPACITY","blockers":[f'source-workers:{used}/{policy["source_worker_limit"]}']}
    return {"decision":"ELIGIBLE","blockers":[]}

def migrate_legacy_controller(controller: Mapping[str, Any], issue_lane: Mapping[str, Any] | None, policy: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
    policy=policy or load_policy()
    if type(controller) is not dict or controller.get("schema") != policy["legacy_singleton"]["schema"]: raise LanePolicyError("legacy controller schema unknown")
    active=controller.get("active_issue")
    if active is None: return []
    if type(active) is not int or issue_lane is None: raise LanePolicyError("legacy active issue lacks issue-local receipt state")
    lane=normalize_lane(issue_lane,policy)
    if lane["issue_number"] != active: raise LanePolicyError("legacy controller/issue receipt mismatch")
    return [lane]

def main() -> int:
    payload=json.load(sys.stdin); result=classify(payload["candidate"],payload.get("active",[])); print(json.dumps(result,sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
