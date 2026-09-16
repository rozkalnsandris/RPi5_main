from __future__ import annotations

import inspect
import json
from typing import Any, Mapping

from .hermes_deals_runner_smoke_install import (
    APPLY_RECEIPT_SCHEMA,
    receipt_dict,
)
from .hermes_deals_runner_smoke_install_runtime import (
    RunnerSmokeInstallRuntimeError,
    build_runner_smoke_install_runtime,
)

REQUEST_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-request.v1"
FAILURE_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-runtime-failure.v1"
SOCKET_PATH = "/run/rozkalns-hermes-deals-runner-smoke-install/request.sock"
BROKER_INSTALL_PATH = "/usr/local/libexec/rozkalns-runner-smoke-install/current/ops/bin/rpi5-hermes-deals-runner-smoke-install-broker"
SOCKET_UNIT = "rozkalns-hermes-deals-runner-smoke-install.socket"
SERVICE_UNIT = "rozkalns-hermes-deals-runner-smoke-install@.service"
REQUEST_MAX_BYTES = 192
MAX_ISSUE_NUMBER = 2_147_483_647
RUNTIME_ACTIVATION_ENABLED = False
SYSTEMD_SOCKET_INSTALLED = False
GENERIC_SUDO_ALLOWED = False


class RunnerSmokeInstallBrokerError(RuntimeError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RunnerSmokeInstallBrokerError(f"duplicate JSON field is forbidden: {key}")
        result[key] = value
    return result


def parse_broker_request(raw: bytes) -> int:
    if type(raw) is not bytes or not raw or len(raw) > REQUEST_MAX_BYTES:
        raise RunnerSmokeInstallBrokerError("broker request size is invalid")
    if b"\x00" in raw or b"\r" in raw:
        raise RunnerSmokeInstallBrokerError("broker request contains forbidden framing")
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise RunnerSmokeInstallBrokerError("broker request must be exactly one newline-terminated frame")
    try:
        decoded = raw[:-1].decode("utf-8", "strict")
        value = json.loads(decoded, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerSmokeInstallBrokerError("broker request is not strict UTF-8 JSON") from exc
    if type(value) is not dict or set(value) != {"schema", "authorization_issue_number"}:
        raise RunnerSmokeInstallBrokerError("broker request fields are not exact")
    if value["schema"] != REQUEST_SCHEMA:
        raise RunnerSmokeInstallBrokerError("broker request schema mismatch")
    issue_number = value["authorization_issue_number"]
    if type(issue_number) is not int or not (1 <= issue_number <= MAX_ISSUE_NUMBER):
        raise RunnerSmokeInstallBrokerError("authorization_issue_number is invalid")
    return issue_number


def _failure(issue_number: int, *, stage: str, reuse_forbidden: bool) -> Mapping[str, Any]:
    return {
        "schema": FAILURE_SCHEMA,
        "result": "FAIL_CLOSED",
        "authorization_issue_number": issue_number,
        "safe_stage": stage,
        "authorization_reuse_forbidden": reuse_forbidden,
        "mutation_state": "UNKNOWN_FAIL_CLOSED" if reuse_forbidden else "NOT_STARTED",
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def execute_broker_request(raw: bytes) -> Mapping[str, Any]:
    """Execute one fixed capability request; the caller supplies only issue identity."""

    issue_number = parse_broker_request(raw)
    try:
        runtime = build_runner_smoke_install_runtime()
    except RunnerSmokeInstallRuntimeError:
        return _failure(issue_number, stage="runtime_composition", reuse_forbidden=False)
    try:
        receipt = runtime.execute(issue_number)
    except RunnerSmokeInstallRuntimeError:
        return _failure(issue_number, stage="install_execution", reuse_forbidden=True)
    result = dict(receipt_dict(receipt))
    if result.get("schema") != APPLY_RECEIPT_SCHEMA or result.get("authorization_issue_number") != issue_number:
        return _failure(issue_number, stage="install_execution", reuse_forbidden=True)
    return result


def encode_broker_receipt(value: Mapping[str, Any]) -> bytes:
    raw = (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw:
        raise RunnerSmokeInstallBrokerError("broker receipt framing invariant failed")
    return raw


def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": 568,
        "identity_only_broker_implemented": True,
        "caller_authority": ("authorization_issue_number",),
        "request_schema": REQUEST_SCHEMA,
        "request_max_bytes": REQUEST_MAX_BYTES,
        "socket_path": SOCKET_PATH,
        "socket_unit": SOCKET_UNIT,
        "service_unit": SERVICE_UNIT,
        "broker_install_path": BROKER_INSTALL_PATH,
        "runtime_factory_arguments": tuple(inspect.signature(build_runner_smoke_install_runtime).parameters),
        "prebuilt_runtime_allowed": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_identity_allowed": False,
        "caller_hash_or_sha_allowed": False,
        "caller_target_or_operation_allowed": False,
        "generic_sudo_allowed": GENERIC_SUDO_ALLOWED,
        "rdc_no_new_privileges_must_remain": True,
        "root_owned_release_layout_required": True,
        "runtime_activation_enabled": RUNTIME_ACTIVATION_ENABLED,
        "systemd_socket_installed": SYSTEMD_SOCKET_INSTALLED,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
