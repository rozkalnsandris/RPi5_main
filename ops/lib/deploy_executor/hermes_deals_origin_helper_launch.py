from __future__ import annotations

from dataclasses import dataclass
import os
import selectors
import subprocess
import time
from typing import Any, Callable, Mapping, Protocol

from .hermes_deals_origin_adapter import (
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
    SOURCE_REPOSITORY,
)
from .hermes_deals_origin_privileged_consumer import (
    CanonicalHermesOriginRevalidator,
    SanitizedHermesOriginHostEvidenceResolver,
)
from .hermes_deals_origin_privileged_dispatcher import (
    INSTALLED_HELPER_PATH,
    HermesDealsOriginPrivilegedDispatchPlan,
    prepare_hermes_deals_origin_privileged_dispatch,
)

HELPER_PROCESS_LAUNCH_IMPLEMENTED = True
HELPER_PROCESS_LAUNCH_WIRED = False
HELPER_TIMEOUT_SECONDS = 50
MAX_STDOUT_BYTES = 4096
MAX_STDERR_BYTES = 4096
READ_CHUNK_BYTES = 1024
FIXED_HELPER_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONUNBUFFERED": "1",
}
ACCEPTED_HELPER_EXIT_CODES = frozenset({0, 1, 2})


class HermesDealsOriginHelperLaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class HelperProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class HermesDealsOriginHelperLaunchReceipt:
    authorization_issue_number: int
    request_id: str
    operation_id: str
    capability: str
    registered_source_sha: str
    canonical_as_of: str
    helper_source_blob: str
    installed_helper_path: str
    helper_arguments: tuple[str, str]
    helper_exit_code: int
    stdout_validated: bool
    production_mutation_started: bool = False


