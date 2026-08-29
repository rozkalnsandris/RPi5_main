from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 2
EXPECTED_AUTHORIZATION_REPOSITORY = "rozkalnsandris/deploy-authorizations"
EXPECTED_OBSERVED_AUTHORIZATION_REPOSITORY_ID = 1350486101
EXPECTED_QUEUE_REPOSITORY = "rozkalnsandris/ops-workflows"
EXPECTED_QUEUE_REPOSITORY_ID = 1328835922
EXPECTED_OWNER_USER_ID = 277435981
EXCLUDED_OPERATOR_APP_ID = 1144995
EXCLUDED_OPERATOR_APP_SLUG = "chatgpt-codex-connector"
EXPECTED_EXECUTOR_APP_ID = 4748870


class IsolatedAuthSurfaceError(ValueError):
    pass


@dataclass(frozen=True)
class IsolatedAuthSurfaceContract:
    authorization_repository: str
    authorization_repository_id: int | None
    observed_repository_id: int
    queue_repository: str
    queue_repository_id: int
    owner_user_id: int
    activation_enabled: bool
    runtime_binding_ready: bool
    host_wiring_enabled: bool
    production_mutation_enabled: bool


_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "activation_enabled",
        "authorization_repository",
        "authorization_repository_id",
        "observed_repository_setup",
        "authorization_repository_visibility",
        "issues_enabled",
        "actions_enabled",
        "queue_repository",
        "queue_repository_id",
        "owner_user_id",
        "authorization_writer",
        "approved_operator_integrations",
        "excluded_operator_integrations",
        "executor_app",
        "required_repository_invariants",
        "runtime_binding_ready",
        "host_wiring_enabled",
        "production_mutation_enabled",
    }
)
_OBSERVED_SETUP_KEYS = frozenset(
    {
        "repository_id",
        "evidence_repository",
        "evidence_issue",
        "evidence_comment_id",
        "visibility",
        "issues_enabled",
        "actions_enabled",
        "direct_collaborator_count",
        "installed_github_app_count",
        "status",
    }
)
_AUTHORIZATION_WRITER_KEYS = frozenset(
    {
        "required_actor_type",
        "required_actor_id",
        "authoring_mode",
        "app_authored_issues_allowed",
    }
)
_EXCLUDED_OPERATOR_KEYS = frozenset(
    {"app_id", "slug", "reason", "observed_repository_permissions"}
)
_EXCLUDED_OPERATOR_PERMISSION_KEYS = frozenset(
    {
        "actions",
        "checks",
        "contents",
        "issues",
        "metadata",
        "pull_requests",
        "statuses",
        "workflows",
    }
)
_EXECUTOR_KEYS = frozenset(
    {"app_id", "issues_permission", "metadata_permission", "write_permissions_allowed"}
)
_INVARIANT_KEYS = frozenset(
    {
        "no_unapproved_human_collaborators",
        "no_unapproved_teams",
        "no_unapproved_integrations",
        "actions_disabled",
        "issues_enabled",
        "no_workflow_authority",
        "owner_only_issue_writes",
        "chatgpt_connector_not_selected",
    }
)


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    if frozenset(value) != expected:
        raise IsolatedAuthSurfaceError(f"{where} keys mismatch")


def _require_bool(value: Any, where: str, expected: bool | None = None) -> bool:
    if type(value) is not bool:
        raise IsolatedAuthSurfaceError(f"{where} must be boolean")
    if expected is not None and value is not expected:
        raise IsolatedAuthSurfaceError(f"{where} must be {str(expected).lower()}")
    return value


def _require_positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise IsolatedAuthSurfaceError(f"{where} must be a positive integer")
    return value


def _require_nonnegative_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise IsolatedAuthSurfaceError(f"{where} must be a nonnegative integer")
    return value


