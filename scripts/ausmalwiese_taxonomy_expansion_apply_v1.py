#!/usr/bin/env python3
"""One-shot Ausmalwiese managed Topic/link taxonomy expansion operator (#1426).

Source is inert unless --plan or --apply is explicitly selected. Runtime targets are
fixed; callers cannot select category, topic, link, lock, job, or manifest paths.
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
import unicodedata
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
CONTENT = Path("/srv/coloring-pages-content")
PUBLIC = CONTENT / "public"
STATE = CONTENT / "state" / "admin-publish"
CATEGORIES = PUBLIC / "categories.json"
TOPICS = PUBLIC / "topics.json"
LINKS = STATE / "category-topic-links.json"
MANIFEST = STATE / "taxonomy-expansion-approved-v1.json"
LOCK = CONTENT / "state" / "drive-ingest" / ".lock"
JOBS = STATE / "jobs"

SCHEMA = "ausmalwiese.taxonomy-expansion-apply.v2"
CATEGORY_SCHEMA = "rozkalns.coloring-pages.categories.v2"
TOPIC_SCHEMA = "rozkalns.coloring-pages.topics.v2"
LINK_SCHEMA = "rozkalns.rpi5-main.category-topic-links.v1"
CONFIRM = "OWNER-AUTHORIZED-AUSMALWIESE-TAXONOMY-EXPANSION-APPLY"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_REGISTRY = 256 * 1024
MAX_MANIFEST = 512 * 1024
MAX_TOPICS = 128
MAX_LINKS = 512
MAX_ADDITIONS = 64
MAX_CATEGORY_ADDITIONS = 8


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


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


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


def validate_category_object(category: Any) -> dict[str, str]:
    if not isinstance(category, dict) or set(category) != {"id", "label"}:
        stop("category object invalid")
    ident, label = category["id"], category["label"]
    if not isinstance(ident, str) or len(ident) > 48 or not ID_RE.fullmatch(ident):
        stop("category ID invalid")
    if (
        not isinstance(label, str)
        or not 1 <= len(label) <= 80
        or label != label.strip()
        or unicodedata.normalize("NFC", label) != label
        or any(unicodedata.category(ch)[0] == "C" for ch in label)
    ):
        stop("category label invalid")
    return {"id": ident, "label": label}


def validate_categories(raw: bytes) -> tuple[dict[str, Any], str, set[str]]:
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
        normalized = validate_category_object(row)
        ident = normalized["id"]
        if ident in ids:
            stop("category registry duplicate ID")
        ids.add(ident)
    if raw != canonical_bytes(doc):
        stop("category registry noncanonical")
    return doc, sha256(raw), ids


def validate_topic_object(topic: Any) -> dict[str, Any]:
    if not isinstance(topic, dict) or topic.get("kind") not in {"seasonal", "evergreen"}:
        stop("topic object invalid")
    required = {"id", "label", "icon", "kind", "legacy_terms"}
    if topic["kind"] == "seasonal":
        required |= {"active_from", "active_to"}
    if set(topic) != required:
        stop("topic fields invalid")
    ident = topic["id"]
    if not isinstance(ident, str) or len(ident) > 48 or not ID_RE.fullmatch(ident):
        stop("topic ID invalid")
    label, icon, terms = topic["label"], topic["icon"], topic["legacy_terms"]
    if (
        not isinstance(label, str)
        or not 1 <= len(label) <= 80
        or label != label.strip()
        or unicodedata.normalize("NFC", label) != label
        or any(unicodedata.category(ch)[0] == "C" for ch in label)
    ):
        stop("topic label invalid")
    if (
        not isinstance(icon, str)
        or not 1 <= len(icon) <= 12
        or unicodedata.normalize("NFC", icon) != icon
        or any(ch in "<>&" or (unicodedata.category(ch)[0] == "C" and ch != "\u200d") for ch in icon)
    ):
        stop("topic icon invalid")
    if not isinstance(terms, list) or len(terms) > 32:
        stop("topic legacy terms invalid")
    for word in terms:
        if (
            not isinstance(word, str)
            or not 1 <= len(word) <= 64
            or word != word.strip()
            or unicodedata.normalize("NFC", word) != word
            or any(unicodedata.category(ch)[0] == "C" for ch in word)
        ):
            stop("topic legacy term invalid")
    if len(set(terms)) != len(terms):
        stop("topic duplicate legacy terms")
    if topic["kind"] == "seasonal":
        from datetime import date
        for key in ("active_from", "active_to"):
            stamp = topic[key]
            if not isinstance(stamp, str) or re.fullmatch(r"[0-9]{2}-[0-9]{2}", stamp) is None:
                stop("topic seasonal date invalid")
            month, day = map(int, stamp.split("-"))
            try:
                date(2024, month, day)
            except ValueError:
                stop("topic seasonal calendar invalid")
    return dict(topic)


def validate_topics(raw: bytes) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]]]:
    doc = parse_json(raw, "topics")
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "revision", "topics"}
        or doc["schema"] != TOPIC_SCHEMA
        or not isinstance(doc["revision"], int)
        or not 1 <= doc["revision"] <= 2147483647
        or not isinstance(doc["topics"], list)
        or not 1 <= len(doc["topics"]) <= MAX_TOPICS
    ):
        stop("topic registry invalid")
    index: dict[str, dict[str, Any]] = {}
    for row in doc["topics"]:
        normalized = validate_topic_object(row)
        ident = normalized["id"]
        if ident in index:
            stop("topic registry duplicate ID")
        index[ident] = normalized
    if raw != canonical_bytes(doc):
        stop("topic registry noncanonical")
    return doc, sha256(raw), index


def validate_links(
    raw: bytes,
    category_ids: set[str],
    topic_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str, set[tuple[str, str]]]:
    doc = parse_json(raw, "links")
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "revision", "links"}
        or doc["schema"] != LINK_SCHEMA
        or not isinstance(doc["revision"], int)
        or not 1 <= doc["revision"] <= 2147483647
        or not isinstance(doc["links"], list)
        or len(doc["links"]) > MAX_LINKS
    ):
        stop("link registry invalid")
    pairs: list[tuple[str, str]] = []
    for row in doc["links"]:
        if not isinstance(row, dict) or set(row) != {"category", "topic"}:
            stop("link row invalid")
        category, topic = row["category"], row["topic"]
        if category not in category_ids or topic not in topic_index:
            stop("link references unknown taxonomy")
        if (topic_index[topic]["kind"] == "seasonal") != (category == "jahreszeiten"):
            stop("link incompatible with topic kind")
        pairs.append((category, topic))
    if pairs != sorted(set(pairs)):
        stop("links must be ordered unique")
    if raw != canonical_bytes(doc):
        stop("link registry noncanonical")
    return doc, sha256(raw), set(pairs)


def manifest_digest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest[key] for key in manifest if key != "manifest_sha256"}


def validate_manifest(
    manifest: Any,
    *,
    hashes: dict[str, str],
    revisions: dict[str, int],
    category_ids: set[str],
    topic_index: dict[str, dict[str, Any]],
    link_pairs: set[tuple[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    required = {
        "schema", "mode", "hashes", "revisions",
        "categories", "topics", "links", "manifest_sha256",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        stop("manifest keys invalid")
    if manifest["schema"] != SCHEMA or manifest["mode"] != "APPROVED_APPLY":
        stop("manifest schema or mode invalid")
    if manifest["hashes"] != hashes or manifest["revisions"] != revisions:
        stop("manifest source hashes/revisions stale")
    digest = manifest["manifest_sha256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        stop("manifest digest invalid")
    if canonical_digest(manifest_digest_payload(manifest)) != digest:
        stop("manifest digest mismatch")

    category_additions = manifest["categories"]
    topic_additions = manifest["topics"]
    requested_links = manifest["links"]
    if (
        not isinstance(category_additions, list)
        or len(category_additions) > MAX_CATEGORY_ADDITIONS
        or not isinstance(topic_additions, list)
        or len(topic_additions) > MAX_ADDITIONS
        or not isinstance(requested_links, list)
        or len(requested_links) > MAX_ADDITIONS * 6
    ):
        stop("manifest additions invalid")

    new_categories: list[dict[str, str]] = []
    new_category_ids: set[str] = set()
    for row in category_additions:
        category = validate_category_object(row)
        ident = category["id"]
        if ident in category_ids or ident in new_category_ids:
            stop("manifest category already exists or duplicates")
        new_category_ids.add(ident)
        new_categories.append(category)

    new_topics: list[dict[str, Any]] = []
    new_topic_ids: set[str] = set()
    for row in topic_additions:
        topic = validate_topic_object(row)
        ident = topic["id"]
        if ident in topic_index or ident in new_topic_ids:
            stop("manifest topic already exists or duplicates")
        new_topic_ids.add(ident)
        new_topics.append(topic)

    combined_category_ids = set(category_ids) | new_category_ids
    combined_topics = dict(topic_index)
    combined_topics.update({row["id"]: row for row in new_topics})

    new_links: list[dict[str, str]] = []
    pair_seen: set[tuple[str, str]] = set()
    for row in requested_links:
        if not isinstance(row, dict) or set(row) != {"category", "topic"}:
            stop("manifest link shape invalid")
        category, topic = row["category"], row["topic"]
        pair = (category, topic)
        if category not in combined_category_ids or topic not in combined_topics:
            stop("manifest link references unknown taxonomy")
        if pair in link_pairs or pair in pair_seen:
            stop("manifest link already exists or duplicates")
        if (combined_topics[topic]["kind"] == "seasonal") != (category == "jahreszeiten"):
            stop("manifest link incompatible with topic kind")
        pair_seen.add(pair)
        new_links.append({"category": category, "topic": topic})

    if new_topic_ids and not new_topic_ids.issubset({row["topic"] for row in new_links}):
        stop("every new topic requires at least one link")
    if new_category_ids and not new_category_ids.issubset({row["category"] for row in new_links}):
        stop("every new category requires at least one link")
    if not (new_category_ids or new_topic_ids or new_links):
        return [], [], []
    return new_categories, new_topics, new_links

def load_runtime_state() -> dict[str, Any]:
    categories_raw, _ = read_regular(CATEGORIES, MAX_REGISTRY)
    topics_raw, _ = read_regular(TOPICS, MAX_REGISTRY)
    links_raw, _ = read_regular(LINKS, MAX_REGISTRY)
    manifest_raw, _ = read_regular(MANIFEST, MAX_MANIFEST)

    categories, category_sha, category_ids = validate_categories(categories_raw)
    topics, topic_sha, topic_index = validate_topics(topics_raw)
    links_doc, links_sha, link_pairs = validate_links(links_raw, category_ids, topic_index)
    hashes = {
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
    category_additions, topic_additions, requested_links = validate_manifest(
        manifest,
        hashes=hashes,
        revisions=revisions,
        category_ids=category_ids,
        topic_index=topic_index,
        link_pairs=link_pairs,
    )
    return {
        "categories": categories,
        "topics": topics,
        "links": links_doc,
        "hashes": hashes,
        "revisions": revisions,
        "manifest": manifest,
        "category_additions": category_additions,
        "topic_additions": topic_additions,
        "requested_links": requested_links,
        "category_ids": category_ids,
    }


def build_plan(state: dict[str, Any]) -> dict[str, Any]:
    category_additions = state["category_additions"]
    topic_additions = state["topic_additions"]
    requested_links = state["requested_links"]

    categories_doc = {
        "schema": state["categories"]["schema"],
        "revision": state["categories"]["revision"] + (1 if category_additions else 0),
        "categories": list(state["categories"]["categories"]) + category_additions,
    }
    topics_doc = {
        "schema": state["topics"]["schema"],
        "revision": state["topics"]["revision"] + (1 if topic_additions else 0),
        "topics": list(state["topics"]["topics"]) + topic_additions,
    }
    links_doc = {
        "schema": state["links"]["schema"],
        "revision": state["links"]["revision"] + (1 if requested_links else 0),
        "links": sorted(
            list(state["links"]["links"]) + requested_links,
            key=lambda row: (row["category"], row["topic"]),
        ),
    }

    categories_bytes = canonical_bytes(categories_doc)
    topics_bytes = canonical_bytes(topics_doc)
    links_bytes = canonical_bytes(links_doc)
    if (
        len(categories_bytes) > MAX_REGISTRY
        or len(topics_bytes) > MAX_REGISTRY
        or len(links_bytes) > MAX_REGISTRY
    ):
        stop("planned registry exceeds size bound")

    _, _, planned_category_ids = validate_categories(categories_bytes)
    _, _, planned_topic_index = validate_topics(topics_bytes)
    validate_links(links_bytes, planned_category_ids, planned_topic_index)

    return {
        "manifest_sha256": state["manifest"]["manifest_sha256"],
        "category_ids": [row["id"] for row in category_additions],
        "topic_ids": [row["id"] for row in topic_additions],
        "links": [[row["category"], row["topic"]] for row in requested_links],
        "category_add_count": len(category_additions),
        "topic_add_count": len(topic_additions),
        "link_add_count": len(requested_links),
        "category_before_sha256": state["hashes"]["category_sha256"],
        "category_after_sha256": sha256(categories_bytes),
        "topic_before_sha256": state["hashes"]["topic_sha256"],
        "topic_after_sha256": sha256(topics_bytes),
        "links_before_sha256": state["hashes"]["links_sha256"],
        "links_after_sha256": sha256(links_bytes),
        "category_before_revision": state["categories"]["revision"],
        "category_after_revision": categories_doc["revision"],
        "topic_before_revision": state["topics"]["revision"],
        "topic_after_revision": topics_doc["revision"],
        "links_before_revision": state["links"]["revision"],
        "links_after_revision": links_doc["revision"],
        "categories_doc": categories_doc,
        "topics_doc": topics_doc,
        "links_doc": links_doc,
        "categories_bytes": categories_bytes,
        "topics_bytes": topics_bytes,
        "links_bytes": links_bytes,
    }

def public_result(plan_result: dict[str, Any], *, status: str, mutation_started: bool) -> dict[str, Any]:
    keys = (
        "manifest_sha256", "category_ids", "topic_ids", "links",
        "category_add_count", "topic_add_count", "link_add_count",
        "category_before_sha256", "category_after_sha256",
        "topic_before_sha256", "topic_after_sha256",
        "links_before_sha256", "links_after_sha256",
        "category_before_revision", "category_after_revision",
        "topic_before_revision", "topic_after_revision",
        "links_before_revision", "links_after_revision",
    )
    return {"status": status, "mutation_started": mutation_started} | {
        key: plan_result[key] for key in keys
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
                stop("active publication job blocks taxonomy expansion")
    for pattern, parent in (
        (".categories.admin.*.tmp", CATEGORIES.parent),
        (".topics.admin.*.tmp", TOPICS.parent),
        (".category-topic-links.admin.*.tmp", LINKS.parent),
        (".categories.taxonomy-expansion.*.tmp", CATEGORIES.parent),
        (".topics.taxonomy-expansion.*.tmp", TOPICS.parent),
        (".category-topic-links.taxonomy-expansion.*.tmp", LINKS.parent),
    ):
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


def require_write_identity(path: Path, mode: int, label: str) -> None:
    _, st = read_regular(path, MAX_REGISTRY)
    if stat.S_IMODE(st.st_mode) != mode:
        stop(f"{label} mode unsafe")
    if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
        stop(f"{label} ownership unsafe")


def stage(path: Path, prefix: str, data: bytes, mode: int) -> Path:
    temp = path.with_name(prefix + secrets.token_hex(8) + ".tmp")
    fd = os.open(
        temp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    with os.fdopen(fd, "wb", buffering=0) as handle:
        os.fchmod(handle.fileno(), mode)
        handle.write(data)
        os.fsync(handle.fileno())
    return temp


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(plan_result: dict[str, Any]) -> dict[str, str]:
    require_write_identity(CATEGORIES, 0o644, "categories")
    require_write_identity(TOPICS, 0o644, "topics")
    require_write_identity(LINKS, 0o600, "links")
    # First filesystem mutation starts with the first staged file. From here onward
    # there is intentionally no retry, rollback, cleanup, or alternate API loop.
    categories_temp = stage(
        CATEGORIES, ".categories.taxonomy-expansion.", plan_result["categories_bytes"], 0o644
    )
    topics_temp = stage(
        TOPICS, ".topics.taxonomy-expansion.", plan_result["topics_bytes"], 0o644
    )
    links_temp = stage(
        LINKS, ".category-topic-links.taxonomy-expansion.", plan_result["links_bytes"], 0o600
    )

    os.replace(categories_temp, CATEGORIES)
    fsync_dir(CATEGORIES.parent)
    os.replace(topics_temp, TOPICS)
    fsync_dir(TOPICS.parent)
    os.replace(links_temp, LINKS)
    fsync_dir(LINKS.parent)

    categories_raw, _ = read_regular(CATEGORIES, MAX_REGISTRY)
    topics_raw, _ = read_regular(TOPICS, MAX_REGISTRY)
    links_raw, _ = read_regular(LINKS, MAX_REGISTRY)
    categories_doc, category_sha, category_ids = validate_categories(categories_raw)
    topics_doc, topic_sha, topic_index = validate_topics(topics_raw)
    links_doc, links_sha, _ = validate_links(links_raw, category_ids, topic_index)

    if (
        categories_doc != plan_result["categories_doc"]
        or category_sha != plan_result["category_after_sha256"]
    ):
        stop("post-write Categories verification failed: STOP")
    if topics_doc != plan_result["topics_doc"] or topic_sha != plan_result["topic_after_sha256"]:
        stop("post-write Topics verification failed: STOP")
    if links_doc != plan_result["links_doc"] or links_sha != plan_result["links_after_sha256"]:
        stop("post-write links verification failed: STOP")
    return {
        "category_sha256": category_sha,
        "topic_sha256": topic_sha,
        "links_sha256": links_sha,
    }

def public_plan(expected_manifest_sha: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_manifest_sha):
        stop("expected manifest SHA invalid")
    state = load_runtime_state()
    if state["manifest"]["manifest_sha256"] != expected_manifest_sha:
        stop("manifest SHA changed")
    result = build_plan(state)
    status = "UNCHANGED" if (
        result["category_add_count"] == 0
        and result["topic_add_count"] == 0
        and result["link_add_count"] == 0
    ) else "PLAN"
    return public_result(result, status=status, mutation_started=False)


def execute_apply(expected_manifest_sha: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_manifest_sha):
        stop("expected manifest SHA invalid")
    with acquire_lock():
        assert_idle()
        state = load_runtime_state()
        if state["manifest"]["manifest_sha256"] != expected_manifest_sha:
            stop("manifest SHA changed")
        result = build_plan(state)
        if (
            result["category_add_count"] == 0
            and result["topic_add_count"] == 0
            and result["link_add_count"] == 0
        ):
            return public_result(result, status="UNCHANGED", mutation_started=False)
        confirmed = write_once(result)
        result["category_after_sha256"] = confirmed["category_sha256"]
        result["topic_after_sha256"] = confirmed["topic_sha256"]
        result["links_after_sha256"] = confirmed["links_sha256"]
        return public_result(result, status="PASS", mutation_started=True)


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
            print("AUSMALWIESE_TAXONOMY_EXPANSION_APPLY_SOURCE=PASS issue=1431 live=false")
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
            print(json.dumps(execute_apply(args.expected_manifest_sha256), sort_keys=True, separators=(",", ":")))
            return 0
        stop("select exactly one of --check-source, --plan or --apply")
    except (Stop, OSError, subprocess.SubprocessError) as exc:
        print("AUSMALWIESE_TAXONOMY_EXPANSION_APPLY=STOP reason=" + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
