from __future__ import annotations

from dataclasses import dataclass
import json
import os
import selectors
import subprocess
import time
from typing import Callable, Mapping, Protocol

from .weather_public_runtime_execution import (
    HELPER_EXECUTABLE,
    WeatherExecutablePlan,
    WeatherExecutableStage,
    validate_weather_executable_plan,
)
from .weather_public_runtime_host_wiring import WeatherHostWiringPlan
from .weather_public_runtime_preactivation import WeatherPreactivationEnvelope

HELPER_PROCESS_LAUNCH_IMPLEMENTED = True
HELPER_PROCESS_LAUNCH_WIRED = True
HELPER_TIMEOUT_SECONDS = 1800
MAX_STDOUT_BYTES = 4096
MAX_STDERR_BYTES = 4096
READ_CHUNK_BYTES = 1024
FIXED_HELPER_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONUNBUFFERED": "1",
}


class WeatherHelperLaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class HelperProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class WeatherHelperLaunchReceipt:
    authorization_issue_number: int
    request_id: str
    stage_id: str
    helper_id: str
    source_sha: str
    preactivation_sha256: str
    operations_performed: int
    helper_exit_code: int
    output_validated: bool
    production_mutation_started: bool


class FixedHelperRunner(Protocol):
    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        env: Mapping[str, str],
        timeout_seconds: int,
        stdout_limit: int,
        stderr_limit: int,
    ) -> HelperProcessResult: ...


