from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

ADAPTER_ID = "rozkalns-cv.exact-sha.v1"
OPERATION_ID = "rozkalns-cv.exact-sha-release.v1"
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns-cv"
TARGET_ALIAS = "rozkalns-cv-production"
ROLLBACK_POLICY = "BUILTIN_TRANSACTIONAL_V1"
MUTATION_BUDGET = (("rozkalns-cv.transactional-release", 1),)
HELPER_PATH = "/usr/local/sbin/rozkalns-cv-pull-deploy-main"
LIBRARY_PATH = "/usr/local/libexec/rozkalns-cv/rozkalns-cv-deploy-library"
EVIDENCE_ROOT_CONTRACT = "sudo-user-home-relative:.local/state/rozkalns-cv-pull-deploy/evidence"
HELPER_BLOB = "c787789e77c31576310bed28da0fbc893cfabb5f"
LIBRARY_BLOB = "ade60abbfea3cf56b1a56bbc1b2e0669b1a1b983"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = frozenset(
    {
        "database migrations",
        "shared ingress control",
        "control-plane activation",
        "secret/permission changes",
    }
)


class CvExactShaAdapter:
    """P5 source-only adapter contract for the proven CV transactional helper.

    This class intentionally contains no process-launch or privilege-escalation
    implementation. Its purpose is to prove the exact registry/helper/rollback/
    evidence interface while the production registry remains execution_disabled.
    A later mutation-capable implementation requires a separately reviewed source
    change and the later owner-authorized live gates.
    """

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("CV adapter operation identity mismatch")
        if prepared.source_repository != SOURCE_REPOSITORY:
            raise AdapterError("CV adapter source repository mismatch")
        if SHA_RE.fullmatch(prepared.source_sha) is None:
            raise AdapterError("CV adapter source SHA is invalid")
        if prepared.target_alias != TARGET_ALIAS:
            raise AdapterError("CV adapter target alias mismatch")
        if prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("CV helper requires BUILTIN_TRANSACTIONAL_V1")
        if prepared.mutation_budget != MUTATION_BUDGET:
            raise AdapterError("CV mutation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("CV required exclusions are missing")
        required_dependencies = {
            f"helper-blob:{HELPER_BLOB}",
            f"deploy-library-blob:{LIBRARY_BLOB}",
            "interface-audit:rozkalns-cv.v1",
        }
        if not required_dependencies.issubset(set(prepared.dependencies)):
            raise AdapterError("CV helper/interface identity dependency mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": ADAPTER_ID,
            "source_sha": prepared.source_sha,
            "helper_path": HELPER_PATH,
            "library_path": LIBRARY_PATH,
            "evidence_root_contract": EVIDENCE_ROOT_CONTRACT,
            "rollback_policy": ROLLBACK_POLICY,
            "mutation_enabled": False,
            "result": "P5_SOURCE_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "P5 CV adapter is mutation-disabled; later executable adapter source and live authorization are required"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "required_summary_fields": (
                "DEPLOY_RESULT",
                "TARGET_SHA",
                "FINAL_STATE_SHA",
                "MUTATION_STARTED",
                "TRANSACTION_COMMITTED",
                "ROLLBACK_PERFORMED",
                "SHARED_INGRESS_CONTROLLED",
                "DATABASE_MIGRATIONS_EXECUTED",
            ),
            "required_public_markers": (
                "PUBLIC_SITE=PASS",
                "PUBLIC_MODULE_MIME=PASS",
                "PUBLIC_CACHE_IMMUTABLE=PASS",
                "PUBLIC_NOSNIFF=PASS",
                "PUBLIC_CSP_NONCE=PASS",
            ),
            "mutation_enabled": False,
        }
