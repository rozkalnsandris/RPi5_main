#!/usr/bin/env python3
"""Simplified Wrangler version/deploy plan for Ausmalwiese Stats Worker (#1045).

SOURCE ONLY. This module does not run Wrangler, access credentials, contact
Cloudflare, upload a version, deploy traffic, or change routes/settings.
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
SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "9590be4276ac1781eafe38cf662b8d224653c9aa"
SOURCE_PATH = "cloudflare/stats-worker.js"
SOURCE_BLOB = "dd5a2859d55b9ef2d9fb9a9d8bf0a535d25a5ba4"
CONFIG_PATH = "cloudflare/wrangler.stats-worker.jsonc"
VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\\Z")
RESOURCE_ID = re.compile(r"[0-9a-f-]{32,36}\\Z")
DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\\Z")
STOP = "STOP_STATS_WRANGLER_SOURCE_ONLY"

class Blocked(Exception):
    """Fixed source-only stop reason."""

def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)

def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\\0" + data
    ).hexdigest()

def verify_source(worker_bytes: Any) -> None:
    need(type(worker_bytes) is bytes and 0 < len(worker_bytes) <= 120000,
         "SOURCE_SIZE")
    need(git_blob(worker_bytes) == SOURCE_BLOB, "SOURCE_BLOB_DRIFT")

def validate_wrangler_config(cfg: Any) -> dict[str, Any]:
    """Validate the reviewed config shape expected for future Wrangler use."""
    need(type(cfg) is dict, "CONFIG_TYPE")
    allowed = {
        "$schema", "name", "main", "compatibility_date", "compatibility_flags",
        "workers_dev", "keep_vars", "d1_databases", "ratelimits", "secrets",
    }
    need(set(cfg) <= allowed, "CONFIG_FIELDS")
    need(cfg.get("name") == WORKER and cfg.get("main") == SOURCE_PATH,
         "CONFIG_TARGET")
    need(cfg.get("workers_dev") is False and cfg.get("keep_vars") is True,
         "CONFIG_REMOTE_STATE")
    need(type(cfg.get("compatibility_date")) is str
         and DATE.fullmatch(cfg["compatibility_date"]) is not None,
         "CONFIG_COMPAT_DATE")
    flags = cfg.get("compatibility_flags", [])
    need(type(flags) is list and len(flags) <= 30
         and all(type(x) is str and re.fullmatch(r"[a-z0-9_]{1,80}", x)
                 for x in flags)
         and len(set(flags)) == len(flags), "CONFIG_COMPAT_FLAGS")

    d1 = cfg.get("d1_databases")
    need(type(d1) is list and len(d1) == 1 and type(d1[0]) is dict
         and set(d1[0]) == {"binding", "database_name", "database_id"}
         and d1[0]["binding"] == "DB"
         and type(d1[0]["database_name"]) is str
         and 1 <= len(d1[0]["database_name"]) <= 128
         and type(d1[0]["database_id"]) is str
         and RESOURCE_ID.fullmatch(d1[0]["database_id"]) is not None,
         "CONFIG_D1")

    rates = cfg.get("ratelimits")
    need(type(rates) is list and len(rates) == 1 and type(rates[0]) is dict
         and set(rates[0]) == {"name", "namespace_id", "simple"}
         and rates[0]["name"] == "RATE_LIMITER"
         and type(rates[0]["namespace_id"]) is str
         and rates[0]["namespace_id"].isdecimal()
         and int(rates[0]["namespace_id"]) > 0
         and type(rates[0]["simple"]) is dict
         and set(rates[0]["simple"]) == {"limit", "period"}
         and type(rates[0]["simple"]["limit"]) is int
         and type(rates[0]["simple"]["limit"]) is not bool
         and rates[0]["simple"]["limit"] > 0
         and rates[0]["simple"]["period"] in (10, 60),
         "CONFIG_RATE_LIMIT")

    secrets = cfg.get("secrets")
    need(type(secrets) is dict and set(secrets) == {"required"}
         and secrets["required"] == [
             "CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"
         ], "CONFIG_SECRETS")
    return cfg

def upload_command(cfg: Any, worker_bytes: Any) -> list[str]:
    """Return the exact future upload command as data; never execute it."""
    validate_wrangler_config(cfg)
    verify_source(worker_bytes)
    return [
        "npx", "wrangler", "versions", "upload", SOURCE_PATH,
        "--config", CONFIG_PATH,
        "--name", WORKER,
        "--no-bundle",
        "--keep-vars",
        "--strict",
        "--tag", "git:" + SOURCE_COMMIT,
        "--message", "source-blob:" + SOURCE_BLOB,
    ]

def deploy_command(version_id: Any) -> list[str]:
    """Return an exact-ID 100% deployment command; never execute it."""
    need(type(version_id) is str and VERSION_ID.fullmatch(version_id) is not None,
         "VERSION_ID")
    return [
        "npx", "wrangler", "versions", "deploy",
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
        "schema_version": 2,
        "status": "SOURCE_ONLY_SIMPLIFIED_WRANGLER_PLAN_NO_LIVE",
        "issue": 1045,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH,
        "source_blob": SOURCE_BLOB,
        "config_path": CONFIG_PATH,
        "workflow": [
            "review-and-commit-wrangler-config-in-coloring-pages",
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
            "required_d1_binding": "DB",
            "required_rate_limit_binding": "RATE_LIMITER",
            "required_secrets": [
                "CF_ANALYTICS_API_TOKEN", "VISITOR_HMAC_KEY"
            ],
        },
        "actions": {
            "run_wrangler": False,
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
    print("STATS_WRANGLER_PLAN_OK_SOURCE_ONLY_NO_LIVE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
