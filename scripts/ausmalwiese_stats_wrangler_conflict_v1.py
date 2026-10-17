#!/usr/bin/env python3
"""Source-only one-time Wrangler strict-conflict takeover planner (#1052).

This module validates sanitized normalized evidence and returns command arrays as
data. It cannot run Wrangler, access credentials, contact Cloudflare, mutate
routes/settings/D1/secrets, deploy traffic, retry, rollback or clean up.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-wrangler-conflict-v1.json"

WORKER = "coloring-pages-stats-v1"
WRANGLER_VERSION = "4.135.0"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "180368f3b81abddde3df94637512436ca50c358f"
SOURCE_PATH = "cloudflare/stats-worker.js"
SOURCE_BLOB = "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4"
CONFIG_PATH = "cloudflare/wrangler.stats-worker.jsonc"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"

BASELINE_VERSION = "e47f145f-1851-4917-be5c-387f96549539"
COMPATIBILITY_DATE = "2026-10-06"
D1 = {
    "binding": "DB",
    "database_name": "coloring-pages-stats-v1",
    "database_id": "f8ac8f1d-a230-4bc4-af13-557c1b91b273",
}
RATE_LIMIT = {
    "binding": "RATE_LIMITER",
    "namespace_id": "1152026106",
    "limit": 100,
    "period": 60,
}
SECRET_NAMES = ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"]
PLAIN_TEXT_VAR_NAMES = ["CF_ANALYTICS_HOST", "CF_ZONE_TAG", "PUBLIC_ORIGIN"]

VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
STOP = "STOP_STATS_WRANGLER_CONFLICT_SOURCE_ONLY"


class Blocked(Exception):
    """Fixed source-only stop reason."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def _uuid(value: Any, reason: str) -> str:
    need(type(value) is str and VERSION_ID.fullmatch(value) is not None, reason)
    return value


def _digest(value: Any, reason: str) -> str:
    need(type(value) is str and DIGEST.fullmatch(value) is not None, reason)
    return value


def canonical_sha256(value: Any) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_snapshot(
    snapshot: Any,
    *,
    stage: str,
    new_version_id: str | None = None,
) -> dict[str, Any]:
    """Validate sanitized trusted-collector evidence, never raw provider JSON."""
    need(stage in {"before", "after_upload"}, "SNAPSHOT_STAGE")
    keys = {
        "schema",
        "worker",
        "environment",
        "wrangler_version",
        "source_commit",
        "source_blob",
        "config_blob",
        "source_class",
        "latest_uploaded_version",
        "active_versions",
        "compatibility_date",
        "compatibility_flags",
        "d1",
        "rate_limit",
        "secret_names",
        "plain_text_vars",
        "settings_sha256",
    }
    need(type(snapshot) is dict and set(snapshot) == keys, "SNAPSHOT_FIELDS")
    need(
        snapshot["schema"]
        == "ausmalwiese.stats-wrangler-conflict-inventory.v1"
        and snapshot["worker"] == WORKER
        and snapshot["environment"] == "production"
        and snapshot["wrangler_version"] == WRANGLER_VERSION
        and snapshot["source_commit"] == SOURCE_COMMIT
        and snapshot["source_blob"] == SOURCE_BLOB
        and snapshot["config_blob"] == CONFIG_BLOB,
        "SNAPSHOT_TARGET",
    )

    latest = _uuid(snapshot["latest_uploaded_version"], "LATEST_VERSION")
    active = snapshot["active_versions"]
    need(type(active) is list and len(active) == 1, "ACTIVE_VERSION_COUNT")
    need(
        type(active[0]) is dict
        and set(active[0]) == {"version_id", "percentage"}
        and type(active[0]["percentage"]) is int
        and active[0]["percentage"] == 100,
        "ACTIVE_TRAFFIC",
    )
    active_id = _uuid(active[0]["version_id"], "ACTIVE_VERSION")

    if stage == "before":
        need(snapshot["source_class"] == "script_api", "CONFLICT_SOURCE_CLASS")
        need(
            latest == BASELINE_VERSION and active_id == BASELINE_VERSION,
            "BASELINE_VERSION_DRIFT",
        )
    else:
        new_id = _uuid(new_version_id, "NEW_VERSION")
        need(new_id != BASELINE_VERSION, "NEW_VERSION_REUSED")
        need(
            snapshot["source_class"] == "wrangler_versions_upload",
            "POST_UPLOAD_SOURCE_CLASS",
        )
        need(latest == new_id, "POST_UPLOAD_LATEST")
        need(active_id == BASELINE_VERSION, "POST_UPLOAD_ACTIVE_DRIFT")

    need(
        snapshot["compatibility_date"] == COMPATIBILITY_DATE
        and snapshot["compatibility_flags"] == [],
        "COMPATIBILITY_DRIFT",
    )
    need(snapshot["d1"] == D1, "D1_DRIFT")
    need(snapshot["rate_limit"] == RATE_LIMIT, "RATE_LIMIT_DRIFT")
    need(snapshot["secret_names"] == SECRET_NAMES, "SECRET_NAME_DRIFT")

    variables = snapshot["plain_text_vars"]
    need(
        type(variables) is dict and sorted(variables) == PLAIN_TEXT_VAR_NAMES,
        "PLAIN_VAR_SET",
    )
    for name in PLAIN_TEXT_VAR_NAMES:
        desc = variables[name]
        need(
            type(desc) is dict
            and set(desc) == {"kind", "fingerprint"}
            and desc["kind"] == "plain_text",
            "PLAIN_VAR_DESCRIPTOR",
        )
        _digest(desc["fingerprint"], "PLAIN_VAR_FINGERPRINT")

    _digest(snapshot["settings_sha256"], "SETTINGS_FINGERPRINT")
    return snapshot


