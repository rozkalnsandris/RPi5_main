#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
REPOSITORY="rozkalnsandris/RPi5_main"; ISSUE=841
OWNER_LOGIN="rozkalnsandris"; OWNER_ID=277435981
COMMAND_RE=re.compile(r"^/rpi5-841 (check|apply|verify) HEAD=([0-9a-f]{40}) CANARY=coloring-public-ingress$")
def fail(reason):
    print("authorization failed: "+reason); raise SystemExit(1)
def out(name,value):
    path=os.environ.get("GITHUB_OUTPUT")
    if not path: fail("GITHUB_OUTPUT missing")
    with open(path,"a",encoding="utf-8") as h: h.write(name+"="+value+"\n")
def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY: fail("repository mismatch")
    event_path=os.environ.get("GITHUB_EVENT_PATH")
    if not event_path: fail("event path missing")
    event=json.loads(Path(event_path).read_text(encoding="utf-8"))
    issue=event.get("issue") or {}; comment=event.get("comment") or {}; sender=event.get("sender") or {}
    if event.get("action")!="created" or issue.get("number")!=ISSUE or issue.get("pull_request") is not None: fail("event mismatch")
    user=comment.get("user") or {}
    if user.get("login")!=OWNER_LOGIN or user.get("id")!=OWNER_ID or sender.get("login")!=OWNER_LOGIN or sender.get("id")!=OWNER_ID or comment.get("author_association")!="OWNER": fail("owner mismatch")
    m=COMMAND_RE.fullmatch(comment.get("body") or "")
    if not m: fail("command mismatch")
    expected_sha=m.group(2)
    if os.environ.get("GITHUB_SHA") != expected_sha: fail("default branch SHA mismatch")
    out("operation",m.group(1)); out("expected_sha",expected_sha); out("issue_number",str(ISSUE)); out("comment_id",str(comment.get("id")))
if __name__=="__main__": main()
