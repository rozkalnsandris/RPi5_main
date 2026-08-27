from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

AUTHORIZATION_REPOSITORY = "rozkalnsandris/ops-workflows"
AUTHORIZATION_REPOSITORY_ID = 1328835922
SCHEMA = "rozkalns.deploy-dispatch-request.v1"
REQUEST_FIELDS = frozenset(
    {
        "schema",
        "authorization_repository",
        "authorization_repository_id",
        "authorization_issue_id",
        "authorization_issue_number",
        "request_id",
    }
)
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class DispatchContractError(ValueError):
    pass


@dataclass(frozen=True)
class DispatchRequest:
    authorization_repository: str
    authorization_repository_id: int
    authorization_issue_id: int
    authorization_issue_number: int
    request_id: str


def _positive_int(value: Any, where: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise DispatchContractError(f"{where} must be an integer in range 1..{maximum}")
    return value


def parse_dispatch_request(value: Mapping[str, Any]) -> DispatchRequest:
    """Parse the only payload allowed to cross the unprivileged->privileged boundary.

    The request deliberately contains no source SHA, target, operation, path, argv,
    mutation budget, rollback command, or executable behavior. The privileged side
    must independently re-fetch LIVE-AUTH, queue/source/CI/baseline state and the
    source-controlled registry before entering any mutation-capable adapter.
    """
    if type(value) is not dict:
        raise DispatchContractError("dispatch request must be an object")
    actual = frozenset(value)
    if actual != REQUEST_FIELDS:
        missing = sorted(REQUEST_FIELDS - actual)
        extra = sorted(actual - REQUEST_FIELDS)
        raise DispatchContractError(
            f"dispatch request keys mismatch; missing={missing}, extra={extra}"
        )
    if value["schema"] != SCHEMA:
        raise DispatchContractError(f"schema must be {SCHEMA!r}")
    if value["authorization_repository"] != AUTHORIZATION_REPOSITORY:
        raise DispatchContractError("authorization repository mismatch")
    repository_id = _positive_int(
        value["authorization_repository_id"], "authorization_repository_id", 2**63 - 1
    )
    if repository_id != AUTHORIZATION_REPOSITORY_ID:
        raise DispatchContractError("authorization repository ID mismatch")
    issue_id = _positive_int(value["authorization_issue_id"], "authorization_issue_id", 2**63 - 1)
    issue_number = _positive_int(
        value["authorization_issue_number"], "authorization_issue_number", 2_147_483_647
    )
    request_id = value["request_id"]
    if type(request_id) is not str or UUID4_RE.fullmatch(request_id) is None:
        raise DispatchContractError("request_id must be canonical lowercase UUIDv4")
    try:
        parsed = uuid.UUID(request_id)
    except ValueError as exc:
        raise DispatchContractError("request_id must be canonical lowercase UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != request_id:
        raise DispatchContractError("request_id must be canonical lowercase UUIDv4")
    return DispatchRequest(
        authorization_repository=AUTHORIZATION_REPOSITORY,
        authorization_repository_id=repository_id,
        authorization_issue_id=issue_id,
        authorization_issue_number=issue_number,
        request_id=request_id,
    )
