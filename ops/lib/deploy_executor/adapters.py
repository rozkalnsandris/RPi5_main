from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from .queue_normalizer import NormalizedQueue
from .registry import OperationSpec


class AdapterError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedOperation:
    operation_id: str
    adapter_id: str
    execution_enabled: bool
    source_repository: str
    source_sha: str
    target_alias: str
    rollback_policy: str
    mutation_budget: tuple[tuple[str, int], ...]
    exclusions: tuple[str, ...]
    dependencies: tuple[str, ...]
    normalized_queue_json: str
    preflight_checks: tuple[str, ...]
    postcondition_checks: tuple[str, ...]
    required_github_evidence: tuple[str, ...]
    expected_baseline_kind: str = "resolver"
    expected_baseline_value: str = ""


@runtime_checkable
class OperationAdapter(Protocol):
    """Fixed project adapter interface.

    Source preparation may register dormant capability-specific adapters for
    interface proof while the production registry remains mutation-disabled.
    A concrete adapter must independently reject unsupported baseline,
    rollback, mutation, path and authority envelopes.
    """

    adapter_id: str

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]: ...

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]: ...

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]: ...


class AdapterCatalog:
    def __init__(self, adapters: tuple[OperationAdapter, ...] = ()):
        values: dict[str, OperationAdapter] = {}
        for adapter in adapters:
            adapter_id = getattr(adapter, "adapter_id", None)
            if type(adapter_id) is not str or not adapter_id:
                raise AdapterError("adapter_id must be a non-empty string")
            if adapter_id in values:
                raise AdapterError(f"duplicate adapter_id: {adapter_id}")
            values[adapter_id] = adapter
        self._values = values

    def require(self, adapter_id: str) -> OperationAdapter:
        try:
            return self._values[adapter_id]
        except KeyError as exc:
            raise AdapterError(f"unknown adapter_id: {adapter_id}") from exc


def prepare_operation(normalized: NormalizedQueue) -> PreparedOperation:
    spec: OperationSpec = normalized.operation
    queue = normalized.as_protocol_queue()
    expected_baseline = queue["expected_baseline"]
    return PreparedOperation(
        operation_id=spec.operation_id,
        adapter_id=spec.adapter_id,
        execution_enabled=normalized.execution_enabled,
        source_repository=queue["source_repository"],
        source_sha=queue["source_sha"],
        target_alias=queue["target_alias"],
        rollback_policy=spec.rollback_policy,
        mutation_budget=tuple(
            (budget.category, budget.max_operations) for budget in spec.mutation_budget
        ),
        exclusions=spec.exclusions,
        dependencies=tuple(queue["dependencies"]),
        normalized_queue_json=normalized.canonical_json,
        preflight_checks=spec.preflight,
        postcondition_checks=spec.postconditions,
        required_github_evidence=spec.required_github_evidence,
        expected_baseline_kind=expected_baseline["kind"],
        expected_baseline_value=expected_baseline["value"],
    )
