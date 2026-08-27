from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
ROLLBACK_POLICIES = frozenset({"NONE", "BUILTIN_TRANSACTIONAL_V1"})
AUTHORIZATION_CLASSES = frozenset({"ORDINARY", "STRICT"})

ROOT_KEYS = frozenset({"schema_version", "execution_enabled", "operations"})
OPERATION_KEYS = frozenset({
    "operation_id", "source_repository", "queue_match", "target_alias", "adapter_id",
    "authorization_class", "ordinary_live_all_eligible", "baseline", "mutation_budget",
    "rollback_policy", "exclusions", "dependencies", "preflight", "postconditions",
    "required_github_evidence",
})
QUEUE_MATCH_KEYS = frozenset({
    "target_alias", "execution_location_class", "repository_entrypoint", "deploy_class"
})
BASELINE_KEYS = frozenset({"kind", "resolver_id"})
BUDGET_KEYS = frozenset({"category", "max_operations"})


class RegistryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise RegistryError(code, message)


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        _fail(
            "REGISTRY_SCHEMA",
            f"{where} keys mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}",
        )


def _string(value: Any, where: str, *, max_len: int = 256, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        _fail("REGISTRY_SCHEMA", f"{where} must be a non-empty string <= {max_len} chars")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail("REGISTRY_SCHEMA", f"{where} has invalid format")
    return value


def _string_list(value: Any, where: str, *, max_items: int = 32) -> tuple[str, ...]:
    if type(value) is not list or len(value) > max_items:
        _fail("REGISTRY_SCHEMA", f"{where} must be a list with <= {max_items} entries")
    out: list[str] = []
    for index, item in enumerate(value):
        out.append(_string(item, f"{where}[{index}]"))
    return tuple(out)


@dataclass(frozen=True)
class MutationBudget:
    category: str
    max_operations: int


@dataclass(frozen=True)
class BaselineContract:
    kind: str
    resolver_id: str


@dataclass(frozen=True)
class QueueMatch:
    target_alias: str
    execution_location_class: str
    repository_entrypoint: str
    deploy_class: str


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    source_repository: str
    queue_match: QueueMatch
    target_alias: str
    adapter_id: str
    authorization_class: str
    ordinary_live_all_eligible: bool
    baseline: BaselineContract
    mutation_budget: tuple[MutationBudget, ...]
    rollback_policy: str
    exclusions: tuple[str, ...]
    dependencies: tuple[str, ...]
    preflight: tuple[str, ...]
    postconditions: tuple[str, ...]
    required_github_evidence: tuple[str, ...]


@dataclass(frozen=True)
class OperationRegistry:
    schema_version: int
    execution_enabled: bool
    operations: tuple[OperationSpec, ...]

    def exact_match(
        self,
        *,
        source_repository: str,
        target_alias: str,
        execution_location_class: str,
        repository_entrypoint: str,
        deploy_class: str,
    ) -> OperationSpec:
        matches = [
            op for op in self.operations
            if op.source_repository == source_repository
            and op.queue_match.target_alias == target_alias
            and op.queue_match.execution_location_class == execution_location_class
            and op.queue_match.repository_entrypoint == repository_entrypoint
            and op.queue_match.deploy_class == deploy_class
        ]
        if not matches:
            _fail("UNKNOWN_OPERATION", "queue selectors do not match a reviewed static operation")
        if len(matches) != 1:
            _fail("AMBIGUOUS_OPERATION", "queue selectors match more than one static operation")
        return matches[0]


def _parse_operation(value: Any, index: int) -> OperationSpec:
    where = f"operations[{index}]"
    if type(value) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where} must be an object")
    _exact_keys(value, OPERATION_KEYS, where)

    operation_id = _string(value["operation_id"], f"{where}.operation_id", pattern=IDENTIFIER_RE)
    source_repository = _string(value["source_repository"], f"{where}.source_repository", max_len=201, pattern=REPOSITORY_RE)
    target_alias = _string(value["target_alias"], f"{where}.target_alias", max_len=64, pattern=IDENTIFIER_RE)
    adapter_id = _string(value["adapter_id"], f"{where}.adapter_id", pattern=IDENTIFIER_RE)

    match = value["queue_match"]
    if type(match) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where}.queue_match must be an object")
    _exact_keys(match, QUEUE_MATCH_KEYS, f"{where}.queue_match")
    queue_match = QueueMatch(
        target_alias=_string(match["target_alias"], f"{where}.queue_match.target_alias"),
        execution_location_class=_string(
            match["execution_location_class"], f"{where}.queue_match.execution_location_class",
            max_len=64, pattern=IDENTIFIER_RE,
        ),
        repository_entrypoint=_string(match["repository_entrypoint"], f"{where}.queue_match.repository_entrypoint"),
        deploy_class=_string(match["deploy_class"], f"{where}.queue_match.deploy_class", max_len=64),
    )

    authorization_class = _string(value["authorization_class"], f"{where}.authorization_class", max_len=32)
    if authorization_class not in AUTHORIZATION_CLASSES:
        _fail("REGISTRY_SCHEMA", f"unsupported authorization_class {authorization_class!r}")
    ordinary = value["ordinary_live_all_eligible"]
    if type(ordinary) is not bool:
        _fail("REGISTRY_SCHEMA", f"{where}.ordinary_live_all_eligible must be boolean")
    if ordinary != (authorization_class == "ORDINARY"):
        _fail("REGISTRY_POLICY", "ordinary_live_all_eligible must exactly match ORDINARY authorization class")

    baseline = value["baseline"]
    if type(baseline) is not dict:
        _fail("REGISTRY_SCHEMA", f"{where}.baseline must be an object")
    _exact_keys(baseline, BASELINE_KEYS, f"{where}.baseline")
    if baseline["kind"] != "resolver":
        _fail("REGISTRY_POLICY", "P4 baseline contracts must use a declared read-only resolver")
    baseline_contract = BaselineContract(
        kind="resolver",
        resolver_id=_string(baseline["resolver_id"], f"{where}.baseline.resolver_id", pattern=IDENTIFIER_RE),
    )

    raw_budget = value["mutation_budget"]
    if type(raw_budget) is not list or not raw_budget or len(raw_budget) > 16:
        _fail("REGISTRY_SCHEMA", f"{where}.mutation_budget must contain 1..16 entries")
    budgets: list[MutationBudget] = []
    seen_categories: set[str] = set()
    for budget_index, budget in enumerate(raw_budget):
        budget_where = f"{where}.mutation_budget[{budget_index}]"
        if type(budget) is not dict:
            _fail("REGISTRY_SCHEMA", f"{budget_where} must be an object")
        _exact_keys(budget, BUDGET_KEYS, budget_where)
        category = _string(budget["category"], f"{budget_where}.category", pattern=IDENTIFIER_RE)
        count = budget["max_operations"]
        if type(count) is not int or not 1 <= count <= 100:
            _fail("REGISTRY_SCHEMA", f"{budget_where}.max_operations must be 1..100")
        if category in seen_categories:
            _fail("REGISTRY_SCHEMA", f"duplicate mutation category {category!r}")
        seen_categories.add(category)
        budgets.append(MutationBudget(category, count))

    rollback = _string(value["rollback_policy"], f"{where}.rollback_policy", max_len=64)
    if rollback not in ROLLBACK_POLICIES:
        _fail("REGISTRY_POLICY", f"unsupported rollback policy {rollback!r}")

    return OperationSpec(
        operation_id=operation_id,
        source_repository=source_repository,
        queue_match=queue_match,
        target_alias=target_alias,
        adapter_id=adapter_id,
        authorization_class=authorization_class,
        ordinary_live_all_eligible=ordinary,
        baseline=baseline_contract,
        mutation_budget=tuple(budgets),
        rollback_policy=rollback,
        exclusions=_string_list(value["exclusions"], f"{where}.exclusions"),
        dependencies=_string_list(value["dependencies"], f"{where}.dependencies"),
        preflight=_string_list(value["preflight"], f"{where}.preflight"),
        postconditions=_string_list(value["postconditions"], f"{where}.postconditions"),
        required_github_evidence=_string_list(
            value["required_github_evidence"], f"{where}.required_github_evidence"
        ),
    )


def load_registry(path: str | Path) -> OperationRegistry:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("REGISTRY_READ", str(exc))
    if type(raw) is not dict:
        _fail("REGISTRY_SCHEMA", "registry root must be an object")
    _exact_keys(raw, ROOT_KEYS, "registry")
    if raw["schema_version"] != 1:
        _fail("REGISTRY_SCHEMA", "schema_version must be 1")
    if raw["execution_enabled"] is not False:
        _fail("P4_EXECUTION_FORBIDDEN", "P4 registry must keep execution_enabled=false")
    if type(raw["operations"]) is not list:
        _fail("REGISTRY_SCHEMA", "operations must be a list")
    operations = tuple(_parse_operation(item, index) for index, item in enumerate(raw["operations"]))
    ids = [op.operation_id for op in operations]
    if len(ids) != len(set(ids)):
        _fail("REGISTRY_SCHEMA", "duplicate operation_id")
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=operations)
