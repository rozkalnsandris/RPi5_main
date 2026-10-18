#!/usr/bin/env python3
"""Source-only minimal Wrangler deploy contract for Ausmalwiese reports (#1102).

The active report path is deliberately small: one Worker, two exact routes and
one Cloudflare Email Service send_email binding. There are no Report secrets,
Turnstile bindings, rate-limit bindings or Stats dependencies in this contract.

Repository execution remains source-only. The separately installed runtime
entrypoint may later dispatch one exact Wrangler deploy under separate LIVE
authorization.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-wrangler-deploy-v1.json"

ISSUE = 1102
WORKER = "coloring-pages-report-v1"
WRANGLER_VERSION = "4.135.0"

SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "9457bab3c0c6b76fd42011b1bf19965cb39b52db"
WORKER_PATH = "cloudflare/report-worker.mjs"
WORKER_BLOB = "6418a4bebad9f89a2e1045d0ad6476e66549993c"
CONFIG_PATH = "cloudflare/wrangler.report.json"
CONFIG_BLOB = "6ef838ec056c3815416e3a8521c5322bd33b4fed"

COMPATIBILITY_DATE = "2026-10-18"
ROUTES = [
    {"pattern": "ausmalwiese.de/api/report", "zone_name": "ausmalwiese.de"},
    {"pattern": "www.ausmalwiese.de/api/report", "zone_name": "ausmalwiese.de"},
]
EMAIL_BINDING_NAME = "EMAIL"
DESTINATION_LOCAL_PART = "INFO"
DESTINATION_DOMAIN = "ausmalwiese.de"
BINDING_KINDS = {"EMAIL": "send_email"}
SEND_FAILURE_DIAGNOSTIC = {
    "event": "report_email_send_failed",
    "fields": ["event", "code"],
    "code_pattern": "^E_[A-Z0-9_]{1,62}$",
    "fallback": "UNKNOWN",
    "source_provenance_only": True,
    "forbidden": [
        "provider-message",
        "stack",
        "request-payload",
        "activity-id",
        "page",
        "reason",
        "sender",
        "destination",
        "headers",
        "ip",
        "url",
    ],
}

VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
STOP = "STOP_REPORT_WRANGLER_DEPLOY_SOURCE_ONLY"

RUNTIME_ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy")
RUNTIME_OPERATOR = "andris"
RUNTIME_OPERATOR_UID = 1000
RUNTIME_OPERATOR_GID = 1000
RUNTIME_HOME_ROOT = Path("/home")
RUNTIME_OPERATOR_HOME = str(RUNTIME_HOME_ROOT / RUNTIME_OPERATOR)
RUNTIME_SOURCE_ROOT = str(Path(RUNTIME_OPERATOR_HOME) / "coloring-pages")
RUNTIME_CONFIRM = "OWNER-AUTHORIZED-REPORT-WRANGLER-DEPLOY"
NPX = "/usr/bin/npx"
RUNTIME_ENTRY_PARENTS = ("/", "/usr", "/usr/local", "/usr/local/sbin")
RUNTIME_ENV = {
    "HOME": RUNTIME_OPERATOR_HOME,
    "USER": RUNTIME_OPERATOR,
    "LOGNAME": RUNTIME_OPERATOR,
    "XDG_CONFIG_HOME": RUNTIME_OPERATOR_HOME + "/.config",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LC_ALL": "C",
    "WRANGLER_SEND_METRICS": "false",
}


class Blocked(Exception):
    """Static non-secret failure classification."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def destination_address() -> str:
    return DESTINATION_LOCAL_PART + "@" + DESTINATION_DOMAIN


def expected_config() -> dict[str, Any]:
    return {
        "name": WORKER,
        "main": "./report-worker.mjs",
        "compatibility_date": COMPATIBILITY_DATE,
        "workers_dev": False,
        "preview_urls": False,
        "no_bundle": True,
        "routes": ROUTES,
        "send_email": [
            {
                "name": EMAIL_BINDING_NAME,
                "destination_address": destination_address(),
            }
        ],
    }


def validate_config(config: Any) -> dict[str, Any]:
    need(type(config) is dict, "CONFIG_DRIFT")
    binding = config.get("send_email")
    need(
        type(binding) is list
        and len(binding) == 1
        and type(binding[0]) is dict
        and set(binding[0]) == {"name", "destination_address"}
        and binding[0].get("name") == EMAIL_BINDING_NAME,
        "CONFIG_DRIFT",
    )
    destination = binding[0].get("destination_address")
    need(destination == destination_address(), "CONFIG_DRIFT")
    need(config == expected_config(), "CONFIG_DRIFT")
    return config


