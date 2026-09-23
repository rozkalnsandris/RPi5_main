from __future__ import annotations

import json
from typing import Any, Mapping

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import AUTHORIZATION_REPOSITORY
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
        value = response.value
        if type(value) is not dict or type(value.get("body")) is not str:
            _fail("authorization issue body is unavailable for fixed dispatch")
        payload = json.loads(value["body"])
        if type(payload) is not dict or type(payload.get("operation_id")) is not str:
            _fail("authorization operation identity is malformed")
        operation = payload["operation_id"]
    except WeatherNextPrivatePrivilegedDispatchError:
        raise
    except Exception:
        _fail("privileged dispatch operation discovery failed closed")
    if operation not in {INSTALL_OPERATION_ID, APPLICATION_STAGE_OPERATION_ID}:
        _fail("authorization operation is outside the fixed WeatherNext privileged allowlist")
    return operation


def run_privileged_request(issue_number: int) -> Mapping[str, Any]:
    operation = _route_operation(issue_number)
    try:
        if operation == INSTALL_OPERATION_ID:
            return dict(public_receipt(run_privileged_install(issue_number)))
        if operation == APPLICATION_STAGE_OPERATION_ID:
            return dict(run_privileged_application_stage(issue_number))
    except (WeatherNextPrivateHostInstallerError, WeatherNextPrivateApplicationStageRuntimeError) as exc:
        raise WeatherNextPrivatePrivilegedDispatchError(str(exc)) from exc
    _fail("fixed WeatherNext privileged dispatch reached unreachable state")
