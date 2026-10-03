#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

API_BASE = "https://api.cloudflare.com/client/v4"
REPOSITORY = "rozkalnsandris/RPi5_main"
TARGET_HOSTNAME = "coloring.rozkalns.net"
TARGET_APP_NAME = "Coloring Pages Public"
TARGET_POLICY_NAME = "public-access"
EXPECTED_PARENT_APP_NAME = "homelab-private"
EXPECTED_PARENT_PATTERN = "*.rozkalns.net"
ACCESS_SECRET_PATH = Path("/etc/rpi5-secrets/cloudflare/access-writer.json")
RELEASE_METADATA_PATH = Path("/usr/local/libexec/rpi5-cloudflare/release.json")
ACCOUNT_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
CONFIRM_TEXT = "CREATE-COLORING-PUBLIC-BYPASS"
DYNAMIC_APP_FIELDS = {"created_at", "updated_at", "aud"}


class OperatorError(RuntimeError):
    pass


class WriteAttemptError(OperatorError):
    pass


class PostWriteError(OperatorError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _sanitize_reason(value: str) -> str:
    allowed = {
        "root_required",
        "hostname_not_allowlisted",
        "expected_main_invalid",
        "release_metadata_invalid",
        "release_source_sha_mismatch",
        "release_operator_hash_mismatch",
        "secret_file_invalid",
        "secret_payload_invalid",
        "cloudflare_get_failed",
        "cloudflare_get_unsuccessful",
        "cloudflare_get_shape_invalid",
        "cloudflare_write_failed",
        "cloudflare_write_unsuccessful",
        "cloudflare_write_shape_invalid",
        "application_inventory_incomplete",
        "exact_target_application_already_exists",
        "parent_wildcard_missing_or_ambiguous",
        "parent_wildcard_identity_mismatch",
        "preexisting_application_missing_after_write",
        "preexisting_application_changed_after_write",
        "created_application_missing_or_ambiguous",
        "created_application_identity_mismatch",
        "created_application_policy_shape_invalid",
        "apply_confirmation_missing",
    }
    return value if value in allowed else "operator_error"


def _emit(
    result: str,
    *,
    reason: str | None = None,
    mutation_performed: bool | None = False,
    write_attempted: bool = False,
    apply_ready: bool | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "operator": "rpi5-cloudflare-access-operator-v1",
        "repository": REPOSITORY,
        "target_hostname": TARGET_HOSTNAME,
        "result": result,
        "write_attempted": write_attempted,
        "mutation_performed": mutation_performed,
        "privacy": {
            "account_id_emitted": False,
            "api_token_emitted": False,
            "application_id_emitted": False,
            "policy_id_emitted": False,
            "raw_cloudflare_payload_emitted": False,
        },
    }
    if apply_ready is not None:
        payload["apply_ready"] = apply_ready
    if reason:
        payload["reason"] = _sanitize_reason(reason)
    print(json.dumps(payload, indent=2, sort_keys=True))


def _validate_regular_root_file(path: Path, expected_mode: int) -> None:
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise OperatorError("secret_file_invalid") from exc
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise OperatorError("secret_file_invalid")
    if st.st_uid != 0 or st.st_gid != 0 or stat.S_IMODE(st.st_mode) != expected_mode:
        raise OperatorError("secret_file_invalid")


def _read_bounded_json(path: Path, *, expected_mode: int, max_bytes: int = 8192) -> dict[str, Any]:
    _validate_regular_root_file(path, expected_mode)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise OperatorError("secret_file_invalid") from exc
    if not data or len(data) > max_bytes:
        raise OperatorError("secret_file_invalid")
    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorError("secret_payload_invalid") from exc
    if not isinstance(decoded, dict):
        raise OperatorError("secret_payload_invalid")
    return decoded


def load_release_metadata(expected_main: str, operator_path: Path) -> dict[str, Any]:
    if not SHA_RE.fullmatch(expected_main):
        raise OperatorError("expected_main_invalid")
    metadata = _read_bounded_json(RELEASE_METADATA_PATH, expected_mode=0o400)
    if set(metadata) != {"schema_version", "repository", "source_sha", "operator_sha256"}:
        raise OperatorError("release_metadata_invalid")
    if metadata.get("schema_version") != 1 or metadata.get("repository") != REPOSITORY:
        raise OperatorError("release_metadata_invalid")
    source_sha = metadata.get("source_sha")
    operator_sha = metadata.get("operator_sha256")
    if source_sha != expected_main:
        raise OperatorError("release_source_sha_mismatch")
    if not isinstance(operator_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", operator_sha):
        raise OperatorError("release_metadata_invalid")
    try:
        actual = hashlib.sha256(operator_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OperatorError("release_metadata_invalid") from exc
    if actual != operator_sha:
        raise OperatorError("release_operator_hash_mismatch")
    return metadata


def load_access_credentials() -> tuple[str, str]:
    decoded = _read_bounded_json(ACCESS_SECRET_PATH, expected_mode=0o600)
    if set(decoded) != {"account_id", "api_token"}:
        raise OperatorError("secret_payload_invalid")
    account_id = decoded.get("account_id")
    api_token = decoded.get("api_token")
    if not isinstance(account_id, str) or not ACCOUNT_ID_RE.fullmatch(account_id):
        raise OperatorError("secret_payload_invalid")
    if (
        not isinstance(api_token, str)
        or len(api_token) < 20
        or len(api_token) > 4096
        or any(ch.isspace() for ch in api_token)
    ):
        raise OperatorError("secret_payload_invalid")
    return account_id, api_token


class CloudflareClient:
    def __init__(self, api_token: str, timeout: int = 20, opener: Any | None = None) -> None:
        if len(api_token) < 20 or any(ch.isspace() for ch in api_token):
            raise OperatorError("secret_payload_invalid")
        self._token = api_token
        self._timeout = timeout
        self._opener = opener or urllib.request.build_opener(NoRedirect)

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(
            body, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "rpi5-main-cloudflare-rdc-operator-v1",
            },
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
        ) as exc:
            if method == "POST":
                raise WriteAttemptError("cloudflare_write_failed") from exc
            raise OperatorError("cloudflare_get_failed") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            if method == "POST":
                raise WriteAttemptError("cloudflare_write_shape_invalid") from exc
            raise OperatorError("cloudflare_get_shape_invalid") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            if method == "POST":
                raise WriteAttemptError("cloudflare_write_unsuccessful")
            raise OperatorError("cloudflare_get_unsuccessful")
        return payload

    def list_applications(self, account_id: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET", f"/accounts/{account_id}/access/apps?page=1&per_page=200"
        )
        result = payload.get("result")
        if not isinstance(result, list) or any(
            not isinstance(item, dict) for item in result
        ):
            raise OperatorError("cloudflare_get_shape_invalid")
        info = payload.get("result_info")
        if isinstance(info, dict):
            total_pages = info.get("total_pages", 1)
            if not isinstance(total_pages, int) or total_pages != 1:
                raise OperatorError("application_inventory_incomplete")
        elif len(result) >= 200:
            raise OperatorError("application_inventory_incomplete")
        return result

    def list_application_policies(
        self, account_id: str, app_id: str
    ) -> list[dict[str, Any]]:
        if not UUID_RE.fullmatch(app_id):
            raise OperatorError("cloudflare_get_shape_invalid")
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/access/apps/{app_id}/policies?page=1&per_page=50",
        )
        result = payload.get("result")
        if not isinstance(result, list) or any(
            not isinstance(item, dict) for item in result
        ):
            raise OperatorError("cloudflare_get_shape_invalid")
        info = payload.get("result_info")
        if isinstance(info, dict):
            total_pages = info.get("total_pages", 1)
            if not isinstance(total_pages, int) or total_pages != 1:
                raise OperatorError("application_inventory_incomplete")
        elif len(result) >= 50:
            raise OperatorError("application_inventory_incomplete")
        return result

    def create_application(
        self, account_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        payload = self._request(
            "POST", f"/accounts/{account_id}/access/apps", body
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise WriteAttemptError("cloudflare_write_shape_invalid")
        return result


def _split_destination(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    return (parsed.hostname or "").casefold(), parsed.path or ""


def _root_destination(path: str) -> bool:
    return path in {"", "/", "/*"}


def _application_destinations(app: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[str] = []
    domain = app.get("domain")
    if isinstance(domain, str) and domain.strip():
        values.append(domain.strip())
    legacy = app.get("self_hosted_domains")
    if isinstance(legacy, list):
        values.extend(
            item for item in legacy if isinstance(item, str) and item.strip()
        )
    destinations = app.get("destinations")
    if isinstance(destinations, list):
        for item in destinations:
            if isinstance(item, dict):
                uri = item.get("uri")
                if isinstance(uri, str) and uri.strip():
                    values.append(uri.strip())
    return list(dict.fromkeys(_split_destination(value) for value in values))


def _matches_hostname(app: dict[str, Any], hostname: str) -> bool:
    return any(
        host == hostname.casefold()
        for host, _path in _application_destinations(app)
    )


def _matches_root(app: dict[str, Any], hostname: str) -> bool:
    return any(
        host == hostname.casefold() and _root_destination(path)
        for host, path in _application_destinations(app)
    )


def _stable_app_projection(app: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(app)
    for key in DYNAMIC_APP_FIELDS:
        projected.pop(key, None)
    return projected


def preflight_applications(apps: list[dict[str, Any]]) -> dict[str, Any]:
    exact = [app for app in apps if _matches_hostname(app, TARGET_HOSTNAME)]
    if exact:
        raise OperatorError("exact_target_application_already_exists")
    parents = [
        app for app in apps if _matches_root(app, EXPECTED_PARENT_PATTERN)
    ]
    if len(parents) != 1:
        raise OperatorError("parent_wildcard_missing_or_ambiguous")
    parent = parents[0]
    if (
        parent.get("name") != EXPECTED_PARENT_APP_NAME
        or parent.get("type") != "self_hosted"
    ):
        raise OperatorError("parent_wildcard_identity_mismatch")
    projection: dict[str, dict[str, Any]] = {}
    for app in apps:
        app_id = app.get("id")
        if isinstance(app_id, str) and UUID_RE.fullmatch(app_id):
            projection[app_id] = _stable_app_projection(app)
    return {
        "parent_wildcard_present": True,
        "exact_target_absent": True,
        "preexisting_apps": projection,
    }


def build_create_body() -> dict[str, Any]:
    return {
        "name": TARGET_APP_NAME,
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": TARGET_HOSTNAME}],
        "policies": [
            {
                "name": TARGET_POLICY_NAME,
                "decision": "bypass",
                "include": [{"everyone": {}}],
            }
        ],
    }


def _policy_is_exact_public_bypass(policy: dict[str, Any]) -> bool:
    return (
        policy.get("name") == TARGET_POLICY_NAME
        and policy.get("decision", policy.get("action")) == "bypass"
        and policy.get("include") == [{"everyone": {}}]
        and policy.get("require", []) == []
        and policy.get("exclude", []) == []
    )


def verify_post_write(
    before: dict[str, Any],
    apps_after: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    created_app_id: str,
) -> dict[str, bool]:
    after_by_id = {
        app.get("id"): app
        for app in apps_after
        if isinstance(app.get("id"), str) and UUID_RE.fullmatch(app["id"])
    }
    for app_id, projection in before["preexisting_apps"].items():
        if app_id not in after_by_id:
            raise OperatorError("preexisting_application_missing_after_write")
        if _stable_app_projection(after_by_id[app_id]) != projection:
            raise OperatorError("preexisting_application_changed_after_write")

    exact = [app for app in apps_after if _matches_root(app, TARGET_HOSTNAME)]
    if len(exact) != 1:
        raise OperatorError("created_application_missing_or_ambiguous")
    app = exact[0]
    if (
        app.get("id") != created_app_id
        or app.get("name") != TARGET_APP_NAME
        or app.get("type") != "self_hosted"
    ):
        raise OperatorError("created_application_identity_mismatch")
    if len(policies) != 1 or not _policy_is_exact_public_bypass(policies[0]):
        raise OperatorError("created_application_policy_shape_invalid")
    return {
        "exact_application_present": True,
        "single_bypass_everyone_policy": True,
        "preexisting_applications_unchanged": True,
    }


def run_operator(
    client: CloudflareClient, account_id: str, *, apply: bool
) -> dict[str, Any]:
    apps_before = client.list_applications(account_id)
    before = preflight_applications(apps_before)
    if not apply:
        return {
            "result": "PASS",
            "apply_ready": True,
            "mutation_performed": False,
        }

    created = client.create_application(account_id, build_create_body())
    created_id = created.get("id")
    if not isinstance(created_id, str) or not UUID_RE.fullmatch(created_id):
        raise PostWriteError("cloudflare_write_shape_invalid")

    try:
        apps_after = client.list_applications(account_id)
        policies = client.list_application_policies(account_id, created_id)
        verification = verify_post_write(
            before, apps_after, policies, created_id
        )
    except OperatorError as exc:
        raise PostWriteError(str(exc)) from exc
    return {
        "result": "PASS",
        "apply_ready": False,
        "mutation_performed": True,
        "verification": verification,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("action", choices=["access-public-bypass"])
    parser.add_argument("hostname")
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if os.geteuid() != 0:
        _emit("BLOCKED", reason="root_required", apply_ready=False)
        return 2
    if args.hostname != TARGET_HOSTNAME:
        _emit(
            "BLOCKED",
            reason="hostname_not_allowlisted",
            apply_ready=False,
        )
        return 2
    if args.apply and args.confirm != CONFIRM_TEXT:
        _emit(
            "BLOCKED",
            reason="apply_confirmation_missing",
            apply_ready=False,
        )
        return 2

    operator_path = Path(sys.argv[0]).resolve()
    try:
        load_release_metadata(args.expected_main, operator_path)
        account_id, token = load_access_credentials()
        client = CloudflareClient(token)
        token = ""
        result = run_operator(client, account_id, apply=args.apply)
    except WriteAttemptError as exc:
        _emit(
            "STOP_ERROR",
            reason=str(exc),
            mutation_performed=None,
            write_attempted=True,
            apply_ready=False,
        )
        return 4
    except PostWriteError as exc:
        _emit(
            "STOP_ERROR",
            reason=str(exc),
            mutation_performed=True,
            write_attempted=True,
            apply_ready=False,
        )
        return 5
    except OperatorError as exc:
        _emit(
            "BLOCKED",
            reason=str(exc),
            mutation_performed=False,
            write_attempted=False,
            apply_ready=False,
        )
        return 3

    _emit(
        "PASS",
        mutation_performed=bool(result["mutation_performed"]),
        write_attempted=bool(args.apply),
        apply_ready=bool(result["apply_ready"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
