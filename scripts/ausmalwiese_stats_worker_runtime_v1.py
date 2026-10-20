#!/usr/bin/env python3
"""SOURCE ONLY: fixed installed Stats Worker deployment runtime for #1118.

A source merge does not install or execute this program. Future execution
requires separate exact COMPOSITE LIVE authority. Credentials are read only
from one protected root-owned file after exact installed release verification.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from typing import Any

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy")
PROVISIONER = Path("/usr/local/sbin/rpi5-ausmalwiese-stats-worker-deploy-provision")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-stats-worker-deploy")
CORE = ROOT / "core.py"
WORKER_SOURCE = ROOT / "stats-worker.js"
CONFIG_SOURCE = ROOT / "wrangler.stats-worker.jsonc"
RELEASE = ROOT / "release.json"
SECRET_DIR = Path("/etc/rpi5-secrets/cloudflare")
SECRET = SECRET_DIR / "ausmalwiese-stats-worker-write.json"

REPOSITORY = "rozkalnsandris/RPi5_main"
APP_REPOSITORY = "rozkalnsandris/coloring-pages"
APP_SHA = "e6c1a4a4fa9f8a9c82dc73babd6b4a2a1bdd4d63"
WORKER = "coloring-pages-stats-v1"
WORKER_BLOB = "c2ac9da6e0701103e0041b30db7dfbea4298f96c"
CONFIG_BLOB = "3733263a391274f2b6b0f2023c8656565bde8e1a"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
HOST = "api.cloudflare.com"
COMPATIBILITY_DATE = "2026-10-06"
D1_DATABASE_ID = "f8ac8f1d-a230-4bc4-af13-557c1b91b273"
RATE_NAMESPACE_ID = "1152026106"
RATE_LIMIT = 100
RATE_PERIOD = 60
ROUTES = {
    "coloring.rozkalns.net/api/stats/*": "rozkalns.net",
    "ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "www.ausmalwiese.de/api/stats/*": "ausmalwiese.de",
    "ausmalwiese.de/q": "ausmalwiese.de",
}
KINDS = {
    "DB": "d1",
    "RATE_LIMITER": "ratelimit",
    "PUBLIC_ORIGIN": "plain_text",
    "CF_ANALYTICS_HOST": "plain_text",
    "CF_ZONE_TAG": "plain_text",
    "VISITOR_HMAC_KEY": "secret_text",
    "CF_ANALYTICS_API_TOKEN": "secret_text",
}
PRE_CONFIRM = "OWNER-AUTHORIZED-STATS-WORKER-PREFLIGHT"
APPLY_CONFIRM = "OWNER-AUTHORIZED-STATS-WORKER-APPLY"
RECOVERY_PRE_CONFIRM = "OWNER-AUTHORIZED-STATS-WORKER-RECOVERY-PREFLIGHT"
RECOVERY_DEPLOY_CONFIRM = "OWNER-AUTHORIZED-STATS-WORKER-DEPLOY-EXISTING"

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ID32 = re.compile(r"[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
SAFE_KEY = re.compile(r"[A-Za-z0-9_.:/-]{1,160}\Z")

MAX_SECRET = 16384
MAX_JSON = 1500000
MAX_UPLOAD = 300000
READ_BUDGET = 48
BOUNDARY = "----rpi5-ausmalwiese-stats-worker-v1"


class Stop(Exception):
    """Stable public-safe runtime reason only."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def safe_parents(path: Path) -> None:
    parent = path.parent
    while True:
        try:
            info = parent.lstat()
        except OSError:
            raise Stop("parent_untrusted") from None
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise Stop("parent_untrusted")
        if parent == parent.parent:
            return
        parent = parent.parent


def guarded_bytes(path: Path, mode: int, maximum: int) -> bytes:
    safe_parents(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("protected_file_unavailable") from None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_nlink != 1
            or not 0 < info.st_size <= maximum
        ):
            raise Stop("protected_file_invalid")
        raw = os.read(fd, maximum + 1)
        if len(raw) != info.st_size:
            raise Stop("protected_file_invalid")
        return raw
    finally:
        os.close(fd)


