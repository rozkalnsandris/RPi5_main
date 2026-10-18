#!/usr/bin/env python3
"""Source-only exact privacy D1 migration planner (#1061 / #996 reconciliation).

This module never executes Wrangler, reads credentials, contacts Cloudflare,
mutates D1, retries, rolls back or cleans up. It validates already-sanitized
Gate A evidence and returns exact future commands as data only.

Gate A is intentionally narrower than the later Worker takeover gate: an
additive D1 schema preparation does not require the currently active Worker to
already match the reviewed replacement Worker.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-privacy-d1-migration-v1.json"

ISSUE = 1061
RECONCILIATION_ISSUE = 996
WORKER = "coloring-pages-stats-v1"
WRANGLER_VERSION = "4.135.0"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "7f07c226105e26c0ca9cf91eb150a3e8f585c5ea"
SOURCE_BLOB = "c2ac9da6e0701103e0041b30db7dfbea4298f96c"
CONFIG_PATH = "cloudflare/wrangler.stats-worker.jsonc"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
DATABASE_BINDING = "DB"
DATABASE_NAME = "coloring-pages-stats-v1"
DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
MIGRATION_PATH = "cloudflare/stats-cookie-like-migration.sql"
MIGRATION_BLOB = "b5346c05cb27de1010dab2027b0b923e999af775"
CLEANUP_PATH = "cloudflare/stats-remove-daily-visitor-hmac.sql"
CLEANUP_BLOB = "a7cffb110adfceb5c1ff4dcd17a7009c549976a5"

SCHEMA = "ausmalwiese.stats-privacy-d1-schema.v1"
REMOTE_SCHEMA = "ausmalwiese.stats-gate-a-remote.v1"
VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\\Z")
STOP = "STOP_STATS_PRIVACY_D1_MIGRATION_SOURCE_ONLY"

KNOWN_BINDINGS = {
    "DB": "d1",
    "RATE_LIMITER": "ratelimit",
    "PUBLIC_ORIGIN": "plain_text",
    "CF_ANALYTICS_HOST": "plain_text",
    "CF_ZONE_TAG": "plain_text",
    "VISITOR_HMAC_KEY": "secret_text",
    "CF_ANALYTICS_API_TOKEN": "secret_text",
}
REQUIRED_GATE_A_BINDINGS = {"DB": "d1"}
PROVENANCE_SOURCES = {"api", "dash", "wrangler"}
PROVENANCE_CLASSES = {"secret_change", "deployment", "upload", "other", "none"}

EXPECTED_POST = {
    "like_cookie_sessions": {
        "kind": "table",
        "columns": [
            {"name": "cookie_hash", "type": "TEXT", "pk": True},
            {"name": "consent_notice_version", "type": "INTEGER", "pk": False},
            {"name": "consent_recorded_at", "type": "TEXT", "pk": False},
            {"name": "expires_at", "type": "INTEGER", "pk": False},
        ],
    },
    "archived_like_totals": {
        "kind": "table",
        "columns": [
            {"name": "page_id", "type": "TEXT", "pk": True},
            {"name": "like_count", "type": "INTEGER", "pk": False},
        ],
    },
    "idx_like_cookie_sessions_expiry": {
        "kind": "index",
        "table": "like_cookie_sessions",
        "columns": ["expires_at"],
    },
}
TARGETS = tuple(EXPECTED_POST)


class Blocked(Exception):
    """Stable source-only stop reason."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _uuid(value: Any, reason: str) -> str:
    need(type(value) is str and VERSION_ID.fullmatch(value) is not None, reason)
    return value


