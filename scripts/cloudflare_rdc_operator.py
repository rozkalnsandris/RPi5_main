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
DNS_SECRET_PATH = SECRET_DIR_PATH / "dns-writer.json"
AUSMALWIESE_ZONE = "ausmalwiese.de"
AUSMALWIESE_NAMES = ("ausmalwiese.de", "www.ausmalwiese.de")
RELEASE_METADATA_PATH = Path("/usr/local/libexec/rpi5-cloudflare/release.json")
PYTHON = "/usr/bin/python3"
FIXED_RUNTIME_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EXPECTED_TUNNEL_NAME = "rpi5-tunnel"
CANONICAL_ORIGINS = {
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
DNS_PROVISION_CONFIRM_TEXT = "PROVISION-AUSMALWIESE-DNS-SECRET"
DNS_APPLY_CONFIRM_TEXT = "CREATE-AUSMALWIESE-CNAME"
GSC_TXT_APPLY_CONFIRM_TEXT = "CREATE-AUSMALWIESE-GSC-TXT"
GSC_TXT_CONTENT = "google-site-verification=CZx413pYLeISdNsik5g5cUSkztdsYyHCOUg2dASib7M"
TUNNEL_APPLY_CONFIRM_TEXT = "ADD-AUSMALWIESE-TUNNEL-ROUTES"
ADMIN_HOSTNAME = "admin.ausmalwiese.de"
ADMIN_APP_NAME = "Ausmalwiese Admin"
ADMIN_POLICY_NAME = "owner-only"
ADMIN_TEMPLATE_HOSTNAME = "dash.rozkalns.net"
ADMIN_ORIGIN = "http://127.0.0.1:8765"
ADMIN_ACCESS_CONFIRM_TEXT = "CREATE-AUSMALWIESE-ADMIN-ACCESS"
ADMIN_TUNNEL_CONFIRM_TEXT = "ADD-AUSMALWIESE-ADMIN-TUNNEL"
ADMIN_DNS_CONFIRM_TEXT = "CREATE-AUSMALWIESE-ADMIN-CNAME"
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
        "dns_zone_invalid",
        "dns_records_incomplete",
        "dns_record_conflict",
        "tunnel_configuration_invalid",
        "tunnel_route_conflict",
        "baseline_mismatch",
        "dns_permission_check_failed",
        "phase7_checkout_invalid",
        "phase7_audit_failed",
        "secret_already_exists",
        "secret_parent_invalid",
        "secret_write_failed",
        "secret_post_write_verification_failed",
        "account_binding_mismatch",
        "admin_template_missing_or_ambiguous",
        "admin_template_policy_invalid",
        "admin_target_application_already_exists",
        "admin_target_application_missing_or_ambiguous",
        "admin_access_binding_invalid",
        "admin_tunnel_route_conflict",
        "admin_tunnel_route_invalid",
    }
    return value if value in allowed else "operator_error"