def strict_json(raw: bytes) -> Any:
    try:
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate")
                out[key] = value
            return out

        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, TypeError):
        raise Stop("json_invalid") from None


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise Stop("canonical_json_invalid") from None


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def guarded_root() -> None:
    safe_parents(ROOT)
    try:
        info = ROOT.lstat()
    except OSError:
        raise Stop("release_root_unavailable") from None
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Stop("release_root_invalid")


def verified_install(expected_main: str) -> tuple[bytes, bytes, bytes]:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    guarded_root()
    package = {
        "launcher_sha256": guarded_bytes(ENTRY, 0o500, 196608),
        "provisioner_sha256": guarded_bytes(PROVISIONER, 0o500, 196608),
        "core_sha256": guarded_bytes(CORE, 0o400, 196608),
        "worker_sha256": guarded_bytes(WORKER_SOURCE, 0o400, 196608),
        "config_sha256": guarded_bytes(CONFIG_SOURCE, 0o400, 131072),
    }
    meta = strict_json(guarded_bytes(RELEASE, 0o400, 16384))
    expected_keys = {
        "schema_version", "repository", "source_sha", "app_repository", "app_sha",
        "worker", "worker_blob", "config_blob", *package.keys(),
    }
    if (
        not isinstance(meta, dict)
        or set(meta) != expected_keys
        or meta["schema_version"] != 1
        or meta["repository"] != REPOSITORY
        or meta["source_sha"] != expected_main
        or meta["app_repository"] != APP_REPOSITORY
        or meta["app_sha"] != APP_SHA
        or meta["worker"] != WORKER
        or meta["worker_blob"] != WORKER_BLOB
        or meta["config_blob"] != CONFIG_BLOB
    ):
        raise Stop("release_identity_invalid")
    for key, raw in package.items():
        value = meta.get(key)
        if (
            not isinstance(value, str)
            or SHA64.fullmatch(value) is None
            or hashlib.sha256(raw).hexdigest() != value
        ):
            raise Stop("release_identity_invalid")
    core = package["core_sha256"]
    worker = package["worker_sha256"]
    config = package["config_sha256"]
    if git_blob(worker) != WORKER_BLOB or git_blob(config) != CONFIG_BLOB:
        raise Stop("application_source_identity_invalid")
    return core, worker, config


def load_core(raw: bytes):
    module = type(sys)("stats_worker_exact_deploy_installed")
    module.__file__ = str(CORE)
    try:
        exec(compile(raw, str(CORE), "exec"), module.__dict__)
    except Exception:
        raise Stop("core_load_failed") from None
    for name in (
        "validate_snapshot", "future_run_once", "verify_source",
        "deployment_payload", "SOURCE_BLOB", "CONFIG_BLOB",
    ):
        if not hasattr(module, name):
            raise Stop("core_interface_invalid")
    if module.SOURCE_BLOB != WORKER_BLOB or module.CONFIG_BLOB != CONFIG_BLOB:
        raise Stop("core_provenance_invalid")
    return module


def safe_secret_dir() -> None:
    safe_parents(SECRET)
    try:
        info = SECRET_DIR.lstat()
    except OSError:
        raise Stop("credential_directory_unavailable") from None
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Stop("credential_directory_untrusted")


def credential() -> tuple[str, str, dict[str, str]]:
    safe_secret_dir()
    obj = strict_json(guarded_bytes(SECRET, 0o600, MAX_SECRET))
    if not isinstance(obj, dict) or set(obj) != {
        "worker", "account_id", "api_token", "zones"
    }:
        raise Stop("credential_shape_invalid")
    if obj["worker"] != WORKER:
        raise Stop("credential_target_invalid")
    account = obj["account_id"]
    token = obj["api_token"]
    zones = obj["zones"]
    if (
        not isinstance(account, str)
        or ID32.fullmatch(account) is None
        or hashlib.sha256(account.encode("ascii")).hexdigest() != ACCOUNT_SHA256
    ):
        raise Stop("account_identity_invalid")
    if (
        not isinstance(token, str)
        or not 20 <= len(token) <= 4096
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
    ):
        raise Stop("token_shape_invalid")
    if (
        not isinstance(zones, dict)
        or set(zones) != {"ausmalwiese.de", "rozkalns.net"}
        or any(
            not isinstance(value, str) or ID32.fullmatch(value) is None
            for value in zones.values()
        )
        or len(set(zones.values())) != 2
    ):
        raise Stop("zone_identity_invalid")
    return account, token, dict(zones)