def validate_remote_evidence(snapshot: Any) -> dict[str, Any]:
    """Validate sanitized Gate A evidence without imposing Gate B takeover state."""
    keys = {
        "schema",
        "worker",
        "environment",
        "wrangler_version",
        "reviewed_source",
        "latest_uploaded_version",
        "active_versions",
        "active_provenance",
        "active_bindings",
        "d1",
    }
    need(type(snapshot) is dict and set(snapshot) == keys, "REMOTE_FIELDS")
    need(
        snapshot["schema"] == REMOTE_SCHEMA
        and snapshot["worker"] == WORKER
        and snapshot["environment"] == "production"
        and snapshot["wrangler_version"] == WRANGLER_VERSION,
        "REMOTE_TARGET",
    )

    reviewed = snapshot["reviewed_source"]
    need(
        reviewed == {
            "repository": SOURCE_REPO,
            "commit": SOURCE_COMMIT,
            "worker_blob": SOURCE_BLOB,
            "config_blob": CONFIG_BLOB,
            "migration_blob": MIGRATION_BLOB,
        },
        "REVIEWED_SOURCE_DRIFT",
    )

    _uuid(snapshot["latest_uploaded_version"], "LATEST_VERSION")
    active = snapshot["active_versions"]
    need(type(active) is list and len(active) == 1, "ACTIVE_VERSION_COUNT")
    need(
        type(active[0]) is dict
        and set(active[0]) == {"version_id", "percentage"}
        and type(active[0]["percentage"]) is int
        and active[0]["percentage"] == 100,
        "ACTIVE_TRAFFIC",
    )
    _uuid(active[0]["version_id"], "ACTIVE_VERSION")
    # Deliberately no equality requirement between latest and active. Gate A is
    # additive D1 preparation; Gate B owns exact Worker upload/deploy alignment.

    provenance = snapshot["active_provenance"]
    need(
        type(provenance) is dict
        and set(provenance) == {"source", "last_deployed_from", "annotation_class"}
        and provenance["source"] in PROVENANCE_SOURCES
        and provenance["last_deployed_from"] in PROVENANCE_SOURCES
        and provenance["source"] == provenance["last_deployed_from"]
        and provenance["annotation_class"] in PROVENANCE_CLASSES,
        "ACTIVE_PROVENANCE",
    )

    bindings = snapshot["active_bindings"]
    need(type(bindings) is list and 1 <= len(bindings) <= len(KNOWN_BINDINGS), "BINDING_SET")
    seen: dict[str, str] = {}
    for entry in bindings:
        need(
            type(entry) is dict and set(entry) == {"name", "type"},
            "BINDING_ENTRY",
        )
        name = entry["name"]
        kind = entry["type"]
        need(
            type(name) is str
            and type(kind) is str
            and name in KNOWN_BINDINGS
            and KNOWN_BINDINGS[name] == kind
            and name not in seen,
            "BINDING_DRIFT",
        )
        seen[name] = kind
    for name, kind in REQUIRED_GATE_A_BINDINGS.items():
        need(seen.get(name) == kind, "REQUIRED_GATE_A_BINDING")

    need(
        snapshot["d1"] == {
            "binding": DATABASE_BINDING,
            "database_name": DATABASE_NAME,
            "database_id": DATABASE_ID,
        },
        "D1_IDENTITY_DRIFT",
    )
    return snapshot


def validate_schema_snapshot(snapshot: Any, *, stage: str) -> dict[str, Any]:
    need(stage in {"before", "after"}, "SCHEMA_STAGE")
    need(type(snapshot) is dict and set(snapshot) == {
        "schema", "database_name", "database_id", "objects"
    }, "SCHEMA_FIELDS")
    need(
        snapshot["schema"] == SCHEMA
        and snapshot["database_name"] == DATABASE_NAME
        and snapshot["database_id"] == DATABASE_ID,
        "SCHEMA_DATABASE",
    )
    objects = snapshot["objects"]
    need(
        type(objects) is dict and set(objects) == set(TARGETS),
        "SCHEMA_OBJECT_SET",
    )
    if stage == "before":
        need(all(objects[name] is None for name in TARGETS), "TARGET_ALREADY_PRESENT")
    else:
        need(objects == EXPECTED_POST, "POST_SCHEMA_MISMATCH")
    return snapshot


def schema_read_commands() -> list[list[str]]:
    """Return fixed read-only D1 evidence commands as data."""
    queries = [
        (
            "SELECT name,type,pk FROM pragma_table_info('like_cookie_sessions') "
            "ORDER BY cid"
        ),
        (
            "SELECT name,type,pk FROM pragma_table_info('archived_like_totals') "
            "ORDER BY cid"
        ),
        (
            "SELECT m.tbl_name AS table_name,m.name AS index_name,ii.name AS "
            "column_name FROM sqlite_schema AS m JOIN pragma_index_info(m.name) "
            "AS ii WHERE m.type='index' AND "
            "m.name='idx_like_cookie_sessions_expiry' ORDER BY ii.seqno"
        ),
    ]
    commands = []
    for query in queries:
        commands.append([
            "npx",
            "--yes",
            f"wrangler@{WRANGLER_VERSION}",
            "d1",
            "execute",
            DATABASE_BINDING,
            "--remote",
            "--command",
            query,
            "--json",
            "--config",
            CONFIG_PATH,
        ])
    return commands


