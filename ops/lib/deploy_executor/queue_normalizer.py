from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .registry import OperationRegistry, OperationSpec, RegistryError

QUEUE_REPOSITORY = "rozkalnsandris/ops-workflows"
TITLE_RE = re.compile(r"^\[DEPLOY-QUEUE\]\[(?P<state>[A-Z_]+)\]\s+.+$")
BULLET_RE = re.compile(r"^- \*\*(?P<key>[a-z0-9_]+):\*\*\s+(?P<value>.+)$")
LEADING_CODE_RE = re.compile(r"^`(?P<value>[^`]+)`")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

QUEUE_FIELDS = frozenset({
    "source_repository",
    "exact_git_sha_or_waiting_merge",
    "source_pr_or_issue_if_applicable",
    "target_alias",
    "execution_location_class",
    "repository_entrypoint",
    "expected_baseline_when_observable",
    "read_only_preflight",
    "verification_and_reconciliation",
    "allowed_mutation_categories_and_limits",
    "explicit_exclusions",
    "dependencies_if_any",
    "deploy_class_and_extra_owner_gate_requirement",
})


class QueueNormalizationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise QueueNormalizationError(code, message)


def _leading_code(fields: Mapping[str, str], key: str) -> str:
    match = LEADING_CODE_RE.match(fields[key])
    if match is None:
        _fail("QUEUE_SCHEMA", f"{key} must begin with exactly one backtick-delimited machine token")
    return match.group("value")


def _contract_fields(body: Any) -> dict[str, str]:
    if type(body) is not str:
        _fail("QUEUE_SCHEMA", "issue body must be a string")
    lines = body.splitlines()
    if lines.count("## Queue contract") != 1:
        _fail("QUEUE_SCHEMA", "exactly one '## Queue contract' section is required")
    start = lines.index("## Queue contract") + 1
    section: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            section.append(line)
    fields: dict[str, str] = {}
    for line in section:
        match = BULLET_RE.fullmatch(line)
        if match is None:
            _fail("QUEUE_SCHEMA", f"queue contract contains unsupported line: {line[:80]!r}")
        key = match.group("key")
        if key in fields:
            _fail("QUEUE_SCHEMA", f"duplicate queue contract field {key!r}")
        fields[key] = match.group("value")
    actual = frozenset(fields)
    if actual != QUEUE_FIELDS:
        _fail(
            "QUEUE_SCHEMA",
            f"queue fields mismatch; missing={sorted(QUEUE_FIELDS-actual)}, extra={sorted(actual-QUEUE_FIELDS)}",
        )
    return fields


def canonical_queue_contract_sha256(fields: Mapping[str, str]) -> str:
    raw = json.dumps(dict(fields), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ParsedQueue:
    issue_number: int
    source_repository: str
    source_sha: str
    raw_target_alias: str
    execution_location_class: str
    repository_entrypoint: str
    deploy_class: str
    contract_sha256: str
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NormalizedQueue:
    parsed: ParsedQueue
    operation: OperationSpec
    execution_enabled: bool
    canonical_json: str

    def as_protocol_queue(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def parse_ready_queue(issue: Mapping[str, Any], *, repository_full_name: str) -> ParsedQueue:
    if repository_full_name != QUEUE_REPOSITORY:
        _fail("WRONG_QUEUE_REPOSITORY", repository_full_name)
    if type(issue) is not dict:
        _fail("QUEUE_SCHEMA", "issue must be an object")
    if issue.get("state") != "open":
        _fail("QUEUE_NOT_OPEN", "queue issue must be open")
    if "pull_request" in issue and issue["pull_request"] is not None:
        _fail("QUEUE_SCHEMA", "deploy queue must be an Issue, not a pull request")
    number = issue.get("number", issue.get("issue_number"))
    if type(number) is not int or number < 1:
        _fail("QUEUE_SCHEMA", "issue number must be a positive integer")
    title = issue.get("title")
    if type(title) is not str:
        _fail("QUEUE_SCHEMA", "title must be a string")
    title_match = TITLE_RE.fullmatch(title)
    if title_match is None:
        _fail("QUEUE_SCHEMA", "title must match [DEPLOY-QUEUE][STATE] description")
    if title_match.group("state") != "READY":
        _fail("QUEUE_NOT_READY", "only READY queue issues may be normalized for deferred pull")

    fields = _contract_fields(issue.get("body"))
    source_repository = _leading_code(fields, "source_repository")
    source_sha = _leading_code(fields, "exact_git_sha_or_waiting_merge")
    if SHA_RE.fullmatch(source_sha) is None:
        _fail("QUEUE_SHA", "READY queue must bind one exact lowercase 40-character SHA")

    raw_target_alias = _leading_code(fields, "target_alias")
    execution_location_class = _leading_code(fields, "execution_location_class")
    repository_entrypoint = _leading_code(fields, "repository_entrypoint")
    deploy_class = _leading_code(fields, "deploy_class_and_extra_owner_gate_requirement")

    return ParsedQueue(
        issue_number=number,
        source_repository=source_repository,
        source_sha=source_sha,
        raw_target_alias=raw_target_alias,
        execution_location_class=execution_location_class,
        repository_entrypoint=repository_entrypoint,
        deploy_class=deploy_class,
        contract_sha256=canonical_queue_contract_sha256(fields),
        fields=tuple(sorted(fields.items())),
    )


def normalize_ready_queue(
    issue: Mapping[str, Any], *, repository_full_name: str, registry: OperationRegistry
) -> NormalizedQueue:
    parsed = parse_ready_queue(issue, repository_full_name=repository_full_name)
    try:
        operation = registry.exact_match(
            source_repository=parsed.source_repository,
            target_alias=parsed.raw_target_alias,
            execution_location_class=parsed.execution_location_class,
            repository_entrypoint=parsed.repository_entrypoint,
            deploy_class=parsed.deploy_class,
        )
    except RegistryError as exc:
        _fail(exc.code, exc.message)

    dependencies = list(operation.dependencies)
    dependencies.append(f"queue-contract-sha256:{parsed.contract_sha256}")
    protocol_queue = {
        "repository": QUEUE_REPOSITORY,
        "issue_number": parsed.issue_number,
        "state": "READY",
        "source_repository": parsed.source_repository,
        "source_sha": parsed.source_sha,
        "target_alias": operation.target_alias,
        "operation_id": operation.operation_id,
        "expected_baseline": {"kind": operation.baseline.kind, "value": operation.baseline.resolver_id},
        "mutation_budget": [
            {"category": item.category, "max_operations": item.max_operations}
            for item in operation.mutation_budget
        ],
        "rollback_policy": operation.rollback_policy,
        "exclusions": list(operation.exclusions),
        "dependencies": dependencies,
    }
    canonical = json.dumps(protocol_queue, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return NormalizedQueue(
        parsed=parsed,
        operation=operation,
        execution_enabled=registry.execution_enabled,
        canonical_json=canonical,
    )
