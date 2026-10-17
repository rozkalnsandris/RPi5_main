#!/usr/bin/env python3
"""Source-only privileged installation *planner*, NOT an installer command.

A future separately reviewed root-owned installer must enforce the owner LIVE
gate and perform the installation. This file provides fixed source-provenance,
installed-state and path/ownership checks without installing anything.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts/ausmalwiese_report_protected_adapter.py"
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-protected-adapter-v1.json"
EXPECTED_ADAPTER_BLOB = "c8a76aeda339a4216f1a72663c602ff14df1c043"
EXPECTED_CONTRACT_BLOB = "106961d0e54401764f082b4087b3b49bcdcaf0bc"
INSTALL_ROOT = "/usr/local/libexec/rpi5-ausmalwiese-report-protected"
ENTRYPOINT = "/usr/local/sbin/rpi5-ausmalwiese-report-protected"
STOP = "STOP_REPORT_INSTALLER_SOURCE_ONLY"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BLOB = re.compile(r"[0-9a-f]{40}\Z")


class Stop(Exception):
    """Only fixed sanitized error reasons."""


def need(ok: bool, message: str) -> None:
    if not ok:
        raise Stop(message)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii")
                        + b"\x00" + raw).hexdigest()


def verify_source_file(raw: Any, role: str) -> dict[str, str]:
    """Pure source byte check, NEVER follows arbitrary paths from user input."""
    expected = {"adapter": EXPECTED_ADAPTER_BLOB,
                "contract": EXPECTED_CONTRACT_BLOB}
    need(role in expected and type(raw) is bytes
         and 0 < len(raw) <= 70000, "SOURCE_ROLE_OR_SIZE")
    need(git_blob(raw) == expected[role], "SOURCE_BLOB_DRIFT")
    return {"role": role, "blob": expected[role],
            "sha256": hashlib.sha256(raw).hexdigest()}


def install_plan(adapter_raw: bytes, contract_raw: bytes) -> dict[str, Any]:
    """Emit fixed immutable *planned* target paths, never write them."""
    adapter = verify_source_file(adapter_raw, "adapter")
    contract = verify_source_file(contract_raw, "contract")
    try:
        parsed = json.loads(contract_raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise Stop("CONTRACT_ENCODING") from None
    need(type(parsed) is dict
         and parsed.get("schema_version") == 1
         and parsed.get("state") == "SOURCE_ONLY_NOT_INSTALLED"
         and parsed.get("issue") == 1039
         and parsed.get("boundaries", {}).get("allow_install") is False,
         "CONTRACT_NOT_SOURCE_ONLY")
    return {
        "schema": "ausmalwiese.report.protected-install-plan.v1",
        "target": "coloring-pages-report-v1",
        "directory": INSTALL_ROOT,
        "entrypoint": ENTRYPOINT,
        "files": [
            {"path": INSTALL_ROOT + "/adapter.py", "blob": adapter["blob"],
             "sha256": adapter["sha256"], "mode": "0644"},
            {"path": INSTALL_ROOT + "/contract.json", "blob": contract["blob"],
             "sha256": contract["sha256"], "mode": "0644"},
        ],
        "directory_mode": "0755",
        "owner": "root:root",
        "requires_separate_authenticated_owner_install_gate": True,
        "may_install_from_repository_checkout": False,
    }


def verify_install_metadata(metadata: Any, plan: dict[str, Any]) -> None:
    """Only a pure check of externally collected, sanitized file metadata.

    This is NOT evidence that an installed program exists. A trusted,
    separately authorized protected collector must independently lstat
    each path and parent, verify ancestry, and obtain provenance bytes.
    """
    need(type(metadata) is dict and set(metadata) == {
        "parent_chain", "paths",
    }, "METADATA_SCHEMA")
    expected = {
        INSTALL_ROOT: ("directory", 0o755, None),
        ENTRYPOINT: ("file", 0o755, None),
    }
    for item in plan["files"]:
        expected[item["path"]] = ("file", 0o644, item["sha256"])
    actual = metadata["paths"]
    need(type(actual) is dict and set(actual) == set(expected),
         "PATH_SCOPE_DRIFT")
    for path, (kind, mode, sha) in expected.items():
        item = actual[path]
        need(type(item) is dict and set(item) == {
            "kind", "uid", "gid", "mode", "nlink", "sha256",
        }, "FILE_META_FIELDS")
        need(item["kind"] == kind and type(item["uid"]) is int
             and type(item["gid"]) is int
             and item["uid"] == 0 and item["gid"] == 0
             and type(item["mode"]) is int and item["mode"] == mode,
             "FILE_META_UNTRUSTED")
        need(type(item["nlink"]) is int
             and item["nlink"] == (1 if kind == "file" else 2),
             "HARDLINK_OR_DIRECTORY_DRIFT")
        need(item["sha256"] == sha, "FILE_HASH_DRIFT")
    chain = metadata["parent_chain"]
    need(type(chain) is dict
         and set(chain) == {"/", "/usr", "/usr/local", "/usr/local/libexec",
                            "/usr/local/sbin"}, "PARENT_CHAIN")
    for path, record in chain.items():
        need(type(record) is dict and set(record) == {
            "kind", "uid", "gid", "mode", "symlink",
        }, "PARENT_FIELDS")
        need(record["kind"] == "directory"
             and type(record["uid"]) is int and record["uid"] == 0
             and type(record["gid"]) is int and record["gid"] == 0
             and type(record["mode"]) is int and record["mode"] & 0o022 == 0
             and record["symlink"] is False, "UNTRUSTED_PARENT")


def main(argv: list[str] | None = None) -> int:
    # Never accept --install, --apply, --sudo, arbitrary paths or secrets.
    if (sys.argv[1:] if argv is None else argv) != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        plan = install_plan(ADAPTER.read_bytes(), CONTRACT.read_bytes())
        need(plan["target"] == "coloring-pages-report-v1", "TARGET_DRIFT")
    except (Stop, ValueError, OSError, UnicodeError):
        print(STOP)
        return 2
    print("REPORT_INSTALLER_PLAN_OK_NOT_INSTALLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
