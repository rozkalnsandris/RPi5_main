#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

REPOSITORY = "rozkalnsandris/RPi5_main"
ISSUE_NUMBER = 61
OWNER_LOGIN = "rozkalnsandris"
OWNER_ID = 277435981
COMMANDS = {
    "/rpi5-61 check": "check",
    "/rpi5-61 cutover": "cutover",
    "/rpi5-61 verify": "verify-loopback",
}


def fail(reason: str) -> None:
    print(f"authorization failed: {reason}")
    raise SystemExit(1)


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        fail("GITHUB_OUTPUT is missing")
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        fail("repository mismatch")

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        fail("event path is missing")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))

    if event.get("action") != "created":
        fail("event action mismatch")

    issue = event.get("issue") or {}
    comment = event.get("comment") or {}
    sender = event.get("sender") or {}

    if issue.get("number") != ISSUE_NUMBER:
        fail("issue mismatch")
    if issue.get("pull_request") is not None:
        fail("pull-request comments are forbidden")

    comment_user = comment.get("user") or {}
    if comment_user.get("login") != OWNER_LOGIN or comment_user.get("id") != OWNER_ID:
        fail("comment author mismatch")
    if sender.get("login") != OWNER_LOGIN or sender.get("id") != OWNER_ID:
        fail("event sender mismatch")
    if comment.get("author_association") != "OWNER":
        fail("owner association mismatch")

    body = comment.get("body")
    if not isinstance(body, str) or body not in COMMANDS:
        fail("command mismatch")

    comment_id = comment.get("id")
    if not isinstance(comment_id, int) or comment_id <= 0:
        fail("comment id mismatch")

    write_output("operation", COMMANDS[body])
    write_output("issue_number", str(ISSUE_NUMBER))
    write_output("comment_id", str(comment_id))
    write_output("trigger_actor", OWNER_LOGIN)


if __name__ == "__main__":
    main()
