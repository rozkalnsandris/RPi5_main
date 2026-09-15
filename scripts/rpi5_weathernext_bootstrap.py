#!/usr/bin/env python3
"""Fixed WeatherNext private-installer bootstrap capability for the V12 engine."""
from __future__ import annotations

import email.utils
import hashlib
import json
import os
import pathlib
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from rpi5_deploy_lib import (
    CTX,
    DeployError,
    append_log,
    engine_source_preflight,
    fsync_dir,
    github_checks,
    host_identity,
    operation_lock,
    require_root,
    run,
    safe_target_parent,
    verify_dir,
)

SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_REPOSITORY_ID = 1323383044
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MINIMUM_REVIEWED_ANCESTOR = "1fa9ace14aa8b0b7c3c46ac465f1a5093d35d0a7"
AUTHORIZATION_REPOSITORY = "rozkalnsandris/deploy-authorizations"
AUTHORIZATION_REPOSITORY_ID = 1350486101
QUEUE_REPOSITORY = "rozkalnsandris/ops-workflows"
QUEUE_REPOSITORY_ID = 1328835922
OWNER_USER_ID = 277435981
LIVE_AUTH_SCHEMA = "rozkalns.live-auth.v1"
TTL_SECONDS = 600
MAX_FUTURE_SKEW_SECONDS = 30
MAX_BODY_BYTES = 16 * 1024

OPERATION_ID = "rpi5.weathernext-private-installer-boundary.install.v1"
TARGET_ALIAS = "rpi5-weathernext-private-installer-boundary"
EXECUTION_LOCATION_CLASS = "trusted-home-host"
REPOSITORY_ENTRYPOINT = "scripts/rpi5-deploy"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
BASELINE = {
    "kind": "resolver",
    "value": "rpi5.weathernext-private-installer-boundary-prestate.v1",
}
MUTATION_BUDGET = [
    {"category": "git.weathernext-private-installer-checkout-fetch", "max_operations": 1},
    {"category": "git.weathernext-private-installer-checkout-worktree-add", "max_operations": 1},
    {"category": "filesystem.weathernext-private-installer-entrypoint-install", "max_operations": 1},
]
ROLLBACK_POLICY = "NONE"
EXCLUSIONS = [
    "caller-selected command/path/argv/environment/repository authority",
    "generic root shell or generic sudo authority",
    "package/service/systemd/Docker/network/Cloudflare mutation",
    "credential/ADC/service-account/IAM read or mutation",
    "Google project/API/Analytics Hub/BigQuery action",
    "Weather application staging or private runtime materialization",
    "SQLite/schema/corpus/snapshot mutation",
    "automatic retry/cleanup/rollback after consume",
]
FIXED_DEPENDENCIES = [
    f"source-repository-id:{SOURCE_REPOSITORY_ID}",
    f"minimum-reviewed-ancestor:{MINIMUM_REVIEWED_ANCESTOR}",
    "v12-root-isolated-deploy-engine",
    "identity-only-live-auth-issue-number",
]

# Fresh read-only host evidence for #557 established this as the only compatible
# existing operator-owned RPi5_main manager checkout. It is Git object/remote
# source only; its checked-out content is never execution authority.
MANAGER_CHECKOUT = "/home/andris/RPi5_main"
TRUSTED_CHECKOUT = "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
ENTRYPOINT_SOURCE = "ops/bin/rpi5-weathernext-private-host-privileged-install"
ENTRYPOINT_DESTINATION = "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install"
ENTRYPOINT_MODE = 0o755
CONSUMED_PREFIX = "weathernext-private-installer-bootstrap-consumed-"

