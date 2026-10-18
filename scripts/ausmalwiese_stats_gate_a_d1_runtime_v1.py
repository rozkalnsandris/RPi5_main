#!/usr/bin/env python3
"""Exact source-reviewed Gate A D1 migration runtime for Ausmalwiese (#996)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-gate-a-d1-runtime-v1.json"

ISSUE = 996
WORKER = "coloring-pages-stats-v1"
WRANGLER_VERSION = "4.135.0"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "7f07c226105e26c0ca9cf91eb150a3e8f585c5ea"
WORKER_PATH = "cloudflare/stats-worker.js"
WORKER_BLOB = "c2ac9da6e0701103e0041b30db7dfbea4298f96c"
CONFIG_PATH = "cloudflare/wrangler.stats-worker.jsonc"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
MIGRATION_PATH = "cloudflare/stats-cookie-like-migration.sql"
MIGRATION_BLOB = "b5346c05cb27de1010dab2027b0b923e999af775"
DATABASE_BINDING = "DB"
DATABASE_NAME = "coloring-pages-stats-v1"
DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"

REMOTE_SCHEMA = "ausmalwiese.stats-gate-a-remote.v1"
SCHEMA = "ausmalwiese.stats-privacy-d1-schema.v1"
REMOTE_EVIDENCE_SHA256 = "3397daf651bbe60512167817bcef9f02421c71f877bef0a92afc44821fb08af6"
PRE_SCHEMA_SHA256 = "470f40bab9b7e2bfcf68b73cfa3aad7bf171bcb764fdfc391c09d1b4fa85e9f6"

RUNTIME_ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-stats-gate-a-d1-migrate")
RUNTIME_CONFIRM = "OWNER-AUTHORIZED-STATS-GATE-A-D1-MIGRATION"
RUNTIME_OPERATOR = "andris"
RUNTIME_OPERATOR_UID = 1000
RUNTIME_OPERATOR_GID = 1000
RUNTIME_HOME = Path("/home/andris")
RUNTIME_SOURCE_ROOT = RUNTIME_HOME / "coloring-pages"
WRANGLER = RUNTIME_HOME / ".local/bin/wrangler"
WRANGLER_PACKAGE = (
    RUNTIME_HOME / ".local/share/wrangler-cli/node_modules/wrangler/package.json"
)
WRANGLER_LOG_DIR = RUNTIME_HOME / ".wrangler/logs"
RUNTIME_ENV = {
    "HOME": str(RUNTIME_HOME),
    "USER": RUNTIME_OPERATOR,
    "LOGNAME": RUNTIME_OPERATOR,
    "XDG_CONFIG_HOME": str(RUNTIME_HOME / ".config"),
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LC_ALL": "C",
    "WRANGLER_SEND_METRICS": "false",
    "WRANGLER_WRITE_LOGS": "false",
}

UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
KNOWN_BINDINGS = {
    "DB": "d1",
    "RATE_LIMITER": "ratelimit",
    "PUBLIC_ORIGIN": "plain_text",
    "CF_ANALYTICS_HOST": "plain_text",
    "CF_ZONE_TAG": "plain_text",
    "VISITOR_HMAC_KEY": "secret_text",
    "CF_ANALYTICS_API_TOKEN": "secret_text",
}
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
SCHEMA_QUERIES = (
    "SELECT name,type,pk FROM pragma_table_info('like_cookie_sessions') ORDER BY cid",
    "SELECT name,type,pk FROM pragma_table_info('archived_like_totals') ORDER BY cid",
    "SELECT m.tbl_name AS table_name,m.name AS index_name,ii.name AS "
    "column_name FROM sqlite_schema AS m JOIN pragma_index_info(m.name) AS ii "
    "WHERE m.type='index' AND m.name='idx_like_cookie_sessions_expiry' "
    "ORDER BY ii.seqno",
)
STOP = "STOP_STATS_GATE_A_D1_RUNTIME"


class Blocked(Exception):
    pass


class MutationUnknown(Exception):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _uuid(value: Any, reason: str) -> str:
    need(type(value) is str and UUID.fullmatch(value) is not None, reason)
    return value


def runtime_subprocess(
    argv: list[str],
    *,
    runner: Any = subprocess.run,
    timeout: int = 45,
) -> Any:
    try:
        return runner(
            list(argv),
            cwd=str(RUNTIME_SOURCE_ROOT),
            env=dict(RUNTIME_ENV),
            user=RUNTIME_OPERATOR_UID,
            group=RUNTIME_OPERATOR_GID,
            extra_groups=(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=timeout,
            check=False,
        )
    except Exception:
        raise Blocked("RUNTIME_COMMAND_UNAVAILABLE") from None


def git_runtime(args: list[str], *, runner: Any = subprocess.run) -> bytes:
    result = runtime_subprocess(
        ["/usr/bin/git", "-C", str(RUNTIME_SOURCE_ROOT), *args],
        runner=runner,
        timeout=10,
    )
    need(
        result.returncode == 0
        and type(result.stdout) is bytes
        and len(result.stdout) <= 262144,
        "SOURCE_GIT_FAILED",
    )
    return result.stdout


def exact_application_bytes(*, runner: Any = subprocess.run) -> dict[str, bytes]:
    need(
        RUNTIME_SOURCE_ROOT.is_dir() and not RUNTIME_SOURCE_ROOT.is_symlink(),
        "SOURCE_ROOT_UNTRUSTED",
    )
    head = git_runtime(["rev-parse", "HEAD"], runner=runner)
    need(head.decode("ascii").strip() == SOURCE_COMMIT, "SOURCE_COMMIT_DRIFT")
    expected = {
        WORKER_PATH: WORKER_BLOB,
        CONFIG_PATH: CONFIG_BLOB,
        MIGRATION_PATH: MIGRATION_BLOB,
    }
    tree = git_runtime(
        ["ls-tree", "HEAD", "--", *expected.keys()], runner=runner
    ).decode("ascii")
    entries: dict[str, tuple[str, str]] = {}
    for line in tree.splitlines():
        match = re.fullmatch(
            r"(100644|100755) blob ([0-9a-f]{40})\\t(.+)", line
        )
        need(match is not None, "SOURCE_TREE_SHAPE")
        entries[match.group(3)] = (match.group(1), match.group(2))
    need(set(entries) == set(expected), "SOURCE_TREE_SET")
    out: dict[str, bytes] = {}
    for path, blob in expected.items():
        mode, actual_blob = entries[path]
        need(mode == "100644" and actual_blob == blob, "SOURCE_BLOB_DRIFT")
        full = RUNTIME_SOURCE_ROOT / path
        try:
            info = full.lstat()
            raw = full.read_bytes()
        except OSError:
            raise Blocked("SOURCE_FILE_UNAVAILABLE") from None
        need(
            stat.S_ISREG(info.st_mode)
            and not full.is_symlink()
            and info.st_nlink == 1
            and 0 < info.st_size <= 262144,
            "SOURCE_FILE_UNTRUSTED",
        )
        canonical = git_runtime(["show", "HEAD:" + path], runner=runner)
        need(raw == canonical and git_blob(raw) == blob, "SOURCE_BYTE_DRIFT")
        out[path] = raw
    return out


def trusted_runtime_entry(*, lstat: Any = os.lstat) -> None:
    need(os.geteuid() == 0, "RUNTIME_ROOT_REQUIRED")
    need(
        str(Path(__file__).absolute()) == str(RUNTIME_ENTRY),
        "RUNTIME_ENTRY_DRIFT",
    )
    for path in (Path("/"), Path("/usr"), Path("/usr/local"), Path("/usr/local/sbin")):
        try:
            info = lstat(path)
        except OSError:
            raise Blocked("RUNTIME_PARENT_UNAVAILABLE") from None
        need(
            stat.S_ISDIR(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and info.st_uid == 0
            and info.st_gid == 0
            and not (stat.S_IMODE(info.st_mode) & 0o022),
            "RUNTIME_PARENT_UNTRUSTED",
        )
    try:
        entry = lstat(RUNTIME_ENTRY)
    except OSError:
        raise Blocked("RUNTIME_ENTRY_UNAVAILABLE") from None
    need(
        stat.S_ISREG(entry.st_mode)
        and not stat.S_ISLNK(entry.st_mode)
        and entry.st_uid == 0
        and entry.st_gid == 0
        and stat.S_IMODE(entry.st_mode) == 0o500
        and entry.st_nlink == 1,
        "RUNTIME_ENTRY_UNTRUSTED",
    )


def wrangler_package_version() -> str:
    try:
        info = WRANGLER_PACKAGE.lstat()
        package = json.loads(WRANGLER_PACKAGE.read_text("utf-8"))
        binary = WRANGLER.lstat()
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Blocked("WRANGLER_PACKAGE_UNAVAILABLE") from None
    need(
        stat.S_ISREG(info.st_mode)
        and not WRANGLER_PACKAGE.is_symlink()
        and info.st_uid == RUNTIME_OPERATOR_UID
        and info.st_size <= 131072
        and package.get("version") == WRANGLER_VERSION,
        "WRANGLER_VERSION_DRIFT",
    )
    need(
        stat.S_ISREG(binary.st_mode)
        and not WRANGLER.is_symlink()
        and binary.st_uid == RUNTIME_OPERATOR_UID
        and bool(stat.S_IMODE(binary.st_mode) & 0o100),
        "WRANGLER_BINARY_UNTRUSTED",
    )
    return WRANGLER_VERSION


def log_snapshot() -> tuple[tuple[str, int, int], ...]:
    if not WRANGLER_LOG_DIR.exists():
        return ()
    try:
        root = WRANGLER_LOG_DIR.lstat()
        need(
            stat.S_ISDIR(root.st_mode) and not WRANGLER_LOG_DIR.is_symlink(),
            "LOG_DIR_UNTRUSTED",
        )
        rows = []
        for path in sorted(WRANGLER_LOG_DIR.iterdir(), key=lambda p: p.name):
            info = path.lstat()
            need(
                stat.S_ISREG(info.st_mode) and not path.is_symlink(),
                "LOG_ENTRY_UNTRUSTED",
            )
            rows.append((path.name, info.st_size, info.st_mtime_ns))
        return tuple(rows)
    except (OSError, Blocked):
        raise Blocked("LOG_METADATA_UNAVAILABLE") from None


def run_wrangler_json(
    args: list[str],
    *,
    reason: str,
    runner: Any = subprocess.run,
) -> Any:
    result = runtime_subprocess(
        [str(WRANGLER), *args], runner=runner, timeout=45
    )
    need(
        result.returncode == 0
        and type(result.stdout) is bytes
        and 0 < len(result.stdout) <= 1048576,
        reason,
    )
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise Blocked(reason) from None


def _list_items(obj: Any, keys: tuple[str, ...], reason: str) -> list[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in keys:
            if isinstance(obj.get(key), list):
                return obj[key]
        result = obj.get("result")
        if isinstance(result, dict):
            for key in keys:
                if isinstance(result.get(key), list):
                    return result[key]
    raise Blocked(reason)


def collect_remote_evidence(*, runner: Any = subprocess.run) -> dict[str, Any]:
    versions = run_wrangler_json(
        ["versions", "list", "--name", WORKER, "--config", CONFIG_PATH, "--json"],
        reason="VERSIONS_READ_FAILED",
        runner=runner,
    )
    items = _list_items(
        versions, ("items", "versions", "result"), "VERSIONS_SHAPE"
    )
    need(items and isinstance(items[0], dict), "VERSIONS_EMPTY")
    latest = _uuid(
        items[0].get("id") or items[0].get("version_id"),
        "LATEST_VERSION",
    )
    deployments = run_wrangler_json(
        [
            "deployments", "list", "--name", WORKER,
            "--config", CONFIG_PATH, "--json",
        ],
        reason="DEPLOYMENTS_READ_FAILED",
        runner=runner,
    )
    deployed = _list_items(
        deployments, ("items", "deployments", "result"), "DEPLOYMENTS_SHAPE"
    )
    need(deployed and isinstance(deployed[0], dict), "DEPLOYMENTS_EMPTY")
    shares = deployed[0].get("versions")
    need(
        type(shares) is list and len(shares) == 1 and type(shares[0]) is dict,
        "ACTIVE_VERSION_COUNT",
    )
    active = _uuid(
        shares[0].get("version_id") or shares[0].get("id"),
        "ACTIVE_VERSION",
    )
    need(
        type(shares[0].get("percentage")) is int
        and shares[0]["percentage"] == 100,
        "ACTIVE_TRAFFIC",
    )
    detail = run_wrangler_json(
        [
            "versions", "view", active, "--name", WORKER,
            "--config", CONFIG_PATH, "--json",
        ],
        reason="ACTIVE_DETAIL_READ_FAILED",
        runner=runner,
    )
    root = detail.get("result", detail) if isinstance(detail, dict) else None
    need(type(root) is dict, "ACTIVE_DETAIL_SHAPE")
    observed = root.get("id") or root.get("version_id")
    need(observed is None or observed == active, "ACTIVE_DETAIL_ID")
    metadata = root.get("metadata") if isinstance(root.get("metadata"), dict) else {}
    resources = root.get("resources") if isinstance(root.get("resources"), dict) else {}
    script = resources.get("script") if isinstance(resources.get("script"), dict) else {}
    source = metadata.get("source")
    last = script.get("last_deployed_from")
    need(
        source in PROVENANCE_SOURCES
        and last in PROVENANCE_SOURCES
        and source == last,
        "ACTIVE_PROVENANCE",
    )
    bindings = resources.get("bindings")
    if isinstance(bindings, dict):
        bindings = list(bindings.values())
    need(
        type(bindings) is list and 1 <= len(bindings) <= len(KNOWN_BINDINGS),
        "BINDING_SET",
    )
    safe = []
    seen = set()
    for item in bindings:
        need(
            type(item) is dict
            and type(item.get("name")) is str
            and type(item.get("type")) is str,
            "BINDING_ENTRY",
        )
        name, kind = item["name"], item["type"]
        need(
            name in KNOWN_BINDINGS
            and KNOWN_BINDINGS[name] == kind
            and name not in seen,
            "BINDING_DRIFT",
        )
        seen.add(name)
        safe.append({"name": name, "type": kind})
    need("DB" in seen, "REQUIRED_GATE_A_BINDING")
    safe.sort(key=lambda x: x["name"])
    annotations = (
        root.get("annotations")
        if isinstance(root.get("annotations"), dict)
        else {}
    )
    message = annotations.get("workers/message")
    annotation_class = "none"
    if isinstance(message, str):
        if message.startswith("Add secret: "):
            annotation_class = "secret_change"
        elif message.startswith("Deploy"):
            annotation_class = "deployment"
        elif message.startswith("Upload"):
            annotation_class = "upload"
        else:
            annotation_class = "other"
    need(annotation_class in PROVENANCE_CLASSES, "ACTIVE_ANNOTATION")
    return {
        "schema": REMOTE_SCHEMA,
        "worker": WORKER,
        "environment": "production",
        "wrangler_version": WRANGLER_VERSION,
        "reviewed_source": {
            "repository": SOURCE_REPO,
            "commit": SOURCE_COMMIT,
            "worker_blob": WORKER_BLOB,
            "config_blob": CONFIG_BLOB,
            "migration_blob": MIGRATION_BLOB,
        },
        "latest_uploaded_version": latest,
        "active_versions": [{"version_id": active, "percentage": 100}],
        "active_provenance": {
            "source": source,
            "last_deployed_from": last,
            "annotation_class": annotation_class,
        },
        "active_bindings": safe,
        "d1": {
            "binding": DATABASE_BINDING,
            "database_name": DATABASE_NAME,
            "database_id": DATABASE_ID,
        },
    }


def collect_schema(*, runner: Any = subprocess.run) -> dict[str, Any]:
    rowsets = []
    for index, query in enumerate(SCHEMA_QUERIES, 1):
        data = run_wrangler_json(
            [
                "d1", "execute", DATABASE_BINDING,
                "--remote", "--command", query,
                "--json", "--config", CONFIG_PATH,
            ],
            reason=f"SCHEMA_READ_{index}_FAILED",
            runner=runner,
        )
        envelopes = data if isinstance(data, list) else [data]
        rows = []
        for envelope in envelopes:
            if not isinstance(envelope, dict):
                continue
            need(
                envelope.get("success") is True,
                f"SCHEMA_READ_{index}_API",
            )
            if isinstance(envelope.get("results"), list):
                rows.extend(
                    x for x in envelope["results"] if isinstance(x, dict)
                )
            result = envelope.get("result")
            if isinstance(result, dict) and isinstance(result.get("results"), list):
                rows.extend(
                    x for x in result["results"] if isinstance(x, dict)
                )
            elif isinstance(result, list):
                for sub in result:
                    if isinstance(sub, dict) and isinstance(sub.get("results"), list):
                        rows.extend(
                            x for x in sub["results"] if isinstance(x, dict)
                        )
        rowsets.append(rows)
    objects: dict[str, Any] = {}
    for table, rows in zip(
        ("like_cookie_sessions", "archived_like_totals"), rowsets[:2]
    ):
        if not rows:
            objects[table] = None
            continue
        columns = []
        for row in rows:
            name, kind, primary = (
                row.get("name"),
                row.get("type"),
                row.get("pk"),
            )
            need(
                type(name) is str
                and type(kind) is str
                and isinstance(primary, (int, bool)),
                "SCHEMA_TABLE_ROW",
            )
            columns.append(
                {"name": name, "type": kind.upper(), "pk": bool(primary)}
            )
        objects[table] = {"kind": "table", "columns": columns}
    rows = rowsets[2]
    if not rows:
        objects["idx_like_cookie_sessions_expiry"] = None
    else:
        tables = {row.get("table_name") for row in rows}
        indexes = {row.get("index_name") for row in rows}
        columns = [row.get("column_name") for row in rows]
        need(
            tables == {"like_cookie_sessions"}
            and indexes == {"idx_like_cookie_sessions_expiry"}
            and all(type(name) is str for name in columns),
            "SCHEMA_INDEX_ROW",
        )
        objects["idx_like_cookie_sessions_expiry"] = {
            "kind": "index",
            "table": "like_cookie_sessions",
            "columns": columns,
        }
    return {
        "schema": SCHEMA,
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "objects": objects,
    }


def validate_before_schema(schema: Any) -> dict[str, Any]:
    need(
        type(schema) is dict
        and set(schema)
        == {"schema", "database_name", "database_id", "objects"}
        and schema["schema"] == SCHEMA
        and schema["database_name"] == DATABASE_NAME
        and schema["database_id"] == DATABASE_ID,
        "PRE_SCHEMA_TARGET",
    )
    objects = schema["objects"]
    need(
        type(objects) is dict
        and set(objects) == set(TARGETS)
        and all(objects[name] is None for name in TARGETS),
        "PRE_SCHEMA_NOT_ABSENT",
    )
    return schema


def validate_after_schema(schema: Any) -> dict[str, Any]:
    need(
        type(schema) is dict
        and set(schema)
        == {"schema", "database_name", "database_id", "objects"}
        and schema["schema"] == SCHEMA
        and schema["database_name"] == DATABASE_NAME
        and schema["database_id"] == DATABASE_ID
        and schema["objects"] == EXPECTED_POST,
        "POST_SCHEMA_MISMATCH",
    )
    return schema


def validate_owner_binding(
    remote_digest: Any,
    schema_digest: Any,
    migration_blob: Any,
) -> None:
    need(
        remote_digest == REMOTE_EVIDENCE_SHA256
        and schema_digest == PRE_SCHEMA_SHA256
        and migration_blob == MIGRATION_BLOB,
        "OWNER_GATE_UNBOUND",
    )


def preflight(*, runner: Any = subprocess.run) -> dict[str, str]:
    trusted_runtime_entry()
    wrangler_package_version()
    exact_application_bytes(runner=runner)
    before_logs = log_snapshot()
    remote = collect_remote_evidence(runner=runner)
    need(
        canonical_sha256(remote) == REMOTE_EVIDENCE_SHA256,
        "REMOTE_EVIDENCE_DRIFT",
    )
    schema = validate_before_schema(collect_schema(runner=runner))
    need(
        canonical_sha256(schema) == PRE_SCHEMA_SHA256,
        "PRE_SCHEMA_DRIFT",
    )
    need(log_snapshot() == before_logs, "PREFLIGHT_LOG_WRITE")
    return {
        "remote_evidence_sha256": REMOTE_EVIDENCE_SHA256,
        "pre_schema_sha256": PRE_SCHEMA_SHA256,
        "migration_blob": MIGRATION_BLOB,
    }


def mutation_command() -> list[str]:
    return [
        str(WRANGLER),
        "d1", "execute", DATABASE_BINDING,
        "--remote", "--file", MIGRATION_PATH,
        "--yes", "--config", CONFIG_PATH,
    ]


def execute_once(*, runner: Any = subprocess.run) -> dict[str, Any]:
    preflight(runner=runner)
    exact_application_bytes(runner=runner)
    log_baseline = log_snapshot()
    result = runtime_subprocess(
        mutation_command(), runner=runner, timeout=60
    )
    if result.returncode != 0:
        raise MutationUnknown("MIGRATION_OUTCOME_UNKNOWN")
    if log_snapshot() != log_baseline:
        raise MutationUnknown("MIGRATION_LOG_WRITE_UNKNOWN")
    try:
        after = validate_after_schema(collect_schema(runner=runner))
        if log_snapshot() != log_baseline:
            raise MutationUnknown("POST_VERIFY_LOG_WRITE_UNKNOWN")
    except MutationUnknown:
        raise
    except Exception:
        raise MutationUnknown("POST_SCHEMA_UNVERIFIED") from None
    return {
        "status": "PASS",
        "mutation_started": True,
        "post_schema_sha256": canonical_sha256(after),
    }


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "SOURCE_ONLY_GATE_A_D1_RUNTIME_NO_LIVE",
        "issue": ISSUE,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "worker_path": WORKER_PATH,
        "worker_blob": WORKER_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "migration_path": MIGRATION_PATH,
        "migration_blob": MIGRATION_BLOB,
        "database_binding": DATABASE_BINDING,
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "remote_evidence_sha256": REMOTE_EVIDENCE_SHA256,
        "pre_schema_sha256": PRE_SCHEMA_SHA256,
        "runtime_entry": str(RUNTIME_ENTRY),
        "runtime_operator": RUNTIME_OPERATOR,
        "runtime_source_root": str(RUNTIME_SOURCE_ROOT),
        "wrangler_binary": str(WRANGLER),
        "no_log_env": {"WRANGLER_WRITE_LOGS": "false"},
        "preflight_reads": [
            "versions-list",
            "deployments-list",
            "active-version-view",
            "three-fixed-d1-schema-queries",
        ],
        "one_mutation": {
            "kind": "d1-execute-file",
            "binding": DATABASE_BINDING,
            "file": MIGRATION_PATH,
            "remote": True,
        },
        "post_verify": [
            "three-fixed-d1-schema-queries",
            "exact-post-schema",
        ],
        "forbidden": [
            "worker-upload",
            "worker-deploy",
            "secret-provision",
            "credential-content-read",
            "arbitrary-sql",
            "alternate-migration-file",
            "retry",
            "rollback",
            "cleanup",
        ],
        "actions": {
            "run_wrangler": False,
            "d1_write": False,
            "cloudflare_write": False,
            "credential_content_access": False,
            "host_install": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
            "cleanup": False,
        },
    }


def check_contract(contract: Any) -> None:
    need(
        type(contract) is dict and contract == expected_contract(),
        "CONTRACT_DRIFT",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-contract", action="store_true")
    parser.add_argument("--runtime-migrate", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--remote-evidence-sha256", default="")
    parser.add_argument("--pre-schema-sha256", default="")
    parser.add_argument("--migration-blob", default="")
    args = parser.parse_args(argv)
    if args.check_contract:
        if any(
            (
                args.runtime_migrate,
                args.confirm,
                args.remote_evidence_sha256,
                args.pre_schema_sha256,
                args.migration_blob,
            )
        ):
            print(STOP)
            return 2
        try:
            check_contract(json.loads(CONTRACT.read_text("utf-8")))
        except (
            Blocked,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
        ):
            print(STOP)
            return 2
        print("STATS_GATE_A_D1_RUNTIME_OK_SOURCE_ONLY_NO_LIVE")
        return 0
    if args.runtime_migrate:
        try:
            need(args.confirm == RUNTIME_CONFIRM, "CONFIRMATION_MISSING")
            validate_owner_binding(
                args.remote_evidence_sha256,
                args.pre_schema_sha256,
                args.migration_blob,
            )
            result = execute_once()
        except MutationUnknown as exc:
            print(
                json.dumps(
                    {
                        "status": "STOP_ERROR",
                        "reason": str(exc),
                        "mutation_state": "unknown",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 4
        except Blocked as exc:
            print(
                json.dumps(
                    {
                        "status": "BLOCKED",
                        "reason": str(exc),
                        "mutation_started": False,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 3
        print(
            json.dumps(
                result, sort_keys=True, separators=(",", ":")
            )
        )
        return 0
    print(STOP)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