def _safe_settings(value: Any, depth: int = 0) -> Any:
    need(depth <= 7, "settings_depth")
    if value is None or isinstance(value, bool):
        return value
    if type(value) is int:
        need(abs(value) <= 10**15, "settings_number")
        return value
    if type(value) is float:
        need(value == value and abs(value) != float("inf"), "settings_number")
        return value
    if type(value) is str:
        need(len(value) <= 4096, "settings_string")
        return value
    if type(value) is list:
        need(len(value) <= 200, "settings_list")
        return [_safe_settings(item, depth + 1) for item in value]
    if type(value) is dict:
        need(len(value) <= 200, "settings_map")
        out = {}
        for key, item in value.items():
            need(
                isinstance(key, str) and SAFE_KEY.fullmatch(key) is not None,
                "settings_key",
            )
            out[key] = _safe_settings(item, depth + 1)
        return out
    raise Stop("settings_type")


class CloudflareTransport:
    def __init__(
        self, account, token, zones, *, connection_factory=None,
        allow_deploy_existing=False,
    ):
        self.account = account
        self.token = token
        self.zones = dict(zones)
        self.allow_deploy_existing = allow_deploy_existing
        self.connection_factory = connection_factory or (
            lambda: http.client.HTTPSConnection(
                HOST, timeout=10, context=ssl.create_default_context()
            )
        )
        self.reads = 0
        self.uploads = 0
        self.deploys = 0

    def _request(
        self, method, path, *, body=None, content_type=None, phase="read"
    ):
        if method == "GET":
            need(self.reads < READ_BUDGET, "read_budget_exhausted")
            self.reads += 1
        elif phase == "upload":
            need(
                not self.allow_deploy_existing
                and self.uploads == 0
                and self.deploys == 0,
                "upload_budget_exhausted",
            )
            self.uploads = 1
        elif phase == "deploy":
            if self.allow_deploy_existing:
                need(
                    self.uploads == 0 and self.deploys == 0,
                    "deploy_budget_exhausted",
                )
            else:
                need(
                    self.uploads == 1 and self.deploys == 0,
                    "deploy_budget_exhausted",
                )
            self.deploys = 1
        else:
            raise Stop("request_phase_invalid")

        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if content_type is not None:
            headers["Content-Type"] = content_type
        conn = None
        dispatched = method != "GET"
        try:
            conn = self.connection_factory()
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                raise Stop("provider_response_unexpected")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise Stop("provider_response_encoding")
            advertised = response.getheader("Content-Length")
            if advertised is not None:
                need(advertised.isdecimal(), "provider_response_length")
                need(int(advertised) <= MAX_JSON, "provider_response_oversize")
            raw = response.read(MAX_JSON + 1)
            need(0 < len(raw) <= MAX_JSON, "provider_response_oversize")
            return strict_json(raw)
        except Stop:
            raise
        except Exception:
            if dispatched:
                raise Stop(phase + "_outcome_unknown_stop") from None
            raise Stop("provider_read_failed") from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _unwrap(payload):
        need(
            isinstance(payload, dict)
            and payload.get("success") is True
            and isinstance(payload.get("errors"), list)
            and not payload["errors"]
            and "result" in payload,
            "provider_envelope_invalid",
        )
        info = payload.get("result_info")
        if info is not None:
            need(isinstance(info, dict), "pagination_invalid")
            if info.get("page") is not None:
                need(info["page"] == 1, "pagination_invalid")
            if info.get("total_pages") is not None:
                need(info["total_pages"] == 1, "pagination_invalid")
            if info.get("cursors") is not None:
                need(
                    isinstance(info["cursors"], dict)
                    and info["cursors"].get("after") is None,
                    "pagination_invalid",
                )
        return payload["result"]

    @staticmethod
    def _list_result(payload, *, prefix, result_key):
        need(isinstance(payload, dict), prefix + "_envelope")
        result = payload.get("result")
        need(isinstance(result, dict), prefix + "_result_shape")
        items = result.get(result_key)
        need(
            isinstance(items, list) and bool(items),
            prefix + "_collection_shape",
        )
        info = payload.get("result_info")
        if info is not None:
            need(isinstance(info, dict), prefix + "_pagination")
            if "page" in info:
                need(
                    type(info["page"]) is int and info["page"] == 1,
                    prefix + "_pagination",
                )
        return items

    @staticmethod
    def _latest_version_from_payload(payload):
        items = CloudflareTransport._list_result(
            payload,
            prefix="versions",
            result_key="items",
        )
        latest = items[0]
        need(isinstance(latest, dict), "version_shape")
        version_id = latest.get("id")
        need(
            isinstance(version_id, str)
            and UUID.fullmatch(version_id) is not None,
            "version_id_invalid",
        )
        return version_id

    @staticmethod
    def _latest_deployment_from_payload(payload):
        items = CloudflareTransport._list_result(
            payload,
            prefix="deployments",
            result_key="deployments",
        )
        latest = items[0]
        need(isinstance(latest, dict), "deployment_shape")
        deployment_id = latest.get("id")
        need(
            isinstance(deployment_id, str)
            and UUID.fullmatch(deployment_id) is not None,
            "deployment_id_invalid",
        )
        versions = latest.get("versions")
        need(
            isinstance(versions, list)
            and len(versions) == 1
            and isinstance(versions[0], dict),
            "traffic_split",
        )
        version_id = versions[0].get("version_id")
        percentage = versions[0].get("percentage")
        need(
            isinstance(version_id, str)
            and UUID.fullmatch(version_id) is not None
            and type(percentage) in (int, float)
            and type(percentage) is not bool
            and percentage == 100,
            "traffic_split",
        )
        return deployment_id, version_id

    def _get(self, path):
        return self._unwrap(self._request("GET", path, phase="read"))

    def _versions(self):
        payload = self._request(
            "GET",
            f"/client/v4/accounts/{self.account}/workers/scripts/{WORKER}"
            "/versions?page=1&per_page=100",
            phase="read",
        )
        return self._latest_version_from_payload(payload)

    def _deployment(self):
        payload = self._request(
            "GET",
            f"/client/v4/accounts/{self.account}/workers/scripts/{WORKER}"
            "/deployments",
            phase="read",
        )
        return self._latest_deployment_from_payload(payload)

    def _version_metadata(self, version_id):
        need(UUID.fullmatch(version_id) is not None, "version_id_invalid")
        result = self._get(
            f"/client/v4/accounts/{self.account}/workers/scripts/{WORKER}"
            f"/versions/{version_id}"
        )
        need(
            isinstance(result, dict)
            and result.get("id") == version_id
            and isinstance(result.get("resources"), dict),
            "version_detail_invalid",
        )
        resources = result["resources"]
        need(
            set(resources).issubset({"bindings", "script", "script_runtime"}),
            "version_resources_unknown",
        )
        bindings = resources.get("bindings")
        script = resources.get("script")
        runtime = resources.get("script_runtime")
        need(
            isinstance(bindings, list)
            and isinstance(script, dict)
            and isinstance(runtime, dict),
            "version_resources_invalid",
        )

        by_name = {}
        for item in bindings:
            need(
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and item["name"] not in by_name,
                "binding_shape",
            )
            by_name[item["name"]] = item
        need(set(by_name) == set(KINDS), "binding_set_drift")

        descriptor = {}
        db = by_name["DB"]
        need(
            set(db).issubset({"name", "type", "database_id", "id"})
            and db.get("type") == "d1",
            "d1_fields",
        )
        database_id = db.get("database_id")
        deprecated_id = db.get("id")
        if database_id is None:
            database_id = deprecated_id
        elif deprecated_id is not None:
            need(deprecated_id == database_id, "d1_identity_ambiguous")
        need(database_id == D1_DATABASE_ID, "d1_identity")
        descriptor["DB"] = {
            "kind": "d1",
            "fingerprint": digest({"database_id": D1_DATABASE_ID}),
        }

        rate = by_name["RATE_LIMITER"]
        simple = rate.get("simple")
        need(
            set(rate).issubset({"name", "type", "namespace_id", "simple"})
            and rate.get("type") == "ratelimit"
            and rate.get("namespace_id") == RATE_NAMESPACE_ID
            and isinstance(simple, dict)
            and set(simple).issubset({"limit", "period", "mitigation_timeout"})
            and simple.get("limit") == RATE_LIMIT
            and simple.get("period") == RATE_PERIOD
            and simple.get("mitigation_timeout", 0) in (0, None),
            "rate_identity",
        )
        descriptor["RATE_LIMITER"] = {
            "kind": "ratelimit",
            "fingerprint": digest({
                "namespace_id": RATE_NAMESPACE_ID,
                "limit": RATE_LIMIT,
                "period": RATE_PERIOD,
            }),
        }

        for name in ("PUBLIC_ORIGIN", "CF_ANALYTICS_HOST", "CF_ZONE_TAG"):
            item = by_name[name]
            need(
                item.get("type") == "plain_text"
                and set(item).issubset({"name", "type", "text"})
                and isinstance(item.get("text"), str)
                and len(item["text"]) <= 4096,
                "plain_binding_invalid",
            )
            descriptor[name] = {
                "kind": "plain_text",
                "fingerprint": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
            }

        for name in ("VISITOR_HMAC_KEY", "CF_ANALYTICS_API_TOKEN"):
            item = by_name[name]
            need(
                item.get("type") == "secret_text"
                and set(item) == {"name", "type"},
                "secret_binding_unsafe",
            )
            descriptor[name] = {"kind": "secret_text", "fingerprint": None}

        allowed_runtime = {
            "compatibility_date", "compatibility_flags", "exports", "limits",
            "migration_tag", "usage_model",
        }
        allowed_script = {"etag", "handlers", "last_deployed_from", "named_handlers"}
        need(set(runtime).issubset(allowed_runtime), "runtime_fields_unknown")
        need(set(script).issubset(allowed_script), "script_fields_unknown")
        raw_date = runtime.get("compatibility_date")
        need(isinstance(raw_date, str), "compatibility_date_invalid")
        if raw_date.endswith("T00:00:00Z"):
            raw_date = raw_date[:10]
        need(raw_date == COMPATIBILITY_DATE, "compatibility_date_drift")
        flags = runtime.get("compatibility_flags", [])
        need(
            isinstance(flags, list)
            and all(isinstance(x, str) and SAFE_KEY.fullmatch(x) for x in flags)
            and len(flags) == len(set(flags))
            and flags == [],
            "compatibility_flags_drift",
        )
        settings = {
            "script": {
                "handlers": _safe_settings(script.get("handlers", [])),
                "named_handlers": _safe_settings(script.get("named_handlers", [])),
            },
            "script_runtime": {
                key: _safe_settings(runtime[key])
                for key in ("exports", "limits", "migration_tag", "usage_model")
                if key in runtime
            },
        }
        return descriptor, {
            "compatibility_date": raw_date,
            "compatibility_flags": flags,
            "settings_sha256": digest(settings),
        }

    def _code_sha(self, version_id):
        need(UUID.fullmatch(version_id) is not None, "version_id_invalid")
        result = self._get(
            f"/client/v4/accounts/{self.account}/workers/workers/{WORKER}"
            f"/versions/{version_id}?include=modules"
        )
        need(
            isinstance(result, dict)
            and result.get("id") == version_id
            and isinstance(result.get("modules"), list),
            "version_modules_invalid",
        )
        main_module = result.get("main_module")
        need(
            isinstance(main_module, str)
            and 1 <= len(main_module) <= 4096,
            "version_modules_invalid",
        )
        matches = [
            item for item in result["modules"]
            if isinstance(item, dict) and item.get("name") == main_module
        ]
        need(len(matches) == 1, "main_module_ambiguous")
        item = matches[0]
        need(
            {"name", "content_type", "content_base64"}.issubset(item)
            and item.get("content_type") in {
                "application/javascript+module", "text/javascript+module",
                "application/javascript", "text/javascript",
            }
            and isinstance(item.get("content_base64"), str),
            "main_module_invalid",
        )
        try:
            raw = base64.b64decode(item["content_base64"], validate=True)
        except Exception:
            raise Stop("main_module_base64_invalid") from None
        need(0 < len(raw) <= 196608, "main_module_size")
        return hashlib.sha256(raw).hexdigest()

    def _routes(self):
        found = {}
        for zone_name, zone_id in self.zones.items():
            zone = self._get(f"/client/v4/zones/{zone_id}")
            need(
                isinstance(zone, dict)
                and zone.get("id") == zone_id
                and zone.get("name") == zone_name
                and zone.get("status") == "active",
                "zone_identity_drift",
            )
            routes = self._get(f"/client/v4/zones/{zone_id}/workers/routes")
            need(isinstance(routes, list) and len(routes) < 1000, "route_list_invalid")
            for item in routes:
                need(
                    isinstance(item, dict)
                    and isinstance(item.get("pattern"), str)
                    and "script" in item,
                    "route_shape",
                )
                if item.get("script") == WORKER:
                    pattern = item["pattern"]
                    need(
                        pattern not in found and ROUTES.get(pattern) == zone_name,
                        "route_drift",
                    )
                    found[pattern] = zone_name
        need(found == ROUTES, "route_set_drift")
        return found

    def read_snapshot(self, *, allow_latest_difference=False):
        latest = self._versions()
        deployment_id, active = self._deployment()
        need(
            latest == active or self.uploads == 1 or allow_latest_difference,
            "latest_active_unexpected",
        )
        routes = self._routes()
        metadata_cache = {}
        code_cache = {}
        for version_id in {active, latest}:
            metadata_cache[version_id] = self._version_metadata(version_id)
            code_cache[version_id] = self._code_sha(version_id)
        active_bindings, active_config = metadata_cache[active]
        latest_bindings, latest_config = metadata_cache[latest]
        return {
            "schema": "ausmalwiese.stats-worker-protected-inventory.v1",
            "account_sha256": ACCOUNT_SHA256,
            "worker": WORKER,
            "environment": "production",
            "active_version": active,
            "latest_uploaded_version": latest,
            "deployment_id": deployment_id,
            "traffic_percent": 100,
            "routes": routes,
            "active_bindings": active_bindings,
            "latest_bindings": latest_bindings,
            "active_configuration": active_config,
            "latest_configuration": latest_config,
            "active_code_sha256": code_cache[active],
            "latest_code_sha256": code_cache[latest],
        }

    def upload_version_once(
        self, *, module_name, module_bytes, metadata, bindings_inherit
    ):
        need(module_name == "stats-worker.js", "upload_module_name")
        need(
            isinstance(module_bytes, bytes)
            and 0 < len(module_bytes) <= 196608
            and git_blob(module_bytes) == WORKER_BLOB,
            "upload_source_invalid",
        )
        need(bindings_inherit == "strict", "upload_inherit_invalid")
        need(BOUNDARY.encode("ascii") not in module_bytes, "upload_boundary_collision")
        meta = dict(metadata)
        meta["annotations"] = {
            "workers/commit_sha": APP_SHA,
            "workers/message": (
                "source-blob:" + WORKER_BLOB + ",config-blob:" + CONFIG_BLOB
            ),
            "workers/tag": "ausmalwiese-stats-cutover",
        }
        metadata_raw = canonical(meta)
        boundary = BOUNDARY.encode("ascii")
        body = b"".join([
            b"--" + boundary + b"\r\n",
            b'Content-Disposition: form-data; name="metadata"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            metadata_raw,
            b"\r\n--" + boundary + b"\r\n",
            b'Content-Disposition: form-data; name="stats-worker.js"; filename="stats-worker.js"\r\n',
            b"Content-Type: application/javascript+module\r\n\r\n",
            module_bytes,
            b"\r\n--" + boundary + b"--\r\n",
        ])
        need(len(body) <= MAX_UPLOAD, "upload_body_oversize")
        payload = self._request(
            "POST",
            f"/client/v4/accounts/{self.account}/workers/scripts/{WORKER}"
            "/versions?bindings_inherit=strict",
            body=body,
            content_type="multipart/form-data; boundary=" + BOUNDARY,
            phase="upload",
        )
        result = self._unwrap(payload)
        need(
            isinstance(result, dict)
            and isinstance(result.get("id"), str)
            and UUID.fullmatch(result["id"]) is not None,
            "upload_response_invalid",
        )
        return {"version_id": result["id"]}

    def deploy_version_once(self, *, payload):
        raw = canonical(payload)
        need(len(raw) <= 8192, "deploy_body_oversize")
        response = self._request(
            "POST",
            f"/client/v4/accounts/{self.account}/workers/scripts/{WORKER}/deployments",
            body=raw,
            content_type="application/json",
            phase="deploy",
        )
        result = self._unwrap(response)
        need(
            isinstance(result, dict)
            and isinstance(result.get("id"), str)
            and UUID.fullmatch(result["id"]) is not None,
            "deploy_response_invalid",
        )
        return {"deployment_id": result["id"]}


