from __future__ import annotations

from typing import Any, Mapping

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    accept_issue,
)
from .weather_private_application_staging import OPERATION_ID as APPLICATION_STAGE_OPERATION_ID
from .weather_private_application_staging_runtime import (
    AUTH_SURFACE,
    EXECUTOR_PRIVATE_KEY,
    WeatherNextPrivateApplicationStageRuntimeError,
    run_privileged_application_stage,
)
from .weather_private_bigquery_host_installer import (
    WeatherNextPrivateHostInstallerError,
    public_receipt,
)
from .weather_private_bigquery_host_installer_runtime import (
    INSTALL_OPERATION_ID,
    run_privileged_install,
)
from .weather_private_bigquery_runtime_materialization import OPERATION_ID as RUNTIME_MATERIALIZATION_OPERATION_ID
from .weather_private_bigquery_runtime_transport import (
    WeatherNextPrivateRuntimeTransportError,
    run_privileged_runtime_materialization,
)
from .weather_private_bigquery_runtime_mode_recovery import (
    OPERATION_ID as RUNTIME_MODE_RECOVERY_OPERATION_ID,
    WeatherNextPrivateRuntimeModeRecoveryError,
    run_privileged_runtime_mode_recovery,
)


class WeatherNextPrivatePrivilegedDispatchError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextPrivatePrivilegedDispatchError(message)


def _route_operation(issue_number: int) -> str:
    if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
        _fail("authorization issue number is invalid")
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
        response = clients.authorization.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        accepted = accept_issue(
            response.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=response.server_time,
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        operation = accepted.payload.get("operation_id")
        if type(operation) is not str:
            _fail("authorization operation identity is malformed")
    except WeatherNextPrivatePrivilegedDispatchError:
        raise
    except Exception:
        _fail("privileged dispatch operation discovery failed closed")
    if operation not in {
        INSTALL_OPERATION_ID,
        APPLICATION_STAGE_OPERATION_ID,
        RUNTIME_MATERIALIZATION_OPERATION_ID,
        RUNTIME_MODE_RECOVERY_OPERATION_ID,
    }:
        _fail("authorization operation is outside the fixed WeatherNext privileged allowlist")
    return operation


def run_privileged_request(issue_number: int) -> Mapping[str, Any]:
    operation = _route_operation(issue_number)
    try:
        if operation == INSTALL_OPERATION_ID:
            return dict(public_receipt(run_privileged_install(issue_number)))
        if operation == APPLICATION_STAGE_OPERATION_ID:
            return dict(run_privileged_application_stage(issue_number))
        if operation == RUNTIME_MATERIALIZATION_OPERATION_ID:
            return dict(run_privileged_runtime_materialization(issue_number))
        if operation == RUNTIME_MODE_RECOVERY_OPERATION_ID:
            return dict(run_privileged_runtime_mode_recovery(issue_number))
    except (
        WeatherNextPrivateHostInstallerError,
        WeatherNextPrivateApplicationStageRuntimeError,
        WeatherNextPrivateRuntimeTransportError,
        WeatherNextPrivateRuntimeModeRecoveryError,
    ) as exc:
        raise WeatherNextPrivatePrivilegedDispatchError(str(exc)) from exc
    _fail("fixed WeatherNext privileged dispatch reached unreachable state")
