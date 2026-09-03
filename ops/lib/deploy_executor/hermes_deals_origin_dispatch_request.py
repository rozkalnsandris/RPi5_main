from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "rozkalns.hermes-deals.origin-dispatch-request.v1"
MIN_ISSUE_NUMBER = 1
MAX_ISSUE_NUMBER = 2_147_483_647
_ALLOWED_FIELDS = frozenset({"schema", "authorization_issue_number"})


class HermesDealsOriginDispatchRequestError(ValueError):
    pass


@dataclass(frozen=True)
class HermesDealsOriginDispatchRequest:
    """Identity-only request for a future privileged Hermes origin-audit boundary.

    This value carries no command, path, argv, environment, repository entrypoint,
    sudo target, source SHA, probe date, artifact path, or other execution authority.
    A future privileged consumer must use the authorization issue identity to
    independently re-resolve all canonical authority and source/runtime evidence.
    """

    authorization_issue_number: int


def parse_hermes_deals_origin_dispatch_request(
    value: Mapping[str, Any],
) -> HermesDealsOriginDispatchRequest:
    if type(value) is not dict:
        raise HermesDealsOriginDispatchRequestError("dispatch request must be an object")
    fields = frozenset(value)
    if fields != _ALLOWED_FIELDS:
        unknown = sorted(fields - _ALLOWED_FIELDS)
        missing = sorted(_ALLOWED_FIELDS - fields)
        details = []
        if missing:
            details.append(f"missing fields: {missing}")
        if unknown:
            details.append(f"unexpected fields: {unknown}")
        raise HermesDealsOriginDispatchRequestError(
            "identity-only dispatch request shape mismatch"
            + (f" ({'; '.join(details)})" if details else "")
        )
    if value["schema"] != SCHEMA:
        raise HermesDealsOriginDispatchRequestError("dispatch request schema mismatch")
    issue_number = value["authorization_issue_number"]
    if type(issue_number) is not int:
        raise HermesDealsOriginDispatchRequestError(
            "authorization_issue_number must be an integer"
        )
    if not MIN_ISSUE_NUMBER <= issue_number <= MAX_ISSUE_NUMBER:
        raise HermesDealsOriginDispatchRequestError(
            "authorization_issue_number is outside the supported range"
        )
    return HermesDealsOriginDispatchRequest(
        authorization_issue_number=issue_number,
    )


def privileged_revalidation_requirements() -> tuple[str, ...]:
    """Static requirements a future privileged consumer must satisfy itself."""

    return (
        "re-fetch owner-authored LIVE-AUTH from isolated authorization repository",
        "revalidate LIVE-AUTH TTL body hash replay state and canonical queue binding",
        "re-fetch READY queue and require exact Hermes operation/source envelope",
        "revalidate exact Hermes source SHA merged reachability and exact-SHA CI",
        "revalidate disabled static registry operation and invocation budget/exclusions",
        "revalidate reviewed workflow dispatcher installer and probe provenance",
        "revalidate root-owned origin registration and installed helper identities",
        "derive all execution parameters from reviewed source/canonical state, never request prose",
    )


def source_readiness() -> Mapping[str, Any]:
    """Describe this source gate without creating an executable dispatch surface."""

    return {
        "schema": SCHEMA,
        "identity_fields": ("authorization_issue_number",),
        "privileged_dispatch_implemented": False,
        "privileged_dispatch_enabled": False,
        "host_wiring_enabled": False,
        "runner_retirement_eligible": False,
        "production_mutation_started": False,
        "independent_revalidation": privileged_revalidation_requirements(),
    }
