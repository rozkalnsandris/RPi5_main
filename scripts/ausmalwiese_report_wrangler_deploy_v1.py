#!/usr/bin/env python3
"""Source-only Wrangler deploy/verification contract for Ausmalwiese reports (#1048).

This module validates exact reviewed application provenance and sanitized
post-deploy evidence. It returns fixed Wrangler/curl command arrays as data.
It does not execute commands, read credentials/secrets, contact Cloudflare,
mutate the host, deploy a Worker, retry, roll back, or clean up.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/ausmalwiese-report-wrangler-deploy-v1.json"

ISSUE = 1048
WORKER = "coloring-pages-report-v1"
STATS_WORKER = "coloring-pages-stats-v1"
WRANGLER_VERSION = "4.135.0"

SOURCE_REPO = "rozkalnsandris/coloring-pages"
SOURCE_COMMIT = "7940c8bef702399f526d82920e848ba4357e5790"
WORKER_PATH = "cloudflare/report-worker.mjs"
WORKER_BLOB = "6560268044bac25e1d63e12edbb2572ca2b9784b"
CONFIG_PATH = "cloudflare/wrangler.report.json"
CONFIG_BLOB = "a49576aa391015e7b0e867bb7eef03c7f90d0987"

COMPATIBILITY_DATE = "2026-10-17"
ROUTES = [
    {"pattern": "ausmalwiese.de/api/report", "zone_name": "ausmalwiese.de"},
    {"pattern": "ausmalwiese.de/api/report/config", "zone_name": "ausmalwiese.de"},
    {"pattern": "www.ausmalwiese.de/api/report", "zone_name": "ausmalwiese.de"},
    {"pattern": "www.ausmalwiese.de/api/report/config", "zone_name": "ausmalwiese.de"},
]
SECRET_NAMES = [
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET",
    "BREVO_API_KEY",
    "REPORT_TO",
]
RATELIMITS = [
    {
        "name": "REPORT_RATE",
        "namespace_id": "2067894450",
        "simple": {"limit": 12, "period": 60},
    },
    {
        "name": "REPORT_DUP",
        "namespace_id": "2051617019",
        "simple": {"limit": 1, "period": 60},
    },
]
BINDING_KINDS = {
    "TURNSTILE_SITE_KEY": "secret_text",
    "TURNSTILE_SECRET": "secret_text",
    "BREVO_API_KEY": "secret_text",
    "REPORT_TO": "secret_text",
    "REPORT_RATE": "ratelimit",
    "REPORT_DUP": "ratelimit",
}
CONFIG_ENDPOINT = "https://ausmalwiese.de/api/report/config"
VERSION_ID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
STOP = "STOP_REPORT_WRANGLER_DEPLOY_SOURCE_ONLY"

RUNTIME_BOUNDARY_ISSUE = 1075
RUNTIME_ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy")
RUNTIME_HOME_ROOT = Path("/home")
RUNTIME_CONTRACT_SOURCE_ROOT = "<fixed-operator-home>/coloring-pages"
RUNTIME_SECRETS_FILE = (
    "/etc/rpi5-secrets/cloudflare/ausmalwiese-report-wrangler-secrets.json"
)
RUNTIME_SECRETS_STDIN = "/dev/stdin"
RUNTIME_OPERATOR = "andris"
RUNTIME_OPERATOR_UID = 1000
RUNTIME_OPERATOR_GID = 1000
RUNTIME_OPERATOR_HOME = str(RUNTIME_HOME_ROOT / RUNTIME_OPERATOR)
RUNTIME_SOURCE_ROOT = str(Path(RUNTIME_OPERATOR_HOME) / "coloring-pages")
RUNTIME_CONFIRM = "OWNER-AUTHORIZED-REPORT-WRANGLER-DEPLOY"
NPX = "/usr/bin/npx"
RUNTIME_ENTRY_PARENTS = ("/", "/usr", "/usr/local", "/usr/local/sbin")
RUNTIME_SECRET_PARENTS = (
    "/",
    "/etc",
    "/etc/rpi5-secrets",
    "/etc/rpi5-secrets/cloudflare",
)
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
    """Fixed source-only stop reason."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _version(value: Any, reason: str) -> str:
    need(type(value) is str and VERSION_ID.fullmatch(value) is not None, reason)
    return value


