#!/usr/bin/env python3
"""Inert-by-default, one-shot owner-gated 21-link taxonomy plan (#1332).

No implicit LIVE rights: --apply requires a separate exact owner authorization,
frozen Git/registry digests, unchanged live taxonomy and a held publish lock.
One stage-file creation + one os.replace; any error is terminal without cleanup.
"""
from __future__ import annotations

import argparse
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
from urllib.request import Request, urlopen

REPO_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
TARGET = Path("/srv/coloring-pages-content/state/admin-publish/category-topic-links.json")
LOCK = Path("/srv/coloring-pages-content/state/drive-ingest/.lock")
SCHEMA = "rozkalns.rpi5-main.category-topic-links.v1"
BASELINE_SHA = "fa0f5200058f6e67e138385fcadb244283539bfb7295e74d1187d2f792b4501c"
CATEGORY_SHA = "fe76364e6245b772d21fb080d982dcbb90de420dd2f2a1056c7a1248d7cab635"
TOPIC_SHA = "a13d970821e96e86ae8a574417610ae2239178c363bbf83c014c7d8b61d1201a"
CATEGORY_IDS = ("tiere", "fahrzeuge", "alphabet", "lernen", "figuren", "jahreszeiten")
SEASONAL = (
    "winter", "fasching", "fruehling", "ostern", "muttertag", "sommer",
    "halloween", "herbst", "sankt-martin", "advent", "nikolaus", "weihnachten",
)
EVERGREEN = (
    "obst", "gemuese", "dinosaurier", "bauernhof", "weltraum",
    "blumen", "meerestiere", "sport", "einhoerner",
)
PLAN = tuple(sorted(
    [("jahreszeiten", t) for t in SEASONAL]
    + [("tiere", t) for t in ("dinosaurier", "bauernhof", "meerestiere")]
    + [("lernen", t) for t in ("obst", "gemuese", "weltraum", "blumen", "sport")]
    + [("figuren", "einhoerner")]
))
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class Stop(Exception):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def planned_bytes() -> bytes:
    require(len(PLAN) == 21 and len(set(PLAN)) == 21, "bad fixed pair set")
    require(set(t for _, t in PLAN) == set(SEASONAL) | set(EVERGREEN), "incomplete Topics")
    require(all((c == "jahreszeiten") == (t in SEASONAL) for c, t in PLAN),
            "seasonal/evergreen importer contract")
    require(all(c in CATEGORY_IDS for c, _ in PLAN), "unknown Category")
    return canonical({"schema": SCHEMA, "revision": 2,
                      "links": [{"category": c, "topic": t} for c, t in PLAN]})


def validate_taxonomy(public: dict) -> None:
    cats, topics = public.get("categories"), public.get("topics")
    require(type(cats) is list and type(topics) is list, "invalid public taxonomy")
    require(set(c["id"] for c in cats) == set(CATEGORY_IDS), "Category ID drift")
    kinds = {t["id"]: t["kind"] for t in topics}
    require(len(kinds) == len(topics) == 21 and set(kinds) == set(SEASONAL) | set(EVERGREEN),
            "Topic ID drift")
    require(all(kinds[t] == "seasonal" for t in SEASONAL)
            and all(kinds[t] == "evergreen" for t in EVERGREEN), "Topic kind drift")


def check_existing(path: Path, uid: int, gid: int) -> bytes:
    require(path.parent.is_dir() and not path.parent.is_symlink(), "unsafe registry directory")
    require(not path.is_symlink(), "unsafe registry symlink")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, "unsafe registry type/links")
        require((st.st_uid, st.st_gid) == (uid, gid)
                and stat.S_IMODE(st.st_mode) == 0o600, "unsafe registry owner/mode")
        require(0 < st.st_size <= 65536, "unsafe registry size")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(65537)
    finally:
        os.close(fd)
    require(sha256(data) == BASELINE_SHA, "existing registry SHA drift")
    expected = canonical({"schema": SCHEMA, "revision": 1, "links": []})
    require(data == expected, "existing registry not exact empty revision 1")
    require(not list(path.parent.glob(".category-topic-links.admin.*.tmp")),
            "interrupted registry stage; manual review required")
    return data


def git_info(repo: Path, args: argparse.Namespace) -> None:
    def git(*a: str) -> str:
        result = subprocess.run(["git", "-C", str(repo), *a],
                                capture_output=True, text=True, check=True, timeout=8)
        return result.stdout.strip()
    require(SHA_RE.fullmatch(args.expected_main) is not None, "expected main missing")
    require(SHA_RE.fullmatch(args.expected_operator_blob) is not None, "operator blob missing")
    require(git("rev-parse", "HEAD") == args.expected_main, "Git HEAD drift")
    require(git("branch", "--show-current") == "main", "not on main")
    require(git("remote", "get-url", "origin") == REPO_ORIGIN, "wrong origin")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"), "dirty source")
    source = repo / "scripts/ausmalwiese-category-topic-links-bulk-v1.py"
    require(git("hash-object", str(source)) == args.expected_operator_blob,
            "operator source blob mismatch")