def validate_application_evidence(evidence: Any) -> dict[str, Any]:
    keys = {
        "schema", "repository", "commit", "worker_path", "worker_blob",
        "config_path", "config_blob", "config",
    }
    need(type(evidence) is dict and set(evidence) == keys,
         "APPLICATION_EVIDENCE_FIELDS")
    need(
        evidence["schema"] == "ausmalwiese.report-wrangler-source.v1"
        and evidence["repository"] == SOURCE_REPO
        and evidence["commit"] == SOURCE_COMMIT
        and evidence["worker_path"] == WORKER_PATH
        and evidence["worker_blob"] == WORKER_BLOB
        and evidence["config_path"] == CONFIG_PATH
        and evidence["config_blob"] == CONFIG_BLOB,
        "APPLICATION_PROVENANCE_DRIFT",
    )
    validate_config(evidence["config"])
    return evidence


def validate_deploy_approval(approval: Any) -> dict[str, Any]:
    keys = {
        "worker", "wrangler_version", "source_commit", "worker_blob",
        "config_blob", "allow_deploy_once",
    }
    need(type(approval) is dict and set(approval) == keys,
         "DEPLOY_APPROVAL_FIELDS")
    need(
        approval["worker"] == WORKER
        and approval["wrangler_version"] == WRANGLER_VERSION
        and approval["source_commit"] == SOURCE_COMMIT
        and approval["worker_blob"] == WORKER_BLOB
        and approval["config_blob"] == CONFIG_BLOB
        and approval["allow_deploy_once"] is True,
        "DEPLOY_APPROVAL_UNBOUND",
    )
    return approval