def _emit(
    result: str,
    *,
    reason: str | None = None,
    mutation_performed: bool | None = False,
    write_attempted: bool = False,
    apply_ready: bool | None = None,
    target_hostname: str = TARGET_HOSTNAME,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "operator": "rpi5-cloudflare-access-operator-v1",
        "repository": REPOSITORY,
        "target_hostname": target_hostname,
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
    legacy_keys = {"schema_version", "repository", "source_sha", "operator_sha256"}
    new_keys = legacy_keys | {"checkout_path"}
    if set(metadata) not in (legacy_keys, new_keys):
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
    checkout_path = metadata.get("checkout_path")
    if checkout_path is not None and (
        not isinstance(checkout_path, str)
        or not os.path.isabs(checkout_path)
        or len(checkout_path) > 4096
        or any(ch in checkout_path for ch in ("\x00", "\n", "\r"))
    ):
        raise OperatorError("release_metadata_invalid")
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


def load_dns_credentials() -> tuple[str, str]:
    raw = _read_bounded_json(DNS_SECRET_PATH, expected_mode=0o600)
    if set(raw) != {"zone_id", "zone_name", "api_token"}:
        raise OperatorError("secret_payload_invalid")
    zone_id, token = raw["zone_id"], raw["api_token"]
    if (raw["zone_name"] != AUSMALWIESE_ZONE
        or not isinstance(zone_id, str) or not ACCOUNT_ID_RE.fullmatch(zone_id)
        or not isinstance(token, str) or not 20 <= len(token) <= 4096
        or any(ch.isspace() for ch in token)):
        raise OperatorError("secret_payload_invalid")
    return zone_id, token


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
            if method in ("POST", "PUT"):
                raise WriteAttemptError("cloudflare_write_failed") from exc
            raise OperatorError("cloudflare_get_failed") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            if method in ("POST", "PUT"):
                raise WriteAttemptError("cloudflare_write_shape_invalid") from exc
            raise OperatorError("cloudflare_get_shape_invalid") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            if method in ("POST", "PUT"):
                raise WriteAttemptError("cloudflare_write_unsuccessful")
            raise OperatorError("cloudflare_get_unsuccessful")
        return payload

    def verify_active_token(self) -> None:
        payload = self._request("GET", "/user/tokens/verify")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("status") != "active":
            raise OperatorError("token_inactive")

    def verify_active_account_token(self, account_id: str) -> None:
        if not isinstance(account_id, str) or not ACCOUNT_ID_RE.fullmatch(account_id):
            raise OperatorError("secret_payload_invalid")
        payload = self._request(
            "GET",
            f"/accounts/{account_id}/tokens/verify",
        )
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


def _read_hidden_dns_credentials() -> tuple[str, str]:
    _ensure_controlling_tty()
    zone_id = _hidden_getpass("Cloudflare ausmalwiese.de zone ID: ")
    token = _hidden_getpass("Cloudflare ausmalwiese.de DNS API token: ")
    if (not ACCOUNT_ID_RE.fullmatch(zone_id) or not 20 <= len(token) <= 4096
        or any(ch.isspace() for ch in token)):
        raise OperatorError("secret_payload_invalid")
    return zone_id, token


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
    client.verify_active_account_token(account_id)
    client.verify_tunnel_permission(account_id)
    _write_tunnel_secret(account_id, token)



def _ausmalwiese_zone(client: CloudflareClient, zone_id: str) -> dict[str, Any]:
    data = client._request("GET", f"/zones/{zone_id}").get("result")
    if (not isinstance(data, dict) or data.get("id") != zone_id
        or data.get("name") != AUSMALWIESE_ZONE or data.get("status") != "active"
        or not isinstance(data.get("account"), dict)
        or not isinstance(data.get("plan"), dict)
        or str(data["plan"].get("legacy_id", "")).lower() != "free"):
        raise OperatorError("dns_zone_invalid")
    return data


def _ausmalwiese_records(client: CloudflareClient, zone_id: str) -> list[dict[str, Any]]:
    data = client._request("GET", f"/zones/{zone_id}/dns_records?page=1&per_page=100")
    rows, info = data.get("result"), data.get("result_info")
    if (not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows)
        or not isinstance(info, dict) or info.get("total_pages") != 1):
        raise OperatorError("dns_records_incomplete")
    return rows


def _rpi5_tunnel(client: CloudflareClient, account_id: str) -> tuple[str, dict[str, Any]]:
    data = client._request("GET", f"/accounts/{account_id}/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100").get("result")
    matches = [r for r in data if isinstance(r, dict)
               and r.get("name") == EXPECTED_TUNNEL_NAME and r.get("config_src") == "cloudflare"] if isinstance(data, list) else []
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not UUID_RE.fullmatch(matches[0]["id"]):
        raise OperatorError("tunnel_configuration_invalid")
    tunnel_id = matches[0]["id"]
    response = client._request("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations").get("result")
    if not isinstance(response, dict) or not isinstance(response.get("config"), dict):
        raise OperatorError("tunnel_configuration_invalid")
    return tunnel_id, response["config"]


def _prepared_tunnel_config(config: dict[str, Any]) -> dict[str, Any]:
    rules = config.get("ingress")
    if not isinstance(rules, list) or len(rules) < 2 or any(not isinstance(r, dict) for r in rules):
        raise OperatorError("tunnel_configuration_invalid")
    sources = [r for r in rules if r.get("hostname") == TARGET_HOSTNAME]
    if len(sources) != 1 or not isinstance(sources[0].get("service"), str):
        raise OperatorError("tunnel_configuration_invalid")
    source = sources[0]
    if (set(source) - {"hostname", "service", "originRequest"}
        or not re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):[0-9]{2,5}", source["service"])
        or not isinstance(rules[-1].get("service"), str)
        or rules[-1].get("hostname") not in (None, "")):
        raise OperatorError("tunnel_configuration_invalid")
    if any(r.get("hostname") in AUSMALWIESE_NAMES for r in rules):
        raise OperatorError("tunnel_route_conflict")
    desired = deepcopy(config)
    additions = []
    for hostname in AUSMALWIESE_NAMES:
        entry = deepcopy(source)
        entry["hostname"] = hostname
        additions.append(entry)
    desired["ingress"] = rules[:-1] + additions + rules[-1:]
    return desired


