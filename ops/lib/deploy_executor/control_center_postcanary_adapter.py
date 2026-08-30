from __future__ import annotations

import re
from typing import Any, Mapping

from .adapters import AdapterError, PreparedOperation

ADAPTER_ID = "rozkalns-control-center.merge-postcanary-reconcile.v1"
OPERATION_ID = ADAPTER_ID
SOURCE_REPOSITORY = "rozkalnsandris/rozkalns-control-center"
SOURCE_REPOSITORY_ID = 1329279953
TARGET_ALIAS = "control-center-merge-postcanary-reconcile"
ROLLBACK_POLICY = "NONE"
INVOCATION_BUDGET = (("control-center.read-only-reconciliation-run", 1),)
WORKFLOW_PATH = ".github/workflows/phase3-merge-postcanary-readonly-reconcile.yml"
WORKFLOW_SOURCE_BLOB = "907447666e510340b241348cd1c6ed3260f8b0ab"
TARGET_REPOSITORY_ID = 1328835922
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = frozenset(
    {
        "GitHub merge/decision mutation",
        "D1 write/migration/apply",
        "Worker deploy",
        "Cloudflare configuration mutation",
        "GitHub App/credential/permission changes",
        "host/runtime mutation",
    }
)

REQUIRED_DEPENDENCIES = frozenset(
    {
        f"source-repository-id:{SOURCE_REPOSITORY_ID}",
        f"workflow-source-blob:{WORKFLOW_SOURCE_BLOB}",
        f"target-repository-id:{TARGET_REPOSITORY_ID}",
        "workflow-trigger:owner-issue-comment-278-v1",
        "d1-access:select-only-zero-write-v1",
        "p9-trigger-dispatch:prohibited",
    }
)


class ControlCenterPostCanaryAdapter:
    """Dormant source contract for the Control Center read-only reconciliation.

    P9 may validate this reviewed envelope and emit DRY_RUN_READY only. The adapter
    cannot post the owner trigger comment, dispatch a workflow, write D1, deploy a
    Worker, change Cloudflare configuration, or mutate a host/runtime boundary.
    """

    adapter_id = ADAPTER_ID

    def _validate(self, prepared: PreparedOperation) -> None:
        if prepared.operation_id != OPERATION_ID or prepared.adapter_id != ADAPTER_ID:
            raise AdapterError("Control Center post-canary operation identity mismatch")
        if prepared.execution_enabled:
            raise AdapterError("Control Center post-canary canary must remain execution-disabled")
        if prepared.source_repository != SOURCE_REPOSITORY:
            raise AdapterError("Control Center source repository mismatch")
        if SHA_RE.fullmatch(prepared.source_sha) is None:
            raise AdapterError("Control Center source SHA is invalid")
        if prepared.target_alias != TARGET_ALIAS:
            raise AdapterError("Control Center target alias mismatch")
        if prepared.rollback_policy != ROLLBACK_POLICY:
            raise AdapterError("read-only reconciliation requires rollback policy NONE")
        if prepared.mutation_budget != INVOCATION_BUDGET:
            raise AdapterError("Control Center reconciliation invocation budget mismatch")
        if not REQUIRED_EXCLUSIONS.issubset(set(prepared.exclusions)):
            raise AdapterError("Control Center required exclusions are missing")
        if not REQUIRED_DEPENDENCIES.issubset(set(prepared.dependencies)):
            raise AdapterError("Control Center source/interface dependency mismatch")

    def preflight(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "adapter_id": ADAPTER_ID,
            "source_sha": prepared.source_sha,
            "source_repository_id": SOURCE_REPOSITORY_ID,
            "workflow_path": WORKFLOW_PATH,
            "workflow_source_blob": WORKFLOW_SOURCE_BLOB,
            "read_only": True,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "mutation_enabled": False,
            "production_apply_authorized": False,
            "result": "SOURCE_CANARY_CONTRACT_PASS",
        }

    def apply(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        raise AdapterError(
            "Control Center post-canary operation is execution-disabled; P9 must not post its owner trigger or dispatch the workflow"
        )

    def postconditions(self, prepared: PreparedOperation) -> Mapping[str, Any]:
        self._validate(prepared)
        return {
            "required_false_flags": (
                "MERGE_POST_SENT",
                "REMOTE_D1_MUTATION",
                "WORKER_MUTATION",
                "CLOUDFLARE_CONFIG_MUTATION",
                "GITHUB_DECISION_MUTATION",
                "GITHUB_APP_PERMISSION_MUTATION",
            ),
            "read_only": True,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
        }