def snapshot_digest(snapshot) -> str:
    return hashlib.sha256(canonical(snapshot)).hexdigest()


def preflight(core, trusted, worker_bytes):
    core.verify_source(worker_bytes)
    try:
        before = core.validate_snapshot(trusted.read_snapshot())
        confirm = core.validate_snapshot(trusted.read_snapshot())
    except Exception:
        raise Stop("preflight_read_failed") from None
    need(before == confirm, "preflight_state_drift")
    candidate = hashlib.sha256(worker_bytes).hexdigest()
    return {
        "schema": "rozkalns.rpi5-main.stats-worker-preflight.v1",
        "worker": WORKER,
        "source_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "active_version": before["active_version"],
        "latest_uploaded_version": before["latest_uploaded_version"],
        "snapshot_sha256": snapshot_digest(before),
        "candidate_code_sha256": candidate,
        "mutation_required": before["active_code_sha256"] != candidate,
        "status": "PASS",
    }


def _recovery_state(core, trusted, worker_bytes):
    core.verify_source(worker_bytes)
    try:
        before = core.validate_snapshot(
            trusted.read_snapshot(allow_latest_difference=True),
            allow_latest_difference=True,
        )
        confirm = core.validate_snapshot(
            trusted.read_snapshot(allow_latest_difference=True),
            allow_latest_difference=True,
        )
    except Exception:
        raise Stop("recovery_read_failed") from None
    need(before == confirm, "recovery_state_drift")
    candidate = hashlib.sha256(worker_bytes).hexdigest()
    need(
        before["latest_uploaded_version"] != before["active_version"],
        "recovery_not_required",
    )
    need(
        before["latest_code_sha256"] == candidate
        and before["active_code_sha256"] != candidate,
        "recovery_candidate_state_invalid",
    )
    need(
        before["active_bindings"] == before["latest_bindings"],
        "recovery_binding_drift",
    )
    need(
        before["active_configuration"] == before["latest_configuration"],
        "recovery_configuration_drift",
    )
    return before, candidate


