from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

AUTHORIZATION_REPOSITORY = "rozkalnsandris/ops-workflows"
AUTHORIZATION_REPOSITORY_ID = 1328835922
OWNER_USER_ID = 277435981
LIVE_AUTH_SCHEMA = "rozkalns.live-auth.v1"
TTL_SECONDS = 600
MAX_FUTURE_SKEW_SECONDS = 30
MAX_BODY_BYTES = 16 * 1024

START_MARKER = "<!-- rozkalns-live-auth:v1 -->"
END_MARKER = "<!-- /rozkalns-live-auth:v1 -->"
PAYLOAD_RE = re.compile(
    re.escape(START_MARKER)
    + r"\n```json\n(?P<payload>.*?)\n```\n"
    + re.escape(END_MARKER),
    re.DOTALL,
)
TITLE_RE = re.compile(r"^\[LIVE-AUTH\]\[PENDING\] (?P<target>[a-z0-9][a-z0-9._-]{0,63})$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ROLLBACK_POLICIES = frozenset({"NONE", "BUILTIN_TRANSACTIONAL_V1"})

PAYLOAD_FIELDS = frozenset(
    {
        "schema",
        "request_id",
        "queue_repository",
        "queue_issue",
        "source_repository",
        "source_sha",
        "target_alias",
        "operation_id",
        "expected_baseline",
        "mutation_budget",
        "rollback_policy",
        "exclusions",
        "dependencies",
    }
)
BASELINE_FIELDS = frozenset({"kind", "value"})
BUDGET_FIELDS = frozenset({"category", "max_operations"})


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AcceptedAuthorization:
    repository_id: int
    repository_full_name: str
    issue_id: int
    issue_number: int
    request_id: str
    created_at: datetime
    target_alias: str
    canonical_payload_json: str
    canonical_payload_sha256: str
    raw_body_sha256: str
    performed_via_github_app_id: int | None
    performed_via_github_app_slug: str | None

    @property
    def payload(self) -> Mapping[str, Any]:
        # Return a fresh object so caller mutation cannot alter accepted authority.
        return _parse_json_strict(self.canonical_payload_json)


def _fail(code: str, message: str) -> None:
    raise ProtocolError(code, message)


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("INVALID_JSON_NUMBER", f"non-finite JSON number {value!r} is forbidden")


def _parse_json_strict(raw: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except ProtocolError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _fail("MALFORMED_JSON", str(exc))
    if type(value) is not dict:
        _fail("MALFORMED_SCHEMA", "payload root must be an object")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], where: str) -> None:
    actual = frozenset(value.keys())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail("MALFORMED_SCHEMA", f"{where} keys mismatch; missing={missing}, extra={extra}")