def snapshot_sha256(snapshot: Any, *, stage: str) -> str:
    validate_snapshot(snapshot, stage=stage)
    return canonical_sha256(snapshot)


def validate_approval(before: dict[str, Any], approval: Any) -> dict[str, Any]:
    validate_snapshot(before, stage="before")
    expected = {
        "worker": WORKER,
        "baseline_version": BASELINE_VERSION,
        "inventory_sha256": canonical_sha256(before),
        "allow_non_strict_upload_once": True,
        "allow_deploy_exact_returned_id": True,
    }
    need(type(approval) is dict and approval == expected, "OWNER_GATE_UNBOUND")
    return approval


def takeover_upload_command(
    before: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    """Return the one-time takeover upload command as data; never execute it."""
    validate_approval(before, approval)
    command = [
        "npx",
        "--yes",
        f"wrangler@{WRANGLER_VERSION}",
        "versions",
        "upload",
        SOURCE_PATH,
        "--config",
        CONFIG_PATH,
        "--name",
        WORKER,
        "--no-bundle",
        "--keep-vars",
        "--tag",
        "git:" + SOURCE_COMMIT,
        "--message",
        "source-blob:"
        + SOURCE_BLOB
        + ",config-blob:"
        + CONFIG_BLOB
        + ",takeover-from:"
        + BASELINE_VERSION,
    ]
    need("--strict" not in command, "TAKEOVER_MUST_BE_NON_STRICT")
    for forbidden in ("--route", "--routes", "--secrets-file", "triggers"):
        need(forbidden not in command, "TAKEOVER_COMMAND_SCOPE")
    return command


def validate_post_upload(
    before: dict[str, Any],
    after: dict[str, Any],
    new_version_id: Any,
) -> dict[str, Any]:
    validate_snapshot(before, stage="before")
    new_id = _uuid(new_version_id, "NEW_VERSION")
    validate_snapshot(after, stage="after_upload", new_version_id=new_id)
    need(
        after["plain_text_vars"] == before["plain_text_vars"],
        "POST_UPLOAD_VAR_DRIFT",
    )
    need(after["settings_sha256"] == before["settings_sha256"], "SETTINGS_DRIFT")
    need(after["d1"] == before["d1"], "POST_UPLOAD_D1_DRIFT")
    need(
        after["rate_limit"] == before["rate_limit"],
        "POST_UPLOAD_RATE_LIMIT_DRIFT",
    )
    need(
        after["secret_names"] == before["secret_names"],
        "POST_UPLOAD_SECRET_DRIFT",
    )
    return after


def deploy_command(
    before: dict[str, Any],
    after: dict[str, Any],
    new_version_id: Any,
    approval: dict[str, Any],
) -> list[str]:
    """Return exact-ID 100% deploy command only after post-upload proof."""
    validate_approval(before, approval)
    new_id = _uuid(new_version_id, "NEW_VERSION")
    validate_post_upload(before, after, new_id)
    return [
        "npx",
        "--yes",
        f"wrangler@{WRANGLER_VERSION}",
        "versions",
        "deploy",
        new_id + "@100%",
        "--config",
        CONFIG_PATH,
        "--name",
        WORKER,
        "-y",
    ]


def verify_command() -> list[str]:
    return [
        "curl",
        "--fail-with-body",
        "--silent",
        "--show-error",
        "--head",
        "https://ausmalwiese.de/q",
    ]


def check_contract(contract: Any) -> None:
    expected = {
        "schema_version": 1,
        "status": "SOURCE_ONLY_ONE_TIME_WRANGLER_TAKEOVER_NO_LIVE",
        "issue": 1052,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH,
        "source_blob": SOURCE_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "baseline_version": BASELINE_VERSION,
        "steady_state_strict": True,
        "takeover_strict": False,
        "preconditions": [
            "trusted-normalized-snapshot-only",
            "latest-equals-single-active-100-percent",
            "script-api-conflict-source",
            "exact-compatibility-settings",
            "exact-d1-and-rate-limit",
            "required-secret-names-only",
            "exact-plain-var-set-with-fingerprints",
            "owner-gate-binds-inventory-sha256",
        ],
        "post_upload_gate": [
            "new-full-version-id",
            "new-version-is-latest",
            "old-baseline-remains-active-100-percent",
            "bindings-and-settings-preserved",
        ],
        "actions": {
            "run_wrangler": False,
            "cloudflare_request": False,
            "credential_access": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
            "cleanup": False,
        },
    }
    need(type(contract) is dict and contract == expected, "CONTRACT_DRIFT")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        check_contract(json.loads(CONTRACT.read_text("utf-8")))
    except (Blocked, OSError, ValueError, TypeError):
        print(STOP)
        return 2
    print("STATS_WRANGLER_CONFLICT_PLAN_OK_SOURCE_ONLY_NO_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
