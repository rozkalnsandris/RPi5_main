from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

ADAPTER_ID = "hermes-deals.origin-path-audit.v1"
OPERATION_ID = "hermes-deals.origin-path-audit.v1"
SOURCE_REPOSITORY = "rozkalnsandris/hermes-deals"
SOURCE_REPOSITORY_ID = 1317143994
REVIEWED_SOURCE_SHA = "2f47f64ab15e767f4e53ad182326e64e313d5094"
TARGET_ALIAS = "hermes-deals-origin-path-audit"
ROLLBACK_POLICY = "NONE"
INVOCATION_BUDGET = (("hermes-deals.read-only-audit-invocation", 1),)

# Legacy self-hosted path identities are retained as compatibility evidence only.
# #358 does not activate, modify, or retire that path.
WORKFLOW_SOURCE_BLOB = "99a18c5f669e7880a8a8288c3f964285df87ae22"
DISPATCHER_SOURCE_BLOB = "f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc"
INSTALLER_SOURCE_BLOB = "41f004420a0f5aed314aaefd796a54e14dbd17ea"
PROBE_SOURCE_BLOB = "2362e8eb578a7279c38fe4ed2a7d1edd05df891a"

# Runner-independent helper contract merged by hermes-deals#834 / PR #840.
PULL_HELPER_SOURCE_PATH = "tools/runner/origin_path_rpi5_pull_helper.py"
PULL_HELPER_SOURCE_BLOB = "51bb23cc6c2083ab7c8b4e81ba82dd880e46d673"
PULL_HELPER_CONTRACT_PATH = "docs/operations/origin-path-rpi5-pull-helper.md"
PULL_HELPER_CONTRACT_BLOB = "7407737a6ded00ba53687de79983ef8395881adb"
PULL_HELPER_CAPABILITY = "origin-path-audit"
PULL_HELPER_ARGUMENTS = ("registered_sha", "as_of")
PULL_HELPER_INSTALLED_PATH = "/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch"
PULL_HELPER_REGISTRATION_SCHEMA = (
    "rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1"
)
PULL_HELPER_REGISTRATION_PATH = (
    "/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json"
)
PULL_HELPER_EVIDENCE_ROOT = (
    "/var/lib/hermes-deals-audits/origin-path-audit/evidence/rpi5"
)
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
        f"reviewed-source-sha:{REVIEWED_SOURCE_SHA}",
        "migration-contract:hermes-deals#787",
        "runner-independent-helper-contract:hermes-deals#834",
        f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}",
        f"dispatcher-source-blob:{DISPATCHER_SOURCE_BLOB}",
        f"installer-source-blob:{INSTALLER_SOURCE_BLOB}",
        f"probe-source-blob:{PROBE_SOURCE_BLOB}",
        f"pull-helper-source-blob:{PULL_HELPER_SOURCE_BLOB}",
        f"pull-helper-contract-blob:{PULL_HELPER_CONTRACT_BLOB}",
        "pull-helper-interface:registered-sha-as-of-v1",
        "pull-helper-evidence-authority:source-fixed-rpi5-v1",
        "privileged-boundary:identity-only-dispatch-request-v1",
    }
)


class HermesDealsOriginAuditAdapter:
    """Inert source contract for the Hermes Deals runner-independent audit path.

    The adapter binds the exact reviewed Hermes source and the capability-specific
    two-argument pull-helper interface. It does not launch the helper, cross the
    privileged boundary, install host state, retain evidence, or replace/retire
    the legacy self-hosted audit path. Those remain later explicit live gates.
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
        if prepared.source_sha != REVIEWED_SOURCE_SHA:
            raise AdapterError("Hermes Deals origin source SHA is not the reviewed helper source")
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
            "reviewed_source_sha": REVIEWED_SOURCE_SHA,
            "workflow_source_blob": WORKFLOW_SOURCE_BLOB,
            "dispatcher_source_blob": DISPATCHER_SOURCE_BLOB,
            "installer_source_blob": INSTALLER_SOURCE_BLOB,
            "probe_source_blob": PROBE_SOURCE_BLOB,
            "pull_helper_source_path": PULL_HELPER_SOURCE_PATH,
            "pull_helper_source_blob": PULL_HELPER_SOURCE_BLOB,
            "pull_helper_contract_path": PULL_HELPER_CONTRACT_PATH,
            "pull_helper_contract_blob": PULL_HELPER_CONTRACT_BLOB,
            "pull_helper_capability": PULL_HELPER_CAPABILITY,
            "pull_helper_arguments": PULL_HELPER_ARGUMENTS,
            "pull_helper_installed_path": PULL_HELPER_INSTALLED_PATH,
            "pull_helper_registration_schema": PULL_HELPER_REGISTRATION_SCHEMA,
            "pull_helper_registration_path": PULL_HELPER_REGISTRATION_PATH,
            "pull_helper_evidence_root": PULL_HELPER_EVIDENCE_ROOT,
            "read_only": True,
            "execution_enabled": False,
            "pull_helper_execution_enabled": False,
            "privileged_dispatch_ready": False,
            "result": "SOURCE_PULL_HELPER_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Hermes Deals origin pull helper is execution-disabled; live authorization and a separately proven privileged dispatch boundary are required"
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
            "pull_helper_execution_enabled": False,
        }
