#!/usr/bin/env python3
"""Pinned Wrangler version/deploy plan for Ausmalwiese Stats Worker (#1050).

SOURCE ONLY. This module does not run Wrangler, install packages, access
credentials, contact Cloudflare, upload a version, deploy traffic, or change
routes/settings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-stats-version-module-proof-v1.json"

WORKER = "coloring-pages-stats-v1"
WRANGLER_VERSION = "4.135.0"
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "180368f3b81abddde3df94637512436ca50c358f"
SOURCE_PATH = "cloudflare/stats-worker.js"
SOURCE_BLOB = "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4"
CONFIG_PATH = "cloudflare/wrangler.stats-worker.jsonc"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
COMPATIBILITY_DATE = "2026-10-06"
D1_DATABASE_NAME = "coloring-pages-stats-v1"
D1_DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
RATE_LIMIT_NAMESPACE_ID = "1152026106"
RATE_LIMIT = 100
RATE_PERIOD = 60
VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
STOP = "STOP_STATS_WRANGLER_SOURCE_ONLY"


class Blocked(Exception):
    """Fixed source-only stop reason."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def verify_source(worker_bytes: Any) -> None:
    need(type(worker_bytes) is bytes and 0 < len(worker_bytes) <= 120000,
         "SOURCE_SIZE")
    need(git_blob(worker_bytes) == SOURCE_BLOB, "SOURCE_BLOB_DRIFT")


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        need(type(key) is str and key not in out, "CONFIG_DUPLICATE_FIELD")
        out[key] = value
    return out


def validate_wrangler_config(cfg: Any) -> dict[str, Any]:
    """Validate the exact reviewed config shape expected for future Wrangler use."""
    need(type(cfg) is dict, "CONFIG_TYPE")
    need(
        set(cfg) == {
            "name",
            "main",
            "compatibility_date",
            "workers_dev",
            "keep_vars",
            "d1_databases",
            "ratelimits",
            "secrets",
        },
        "CONFIG_FIELDS",
    )
    need(cfg["name"] == WORKER and cfg["main"] == SOURCE_PATH,
         "CONFIG_TARGET")
    need(cfg["compatibility_date"] == COMPATIBILITY_DATE,
         "CONFIG_COMPAT_DATE")
    need(cfg["workers_dev"] is False and cfg["keep_vars"] is True,
         "CONFIG_REMOTE_STATE")
    need(
        cfg["d1_databases"] == [{
            "binding": "DB",
            "database_name": D1_DATABASE_NAME,
            "database_id": D1_DATABASE_ID,
        }],
        "CONFIG_D1",
    )
    need(
        cfg["ratelimits"] == [{
            "name": "RATE_LIMITER",
            "namespace_id": RATE_LIMIT_NAMESPACE_ID,
            "simple": {"limit": RATE_LIMIT, "period": RATE_PERIOD},
        }],
        "CONFIG_RATE_LIMIT",
    )
    need(
        cfg["secrets"] == {
            "required": ["CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"]
        },
        "CONFIG_SECRETS",
    )
    return cfg


def verify_config(config_bytes: Any) -> dict[str, Any]:
    need(type(config_bytes) is bytes and 0 < len(config_bytes) <= 65536,
         "CONFIG_SIZE")
    need(git_blob(config_bytes) == CONFIG_BLOB, "CONFIG_BLOB_DRIFT")
    try:
        text = config_bytes.decode("utf-8", errors="strict")
        cfg = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Blocked("CONFIG_JSON") from exc
    return validate_wrangler_config(cfg)


def verify_provenance(
    source_commit: Any,
    wrangler_version: Any,
    config_bytes: Any,
    worker_bytes: Any,
) -> dict[str, Any]:
    need(source_commit == SOURCE_COMMIT, "SOURCE_COMMIT_DRIFT")
    need(wrangler_version == WRANGLER_VERSION, "WRANGLER_VERSION_DRIFT")
    verify_source(worker_bytes)
    return verify_config(config_bytes)


def _wrangler_prefix(wrangler_version: Any) -> list[str]:
    need(wrangler_version == WRANGLER_VERSION, "WRANGLER_VERSION_DRIFT")
    return ["npx", "--yes", f"wrangler@{WRANGLER_VERSION}"]


def upload_command(
    source_commit: Any,
    wrangler_version: Any,
    config_bytes: Any,
    worker_bytes: Any,
) -> list[str]:
    """Return the exact future upload command as data; never execute it."""
    verify_provenance(
        source_commit, wrangler_version, config_bytes, worker_bytes
    )
    return _wrangler_prefix(wrangler_version) + [
        "versions", "upload", SOURCE_PATH,
        "--config", CONFIG_PATH,
        "--name", WORKER,
        "--no-bundle",
        "--keep-vars",
        "--strict",
        "--tag", "git:" + SOURCE_COMMIT,
        "--message", "source-blob:" + SOURCE_BLOB
        + ";config-blob:" + CONFIG_BLOB,
    ]


def deploy_command(version_id: Any, wrangler_version: Any) -> list[str]:
    """Return an exact-ID 100% deployment command; never execute it."""
    need(type(version_id) is str and VERSION_ID.fullmatch(version_id) is not None,
         "VERSION_ID")
    return _wrangler_prefix(wrangler_version) + [
        "versions", "deploy",
        version_id + "@100%",
        "--config", CONFIG_PATH,
        "--name", WORKER,
        "-y",
    ]


def verify_command() -> list[str]:
    """Read-only post-deploy check for the /q behavior."""
    return [
        "curl", "--fail-with-body", "--silent", "--show-error",
        "--head", "https://ausmalwiese.de/q",
    ]


def check_contract(c: Any) -> None:
    expected = {
        "schema_version": 3,
        "status": "SOURCE_ONLY_PINNED_WRANGLER_CONFIG_PROVENANCE_NO_LIVE",
        "issue": 1050,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH,
        "source_blob": SOURCE_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "workflow": [
            "verify-exact-coloring-pages-commit-worker-config-blobs",
            "wrangler-versions-upload-no-bundle-strict",
            "capture-exact-version-id",
            "wrangler-versions-deploy-exact-id-at-100-percent",
            "head-q-verify",
        ],
        "config_rules": {
            "routes_or_triggers_in_config": False,
            "plain_text_vars_in_config": False,
            "keep_vars": True,
            "workers_dev": False,
            "compatibility_date": COMPATIBILITY_DATE,
            "d1": {
                "binding": "DB",
                "database_name": D1_DATABASE_NAME,
                "database_id": D1_DATABASE_ID,
            },
            "rate_limit": {
                "binding": "RATE_LIMITER",
                "namespace_id": RATE_LIMIT_NAMESPACE_ID,
                "limit": RATE_LIMIT,
                "period": RATE_PERIOD,
            },
            "required_secrets": [
                "CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"
            ],
        },
        "actions": {
            "run_wrangler": False,
            "package_install": False,
            "credential_access": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
        },
    }
    need(type(c) is dict and c == expected, "CONTRACT_DRIFT")


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
    print("STATS_WRANGLER_PINNED_PROVENANCE_OK_SOURCE_ONLY_NO_LIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
