from __future__ import annotations

from typing import Any, Mapping

from .hermes_deals_origin_canonical_revalidator import (
    ConcreteCanonicalHermesOriginRevalidator,
)
from .hermes_deals_origin_dispatch_request import SCHEMA as REQUEST_SCHEMA
from .hermes_deals_origin_helper_launch import (
    FixedHelperRunner,
    HermesDealsOriginHelperLaunchReceipt,
    HermesDealsOriginOneShotHelperLauncher,
)
from .hermes_deals_origin_host_evidence import (
    ConcreteSanitizedHermesOriginHostEvidenceResolver,
)
from .hermes_deals_origin_privileged_broker import parse_broker_transport_request

PRIVILEGED_DISPATCH_ENABLED = False
HOST_WIRING_ENABLED = False
LIVE_INSTALL_ELIGIBLE = False
GENUINE_HERMES_AUDIT_AUTHORIZED = False
RUNNER_RETIREMENT_ELIGIBLE = False
PRODUCTION_MUTATION_STARTED = False
BROKER_ENTRYPOINT_WIRED = False


class HermesDealsOriginBrokerCompositionError(RuntimeError):
    pass


class HermesDealsOriginBrokerComposition:
    """Bind the concrete validators to the fixed one-shot launcher.

    No instance is constructed by the installed broker entrypoint while host
    wiring and LIVE gates remain false. Tests must inject a fake runner; this
    module never imports or selects the real process runner.
    """

    def __init__(
        self,
        *,
        canonical_revalidator: ConcreteCanonicalHermesOriginRevalidator,
        host_evidence_resolver: ConcreteSanitizedHermesOriginHostEvidenceResolver,
        runner: FixedHelperRunner,
    ):
        if type(canonical_revalidator) is not ConcreteCanonicalHermesOriginRevalidator:
            raise HermesDealsOriginBrokerCompositionError(
                "broker composition requires the concrete Hermes canonical revalidator"
            )
        if (
            type(host_evidence_resolver)
            is not ConcreteSanitizedHermesOriginHostEvidenceResolver
        ):
            raise HermesDealsOriginBrokerCompositionError(
                "broker composition requires the concrete sanitized host resolver"
            )
        if not callable(runner):
            raise HermesDealsOriginBrokerCompositionError(
                "broker composition test runner is missing"
            )
        self._canonical_revalidator = canonical_revalidator
        self._host_evidence_resolver = host_evidence_resolver
        self._launcher = HermesDealsOriginOneShotHelperLauncher(runner=runner)

    def prepare_and_launch(
        self,
        raw_request: bytes,
    ) -> HermesDealsOriginHelperLaunchReceipt:
        request = parse_broker_transport_request(raw_request)
        return self._launcher.prepare_and_launch(
            {
                "schema": REQUEST_SCHEMA,
                "authorization_issue_number": request.authorization_issue_number,
            },
            canonical_revalidator=self._canonical_revalidator,
            host_evidence_resolver=self._host_evidence_resolver,
        )


def source_readiness() -> Mapping[str, Any]:
    return {
        "broker_composition_implemented": True,
        "concrete_canonical_revalidator_required": True,
        "concrete_sanitized_host_resolver_required": True,
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
