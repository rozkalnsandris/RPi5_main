#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
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
SECRET_ROOT_PATH = Path("/etc/rpi5-secrets")
SECRET_DIR_PATH = SECRET_ROOT_PATH / "cloudflare"
ACCESS_SECRET_PATH = SECRET_DIR_PATH / "access-writer.json"
TUNNEL_SECRET_PATH = SECRET_DIR_PATH / "tunnel-writer.json"
RELEASE_METADATA_PATH = Path("/usr/local/libexec/rpi5-cloudflare/release.json")
CHECKOUT_PATH = Path("/home/andris/RPi5_main")
PHASE7_AUDIT_PATH = CHECKOUT_PATH / "scripts" / "ingress_drift_audit.py"
PYTHON = "/usr/bin/python3"
FIXED_RUNTIME_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EXPECTED_TUNNEL_NAME = "rpi5-tunnel"
CANONICAL_ORIGINS = {
    "git@github.com:rozkalnsandris/RPi5_main.git",
    "https://github.com/rozkalnsandris/RPi5_main.git",
}
ACCOUNT_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
CONFIRM_TEXT = "CREATE-COLORING-PUBLIC-BYPASS"
PROVISION_CONFIRM_TEXT = "PROVISION-CLOUDFLARE-ACCESS-SECRET"
TUNNEL_PROVISION_CONFIRM_TEXT = "PROVISION-CLOUDFLARE-TUNNEL-SECRET"
DYNAMIC_APP_FIELDS = {"created_at", "updated_at", "aud"}


class OperatorError(RuntimeError):
    pass


class WriteAttemptError(OperatorError):
    pass


class PostWriteError(OperatorError):
    pass


class SecretProvisionError(OperatorError):
    def __init__(self, reason: str, mutation_performed: bool) -> None:
        super().__init__(reason)
        self.mutation_performed = mutation_performed


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
        "provision_confirmation_missing",
        "local_tty_required",
        "token_inactive",
        "access_permission_check_failed",
        "tunnel_permission_check_failed",
        "phase7_checkout_invalid",
        "phase7_audit_failed",
        "secret_already_exists",
        "secret_parent_invalid",
        "secret_write_failed",
        "secret_post_write_verification_failed",
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


def _load_capability_credentials(path: Path) -> tuple[str, str]:
    decoded = _read_bounded_json(path, expected_mode=0o600)
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


def load_access_credentials() -> tuple[str, str]:
    return _load_capability_credentials(ACCESS_SECRET_PATH)


def load_tunnel_credentials() -> tuple[str, str]:
    return _load_capability_credentials(TUNNEL_SECRET_PATH)


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

    def verify_active_token(self) -> None:
        payload = self._request("GET", "/user/tokens/verify")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("status") != "active":
            raise OperatorError("token_inactive")

    def verify_access_permission(self, account_id: str) -> None:
        try:
            self._request(
                "GET", f"/accounts/{account_id}/access/apps?page=1&per_page=1"
            )
        except OperatorError as exc:
            raise OperatorError("access_permission_check_failed") from exc

    def verify_tunnel_permission(self, account_id: str) -> None:
        try:
            payload = self._request(
                "GET",
                f"/accounts/{account_id}/cfd_tunnel"
                f"?name={urllib.parse.quote(EXPECTED_TUNNEL_NAME)}"
                "&is_deleted=false&per_page=100",
            )
            result = payload.get("result")
            if not isinstance(result, list):
                raise OperatorError("tunnel_permission_check_failed")
            matches = [
                item
                for item in result
                if isinstance(item, dict)
                and item.get("name") == EXPECTED_TUNNEL_NAME
                and item.get("config_src") == "cloudflare"
            ]
            if len(matches) != 1:
                raise OperatorError("tunnel_permission_check_failed")
            tunnel_id = matches[0].get("id")
            if not isinstance(tunnel_id, str) or not UUID_RE.fullmatch(tunnel_id):
                raise OperatorError("tunnel_permission_check_failed")
            configuration = self._request(
                "GET",
                f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
            )
            config_result = configuration.get("result")
            if not isinstance(config_result, dict) or not isinstance(
                config_result.get("config"), dict
            ):
                raise OperatorError("tunnel_permission_check_failed")
        except OperatorError as exc:
            if str(exc) == "tunnel_permission_check_failed":
                raise
            raise OperatorError("tunnel_permission_check_failed") from exc

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


def _ensure_controlling_tty() -> None:
    flags = os.O_RDWR
    if hasattr(os, "O_NOCTTY"):
        flags |= os.O_NOCTTY
    try:
        fd = os.open("/dev/tty", flags)
    except OSError as exc:
        raise OperatorError("local_tty_required") from exc
    try:
        if not os.isatty(fd):
            raise OperatorError("local_tty_required")
    finally:
        os.close(fd)


