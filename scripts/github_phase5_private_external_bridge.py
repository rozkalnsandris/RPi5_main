#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
from typing import Any

REPOSITORY="rozkalnsandris/RPi5_main"
ISSUE_NUMBER=866
OWNER_LOGIN="rozkalnsandris"
OWNER_ID=277435981
CANARY_ID="phase5-private-external-v1"
COMMAND_RE=re.compile(rf"^/rpi5-p5-private-external check HEAD=([0-9a-f]{{40}}) CANARY={re.escape(CANARY_ID)}$")
SHA_RE=re.compile(r"^[0-9a-f]{40}$")

class AuthorizationError(RuntimeError): pass

def authorize_event(event:dict[str,Any], *, repository:str, github_sha:str, run_attempt:str)->dict[str,str]:
    if repository!=REPOSITORY: raise AuthorizationError("repository_mismatch")
    if run_attempt!="1": raise AuthorizationError("workflow_rerun_forbidden")
    if not SHA_RE.fullmatch(github_sha): raise AuthorizationError("github_sha_invalid")
    if event.get("action")!="created": raise AuthorizationError("event_action_mismatch")
    issue=event.get("issue") or {}
    comment=event.get("comment") or {}
    sender=event.get("sender") or {}
    user=comment.get("user") or {}
    if issue.get("number")!=ISSUE_NUMBER or issue.get("pull_request") is not None: raise AuthorizationError("issue_mismatch")
    for actor,label in ((user,"comment"),(sender,"sender")):
        if actor.get("login")!=OWNER_LOGIN or actor.get("id")!=OWNER_ID or actor.get("type")!="User":
            raise AuthorizationError(f"{label}_author_mismatch")
    if comment.get("author_association")!="OWNER": raise AuthorizationError("owner_association_mismatch")
    if comment.get("performed_via_github_app") is not None: raise AuthorizationError("app_authored_comment_forbidden")
    body=comment.get("body")
    match=COMMAND_RE.fullmatch(body) if isinstance(body,str) else None
    if match is None: raise AuthorizationError("command_mismatch")
    expected_sha=match.group(1)
    if expected_sha!=github_sha: raise AuthorizationError("command_sha_not_event_main")
    comment_id=comment.get("id")
    if not isinstance(comment_id,int) or comment_id<=0: raise AuthorizationError("comment_id_invalid")
    return {"expected_sha":expected_sha,"canary":CANARY_ID,"issue_number":str(ISSUE_NUMBER),"comment_id":str(comment_id),"trigger_actor":OWNER_LOGIN}

def write_output(name:str,value:str)->None:
    path=os.environ.get("GITHUB_OUTPUT")
    if not path: raise AuthorizationError("github_output_missing")
    with open(path,"a",encoding="utf-8") as handle: handle.write(f"{name}={value}\n")

def main()->int:
    event_path=os.environ.get("GITHUB_EVENT_PATH")
    if not event_path: print("authorization failed"); return 1
    try:
        event=json.loads(Path(event_path).read_text(encoding="utf-8"))
        outputs=authorize_event(event,repository=os.environ.get("GITHUB_REPOSITORY",""),github_sha=os.environ.get("GITHUB_SHA",""),run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT",""))
        for k,v in outputs.items(): write_output(k,v)
    except (AuthorizationError,json.JSONDecodeError,OSError):
        print("authorization failed"); return 1
    return 0
if __name__=="__main__": raise SystemExit(main())