def _require_string(value: Any, where: str, max_len: int, *, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str:
        _fail("MALFORMED_SCHEMA", f"{where} must be a string")
    if not value or len(value) > max_len:
        _fail("MALFORMED_SCHEMA", f"{where} length is invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail("INVALID_UNICODE", f"{where} contains invalid Unicode")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail("MALFORMED_SCHEMA", f"{where} format is invalid")
    return value


def _parse_rfc3339_utc(value: Any, where: str) -> datetime:
    text = _require_string(value, where, 40)
    if not text.endswith("Z"):
        _fail("MALFORMED_TIMESTAMP", f"{where} must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        _fail("MALFORMED_TIMESTAMP", f"{where}: {exc}")
    if parsed.tzinfo is None:
        _fail("MALFORMED_TIMESTAMP", f"{where} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_uuid4(value: Any) -> str:
    text = _require_string(value, "request_id", 36)
    try:
        parsed = uuid.UUID(text)
    except ValueError:
        _fail("MALFORMED_SCHEMA", "request_id must be canonical UUIDv4")
    if parsed.version != 4 or str(parsed) != text:
        _fail("MALFORMED_SCHEMA", "request_id must be canonical lowercase UUIDv4")
    return text


def _parse_positive_int(value: Any, where: str, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        _fail("MALFORMED_SCHEMA", f"{where} must be an integer in range 1..{maximum}")
    return value


def _validate_public_string_list(value: Any, where: str) -> list[str]:
    if type(value) is not list or len(value) > 32:
        _fail("MALFORMED_SCHEMA", f"{where} must be a list with at most 32 entries")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_string(item, f"{where}[{index}]", 256))
    return result


def _validate_baseline(value: Any, where: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("MALFORMED_SCHEMA", f"{where} must be an object")
    _require_exact_keys(value, BASELINE_FIELDS, where)
    _require_string(value["kind"], f"{where}.kind", 64, pattern=IDENTIFIER_RE)
    _require_string(value["value"], f"{where}.value", 512)
    return value


def _validate_mutation_budget(value: Any, where: str) -> list[Mapping[str, Any]]:
    if type(value) is not list or not value or len(value) > 16:
        _fail("MALFORMED_SCHEMA", f"{where} must contain 1..16 entries")
    seen_categories: set[str] = set()
    for index, budget in enumerate(value):
        item_where = f"{where}[{index}]"
        if type(budget) is not dict:
            _fail("MALFORMED_SCHEMA", f"{item_where} must be an object")
        _require_exact_keys(budget, BUDGET_FIELDS, item_where)
        category = _require_string(
            budget["category"], f"{item_where}.category", 128, pattern=IDENTIFIER_RE
        )
        if category in seen_categories:
            _fail("MALFORMED_SCHEMA", f"duplicate mutation category {category!r}")
        seen_categories.add(category)
        _parse_positive_int(budget["max_operations"], f"{item_where}.max_operations", maximum=100)
    return value


def _validate_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_exact_keys(payload, PAYLOAD_FIELDS, "payload")

    if payload["schema"] != LIVE_AUTH_SCHEMA:
        _fail("UNSUPPORTED_SCHEMA", f"schema must be {LIVE_AUTH_SCHEMA!r}")

    _parse_uuid4(payload["request_id"])

    queue_repository = _require_string(payload["queue_repository"], "queue_repository", 201, pattern=REPOSITORY_RE)
    if queue_repository != AUTHORIZATION_REPOSITORY:
        _fail("WRONG_QUEUE_REPOSITORY", f"queue_repository must be {AUTHORIZATION_REPOSITORY!r}")

    _parse_positive_int(payload["queue_issue"], "queue_issue", maximum=2_147_483_647)
    _require_string(payload["source_repository"], "source_repository", 201, pattern=REPOSITORY_RE)
    _require_string(payload["source_sha"], "source_sha", 40, pattern=SHA_RE)
    _require_string(payload["target_alias"], "target_alias", 64, pattern=IDENTIFIER_RE)
    _require_string(payload["operation_id"], "operation_id", 128, pattern=IDENTIFIER_RE)

    _validate_baseline(payload["expected_baseline"], "expected_baseline")
    _validate_mutation_budget(payload["mutation_budget"], "mutation_budget")

    rollback_policy = _require_string(payload["rollback_policy"], "rollback_policy", 64)
    if rollback_policy not in ROLLBACK_POLICIES:
        _fail("UNSUPPORTED_ROLLBACK_POLICY", rollback_policy)

    _validate_public_string_list(payload["exclusions"], "exclusions")
    _validate_public_string_list(payload["dependencies"], "dependencies")

    return payload


def canonicalize_payload(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        _fail("CANONICALIZATION_ERROR", str(exc))


def _extract_payload(body: Any) -> tuple[Mapping[str, Any], str]:
    text = _require_string(body, "issue.body", MAX_BODY_BYTES)
    encoded = text.encode("utf-8", "strict")
    if len(encoded) > MAX_BODY_BYTES:
        _fail("BODY_TOO_LARGE", f"issue body exceeds {MAX_BODY_BYTES} bytes")
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        _fail("AUTHORITY_BLOCK_COUNT", "exactly one LIVE-AUTH authority block is required")
    match = PAYLOAD_RE.search(text)
    if match is None:
        _fail("MALFORMED_AUTHORITY_BLOCK", "LIVE-AUTH markers/fence are malformed")
    payload = _validate_payload(_parse_json_strict(match.group("payload")))
    return payload, text


def _validate_issue_shape(issue: Mapping[str, Any], repository_full_name: str) -> tuple[int, int, datetime, str]:
    if type(issue) is not dict:
        _fail("MALFORMED_ISSUE", "issue must be an object")
    if repository_full_name != AUTHORIZATION_REPOSITORY:
        _fail("WRONG_AUTHORIZATION_REPOSITORY", repository_full_name)

    if "pull_request" in issue and issue["pull_request"] is not None:
        _fail("PULL_REQUEST_FORBIDDEN", "LIVE-AUTH must be an Issue, not a pull request")
    if issue.get("state") != "open":
        _fail("ISSUE_NOT_OPEN", "LIVE-AUTH issue must be open")

    issue_id = _parse_positive_int(issue.get("id"), "issue.id", maximum=2**63 - 1)
    issue_number = _parse_positive_int(issue.get("number"), "issue.number", maximum=2_147_483_647)
    created_at = _parse_rfc3339_utc(issue.get("created_at"), "issue.created_at")

    user = issue.get("user")
    if type(user) is not dict:
        _fail("MALFORMED_ISSUE", "issue.user must be an object")
    if user.get("id") != OWNER_USER_ID:
        _fail("WRONG_OWNER", "issue author numeric GitHub ID does not match configured owner")
    if user.get("type") != "User":
        _fail("BOT_AUTHOR_REJECTED", "issue author must be GitHub type=User")

    title = _require_string(issue.get("title"), "issue.title", 160)
    title_match = TITLE_RE.fullmatch(title)
    if title_match is None:
        _fail("MALFORMED_TITLE", "issue title does not match LIVE-AUTH v1")
    return issue_id, issue_number, created_at, title_match.group("target")


def _validate_server_time(created_at: datetime, server_time: datetime) -> None:
    if not isinstance(server_time, datetime) or server_time.tzinfo is None:
        _fail("SERVER_TIME_UNAVAILABLE", "server_time must be a timezone-aware datetime")
    now = server_time.astimezone(timezone.utc)
    age = (now - created_at).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS:
        _fail("SERVER_TIME_SKEW", "authorization creation time is too far in the future")
    if age > TTL_SECONDS:
        _fail("AUTH_EXPIRED", f"authorization age {age:.0f}s exceeds {TTL_SECONDS}s TTL")


def accept_issue(
    issue: Mapping[str, Any],
    *,
    repository_id: int,
    repository_full_name: str,
    server_time: datetime,
    governance_ok: bool,
    approved_operator_app_ids: frozenset[int] = frozenset(),
) -> AcceptedAuthorization:
    if type(repository_id) is not int or repository_id < 1:
        _fail("MALFORMED_REPOSITORY_ID", "repository_id must be a positive integer")
    if repository_id != AUTHORIZATION_REPOSITORY_ID:
        _fail(
            "WRONG_AUTHORIZATION_REPOSITORY_ID",
            f"repository_id must be {AUTHORIZATION_REPOSITORY_ID}",
        )
    if governance_ok is not True:
        _fail("GOVERNANCE_UNTRUSTED", "authorization surface is not in a reviewed trusted state")

    issue_id, issue_number, created_at, title_target = _validate_issue_shape(issue, repository_full_name)
    _validate_server_time(created_at, server_time)
    payload, raw_body = _extract_payload(issue.get("body"))

    if payload["target_alias"] != title_target:
        _fail("TITLE_TARGET_MISMATCH", "title target alias does not match payload target_alias")

    canonical = canonicalize_payload(payload)
    app = issue.get("performed_via_github_app")
    app_id: int | None = None
    app_slug: str | None = None
    if app is not None:
        if type(app) is not dict:
            _fail("MALFORMED_ISSUE", "performed_via_github_app must be an object or null")
        app_id = _parse_positive_int(
            app.get("id"), "performed_via_github_app.id", maximum=2**63 - 1
        )
        if app_id not in approved_operator_app_ids:
            _fail(
                "UNAPPROVED_OPERATOR_INTEGRATION",
                f"performed_via_github_app.id {app_id} is not in the reviewed owner-operator trust set",
            )
        slug = app.get("slug")
        if slug is not None:
            app_slug = _require_string(slug, "performed_via_github_app.slug", 128)

    return AcceptedAuthorization(
        repository_id=repository_id,
        repository_full_name=repository_full_name,
        issue_id=issue_id,
        issue_number=issue_number,
        request_id=payload["request_id"],
        created_at=created_at,
        target_alias=payload["target_alias"],
        canonical_payload_json=canonical.decode("utf-8"),
        canonical_payload_sha256=hashlib.sha256(canonical).hexdigest(),
        raw_body_sha256=hashlib.sha256(raw_body.encode("utf-8", "strict")).hexdigest(),
        performed_via_github_app_id=app_id,
        performed_via_github_app_slug=app_slug,
    )


def validate_queue_binding(auth: AcceptedAuthorization, queue: Mapping[str, Any]) -> None:
    if type(queue) is not dict:
        _fail("MALFORMED_QUEUE", "queue fixture must be an object")
    expected_fields = frozenset(
        {
            "repository",
            "issue_number",
            "state",
            "source_repository",
            "source_sha",
            "target_alias",
            "operation_id",
            "expected_baseline",
            "mutation_budget",
            "rollback_policy",
            "exclusions",
            "dependencies",
        }
    )
    _require_exact_keys(queue, expected_fields, "queue")

    repository = _require_string(queue["repository"], "queue.repository", 201, pattern=REPOSITORY_RE)
    issue_number = _parse_positive_int(queue["issue_number"], "queue.issue_number", maximum=2_147_483_647)
    state = _require_string(queue["state"], "queue.state", 32)
    if state != "READY":
        _fail("QUEUE_NOT_READY", "referenced deploy queue is not READY")
    source_repository = _require_string(
        queue["source_repository"], "queue.source_repository", 201, pattern=REPOSITORY_RE
    )
    source_sha = _require_string(queue["source_sha"], "queue.source_sha", 40, pattern=SHA_RE)
    target_alias = _require_string(
        queue["target_alias"], "queue.target_alias", 64, pattern=IDENTIFIER_RE
    )
    operation_id = _require_string(
        queue["operation_id"], "queue.operation_id", 128, pattern=IDENTIFIER_RE
    )
    baseline = _validate_baseline(queue["expected_baseline"], "queue.expected_baseline")
    mutation_budget = _validate_mutation_budget(queue["mutation_budget"], "queue.mutation_budget")
    rollback_policy = _require_string(queue["rollback_policy"], "queue.rollback_policy", 64)
    if rollback_policy not in ROLLBACK_POLICIES:
        _fail("UNSUPPORTED_ROLLBACK_POLICY", rollback_policy)
    exclusions = _validate_public_string_list(queue["exclusions"], "queue.exclusions")
    dependencies = _validate_public_string_list(queue["dependencies"], "queue.dependencies")

    payload = auth.payload
    comparisons = {
        "repository": (repository, payload["queue_repository"]),
        "issue_number": (issue_number, payload["queue_issue"]),
        "source_repository": (source_repository, payload["source_repository"]),
        "source_sha": (source_sha, payload["source_sha"]),
        "target_alias": (target_alias, payload["target_alias"]),
        "operation_id": (operation_id, payload["operation_id"]),
        "expected_baseline": (baseline, payload["expected_baseline"]),
        "mutation_budget": (mutation_budget, payload["mutation_budget"]),
        "rollback_policy": (rollback_policy, payload["rollback_policy"]),
        "exclusions": (exclusions, payload["exclusions"]),
        "dependencies": (dependencies, payload["dependencies"]),
    }
    for key, (actual, expected) in comparisons.items():
        if actual != expected:
            _fail("QUEUE_BINDING_MISMATCH", f"{key} mismatch")


def verify_authorization_unchanged(
    accepted: AcceptedAuthorization,
    current_issue: Mapping[str, Any],
    *,
    server_time: datetime,
    governance_ok: bool,
    approved_operator_app_ids: frozenset[int] = frozenset(),
) -> None:
    current = accept_issue(
        current_issue,
        repository_id=accepted.repository_id,
        repository_full_name=accepted.repository_full_name,
        server_time=server_time,
        governance_ok=governance_ok,
        approved_operator_app_ids=approved_operator_app_ids,
    )
    if current.issue_id != accepted.issue_id or current.issue_number != accepted.issue_number:
        _fail("AUTHORITY_IDENTITY_DRIFT", "GitHub issue identity changed")
    if current.request_id != accepted.request_id:
        _fail("AUTHORITY_IDENTITY_DRIFT", "request_id changed")
    if current.canonical_payload_sha256 != accepted.canonical_payload_sha256:
        _fail("CANONICAL_PAYLOAD_DRIFT", "canonical payload digest changed")
    if current.raw_body_sha256 != accepted.raw_body_sha256:
        _fail("RAW_BODY_DRIFT", "raw issue body digest changed")
