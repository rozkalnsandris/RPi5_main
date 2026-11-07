#!/usr/bin/env python3
"""Convert one complete #1395 DRY_RUN_ONLY review export to #1396 apply manifest.

Read-only bridge: reads one local JSON file and writes the deterministic apply
manifest to stdout. It never stages files or touches LIVE catalog state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

REVIEW_SCHEMA = "ausmalwiese.catalog-classification-review.v2"
APPLY_SCHEMA = "ausmalwiese.catalog-classification-apply.v1"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT = 4 * 1024 * 1024
MAX_ENTRIES = 4096


class Stop(RuntimeError):
    pass


def stop(message: str) -> None:
    raise Stop(message)


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def same_assignment(a: Any, b: Any) -> bool:
    return a == b


def validate_assignment(value: Any, *, allow_empty_topics: bool) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != {"categories", "topics"}:
        stop("assignment shape invalid")
    categories, topics = value["categories"], value["topics"]
    if (
        not isinstance(categories, list)
        or not 1 <= len(categories) <= 6
        or len(categories) != len(set(categories))
        or any(not isinstance(v, str) or not ID_RE.fullmatch(v) for v in categories)
        or not isinstance(topics, list)
        or (not allow_empty_topics and not topics)
        or len(topics) != len(set(topics))
        or any(not isinstance(v, str) or not ID_RE.fullmatch(v) for v in topics)
    ):
        stop("assignment invalid")
    return {"categories": list(categories), "topics": list(topics)}


def validate_review(review: Any) -> dict[str, Any]:
    expected = {
        "schema", "mode", "complete_review", "hashes", "revisions", "totals",
        "unmatched_title_terms", "approved_changes", "review_decisions",
    }
    if not isinstance(review, dict) or set(review) != expected:
        stop("review export keys invalid")
    if review["schema"] != REVIEW_SCHEMA or review["mode"] != "DRY_RUN_ONLY":
        stop("review export schema/mode invalid")
    if review["complete_review"] is not True:
        stop("review is not complete")

    hashes = review["hashes"]
    if not isinstance(hashes, dict) or set(hashes) != {
        "catalog_sha256", "taxonomy_sha256", "category_sha256",
        "topic_sha256", "links_sha256",
    }:
        stop("review hashes invalid")
    if any(not isinstance(v, str) or not SHA256_RE.fullmatch(v) for v in hashes.values()):
        stop("review hash value invalid")

    revisions = review["revisions"]
    if not isinstance(revisions, dict) or set(revisions) != {
        "category_revision", "topic_revision", "links_revision",
    }:
        stop("review revisions invalid")
    if any(type(v) is not int or not 1 <= v <= 2147483647 for v in revisions.values()):
        stop("review revision value invalid")

    totals = review["totals"]
    required_totals = {
        "published", "missingTopic", "proposed", "needsReview", "approved",
        "rejected", "deferred", "pending", "reviewed", "unmatched",
    }
    if not isinstance(totals, dict) or set(totals) != required_totals:
        stop("review totals invalid")
    if any(type(v) is not int or v < 0 for v in totals.values()):
        stop("review total value invalid")
    if (
        totals["pending"] != 0
        or totals["reviewed"] != totals["published"]
        or totals["approved"] + totals["rejected"] + totals["deferred"] != totals["published"]
    ):
        stop("review totals do not prove complete review")

    decisions = review["review_decisions"]
    if (
        not isinstance(decisions, list)
        or not 1 <= len(decisions) <= MAX_ENTRIES
        or len(decisions) != totals["published"]
    ):
        stop("review decision count invalid")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in decisions:
        if not isinstance(row, dict) or set(row) != {
            "id", "decision", "before", "after", "reason", "confidence"
        }:
            stop("review decision shape invalid")
        ident = row["id"]
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in seen:
            stop("review decision id invalid or duplicate")
        seen.add(ident)
        decision = row["decision"]
        if decision not in {"approved", "rejected", "deferred"}:
            stop("pending/unrecognized decision forbidden")
        before = validate_assignment(row["before"], allow_empty_topics=True)
        after = validate_assignment(
            row["after"], allow_empty_topics=(decision != "approved")
        )
        reason, confidence = row["reason"], row["confidence"]
        if not isinstance(reason, str) or not 1 <= len(reason) <= 1000:
            stop("review reason invalid")
        if not isinstance(confidence, str) or not 1 <= len(confidence) <= 32:
            stop("review confidence invalid")
        normalized.append({
            "id": ident,
            "decision": decision,
            "before": before,
            "after": after,
            "reason": reason,
            "confidence": confidence,
        })

    expected_changes = [
        row for row in normalized
        if row["decision"] == "approved" and not same_assignment(row["before"], row["after"])
    ]
    approved_changes = review["approved_changes"]
    if not isinstance(approved_changes, list):
        stop("approved_changes invalid")
    if approved_changes != expected_changes:
        stop("approved_changes does not match reviewed decisions")

    if not isinstance(review["unmatched_title_terms"], list):
        stop("unmatched title terms invalid")

    return {
        "hashes": hashes,
        "revisions": revisions,
        "review_decisions": normalized,
    }


def convert(review: Any) -> dict[str, Any]:
    checked = validate_review(review)
    manifest = {
        "schema": APPLY_SCHEMA,
        "source_review_schema": REVIEW_SCHEMA,
        "mode": "APPROVED_APPLY",
        "hashes": {
            "catalog_sha256": checked["hashes"]["catalog_sha256"],
            "category_sha256": checked["hashes"]["category_sha256"],
            "topic_sha256": checked["hashes"]["topic_sha256"],
            "links_sha256": checked["hashes"]["links_sha256"],
        },
        "revisions": dict(checked["revisions"]),
        "review_decisions": checked["review_decisions"],
    }
    manifest["manifest_sha256"] = canonical_digest(manifest)
    return manifest


def read_review(path: Path) -> Any:
    try:
        st = path.stat()
        if not path.is_file() or not 0 < st.st_size <= MAX_INPUT:
            stop("review input size/type invalid")
        raw = path.read_bytes()
    except Stop:
        raise
    except OSError:
        stop("review input unavailable")
    if len(raw) > MAX_INPUT:
        stop("review input too large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        stop("review input JSON invalid")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--review", type=Path)
    p.add_argument("--check-source", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.check_source:
            if args.review is not None:
                stop("--check-source cannot combine with --review")
            print("AUSMALWIESE_CLASSIFICATION_REVIEW_TO_APPLY_SOURCE=PASS issue=1396 live=false")
            return 0
        if args.review is None:
            stop("--review is required")
        manifest = convert(read_review(args.review))
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        print("AUSMALWIESE_CLASSIFICATION_REVIEW_TO_APPLY=STOP reason=" + str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