class FixedHelperRunner(Protocol):
    def __call__(
        self,
        argv: tuple[str, str, str],
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


def _run_fixed_helper_process(
    argv: tuple[str, str, str],
    *,
    env: Mapping[str, str],
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
) -> HelperProcessResult:
    """Run only the source-fixed helper argv with bounded pipe capture."""

    if argv[0] != INSTALLED_HELPER_PATH or len(argv) != 3:
        raise HermesDealsOriginHelperLaunchError("fixed helper runner argv drift")
    if dict(env) != FIXED_HELPER_ENV:
        raise HermesDealsOriginHelperLaunchError("fixed helper runner environment drift")
    if timeout_seconds != HELPER_TIMEOUT_SECONDS:
        raise HermesDealsOriginHelperLaunchError("fixed helper runner timeout drift")
    if stdout_limit != MAX_STDOUT_BYTES or stderr_limit != MAX_STDERR_BYTES:
        raise HermesDealsOriginHelperLaunchError("fixed helper runner output limit drift")

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
        raise HermesDealsOriginHelperLaunchError("fixed helper process could not start") from exc
    if process.stdout is None or process.stderr is None:
        _kill_and_wait(process)
        raise HermesDealsOriginHelperLaunchError("fixed helper process pipes are unavailable")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, ("stdout", MAX_STDOUT_BYTES))
    selector.register(process.stderr, selectors.EVENT_READ, ("stderr", MAX_STDERR_BYTES))
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + HELPER_TIMEOUT_SECONDS
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_and_wait(process)
                raise HermesDealsOriginHelperLaunchError("fixed helper process timed out")
            events = selector.select(remaining)
            if not events:
                continue
            for key, _mask in events:
                name, limit = key.data
                try:
                    chunk = os.read(key.fileobj.fileno(), READ_CHUNK_BYTES)
                except OSError as exc:
                    _kill_and_wait(process)
                    raise HermesDealsOriginHelperLaunchError(
                        "fixed helper process output read failed"
                    ) from exc
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                captured[name].extend(chunk)
                if len(captured[name]) > limit:
                    _kill_and_wait(process)
                    raise HermesDealsOriginHelperLaunchError(
                        f"fixed helper {name} exceeded source limit"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _kill_and_wait(process)
            raise HermesDealsOriginHelperLaunchError("fixed helper process timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            _kill_and_wait(process)
            raise HermesDealsOriginHelperLaunchError("fixed helper process timed out") from exc
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()

    return HelperProcessResult(
        returncode=returncode,
        stdout=bytes(captured["stdout"]),
        stderr=bytes(captured["stderr"]),
    )


def _validate_plan(plan: HermesDealsOriginPrivilegedDispatchPlan) -> None:
    if type(plan) is not HermesDealsOriginPrivilegedDispatchPlan:
        raise HermesDealsOriginHelperLaunchError("helper launch requires the canonical dispatch plan")
    if plan.operation_id != OPERATION_ID or plan.source_repository != SOURCE_REPOSITORY:
        raise HermesDealsOriginHelperLaunchError("helper launch operation/source identity drift")
    if plan.capability != PULL_HELPER_CAPABILITY:
        raise HermesDealsOriginHelperLaunchError("helper launch capability drift")
    if plan.helper_source_blob != PULL_HELPER_SOURCE_BLOB:
        raise HermesDealsOriginHelperLaunchError("helper launch source blob drift")
    if plan.installed_helper_path != INSTALLED_HELPER_PATH:
        raise HermesDealsOriginHelperLaunchError("helper launch executable identity drift")
    if plan.helper_argument_names != PULL_HELPER_ARGUMENTS:
        raise HermesDealsOriginHelperLaunchError("helper launch interface drift")
    if plan.helper_arguments != (plan.registered_source_sha, plan.canonical_as_of):
        raise HermesDealsOriginHelperLaunchError("helper launch canonical argv drift")
    if any(
        (
            plan.privileged_dispatch_enabled,
            plan.host_wiring_enabled,
            plan.genuine_hermes_audit_authorized,
            plan.runner_retirement_eligible,
            plan.production_mutation_started,
        )
    ):
        raise HermesDealsOriginHelperLaunchError("unexpected live authority entered helper plan")


def _validate_result(
    plan: HermesDealsOriginPrivilegedDispatchPlan,
    result: HelperProcessResult,
) -> None:
    if type(result) is not HelperProcessResult:
        raise HermesDealsOriginHelperLaunchError("fixed helper runner returned an invalid result")
    if result.returncode not in ACCEPTED_HELPER_EXIT_CODES:
        raise HermesDealsOriginHelperLaunchError("fixed helper returned an unexpected exit code")
    if len(result.stdout) > MAX_STDOUT_BYTES or len(result.stderr) > MAX_STDERR_BYTES:
        raise HermesDealsOriginHelperLaunchError("fixed helper output exceeded source limit")
    if result.stderr:
        raise HermesDealsOriginHelperLaunchError("fixed helper emitted stderr")
    expected = (
        f"CAPABILITY={PULL_HELPER_CAPABILITY} SOURCE_SHA={plan.registered_source_sha} "
        f"AS_OF={plan.canonical_as_of} PROBE_EXIT_CODE={result.returncode}\n"
        "PRODUCTION_DATABASE_WRITE=false\n"
        "PRODUCTION_DEPLOYMENT=false\n"
        "RESTART_OR_CONFIGURATION_MUTATION=false\n"
    ).encode("ascii")
    if result.stdout != expected:
        raise HermesDealsOriginHelperLaunchError("fixed helper stdout contract drift")


class HermesDealsOriginOneShotHelperLauncher:
    """One-shot fixed helper launcher; the socket caller never receives this seam."""

    def __init__(self, *, runner: FixedHelperRunner = _run_fixed_helper_process):
        self._runner = runner
        self._invoked = False

    def _launch_validated_plan(
        self,
        plan: HermesDealsOriginPrivilegedDispatchPlan,
    ) -> HermesDealsOriginHelperLaunchReceipt:
        if self._invoked:
            raise HermesDealsOriginHelperLaunchError("helper invocation budget already consumed")
        _validate_plan(plan)
        self._invoked = True
        argv = (
            INSTALLED_HELPER_PATH,
            plan.registered_source_sha,
            plan.canonical_as_of,
        )
        try:
            result = self._runner(
                argv,
                env=FIXED_HELPER_ENV,
                timeout_seconds=HELPER_TIMEOUT_SECONDS,
                stdout_limit=MAX_STDOUT_BYTES,
                stderr_limit=MAX_STDERR_BYTES,
            )
        except HermesDealsOriginHelperLaunchError:
            raise
        except Exception:
            raise HermesDealsOriginHelperLaunchError("fixed helper runner failed") from None
        _validate_result(plan, result)
        return HermesDealsOriginHelperLaunchReceipt(
            authorization_issue_number=plan.authorization_issue_number,
            request_id=plan.request_id,
            operation_id=plan.operation_id,
            capability=plan.capability,
            registered_source_sha=plan.registered_source_sha,
            canonical_as_of=plan.canonical_as_of,
            helper_source_blob=plan.helper_source_blob,
            installed_helper_path=plan.installed_helper_path,
            helper_arguments=plan.helper_arguments,
            helper_exit_code=result.returncode,
            stdout_validated=True,
        )

    def prepare_and_launch(
        self,
        request_payload: Mapping[str, Any],
        *,
        canonical_revalidator: CanonicalHermesOriginRevalidator,
        host_evidence_resolver: SanitizedHermesOriginHostEvidenceResolver,
    ) -> HermesDealsOriginHelperLaunchReceipt:
        """Revalidate the identity-only request immediately before one fixed launch."""

        plan = prepare_hermes_deals_origin_privileged_dispatch(
            request_payload,
            canonical_revalidator=canonical_revalidator,
            host_evidence_resolver=host_evidence_resolver,
        )
        return self._launch_validated_plan(plan)


def source_readiness() -> Mapping[str, object]:
    return {
        "helper_process_launch_implemented": HELPER_PROCESS_LAUNCH_IMPLEMENTED,
        "helper_process_launch_wired": HELPER_PROCESS_LAUNCH_WIRED,
        "executable": INSTALLED_HELPER_PATH,
        "argument_names": PULL_HELPER_ARGUMENTS,
        "timeout_seconds": HELPER_TIMEOUT_SECONDS,
        "stdout_limit_bytes": MAX_STDOUT_BYTES,
        "stderr_limit_bytes": MAX_STDERR_BYTES,
        "shell": False,
        "environment": dict(FIXED_HELPER_ENV),
        "invocation_budget": 1,
        "accepted_exit_codes": tuple(sorted(ACCEPTED_HELPER_EXIT_CODES)),
        "caller_plan_authority": False,
        "canonical_revalidation_required": True,
        "production_mutation_started": False,
    }
