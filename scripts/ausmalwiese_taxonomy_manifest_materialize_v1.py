#!/usr/bin/env python3
"""Materialize the exact owner-approved #1395 taxonomy bundle manifest (#1434).

The approved bundle is immutable source data. Runtime paths are fixed. Plan mode is
read-only; materialization requires an exact confirmation and only writes the
generated manifest, never Category/Topic/link registries or catalog metadata.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONSUMER_PATH = ROOT / "scripts" / "ausmalwiese_taxonomy_expansion_apply_v1.py"
BUNDLE_PATH = ROOT / "ops" / "admin" / "coloring-pages" / "taxonomy-approved-1395-v1.json"

CONTENT = Path("/srv/coloring-pages-content")
PUBLIC = CONTENT / "public"
STATE = CONTENT / "state" / "admin-publish"
CATEGORIES = PUBLIC / "categories.json"
TOPICS = PUBLIC / "topics.json"
LINKS = STATE / "category-topic-links.json"
MANIFEST = STATE / "taxonomy-expansion-approved-v1.json"
LOCK = CONTENT / "state" / "drive-ingest" / ".lock"
JOBS = STATE / "jobs"

BUNDLE_SCHEMA = "ausmalwiese.taxonomy-approved-bundle.v1"
BUNDLE_RAW_SHA256 = "15eb5e004b82115d79d2bcb0f4e0fec838f6a62eeb086bae28aad3ca67bffea4"
ISSUE = 1395
PROPOSAL_COMMENT_ID = 6712760996
APPROVAL_COMMENT_ID = 6712767989
CONFIRM = "OWNER-AUTHORIZED-AUSMALWIESE-TAXONOMY-MANIFEST-MATERIALIZE"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MAX_BUNDLE = 128 * 1024
MAX_MANIFEST = 512 * 1024
SHA40_RE = __import__("re").compile(r"^[0-9a-f]{40}$")


class Stop(RuntimeError):
    pass


def stop(message: str) -> None:
    raise Stop(message)


def load_consumer():
    spec = importlib.util.spec_from_file_location("ausmalwiese_taxonomy_consumer_1431", CONSUMER_PATH)
    if spec is None or spec.loader is None:
        stop("consumer import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.SCHEMA != "ausmalwiese.taxonomy-expansion-apply.v2":
        stop("consumer schema mismatch")
    return module


CONSUMER = load_consumer()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_regular(path: Path, limit: int, label: str) -> tuple[bytes, os.stat_result]:
    try:
        st = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            stop(f"unsafe {label} file")
        if not 0 < st.st_size <= limit:
            stop(f"unsafe {label} size")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as handle:
            fst = os.fstat(handle.fileno())
            if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
                stop(f"{label} identity changed")
            raw = handle.read(limit + 1)
    except Stop:
        raise
    except OSError:
        stop(f"{label} unavailable")
    if len(raw) > limit:
        stop(f"{label} oversized")
    return raw, st


def parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        stop(f"invalid {label} JSON")


def require_source(expected_sha: str, runner=subprocess.run) -> None:
    if not SHA40_RE.fullmatch(expected_sha):
        stop("expected source SHA invalid")

    def git(*args: str) -> str:
        cp = runner(
            ["/usr/bin/git", "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"},
        )
        if cp.returncode != 0:
            stop("source git check failed")
        return cp.stdout.decode("utf-8", "strict").strip()

    if git("rev-parse", "HEAD") != expected_sha:
        stop("source HEAD mismatch")
    if git("branch", "--show-current") != "main":
        stop("source branch mismatch")
    if git("remote", "get-url", "origin") != ORIGIN:
        stop("source origin mismatch")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        stop("source checkout dirty")


def load_approved_bundle() -> dict[str, Any]:
    raw, _ = read_regular(BUNDLE_PATH, MAX_BUNDLE, "approved bundle")
    if sha256(raw) != BUNDLE_RAW_SHA256:
        stop("approved bundle raw digest mismatch")
    doc = parse_json(raw, "approved bundle")
    required = {
        "schema", "issue", "proposal_comment_id", "approval_comment_id",
        "categories", "topics", "links",
    }
    if not isinstance(doc, dict) or set(doc) != required:
        stop("approved bundle keys invalid")
    if (
        doc["schema"] != BUNDLE_SCHEMA
        or doc["issue"] != ISSUE
        or doc["proposal_comment_id"] != PROPOSAL_COMMENT_ID
        or doc["approval_comment_id"] != APPROVAL_COMMENT_ID
    ):
        stop("approved bundle provenance mismatch")
    if raw != canonical_bytes(doc):
        stop("approved bundle serialization noncanonical")

    categories = doc["categories"]
    topics = doc["topics"]
    links = doc["links"]
    if not isinstance(categories, list) or len(categories) != 1:
        stop("approved bundle category count invalid")
    if not isinstance(topics, list) or len(topics) != 12:
        stop("approved bundle topic count invalid")
    if not isinstance(links, list) or len(links) != 15:
        stop("approved bundle link count invalid")

    for row in categories:
        CONSUMER.validate_category_object(row)
    for row in topics:
        CONSUMER.validate_topic_object(row)
    for row in links:
        if not isinstance(row, dict) or set(row) != {"category", "topic"}:
            stop("approved bundle link invalid")
    if len({(row["category"], row["topic"]) for row in links}) != len(links):
        stop("approved bundle duplicate link")
    return doc


def load_runtime() -> dict[str, Any]:
    categories_raw, _ = read_regular(CATEGORIES, CONSUMER.MAX_REGISTRY, "categories")
    topics_raw, _ = read_regular(TOPICS, CONSUMER.MAX_REGISTRY, "topics")
    links_raw, _ = read_regular(LINKS, CONSUMER.MAX_REGISTRY, "links")

    categories, category_sha, category_ids = CONSUMER.validate_categories(categories_raw)
    topics, topic_sha, topic_index = CONSUMER.validate_topics(topics_raw)
    links, links_sha, link_pairs = CONSUMER.validate_links(links_raw, category_ids, topic_index)
    return {
        "categories": categories,
        "topics": topics,
        "links": links,
        "hashes": {
            "category_sha256": category_sha,
            "topic_sha256": topic_sha,
            "links_sha256": links_sha,
        },
        "revisions": {
            "category_revision": categories["revision"],
            "topic_revision": topics["revision"],
            "links_revision": links["revision"],
        },
        "category_ids": category_ids,
        "topic_index": topic_index,
        "link_pairs": link_pairs,
    }


def generate() -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = load_approved_bundle()
    runtime = load_runtime()
    manifest = {
        "schema": CONSUMER.SCHEMA,
        "mode": "APPROVED_APPLY",
        "hashes": runtime["hashes"],
        "revisions": runtime["revisions"],
        "categories": bundle["categories"],
        "topics": bundle["topics"],
        "links": bundle["links"],
    }
    manifest["manifest_sha256"] = CONSUMER.canonical_digest(manifest)

    category_additions, topic_additions, requested_links = CONSUMER.validate_manifest(
        manifest,
        hashes=runtime["hashes"],
        revisions=runtime["revisions"],
        category_ids=runtime["category_ids"],
        topic_index=runtime["topic_index"],
        link_pairs=runtime["link_pairs"],
    )
    state = {
        "categories": runtime["categories"],
        "topics": runtime["topics"],
        "links": runtime["links"],
        "hashes": runtime["hashes"],
        "revisions": runtime["revisions"],
        "manifest": manifest,
        "category_additions": category_additions,
        "topic_additions": topic_additions,
        "requested_links": requested_links,
        "category_ids": runtime["category_ids"],
    }
    plan = CONSUMER.build_plan(state)
    return manifest, plan


def public_summary(manifest: dict[str, Any], plan: dict[str, Any], *, status: str, mutation_started: bool) -> dict[str, Any]:
    return {
        "status": status,
        "mutation_started": mutation_started,
        "source_bundle_sha256": BUNDLE_RAW_SHA256,
        "proposal_comment_id": PROPOSAL_COMMENT_ID,
        "approval_comment_id": APPROVAL_COMMENT_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "category_ids": plan["category_ids"],
        "topic_ids": plan["topic_ids"],
        "links": plan["links"],
        "category_before_sha256": plan["category_before_sha256"],
        "category_after_sha256": plan["category_after_sha256"],
        "topic_before_sha256": plan["topic_before_sha256"],
        "topic_after_sha256": plan["topic_after_sha256"],
        "links_before_sha256": plan["links_before_sha256"],
        "links_after_sha256": plan["links_after_sha256"],
        "category_before_revision": plan["category_before_revision"],
        "category_after_revision": plan["category_after_revision"],
        "topic_before_revision": plan["topic_before_revision"],
        "topic_after_revision": plan["topic_after_revision"],
        "links_before_revision": plan["links_before_revision"],
        "links_after_revision": plan["links_after_revision"],
    }


def assert_idle() -> None:
    if JOBS.is_dir():
        for path in sorted(JOBS.glob("*/job.json")):
            raw, _ = read_regular(path, 256 * 1024, "job state")
            payload = parse_json(raw, "job")
            if isinstance(payload, dict) and payload.get("status") in {"queued", "running"}:
                stop("active publication job blocks manifest materialization")
    patterns = (
        ".taxonomy-expansion-approved.materialize.*.tmp",
        ".categories.admin.*.tmp",
        ".topics.admin.*.tmp",
        ".category-topic-links.admin.*.tmp",
        ".categories.taxonomy-expansion.*.tmp",
        ".topics.taxonomy-expansion.*.tmp",
        ".category-topic-links.taxonomy-expansion.*.tmp",
    )
    for pattern in patterns:
        parent = MANIFEST.parent if "taxonomy-expansion-approved" in pattern else (
            CATEGORIES.parent if "categories." in pattern else
            TOPICS.parent if "topics." in pattern and "category-topic" not in pattern else
            LINKS.parent
        )
        if list(parent.glob(pattern)):
            stop("interrupted taxonomy staging requires manual review")


def acquire_lock():
    try:
        st = LOCK.lstat()
        if LOCK.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            stop("shared publication lock unsafe")
        if stat.S_IMODE(st.st_mode) != 0o600:
            stop("shared publication lock mode unsafe")
        if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
            stop("shared publication lock ownership unsafe")
        handle = LOCK.open("r+b", buffering=0)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        stop("shared publication lock busy")
    except Stop:
        raise
    except OSError:
        stop("shared publication lock unavailable")


def require_target_parent() -> None:
    try:
        st = MANIFEST.parent.lstat()
    except OSError:
        stop("manifest parent unavailable")
    if MANIFEST.parent.is_symlink() or not stat.S_ISDIR(st.st_mode):
        stop("manifest parent unsafe")
    if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
        stop("manifest parent ownership unsafe")


def inspect_existing(expected: bytes) -> str:
    if not MANIFEST.exists():
        if MANIFEST.is_symlink():
            stop("manifest target symlink unsafe")
        return "ABSENT"
    raw, st = read_regular(MANIFEST, MAX_MANIFEST, "manifest target")
    if stat.S_IMODE(st.st_mode) != 0o600:
        stop("manifest target mode unsafe")
    if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
        stop("manifest target ownership unsafe")
    if raw != expected:
        stop("existing manifest differs")
    return "IDENTICAL"


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_manifest_once(expected: bytes) -> None:
    temp = MANIFEST.with_name(".taxonomy-expansion-approved.materialize." + secrets.token_hex(8) + ".tmp")
    fd = os.open(
        temp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb", buffering=0) as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(expected)
        os.fsync(handle.fileno())
    os.replace(temp, MANIFEST)
    fsync_dir(MANIFEST.parent)

    raw, st = read_regular(MANIFEST, MAX_MANIFEST, "manifest target")
    if stat.S_IMODE(st.st_mode) != 0o600:
        stop("post-write manifest mode mismatch: STOP")
    if raw != expected:
        stop("post-write manifest verification failed: STOP")


def plan() -> dict[str, Any]:
    manifest, planned = generate()
    return public_summary(manifest, planned, status="PLAN", mutation_started=False)


def materialize() -> dict[str, Any]:
    with acquire_lock():
        assert_idle()
        require_target_parent()
        manifest, planned = generate()
        expected = canonical_bytes(manifest)
        state = inspect_existing(expected)
        if state == "IDENTICAL":
            return public_summary(manifest, planned, status="UNCHANGED", mutation_started=False)
        # The first filesystem mutation begins inside write_manifest_once. From that
        # point, any error is terminal STOP: no retry, rollback, cleanup or fallback.
        write_manifest_once(expected)
        return public_summary(manifest, planned, status="PASS", mutation_started=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-source-sha")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-source", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--emit-summary", action="store_true")
    mode.add_argument("--materialize", action="store_true")
    p.add_argument("--confirm")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.check_source:
            if args.confirm:
                stop("confirmation forbidden for source check")
            load_approved_bundle()
            print("AUSMALWIESE_TAXONOMY_MANIFEST_MATERIALIZER_SOURCE=PASS issue=1434 live=false")
            return 0

        if not args.expected_source_sha:
            stop("--expected-source-sha required")
        require_source(args.expected_source_sha)

        if args.plan or args.emit_summary:
            if args.confirm:
                stop("confirmation forbidden for plan")
            print(json.dumps(plan(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0

        if args.materialize:
            if args.confirm != CONFIRM:
                stop("exact materialize confirmation required")
            print(json.dumps(materialize(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0

        stop("unsupported mode")
    except (Stop, CONSUMER.Stop, OSError, subprocess.SubprocessError) as exc:
        print("AUSMALWIESE_TAXONOMY_MANIFEST_MATERIALIZER=STOP reason=" + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
