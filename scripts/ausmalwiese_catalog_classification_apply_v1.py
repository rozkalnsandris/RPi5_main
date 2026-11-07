#!/usr/bin/env python3
"""One-shot Ausmalwiese catalog Category/Topic reclassification operator (#1396).

Source is inert unless --plan or --apply is explicitly selected. Runtime targets are
fixed; callers cannot select catalog, taxonomy, link, lock, or manifest paths.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
CONTENT = Path("/srv/coloring-pages-content")
PUBLIC = CONTENT / "public"
STATE = CONTENT / "state" / "admin-publish"
CATALOG = PUBLIC / "catalog.json"
CATEGORIES = PUBLIC / "categories.json"
TOPICS = PUBLIC / "topics.json"
LINKS = STATE / "category-topic-links.json"
MANIFEST = STATE / "classification-approved-v1.json"
LOCK = CONTENT / "state" / "drive-ingest" / ".lock"
JOBS = STATE / "jobs"

SCHEMA = "ausmalwiese.catalog-classification-apply.v1"
REVIEW_SCHEMA = "ausmalwiese.catalog-classification-review.v2"
CATEGORY_SCHEMA = "rozkalns.coloring-pages.categories.v2"
TOPIC_SCHEMA = "rozkalns.coloring-pages.topics.v2"
LINK_SCHEMA = "rozkalns.rpi5-main.category-topic-links.v1"
CONFIRM = "OWNER-AUTHORIZED-AUSMALWIESE-CATALOG-CLASSIFICATION-APPLY"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_CATALOG = 4 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024
MAX_REGISTRY = 256 * 1024
MAX_ENTRIES = 4096


class Stop(RuntimeError):
    pass


def stop(message: str) -> None:
    raise Stop(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(raw)


def read_regular(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    try:
        st = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            stop(f"unsafe file: {path.name}")
        if not 0 < st.st_size <= limit:
            stop(f"unsafe size: {path.name}")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as handle:
            fst = os.fstat(handle.fileno())
            if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
                stop(f"file identity changed: {path.name}")
            raw = handle.read(limit + 1)
    except Stop:
        raise
    except OSError:
        stop(f"unavailable file: {path.name}")
    if len(raw) > limit:
        stop(f"oversized file: {path.name}")
    return raw, st


def parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        stop(f"invalid JSON: {label}")


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


def membership(entry: dict[str, Any]) -> dict[str, list[str]]:
    primary = entry.get("category")
    categories = entry.get("categories", [primary])
    topics = entry.get("topics", [entry["topic"]] if entry.get("topic") else [])
    if (
        not isinstance(primary, str)
        or not isinstance(categories, list)
        or not categories
        or categories[0] != primary
        or len(categories) > 6
        or any(not isinstance(x, str) or not ID_RE.fullmatch(x) for x in categories)
        or len(categories) != len(set(categories))
        or not isinstance(topics, list)
        or any(not isinstance(x, str) or not ID_RE.fullmatch(x) for x in topics)
        or len(topics) != len(set(topics))
    ):
        stop("invalid catalog membership")
    return {"categories": list(categories), "topics": list(topics)}


def validate_catalog(raw: bytes) -> tuple[list[dict[str, Any]], str]:
    data = parse_json(raw, "catalog")
    if not isinstance(data, list) or not 0 < len(data) <= MAX_ENTRIES:
        stop("catalog shape invalid")
    ids: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            stop("catalog entry invalid")
        ident = entry.get("id")
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in ids:
            stop("catalog id invalid or duplicate")
        ids.add(ident)
        membership(entry)
    return data, sha256(raw)


def validate_categories(raw: bytes) -> tuple[dict[str, Any], str]:
    doc = parse_json(raw, "categories")
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "revision", "categories"}
        or doc["schema"] != CATEGORY_SCHEMA
        or not isinstance(doc["revision"], int)
        or not 1 <= doc["revision"] <= 2147483647
        or not isinstance(doc["categories"], list)
        or not 1 <= len(doc["categories"]) <= 128
    ):
        stop("category registry invalid")
    ids: set[str] = set()
    for row in doc["categories"]:
        if not isinstance(row, dict) or set(row) != {"id", "label"}:
            stop("category row invalid")
        ident = row["id"]
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in ids:
            stop("category id invalid or duplicate")
        ids.add(ident)
    return doc, sha256(raw)


def validate_topics(raw: bytes) -> tuple[dict[str, Any], str]:
    doc = parse_json(raw, "topics")
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "revision", "topics"}
        or doc["schema"] != TOPIC_SCHEMA
        or not isinstance(doc["revision"], int)
        or not 1 <= doc["revision"] <= 2147483647
        or not isinstance(doc["topics"], list)
        or not 1 <= len(doc["topics"]) <= 128
    ):
        stop("topic registry invalid")
    ids: set[str] = set()
    for row in doc["topics"]:
        if not isinstance(row, dict) or row.get("kind") not in {"seasonal", "evergreen"}:
            stop("topic row invalid")
        ident = row.get("id")
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in ids:
            stop("topic id invalid or duplicate")
        ids.add(ident)
    return doc, sha256(raw)


def validate_links(raw: bytes, category_ids: set[str], topic_ids: set[str]) -> tuple[dict[str, Any], str]:
    doc = parse_json(raw, "links")
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "revision", "links"}
        or doc["schema"] != LINK_SCHEMA
        or not isinstance(doc["revision"], int)
        or not 1 <= doc["revision"] <= 2147483647
        or not isinstance(doc["links"], list)
        or len(doc["links"]) > 512
    ):
        stop("link registry invalid")
    pairs: list[tuple[str, str]] = []
    for row in doc["links"]:
        if not isinstance(row, dict) or set(row) != {"category", "topic"}:
            stop("link row invalid")
        pair = (row["category"], row["topic"])
        if pair[0] not in category_ids or pair[1] not in topic_ids:
            stop("link references unknown taxonomy")
        pairs.append(pair)
    if pairs != sorted(set(pairs)):
        stop("links must be ordered unique")
    return doc, sha256(raw)


def validate_assignment(
    value: Any,
    category_ids: set[str],
    topic_ids: set[str],
    links: set[tuple[str, str]],
    *,
    require_topic: bool,
) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != {"categories", "topics"}:
        stop("classification assignment shape invalid")
    categories, topics = value["categories"], value["topics"]
    if (
        not isinstance(categories, list)
        or not 1 <= len(categories) <= 6
        or len(categories) != len(set(categories))
        or any(x not in category_ids for x in categories)
        or not isinstance(topics, list)
        or (require_topic and not topics)
        or len(topics) != len(set(topics))
        or any(x not in topic_ids for x in topics)
    ):
        stop("classification assignment invalid")
    for topic in topics:
        if not any((category, topic) in links for category in categories):
            stop("topic is not linked to selected categories")
    return {"categories": list(categories), "topics": list(topics)}


def manifest_digest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest[key] for key in manifest if key != "manifest_sha256"}


def validate_manifest(
    manifest: Any,
    catalog: list[dict[str, Any]],
    hashes: dict[str, str],
    revisions: dict[str, int],
    category_ids: set[str],
    topic_ids: set[str],
    links: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    required = {
        "schema",
        "source_review_schema",
        "mode",
        "hashes",
        "revisions",
        "review_decisions",
        "manifest_sha256",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        stop("manifest keys invalid")
    if (
        manifest["schema"] != SCHEMA
        or manifest["source_review_schema"] != REVIEW_SCHEMA
        or manifest["mode"] != "APPROVED_APPLY"
    ):
        stop("manifest schema or mode invalid")
    if manifest["hashes"] != hashes or manifest["revisions"] != revisions:
        stop("manifest source hashes/revisions stale")
    digest = manifest["manifest_sha256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        stop("manifest digest invalid")
    if canonical_digest(manifest_digest_payload(manifest)) != digest:
        stop("manifest digest mismatch")

    decisions = manifest["review_decisions"]
    if not isinstance(decisions, list) or len(decisions) != len(catalog):
        stop("manifest must account for every catalog ID")
    current = {entry["id"]: membership(entry) for entry in catalog}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in decisions:
        if not isinstance(row, dict) or set(row) != {
            "id", "decision", "before", "after", "reason", "confidence"
        }:
            stop("review decision shape invalid")
        ident = row["id"]
        if not isinstance(ident, str) or ident not in current or ident in seen:
            stop("review decision ID invalid or duplicate")
        seen.add(ident)
        if row["decision"] not in {"approved", "rejected", "deferred"}:
            stop("pending/unrecognized review decision forbidden")
        if not isinstance(row["reason"], str) or not 1 <= len(row["reason"]) <= 1000:
            stop("review reason invalid")
        if not isinstance(row["confidence"], str) or not 1 <= len(row["confidence"]) <= 32:
            stop("review confidence invalid")
        before = validate_assignment(
            row["before"], category_ids, topic_ids, links, require_topic=False
        )
        after = validate_assignment(
            row["after"], category_ids, topic_ids, links,
            require_topic=row["decision"] == "approved",
        )
        if before != current[ident]:
            stop("manifest before-state does not match current catalog")
        normalized.append({
            "id": ident,
            "decision": row["decision"],
            "before": before,
            "after": after,
        })
    if seen != set(current):
        stop("manifest catalog coverage mismatch")
    return normalized


def load_runtime_state() -> dict[str, Any]:
    catalog_raw, _ = read_regular(CATALOG, MAX_CATALOG)
    categories_raw, _ = read_regular(CATEGORIES, MAX_REGISTRY)
    topics_raw, _ = read_regular(TOPICS, MAX_REGISTRY)
    links_raw, _ = read_regular(LINKS, MAX_REGISTRY)
    manifest_raw, _ = read_regular(MANIFEST, MAX_MANIFEST)

    catalog, catalog_sha = validate_catalog(catalog_raw)
    categories, category_sha = validate_categories(categories_raw)
    topics, topic_sha = validate_topics(topics_raw)
    category_ids = {row["id"] for row in categories["categories"]}
    topic_ids = {row["id"] for row in topics["topics"]}
    links_doc, links_sha = validate_links(links_raw, category_ids, topic_ids)
    link_pairs = {(row["category"], row["topic"]) for row in links_doc["links"]}
    hashes = {
        "catalog_sha256": catalog_sha,
        "category_sha256": category_sha,
        "topic_sha256": topic_sha,
        "links_sha256": links_sha,
    }
    revisions = {
        "category_revision": categories["revision"],
        "topic_revision": topics["revision"],
        "links_revision": links_doc["revision"],
    }
    manifest = parse_json(manifest_raw, "manifest")
    decisions = validate_manifest(
        manifest, catalog, hashes, revisions, category_ids, topic_ids, link_pairs
    )
    return {
        "catalog": catalog,
        "catalog_raw": catalog_raw,
        "hashes": hashes,
        "revisions": revisions,
        "manifest": manifest,
        "decisions": decisions,
    }


def plan(state: dict[str, Any]) -> dict[str, Any]:
    by_id = {row["id"]: row for row in state["decisions"]}
    candidate: list[dict[str, Any]] = []
    changed_ids: list[str] = []
    for original in state["catalog"]:
        entry = dict(original)
        decision = by_id[entry["id"]]
        if decision["decision"] == "approved" and decision["after"] != decision["before"]:
            categories = decision["after"]["categories"]
            topics = decision["after"]["topics"]
            entry["category"] = categories[0]
            entry["categories"] = categories
            entry["topics"] = topics
            entry.pop("topic", None)
            changed_ids.append(entry["id"])
        candidate.append(entry)
    data = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return {
        "candidate": candidate,
        "candidate_bytes": data,
        "changed_ids": changed_ids,
        "changed_count": len(changed_ids),
        "unchanged_count": len(candidate) - len(changed_ids),
        "catalog_before_sha256": state["hashes"]["catalog_sha256"],
        "catalog_after_sha256": sha256(data),
        "manifest_sha256": state["manifest"]["manifest_sha256"],
    }


def assert_idle() -> None:
    if JOBS.is_dir():
        for path in sorted(JOBS.glob("*/job.json")):
            try:
                raw, _ = read_regular(path, 256 * 1024)
                payload = parse_json(raw, "job")
            except Stop:
                stop("job state unreadable")
            if isinstance(payload, dict) and payload.get("status") in {"queued", "running"}:
                stop("active publication job blocks classification apply")
    for pattern, parent in (
        (".catalog.admin.*.tmp", CATALOG.parent),
        (".categories.admin.*.tmp", CATEGORIES.parent),
        (".topics.admin.*.tmp", TOPICS.parent),
        (".category-topic-links.admin.*.tmp", LINKS.parent),
    ):
        if list(parent.glob(pattern)):
            stop("interrupted catalog/taxonomy staging requires manual review")


def acquire_lock():
    try:
        handle = LOCK.open("r+b", buffering=0)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        stop("shared publication lock busy")
    except OSError:
        stop("shared publication lock unavailable")


def write_catalog_once(plan_result: dict[str, Any]) -> str:
    _, st = read_regular(CATALOG, MAX_CATALOG)
    if stat.S_IMODE(st.st_mode) != 0o644:
        stop("catalog mode unsafe")
    if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
        stop("catalog ownership unsafe")
    temp = CATALOG.with_name(".catalog.classification." + secrets.token_hex(8) + ".tmp")
    data = plan_result["candidate_bytes"]
    # First filesystem mutation. From this line onward no retry/rollback/cleanup.
    fd = os.open(
        temp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o644,
    )
    with os.fdopen(fd, "wb", buffering=0) as handle:
        os.fchmod(handle.fileno(), 0o644)
        handle.write(data)
        os.fsync(handle.fileno())
    os.replace(temp, CATALOG)
    dirfd = os.open(CATALOG.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)
    confirmed_raw, _ = read_regular(CATALOG, MAX_CATALOG)
    confirmed, confirmed_sha = validate_catalog(confirmed_raw)
    if confirmed != plan_result["candidate"] or confirmed_sha != plan_result["catalog_after_sha256"]:
        stop("post-write catalog verification failed: STOP")
    return confirmed_sha


def execute_apply(expected_manifest_sha: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_manifest_sha):
        stop("expected manifest SHA invalid")
    with acquire_lock():
        assert_idle()
        state = load_runtime_state()
        if state["manifest"]["manifest_sha256"] != expected_manifest_sha:
            stop("manifest SHA changed")
        result = plan(state)
        if result["changed_count"] == 0:
            return dict(result, status="UNCHANGED", mutation_started=False)
        new_sha = write_catalog_once(result)
        return dict(result, status="PASS", mutation_started=True, catalog_after_sha256=new_sha)


def public_plan(expected_manifest_sha: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_manifest_sha):
        stop("expected manifest SHA invalid")
    state = load_runtime_state()
    if state["manifest"]["manifest_sha256"] != expected_manifest_sha:
        stop("manifest SHA changed")
    result = plan(state)
    return {
        "status": "PLAN",
        "mutation_started": False,
        "manifest_sha256": result["manifest_sha256"],
        "catalog_before_sha256": result["catalog_before_sha256"],
        "catalog_after_sha256": result["catalog_after_sha256"],
        "changed_count": result["changed_count"],
        "unchanged_count": result["unchanged_count"],
        "changed_ids": result["changed_ids"],
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-source", action="store_true")
    p.add_argument("--expected-source-sha")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--expected-manifest-sha256")
    p.add_argument("--confirm")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.check_source:
            if args.plan or args.apply or args.confirm or args.expected_manifest_sha256:
                stop("--check-source cannot combine with runtime actions")
            print("AUSMALWIESE_CATALOG_CLASSIFICATION_APPLY_SOURCE=PASS issue=1396 live=false")
            return 0
        if not args.expected_source_sha:
            stop("--expected-source-sha required")
        require_source(args.expected_source_sha)
        if not args.expected_manifest_sha256:
            stop("--expected-manifest-sha256 required")
        if args.plan:
            if args.confirm:
                stop("confirmation is forbidden for plan")
            print(json.dumps(public_plan(args.expected_manifest_sha256), sort_keys=True, separators=(",", ":")))
            return 0
        if args.apply:
            if args.confirm != CONFIRM:
                stop("exact apply confirmation required")
            result = execute_apply(args.expected_manifest_sha256)
            safe = {
                key: result[key]
                for key in (
                    "status", "mutation_started", "manifest_sha256",
                    "catalog_before_sha256", "catalog_after_sha256",
                    "changed_count", "unchanged_count", "changed_ids",
                )
            }
            print(json.dumps(safe, sort_keys=True, separators=(",", ":")))
            return 0
        stop("select exactly one of --check-source, --plan or --apply")
    except (Stop, OSError, subprocess.SubprocessError) as exc:
        print("AUSMALWIESE_CATALOG_CLASSIFICATION_APPLY=STOP reason=" + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