def _hidden_getpass(prompt: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt).strip()
    except (
        OSError,
        EOFError,
        KeyboardInterrupt,
        getpass.GetPassWarning,
    ) as exc:
        raise OperatorError("local_tty_required") from exc


def _read_hidden_capability_credentials(token_prompt: str) -> tuple[str, str]:
    _ensure_controlling_tty()
    account_id = _hidden_getpass("Cloudflare account ID: ")
    token = _hidden_getpass(token_prompt)
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise OperatorError("secret_payload_invalid")
    if (
        len(token) < 20
        or len(token) > 4096
        or any(ch.isspace() for ch in token)
    ):
        raise OperatorError("secret_payload_invalid")
    return account_id, token


def _read_hidden_provisioning_credentials() -> tuple[str, str]:
    return _read_hidden_capability_credentials("Cloudflare Access API token: ")


def _read_hidden_tunnel_provisioning_credentials() -> tuple[str, str]:
    return _read_hidden_capability_credentials("Cloudflare Tunnel API token: ")


def _validate_secret_parent(path: Path) -> None:
    if not path.exists():
        return
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise OperatorError("secret_parent_invalid") from exc
    if (
        not stat.S_ISDIR(st.st_mode)
        or stat.S_ISLNK(st.st_mode)
        or st.st_uid != 0
        or st.st_gid != 0
        or stat.S_IMODE(st.st_mode) != 0o700
    ):
        raise OperatorError("secret_parent_invalid")


