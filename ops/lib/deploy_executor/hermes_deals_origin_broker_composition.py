from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .hermes_deals_origin_canonical_revalidator import (
    ConcreteCanonicalHermesOriginRevalidator,
)
from .hermes_deals_origin_dispatch_request import SCHEMA as REQUEST_SCHEMA
from .hermes_deals_origin_helper_launch import (
    FixedHelperRunner,
    HermesDealsOriginOneShotHelperLauncher,
)
from .hermes_deals_origin_host_evidence import (
    ConcreteSanitizedHermesOriginHostEvidenceResolver,
)
from .hermes_deals_origin_privileged_broker import parse_broker_transport_request
from .hermes_deals_origin_privileged_dispatcher import (
    prepare_hermes_deals_origin_privileged_dispatch,
)

PRIVILEGED_DISPATCH_ENABLED = False
HOST_WIRING_ENABLED = False
LIVE_INSTALL_ELIGIBLE = False
GENUINE_HERMES_AUDIT_AUTHORIZED = False
RUNNER_RETIREMENT_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False
BROKER_ENTRYPOINT_WIRED = True
BROKER_DISPATCH_RECEIPT_SCHEMA = "rozkalns.hermes-deals.origin-broker-dispatch-receipt.v1"
_SAFE_FAILURE_STAGES = frozenset({"canonical_prepare", "replay_consume", "helper_launch"})


class DurableHermesOriginReplayAuthority(Protocol):
    def consume(self, request_id: str) -> Any: ...


class HermesDealsOriginBrokerCompositionError(RuntimeError):
    def __init__(
        self,
        stage: str,
        *,
        replay_consume_attempted: bool = False,
        durable_replay_consumed: bool = False,
        helper_execution_attempted: bool = False,
    ):
        if stage not in _SAFE_FAILURE_STAGES:
            raise ValueError("broker composition failure stage is not allowlisted")
        self.stage = stage
        self.replay_consume_attempted = replay_consume_attempted
        self.durable_replay_consumed = durable_replay_consumed
        self.helper_execution_attempted = helper_execution_attempted
        super().__init__(stage)


@dataclass(frozen=True)
class HermesDealsOriginBrokerDispatchReceipt:
    schema: str
    result: str
    authorization_issue_number: int
    request_id: str
    operation_id: str
    capability: str
    registered_source_sha: str
    canonical_as_of: str
    replay_availability_checks: int
    durable_replay_consumed: bool
    replay_mutation_started: bool
    authorization_reuse_forbidden: bool
    helper_executed: bool
    helper_arguments: tuple[str, str]
    helper_exit_code: int
    helper_stdout_validated: bool
    production_mutation_started: bool = False


def _validate_replay_receipt(value: Any, request_id: str) -> int:
    if (
        getattr(value, "request_id", None) != request_id
        or getattr(value, "state", None) != "CONSUMED"
        or getattr(value, "availability_checks", None) != 2
        or getattr(value, "durable_replay_consumed", None) is not True
        or getattr(value, "replay_mutation_started", None) is not True
        or getattr(value, "production_mutation_started", None) is not False
    ):
        raise HermesDealsOriginBrokerCompositionError(
            "replay_consume",
            replay_consume_attempted=True,
        )
    return 2


