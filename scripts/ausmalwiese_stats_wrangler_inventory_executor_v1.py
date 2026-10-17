#!/usr/bin/env python3
"""Protected future Stats Wrangler inventory runtime source (#1056).

SOURCE ONLY in this repository. The program is intended to run only after a
separately authorized, root-owned installation and separately authorized
credential access + three Cloudflare GETs. Repository-checkout execution is
rejected by the trusted entry check.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from typing import Any, Callable

WORKER = "coloring-pages-stats-v1"
HOST = "api.cloudflare.com"
ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-stats-wrangler-inventory")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-stats-wrangler-inventory")
NORMALIZER = ROOT / "normalizer.py"
RELEASE = ROOT / "release.json"
CREDENTIAL = Path(
    "/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json"
)

ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
BASELINE_VERSION = "e47f145f-1851-4917-be5c-387f96549539"
TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 65536
MAX_REQUESTS = 3
CONFIRM = "OWNER-AUTHORIZED-ONE-STATS-WRANGLER-INVENTORY"
ACCOUNT_RE = re.compile(r"[0-9a-f]{32}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
UUID_RE = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")


class Stop(Exception):
    """Static safe error code only."""


def strict_json(data: bytes) -> object:
    try:
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate")
                out[key] = value
            return out
        def constant(_: str):
            raise ValueError("constant")
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (ValueError, UnicodeError):
        raise Stop("json_invalid") from None


def safe_parents(path: Path) -> None:
    parent = path.parent
    while True:
        try:
            info = parent.lstat()
        except OSError:
            raise Stop("parent_untrusted") from None
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise Stop("parent_untrusted")
        if parent == parent.parent:
            return
        parent = parent.parent


def guarded_bytes(path: Path, mode: int, limit: int) -> bytes:
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
            or not 0 < info.st_size <= limit
        ):
            raise Stop("protected_file_invalid")
        data = os.read(fd, limit + 1)
        if len(data) != info.st_size:
            raise Stop("protected_file_invalid")
        return data
    finally:
        os.close(fd)


def trusted_entry() -> None:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    safe_parents(ENTRY)


def verified_install(expected_main: str) -> tuple[bytes, str]:
    if not isinstance(expected_main, str) or not SHA40.fullmatch(expected_main):
        raise Stop("expected_main_invalid")
    executor = guarded_bytes(ENTRY, 0o500, 196608)
    normalizer = guarded_bytes(NORMALIZER, 0o400, 196608)
    metadata = strict_json(guarded_bytes(RELEASE, 0o400, 8192))
    fields = {
        "schema_version",
        "repository",
        "source_sha",
        "worker",
        "executor_sha256",
        "normalizer_sha256",
        "account_sha256",
    }
    if not isinstance(metadata, dict) or set(metadata) != fields:
        raise Stop("release_identity_invalid")
    if (
        metadata["schema_version"] != 1
        or metadata["repository"] != "rozkalnsandris/RPi5_main"
        or metadata["source_sha"] != expected_main
        or metadata["worker"] != WORKER
        or metadata["account_sha256"] != ACCOUNT_SHA256
    ):
        raise Stop("release_identity_invalid")
    for key, payload in (
        ("executor_sha256", executor),
        ("normalizer_sha256", normalizer),
    ):
        digest = metadata[key]
        if (
            not isinstance(digest, str)
            or not SHA64.fullmatch(digest)
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            raise Stop("release_identity_invalid")
    return normalizer, metadata["account_sha256"]


def checked_credential(expected_account_digest: str) -> tuple[str, str]:
    obj = strict_json(guarded_bytes(CREDENTIAL, 0o600, 8192))
    if not isinstance(obj, dict) or set(obj) != {
        "worker",
        "account_id",
        "api_token",
    }:
        raise Stop("credential_invalid")
    account = obj["account_id"]
    token = obj["api_token"]
    if (
        obj["worker"] != WORKER
        or not isinstance(account, str)
        or not ACCOUNT_RE.fullmatch(account)
        or hashlib.sha256(account.encode("ascii")).hexdigest()
        != expected_account_digest
        or not isinstance(token, str)
        or not 20 <= len(token) <= 4096
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
    ):
        raise Stop("credential_invalid")
    return account, token


def load_normalizer(source: bytes) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "__name__": "ausmalwiese_stats_wrangler_inventory_installed",
        "__file__": str(NORMALIZER),
    }
    try:
        exec(compile(source, str(NORMALIZER), "exec"), scope)
    except Exception:
        raise Stop("normalizer_load_failed") from None
    required = {
        "request_specs",
        "decode_reply",
        "parse_versions",
        "build_inventory",
        "canonical_sha256",
    }
    if not required.issubset(scope):
        raise Stop("normalizer_interface_invalid")
    return scope


def _expected_path(stage: str, version_id: str | None = None) -> str:
    base = (
        "/client/v4/accounts/{account_id}/workers/scripts/"
        + WORKER
    )
    if stage == "versions":
        return base + "/versions?page=1&per_page=2"
    if stage == "deployments":
        return base + "/deployments?page=1&per_page=2"
    if stage == "version_detail":
        if not isinstance(version_id, str) or not UUID_RE.fullmatch(version_id):
            raise Stop("version_id_invalid")
        return base + "/versions/" + version_id
    raise Stop("request_stage_invalid")


def validate_spec(
    spec: Any,
    *,
    stage: str,
    version_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(spec, dict) or set(spec) != {
        "stage",
        "method",
        "host",
        "path",
        "max_response_bytes",
        "timeout_s",
        "retries",
        "redirects",
    }:
        raise Stop("request_spec_invalid")
    if (
        spec["stage"] != stage
        or spec["method"] != "GET"
        or spec["host"] != HOST
        or spec["path"] != _expected_path(stage, version_id)
        or spec["max_response_bytes"] != MAX_RESPONSE_BYTES
        or spec["timeout_s"] != TIMEOUT_S
        or spec["retries"] != 0
        or spec["redirects"] != 0
    ):
        raise Stop("request_spec_invalid")
    return spec


def single_get(
    account: str,
    token: str,
    spec: dict[str, Any],
    decoder: Callable[[Any, Any, Any, Any], dict[str, Any]],
) -> dict[str, Any]:
    if (
        not isinstance(account, str)
        or not ACCOUNT_RE.fullmatch(account)
        or hashlib.sha256(account.encode("ascii")).hexdigest()
        != ACCOUNT_SHA256
        or not isinstance(token, str)
    ):
        raise Stop("request_identity_invalid")
    conn = None
    try:
        conn = http.client.HTTPSConnection(
            HOST,
            timeout=TIMEOUT_S,
            context=ssl.create_default_context(),
        )
        path = spec["path"].format(account_id=account)
        conn.request(
            "GET",
            path,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        reply = conn.getresponse()
        if reply.status != 200:
            raise Stop("upstream_get_failed")
        content_type = reply.getheader("Content-Type", "")
        encoding = reply.getheader("Content-Encoding", "identity")
        length = reply.getheader("Content-Length")
        if length is not None and (
            not length.isdecimal()
            or int(length) > MAX_RESPONSE_BYTES
        ):
            raise Stop("response_size_invalid")
        body = reply.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise Stop("response_size_invalid")
        return decoder(reply.status, content_type, encoding, body)
    except Stop:
        raise
    except Exception:
        raise Stop("trusted_get_failed") from None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _safe_output(snapshot: Any, digest: Any) -> dict[str, Any]:
    expected = {
        "schema",
        "worker",
        "environment",
        "wrangler_version",
        "source_commit",
        "source_blob",
        "config_blob",
        "source_class",
        "latest_uploaded_version",
        "active_versions",
        "compatibility_date",
        "compatibility_flags",
        "d1",
        "rate_limit",
        "secret_names",
        "plain_text_vars",
        "settings_sha256",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != expected:
        raise Stop("normalized_output_invalid")
    if not isinstance(digest, str) or not SHA64.fullmatch(digest):
        raise Stop("normalized_output_invalid")
    return {"inventory": snapshot, "inventory_sha256": digest}


def _stage_args(stage: str, new_version_id: str | None) -> dict[str, Any]:
    if stage == "after_upload":
        if not isinstance(new_version_id, str) or not UUID_RE.fullmatch(
            new_version_id
        ):
            raise Stop("new_version_required")
        return {"stage": stage, "new_version_id": new_version_id}
    if stage == "before":
        if new_version_id is not None:
            raise Stop("new_version_not_allowed")
        return {"stage": stage}
    raise Stop("stage_invalid")


def _validate_stage_snapshot(
    snapshot: dict[str, Any],
    *,
    stage: str,
    new_version_id: str | None,
) -> None:
    active = snapshot.get("active_versions")
    if (
        not isinstance(active, list)
        or len(active) != 1
        or not isinstance(active[0], dict)
        or active[0].get("version_id") != BASELINE_VERSION
        or active[0].get("percentage") != 100
    ):
        raise Stop("normalized_stage_invalid")
    if stage == "before":
        if (
            snapshot.get("source_class") != "script_api"
            or snapshot.get("latest_uploaded_version") != BASELINE_VERSION
        ):
            raise Stop("normalized_stage_invalid")
    elif stage == "after_upload":
        if (
            snapshot.get("source_class") != "wrangler_versions_upload"
            or snapshot.get("latest_uploaded_version") != new_version_id
        ):
            raise Stop("normalized_stage_invalid")
    else:
        raise Stop("stage_invalid")


def run_once(
    expected_main: str,
    *,
    stage: str,
    new_version_id: str | None = None,
) -> dict[str, Any]:
    kwargs = _stage_args(stage, new_version_id)
    trusted_entry()
    normalizer_bytes, account_digest = verified_install(expected_main)
    account, token = checked_credential(account_digest)
    normalizer = load_normalizer(normalizer_bytes)

    specs = normalizer["request_specs"]()
    if not isinstance(specs, list) or len(specs) != 2:
        raise Stop("request_plan_invalid")
    versions_spec = validate_spec(specs[0], stage="versions")
    deployments_spec = validate_spec(specs[1], stage="deployments")

    versions_payload = single_get(
        account, token, versions_spec, normalizer["decode_reply"]
    )
    latest_id, _ = normalizer["parse_versions"](versions_payload)
    if not isinstance(latest_id, str) or not UUID_RE.fullmatch(latest_id):
        raise Stop("latest_version_invalid")

    deployments_payload = single_get(
        account, token, deployments_spec, normalizer["decode_reply"]
    )
    specs = normalizer["request_specs"](latest_id)
    if not isinstance(specs, list) or len(specs) != MAX_REQUESTS:
        raise Stop("request_plan_invalid")
    detail_spec = validate_spec(
        specs[2],
        stage="version_detail",
        version_id=latest_id,
    )
    detail_payload = single_get(
        account, token, detail_spec, normalizer["decode_reply"]
    )

    try:
        snapshot = normalizer["build_inventory"](
            versions_payload,
            deployments_payload,
            detail_payload,
            **kwargs,
        )
        digest = normalizer["canonical_sha256"](snapshot)
    except Exception:
        raise Stop("normalization_failed") from None
    _validate_stage_snapshot(
        snapshot,
        stage=stage,
        new_version_id=new_version_id,
    )
    return _safe_output(snapshot, digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixed protected Stats Wrangler inventory GET runtime"
    )
    parser.add_argument("--expected-main", required=True)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("before", "after_upload"),
    )
    parser.add_argument("--new-version-id")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print("STOP: confirmation_missing", file=sys.stderr)
        return 3
    try:
        result = run_once(
            args.expected_main,
            stage=args.stage,
            new_version_id=args.new_version_id,
        )
        print(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        )
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 3
    except Exception:
        print("STOP: trusted_runtime_failed", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