def _digest(value: Any, reason: str) -> str:
    need(type(value) is str and DIGEST.fullmatch(value) is not None, reason)
    return value


def expected_config() -> dict[str, Any]:
    return {
        "name": WORKER,
        "main": "./report-worker.mjs",
        "compatibility_date": COMPATIBILITY_DATE,
        "workers_dev": False,
        "preview_urls": False,
        "no_bundle": True,
        "routes": ROUTES,
        "secrets": {"required": SECRET_NAMES},
        "ratelimits": RATELIMITS,
    }


def validate_config(config: Any) -> dict[str, Any]:
    """Require the exact reviewed Wrangler config, with no hidden extras."""
    need(type(config) is dict and config == expected_config(), "CONFIG_DRIFT")
    ids = [item["namespace_id"] for item in config["ratelimits"]]
    need(
        len(ids) == len(set(ids))
        and all(type(value) is str and value.isdecimal() and int(value) > 0
                for value in ids),
        "RATE_NAMESPACE_INVALID",
    )
    need(
        all(item["simple"]["period"] in {10, 60}
            for item in config["ratelimits"]),
        "RATE_PERIOD_INVALID",
    )
    return config


def validate_application_evidence(evidence: Any) -> dict[str, Any]:
    """Validate sanitized exact-Git provenance plus parsed reviewed config."""
    expected_keys = {
        "schema",
        "repository",
        "commit",
        "worker_path",
        "worker_blob",
        "config_path",
        "config_blob",
        "config",
    }
    need(type(evidence) is dict and set(evidence) == expected_keys,
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
    """Bind the future one-shot plan to an exact protected secrets path."""
    keys = {
        "worker",
        "wrangler_version",
        "source_commit",
        "worker_blob",
        "config_blob",
        "secrets_file",
        "allow_deploy_once",
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
    path = approval["secrets_file"]
    need(
        type(path) is str
        and 1 <= len(path) <= 512
        and chr(0) not in path
        and not any(ch in path for ch in (chr(10), chr(13))),
        "SECRETS_FILE_INVALID",
    )
    pure = PurePosixPath(path)
    need(pure.is_absolute() and ".." not in pure.parts,
         "SECRETS_FILE_NOT_ABSOLUTE")
    return approval


def application_evidence_from_checkout(
    source_root: Any,
    *,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Bind a future deploy to one exact clean application checkout."""
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

    evidence = {
        "schema": "ausmalwiese.report-wrangler-source.v1",
        "repository": SOURCE_REPO,
        "commit": SOURCE_COMMIT,
        "worker_path": WORKER_PATH,
        "worker_blob": WORKER_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "config": config,
    }
    return validate_application_evidence(evidence)


def validate_protected_secrets_file(
    approval: dict[str, Any],
    *,
    lstat: Any = os.lstat,
    current_uid: int | None = None,
) -> str:
    """Validate metadata only. Secret file contents are never read here."""
    validate_deploy_approval(approval)
    path = approval["secrets_file"]
    try:
        item = lstat(path)
    except OSError:
        raise Blocked("SECRETS_FILE_METADATA") from None
    uid = os.geteuid() if current_uid is None else current_uid
    mode = stat.S_IMODE(item.st_mode)
    need(
        stat.S_ISREG(item.st_mode)
        and item.st_uid == uid
        and item.st_nlink == 1
        and 1 <= item.st_size <= 65536
        and mode in {0o400, 0o600},
        "SECRETS_FILE_UNPROTECTED",
    )
    return "PROTECTED_SECRETS_METADATA_OK_CONTENT_NOT_READ"


def deploy_command(
    application: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    """Return one exact production deploy command as data; never execute it."""
    validate_application_evidence(application)
    validate_deploy_approval(approval)
    message = (
        "source-commit:" + SOURCE_COMMIT
        + ",source-blob:" + WORKER_BLOB
        + ",config-blob:" + CONFIG_BLOB
    )
    command = [
        "npx",
        "--yes",
        f"wrangler@{WRANGLER_VERSION}",
        "deploy",
        "--config",
        CONFIG_PATH,
        "--name",
        WORKER,
        "--no-bundle",
        "--strict",
        "--secrets-file",
        approval["secrets_file"],
        "--tag",
        "git:" + SOURCE_COMMIT,
        "--message",
        message,
    ]
    for forbidden in (
        "--route",
        "--routes",
        "--var",
        "--define",
        "--env-file",
        "secret",
        "versions",
        "triggers",
        "d1",
    ):
        need(forbidden not in command, "DEPLOY_COMMAND_SCOPE")
    return command


def execute_deploy_once(
    source_root: str,
    approval: dict[str, Any],
    *,
    runner: Any = subprocess.run,
    lstat: Any = os.lstat,
    current_uid: int | None = None,
) -> str:
    """Future fixed-purpose launcher. Current issue does not authorize calling it."""
    application = application_evidence_from_checkout(source_root, runner=runner)
    validate_protected_secrets_file(
        approval, lstat=lstat, current_uid=current_uid
    )
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
        and re.search(r"(?<![0-9.])4\.135\.0(?![0-9.])", observed)
        is not None,
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
    kind_ok = (
        stat.S_ISDIR(item.st_mode)
        if directory
        else stat.S_ISREG(item.st_mode)
    )
    need(
        kind_ok
        and item.st_uid == 0
        and item.st_gid == 0
        and (directory or item.st_nlink == 1),
        "RUNTIME_PATH_UNTRUSTED",
    )
    mode = stat.S_IMODE(item.st_mode)
    if expected_mode is None:
        need(
            mode & 0o022 == 0 and mode & 0o700 == 0o700,
            "RUNTIME_PATH_UNTRUSTED",
        )
    else:
        need(mode == expected_mode, "RUNTIME_PATH_UNTRUSTED")
    return item


def trusted_runtime_entry(*, lstat: Any = os.lstat) -> None:
    """Require future root-installed exact entry, never repository execution."""
    need(os.geteuid() == 0, "RUNTIME_ROOT_REQUIRED")
    need(
        str(Path(__file__).absolute()) == str(RUNTIME_ENTRY),
        "RUNTIME_INSTALLED_ENTRY_REQUIRED",
    )
    for parent in RUNTIME_ENTRY_PARENTS:
        _trusted_root_path(
            parent, expected_mode=None, directory=True, lstat=lstat
        )
    _trusted_root_path(
        str(RUNTIME_ENTRY), expected_mode=0o500, directory=False, lstat=lstat
    )


def validate_root_owned_runtime_secret(
    *,
    lstat: Any = os.lstat,
) -> Any:
    """Validate only metadata for the fixed persistent root-owned secret file."""
    for parent in RUNTIME_SECRET_PARENTS:
        expected = 0o700 if parent.endswith("/cloudflare") else None
        _trusted_root_path(
            parent, expected_mode=expected, directory=True, lstat=lstat
        )
    try:
        item = lstat(RUNTIME_SECRETS_FILE)
    except OSError:
        raise Blocked("RUNTIME_SECRETS_METADATA") from None
    need(
        stat.S_ISREG(item.st_mode)
        and item.st_uid == 0
        and item.st_gid == 0
        and item.st_nlink == 1
        and stat.S_IMODE(item.st_mode) == 0o600
        and 1 <= item.st_size <= 65536,
        "RUNTIME_SECRETS_UNPROTECTED",
    )
    return item


def open_root_owned_runtime_secret(
    *,
    lstat: Any = os.lstat,
    opener: Any = os.open,
    fstat: Any = os.fstat,
) -> tuple[int, int]:
    """Open the fixed file without following symlinks; never parse its bytes."""
    before = validate_root_owned_runtime_secret(lstat=lstat)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = opener(RUNTIME_SECRETS_FILE, flags)
    except OSError:
        raise Blocked("RUNTIME_SECRETS_OPEN") from None
    try:
        after = fstat(fd)
        need(
            stat.S_ISREG(after.st_mode)
            and after.st_uid == 0
            and after.st_gid == 0
            and after.st_nlink == 1
            and stat.S_IMODE(after.st_mode) == 0o600
            and after.st_size == before.st_size
            and after.st_dev == before.st_dev
            and after.st_ino == before.st_ino,
            "RUNTIME_SECRETS_OPEN_DRIFT",
        )
        return fd, after.st_size
    except Exception:
        os.close(fd)
        raise


def sealed_operator_secret_memfd(secret_fd: int, size: int) -> int:
    """Kernel-copy secret bytes into anonymous memory; never materialize a value."""
    need(
        type(secret_fd) is int
        and secret_fd >= 0
        and type(size) is int
        and 1 <= size <= 65536,
        "RUNTIME_SECRETS_SIZE",
    )
    fd = -1
    try:
        fd = os.memfd_create(
            "ausmalwiese-report-wrangler-secrets",
            os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
        )
        offset = 0
        while offset < size:
            sent = os.sendfile(fd, secret_fd, offset, size - offset)
            if not isinstance(sent, int) or sent <= 0:
                raise Blocked("RUNTIME_SECRET_COPY")
            offset += sent
        os.fchown(fd, RUNTIME_OPERATOR_UID, RUNTIME_OPERATOR_GID)
        os.fchmod(fd, 0o400)
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(
            fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL,
        )
        item = os.fstat(fd)
        need(
            stat.S_ISREG(item.st_mode)
            and item.st_uid == RUNTIME_OPERATOR_UID
            and item.st_gid == RUNTIME_OPERATOR_GID
            and stat.S_IMODE(item.st_mode) == 0o400
            and item.st_size == size,
            "RUNTIME_SECRET_MEMFD_METADATA",
        )
        return fd
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise Blocked("RUNTIME_SECRET_MEMFD") from None


def runtime_deploy_command(application: dict[str, Any]) -> list[str]:
    """Use anonymous stdin as Wrangler's JSON secrets-file path."""
    approval = {
        "worker": WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_commit": SOURCE_COMMIT,
        "worker_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "secrets_file": RUNTIME_SECRETS_STDIN,
        "allow_deploy_once": True,
    }
    command = deploy_command(application, approval)
    command[0] = NPX
    return command


def _operator_runner(runner: Any) -> Any:
    """Bind child processes to the fixed non-root Wrangler operator."""

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
    opener: Any = os.open,
    fstat: Any = os.fstat,
) -> str:
    """Future installed root boundary; source issue #1075 does not authorize use."""
    trusted_runtime_entry(lstat=lstat)
    operator_runner = _operator_runner(runner)
    application = application_evidence_from_checkout(
        RUNTIME_SOURCE_ROOT,
        runner=operator_runner,
    )

    try:
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
    except Blocked:
        raise
    observed = (version.stdout + "\n" + version.stderr).strip()
    need(
        version.returncode == 0
        and re.search(r"(?<![0-9.])4\.135\.0(?![0-9.])", observed)
        is not None,
        "WRANGLER_VERSION_DRIFT",
    )

    secret_fd = -1
    memfd = -1
    try:
        secret_fd, size = open_root_owned_runtime_secret(
            lstat=lstat, opener=opener, fstat=fstat
        )
        memfd = sealed_operator_secret_memfd(secret_fd, size)
    finally:
        if secret_fd >= 0:
            os.close(secret_fd)

    try:
        command = runtime_deploy_command(application)
        result = operator_runner(
            command,
            cwd=RUNTIME_SOURCE_ROOT,
            stdin=memfd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        need(result.returncode == 0, "DEPLOY_DISPATCH_UNKNOWN")
    except Blocked:
        raise
    except Exception:
        raise Blocked("DEPLOY_DISPATCH_UNKNOWN") from None
    finally:
        if memfd >= 0:
            os.close(memfd)

    return "DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED"


def read_only_verification_commands(version_id: Any) -> list[list[str]]:
    """Return only documented read-only Wrangler checks for the report Worker."""
    version = _version(version_id, "VERSION_ID")
    prefix = ["npx", "--yes", f"wrangler@{WRANGLER_VERSION}"]
    suffix = ["--name", WORKER, "--config", CONFIG_PATH]
    commands = [
        prefix + ["versions", "list"] + suffix + ["--json"],
        prefix + ["deployments", "list"] + suffix + ["--json"],
        prefix + ["versions", "view", version] + suffix + ["--json"],
        prefix + ["secret", "list"] + suffix + ["--format", "json"],
        [
            "curl",
            "--fail-with-body",
            "--silent",
            "--show-error",
            "--max-time",
            "10",
            "--header",
            "accept: application/json",
            CONFIG_ENDPOINT,
        ],
    ]
    return commands


def validate_report_snapshot(snapshot: Any) -> dict[str, Any]:
    """Validate sanitized post-deploy report evidence, never raw secrets."""
    keys = {
        "schema",
        "worker",
        "wrangler_version",
        "source_commit",
        "source_blob",
        "config_blob",
        "latest_version",
        "active_versions",
        "version_tag",
        "version_message",
        "routes",
        "binding_kinds",
        "ratelimits",
        "config_endpoint",
    }
    need(type(snapshot) is dict and set(snapshot) == keys,
         "REPORT_SNAPSHOT_FIELDS")
    need(
        snapshot["schema"] == "ausmalwiese.report-wrangler-post-deploy.v1"
        and snapshot["worker"] == WORKER
        and snapshot["wrangler_version"] == WRANGLER_VERSION
        and snapshot["source_commit"] == SOURCE_COMMIT
        and snapshot["source_blob"] == WORKER_BLOB
        and snapshot["config_blob"] == CONFIG_BLOB,
        "REPORT_SNAPSHOT_TARGET",
    )
    latest = _version(snapshot["latest_version"], "REPORT_LATEST_VERSION")
    active = snapshot["active_versions"]
    need(type(active) is list and len(active) == 1, "REPORT_ACTIVE_COUNT")
    need(
        type(active[0]) is dict
        and set(active[0]) == {"version_id", "percentage"}
        and _version(active[0]["version_id"], "REPORT_ACTIVE_VERSION") == latest
        and type(active[0]["percentage"]) is int
        and active[0]["percentage"] == 100,
        "REPORT_ACTIVE_TRAFFIC",
    )
    expected_message = (
        "source-commit:" + SOURCE_COMMIT
        + ",source-blob:" + WORKER_BLOB
        + ",config-blob:" + CONFIG_BLOB
    )
    need(
        snapshot["version_tag"] == "git:" + SOURCE_COMMIT
        and snapshot["version_message"] == expected_message,
        "REPORT_VERSION_PROVENANCE",
    )
    need(snapshot["routes"] == ROUTES, "REPORT_ROUTE_DRIFT")
    need(snapshot["binding_kinds"] == BINDING_KINDS,
         "REPORT_BINDING_DRIFT")
    need(snapshot["ratelimits"] == RATELIMITS, "REPORT_RATE_DRIFT")
    need(
        snapshot["config_endpoint"] == {
            "url": CONFIG_ENDPOINT,
            "status": 200,
            "site_key_present": True,
        },
        "REPORT_CONFIG_ENDPOINT",
    )
    return snapshot


def validate_stats_snapshot(snapshot: Any) -> dict[str, Any]:
    keys = {
        "schema",
        "worker",
        "latest_version",
        "active_versions",
        "routes_sha256",
        "bindings_sha256",
        "settings_sha256",
    }
    need(type(snapshot) is dict and set(snapshot) == keys,
         "STATS_SNAPSHOT_FIELDS")
    need(
        snapshot["schema"] == "ausmalwiese.stats-unchanged-proof.v1"
        and snapshot["worker"] == STATS_WORKER,
        "STATS_SNAPSHOT_TARGET",
    )
    latest = _version(snapshot["latest_version"], "STATS_LATEST_VERSION")
    active = snapshot["active_versions"]
    need(type(active) is list and len(active) == 1, "STATS_ACTIVE_COUNT")
    need(
        type(active[0]) is dict
        and set(active[0]) == {"version_id", "percentage"}
        and _version(active[0]["version_id"], "STATS_ACTIVE_VERSION") == latest
        and type(active[0]["percentage"]) is int
        and active[0]["percentage"] == 100,
        "STATS_ACTIVE_TRAFFIC",
    )
    _digest(snapshot["routes_sha256"], "STATS_ROUTES_DIGEST")
    _digest(snapshot["bindings_sha256"], "STATS_BINDINGS_DIGEST")
    _digest(snapshot["settings_sha256"], "STATS_SETTINGS_DIGEST")
    return snapshot


def validate_stats_unchanged(before: Any, after: Any) -> str:
    validate_stats_snapshot(before)
    validate_stats_snapshot(after)
    need(after == before, "STATS_DRIFT")
    return canonical_sha256(after)


def check_contract(contract: Any) -> None:
    expected = {
        "schema_version": 1,
        "status": "SOURCE_ONLY_REPORT_WRANGLER_DEPLOY_NO_LIVE",
        "issue": ISSUE,
        "repository": "rozkalnsandris/RPi5_main",
        "worker": WORKER,
        "stats_worker": STATS_WORKER,
        "wrangler_version": WRANGLER_VERSION,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "worker_path": WORKER_PATH,
        "worker_blob": WORKER_BLOB,
        "config_path": CONFIG_PATH,
        "config_blob": CONFIG_BLOB,
        "routes": ROUTES,
        "required_secret_names": SECRET_NAMES,
        "ratelimits": RATELIMITS,
        "deploy_flags": [
            "--no-bundle",
            "--strict",
            "--secrets-file",
            "--tag",
            "--message",
        ],
        "launcher": {
            "future_fixed_deploy_capability": True,
            "verifies_exact_checkout_before_dispatch": True,
            "verifies_protected_secrets_metadata_without_reading_contents": True,
            "current_issue_authorizes_execution": False,
            "root_owned_runtime_boundary_issue": RUNTIME_BOUNDARY_ISSUE,
            "runtime_entry": str(RUNTIME_ENTRY),
            "runtime_source_root": RUNTIME_CONTRACT_SOURCE_ROOT,
            "runtime_secrets_file": RUNTIME_SECRETS_FILE,
            "runtime_secrets_transport": "sealed-memfd-via-dev-stdin",
            "runtime_operator": RUNTIME_OPERATOR,
            "runtime_persistent_permission_widening": False,
        },
        "post_deploy_requires": [
            "exact-source-and-config-provenance",
            "latest-equals-single-active-100-percent",
            "exact-four-report-routes",
            "exact-six-binding-kinds",
            "exact-two-ratelimits",
            "config-endpoint-200-site-key-present",
            "stats-worker-pre-post-snapshot-byte-equivalent",
        ],
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
    }
    need(type(contract) is dict and contract == expected, "CONTRACT_DRIFT")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    # The future runtime branch deliberately does not depend on a repository
    # contract file: only separately installed exact script bytes may reach it.
    if args == ["--runtime-deploy", "--confirm", RUNTIME_CONFIRM]:
        try:
            print(execute_root_owned_runtime_once())
            return 0
        except (Blocked, OSError, ValueError, TypeError):
            print(STOP)
            return 2

    try:
        check_contract(json.loads(CONTRACT.read_text("utf-8")))
        if args == ["--check-contract"]:
            print("REPORT_WRANGLER_DEPLOY_PLAN_OK_SOURCE_ONLY_NO_LIVE")
            return 0
        if (
            len(args) == 5
            and args[0] == "--deploy"
            and args[1] == "--source-root"
            and args[3] == "--secrets-file"
        ):
            approval = {
                "worker": WORKER,
                "wrangler_version": WRANGLER_VERSION,
                "source_commit": SOURCE_COMMIT,
                "worker_blob": WORKER_BLOB,
                "config_blob": CONFIG_BLOB,
                "secrets_file": args[4],
                "allow_deploy_once": True,
            }
            print(execute_deploy_once(args[2], approval))
            return 0
    except (Blocked, OSError, ValueError, TypeError):
        pass
    print(STOP)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