def _write_capability_secret(path: Path, account_id: str, token: str) -> None:
    if path.exists():
        raise OperatorError("secret_already_exists")
    _validate_secret_parent(SECRET_ROOT_PATH)
    _validate_secret_parent(SECRET_DIR_PATH)

    payload = (
        json.dumps(
            {"account_id": account_id, "api_token": token},
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    mutation_started = False
    fd: int | None = None
    try:
        for parent in (SECRET_ROOT_PATH, SECRET_DIR_PATH):
            if not parent.exists():
                os.mkdir(parent, 0o700)
                mutation_started = True
                _validate_secret_parent(parent)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        mutation_started = True
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None

        _validate_regular_root_file(path, 0o600)
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise SecretProvisionError(
                "secret_post_write_verification_failed", True
            ) from exc
        if observed != payload:
            raise SecretProvisionError(
                "secret_post_write_verification_failed", True
            )
    except SecretProvisionError:
        raise
    except (OSError, OperatorError) as exc:
        raise SecretProvisionError("secret_write_failed", mutation_started) from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _write_access_secret(account_id: str, token: str) -> None:
    _write_capability_secret(ACCESS_SECRET_PATH, account_id, token)


def _write_tunnel_secret(account_id: str, token: str) -> None:
    _write_capability_secret(TUNNEL_SECRET_PATH, account_id, token)


def provision_access_secret(
    client: CloudflareClient, account_id: str, token: str
) -> None:
    if ACCESS_SECRET_PATH.exists():
        raise OperatorError("secret_already_exists")
    client.verify_active_token()
    client.verify_access_permission(account_id)
    _write_access_secret(account_id, token)


def provision_tunnel_secret(
    client: CloudflareClient, account_id: str, token: str
) -> None:
    if TUNNEL_SECRET_PATH.exists():
        raise OperatorError("secret_already_exists")
    client.verify_active_token()
    client.verify_tunnel_permission(account_id)
    _write_tunnel_secret(account_id, token)


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


def _checkout_git(
    args: list[str],
    *,
    runner: Any = subprocess.run,
) -> subprocess.CompletedProcess[Any]:
    return runner(
        ["/usr/bin/git", "-C", str(CHECKOUT_PATH), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15,
    )


def verify_phase7_checkout(
    expected_main: str,
    *,
    runner: Any = subprocess.run,
) -> Path:
    if not SHA_RE.fullmatch(expected_main) or not CHECKOUT_PATH.is_dir():
        raise OperatorError("phase7_checkout_invalid")

    def read(args: list[str]) -> str:
        completed = _checkout_git(args, runner=runner)
        if completed.returncode != 0:
            raise OperatorError("phase7_checkout_invalid")
        return completed.stdout.strip()

    if Path(read(["rev-parse", "--show-toplevel"])).resolve() != CHECKOUT_PATH.resolve():
        raise OperatorError("phase7_checkout_invalid")
    if read(["branch", "--show-current"]) != "main":
        raise OperatorError("phase7_checkout_invalid")
    if read(["remote", "get-url", "origin"]) not in CANONICAL_ORIGINS:
        raise OperatorError("phase7_checkout_invalid")
    if read(["status", "--porcelain=v1", "--untracked-files=all"]):
        raise OperatorError("phase7_checkout_invalid")
    if read(["rev-parse", "HEAD"]) != expected_main:
        raise OperatorError("phase7_checkout_invalid")
    if read(["ls-files", "--error-unmatch", "scripts/ingress_drift_audit.py"]) != "scripts/ingress_drift_audit.py":
        raise OperatorError("phase7_checkout_invalid")
    try:
        st = os.lstat(PHASE7_AUDIT_PATH)
    except OSError as exc:
        raise OperatorError("phase7_checkout_invalid") from exc
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise OperatorError("phase7_checkout_invalid")
    return PHASE7_AUDIT_PATH


def run_phase7_audit(
    audit_path: Path,
    expected_main: str,
    account_id: str,
    token: str,
    *,
    runner: Any = subprocess.run,
) -> tuple[int, dict[str, Any]]:
    env = {
        "PATH": FIXED_RUNTIME_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "CLOUDFLARE_ACCOUNT_ID": account_id,
    }
    completed = runner(
        [PYTHON, str(audit_path), "--expected-main", expected_main],
        cwd=str(CHECKOUT_PATH),
        check=False,
        input=(token + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        timeout=120,
    )
    if completed.returncode not in {0, 2, 3}:
        raise OperatorError("phase7_audit_failed")
    raw = completed.stdout
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OperatorError("phase7_audit_failed") from exc
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OperatorError("phase7_audit_failed") from exc
    if (
        not isinstance(report, dict)
        or report.get("schema") != "rozkalns.rpi5-main.ingress-drift-audit-evidence.v1"
        or report.get("source_main_sha") != expected_main
        or report.get("mutation_performed") is not False
        or report.get("result") not in {"PASS", "DRIFT", "BLOCKED"}
    ):
        raise OperatorError("phase7_audit_failed")
    expected_rc = {"PASS": 0, "BLOCKED": 2, "DRIFT": 3}[report["result"]]
    if completed.returncode != expected_rc:
        raise OperatorError("phase7_audit_failed")
    return completed.returncode, report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    subparsers = parser.add_subparsers(dest="action", required=True)

    access = subparsers.add_parser("access-public-bypass")
    access.add_argument("hostname")
    access.add_argument("--expected-main", required=True)
    access.add_argument("--apply", action="store_true")
    access.add_argument("--confirm", default="")

    provision = subparsers.add_parser("provision-access-secret")
    provision.add_argument("--expected-main", required=True)
    provision.add_argument("--confirm", default="")

    tunnel = subparsers.add_parser("provision-tunnel-secret")
    tunnel.add_argument("--expected-main", required=True)
    tunnel.add_argument("--confirm", default="")

    phase7 = subparsers.add_parser("phase7-ingress-drift-audit")
    phase7.add_argument("--expected-main", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if os.geteuid() != 0:
        _emit("BLOCKED", reason="root_required", apply_ready=False)
        return 2

    operator_path = Path(sys.argv[0]).resolve()
    try:
        load_release_metadata(args.expected_main, operator_path)

        if args.action == "provision-access-secret":
            if args.confirm != PROVISION_CONFIRM_TEXT:
                raise OperatorError("provision_confirmation_missing")
            account_id, token = _read_hidden_provisioning_credentials()
            client = CloudflareClient(token)
            provision_access_secret(client, account_id, token)
            token = ""
            _emit(
                "PASS",
                mutation_performed=True,
                write_attempted=False,
                apply_ready=False,
            )
            return 0

        if args.action == "provision-tunnel-secret":
            if args.confirm != TUNNEL_PROVISION_CONFIRM_TEXT:
                raise OperatorError("provision_confirmation_missing")
            account_id, token = _read_hidden_tunnel_provisioning_credentials()
            client = CloudflareClient(token)
            provision_tunnel_secret(client, account_id, token)
            token = ""
            _emit(
                "PASS",
                mutation_performed=True,
                write_attempted=False,
                apply_ready=False,
            )
            return 0

        if args.action == "phase7-ingress-drift-audit":
            audit_path = verify_phase7_checkout(args.expected_main)
            account_id, token = load_tunnel_credentials()
            rc, report = run_phase7_audit(
                audit_path,
                args.expected_main,
                account_id,
                token,
            )
            token = ""
            print(json.dumps(report, indent=2, sort_keys=True))
            return rc

        if args.hostname != TARGET_HOSTNAME:
            raise OperatorError("hostname_not_allowlisted")
        if args.apply and args.confirm != CONFIRM_TEXT:
            raise OperatorError("apply_confirmation_missing")

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
    except SecretProvisionError as exc:
        _emit(
            "STOP_ERROR",
            reason=str(exc),
            mutation_performed=exc.mutation_performed,
            write_attempted=False,
            apply_ready=False,
        )
        return 6
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