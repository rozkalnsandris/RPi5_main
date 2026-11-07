#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci" / "validate-groups.json"
SCHEMA = "rpi5.validate-groups.v1"


def load_groups() -> dict[str, list[list[str]]]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise SystemExit("validate groups: unsupported manifest schema")
    groups = payload.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise SystemExit("validate groups: groups must be a non-empty object")
    return groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", nargs="?")
    parser.add_argument("--list-groups", action="store_true")
    args = parser.parse_args()

    groups = load_groups()
    if args.list_groups:
        for name in groups:
            print(name)
        return 0
    if not args.group or args.group not in groups:
        raise SystemExit(f"validate groups: unknown group: {args.group!r}")

    commands = groups[args.group]
    if not isinstance(commands, list) or not commands:
        raise SystemExit(f"validate groups: empty group: {args.group}")

    for index, argv in enumerate(commands, start=1):
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(part, str) and part for part in argv)
        ):
            raise SystemExit(
                f"validate groups: invalid command at {args.group}[{index}]"
            )
        print(f"[{args.group} {index}/{len(commands)}] {' '.join(argv)}", flush=True)
        subprocess.run(argv, cwd=ROOT, check=True)

    print(f"VALIDATE_GROUP={args.group} PASS ({len(commands)} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
