from __future__ import annotations

from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation
from . import dashboard_bootstrap_contract as c


class DashboardHardenedControllerBootstrapAdapter:
    """Dormant source contract; it never dispatches the root bootstrap helper."""

    adapter_id = c.ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != c.OPERATION_ID or prepared.adapter_id != c.ADAPTER_ID:
            raise AdapterError("Dashboard bootstrap operation identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("Dashboard bootstrap source adapter must remain execution-disabled")
        if prepared.source_repository != c.SOURCE_REPOSITORY or prepared.source_sha != c.SOURCE_SHA:
            raise AdapterError("Dashboard bootstrap source identity mismatch")
        if prepared.target_alias != c.TARGET_ALIAS or prepared.rollback_policy != c.ROLLBACK_POLICY:
            raise AdapterError("Dashboard bootstrap target/rollback mismatch")
        if prepared.mutation_budget != c.MUTATION_BUDGET:
            raise AdapterError("Dashboard bootstrap mutation budget mismatch")
        if not c.REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("Dashboard bootstrap required exclusions are missing")
        if not c.REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("Dashboard bootstrap dependency binding mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": c.ADAPTER_ID,
            "source_sha": c.SOURCE_SHA,
            "target_alias": c.TARGET_ALIAS,
            "historical_controller_blob": c.HISTORICAL_CONTROLLER_BLOB,
            "hardened_controller_blob": c.HARDENED_CONTROLLER_BLOB,
            "candidate_root": str(c.CANDIDATE_ROOT),
            "manifest_path": str(c.MANIFEST_PATH),
            "installed_entrypoint": str(c.INSTALLED_ENTRYPOINT),
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "live_authorized": False,
            "result": "SOURCE_BOOTSTRAP_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Dashboard bootstrap adapter is source-only and execution-disabled; a separate LIVE/root gate is required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "execution_enabled": False,
            "required_current_controller_blob": c.HARDENED_CONTROLLER_BLOB,
            "required_current_source_sha": c.SOURCE_SHA,
            "releases_deleted": 0,
            "p10_apply_executed": False,
        }