def _kill_and_wait(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run_fixed_helper_process(
    argv: tuple[str, ...],
    *,
    env: Mapping[str, str],
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
) -> HelperProcessResult:
    if len(argv) < 7 or argv[0] != HELPER_EXECUTABLE:
        raise WeatherHelperLaunchError("fixed Weather helper argv drift")
    if dict(env) != FIXED_HELPER_ENV:
        raise WeatherHelperLaunchError("fixed Weather helper environment drift")
    if timeout_seconds != HELPER_TIMEOUT_SECONDS:
        raise WeatherHelperLaunchError("fixed Weather helper timeout drift")
    if stdout_limit != MAX_STDOUT_BYTES or stderr_limit != MAX_STDERR_BYTES:
        raise WeatherHelperLaunchError("fixed Weather helper output limit drift")
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(FIXED_HELPER_ENV),
            shell=False,
            close_fds=True,
        )
    except OSError as exc:
        raise WeatherHelperLaunchError("fixed Weather helper process could not start") from exc
    if process.stdout is None or process.stderr is None:
        _kill_and_wait(process)
        raise WeatherHelperLaunchError("fixed Weather helper pipes unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout_limit))
    selector.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr_limit))
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_and_wait(process)
                raise WeatherHelperLaunchError("fixed Weather helper timed out")
            events = selector.select(remaining)
            if not events:
                continue
            for key, _mask in events:
                name, limit = key.data
                chunk = os.read(key.fileobj.fileno(), READ_CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                captured[name].extend(chunk)
                if len(captured[name]) > limit:
                    _kill_and_wait(process)
                    raise WeatherHelperLaunchError(f"fixed Weather helper {name} exceeded source limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _kill_and_wait(process)
            raise WeatherHelperLaunchError("fixed Weather helper timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            _kill_and_wait(process)
            raise WeatherHelperLaunchError("fixed Weather helper timed out") from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return HelperProcessResult(returncode, bytes(captured["stdout"]), bytes(captured["stderr"]))


def _stage(plan: WeatherExecutablePlan, stage_id: str) -> WeatherExecutableStage:
    matches = tuple(stage for stage in plan.stages if stage.stage_id == stage_id)
    if len(matches) != 1:
        raise WeatherHelperLaunchError("Weather helper stage identity is unknown or duplicated")
    return matches[0]


def _validate_result(stage: WeatherExecutableStage, plan: WeatherExecutablePlan, result: HelperProcessResult) -> int:
    if type(result) is not HelperProcessResult:
        raise WeatherHelperLaunchError("Weather helper runner returned unsupported result")
    if result.returncode != 0 or result.stderr:
        raise WeatherHelperLaunchError("Weather helper failed closed")
    try:
        payload = json.loads(result.stdout.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherHelperLaunchError("Weather helper output is not strict JSON") from exc
    expected_fields = {
        "schema",
        "stage_id",
        "helper_id",
        "source_sha",
        "preactivation_sha256",
        "operations_performed",
        "production_mutation_started",
    }
    if type(payload) is not dict or set(payload) != expected_fields:
        raise WeatherHelperLaunchError("Weather helper output fields drifted")
    if payload["schema"] != "rozkalns-weather.public-runtime-helper-receipt.v1":
        raise WeatherHelperLaunchError("Weather helper receipt schema drifted")
    if payload["stage_id"] != stage.stage_id or payload["helper_id"] != stage.helper_id:
        raise WeatherHelperLaunchError("Weather helper receipt identity drifted")
    if payload["source_sha"] != plan.source_sha or payload["preactivation_sha256"] != plan.preactivation_sha256:
        raise WeatherHelperLaunchError("Weather helper receipt provenance drifted")
    operations = payload["operations_performed"]
    if type(operations) is not int or not 0 <= operations <= stage.max_operations:
        raise WeatherHelperLaunchError("Weather helper operation budget exceeded")
    expected_started = not stage.read_only and operations > 0
    if payload["production_mutation_started"] is not expected_started:
        raise WeatherHelperLaunchError("Weather helper mutation-start receipt drifted")
    return operations


class WeatherOneShotStageLauncher:
    """Launch each canonical Weather stage at most once; no automatic retry exists."""

    def __init__(self, *, runner: FixedHelperRunner = run_fixed_helper_process):
        self._runner = runner
        self._invoked: set[str] = set()

    def launch_stage(
        self,
        executable_plan: WeatherExecutablePlan,
        host_plan: WeatherHostWiringPlan,
        envelope: WeatherPreactivationEnvelope,
        stage_id: str,
    ) -> WeatherHelperLaunchReceipt:
        validate_weather_executable_plan(executable_plan, host_plan, envelope)
        stage = _stage(executable_plan, stage_id)
        if stage.stage_id in self._invoked:
            raise WeatherHelperLaunchError("Weather helper stage invocation already consumed")
        if stage.executable != HELPER_EXECUTABLE:
            raise WeatherHelperLaunchError("Weather helper executable identity drifted")
        self._invoked.add(stage.stage_id)
        argv = (stage.executable,) + stage.arguments
        try:
            result = self._runner(
                argv,
                env=FIXED_HELPER_ENV,
                timeout_seconds=HELPER_TIMEOUT_SECONDS,
                stdout_limit=MAX_STDOUT_BYTES,
                stderr_limit=MAX_STDERR_BYTES,
            )
        except WeatherHelperLaunchError:
            raise
        except Exception:
            raise WeatherHelperLaunchError("fixed Weather helper runner failed") from None
        operations = _validate_result(stage, executable_plan, result)
        return WeatherHelperLaunchReceipt(
            authorization_issue_number=executable_plan.authorization_issue_number,
            request_id=executable_plan.request_id,
            stage_id=stage.stage_id,
            helper_id=stage.helper_id,
            source_sha=executable_plan.source_sha,
            preactivation_sha256=executable_plan.preactivation_sha256,
            operations_performed=operations,
            helper_exit_code=result.returncode,
            output_validated=True,
            production_mutation_started=not stage.read_only and operations > 0,
        )


def source_readiness() -> Mapping[str, object]:
    return {
        "helper_process_launch_implemented": HELPER_PROCESS_LAUNCH_IMPLEMENTED,
        "helper_process_launch_wired": HELPER_PROCESS_LAUNCH_WIRED,
        "executable": HELPER_EXECUTABLE,
        "timeout_seconds": HELPER_TIMEOUT_SECONDS,
        "stdout_limit_bytes": MAX_STDOUT_BYTES,
        "stderr_limit_bytes": MAX_STDERR_BYTES,
        "shell": False,
        "environment": dict(FIXED_HELPER_ENV),
        "stage_invocation_budget": 1,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "caller_supplied_executable": False,
        "caller_supplied_environment": False,
        "canonical_revalidation_required_immediately_before_launch": True,
        "production_mutation_started": False,
    }
