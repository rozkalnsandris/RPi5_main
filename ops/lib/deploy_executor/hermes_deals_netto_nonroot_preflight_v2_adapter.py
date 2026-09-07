from __future__ import annotations

from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

OPERATION_ID = "hermes-deals.netto-missing-normal-price-nonroot-preflight-v2.v1"
ADAPTER_ID = OPERATION_ID
SOURCE_REPOSITORY = "rozkalnsandris/hermes-deals"
SOURCE_REPOSITORY_ID = 1317143994
SOURCE_SHA = "067db7bd4b8057bc16a9bf0ef9ed8487127a0a05"
TARGET_ALIAS = "hermes-deals-netto-nonroot-preflight-v2"
BASELINE_RESOLVER_ID = "hermes-deals.netto-nonroot-preflight-v2-registration.v1"
ROLLBACK_POLICY = "NONE"
HELPER_SOURCE_PATH = "tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py"
HELPER_SOURCE_BLOB = "0f8b01ed3129323cc59e526262b369cf33346aba"
HELPER_CAPABILITY = "netto-missing-normal-price-nonroot-preflight-v2"
HELPER_REGISTRATION_SCHEMA = (
    "rozkalns.hermes-deals.netto-nonroot-preflight-v2-registration.v1"
)
HELPER_EVIDENCE_SCHEMA = "rozkalns.hermes-deals.netto-nonroot-preflight-v2-evidence.v1"
HELPER_ARGUMENTS = ("registered_source_sha",)
N9_MANIFEST_SHA256 = "2b180d67af4c5d1e586704088e3d685cff21ae2e12f3052254daf4553dd4e147"
MUTATION_BUDGET = (("hermes-deals.read-only-netto-nonroot-preflight-v2-invocation", 1),)

REQUIRED_EXCLUSIONS = frozenset(
    {
        "arbitrary command/path/argv/environment authority",
        "root/sudo authority",
        "Docker authority",
        "parser execution",
        "production database writes",
        "Review/publication writes",
        "production deployment/cutover",
        "systemd/service/host mutation",
        "runner registration/deregistration",
        "GitHub App/credential/permission changes",
        "automatic retry/cleanup/rollback",
    }
)

REQUIRED_DEPENDENCIES = frozenset(
    {
        f"source-repository-id:{SOURCE_REPOSITORY_ID}",
        "source-contract:RPi5_main#407",
        "source-helper-issue:hermes-deals#858",
        "source-helper-pr:hermes-deals#859",
        f"source-sha:{SOURCE_SHA}",
        f"pull-helper-source-path:{HELPER_SOURCE_PATH}",
        f"pull-helper-source-blob:{HELPER_SOURCE_BLOB}",
        f"pull-helper-capability:{HELPER_CAPABILITY}",
        f"pull-helper-registration-schema:{HELPER_REGISTRATION_SCHEMA}",
        f"pull-helper-evidence-schema:{HELPER_EVIDENCE_SCHEMA}",
        "pull-helper-arguments:registered_source_sha",
        f"n9-manifest-sha256:{N9_MANIFEST_SHA256}",
        "execution-boundary:nonroot-no-docker",
    }
)


class HermesDealsNettoNonrootPreflightV2Adapter:
    """Static source contract for the runner-independent Netto v2 preflight.

    The adapter binds one reviewed Hermes helper and exact merged source SHA. It
    has no execution bridge and remains inert until separately reviewed host
    wiring and LIVE authorization exist.
    """

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("Netto v2 operation identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("Netto v2 operation must remain execution-disabled")
        if prepared.source_repository != SOURCE_REPOSITORY:
            raise AdapterError("Netto v2 source repository mismatch")
        if prepared.source_sha != SOURCE_SHA:
            raise AdapterError("Netto v2 source SHA mismatch")
        if prepared.target_alias != TARGET_ALIAS:
            raise AdapterError("Netto v2 target alias mismatch")
        if prepared.expected_baseline_kind != "resolver":
            raise AdapterError("Netto v2 baseline kind mismatch")
        if prepared.expected_baseline_value != BASELINE_RESOLVER_ID:
            raise AdapterError("Netto v2 baseline resolver mismatch")
        if prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("Netto v2 rollback policy must remain NONE")
        if prepared.mutation_budget != MUTATION_BUDGET:
            raise AdapterError("Netto v2 invocation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("Netto v2 required exclusions are missing")
        if not REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("Netto v2 source/interface dependency mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": ADAPTER_ID,
            "source_repository_id": SOURCE_REPOSITORY_ID,
            "source_sha": SOURCE_SHA,
            "helper_source_path": HELPER_SOURCE_PATH,
            "helper_source_blob": HELPER_SOURCE_BLOB,
            "helper_capability": HELPER_CAPABILITY,
            "helper_registration_schema": HELPER_REGISTRATION_SCHEMA,
            "helper_evidence_schema": HELPER_EVIDENCE_SCHEMA,
            "helper_arguments": HELPER_ARGUMENTS,
            "n9_manifest_sha256": N9_MANIFEST_SHA256,
            "read_only": True,
            "non_root_required": True,
            "docker_authority_allowed": False,
            "parser_execution_allowed": False,
            "database_write_allowed": False,
            "review_write_allowed": False,
            "deployment_allowed": False,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "requires_separate_live_authorization": True,
            "result": "HERMES_NETTO_NONROOT_PREFLIGHT_V2_SOURCE_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Netto v2 operation is execution-disabled; separately reviewed host wiring and LIVE authorization are required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "registered_source_sha": SOURCE_SHA,
            "sudo_used": False,
            "file_contents_exported": False,
            "parser_executed": False,
            "database_write_performed": False,
            "review_write_performed": False,
            "deployment_performed": False,
            "runner_registration_changed": False,
            "automatic_retry_cleanup_rollback": False,
            "execution_enabled": False,
        }
