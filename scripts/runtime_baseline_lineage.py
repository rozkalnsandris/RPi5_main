#!/usr/bin/env python3
"""Deterministic lineage construction for verified runtime baseline archives."""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

SCHEMA = "rpi5.runtime-baseline-lineage.v1"
BINDING_KEYS = {
    "sha256",
    "collection_utc",
    "source_commit",
    "evidence_manifest_sha256",
    "context",
}


def _exact_keys(value: Any, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid lineage object")


def binding_from_baseline(path: pathlib.Path, data: dict[str, Any]) -> dict[str, Any]:
    metadata = data["metadata"]
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "collection_utc": metadata["collection_utc"],
        "source_commit": metadata["source_commit"],
        "evidence_manifest_sha256": metadata["evidence_manifest_sha256"],
        "context": metadata["context"],
    }


def validate_chain(
    entries: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Validate a continuous, acyclic archive chain ending at current."""
    _exact_keys(current, BINDING_KEYS)
    if len(entries) != len(transitions):
        raise ValueError("lineage transition count mismatch")

    if not entries:
        return {
            "root": dict(current),
            "head": dict(current),
            "transitions": [],
        }

    seen_nodes: set[str] = set()
    seen_reviews: set[str] = set()
    rendered: list[dict[str, Any]] = []
    previous_new: dict[str, Any] | None = None

    for entry, transition in zip(entries, transitions, strict=True):
        required_entry = {
            "entry_id",
            "old_collection_utc",
            "old_sha256",
            "new_collection_utc",
            "new_sha256",
            "review_id",
            "decision",
            "review_level",
            "transition_sha256",
        }
        _exact_keys(entry, required_entry)
        required_transition = {
            "schema",
            "entry_id",
            "old",
            "new",
            "review_id",
            "decision",
            "review_level",
            "diff_json_sha256",
            "diff_markdown_sha256",
            "archive_checksums",
        }
        _exact_keys(transition, required_transition)
        _exact_keys(transition["old"], BINDING_KEYS)
        _exact_keys(transition["new"], BINDING_KEYS)

        if transition["entry_id"] != entry["entry_id"]:
            raise ValueError("lineage entry binding mismatch")
        if transition["review_id"] != entry["review_id"]:
            raise ValueError("lineage review binding mismatch")
        if transition["decision"] != "accepted" or entry["decision"] != "accepted":
            raise ValueError("lineage requires accepted transitions")
        if transition["review_level"] != entry["review_level"]:
            raise ValueError("lineage review level mismatch")

        old = transition["old"]
        new = transition["new"]
        if old["sha256"] != entry["old_sha256"] or new["sha256"] != entry["new_sha256"]:
            raise ValueError("lineage digest mismatch")
        if old["collection_utc"] != entry["old_collection_utc"] or new["collection_utc"] != entry["new_collection_utc"]:
            raise ValueError("lineage timestamp mismatch")
        if new["collection_utc"] <= old["collection_utc"]:
            raise ValueError("lineage chronology regression")

        if previous_new is not None and old != previous_new:
            raise ValueError("lineage continuity gap")
        if entry["review_id"] in seen_reviews:
            raise ValueError("duplicate lineage review")
        seen_reviews.add(entry["review_id"])

        if previous_new is None:
            seen_nodes.add(old["sha256"])
        elif old["sha256"] not in seen_nodes:
            raise ValueError("lineage predecessor missing")
        if new["sha256"] in seen_nodes:
            raise ValueError("lineage cycle or duplicate head")
        seen_nodes.add(new["sha256"])

        rendered.append(
            {
                "entry_id": entry["entry_id"],
                "old": dict(old),
                "new": dict(new),
                "review_id": entry["review_id"],
                "review_level": entry["review_level"],
                "transition_sha256": entry["transition_sha256"],
            }
        )
        previous_new = dict(new)

    if previous_new != current:
        raise ValueError("lineage head does not match current baseline")

    return {
        "root": dict(rendered[0]["old"]),
        "head": dict(current),
        "transitions": rendered,
    }


def build_report(index: dict[str, Any], transitions: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    if set(index) != {"schema", "entries"} or index["schema"] != "rpi5.runtime-baseline-archive-index.v1":
        raise ValueError("unsupported archive index")
    result = validate_chain(index["entries"], transitions, current)
    return {
        "schema": SCHEMA,
        "archive_schema": index["schema"],
        "entry_count": len(index["entries"]),
        "root": result["root"],
        "head": result["head"],
        "transitions": result["transitions"],
        "checks": {
            "archive_verified": True,
            "current_canonical": True,
            "current_markdown_exact": True,
            "continuous": True,
            "acyclic": True,
            "head_matches_current": True,
        },
    }


def canonical(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2) + "\n"


def markdown(report: dict[str, Any]) -> str:
    root = report["root"]
    head = report["head"]
    lines = [
        "# Runtime baseline lineage",
        "",
        f"Schema: `{report['schema']}`",
        "",
        f"Verified transitions: {report['entry_count']}.",
        f"Root: `{root['collection_utc']}` / `{root['sha256']}`.",
        f"Head: `{head['collection_utc']}` / `{head['sha256']}`.",
        "",
        "The lineage is continuous, acyclic, and ends at the exact tracked current baseline.",
        "",
        "## Transitions",
        "",
    ]
    if not report["transitions"]:
        lines.append("- No archived transitions; the current baseline is the standalone lineage head.")
    else:
        for item in report["transitions"]:
            lines.append(
                f"- `{item['entry_id']}`: `{item['old']['sha256']}` → `{item['new']['sha256']}`; "
                f"review `{item['review_id']}`; level `{item['review_level']}`."
            )
    lines += [
        "",
        "## Verification checks",
        "",
    ]
    for name, value in sorted(report["checks"].items()):
        lines.append(f"- `{name}`: `{str(value).lower()}`.")
    lines += [
        "",
        "This is an offline integrity statement over tracked sanitized metadata. It does not collect host data or infer runtime health.",
    ]
    return "\n".join(lines) + "\n"