def recovery_preflight(core, trusted, worker_bytes):
    before, candidate = _recovery_state(core, trusted, worker_bytes)
    return {
        "schema": "rozkalns.rpi5-main.stats-worker-recovery-preflight.v1",
        "worker": WORKER,
        "source_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "snapshot_sha256": snapshot_digest(before),
        "candidate_code_sha256": candidate,
        "recovery_required": True,
        "provider_writes": 0,
        "status": "PASS",
    }


def deploy_existing(core, trusted, worker_bytes, expected_recovery_sha256):
    before, candidate = _recovery_state(core, trusted, worker_bytes)
    need(
        snapshot_digest(before) == expected_recovery_sha256,
        "recovery_snapshot_binding_drift",
    )
    target = before["latest_uploaded_version"]
    previous_deployment = before["deployment_id"]
    try:
        deployment = trusted.deploy_version_once(
            payload=core.deployment_payload(target)
        )
    except Exception:
        raise Stop("recovery_deploy_outcome_unknown_stop") from None
    need(
        isinstance(deployment, dict)
        and set(deployment) == {"deployment_id"}
        and isinstance(deployment["deployment_id"], str)
        and UUID.fullmatch(deployment["deployment_id"]) is not None,
        "recovery_deploy_reply_outcome_unknown_stop",
    )
    try:
        after = core.validate_snapshot(trusted.read_snapshot())
        need(
            after["active_version"] == target
            and after["latest_uploaded_version"] == target
            and after["deployment_id"] != previous_deployment
            and after["deployment_id"] == deployment["deployment_id"],
            "recovery_post_deploy_version_drift",
        )
        need(
            after["active_code_sha256"] == candidate
            and after["latest_code_sha256"] == candidate,
            "recovery_post_deploy_code_drift",
        )
        need(
            after["routes"] == before["routes"]
            and after["active_bindings"] == before["latest_bindings"]
            and after["latest_bindings"] == before["latest_bindings"]
            and after["active_configuration"] == before["latest_configuration"]
            and after["latest_configuration"] == before["latest_configuration"],
            "recovery_post_deploy_preservation_drift",
        )
    except Exception:
        raise Stop("recovery_post_deploy_outcome_unknown_stop") from None
    return {
        "schema": "rozkalns.rpi5-main.stats-worker-recovery-apply.v1",
        "worker": WORKER,
        "source_blob": WORKER_BLOB,
        "config_blob": CONFIG_BLOB,
        "candidate_code_sha256": candidate,
        "provider_writes": 1,
        "status": "PASS",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixed installed Ausmalwiese Stats Worker deploy runtime"
    )
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--expected-source-blob", required=True)
    parser.add_argument("--expected-config-blob", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--recovery-preflight", action="store_true")
    mode.add_argument("--deploy-existing", action="store_true")
    parser.add_argument("--expected-preflight-sha256", default="")
    parser.add_argument("--expected-recovery-sha256", default="")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)

    try:
        if (
            args.expected_source_blob != WORKER_BLOB
            or args.expected_config_blob != CONFIG_BLOB
        ):
            raise Stop("owner_provenance_binding_invalid")
        if args.preflight:
            if (
                args.confirm != PRE_CONFIRM
                or args.expected_preflight_sha256
                or args.expected_recovery_sha256
            ):
                raise Stop("preflight_confirmation_invalid")
        elif args.apply:
            if (
                args.confirm != APPLY_CONFIRM
                or SHA64.fullmatch(args.expected_preflight_sha256) is None
                or args.expected_recovery_sha256
            ):
                raise Stop("apply_confirmation_invalid")
        elif args.recovery_preflight:
            if (
                args.confirm != RECOVERY_PRE_CONFIRM
                or args.expected_preflight_sha256
                or args.expected_recovery_sha256
            ):
                raise Stop("recovery_preflight_confirmation_invalid")
        elif (
            args.confirm != RECOVERY_DEPLOY_CONFIRM
            or args.expected_preflight_sha256
            or SHA64.fullmatch(args.expected_recovery_sha256) is None
        ):
            raise Stop("recovery_deploy_confirmation_invalid")

        core_raw, worker_bytes, config_bytes = verified_install(args.expected_main)
        core = load_core(core_raw)
        if git_blob(config_bytes) != CONFIG_BLOB:
            raise Stop("config_identity_invalid")
        account, token, zones = credential()
        trusted = CloudflareTransport(
            account,
            token,
            zones,
            allow_deploy_existing=args.deploy_existing,
        )

        if args.preflight:
            result = preflight(core, trusted, worker_bytes)
        elif args.recovery_preflight:
            result = recovery_preflight(core, trusted, worker_bytes)
        elif args.deploy_existing:
            result = deploy_existing(
                core,
                trusted,
                worker_bytes,
                args.expected_recovery_sha256,
            )
        else:
            approval = {
                "source_blob": WORKER_BLOB,
                "config_blob": CONFIG_BLOB,
                "worker": WORKER,
                "preflight_sha256": args.expected_preflight_sha256,
                "allow_upload_once": True,
                "allow_deploy_once": True,
            }
            outcome = core.future_run_once(trusted, approval, worker_bytes)
            result = {
                "schema": "rozkalns.rpi5-main.stats-worker-apply.v1",
                "status": "PASS",
                "worker": WORKER,
                "source_blob": WORKER_BLOB,
                "config_blob": CONFIG_BLOB,
                "new_version": outcome["new_version"],
                "provider_writes": 2,
            }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        reason = str(exc)
        uncertain = reason.endswith("_outcome_unknown_stop")
        print(json.dumps({
            "status": "STOP_ERROR" if uncertain else "BLOCKED",
            "reason": reason,
            "credential_content_emitted": False,
            "provider_body_emitted": False,
        }, sort_keys=True, separators=(",", ":")))
        return 4 if uncertain else 3
    except Exception:
        print('{"credential_content_emitted":false,"provider_body_emitted":false,'
              '"reason":"trusted_runtime_failed","status":"STOP_ERROR"}')
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