def validate_approval(
    remote: dict[str, Any],
    before_schema: dict[str, Any],
    approval: Any,
) -> dict[str, Any]:
    validate_remote_evidence(remote)
    validate_schema_snapshot(before_schema, stage="before")
    expected = {
        "worker": WORKER,
        "database_id": DATABASE_ID,
        "source_commit": SOURCE_COMMIT,
        "source_blob": SOURCE_BLOB,
        "config_blob": CONFIG_BLOB,
        "migration_blob": MIGRATION_BLOB,
        "remote_evidence_sha256": canonical_sha256(remote),
        "pre_schema_sha256": canonical_sha256(before_schema),
        "allow_additive_d1_migration_once": True,
    }
    need(type(approval) is dict and approval == expected, "OWNER_GATE_UNBOUND")
    return approval


def migration_command(
    remote: dict[str, Any],
    before_schema: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    """Return one exact remote additive migration command as data only."""
    validate_approval(remote, before_schema, approval)
    command = [
        "npx",
        "--yes",
        f"wrangler@{WRANGLER_VERSION}",
        "d1",
        "execute",
        DATABASE_BINDING,
        "--remote",
        "--file",
        MIGRATION_PATH,
        "--yes",
        "--config",
        CONFIG_PATH,
    ]
    joined = " ".join(command)
    need(CLEANUP_PATH not in joined, "CLEANUP_NOT_ALLOWED")
    need("--command" not in command, "ARBITRARY_SQL_NOT_ALLOWED")
    need("--local" not in command and "--preview" not in command, "D1_SCOPE")
    return command


def validate_post(
    remote: dict[str, Any],
    before_schema: dict[str, Any],
    after_schema: dict[str, Any],
) -> dict[str, Any]:
    validate_remote_evidence(remote)
    validate_schema_snapshot(before_schema, stage="before")
    return validate_schema_snapshot(after_schema, stage="after")


def check_contract(contract: Any) -> None:
    expected = {
        "schema_version": 2,
        "status": "SOURCE_ONLY_PRIVACY_D1_MIGRATION_NO_LIVE",
        "issue": ISSUE,
        "reconciliation_issue": RECONCILIATION_ISSUE,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "source_blob": SOURCE_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "database_binding": DATABASE_BINDING,
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "migration_path": MIGRATION_PATH,
        "migration_blob": MIGRATION_BLOB,
        "cleanup_path": CLEANUP_PATH,
        "cleanup_blob": CLEANUP_BLOB,
        "cleanup_is_later_separate_gate": True,
        "gate_a_remote_schema": REMOTE_SCHEMA,
        "gate_a_required_bindings": REQUIRED_GATE_A_BINDINGS,
        "gate_a_known_bindings": KNOWN_BINDINGS,
        "visitor_hmac_required_for_gate_a": False,
        "latest_must_equal_active_for_gate_a": False,
        "worker_takeover_gate_unchanged": True,
        "preconditions": [
            "sanitized-gate-a-remote-evidence",
            "single-active-version-100-percent",
            "latest-may-differ-from-active",
            "known-binding-kinds-with-db-required",
            "visitor-hmac-not-required-for-additive-d1-gate",
            "exact-reviewed-source-config-and-migration-blobs",
            "exact-d1-binding-identity",
            "target-schema-objects-absent",
            "owner-gate-binds-remote-and-schema-digests",
        ],
        "postconditions": [
            "like-cookie-session-table-present",
            "archived-like-totals-table-present",
            "expiry-index-present",
            "exact-target-column-shapes",
        ],
        "actions": {
            "run_wrangler": False,
            "cloudflare_request": False,
            "credential_access": False,
            "d1_write": False,
            "worker_upload": False,
            "worker_deploy": False,
            "cron_change": False,
            "cleanup": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
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
    print("STATS_PRIVACY_D1_MIGRATION_OK_SOURCE_ONLY_NO_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
