from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

ADAPTER_ID = "hermes-deals.origin-path-audit.v1"
OPERATION_ID = "hermes-deals.origin-path-audit.v1"
SOURCE_REPOSITORY = "rozkalnsandris/hermes-deals"
SOURCE_REPOSITORY_ID = 1317143994
TARGET_ALIAS = "hermes-deals-origin-path-audit"
ROLLBACK_POLICY = "NONE"
INVOCATION_BUDGET = (("hermes-deals.read-only-audit-invocation", 1),)
WORKFLOW_SOURCE_BLOB = "99a18c5f669e7880a8a8288c3f964285df87ae22"
DISPATCHER_SOURCE_BLOB = "f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc"
INSTALLER_SOURCE_BLOB = "41f004420a0f5aed314aaefd796a54e14dbd17ea"
PROBE_SOURCE_BLOB = "2362e8eb578a7279c38fe4ed2a7d1edd05df891a"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = frozenset(
    {
        "production database writes",
        "production deployment/cutover",
        "restart/configuration mutation",
        "parser/collector behavior changes",
        "runner registration/deregistration",
        "GitHub App/credential/permission changes",
    }
)

REQUIRED_DEPENDENCIES = frozenset(
    {
        f"source-repository-id:{SOURCE_REPOSITORY_ID}",
        "migration-contract:hermes-deals#787",
        f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}",
        f"dispatcher-source-blob:{DISPATCHER_SOURCE_BLOB}",
        f"installer-source-blob:{INSTALLER_SOURCE_BLOB}",
        f"probe-source-blob:{PROBE_SOURCE_BLOB}",
        "privileged-boundary:identity-only-dispatch-request-v1",
    }
)


class HermesDealsOriginAuditAdapter:
    """Source-only contract for the first Hermes Deals pull-control canary.

    The adapter validates one reviewed read-only operation envelope. It does not
    launch commands, cross the privileged boundary, install host state, or replace
    the existing self-hosted audit path. Activation remains a later explicit live
    gate after the authorization and privileged-broker boundaries are proven.
    """

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("Hermes Deals origin adapter operation identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("Hermes Deals origin canary must remain execution-disabled")
        if prepared.source_repository != SOURCE_REPOSITORY:
            raise AdapterError("Hermes Deals origin source repository mismatch")
        if SHA_RE.fullmatch(prepared.source_sha) is None:
            raise AdapterError("Hermes Deals origin source SHA is invalid")
        if prepared.target_alias != TARGET_ALIAS:
            raise AdapterError("Hermes Deals origin target alias mismatch")
        if prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("read-only origin audit requires rollback policy NONE")
        if prepared.mutation_budget != INVOCATION_BUDGET:
            raise AdapterError("Hermes Deals origin invocation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("Hermes Deals origin required exclusions are missing")
        if not REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("Hermes Deals origin source/interface dependency mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": ADAPTER_ID,
            "source_sha": prepared.source_sha,
            "source_repository_id": SOURCE_REPOSITORY_ID,
            "workflow_source_blob": WORKFLOW_SOURCE_BLOB,
            "dispatcher_source_blob": DISPATCHER_SOURCE_BLOB,
            "installer_source_blob": INSTALLER_SOURCE_BLOB,
            "probe_source_blob": PROBE_SOURCE_BLOB,
            "read_only": True,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "result": "SOURCE_CANARY_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Hermes Deals origin canary is execution-disabled; live authorization and a separately proven privileged dispatch boundary are required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "required_manifest_fields": (
                "commit_sha",
                "as_of",
                "probe_exit_code",
                "sanitization_passed",
                "production_apply_authorized",
                "production_database_write",
                "production_deployment",
                "restart_or_configuration_mutation",
            ),
            "required_false_flags": (
                "production_apply_authorized",
                "production_database_write",
                "production_deployment",
                "restart_or_configuration_mutation",
            ),
            "read_only": True,
            "execution_enabled": False,
        }