START_MARKER = "<!-- rozkalns-live-auth:v1 -->"
END_MARKER = "<!-- /rozkalns-live-auth:v1 -->"
PAYLOAD_RE = re.compile(
    re.escape(START_MARKER) + r"\n```json\n(?P<payload>.*?)\n```\n" + re.escape(END_MARKER),
    re.DOTALL,
)
TITLE_RE = re.compile(r"^\[LIVE-AUTH\]\[PENDING\] (?P<target>[a-z0-9][a-z0-9._-]{0,63})$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
QUEUE_TITLE_RE = re.compile(r"^\[DEPLOY-QUEUE\]\[(?P<state>[A-Z_]+)\]\s+.+$")
QUEUE_BULLET_RE = re.compile(r"^- \*\*(?P<key>[a-z0-9_]+):\*\*\s+(?P<value>.+)$")
LEADING_CODE_RE = re.compile(r"^`(?P<value>[^`]+)`")
PAYLOAD_FIELDS = frozenset({
    "schema", "request_id", "queue_repository", "queue_issue", "source_repository",
    "source_sha", "target_alias", "operation_id", "expected_baseline",
    "mutation_budget", "rollback_policy", "exclusions", "dependencies",
})
QUEUE_FIELDS = frozenset({
    "source_repository", "exact_git_sha_or_waiting_merge", "source_pr_or_issue_if_applicable",
    "target_alias", "execution_location_class", "repository_entrypoint",
    "expected_baseline_when_observable", "read_only_preflight", "verification_and_reconciliation",
    "allowed_mutation_categories_and_limits", "explicit_exclusions", "dependencies_if_any",
    "deploy_class_and_extra_owner_gate_requirement",
})


@dataclass(frozen=True)
class AcceptedAuthorization:
    issue_id: int
    issue_number: int
    request_id: str
    canonical_payload_json: str
    canonical_payload_sha256: str
    raw_body_sha256: str

    @property
    def payload(self) -> Mapping[str, Any]:
        return _strict_json(self.canonical_payload_json)


@dataclass(frozen=True)
class NormalizedQueue:
    issue_id: int
    issue_number: int
    canonical_json: str
    raw_body_sha256: str
    contract_sha256: str

    @property
    def payload(self) -> Mapping[str, Any]:
        return _strict_json(self.canonical_json)


class BootstrapStop(DeployError):
    pass


def capability_descriptor() -> dict[str, str]:
    return {
        "status": "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED",
        "operation": OPERATION_ID,
        "target": TARGET_ALIAS,
        "caller_input": "authorization_issue_number",
        "manager_checkout": MANAGER_CHECKOUT,
        "rollback_policy": ROLLBACK_POLICY,
    }


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapStop(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BootstrapStop(f"invalid JSON number: {value}")


def _strict_json(raw: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except BootstrapStop:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise BootstrapStop("malformed strict JSON") from exc
    if type(value) is not dict:
        raise BootstrapStop("JSON payload root must be an object")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BootstrapStop("payload is not canonicalizable") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1 or value > 2**63 - 1:
        raise BootstrapStop(f"{where} must be a positive integer")
    return value


def _uuid4(value: Any) -> str:
    if type(value) is not str:
        raise BootstrapStop("request_id must be canonical UUIDv4")
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise BootstrapStop("request_id must be canonical UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise BootstrapStop("request_id must be canonical UUIDv4")
    return value


def _server_time(value: str) -> datetime:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BootstrapStop("GitHub Date header is invalid") from exc
    if parsed.tzinfo is None:
        raise BootstrapStop("GitHub Date header has no timezone")
    return parsed.astimezone(timezone.utc)


def _gh_api_json(path: str) -> tuple[Mapping[str, Any], datetime]:
    result = run(
        ["gh", "api", "-i", "-H", "Accept: application/vnd.github+json",
         "-H", "X-GitHub-Api-Version: 2022-11-28", path],
        cwd=CTX.repo,
        timeout=120,
        as_user=True,
    )
    raw = result.stdout.replace("\r\n", "\n")
    separators = [m.start() for m in re.finditer(r"\n\n(?=[\[{])", raw)]
    if not separators:
        raise BootstrapStop("GitHub API response omitted headers or JSON body")
    split_at = separators[-1]
    headers, body = raw[:split_at], raw[split_at + 2:]
    dates = re.findall(r"(?im)^date:\s*(.+?)\s*$", headers)
    if not dates:
        raise BootstrapStop("GitHub API response omitted Date header")
    return _strict_json(body), _server_time(dates[-1])


def _require_repo_identity(repository: str, repository_id: int) -> None:
    value, _ = _gh_api_json(f"repos/{repository}")
    if value.get("id") != repository_id or value.get("full_name") != repository:
        raise BootstrapStop(f"repository identity drifted: {repository}")


def _validate_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if frozenset(payload) != PAYLOAD_FIELDS:
        raise BootstrapStop("LIVE-AUTH payload keys mismatch")
    if payload.get("schema") != LIVE_AUTH_SCHEMA:
        raise BootstrapStop("LIVE-AUTH schema mismatch")
    _uuid4(payload.get("request_id"))
    if payload.get("queue_repository") != QUEUE_REPOSITORY:
        raise BootstrapStop("LIVE-AUTH queue repository mismatch")
    _positive_int(payload.get("queue_issue"), "queue_issue")
    if payload.get("source_repository") != SOURCE_REPOSITORY:
        raise BootstrapStop("LIVE-AUTH source repository mismatch")
    source_sha = payload.get("source_sha")
    if type(source_sha) is not str or SHA_RE.fullmatch(source_sha) is None:
        raise BootstrapStop("LIVE-AUTH source SHA is invalid")
    if payload.get("target_alias") != TARGET_ALIAS or payload.get("operation_id") != OPERATION_ID:
        raise BootstrapStop("LIVE-AUTH operation or target mismatch")
    if payload.get("expected_baseline") != BASELINE:
        raise BootstrapStop("LIVE-AUTH baseline mismatch")
    if payload.get("mutation_budget") != MUTATION_BUDGET:
        raise BootstrapStop("LIVE-AUTH mutation budget mismatch")
    if payload.get("rollback_policy") != ROLLBACK_POLICY:
        raise BootstrapStop("LIVE-AUTH rollback policy mismatch")
    if payload.get("exclusions") != EXCLUSIONS:
        raise BootstrapStop("LIVE-AUTH exclusions mismatch")
    deps = payload.get("dependencies")
    if type(deps) is not list or not all(type(item) is str for item in deps):
        raise BootstrapStop("LIVE-AUTH dependencies are invalid")
    return payload


def accept_authorization(issue: Mapping[str, Any], *, server_time: datetime) -> AcceptedAuthorization:
    if type(issue) is not dict or issue.get("state") != "open" or issue.get("pull_request") is not None:
        raise BootstrapStop("LIVE-AUTH must be one open Issue")
    issue_id = _positive_int(issue.get("id"), "issue.id")
    issue_number = _positive_int(issue.get("number"), "issue.number")
    user = issue.get("user")
    if type(user) is not dict or user.get("id") != OWNER_USER_ID or user.get("type") != "User":
        raise BootstrapStop("LIVE-AUTH author is not the configured human owner")
    if issue.get("performed_via_github_app") is not None:
        raise BootstrapStop("app-authored LIVE-AUTH is forbidden")
    title = issue.get("title")
    match = TITLE_RE.fullmatch(title) if type(title) is str else None
    if match is None or match.group("target") != TARGET_ALIAS:
        raise BootstrapStop("LIVE-AUTH title target mismatch")
    created_at = issue.get("created_at")
    if type(created_at) is not str or not created_at.endswith("Z"):
        raise BootstrapStop("LIVE-AUTH creation time is invalid")
    try:
        created = datetime.fromisoformat(created_at[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise BootstrapStop("LIVE-AUTH creation time is invalid") from exc
    age = (server_time.astimezone(timezone.utc) - created).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > TTL_SECONDS:
        raise BootstrapStop("LIVE-AUTH is expired or from the future")
    body = issue.get("body")
    if type(body) is not str or len(body.encode("utf-8", "strict")) > MAX_BODY_BYTES:
        raise BootstrapStop("LIVE-AUTH body is invalid or too large")
    if body.count(START_MARKER) != 1 or body.count(END_MARKER) != 1:
        raise BootstrapStop("LIVE-AUTH authority block count is invalid")
    match = PAYLOAD_RE.search(body)
    if match is None:
        raise BootstrapStop("LIVE-AUTH authority block is malformed")
    payload = _validate_payload(_strict_json(match.group("payload")))
    canonical = _canonical_json(payload)
    return AcceptedAuthorization(
        issue_id=issue_id,
        issue_number=issue_number,
        request_id=str(payload["request_id"]),
        canonical_payload_json=canonical,
        canonical_payload_sha256=_sha256_text(canonical),
        raw_body_sha256=_sha256_text(body),
    )


def verify_authorization_unchanged(accepted: AcceptedAuthorization, issue: Mapping[str, Any], *, server_time: datetime) -> None:
    current = accept_authorization(issue, server_time=server_time)
    if current != accepted:
        raise BootstrapStop("LIVE-AUTH changed after acceptance")


def _queue_fields(body: Any) -> dict[str, str]:
    if type(body) is not str:
        raise BootstrapStop("queue body is invalid")
    lines = body.splitlines()
    if lines.count("## Queue contract") != 1:
        raise BootstrapStop("queue contract section count is invalid")
    start = lines.index("## Queue contract") + 1
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            section.append(line)
    fields: dict[str, str] = {}
    for line in section:
        match = QUEUE_BULLET_RE.fullmatch(line)
        if match is None or match.group("key") in fields:
            raise BootstrapStop("queue contract contains unsupported or duplicate fields")
        fields[match.group("key")] = match.group("value")
    if frozenset(fields) != QUEUE_FIELDS:
        raise BootstrapStop("queue contract fields mismatch")
    return fields


def _leading_code(fields: Mapping[str, str], key: str) -> str:
    match = LEADING_CODE_RE.match(fields[key])
    if match is None:
        raise BootstrapStop(f"queue field lacks machine token: {key}")
    return match.group("value")


def normalize_ready_queue(issue: Mapping[str, Any]) -> NormalizedQueue:
    if type(issue) is not dict or issue.get("state") != "open" or issue.get("pull_request") is not None:
        raise BootstrapStop("deploy queue must be one open Issue")
    issue_id = _positive_int(issue.get("id"), "queue.id")
    issue_number = _positive_int(issue.get("number"), "queue.number")
    title = issue.get("title")
    title_match = QUEUE_TITLE_RE.fullmatch(title) if type(title) is str else None
    if title_match is None or title_match.group("state") != "READY":
        raise BootstrapStop("deploy queue is not READY")
    body = issue.get("body")
    fields = _queue_fields(body)
    if _leading_code(fields, "source_repository") != SOURCE_REPOSITORY:
        raise BootstrapStop("queue source repository mismatch")
    source_sha = _leading_code(fields, "exact_git_sha_or_waiting_merge")
    if SHA_RE.fullmatch(source_sha) is None:
        raise BootstrapStop("queue source SHA is invalid")
    fixed = {
        "target_alias": TARGET_ALIAS,
        "execution_location_class": EXECUTION_LOCATION_CLASS,
        "repository_entrypoint": REPOSITORY_ENTRYPOINT,
        "deploy_class_and_extra_owner_gate_requirement": DEPLOY_CLASS,
    }
    for key, expected in fixed.items():
        if _leading_code(fields, key) != expected:
            raise BootstrapStop(f"queue fixed machine field mismatch: {key}")
    contract_sha = _sha256_text(_canonical_json(dict(sorted(fields.items()))))
    normalized = {
        "repository": QUEUE_REPOSITORY,
        "issue_number": issue_number,
        "state": "READY",
        "source_repository": SOURCE_REPOSITORY,
        "source_sha": source_sha,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "expected_baseline": BASELINE,
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "exclusions": EXCLUSIONS,
        "dependencies": [*FIXED_DEPENDENCIES, f"queue-contract-sha256:{contract_sha}"],
    }
    return NormalizedQueue(
        issue_id=issue_id,
        issue_number=issue_number,
        canonical_json=_canonical_json(normalized),
        raw_body_sha256=_sha256_text(str(body)),
        contract_sha256=contract_sha,
    )


def validate_queue_binding(accepted: AcceptedAuthorization, queue: NormalizedQueue) -> None:
    auth = accepted.payload
    normalized = queue.payload
    comparisons = {
        "queue_repository": (auth["queue_repository"], normalized["repository"]),
        "queue_issue": (auth["queue_issue"], normalized["issue_number"]),
        "source_repository": (auth["source_repository"], normalized["source_repository"]),
        "source_sha": (auth["source_sha"], normalized["source_sha"]),
        "target_alias": (auth["target_alias"], normalized["target_alias"]),
        "operation_id": (auth["operation_id"], normalized["operation_id"]),
        "expected_baseline": (auth["expected_baseline"], normalized["expected_baseline"]),
        "mutation_budget": (auth["mutation_budget"], normalized["mutation_budget"]),
        "rollback_policy": (auth["rollback_policy"], normalized["rollback_policy"]),
        "exclusions": (auth["exclusions"], normalized["exclusions"]),
        "dependencies": (auth["dependencies"], normalized["dependencies"]),
    }
    for key, (actual, expected) in comparisons.items():
        if actual != expected:
            raise BootstrapStop(f"LIVE-AUTH and READY queue binding mismatch: {key}")


def verify_queue_unchanged(accepted: NormalizedQueue, issue: Mapping[str, Any]) -> None:
    current = normalize_ready_queue(issue)
    if current != accepted:
        raise BootstrapStop("READY queue changed after acceptance")


def _git_checkout(path: pathlib.Path, *args: str, check: bool = True, as_manager_user: bool = False) -> str:
    result = run(
        ["git", "-c", f"safe.directory={path}", "-C", str(path), *args],
        check=check,
        timeout=300,
        as_user=as_manager_user,
    )
    return result.stdout.strip()


def _manager_git(manager: pathlib.Path, *args: str, check: bool = True) -> str:
    return _git_checkout(manager, *args, check=check, as_manager_user=True)


def _manager_checkout() -> pathlib.Path:
    manager = pathlib.Path(MANAGER_CHECKOUT) if not CTX.test_mode else CTX.rooted(MANAGER_CHECKOUT)
    info = manager.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise BootstrapStop("fixed manager checkout is not a real directory")
    if not CTX.test_mode and info.st_uid != CTX.repo.stat().st_uid:
        raise BootstrapStop("fixed manager checkout owner drifted")
    git_dir = manager / ".git"
    git_info = git_dir.lstat()
    if not stat.S_ISDIR(git_info.st_mode) or stat.S_ISLNK(git_info.st_mode):
        raise BootstrapStop("fixed manager checkout Git directory is unsafe")
    if _manager_git(manager, "remote", "get-url", "origin") != REVIEWED_ORIGIN:
        raise BootstrapStop("fixed manager checkout origin drifted")
    return manager


def _manager_snapshot(manager: pathlib.Path) -> tuple[str, str]:
    status = _manager_git(manager, "status", "--porcelain=v1", "--untracked-files=all")
    return _manager_git(manager, "rev-parse", "HEAD"), _sha256_text(status)


def _require_manager_snapshot(manager: pathlib.Path, before: tuple[str, str]) -> None:
    if _manager_snapshot(manager) != before:
        raise BootstrapStop("manager working tree/index/HEAD changed during bootstrap")


def _remote_main_sha(manager: pathlib.Path) -> str:
    output = _manager_git(manager, "ls-remote", "--exit-code", "origin", "refs/heads/main")
    rows = [line.split() for line in output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != "refs/heads/main" or SHA_RE.fullmatch(rows[0][0]) is None:
        raise BootstrapStop("reviewed origin main ref response is invalid")
    return rows[0][0]


def _require_source_current(source_sha: str) -> None:
    repo, _ = _gh_api_json(f"repos/{SOURCE_REPOSITORY}")
    if repo.get("id") != SOURCE_REPOSITORY_ID or repo.get("full_name") != SOURCE_REPOSITORY:
        raise BootstrapStop("source repository identity drifted")
    ref, _ = _gh_api_json(f"repos/{SOURCE_REPOSITORY}/git/ref/heads/main")
    obj = ref.get("object") if type(ref) is dict else None
    if type(obj) is not dict or obj.get("type") != "commit" or obj.get("sha") != source_sha:
        raise BootstrapStop("authorized source SHA is not current RPi5_main/main")
    comparison, _ = _gh_api_json(f"repos/{SOURCE_REPOSITORY}/compare/{MINIMUM_REVIEWED_ANCESTOR}...{source_sha}")
    merge_base = comparison.get("merge_base_commit") if type(comparison) is dict else None
    if type(merge_base) is not dict or merge_base.get("sha") != MINIMUM_REVIEWED_ANCESTOR:
        raise BootstrapStop("authorized source is not descended from the reviewed WeatherNext baseline")
    checks = github_checks(source_sha)
    if "validate" not in {str(name) for name in checks.get("names", [])}:
        raise BootstrapStop("required exact-main validate check is missing")


def _read_authorization(issue_number: int) -> AcceptedAuthorization:
    _require_repo_identity(AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID)
    issue, server_time = _gh_api_json(f"repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}")
    return accept_authorization(issue, server_time=server_time)


def _read_queue(issue_number: int) -> NormalizedQueue:
    _require_repo_identity(QUEUE_REPOSITORY, QUEUE_REPOSITORY_ID)
    issue, _ = _gh_api_json(f"repos/{QUEUE_REPOSITORY}/issues/{issue_number}")
    return normalize_ready_queue(issue)


def _trusted_checkout_state(manager: pathlib.Path, source_sha: str) -> str:
    trusted = CTX.rooted(TRUSTED_CHECKOUT)
    destination = CTX.rooted(ENTRYPOINT_DESTINATION)
    trusted_exists = os.path.lexists(trusted)
    destination_exists = os.path.lexists(destination)
    if not trusted_exists and not destination_exists:
        return "ABSENT"
    if trusted_exists != destination_exists:
        raise BootstrapStop("WeatherNext bootstrap targets show partial/conflicting prior state")
    info = trusted.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise BootstrapStop("WeatherNext trusted checkout is unsafe")
    if not CTX.test_mode and (info.st_uid != 0 or info.st_gid != 0):
        raise BootstrapStop("WeatherNext trusted checkout ownership drifted")
    head = _git_checkout(trusted, "rev-parse", "HEAD")
    branch = _git_checkout(trusted, "branch", "--show-current")
    dirty = _git_checkout(trusted, "status", "--porcelain=v1", "--untracked-files=all")
    if head != source_sha or branch or dirty:
        raise BootstrapStop("WeatherNext trusted checkout is not exact detached clean authorized source")
    source = trusted / ENTRYPOINT_SOURCE
    source_info = source.lstat()
    if not stat.S_ISREG(source_info.st_mode) or stat.S_ISLNK(source_info.st_mode) or source_info.st_nlink != 1:
        raise BootstrapStop("WeatherNext bootstrap entrypoint source is unsafe")
    reviewed_bytes = _manager_git(manager, "show", f"{source_sha}:{ENTRYPOINT_SOURCE}").encode("utf-8")
    if source.read_bytes() != reviewed_bytes:
        raise BootstrapStop("WeatherNext trusted checkout entrypoint differs from reviewed Git object")
    dest_info = destination.lstat()
    expected_uid = os.getuid() if CTX.test_mode else 0
    expected_gid = os.getgid() if CTX.test_mode else 0
    if (
        not stat.S_ISREG(dest_info.st_mode) or stat.S_ISLNK(dest_info.st_mode) or dest_info.st_nlink != 1
        or dest_info.st_uid != expected_uid or dest_info.st_gid != expected_gid
        or stat.S_IMODE(dest_info.st_mode) != ENTRYPOINT_MODE or destination.read_bytes() != reviewed_bytes
    ):
        raise BootstrapStop("installed WeatherNext bootstrap entrypoint conflicts with reviewed state")
    return "EXACT"


def _consumed_marker(request_id: str) -> pathlib.Path:
    return CTX.state_dir / f"{CONSUMED_PREFIX}{request_id}.json"


def _require_not_consumed(request_id: str) -> pathlib.Path:
    marker = _consumed_marker(request_id)
    if os.path.lexists(marker):
        raise BootstrapStop("WeatherNext bootstrap authorization was already consumed")
    return marker


def _consume_authorization(accepted: AcceptedAuthorization, source_sha: str) -> pathlib.Path:
    verify_dir(CTX.state_dir, root_owned=not CTX.test_mode)
    marker = _require_not_consumed(accepted.request_id)
    payload = {
        "schema": "rpi5.weathernext-private-installer-bootstrap-consume.v1",
        "authorization_repository_id": AUTHORIZATION_REPOSITORY_ID,
        "authorization_issue_id": accepted.issue_id,
        "authorization_issue_number": accepted.issue_number,
        "request_id": accepted.request_id,
        "canonical_payload_sha256": accepted.canonical_payload_sha256,
        "raw_body_sha256": accepted.raw_body_sha256,
        "source_sha": source_sha,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "consumed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(marker, flags, 0o600)
    try:
        os.write(fd, raw)
        os.fchmod(fd, 0o600)
        if not CTX.test_mode:
            os.fchown(fd, 0, 0)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(CTX.state_dir)
    return marker


def _fetch_source(manager: pathlib.Path, source_sha: str) -> None:
    _manager_git(manager, "fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main")
    if _manager_git(manager, "rev-parse", "refs/remotes/origin/main^{commit}") != source_sha:
        raise BootstrapStop("fetched origin/main differs from authorized source SHA")
    result = run(
        ["git", "-c", f"safe.directory={manager}", "-C", str(manager),
         "merge-base", "--is-ancestor", MINIMUM_REVIEWED_ANCESTOR, source_sha],
        check=False, timeout=60, as_user=True,
    )
    if result.returncode != 0:
        raise BootstrapStop("fetched authorized source failed reviewed ancestry check")


def _add_trusted_worktree(manager: pathlib.Path, source_sha: str) -> pathlib.Path:
    trusted = CTX.rooted(TRUSTED_CHECKOUT)
    if os.path.lexists(trusted):
        raise BootstrapStop("WeatherNext trusted checkout appeared before worktree creation")
    # This exact worktree-add runs as root only because the fixed destination parent
    # is root-owned 0700. It cannot select another path or source SHA.
    _git_checkout(manager, "worktree", "add", "--detach", str(trusted), source_sha)
    return trusted


def _reviewed_source_bytes(manager: pathlib.Path, trusted: pathlib.Path, source_sha: str) -> bytes:
    if (
        _git_checkout(trusted, "rev-parse", "HEAD") != source_sha
        or _git_checkout(trusted, "branch", "--show-current")
        or _git_checkout(trusted, "status", "--porcelain=v1", "--untracked-files=all")
    ):
        raise BootstrapStop("new trusted checkout is not exact detached clean authorized source")
    source = trusted / ENTRYPOINT_SOURCE
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
        raise BootstrapStop("new trusted checkout entrypoint source is unsafe")
    reviewed = _manager_git(manager, "show", f"{source_sha}:{ENTRYPOINT_SOURCE}").encode("utf-8")
    if source.read_bytes() != reviewed:
        raise BootstrapStop("new trusted checkout entrypoint differs from reviewed Git object")
    return reviewed


def _install_entrypoint(reviewed: bytes) -> pathlib.Path:
    destination = CTX.rooted(ENTRYPOINT_DESTINATION)
    safe_target_parent(destination)
    if os.path.lexists(destination):
        raise BootstrapStop("WeatherNext bootstrap entrypoint appeared before install")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(destination, flags, ENTRYPOINT_MODE)
    try:
        offset = 0
        while offset < len(reviewed):
            written = os.write(fd, reviewed[offset:])
            if written <= 0:
                raise BootstrapStop("WeatherNext bootstrap entrypoint write failed")
            offset += written
        os.fchmod(fd, ENTRYPOINT_MODE)
        if not CTX.test_mode:
            os.fchown(fd, 0, 0)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(destination.parent)
    info = destination.lstat()
    expected_uid = os.getuid() if CTX.test_mode else 0
    expected_gid = os.getgid() if CTX.test_mode else 0
    if (
        not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1
        or info.st_uid != expected_uid or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != ENTRYPOINT_MODE or destination.read_bytes() != reviewed
    ):
        raise BootstrapStop("installed WeatherNext bootstrap entrypoint verification failed")
    return destination


def _final_authority_revalidation(accepted: AcceptedAuthorization, queue: NormalizedQueue, manager: pathlib.Path, manager_before: tuple[str, str]) -> None:
    issue, server_time = _gh_api_json(f"repos/{AUTHORIZATION_REPOSITORY}/issues/{accepted.issue_number}")
    verify_authorization_unchanged(accepted, issue, server_time=server_time)
    queue_issue, _ = _gh_api_json(f"repos/{QUEUE_REPOSITORY}/issues/{queue.issue_number}")
    verify_queue_unchanged(queue, queue_issue)
    source_sha = str(accepted.payload["source_sha"])
    _require_source_current(source_sha)
    _require_manager_snapshot(manager, manager_before)
    if _remote_main_sha(manager) != source_sha:
        raise BootstrapStop("reviewed origin main changed before authorization consume")
    if _trusted_checkout_state(manager, source_sha) != "ABSENT":
        raise BootstrapStop("WeatherNext bootstrap prestate changed before authorization consume")
    safe_target_parent(CTX.rooted(ENTRYPOINT_DESTINATION))
    host_identity()
    _require_not_consumed(accepted.request_id)


def execute_weathernext_bootstrap(authorization_issue_number: int) -> dict[str, Any]:
    _positive_int(authorization_issue_number, "authorization_issue_number")
    require_root()
    stage = "preflight"
    with operation_lock():
        engine_source_preflight()
        host_identity()
        manager = _manager_checkout()
        manager_before = _manager_snapshot(manager)
        accepted = _read_authorization(authorization_issue_number)
        source_sha = str(accepted.payload["source_sha"])
        queue = _read_queue(int(accepted.payload["queue_issue"]))
        validate_queue_binding(accepted, queue)
        _require_source_current(source_sha)
        if _remote_main_sha(manager) != source_sha:
            raise BootstrapStop("reviewed origin main does not equal authorized current main")
        state = _trusted_checkout_state(manager, source_sha)
        if state == "EXACT":
            issue, server_time = _gh_api_json(f"repos/{AUTHORIZATION_REPOSITORY}/issues/{accepted.issue_number}")
            verify_authorization_unchanged(accepted, issue, server_time=server_time)
            queue_issue, _ = _gh_api_json(f"repos/{QUEUE_REPOSITORY}/issues/{queue.issue_number}")
            verify_queue_unchanged(queue, queue_issue)
            _require_source_current(source_sha)
            _require_manager_snapshot(manager, manager_before)
            if _remote_main_sha(manager) != source_sha:
                raise BootstrapStop("reviewed origin main changed during exact-state verification")
            return {
                "result": "ALREADY_EXACT_NOOP",
                "source_sha": source_sha,
                "authorization_consumed": False,
                "mutation_counts": {item["category"]: 0 for item in MUTATION_BUDGET},
            }

        _final_authority_revalidation(accepted, queue, manager, manager_before)
        stage = "authorization-consume"
        _consume_authorization(accepted, source_sha)
        try:
            stage = "checkout-fetch"
            _fetch_source(manager, source_sha)
            _require_manager_snapshot(manager, manager_before)
            stage = "worktree-add"
            trusted = _add_trusted_worktree(manager, source_sha)
            _require_manager_snapshot(manager, manager_before)
            reviewed = _reviewed_source_bytes(manager, trusted, source_sha)
            stage = "entrypoint-install"
            _install_entrypoint(reviewed)
            if _trusted_checkout_state(manager, source_sha) != "EXACT":
                raise BootstrapStop("WeatherNext bootstrap postcondition is not exact")
        except Exception as exc:
            try:
                append_log(f"WEATHERNEXT_BOOTSTRAP STOP consumed=1 stage={stage} retry=NO cleanup=NO rollback=NO")
            except Exception:
                pass
            raise BootstrapStop(
                f"WeatherNext bootstrap stopped after authorization consume at stage={stage}; retry/cleanup/rollback forbidden"
            ) from exc

        append_log(
            f"WEATHERNEXT_BOOTSTRAP PASS source={source_sha[:12]} operation={OPERATION_ID} "
            "fetch=1 worktree_add=1 entrypoint_install=1 rollback=NONE"
        )
        return {
            "result": "HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED",
            "source_sha": source_sha,
            "trusted_checkout": TRUSTED_CHECKOUT,
            "entrypoint_destination": ENTRYPOINT_DESTINATION,
            "authorization_consumed": True,
            "mutation_counts": {item["category"]: 1 for item in MUTATION_BUDGET},
            "rollback_policy": ROLLBACK_POLICY,
        }