def validate_contract(payload: Mapping[str, Any]) -> IsolatedAuthSurfaceContract:
    if type(payload) is not dict:
        raise IsolatedAuthSurfaceError("contract root must be an object")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "contract")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise IsolatedAuthSurfaceError("unsupported schema_version")
    if payload["authorization_repository"] != EXPECTED_AUTHORIZATION_REPOSITORY:
        raise IsolatedAuthSurfaceError("authorization repository drifted")
    if payload["authorization_repository_visibility"] != "private":
        raise IsolatedAuthSurfaceError("authorization repository must be private")
    if payload["queue_repository"] != EXPECTED_QUEUE_REPOSITORY:
        raise IsolatedAuthSurfaceError("queue repository drifted")
    if payload["queue_repository_id"] != EXPECTED_QUEUE_REPOSITORY_ID:
        raise IsolatedAuthSurfaceError("queue repository id drifted")
    if payload["owner_user_id"] != EXPECTED_OWNER_USER_ID:
        raise IsolatedAuthSurfaceError("owner identity drifted")

    observed_setup = payload["observed_repository_setup"]
    if type(observed_setup) is not dict:
        raise IsolatedAuthSurfaceError("observed_repository_setup must be an object")
    _require_exact_keys(observed_setup, _OBSERVED_SETUP_KEYS, "observed_repository_setup")
    if observed_setup["repository_id"] != EXPECTED_OBSERVED_AUTHORIZATION_REPOSITORY_ID:
        raise IsolatedAuthSurfaceError("observed authorization repository id drifted")
    if observed_setup["evidence_repository"] != "rozkalnsandris/RPi5_main":
        raise IsolatedAuthSurfaceError("observed setup evidence repository drifted")
    if observed_setup["evidence_issue"] != 191:
        raise IsolatedAuthSurfaceError("observed setup evidence issue drifted")
    if observed_setup["evidence_comment_id"] != 5461784620:
        raise IsolatedAuthSurfaceError("observed setup evidence comment drifted")
    if observed_setup["visibility"] != "private":
        raise IsolatedAuthSurfaceError("observed authorization repository must be private")
    _require_bool(observed_setup["issues_enabled"], "observed_repository_setup.issues_enabled", True)
    _require_bool(observed_setup["actions_enabled"], "observed_repository_setup.actions_enabled", False)
    if _require_nonnegative_int(
        observed_setup["direct_collaborator_count"],
        "observed_repository_setup.direct_collaborator_count",
    ) != 0:
        raise IsolatedAuthSurfaceError("observed setup must have zero direct collaborators")
    if _require_nonnegative_int(
        observed_setup["installed_github_app_count"],
        "observed_repository_setup.installed_github_app_count",
    ) != 0:
        raise IsolatedAuthSurfaceError("observed setup must have zero installed GitHub Apps")
    if observed_setup["status"] != "partial-stop":
        raise IsolatedAuthSurfaceError("observed setup status drifted")

    _require_bool(payload["issues_enabled"], "issues_enabled", True)
    _require_bool(payload["actions_enabled"], "actions_enabled", False)
    activation_enabled = _require_bool(payload["activation_enabled"], "activation_enabled")
    runtime_binding_ready = _require_bool(payload["runtime_binding_ready"], "runtime_binding_ready")
    host_wiring_enabled = _require_bool(payload["host_wiring_enabled"], "host_wiring_enabled")
    production_mutation_enabled = _require_bool(
        payload["production_mutation_enabled"], "production_mutation_enabled"
    )

    repository_id = payload["authorization_repository_id"]
    if repository_id is not None:
        repository_id = _require_positive_int(repository_id, "authorization_repository_id")
        if repository_id != observed_setup["repository_id"]:
            raise IsolatedAuthSurfaceError(
                "authorization_repository_id must match observed repository id"
            )

    writer = payload["authorization_writer"]
    if type(writer) is not dict:
        raise IsolatedAuthSurfaceError("authorization_writer must be an object")
    _require_exact_keys(writer, _AUTHORIZATION_WRITER_KEYS, "authorization_writer")
    if writer["required_actor_type"] != "User":
        raise IsolatedAuthSurfaceError("authorization writer actor type must be User")
    if writer["required_actor_id"] != EXPECTED_OWNER_USER_ID:
        raise IsolatedAuthSurfaceError("authorization writer actor id drifted")
    if writer["authoring_mode"] != "owner-authenticated-github-session":
        raise IsolatedAuthSurfaceError("authorization writer authoring mode drifted")
    _require_bool(
        writer["app_authored_issues_allowed"],
        "authorization_writer.app_authored_issues_allowed",
        False,
    )

    operators = payload["approved_operator_integrations"]
    if type(operators) is not list or operators:
        raise IsolatedAuthSurfaceError("approved operator integrations must remain empty")

    excluded_operators = payload["excluded_operator_integrations"]
    if (
        type(excluded_operators) is not list
        or len(excluded_operators) != 1
        or type(excluded_operators[0]) is not dict
    ):
        raise IsolatedAuthSurfaceError("exactly one excluded operator integration is required")
    excluded_operator = excluded_operators[0]
    _require_exact_keys(
        excluded_operator,
        _EXCLUDED_OPERATOR_KEYS,
        "excluded_operator_integrations[0]",
    )
    if excluded_operator["app_id"] != EXCLUDED_OPERATOR_APP_ID:
        raise IsolatedAuthSurfaceError("excluded operator app id drifted")
    if excluded_operator["slug"] != EXCLUDED_OPERATOR_APP_SLUG:
        raise IsolatedAuthSurfaceError("excluded operator app slug drifted")
    if excluded_operator["reason"] != "fixed-broad-repository-write-permissions":
        raise IsolatedAuthSurfaceError("excluded operator reason drifted")
    permissions = excluded_operator["observed_repository_permissions"]
    if type(permissions) is not dict:
        raise IsolatedAuthSurfaceError(
            "excluded operator observed permissions must be an object"
        )
    _require_exact_keys(
        permissions,
        _EXCLUDED_OPERATOR_PERMISSION_KEYS,
        "excluded operator observed permissions",
    )
    expected_permissions = {
        "actions": "write",
        "checks": "read",
        "contents": "write",
        "issues": "write",
        "metadata": "read",
        "pull_requests": "write",
        "statuses": "read",
        "workflows": "write",
    }
    if permissions != expected_permissions:
        raise IsolatedAuthSurfaceError("excluded operator permission evidence drifted")

    executor = payload["executor_app"]
    if type(executor) is not dict:
        raise IsolatedAuthSurfaceError("executor_app must be an object")
    _require_exact_keys(executor, _EXECUTOR_KEYS, "executor_app")
    if executor["app_id"] != EXPECTED_EXECUTOR_APP_ID:
        raise IsolatedAuthSurfaceError("executor app id drifted")
    if executor["issues_permission"] != "read" or executor["metadata_permission"] != "read":
        raise IsolatedAuthSurfaceError("executor App must remain Issues read + Metadata read")
    _require_bool(executor["write_permissions_allowed"], "executor_app.write_permissions_allowed", False)

    invariants = payload["required_repository_invariants"]
    if type(invariants) is not dict:
        raise IsolatedAuthSurfaceError("required_repository_invariants must be an object")
    _require_exact_keys(invariants, _INVARIANT_KEYS, "required_repository_invariants")
    for key in sorted(_INVARIANT_KEYS):
        _require_bool(invariants[key], f"required_repository_invariants.{key}", True)

    if repository_id is None:
        if activation_enabled or runtime_binding_ready or host_wiring_enabled or production_mutation_enabled:
            raise IsolatedAuthSurfaceError(
                "unbound authorization repository id requires dormant fail-closed state"
            )
    if activation_enabled and not runtime_binding_ready:
        raise IsolatedAuthSurfaceError("activation requires runtime_binding_ready")
    if host_wiring_enabled and not activation_enabled:
        raise IsolatedAuthSurfaceError("host wiring requires activation")
    if production_mutation_enabled:
        raise IsolatedAuthSurfaceError("P9 isolated auth source contract may not enable production mutation")

    return IsolatedAuthSurfaceContract(
        authorization_repository=payload["authorization_repository"],
        authorization_repository_id=repository_id,
        observed_repository_id=observed_setup["repository_id"],
        queue_repository=payload["queue_repository"],
        queue_repository_id=payload["queue_repository_id"],
        owner_user_id=payload["owner_user_id"],
        activation_enabled=activation_enabled,
        runtime_binding_ready=runtime_binding_ready,
        host_wiring_enabled=host_wiring_enabled,
        production_mutation_enabled=production_mutation_enabled,
    )


def load_contract(path: str | Path) -> IsolatedAuthSurfaceContract:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IsolatedAuthSurfaceError("isolated auth surface contract is unreadable") from exc
    return validate_contract(payload)