def get_json(path: str) -> dict:
    req = Request("http://127.0.0.1:8765" + path,
                  headers={"X-Ausmalwiese-Admin": "1", "Cache-Control": "no-store"})
    with urlopen(req, timeout=10) as response:
        require(response.status == 200 and response.geturl() == req.full_url,
                "unexpected API response")
        data = response.read(131073)
    require(0 < len(data) <= 131072, "unexpected API response size")
    result = json.loads(data)
    require(type(result) is dict, "unexpected API schema")
    return result


def verify_runtime() -> None:
    active = get_json("/api/jobs/active")
    require(active.get("active") is False and active.get("job") is None, "publication busy")
    validate_taxonomy(get_json("/api/categories"))
    links = get_json("/api/category-topics/manage")
    require(links.get("enabled") is True and links.get("revision") == 1
            and links.get("links") == [] and links.get("registry_sha256") == BASELINE_SHA
            and links.get("category_sha256") == CATEGORY_SHA
            and links.get("topic_sha256") == TOPIC_SHA, "protected taxonomy/link drift")


def replace_once(path: Path, payload: bytes, uid: int, gid: int) -> None:
    # FIRST MUTATION: no retry, rollback, cleanup or alternate path after this.
    stage = path.parent / (".category-topic-links.admin." + secrets.token_hex(8) + ".tmp")
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb", buffering=0) as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)
        os.fsync(stream.fileno())
    os.replace(stage, path)
    dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    after_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(after_fd)
        require(info.st_nlink == 1 and stat.S_ISREG(info.st_mode)
                and (info.st_uid, info.st_gid) == (uid, gid)
                and stat.S_IMODE(info.st_mode) == 0o600, "postwrite metadata drift")
        require(os.read(after_fd, 65537) == payload, "postwrite bytes mismatch")
    finally:
        os.close(after_fd)


def apply(args: argparse.Namespace) -> None:
    require(args.confirm == "OWNER-AUTHORIZED-EXACT-21-LINKS-ONE-SHOT",
            "exact owner authorization not supplied")
    require(args.expected_registry_sha == BASELINE_SHA
            and args.expected_category_sha == CATEGORY_SHA
            and args.expected_topic_sha == TOPIC_SHA, "expected registry digests not exact")
    payload = planned_bytes()
    require(args.expected_plan_sha == sha256(payload), "proposed mapping SHA mismatch")
    require(os.uname().nodename.split(".")[0] == "rpi5", "wrong host")
    identity = pwd.getpwnam("andris")
    group = grp.getgrnam("andris")
    require(os.geteuid() == identity.pw_uid and os.getegid() == group.gr_gid,
            "not the unprivileged owner")
    repo = Path(__file__).resolve().parent.parent
    git_info(repo, args)
    require(LOCK.is_file() and not LOCK.is_symlink(), "unsafe publication lock")
    lockst = LOCK.stat()
    require((lockst.st_uid, lockst.st_gid) == (identity.pw_uid, group.gr_gid)
            and stat.S_IMODE(lockst.st_mode) == 0o600 and lockst.st_nlink == 1,
            "unsafe publication lock metadata")
    with open(LOCK, "r+b", buffering=0) as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_existing(TARGET, identity.pw_uid, group.gr_gid)
        verify_runtime()
        # All immutable SHA and runtime gates passed. Exactly one atomic replacement.
        replace_once(TARGET, payload, identity.pw_uid, group.gr_gid)
    print("EXACT_21_CATEGORY_TOPIC_LINKS=PASS")
    print("REGISTRY_SHA256=" + sha256(payload))
    print("NO_SERVICE_RESTART=true")


def main() -> int:
    p = argparse.ArgumentParser(description="Review inert 21-link plan; apply only under separate exact LIVE authorization")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--confirm")
    p.add_argument("--expected-main")
    p.add_argument("--expected-operator-blob")
    p.add_argument("--expected-registry-sha")
    p.add_argument("--expected-category-sha")
    p.add_argument("--expected-topic-sha")
    p.add_argument("--expected-plan-sha")
    args = p.parse_args()
    try:
        payload = planned_bytes()
        if args.plan:
            print(json.dumps({"operation": "PLAN_ONLY_NO_WRITES",
                "links": [{"category": c, "topic": t} for c, t in PLAN],
                "existing_registry_sha256": BASELINE_SHA,
                "category_sha256": CATEGORY_SHA, "topic_sha256": TOPIC_SHA,
                "next_registry_sha256": sha256(payload)}, ensure_ascii=False, indent=2))
        else:
            apply(args)
        return 0
    except (Stop, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        print("STOP: " + str(error) + " (NO RETRY / ROLLBACK / CLEANUP)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
