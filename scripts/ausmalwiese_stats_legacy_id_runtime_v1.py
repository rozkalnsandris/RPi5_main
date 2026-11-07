#!/usr/bin/env python3
"""Trusted runtime boundary for Ausmalwiese Stats legacy-ID migration (#1417).

The installed runtime is fail-closed until a separately reviewed D1 Read+Write
credential provider is established in this source contract. Source merge alone
performs no network, credential, D1, host-data, service or LIVE mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
from typing import Any, Callable
import urllib.error
import urllib.request

ISSUE = 1417
REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_ROOT_RUNTIME = Path("/home/andris/RPi5_main")
SOURCE_REL = "scripts/ausmalwiese_stats_legacy_id_runtime_v1.py"
PLANNER_REL = "scripts/ausmalwiese_stats_legacy_id_migration_v1.py"
PLANNER_BLOB = "fb0c39fd552ec55e3fbb4310fe70dfee42e4e1c4"
MIGRATION_CONTRACT_REL = "ops/contracts/ausmalwiese-stats-legacy-id-migration-v1.json"
MIGRATION_CONTRACT_BLOB = "c571dc6efc702ecf5f933aa58f3f7a59e5db02e9"
ALIASES_REL = "ops/vendor/coloring-pages/legacy-id-aliases-457.json"
ALIASES_BLOB = "2e20a2a7a7e716274934a0eb662091150ef55e7f"
RUNTIME_CONTRACT_REL = "ops/contracts/ausmalwiese-stats-legacy-id-runtime-v1.json"
RUNTIME_ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-stats-legacy-id-d1-migrate")
PROVIDER_PATH = Path("/usr/local/libexec/rpi5-ausmalwiese-stats-d1-credentials-v1")
DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
DATABASE_NAME = "coloring-pages-stats-v1"
DATABASE_BINDING = "DB"
API_HOST = "api.cloudflare.com"
API_BASE = "https://api.cloudflare.com/client/v4"
CONFIRM = "OWNER-AUTHORIZED-STATS-LEGACY-ID-D1-MIGRATION"
MAX_RESPONSE_BYTES = 1048576
TIMEOUT_SECONDS = 12
RUNTIME_OPERATOR_UID = 1000
RUNTIME_OPERATOR_GID = 1000
RUNTIME_ENV = {
    "HOME": "/home/andris",
    "USER": "andris",
    "LOGNAME": "andris",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LC_ALL": "C",
}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ACCOUNT_ID = re.compile(r"[0-9a-fA-F]{32}\Z")
STOP = "STOP_STATS_LEGACY_ID_RUNTIME"


class Blocked(RuntimeError):
    pass


class MutationUnknown(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def source_root() -> Path:
    return (
        SOURCE_ROOT_RUNTIME
        if Path(__file__).absolute() == RUNTIME_ENTRY
        else Path(__file__).resolve().parents[1]
    )


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "SOURCE_ONLY_INSTALLABLE_RUNTIME_PROVIDER_REQUIRED_NO_LIVE",
        "issue": ISSUE,
        "repository": REPOSITORY,
        "runtime_entry": str(RUNTIME_ENTRY),
        "source_dependencies": {
            "planner_path": PLANNER_REL,
            "planner_blob": PLANNER_BLOB,
            "migration_contract_path": MIGRATION_CONTRACT_REL,
            "migration_contract_blob": MIGRATION_CONTRACT_BLOB,
            "aliases_path": ALIASES_REL,
            "aliases_blob": ALIASES_BLOB,
        },
        "d1": {
            "binding": DATABASE_BINDING,
            "database_name": DATABASE_NAME,
            "database_id": DATABASE_ID,
            "api_host": API_HOST,
            "api_path_template": (
                "/accounts/{account_id}/d1/database/"
                + DATABASE_ID
                + "/query"
            ),
            "mutation_batch_entries": 6,
            "read_batch_entries": 24,
        },
        "credential_provider": {
            "status": "REQUIRED_NOT_ESTABLISHED",
            "path": str(PROVIDER_PATH),
            "provider_sha256": None,
            "required_capabilities": ["D1 Read", "D1 Write"],
        },
        "transport": {
            "verified_https": True,
            "redirects": False,
            "ambient_proxy": False,
            "automatic_retries": 0,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_response_bytes": MAX_RESPONSE_BYTES,
        },
        "confirmation": CONFIRM,
        "actions": {
            "install": False,
            "credential_read": False,
            "cloudflare_request": False,
            "d1_read": False,
            "d1_write": False,
            "rpi5_content_write": False,
            "service_lifecycle": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
            "cleanup": False,
        },
    }


def load_runtime_contract(root: Path | None = None) -> dict[str, Any]:
    root = source_root() if root is None else root
    try:
        value = json.loads((root / RUNTIME_CONTRACT_REL).read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Blocked("RUNTIME_CONTRACT_UNAVAILABLE") from None
    need(value == expected_contract(), "RUNTIME_CONTRACT_DRIFT")
    return value


def _run(
    argv: list[str],
    *,
    timeout: int = 10,
    runner: Any = subprocess.run,
    as_operator: bool = False,
) -> Any:
    kwargs: dict[str, Any] = {
        "cwd": str(SOURCE_ROOT_RUNTIME),
        "env": dict(RUNTIME_ENV),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "check": False,
        "timeout": timeout,
    }
    if as_operator and os.geteuid() == 0:
        kwargs.update(
            user=RUNTIME_OPERATOR_UID,
            group=RUNTIME_OPERATOR_GID,
            extra_groups=(),
        )
    try:
        return runner(list(argv), **kwargs)
    except Exception:
        raise Blocked("COMMAND_UNAVAILABLE") from None


def git_runtime(args: list[str], *, runner: Any = subprocess.run) -> bytes:
    result = _run(
        ["/usr/bin/git", "-C", str(SOURCE_ROOT_RUNTIME), *args],
        runner=runner,
        as_operator=True,
    )
    need(
        result.returncode == 0
        and type(result.stdout) is bytes
        and len(result.stdout) <= 524288,
        "SOURCE_GIT_FAILED",
    )
    return result.stdout


def trusted_runtime_entry(*, lstat: Any = os.lstat) -> None:
    need(os.geteuid() == 0, "RUNTIME_ROOT_REQUIRED")
    need(Path(__file__).absolute() == RUNTIME_ENTRY, "RUNTIME_ENTRY_DRIFT")
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


def _exact_working_file(
    root: Path,
    rel: str,
    expected_blob: str | None,
    *,
    runner: Any = subprocess.run,
) -> bytes:
    full = root / rel
    try:
        info = full.lstat()
        raw = full.read_bytes()
    except OSError:
        raise Blocked("SOURCE_FILE_UNAVAILABLE") from None
    need(
        stat.S_ISREG(info.st_mode)
        and not full.is_symlink()
        and info.st_nlink == 1
        and 0 < info.st_size <= 524288,
        "SOURCE_FILE_UNTRUSTED",
    )
    canonical = git_runtime(["show", "HEAD:" + rel], runner=runner)
    tree = git_runtime(["ls-tree", "HEAD", "--", rel], runner=runner).decode("ascii").strip()
    match = re.fullmatch(r"100(?:644|755) blob ([0-9a-f]{40})\t(.+)", tree)
    need(
        raw == canonical
        and match is not None
        and match.group(2) == rel
        and git_blob(raw) == match.group(1),
        "SOURCE_BYTE_DRIFT",
    )
    if expected_blob is not None:
        need(match.group(1) == expected_blob, "SOURCE_BLOB_DRIFT")
    return raw


def validate_installed_source(
    expected_main: str,
    *,
    runner: Any = subprocess.run,
) -> Path:
    trusted_runtime_entry()
    need(type(expected_main) is str and SHA40.fullmatch(expected_main) is not None,
         "EXPECTED_MAIN_INVALID")
    root = SOURCE_ROOT_RUNTIME
    need(root.is_dir() and not root.is_symlink(), "SOURCE_ROOT_UNTRUSTED")
    head = git_runtime(["rev-parse", "HEAD"], runner=runner).decode("ascii").strip()
    branch = git_runtime(
        ["symbolic-ref", "--quiet", "--short", "HEAD"], runner=runner
    ).decode("ascii").strip()
    dirty = git_runtime(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner=runner
    )
    origin = git_runtime(["remote", "get-url", "origin"], runner=runner).decode("ascii").strip().rstrip("/")
    need(head == expected_main and branch == "main" and dirty == b"", "SOURCE_CHECKOUT_DRIFT")
    need(origin in {
        "https://github.com/rozkalnsandris/RPi5_main",
        "https://github.com/rozkalnsandris/RPi5_main.git",
        "git@github.com:rozkalnsandris/RPi5_main",
        "git@github.com:rozkalnsandris/RPi5_main.git",
    }, "SOURCE_ORIGIN_DRIFT")
    source_bytes = _exact_working_file(root, SOURCE_REL, None, runner=runner)
    try:
        installed = RUNTIME_ENTRY.read_bytes()
    except OSError:
        raise Blocked("RUNTIME_ENTRY_UNAVAILABLE") from None
    need(installed == source_bytes, "INSTALLED_SOURCE_DRIFT")
    _exact_working_file(root, PLANNER_REL, PLANNER_BLOB, runner=runner)
    _exact_working_file(
        root, MIGRATION_CONTRACT_REL, MIGRATION_CONTRACT_BLOB, runner=runner
    )
    _exact_working_file(root, ALIASES_REL, ALIASES_BLOB, runner=runner)
    _exact_working_file(root, RUNTIME_CONTRACT_REL, None, runner=runner)
    load_runtime_contract(root)
    return root


def load_planner(root: Path | None = None) -> Any:
    root = source_root() if root is None else root
    path = root / PLANNER_REL
    spec = importlib.util.spec_from_file_location("stats_legacy_1412_runtime", path)
    need(spec is not None and spec.loader is not None, "PLANNER_IMPORT")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        raise Blocked("PLANNER_IMPORT") from None
    return module


def _provider_metadata(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise Blocked("CREDENTIAL_PROVIDER_REQUIRED") from None
    need(
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == 0
        and info.st_gid == 0
        and stat.S_IMODE(info.st_mode) == 0o500
        and info.st_nlink == 1,
        "CREDENTIAL_PROVIDER_UNTRUSTED",
    )


def provider_credentials(
    contract: dict[str, Any] | None = None,
    *,
    runner: Any = subprocess.run,
) -> dict[str, str]:
    contract = load_runtime_contract() if contract is None else contract
    provider = contract["credential_provider"]
    need(provider["status"] == "ESTABLISHED", "CREDENTIAL_PROVIDER_REQUIRED")
    provider_sha = provider.get("provider_sha256")
    need(type(provider_sha) is str and SHA256.fullmatch(provider_sha) is not None,
         "CREDENTIAL_PROVIDER_IDENTITY")
    _provider_metadata(PROVIDER_PATH)
    try:
        raw = PROVIDER_PATH.read_bytes()
    except OSError:
        raise Blocked("CREDENTIAL_PROVIDER_UNTRUSTED") from None
    need(hashlib.sha256(raw).hexdigest() == provider_sha, "CREDENTIAL_PROVIDER_IDENTITY")
    result = _run(
        [str(PROVIDER_PATH), "--database-id", DATABASE_ID, "--json"],
        timeout=10,
        runner=runner,
        as_operator=False,
    )
    need(
        result.returncode == 0
        and type(result.stdout) is bytes
        and 0 < len(result.stdout) <= 8192,
        "CREDENTIAL_PROVIDER_FAILED",
    )
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise Blocked("CREDENTIAL_PROVIDER_FAILED") from None
    need(
        type(value) is dict
        and set(value) == {
            "schema", "account_id", "api_token", "database_id", "capabilities"
        }
        and value["schema"] == "rpi5.cloudflare-d1-credential.v1"
        and type(value["account_id"]) is str
        and ACCOUNT_ID.fullmatch(value["account_id"]) is not None
        and type(value["api_token"]) is str
        and 20 <= len(value["api_token"]) <= 4096
        and not any(ch.isspace() for ch in value["api_token"])
        and value["database_id"] == DATABASE_ID
        and value["capabilities"] == ["D1 Read", "D1 Write"],
        "CREDENTIAL_PROVIDER_FAILED",
    )
    return {"account_id": value["account_id"], "api_token": value["api_token"]}


def api_path(account_id: str) -> str:
    need(type(account_id) is str and ACCOUNT_ID.fullmatch(account_id) is not None,
         "ACCOUNT_ID_INVALID")
    return f"/accounts/{account_id}/d1/database/{DATABASE_ID}/query"


def build_opener() -> Any:
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )


def _validated_payload(payload: Any, expected_count: int, *, mutation: bool) -> dict[str, Any]:
    error = MutationUnknown if mutation else Blocked
    if (
        type(payload) is not dict
        or payload.get("success") is not True
        or type(payload.get("result")) is not list
        or len(payload["result"]) != expected_count
        or any(type(item) is not dict or item.get("success") is not True
               for item in payload["result"])
    ):
        raise error("MUTATION_RESPONSE_UNKNOWN" if mutation else "D1_READ_SHAPE")
    return payload


def api_request(
    credentials: dict[str, str],
    body: dict[str, Any],
    *,
    mutation: bool,
    opener: Any | None = None,
) -> dict[str, Any]:
    need(set(credentials) == {"account_id", "api_token"}, "CREDENTIAL_SHAPE")
    account_id, token = credentials["account_id"], credentials["api_token"]
    need(ACCOUNT_ID.fullmatch(account_id) is not None, "ACCOUNT_ID_INVALID")
    need(20 <= len(token) <= 4096 and not any(ch.isspace() for ch in token),
         "TOKEN_INVALID")
    need(type(body) is dict and set(body) == {"batch"} and type(body["batch"]) is list,
         "REQUEST_BODY_INVALID")
    expected_count = 6 if mutation else 24
    need(len(body["batch"]) == expected_count, "REQUEST_BATCH_COUNT")
    data = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    request = urllib.request.Request(
        API_BASE + api_path(account_id),
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "rpi5-ausmalwiese-stats-legacy-id-runtime-v1",
        },
    )
    client = build_opener() if opener is None else opener
    try:
        with client.open(request, timeout=TIMEOUT_SECONDS) as response:
            need(getattr(response, "status", 200) == 200, "HTTP_STATUS")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except Blocked:
        if mutation:
            raise MutationUnknown("MUTATION_TRANSPORT_UNKNOWN") from None
        raise
    except Exception:
        if mutation:
            raise MutationUnknown("MUTATION_TRANSPORT_UNKNOWN") from None
        raise Blocked("D1_READ_FAILED") from None
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        if mutation:
            raise MutationUnknown("MUTATION_RESPONSE_UNKNOWN")
        raise Blocked("D1_READ_SHAPE")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        if mutation:
            raise MutationUnknown("MUTATION_RESPONSE_UNKNOWN") from None
        raise Blocked("D1_READ_SHAPE") from None
    return _validated_payload(payload, expected_count, mutation=mutation)


def _nonnegative_int(value: Any, reason: str) -> int:
    need(type(value) is int and value >= 0, reason)
    return value


def _results(item: dict[str, Any]) -> list[dict[str, Any]]:
    rows = item.get("results")
    need(type(rows) is list and all(type(row) is dict for row in rows), "D1_READ_ROWS")
    return rows


def evidence_from_response(
    planner: Any,
    queries: list[dict[str, Any]],
    payload: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    _validated_payload(payload, 24, mutation=False)
    need(len(queries) == 24, "READ_PLAN_COUNT")
    tables: dict[str, Any] = {}
    for query, item in zip(queries, payload["result"], strict=True):
        table = query["table"]
        kind = query["kind"]
        if table not in tables:
            tables[table] = {
                "columns": None,
                "legacy": [],
                "target": [],
                "unrelated_row_count": None,
            }
        rows = _results(item)
        if kind == "schema":
            columns = []
            try:
                ordered = sorted(rows, key=lambda row: int(row["cid"]))
                for row in ordered:
                    columns.append([
                        str(row["name"]),
                        str(row["type"]).upper(),
                        int(row["pk"]),
                    ])
            except (KeyError, TypeError, ValueError):
                raise Blocked("D1_SCHEMA_ROWS") from None
            tables[table]["columns"] = columns
        elif kind in {"legacy", "target"}:
            parsed = []
            metrics = planner.TABLES[table]["metrics"]
            for row in rows:
                need(
                    set(row).issuperset({"page_id", "row_count", *metrics}),
                    "D1_AGGREGATE_ROWS",
                )
                parsed.append({
                    "page_id": str(row["page_id"]),
                    "row_count": _nonnegative_int(row["row_count"], "D1_ROW_COUNT"),
                    "metrics": {
                        metric: _nonnegative_int(row[metric], "D1_METRIC")
                        for metric in metrics
                    },
                })
            tables[table][kind] = parsed
        elif kind == "unrelated_count":
            need(len(rows) == 1 and set(rows[0]).issuperset({"row_count"}),
                 "D1_UNRELATED_ROWS")
            tables[table]["unrelated_row_count"] = _nonnegative_int(
                rows[0]["row_count"], "D1_UNRELATED_COUNT"
            )
        else:
            raise Blocked("READ_PLAN_KIND")
    evidence = {
        "schema": planner.EVIDENCE_SCHEMA,
        "stage": stage,
        "database": planner.database_identity(),
        "source": planner.source_identity(),
        "alias": planner.alias_identity(),
        "tables": tables,
    }
    planner.validate_evidence(evidence, stage, planner.load_aliases(planner.ALIASES.read_bytes()))
    return evidence


def read_body(planner: Any, pairs: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = planner.read_plan(pairs)
    need(len(queries) == 24, "READ_PLAN_COUNT")
    batch = []
    for query in queries:
        need(
            type(query) is dict
            and set(query) == {"kind", "table", "sql", "params"}
            and query["table"] in planner.TABLES
            and type(query["sql"]) is str
            and type(query["params"]) is list,
            "READ_PLAN_SHAPE",
        )
        batch.append({"sql": query["sql"], "params": query["params"]})
    return queries, {"batch": batch}


def mutation_body(operation: dict[str, Any], planner: Any) -> dict[str, Any]:
    need(
        operation.get("schema") == planner.OP_SCHEMA
        and operation.get("transaction") == "D1_DATABASE_BATCH"
        and operation.get("statement_count") == 6
        and operation.get("database") == planner.database_identity()
        and operation.get("alias") == planner.alias_identity()
        and operation.get("runtime_authority") is False
        and operation.get("execution") == "NOT_PERFORMED",
        "MUTATION_PLAN_DRIFT",
    )
    statements = operation.get("statements")
    need(
        type(statements) is list
        and len(statements) == 6
        and [item.get("table") for item in statements] == list(planner.TABLES),
        "MUTATION_STATEMENT_SET",
    )
    batch = []
    for item in statements:
        need(
            type(item) is dict
            and set(item) == {"table", "sql", "params"}
            and type(item["sql"]) is str
            and type(item["params"]) is list
            and len(item["params"]) == 60,
            "MUTATION_STATEMENT_SHAPE",
        )
        batch.append({"sql": item["sql"], "params": item["params"]})
    return {"batch": batch}


def collect_evidence(
    planner: Any,
    credentials: dict[str, str],
    stage: str,
    *,
    requester: Callable[..., dict[str, Any]] = api_request,
) -> dict[str, Any]:
    pairs = planner.load_aliases(planner.ALIASES.read_bytes())
    queries, body = read_body(planner, pairs)
    payload = requester(credentials, body, mutation=False)
    return evidence_from_response(planner, queries, payload, stage)


def runtime_preflight(
    expected_main: str,
    *,
    source_validator: Callable[[str], Path] = validate_installed_source,
    provider_loader: Callable[..., dict[str, str]] = provider_credentials,
    requester: Callable[..., dict[str, Any]] = api_request,
) -> dict[str, Any]:
    root = source_validator(expected_main)
    contract = load_runtime_contract(root)
    planner = load_planner(root)
    pairs = planner.load_aliases(planner.ALIASES.read_bytes())
    credentials = provider_loader(contract)
    before = collect_evidence(
        planner, credentials, "before", requester=requester
    )
    operation = planner.migration_operation(pairs, before)
    return {
        "planner": planner,
        "pairs": pairs,
        "credentials": credentials,
        "before": before,
        "operation": operation,
        "baseline_sha256": canonical_sha(before),
    }


def execute_once(
    expected_main: str,
    expected_baseline: str,
    *,
    source_validator: Callable[[str], Path] = validate_installed_source,
    provider_loader: Callable[..., dict[str, str]] = provider_credentials,
    requester: Callable[..., dict[str, Any]] = api_request,
) -> dict[str, Any]:
    need(type(expected_baseline) is str and SHA256.fullmatch(expected_baseline) is not None,
         "BASELINE_INVALID")
    state = runtime_preflight(
        expected_main,
        source_validator=source_validator,
        provider_loader=provider_loader,
        requester=requester,
    )
    need(state["baseline_sha256"] == expected_baseline, "BASELINE_DRIFT")
    source_validator(expected_main)
    body = mutation_body(state["operation"], state["planner"])
    requester(state["credentials"], body, mutation=True)
    try:
        after = collect_evidence(
            state["planner"],
            state["credentials"],
            "after",
            requester=requester,
        )
        state["planner"].validate_post(
            state["before"], after, state["pairs"]
        )
    except Exception:
        raise MutationUnknown("POST_VERIFY_UNKNOWN") from None
    return {
        "status": "PASS",
        "mutation_started": True,
        "statement_count": 6,
        "before_sha256": state["baseline_sha256"],
        "after_sha256": canonical_sha(after),
        "legacy_ids_remaining": 0,
    }


def source_check() -> str:
    root = source_root()
    load_runtime_contract(root)
    planner = load_planner(root)
    planner.check_contract(
        json.loads((root / MIGRATION_CONTRACT_REL).read_text("utf-8"))
    )
    pairs = planner.load_aliases((root / ALIASES_REL).read_bytes())
    need(len(pairs) == 30, "ALIAS_COUNT")
    dummy_tables = {}
    for table, spec in planner.TABLES.items():
        dummy_tables[table] = {
            "columns": spec["columns"],
            "legacy": [],
            "target": [],
            "unrelated_row_count": 0,
        }
    before = {
        "schema": planner.EVIDENCE_SCHEMA,
        "stage": "before",
        "database": planner.database_identity(),
        "source": planner.source_identity(),
        "alias": planner.alias_identity(),
        "tables": dummy_tables,
    }
    op = planner.migration_operation(pairs, before)
    mutation_body(op, planner)
    return "STATS_LEGACY_ID_RUNTIME_SOURCE_OK_PROVIDER_REQUIRED_NO_LIVE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-contract", action="store_true")
    parser.add_argument("--runtime-preflight", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-main", default="")
    parser.add_argument("--expected-baseline", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    try:
        modes = sum(bool(x) for x in (
            args.check_contract, args.runtime_preflight, args.apply
        ))
        need(modes == 1, "MODE")
        if args.check_contract:
            need(
                not args.expected_main
                and not args.expected_baseline
                and not args.confirm,
                "CHECK_ARGUMENTS",
            )
            print(source_check())
            return 0
        need(args.expected_main != "", "EXPECTED_MAIN_REQUIRED")
        if args.runtime_preflight:
            need(not args.expected_baseline and not args.confirm, "PREFLIGHT_ARGUMENTS")
            state = runtime_preflight(args.expected_main)
            print(json.dumps({
                "status": "PREFLIGHT_PASS",
                "mutation_started": False,
                "baseline_sha256": state["baseline_sha256"],
                "statement_count": 6,
            }, sort_keys=True, separators=(",", ":")))
            return 0
        need(args.confirm == CONFIRM, "CONFIRMATION_MISSING")
        result = execute_once(args.expected_main, args.expected_baseline)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except MutationUnknown as exc:
        print(json.dumps({
            "status": "STOP_ERROR",
            "reason": str(exc),
            "mutation_state": "unknown",
        }, sort_keys=True, separators=(",", ":")))
        return 4
    except (Blocked, OSError, UnicodeError, json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, Blocked) else "SOURCE_ERROR"
        print(json.dumps({
            "status": "BLOCKED",
            "reason": reason,
            "mutation_state": "not_started",
        }, sort_keys=True, separators=(",", ":")))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
