from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
EXPECTED_AUTHORIZATION_REPOSITORY = "rozkalnsandris/deploy-authorizations"
EXPECTED_QUEUE_REPOSITORY = "rozkalnsandris/ops-workflows"
EXPECTED_QUEUE_REPOSITORY_ID = 1328835922
EXPECTED_OWNER_USER_ID = 277435981
EXPECTED_OPERATOR_APP_ID = 1144995
EXPECTED_OPERATOR_APP_SLUG = "chatgpt-codex-connector"
EXPECTED_EXECUTOR_APP_ID = 4748870


class IsolatedAuthSurfaceError(ValueError):
    pass


@dataclass(frozen=True)
class IsolatedAuthSurfaceContract:
    authorization_repository: str
    authorization_repository_id: int | None
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
        "authorization_repository_visibility",
        "issues_enabled",
        "actions_enabled",
        "queue_repository",
        "queue_repository_id",
        "owner_user_id",
        "approved_operator_integrations",
        "executor_app",
        "required_repository_invariants",
        "runtime_binding_ready",
        "host_wiring_enabled",
        "production_mutation_enabled",
    }
)
_OPERATOR_KEYS = frozenset(
    {"app_id", "slug", "issues_permission", "authority_mode"}
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

    operators = payload["approved_operator_integrations"]
    if type(operators) is not list or len(operators) != 1 or type(operators[0]) is not dict:
        raise IsolatedAuthSurfaceError("exactly one approved operator integration is required")
    operator = operators[0]
    _require_exact_keys(operator, _OPERATOR_KEYS, "approved_operator_integrations[0]")
    if operator["app_id"] != EXPECTED_OPERATOR_APP_ID:
        raise IsolatedAuthSurfaceError("operator app id drifted")
    if operator["slug"] != EXPECTED_OPERATOR_APP_SLUG:
        raise IsolatedAuthSurfaceError("operator app slug drifted")
    if operator["issues_permission"] != "write":
        raise IsolatedAuthSurfaceError("operator integration must have Issues write")
    if operator["authority_mode"] != "explicit-owner-invocation-only":
        raise IsolatedAuthSurfaceError("operator authority mode drifted")

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