def application_evidence_from_checkout(
    source_root: Any,
    *,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    need(type(source_root) is str and 1 <= len(source_root) <= 1024,
         "SOURCE_ROOT_INVALID")
    root = Path(source_root)
    need(root.is_absolute() and root.is_dir() and not root.is_symlink(),
         "SOURCE_ROOT_UNTRUSTED")

    worker = root / WORKER_PATH
    config_path = root / CONFIG_PATH
    need(worker.is_file() and not worker.is_symlink(), "WORKER_FILE_UNTRUSTED")
    need(config_path.is_file() and not config_path.is_symlink(),
         "CONFIG_FILE_UNTRUSTED")

    def git(args: list[str]) -> Any:
        try:
            return runner(
                ["git", "-C", str(root)] + args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise Blocked("GIT_CHECK_FAILED") from None

    head = git(["rev-parse", "HEAD"])
    need(head.returncode == 0 and head.stdout.strip() == SOURCE_COMMIT,
         "SOURCE_COMMIT_DRIFT")

    tree = git(["ls-tree", "HEAD", "--", WORKER_PATH, CONFIG_PATH])
    need(tree.returncode == 0, "SOURCE_TREE_FAILED")
    entries: dict[str, str] = {}
    for line in tree.stdout.splitlines():
        match = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t(.+)", line)
        need(match is not None, "SOURCE_TREE_SHAPE")
        entries[match.group(2)] = match.group(1)
    need(
        entries == {WORKER_PATH: WORKER_BLOB, CONFIG_PATH: CONFIG_BLOB},
        "SOURCE_BLOB_DRIFT",
    )

    clean = git(["diff", "--quiet", "HEAD", "--", WORKER_PATH, CONFIG_PATH])
    need(clean.returncode == 0, "SOURCE_WORKTREE_DRIFT")

    try:
        config = json.loads(config_path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise Blocked("CONFIG_READ_FAILED") from None

    return validate_application_evidence({
        "schema": "ausmalwiese.report-wrangler-source.v1",
        "repository": SOURCE_REPO,
        "commit": SOURCE_COMMIT,
        "worker_path": WORKER_PATH,
        "worker_blob": WORKER_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "config": config,
    })


def deploy_command(
    application: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    validate_application_evidence(application)
    validate_deploy_approval(approval)
    message = (
        "source-commit:" + SOURCE_COMMIT
        + ",source-blob:" + WORKER_BLOB
        + ",config-blob:" + CONFIG_BLOB
    )
    command = [
        "npx", "--yes", f"wrangler@{WRANGLER_VERSION}", "deploy",
        "--config", CONFIG_PATH,
        "--name", WORKER,
        "--no-bundle",
        "--strict",
        "--tag", "git:" + SOURCE_COMMIT,
        "--message", message,
    ]
    joined = " ".join(command)
    for forbidden in (
        "--secrets-file", "--env-file", " secret ", " d1 ",
        "--route", "--routes", "--var", "--define",
    ):
        need(forbidden not in joined, "DEPLOY_COMMAND_SCOPE")
    return command


def execute_deploy_once(
    source_root: str,
    approval: dict[str, Any],
    *,
    runner: Any = subprocess.run,
) -> str:
    application = application_evidence_from_checkout(source_root, runner=runner)
    command = deploy_command(application, approval)

    def invoke(args: list[str], *, timeout: int) -> Any:
        try:
            return runner(
                args,
                cwd=source_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise Blocked("DEPLOY_DISPATCH_UNKNOWN") from None

    version = invoke(
        ["npx", "--yes", f"wrangler@{WRANGLER_VERSION}", "--version"],
        timeout=60,
    )
    observed = (version.stdout + "\n" + version.stderr).strip()
    need(
        version.returncode == 0
        and re.search(r"(?<![0-9.])4\.135\.0(?![0-9.])", observed),
        "WRANGLER_VERSION_DRIFT",
    )

    result = invoke(command, timeout=120)
    need(result.returncode == 0, "DEPLOY_DISPATCH_UNKNOWN")
    return "DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED"


def _trusted_root_path(
    path: str,
    *,
    expected_mode: int | None,
    directory: bool,
    lstat: Any = os.lstat,
) -> Any:
    try:
        item = lstat(path)
    except OSError:
        raise Blocked("RUNTIME_PATH_METADATA") from None
    kind_ok = stat.S_ISDIR(item.st_mode) if directory else stat.S_ISREG(item.st_mode)
    need(
        kind_ok and item.st_uid == 0 and item.st_gid == 0
        and (directory or item.st_nlink == 1),
        "RUNTIME_PATH_UNTRUSTED",
    )
    mode = stat.S_IMODE(item.st_mode)
    if expected_mode is None:
        need(mode & 0o022 == 0 and mode & 0o700 == 0o700,
             "RUNTIME_PATH_UNTRUSTED")
    else:
        need(mode == expected_mode, "RUNTIME_PATH_UNTRUSTED")
    return item


def trusted_runtime_entry(*, lstat: Any = os.lstat) -> None:
    need(os.geteuid() == 0, "RUNTIME_ROOT_REQUIRED")
    need(str(Path(__file__).absolute()) == str(RUNTIME_ENTRY),
         "RUNTIME_INSTALLED_ENTRY_REQUIRED")
    for parent in RUNTIME_ENTRY_PARENTS:
        _trusted_root_path(parent, expected_mode=None, directory=True, lstat=lstat)
    _trusted_root_path(
        str(RUNTIME_ENTRY), expected_mode=0o500, directory=False, lstat=lstat
    )


def runtime_deploy_command(application: dict[str, Any]) -> list[str]:
    approval = {
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_commit": SOURCE_COMMIT,
        "worker_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "allow_deploy_once": True,
    }
    command = deploy_command(application, approval)
    command[0] = NPX
    return command


def _operator_runner(runner: Any) -> Any:
    def invoke(args: list[str], **kwargs: Any) -> Any:
        try:
            return runner(
                args,
                user=RUNTIME_OPERATOR_UID,
                group=RUNTIME_OPERATOR_GID,
                extra_groups=(),
                env=RUNTIME_ENV,
                **kwargs,
            )
        except (OSError, subprocess.SubprocessError):
            raise Blocked("RUNTIME_OPERATOR_EXEC") from None
    return invoke


def execute_root_owned_runtime_once(
    *,
    runner: Any = subprocess.run,
    lstat: Any = os.lstat,
) -> str:
    trusted_runtime_entry(lstat=lstat)
    operator_runner = _operator_runner(runner)
    application = application_evidence_from_checkout(
        RUNTIME_SOURCE_ROOT, runner=operator_runner
    )

    version = operator_runner(
        [NPX, "--yes", f"wrangler@{WRANGLER_VERSION}", "--version"],
        cwd=RUNTIME_SOURCE_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    observed = (version.stdout + "\n" + version.stderr).strip()
    need(
        version.returncode == 0
        and re.search(r"(?<![0-9.])4\.135\.0(?![0-9.])", observed),
        "WRANGLER_VERSION_DRIFT",
    )

    command = runtime_deploy_command(application)
    try:
        result = operator_runner(
            command,
            cwd=RUNTIME_SOURCE_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
    except Blocked:
        raise
    need(result.returncode == 0, "DEPLOY_DISPATCH_UNKNOWN")
    return "DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED"


def read_only_verification_commands(version_id: Any) -> list[list[str]]:
    need(
        type(version_id) is str and VERSION_ID.fullmatch(version_id) is not None,
        "VERSION_ID_INVALID",
    )
    prefix = ["npx", "--yes", f"wrangler@{WRANGLER_VERSION}"]
    suffix = ["--name", WORKER, "--config", CONFIG_PATH]
    return [
        prefix + ["versions", "list"] + suffix + ["--json"],
        prefix + ["deployments", "list"] + suffix + ["--json"],
        prefix + ["versions", "view", version_id] + suffix + ["--json"],
    ]


def validate_report_snapshot(snapshot: Any) -> dict[str, Any]:
    keys = {
        "schema", "worker", "wrangler_version", "source_commit", "source_blob",
        "config_blob", "latest_version", "active_versions", "version_tag",
        "version_message", "routes", "binding_kinds",
    }
    need(type(snapshot) is dict and set(snapshot) == keys,
         "REPORT_SNAPSHOT_FIELDS")
    latest = snapshot["latest_version"]
    need(type(latest) is str and VERSION_ID.fullmatch(latest),
         "REPORT_VERSION_INVALID")
    active = snapshot["active_versions"]
    need(
        type(active) is list and len(active) == 1
        and type(active[0]) is dict
        and set(active[0]) == {"version_id", "percentage"}
        and active[0]["version_id"] == latest
        and active[0]["percentage"] == 100,
        "REPORT_ACTIVE_INVALID",
    )
    expected_message = (
        "source-commit:" + SOURCE_COMMIT
        + ",source-blob:" + WORKER_BLOB
        + ",config-blob:" + CONFIG_BLOB
    )
    need(
        snapshot["schema"] == "ausmalwiese.report-wrangler-post-deploy.v2"
        and snapshot["worker"] == WORKER
        and snapshot["wrangler_version"] == WRANGLER_VERSION
        and snapshot["source_commit"] == SOURCE_COMMIT
        and snapshot["source_blob"] == WORKER_BLOB
        and snapshot["config_blob"] == CONFIG_BLOB
        and snapshot["version_tag"] == "git:" + SOURCE_COMMIT
        and snapshot["version_message"] == expected_message
        and snapshot["routes"] == ROUTES
        and snapshot["binding_kinds"] == BINDING_KINDS,
        "REPORT_SNAPSHOT_DRIFT",
    )
    return snapshot


def expected_contract() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "status": "SOURCE_ONLY_REPORT_WRANGLER_DEPLOY_NO_LIVE",
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
        "routes": ROUTES,
        "email_binding": {
            "name": EMAIL_BINDING_NAME,
            "destination_local_part": DESTINATION_LOCAL_PART,
            "destination_domain": DESTINATION_DOMAIN,
            "destination_source": "assembled-fixed-config",
        },
        "deploy_flags": ["--no-bundle", "--strict", "--tag", "--message"],
        "post_deploy_requires": [
            "exact-source-and-config-provenance",
            "latest-equals-single-active-100-percent",
            "exact-two-report-routes",
            "exact-one-send-email-binding",
            "exact-info-destination-case",
            "sanitized-email-send-failure-diagnostic-by-exact-worker-blob",
        ],
        "send_failure_diagnostic": SEND_FAILURE_DIAGNOSTIC,
        "actions": {
            "run_wrangler": False,
            "cloudflare_request": False,
            "credential_or_secret_access": False,
            "host_install": False,
            "merge": False,
            "live": False,
            "retry": False,
            "rollback": False,
            "cleanup": False,
        },
        "launcher": {
            "future_fixed_deploy_capability": True,
            "verifies_exact_checkout_before_dispatch": True,
            "requires_report_secrets": False,
            "stats_dependency": False,
            "current_issue_authorizes_execution": False,
            "runtime_entry": str(RUNTIME_ENTRY),
            "runtime_source_root": "<fixed-operator-home>/coloring-pages",
            "runtime_operator": RUNTIME_OPERATOR,
            "runtime_persistent_permission_widening": False,
        },
    }


def check_contract(contract: Any) -> None:
    need(type(contract) is dict and contract == expected_contract(), "CONTRACT_DRIFT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-contract", action="store_true")
    parser.add_argument("--runtime-deploy", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    if args.check_contract and not args.runtime_deploy and not args.confirm:
        try:
            check_contract(json.loads(CONTRACT.read_text("utf-8")))
        except (Blocked, OSError, UnicodeError, json.JSONDecodeError, TypeError):
            print(STOP)
            return 2
        print("REPORT_WRANGLER_DEPLOY_V2_OK_SOURCE_ONLY_NO_LIVE")
        return 0

    if args.runtime_deploy and not args.check_contract and args.confirm == RUNTIME_CONFIRM:
        if str(Path(__file__).absolute()) != str(RUNTIME_ENTRY):
            print(STOP)
            return 2
        try:
            result = execute_root_owned_runtime_once()
        except Blocked:
            print(STOP)
            return 2
        print(result)
        return 0

    print(STOP)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