def _baseline(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def provision_dns_secret(client: CloudflareClient, zone_id: str, token: str) -> None:
    if DNS_SECRET_PATH.exists():
        raise OperatorError("secret_already_exists")
    try:
        _ausmalwiese_zone(client, zone_id)
        _ausmalwiese_records(client, zone_id)
    except OperatorError as exc:
        raise OperatorError("dns_permission_check_failed") from exc
    payload = (json.dumps({"zone_id": zone_id, "zone_name": AUSMALWIESE_ZONE, "api_token": token},
                           separators=(",", ":"), sort_keys=True) + "\n").encode()
    _validate_secret_parent(SECRET_ROOT_PATH)
    _validate_secret_parent(SECRET_DIR_PATH)
    started = False
    fd = None
    try:
        for parent in (SECRET_ROOT_PATH, SECRET_DIR_PATH):
            if not parent.exists():
                os.mkdir(parent, 0o700)
                started = True
                _validate_secret_parent(parent)
        fd = os.open(DNS_SECRET_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        started = True
        view = memoryview(payload)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short_write")
            view = view[n:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        _validate_regular_root_file(DNS_SECRET_PATH, 0o600)
        if DNS_SECRET_PATH.read_bytes() != payload:
            raise SecretProvisionError("secret_post_write_verification_failed", True)
    except SecretProvisionError:
        raise
    except (OSError, OperatorError) as exc:
        raise SecretProvisionError("secret_write_failed", started) from exc
    finally:
        if fd is not None:
            os.close(fd)


def run_ausmalwiese(
    dns: CloudflareClient, tunnel: CloudflareClient, zone_id: str,
    account_id: str, action: str, apply: bool, expected_baseline: str,
) -> dict[str, Any]:
    zone = _ausmalwiese_zone(dns, zone_id)
    if zone["account"].get("id") != account_id:
        raise OperatorError("dns_zone_invalid")
    tunnel_id, config = _rpi5_tunnel(tunnel, account_id)
    if action == "tunnel-ausmalwiese":
        desired = _prepared_tunnel_config(config)
        baseline = _baseline(config)
        if apply:
            if expected_baseline != baseline:
                raise OperatorError("baseline_mismatch")
            tunnel._request("PUT", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
                            {"config": desired})
            _, observed = _rpi5_tunnel(tunnel, account_id)
            if observed != desired:
                raise PostWriteError("tunnel_configuration_invalid")
        return {"baseline": baseline, "applied": apply}

    if action not in ("dns-ausmalwiese-apex", "dns-ausmalwiese-www"):
        raise OperatorError("hostname_not_allowlisted")
    hostname = AUSMALWIESE_NAMES[0 if action == "dns-ausmalwiese-apex" else 1]
    rows = _ausmalwiese_records(dns, zone_id)
    if any(str(r.get("name", "")).lower().rstrip(".") == hostname for r in rows):
        raise OperatorError("dns_record_conflict")
    baseline = _baseline(rows)
    target = tunnel_id + ".cfargotunnel.com"
    if apply:
        if expected_baseline != baseline:
            raise OperatorError("baseline_mismatch")
        body = {"type": "CNAME", "name": hostname, "content": target, "ttl": 1, "proxied": True}
        dns._request("POST", f"/zones/{zone_id}/dns_records", body)
        observed = [r for r in _ausmalwiese_records(dns, zone_id) if r.get("name") == hostname]
        if (len(observed) != 1 or observed[0].get("type") != "CNAME"
            or observed[0].get("content") != target or observed[0].get("proxied") is not True):
            raise PostWriteError("cloudflare_write_shape_invalid")
    return {"baseline": baseline, "applied": apply}



def run_ausmalwiese_gsc_txt(
    dns: CloudflareClient, zone_id: str, apply: bool, expected_baseline: str,
) -> dict[str, Any]:
    """One fixed apex Google verification TXT. No Tunnel/Access credential or API."""
    _ausmalwiese_zone(dns, zone_id)
    before = _ausmalwiese_records(dns, zone_id)
    for row in before:
        name = str(row.get("name", "")).lower().rstrip(".")
        content = row.get("content")
        if (name == AUSMALWIESE_ZONE and row.get("type") == "TXT"
            and isinstance(content, str)
            and content.strip('"').startswith("google-site-verification=")):
            raise OperatorError("dns_record_conflict")

    baseline = _baseline(before)
    if not apply:
        return {"baseline": baseline, "applied": False}
    if expected_baseline != baseline:
        raise OperatorError("baseline_mismatch")

    body = {"type": "TXT", "name": AUSMALWIESE_ZONE,
            "content": GSC_TXT_CONTENT, "ttl": 1}
    response = dns._request("POST", f"/zones/{zone_id}/dns_records", body)
    created = response.get("result")
    created_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(created_id, str) or not ACCOUNT_ID_RE.fullmatch(created_id):
        raise PostWriteError("cloudflare_write_shape_invalid")
    try:
        after = _ausmalwiese_records(dns, zone_id)
    except OperatorError as exc:
        raise PostWriteError("cloudflare_write_shape_invalid") from exc
    matching = [row for row in after if row.get("id") == created_id]
    if (len(matching) != 1 or matching[0].get("type") != "TXT"
        or str(matching[0].get("name", "")).lower().rstrip(".") != AUSMALWIESE_ZONE
        or not isinstance(matching[0].get("content"), str)
        or matching[0]["content"].strip('"') != GSC_TXT_CONTENT
        or _baseline([row for row in after if row.get("id") != created_id]) != baseline):
        raise PostWriteError("cloudflare_write_shape_invalid")
    return {"baseline": baseline, "applied": True}


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



def _exact_owner_selector(policy: dict[str, Any]) -> dict[str, Any]:
    action = policy.get("decision", policy.get("action"))
    include = policy.get("include")
    require = policy.get("require", [])
    exclude = policy.get("exclude", [])
    if (
        action != "allow"
        or not isinstance(include, list)
        or len(include) != 1
        or not isinstance(include[0], dict)
        or set(include[0]) != {"email"}
        or require != []
        or exclude != []
    ):
        raise OperatorError("admin_template_policy_invalid")
    email_rule = include[0]["email"]
    if isinstance(email_rule, str):
        valid = bool(email_rule.strip())
    elif isinstance(email_rule, dict):
        value = email_rule.get("email")
        valid = isinstance(value, str) and bool(value.strip()) and set(email_rule) == {"email"}
    else:
        valid = False
    if not valid:
        raise OperatorError("admin_template_policy_invalid")
    return deepcopy(include[0])


def _admin_access_preflight(
    client: CloudflareClient,
    account_id: str,
) -> dict[str, Any]:
    apps = client.list_applications(account_id)
    if any(_matches_hostname(app, ADMIN_HOSTNAME) for app in apps):
        raise OperatorError("admin_target_application_already_exists")
    templates = [app for app in apps if _matches_root(app, ADMIN_TEMPLATE_HOSTNAME)]
    if len(templates) != 1:
        raise OperatorError("admin_template_missing_or_ambiguous")
    template = templates[0]
    template_id = template.get("id")
    if (
        template.get("type") != "self_hosted"
        or not isinstance(template_id, str)
        or not UUID_RE.fullmatch(template_id)
    ):
        raise OperatorError("admin_template_missing_or_ambiguous")
    policies = client.list_application_policies(account_id, template_id)
    if len(policies) != 1:
        raise OperatorError("admin_template_policy_invalid")
    owner_selector = _exact_owner_selector(policies[0])
    preexisting = {
        app["id"]: _stable_app_projection(app)
        for app in apps
        if isinstance(app.get("id"), str) and UUID_RE.fullmatch(app["id"])
    }
    baseline = _baseline({
        "apps": preexisting,
        "template_policy": policies[0],
    })
    return {
        "baseline": baseline,
        "owner_selector": owner_selector,
        "preexisting_apps": preexisting,
    }


def _admin_access_create_body(owner_selector: dict[str, Any]) -> dict[str, Any]:
    _exact_owner_selector({
        "decision": "allow",
        "include": [owner_selector],
        "require": [],
        "exclude": [],
    })
    return {
        "name": ADMIN_APP_NAME,
        "type": "self_hosted",
        "destinations": [{"type": "public", "uri": ADMIN_HOSTNAME}],
        "policies": [{
            "name": ADMIN_POLICY_NAME,
            "decision": "allow",
            "include": [deepcopy(owner_selector)],
            "require": [],
            "exclude": [],
        }],
    }


def _verify_admin_access_post_write(
    before: dict[str, Any],
    apps_after: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    created_app_id: str,
) -> None:
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
    exact = [app for app in apps_after if _matches_root(app, ADMIN_HOSTNAME)]
    if len(exact) != 1:
        raise OperatorError("admin_target_application_missing_or_ambiguous")
    app = exact[0]
    if (
        app.get("id") != created_app_id
        or app.get("name") != ADMIN_APP_NAME
        or app.get("type") != "self_hosted"
    ):
        raise OperatorError("created_application_identity_mismatch")
    if len(policies) != 1 or policies[0].get("name") != ADMIN_POLICY_NAME:
        raise OperatorError("created_application_policy_shape_invalid")
    observed_selector = _exact_owner_selector(policies[0])
    if observed_selector != before["owner_selector"]:
        raise OperatorError("created_application_policy_shape_invalid")


def run_ausmalwiese_admin_access(
    client: CloudflareClient,
    account_id: str,
    *,
    apply: bool,
    expected_baseline: str,
) -> dict[str, Any]:
    before = _admin_access_preflight(client, account_id)
    if not apply:
        return {"baseline": before["baseline"], "applied": False}
    if expected_baseline != before["baseline"]:
        raise OperatorError("baseline_mismatch")
    created = client.create_application(
        account_id,
        _admin_access_create_body(before["owner_selector"]),
    )
    created_id = created.get("id")
    if not isinstance(created_id, str) or not UUID_RE.fullmatch(created_id):
        raise PostWriteError("cloudflare_write_shape_invalid")
    try:
        apps_after = client.list_applications(account_id)
        policies = client.list_application_policies(account_id, created_id)
        _verify_admin_access_post_write(before, apps_after, policies, created_id)
    except OperatorError as exc:
        raise PostWriteError(str(exc)) from exc
    return {"baseline": before["baseline"], "applied": True}


def _admin_access_binding(
    client: CloudflareClient,
    account_id: str,
) -> dict[str, Any]:
    apps = client.list_applications(account_id)
    exact = [app for app in apps if _matches_root(app, ADMIN_HOSTNAME)]
    if len(exact) != 1:
        raise OperatorError("admin_target_application_missing_or_ambiguous")
    app = exact[0]
    app_id = app.get("id")
    aud = app.get("aud")
    if (
        app.get("name") != ADMIN_APP_NAME
        or app.get("type") != "self_hosted"
        or not isinstance(app_id, str)
        or not UUID_RE.fullmatch(app_id)
        or not isinstance(aud, str)
        or not aud
        or len(aud) > 4096
        or any(ch.isspace() for ch in aud)
    ):
        raise OperatorError("admin_access_binding_invalid")
    policies = client.list_application_policies(account_id, app_id)
    if len(policies) != 1 or policies[0].get("name") != ADMIN_POLICY_NAME:
        raise OperatorError("admin_access_binding_invalid")
    _exact_owner_selector(policies[0])
    organization = client._request(
        "GET",
        f"/accounts/{account_id}/access/organizations",
    ).get("result")
    if not isinstance(organization, dict):
        raise OperatorError("admin_access_binding_invalid")
    team_name = organization.get("name")
    if (
        not isinstance(team_name, str)
        or not team_name.strip()
        or len(team_name) > 255
        or any(ch.isspace() for ch in team_name)
    ):
        raise OperatorError("admin_access_binding_invalid")
    return {
        "team_name": team_name,
        "aud": aud,
        "private_baseline": _baseline({
            "application": _stable_app_projection(app),
            "policy": policies[0],
            "organization_name": team_name,
        }),
    }


def _prepared_admin_tunnel_config(
    config: dict[str, Any],
    *,
    team_name: str,
    aud: str,
) -> dict[str, Any]:
    rules = config.get("ingress")
    if (
        not isinstance(rules, list)
        or not rules
        or any(not isinstance(rule, dict) for rule in rules)
        or rules[-1].get("hostname") not in (None, "")
        or not isinstance(rules[-1].get("service"), str)
    ):
        raise OperatorError("tunnel_configuration_invalid")
    if any(rule.get("hostname") == ADMIN_HOSTNAME for rule in rules):
        raise OperatorError("admin_tunnel_route_conflict")
    entry = {
        "hostname": ADMIN_HOSTNAME,
        "service": ADMIN_ORIGIN,
        "originRequest": {
            "access": {
                "required": True,
                "teamName": team_name,
                "audTag": [aud],
            }
        },
    }
    desired = deepcopy(config)
    desired["ingress"] = rules[:-1] + [entry] + [rules[-1]]
    return desired


def _admin_tunnel_entry_valid(config: dict[str, Any]) -> bool:
    rules = config.get("ingress")
    if not isinstance(rules, list):
        return False
    matches = [rule for rule in rules if isinstance(rule, dict) and rule.get("hostname") == ADMIN_HOSTNAME]
    if len(matches) != 1:
        return False
    rule = matches[0]
    origin = rule.get("originRequest")
    access = origin.get("access") if isinstance(origin, dict) else None
    aud = access.get("audTag") if isinstance(access, dict) else None
    return (
        rule.get("service") == ADMIN_ORIGIN
        and isinstance(access, dict)
        and access.get("required") is True
        and isinstance(access.get("teamName"), str)
        and bool(access["teamName"])
        and isinstance(aud, list)
        and len(aud) == 1
        and isinstance(aud[0], str)
        and bool(aud[0])
    )


def run_ausmalwiese_admin_tunnel(
    access: CloudflareClient,
    tunnel: CloudflareClient,
    account_id: str,
    *,
    apply: bool,
    expected_baseline: str,
) -> dict[str, Any]:
    binding = _admin_access_binding(access, account_id)
    tunnel_id, config = _rpi5_tunnel(tunnel, account_id)
    desired = _prepared_admin_tunnel_config(
        config,
        team_name=binding["team_name"],
        aud=binding["aud"],
    )
    baseline = _baseline({
        "tunnel_config": config,
        "access_binding": binding["private_baseline"],
    })
    if not apply:
        return {"baseline": baseline, "applied": False}
    if expected_baseline != baseline:
        raise OperatorError("baseline_mismatch")
    tunnel._request(
        "PUT",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
        {"config": desired},
    )
    try:
        _, observed = _rpi5_tunnel(tunnel, account_id)
    except OperatorError as exc:
        raise PostWriteError("admin_tunnel_route_invalid") from exc
    if observed != desired or not _admin_tunnel_entry_valid(observed):
        raise PostWriteError("admin_tunnel_route_invalid")
    return {"baseline": baseline, "applied": True}


def run_ausmalwiese_admin_dns(
    dns: CloudflareClient,
    tunnel: CloudflareClient,
    zone_id: str,
    account_id: str,
    *,
    apply: bool,
    expected_baseline: str,
) -> dict[str, Any]:
    zone = _ausmalwiese_zone(dns, zone_id)
    if zone["account"].get("id") != account_id:
        raise OperatorError("account_binding_mismatch")
    tunnel_id, config = _rpi5_tunnel(tunnel, account_id)
    if not _admin_tunnel_entry_valid(config):
        raise OperatorError("admin_tunnel_route_invalid")
    records = _ausmalwiese_records(dns, zone_id)
    if any(str(row.get("name", "")).lower().rstrip(".") == ADMIN_HOSTNAME for row in records):
        raise OperatorError("dns_record_conflict")
    baseline = _baseline({"dns_records": records, "tunnel_config": config})
    if not apply:
        return {"baseline": baseline, "applied": False}
    if expected_baseline != baseline:
        raise OperatorError("baseline_mismatch")
    body = {
        "type": "CNAME",
        "name": ADMIN_HOSTNAME,
        "content": tunnel_id + ".cfargotunnel.com",
        "ttl": 1,
        "proxied": True,
    }
    response = dns._request("POST", f"/zones/{zone_id}/dns_records", body)
    created = response.get("result")
    created_id = created.get("id") if isinstance(created, dict) else None
    if not isinstance(created_id, str) or not ACCOUNT_ID_RE.fullmatch(created_id):
        raise PostWriteError("cloudflare_write_shape_invalid")
    try:
        after = _ausmalwiese_records(dns, zone_id)
    except OperatorError as exc:
        raise PostWriteError("cloudflare_write_shape_invalid") from exc
    matching = [
        row for row in after
        if row.get("id") == created_id
        and str(row.get("name", "")).lower().rstrip(".") == ADMIN_HOSTNAME
    ]
    if (
        len(matching) != 1
        or matching[0].get("type") != "CNAME"
        or matching[0].get("content") != body["content"]
        or matching[0].get("proxied") is not True
        or _baseline([row for row in after if row.get("id") != created_id])
        != _baseline(records)
    ):
        raise PostWriteError("cloudflare_write_shape_invalid")
    return {"baseline": baseline, "applied": True}


def _checkout_git(
    checkout_path: Path,
    args: list[str],
    *,
    runner: Any = subprocess.run,
) -> subprocess.CompletedProcess[Any]:
    return runner(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-c",
            f"safe.directory={checkout_path}",
            "-C",
            str(checkout_path),
            *args,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=15,
    )


def verify_phase7_checkout(
    expected_main: str,
    checkout_path: Path,
    *,
    runner: Any = subprocess.run,
) -> Path:
    if not SHA_RE.fullmatch(expected_main) or not checkout_path.is_dir():
        raise OperatorError("phase7_checkout_invalid")

    def read(args: list[str]) -> str:
        completed = _checkout_git(checkout_path, args, runner=runner)
        if completed.returncode != 0:
            raise OperatorError("phase7_checkout_invalid")
        return completed.stdout.strip()

    if Path(read(["rev-parse", "--show-toplevel"])).resolve() != checkout_path.resolve():
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
    audit_path = checkout_path / "scripts" / "ingress_drift_audit.py"
    try:
        st = os.lstat(audit_path)
    except OSError as exc:
        raise OperatorError("phase7_checkout_invalid") from exc
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise OperatorError("phase7_checkout_invalid")
    return audit_path


def run_phase7_audit(
    audit_path: Path,
    checkout_path: Path,
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
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(checkout_path),
        "GIT_OPTIONAL_LOCKS": "0",
    }
    completed = runner(
        [PYTHON, str(audit_path), "--expected-main", expected_main],
        cwd=str(checkout_path),
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


def _emit_phase7_blocked(expected_main: str) -> None:
    print(
        json.dumps(
            {
                "schema": "rozkalns.rpi5-main.ingress-drift-audit-evidence.v1",
                "schema_version": 1,
                "audit": "phase7-automated-ingress-drift",
                "canonical_issue": 903,
                "source_main_sha": expected_main,
                "mutation_performed": False,
                "result": "BLOCKED",
                "reason": "read_only_ingress_drift_audit_failed",
            },
            indent=2,
            sort_keys=True,
        )
    )


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

    dns_secret = subparsers.add_parser("provision-ausmalwiese-dns-secret")
    dns_secret.add_argument("--expected-main", required=True)
    dns_secret.add_argument("--confirm", default="")

    for name in ("dns-ausmalwiese-apex", "dns-ausmalwiese-www", "tunnel-ausmalwiese"):
        command = subparsers.add_parser(name)
        command.add_argument("--expected-main", required=True)
        command.add_argument("--apply", action="store_true")
        command.add_argument("--expected-baseline", default="")
        command.add_argument("--confirm", default="")

    for name in (
        "ausmalwiese-admin-access",
        "ausmalwiese-admin-tunnel",
        "ausmalwiese-admin-dns",
    ):
        command = subparsers.add_parser(name)
        command.add_argument("--expected-main", required=True)
        command.add_argument("--apply", action="store_true")
        command.add_argument("--expected-baseline", default="")
        command.add_argument("--confirm", default="")

    gsc_txt = subparsers.add_parser("dns-ausmalwiese-gsc-txt")
    gsc_txt.add_argument("--expected-main", required=True)
    gsc_txt.add_argument("--apply", action="store_true")
    gsc_txt.add_argument("--expected-baseline", default="")
    gsc_txt.add_argument("--confirm", default="")

    phase7 = subparsers.add_parser("phase7-ingress-drift-audit")
    phase7.add_argument("--expected-main", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    output_target = (
        ADMIN_HOSTNAME
        if args.action.startswith("ausmalwiese-admin-")
        else TARGET_HOSTNAME
    )
    if os.geteuid() != 0:
        _emit(
            "BLOCKED",
            reason="root_required",
            apply_ready=False,
            target_hostname=output_target,
        )
        return 2

    operator_path = Path(sys.argv[0]).resolve()
    try:
        release = load_release_metadata(args.expected_main, operator_path)

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

        if args.action == "provision-ausmalwiese-dns-secret":
            if args.confirm != DNS_PROVISION_CONFIRM_TEXT:
                raise OperatorError("provision_confirmation_missing")
            zone_id, token = _read_hidden_dns_credentials()
            provision_dns_secret(CloudflareClient(token), zone_id, token)
            token = ""
            _emit("PASS", mutation_performed=True)
            return 0

        if args.action == "dns-ausmalwiese-gsc-txt":
            if args.apply and (
                args.confirm != GSC_TXT_APPLY_CONFIRM_TEXT
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)
            ):
                raise OperatorError("apply_confirmation_missing")
            zone_id, dns_token = load_dns_credentials()
            report = run_ausmalwiese_gsc_txt(
                CloudflareClient(dns_token), zone_id, args.apply, args.expected_baseline
            )
            print(json.dumps({"operation": args.action, "result": "PASS",
                              "baseline_sha256": report["baseline"],
                              "mutation_performed": report["applied"]}, sort_keys=True))
            return 0

        if args.action in ("dns-ausmalwiese-apex", "dns-ausmalwiese-www", "tunnel-ausmalwiese"):
            confirm = TUNNEL_APPLY_CONFIRM_TEXT if args.action == "tunnel-ausmalwiese" else DNS_APPLY_CONFIRM_TEXT
            if args.apply and (args.confirm != confirm or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)):
                raise OperatorError("apply_confirmation_missing")
            zone_id, dns_token = load_dns_credentials()
            account_id, tunnel_token = load_tunnel_credentials()
            report = run_ausmalwiese(
                CloudflareClient(dns_token), CloudflareClient(tunnel_token),
                zone_id, account_id, args.action, args.apply, args.expected_baseline)
            print(json.dumps({"operation": args.action, "result": "PASS",
                              "baseline_sha256": report["baseline"],
                              "mutation_performed": report["applied"]}, sort_keys=True))
            return 0

        if args.action == "ausmalwiese-admin-access":
            if args.apply and (
                args.confirm != ADMIN_ACCESS_CONFIRM_TEXT
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)
            ):
                raise OperatorError("apply_confirmation_missing")
            account_id, access_token = load_access_credentials()
            report = run_ausmalwiese_admin_access(
                CloudflareClient(access_token),
                account_id,
                apply=args.apply,
                expected_baseline=args.expected_baseline,
            )
            access_token = ""
            print(json.dumps({
                "operation": args.action,
                "target_hostname": ADMIN_HOSTNAME,
                "result": "PASS",
                "baseline_sha256": report["baseline"],
                "mutation_performed": report["applied"],
                "privacy": {"owner_identity_emitted": False, "aud_emitted": False},
            }, sort_keys=True))
            return 0

        if args.action == "ausmalwiese-admin-tunnel":
            if args.apply and (
                args.confirm != ADMIN_TUNNEL_CONFIRM_TEXT
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)
            ):
                raise OperatorError("apply_confirmation_missing")
            access_account_id, access_token = load_access_credentials()
            tunnel_account_id, tunnel_token = load_tunnel_credentials()
            if access_account_id != tunnel_account_id:
                raise OperatorError("account_binding_mismatch")
            report = run_ausmalwiese_admin_tunnel(
                CloudflareClient(access_token),
                CloudflareClient(tunnel_token),
                access_account_id,
                apply=args.apply,
                expected_baseline=args.expected_baseline,
            )
            access_token = ""
            tunnel_token = ""
            print(json.dumps({
                "operation": args.action,
                "target_hostname": ADMIN_HOSTNAME,
                "result": "PASS",
                "baseline_sha256": report["baseline"],
                "mutation_performed": report["applied"],
                "privacy": {"owner_identity_emitted": False, "aud_emitted": False, "team_name_emitted": False},
            }, sort_keys=True))
            return 0

        if args.action == "ausmalwiese-admin-dns":
            if args.apply and (
                args.confirm != ADMIN_DNS_CONFIRM_TEXT
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)
            ):
                raise OperatorError("apply_confirmation_missing")
            zone_id, dns_token = load_dns_credentials()
            account_id, tunnel_token = load_tunnel_credentials()
            report = run_ausmalwiese_admin_dns(
                CloudflareClient(dns_token),
                CloudflareClient(tunnel_token),
                zone_id,
                account_id,
                apply=args.apply,
                expected_baseline=args.expected_baseline,
            )
            dns_token = ""
            tunnel_token = ""
            print(json.dumps({
                "operation": args.action,
                "target_hostname": ADMIN_HOSTNAME,
                "result": "PASS",
                "baseline_sha256": report["baseline"],
                "mutation_performed": report["applied"],
            }, sort_keys=True))
            return 0

        if args.action == "phase7-ingress-drift-audit":
            checkout_value = release.get("checkout_path")
            if not isinstance(checkout_value, str):
                raise OperatorError("phase7_checkout_invalid")
            checkout_path = Path(checkout_value)
            audit_path = verify_phase7_checkout(
                args.expected_main,
                checkout_path,
            )
            account_id, token = load_tunnel_credentials()
            rc, report = run_phase7_audit(
                audit_path,
                checkout_path,
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
            target_hostname=output_target,
        )
        return 4
    except PostWriteError as exc:
        _emit(
            "STOP_ERROR",
            reason=str(exc),
            mutation_performed=True,
            write_attempted=True,
            apply_ready=False,
            target_hostname=output_target,
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
        if args.action == "phase7-ingress-drift-audit":
            _emit_phase7_blocked(args.expected_main)
            return 2
        _emit(
            "BLOCKED",
            reason=str(exc),
            mutation_performed=False,
            write_attempted=False,
            apply_ready=False,
            target_hostname=output_target,
        )
        return 3

    _emit(
        "PASS",
        mutation_performed=bool(result["mutation_performed"]),
        write_attempted=bool(args.apply),
        apply_ready=bool(result["apply_ready"]),
        target_hostname=output_target,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())