class HermesDealsOriginBrokerComposition:
    """Bind canonical validation, durable replay consume and one fixed helper launch.

    The socket caller controls only ``authorization_issue_number``. The replay
    authority must be the exact object already used by the concrete revalidator,
    so the consume boundary can only follow its two identical availability checks.
    Tests inject a fake runner; production selection is isolated in the fixed
    no-argument runtime factory.
    """

    def __init__(
        self,
        *,
        canonical_revalidator: ConcreteCanonicalHermesOriginRevalidator,
        host_evidence_resolver: ConcreteSanitizedHermesOriginHostEvidenceResolver,
        replay_authority: DurableHermesOriginReplayAuthority,
        runner: FixedHelperRunner,
    ):
        if type(canonical_revalidator) is not ConcreteCanonicalHermesOriginRevalidator:
            raise TypeError("broker composition requires the concrete Hermes canonical revalidator")
        if type(host_evidence_resolver) is not ConcreteSanitizedHermesOriginHostEvidenceResolver:
            raise TypeError("broker composition requires the concrete sanitized host resolver")
        if getattr(canonical_revalidator, "_replay_availability", None) is not replay_authority:
            raise TypeError("broker composition requires the revalidator replay authority instance")
        if not callable(getattr(replay_authority, "consume", None)):
            raise TypeError("broker composition durable replay consume boundary is missing")
        if not callable(runner):
            raise TypeError("broker composition fixed runner is missing")
        self._canonical_revalidator = canonical_revalidator
        self._host_evidence_resolver = host_evidence_resolver
        self._replay_authority = replay_authority
        self._launcher = HermesDealsOriginOneShotHelperLauncher(runner=runner)

    def prepare_and_launch(self, raw_request: bytes) -> HermesDealsOriginBrokerDispatchReceipt:
        request = parse_broker_transport_request(raw_request)
        payload = {
            "schema": REQUEST_SCHEMA,
            "authorization_issue_number": request.authorization_issue_number,
        }
        try:
            plan = prepare_hermes_deals_origin_privileged_dispatch(
                payload,
                canonical_revalidator=self._canonical_revalidator,
                host_evidence_resolver=self._host_evidence_resolver,
            )
        except Exception:
            raise HermesDealsOriginBrokerCompositionError("canonical_prepare") from None

        try:
            replay = self._replay_authority.consume(plan.request_id)
            availability_checks = _validate_replay_receipt(replay, plan.request_id)
        except HermesDealsOriginBrokerCompositionError:
            raise
        except Exception:
            raise HermesDealsOriginBrokerCompositionError(
                "replay_consume",
                replay_consume_attempted=True,
            ) from None

        try:
            helper = self._launcher.launch_prepared_plan(plan)
        except Exception:
            raise HermesDealsOriginBrokerCompositionError(
                "helper_launch",
                replay_consume_attempted=True,
                durable_replay_consumed=True,
                helper_execution_attempted=True,
            ) from None

        return HermesDealsOriginBrokerDispatchReceipt(
            schema=BROKER_DISPATCH_RECEIPT_SCHEMA,
            result="HERMES_ORIGIN_BROKER_DISPATCH_COMPLETE",
            authorization_issue_number=helper.authorization_issue_number,
            request_id=helper.request_id,
            operation_id=helper.operation_id,
            capability=helper.capability,
            registered_source_sha=helper.registered_source_sha,
            canonical_as_of=helper.canonical_as_of,
            replay_availability_checks=availability_checks,
            durable_replay_consumed=True,
            replay_mutation_started=True,
            authorization_reuse_forbidden=True,
            helper_executed=True,
            helper_arguments=helper.helper_arguments,
            helper_exit_code=helper.helper_exit_code,
            helper_stdout_validated=helper.stdout_validated,
            production_mutation_started=False,
        )


def source_readiness() -> Mapping[str, Any]:
    return {
        "broker_composition_implemented": True,
        "concrete_canonical_revalidator_required": True,
        "concrete_sanitized_host_resolver_required": True,
        "shared_durable_replay_authority_required": True,
        "double_identical_replay_availability_required": True,
        "durable_replay_consume_before_helper": True,
        "fixed_one_shot_helper_launcher_required": True,
        "caller_authority": ("authorization_issue_number",),
        "broker_entrypoint_wired": BROKER_ENTRYPOINT_WIRED,
        "privileged_dispatch_enabled": PRIVILEGED_DISPATCH_ENABLED,
        "host_wiring_enabled": HOST_WIRING_ENABLED,
        "live_install_eligible": LIVE_INSTALL_ELIGIBLE,
        "genuine_hermes_audit_authorized": GENUINE_HERMES_AUDIT_AUTHORIZED,
        "runner_retirement_eligible": RUNNER_RETIREMENT_ELIGIBLE,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
    }
