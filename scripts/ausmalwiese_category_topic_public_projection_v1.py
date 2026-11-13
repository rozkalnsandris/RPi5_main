#!/usr/bin/env python3
"""Materialize the canonical Category↔Topic registry as a public read-only projection (#1464).

Plan mode is read-only. Apply mode can only create the fixed public projection when it
is absent; an existing differing projection is a manual-review STOP. It never edits
Categories, Topics, private links, catalog metadata, media, or service configuration.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
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
CONSUMER_PATH = ROOT / "scripts" / "ausmalwiese_taxonomy_expansion_apply_v1.py"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"

CONTENT = Path("/srv/coloring-pages-content")
PUBLIC = CONTENT / "public"
STATE = CONTENT / "state" / "admin-publish"
CATEGORIES = PUBLIC / "categories.json"
TOPICS = PUBLIC / "topics.json"
LINKS = STATE / "category-topic-links.json"
PROJECTION = PUBLIC / "category-topics.json"
LOCK = CONTENT / "state" / "drive-ingest" / ".lock"
JOBS = STATE / "jobs"

PUBLIC_SCHEMA = "rozkalns.coloring-pages.category-topics.v1"
CONFIRM = "OWNER-AUTHORIZED-AUSMALWIESE-CATEGORY-TOPIC-PUBLIC-PROJECTION"
MAX_PROJECTION = 64 * 1024
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Stop(RuntimeError):
    pass


def stop(message: str) -> None:
    raise Stop(message)


def load_consumer():
    spec = importlib.util.spec_from_file_location("ausmalwiese_taxonomy_projection_consumer", CONSUMER_PATH)
    if spec is None or spec.loader is None:
        stop("taxonomy validator import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if (
        module.CATEGORY_SCHEMA != "rozkalns.coloring-pages.categories.v2"
        or module.TOPIC_SCHEMA != "rozkalns.coloring-pages.topics.v2"
        or module.LINK_SCHEMA != "rozkalns.rpi5-main.category-topic-links.v1"
    ):
        stop("taxonomy validator schema mismatch")
    return module


CONSUMER = load_consumer()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_fixed(path: Path, *, mode: int, limit: int, label: str) -> bytes:
    try:
        st = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            stop(f"unsafe {label} file")
        if (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()) or stat.S_IMODE(st.st_mode) != mode:
            stop(f"unsafe {label} ownership or mode")
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
    return raw


def projection_bytes(doc: Any) -> bytes:
    required = {
        "schema", "revision", "category_revision", "topic_revision",
        "category_sha256", "topic_sha256", "source_links_sha256", "links",
    }
    if not isinstance(doc, dict) or set(doc) != required or doc.get("schema") != PUBLIC_SCHEMA:
        stop("public projection schema invalid")
    for key in ("revision", "category_revision", "topic_revision"):
        if not isinstance(doc[key], int) or isinstance(doc[key], bool) or not 1 <= doc[key] <= 2147483647:
            stop("public projection revision invalid")
    for key in ("category_sha256", "topic_sha256", "source_links_sha256"):
        if not isinstance(doc[key], str) or not SHA256_RE.fullmatch(doc[key]):
            stop("public projection digest invalid")
    if not isinstance(doc["links"], list) or len(doc["links"]) > CONSUMER.MAX_LINKS:
        stop("public projection link count invalid")
    prior = None
    for row in doc["links"]:
        if not isinstance(row, dict) or set(row) != {"category", "topic"}:
            stop("public projection link row invalid")
        pair = (row["category"], row["topic"])
        if not all(isinstance(value, str) and CONSUMER.ID_RE.fullmatch(value) for value in pair):
            stop("public projection link ID invalid")
        if prior is not None and pair <= prior:
            stop("public projection links must be ordered unique")
        prior = pair
    raw = canonical_bytes(doc)
    if len(raw) > MAX_PROJECTION:
        stop("public projection too large")
    return raw


def build_projection(categories_raw: bytes, topics_raw: bytes, links_raw: bytes) -> tuple[dict[str, Any], bytes]:
    categories, category_sha, category_ids = CONSUMER.validate_categories(categories_raw)
    topics, topic_sha, topic_index = CONSUMER.validate_topics(topics_raw)
    links, links_sha, _ = CONSUMER.validate_links(links_raw, category_ids, topic_index)
    doc = {
        "schema": PUBLIC_SCHEMA,
        "revision": links["revision"],
        "category_revision": categories["revision"],
        "topic_revision": topics["revision"],
        "category_sha256": category_sha,
        "topic_sha256": topic_sha,
        "source_links_sha256": links_sha,
        "links": links["links"],
    }
    return doc, projection_bytes(doc)


def load_runtime() -> tuple[dict[str, Any], bytes]:
    categories_raw = read_fixed(CATEGORIES, mode=0o644, limit=CONSUMER.MAX_REGISTRY, label="Categories")
    topics_raw = read_fixed(TOPICS, mode=0o644, limit=CONSUMER.MAX_REGISTRY, label="Topics")
    links_raw = read_fixed(LINKS, mode=0o600, limit=CONSUMER.MAX_REGISTRY, label="Category-Topic links")
    return build_projection(categories_raw, topics_raw, links_raw)


def inspect_projection(expected: bytes) -> str:
    if not PROJECTION.exists():
        if PROJECTION.is_symlink():
            stop("public projection target symlink unsafe")
        return "ABSENT"
    raw = read_fixed(PROJECTION, mode=0o644, limit=MAX_PROJECTION, label="public projection")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        stop("public projection JSON invalid")
    if raw != projection_bytes(doc):
        stop("public projection serialization invalid")
    return "IDENTICAL" if raw == expected else "DIFFERENT"


def public_summary(doc: dict[str, Any], raw: bytes, status: str, mutation_started: bool) -> dict[str, Any]:
    return {
        "status": status,
        "mutation_started": mutation_started,
        "schema": doc["schema"],
        "revision": doc["revision"],
        "category_revision": doc["category_revision"],
        "topic_revision": doc["topic_revision"],
        "category_sha256": doc["category_sha256"],
        "topic_sha256": doc["topic_sha256"],
        "source_links_sha256": doc["source_links_sha256"],
        "projection_sha256": hashlib.sha256(raw).hexdigest(),
        "link_count": len(doc["links"]),
        "target": "/category-topics.json",
    }


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


def assert_idle() -> None:
    if JOBS.is_dir():
        for path in sorted(JOBS.glob("*/job.json")):
            raw = read_fixed(path, mode=0o600, limit=256 * 1024, label="job state")
            try:
                job = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                stop("job state invalid")
            if isinstance(job, dict) and job.get("status") in {"queued", "running"}:
                stop("active publication job blocks public projection materialization")
    for pattern, parent in (
        (".category-topics.public-projection.*.tmp", PROJECTION.parent),
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
    handle = None
    try:
        st = LOCK.lstat()
        if LOCK.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            stop("shared publication lock unsafe")
        if stat.S_IMODE(st.st_mode) != 0o600 or (st.st_uid, st.st_gid) != (os.geteuid(), os.getegid()):
            stop("shared publication lock ownership or mode unsafe")
        handle = LOCK.open("r+b", buffering=0)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except BlockingIOError:
        if handle is not None:
            handle.close()
        stop("shared publication lock busy")
    except Stop:
        if handle is not None and not handle.closed:
            handle.close()
        raise
    except OSError:
        if handle is not None and not handle.closed:
            handle.close()
        stop("shared publication lock unavailable")


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(expected: bytes) -> None:
    temp = PROJECTION.with_name(".category-topics.public-projection." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb", buffering=0) as handle:
        os.fchmod(handle.fileno(), 0o644)
        handle.write(expected)
        os.fsync(handle.fileno())
    os.replace(temp, PROJECTION)
    fsync_dir(PROJECTION.parent)
    confirmed = read_fixed(PROJECTION, mode=0o644, limit=MAX_PROJECTION, label="public projection")
    if confirmed != expected:
        stop("public projection post-write verification failed: STOP")


def plan() -> dict[str, Any]:
    doc, raw = load_runtime()
    status = inspect_projection(raw)
    return public_summary(doc, raw, status=status, mutation_started=False)


def apply() -> dict[str, Any]:
    with acquire_lock():
        assert_idle()
        doc, raw = load_runtime()
        status = inspect_projection(raw)
        if status == "IDENTICAL":
            return public_summary(doc, raw, status="UNCHANGED", mutation_started=False)
        if status != "ABSENT":
            stop("existing public projection differs; manual review required")
        write_once(raw)
        return public_summary(doc, raw, status="PASS", mutation_started=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-source", action="store_true")
    p.add_argument("--expected-source-sha")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p.add_argument("--confirm")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.check_source:
            if args.plan or args.apply or args.confirm:
                stop("--check-source cannot combine with runtime actions")
            print("AUSMALWIESE_CATEGORY_TOPIC_PUBLIC_PROJECTION_SOURCE=PASS issue=1464 live=false")
            return 0
        if not args.expected_source_sha:
            stop("--expected-source-sha required")
        require_source(args.expected_source_sha)
        if args.plan:
            if args.confirm:
                stop("confirmation is forbidden for plan")
            print(json.dumps(plan(), sort_keys=True, separators=(",", ":")))
            return 0
        if args.apply:
            if args.confirm != CONFIRM:
                stop("exact apply confirmation required")
            print(json.dumps(apply(), sort_keys=True, separators=(",", ":")))
            return 0
        stop("select exactly one of --check-source, --plan or --apply")
    except (Stop, OSError, subprocess.SubprocessError) as exc:
        print("AUSMALWIESE_CATEGORY_TOPIC_PUBLIC_PROJECTION=STOP reason=" + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
