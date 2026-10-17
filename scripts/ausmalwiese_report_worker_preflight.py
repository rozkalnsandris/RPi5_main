#!/usr/bin/env python3
"""Offline, synthetic-only validation of a fixed report Worker activation plan.

Never queries Cloudflare, executes a deployment, or reads protected settings.
A valid candidate is NOT evidence of live readiness or operator permission.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-worker-activation-v1.json"
STOP = "STOP_REPORT_SOURCE_PLAN_INVALID"


class PlanStop(ValueError):
    """Static, non-sensitive failure code only."""


def require(condition: bool) -> None:
    if not condition:
        raise PlanStop(STOP)


def check_keys(value: Any, names: set[str]) -> None:
    require(type(value) is dict and set(value) == names)


def contract_data() -> dict[str, Any]:
    """Read only the repository-tracked static contract, never external paths."""
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def validate_contract(value: Any) -> None:
    check_keys(value, {"schema_version", "state", "target", "routes", "binding_kinds", "rate_limits", "turnstile", "brevo", "scope"})
    require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    require(value["state"] == "SOURCE_ONLY_NOT_LIVE_AUTHORIZED")
    target = value["target"]
    check_keys(target, {"worker", "zone", "account_sha256", "source_repo", "source_path", "source_commit", "source_git_blob", "source_sha256"})
    require(target == {
        "worker": "coloring-pages-report-v1", "zone": "ausmalwiese.de",
        "account_sha256": "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34",
        "source_repo": "rozkalnsandris/coloring-pages", "source_path": "cloudflare/report-worker.mjs",
        "source_commit": "a90c6a6a7ccca2941d99e9edddd5cfa31ac9ed18",
        "source_git_blob": "6d2359752d12f4a40847008fc7fdcc457124e893",
        "source_sha256": "26d4e597d8c2c961c3a637957ea566654c97c5657a4b2595129c410e9fae22a1",
    })
    require(value["routes"] == [
        "ausmalwiese.de/api/report", "ausmalwiese.de/api/report/config",
        "www.ausmalwiese.de/api/report", "www.ausmalwiese.de/api/report/config",
    ])
    require(value["binding_kinds"] == {
        "TURNSTILE_SITE_KEY": "plain_text", "TURNSTILE_SECRET": "secret_text",
        "BREVO_API_KEY": "secret_text", "REPORT_TO": "secret_text",
        "REPORT_RATE": "ratelimit", "REPORT_DUP": "ratelimit",
    })
    require(value["rate_limits"] == {"REPORT_RATE": {"limit": 12, "period": 60}, "REPORT_DUP": {"limit": 1, "period": 60}})
    require(value["turnstile"] == {"action": "report", "hostnames": ["ausmalwiese.de", "www.ausmalwiese.de"]})
    require(value["brevo"] == {
        "sender": "FROM_PINNED_APP_WORKER_SOURCE", "api": "https://api.brevo.com/v3/smtp/email",
        "accepted_response": "HTTP_201_WITH_NONEMPTY_MESSAGE_ID_NOT_DELIVERED",
    })
    require(value["scope"] == {
        "status": "READ_ONLY_SOURCE_PLAN", "max_attempts_after_first_live_mutation": 0,
        "merge_authorized": False, "live_authorized": False,
        "stats_worker_changes": False, "credential_access": False,
    })


def validate_synthetic_candidate(candidate: Any, contract: dict[str, Any]) -> None:
    """Validate only allowlisted *shapes*. Caller assertions cannot prove LIVE."""
    validate_contract(contract)
    check_keys(candidate, {"schema_version", "target", "routes", "binding_kinds", "rate_limits", "namespace_ids", "turnstile", "brevo"})
    require(type(candidate["schema_version"]) is int and candidate["schema_version"] == 1)
    require(candidate["target"] == contract["target"])
    require(candidate["routes"] == contract["routes"])
    require(candidate["binding_kinds"] == contract["binding_kinds"])
    require(candidate["rate_limits"] == contract["rate_limits"])
    check_keys(candidate["namespace_ids"], {"REPORT_RATE", "REPORT_DUP"})
    first, second = candidate["namespace_ids"]["REPORT_RATE"], candidate["namespace_ids"]["REPORT_DUP"]
    require(type(first) is str and type(second) is str and
            re.fullmatch(r"[1-9][0-9]{0,9}", first) is not None and
            re.fullmatch(r"[1-9][0-9]{0,9}", second) is not None and
            int(first) <= 4294967295 and int(second) <= 4294967295 and first != second)
    require(candidate["turnstile"] == contract["turnstile"])
    require(candidate["brevo"] == contract["brevo"])


def main() -> int:
    # Deliberately no --apply, --plan-path, network access or credential reader.
    if sys.argv[1:] != ["--check-contract"]:
        print(STOP)
        return 2
    try:
        validate_contract(contract_data())
    except (ValueError, OSError, TypeError, KeyError):
        print(STOP)
        return 2
    print("SOURCE_CONTRACT_OK_NOT_LIVE_PROOF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
