#!/usr/bin/env python3
"""Verify the complete runtime baseline archive lineage and current head."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = load_module("v07_review", "runtime-baseline-review-schema.py")
ARCHIVE = load_module("v07_archive", "verify-runtime-baseline-archive.py")
LINEAGE = load_module("v07_lineage", "runtime_baseline_lineage.py")


def fail(message: str) -> None:
    print(f"Runtime baseline lineage verification: FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def safe_existing(path: pathlib.Path, root: pathlib.Path, *, directory: bool = False) -> pathlib.Path:
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if path.is_symlink() or (directory and not path.is_dir()) or (not directory and not path.is_file()):
        raise ValueError("invalid lineage path")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("symlink lineage path")
    if not directory and (path.stat().st_nlink != 1 or path.stat().st_size > 2_000_000):
        raise ValueError("invalid lineage file")
    return resolved


def safe_output(value: str, root: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(value)
    absolute = path if path.is_absolute() else pathlib.Path.cwd() / path
    cursor = pathlib.Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        if cursor.exists() and cursor.is_symlink():
            raise ValueError("symlink lineage output")
    resolved = absolute.resolve(strict=False)
    if not any(str(resolved).startswith(str(root / name) + os.sep) for name in ("evidence", "exports")):
        raise ValueError("lineage output outside evidence/exports")
    if resolved.exists():
        raise ValueError("refusing lineage output overwrite")
    return resolved


def write_atomic(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".v07-lineage-", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive")
    parser.add_argument("--current")
    parser.add_argument("--markdown")
    parser.add_argument("--json-out")
    parser.add_argument("--markdown-out")
    arguments = parser.parse_args()

    try:
        root = V.repo_root().resolve()
        archive = safe_existing(
            pathlib.Path(arguments.archive) if arguments.archive else root / "baselines/runtime/archive",
            root,
            directory=True,
        )
        current = safe_existing(
            pathlib.Path(arguments.current) if arguments.current else root / "baselines/runtime/current.json",
            root,
        )
        current_markdown = safe_existing(
            pathlib.Path(arguments.markdown) if arguments.markdown else root / "docs/CURRENT_RUNTIME_BASELINE.md",
            root,
        )
        if bool(arguments.json_out) != bool(arguments.markdown_out):
            raise ValueError("both lineage outputs are required")

        index = ARCHIVE.verify(archive)
        current_data = V.load_canonical(current)
        if current_markdown.read_text(encoding="utf-8") != V.DOC.render(current_data):
            raise ValueError("current lineage Markdown mismatch")
        current_binding = LINEAGE.binding_from_baseline(current, current_data)

        transitions = []
        for entry in index["entries"]:
            entry_dir = archive / entry["entry_id"]
            transition = json.loads((entry_dir / "transition.json").read_text(encoding="utf-8"))
            archived = V.load_canonical(entry_dir / "baseline.json")
            archived_binding = LINEAGE.binding_from_baseline(entry_dir / "baseline.json", archived)
            if transition.get("old") != archived_binding:
                raise ValueError("archived lineage binding mismatch")
            transitions.append(transition)

        report = LINEAGE.build_report(index, transitions, current_binding)
        rendered_json = LINEAGE.canonical(report)
        rendered_markdown = LINEAGE.markdown(report)

        if arguments.json_out:
            json_out = safe_output(arguments.json_out, root)
            markdown_out = safe_output(arguments.markdown_out, root)
            if json_out == markdown_out:
                raise ValueError("lineage outputs must differ")
            write_atomic(json_out, rendered_json)
            write_atomic(markdown_out, rendered_markdown)

        print(
            "Runtime baseline lineage verification: PASS "
            f"(entries={report['entry_count']}, head={report['head']['sha256']})"
        )
        return 0
    except Exception as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
