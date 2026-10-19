#!/usr/bin/env python3
"""SOURCE ONLY: fixed installed runtime for Ausmalwiese legacy redirect write.

A source merge does not install or run this program. Future execution requires
separate exact LIVE authority. Credentials are read only from one protected,
root-owned file after installed release verification; never argv/env/stdin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
from typing import Any

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-redirect-write")
PROVISIONER = Path("/usr/local/sbin/rpi5-ausmalwiese-redirect-write-provision")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-redirect-write")
INVENTORY = ROOT / "inventory.py"
ADAPTER = ROOT / "adapter.py"
WRITE = ROOT / "write.py"
RELEASE = ROOT / "release.json"
SECRET_DIR = Path("/etc/rpi5-secrets/cloudflare")
SECRET = SECRET_DIR / "ausmalwiese-redirect-write.json"
REPOSITORY = "rozkalnsandris/RPi5_main"
ZONE_NAME = "rozkalns.net"
PRE_CONFIRM = "OWNER-AUTHORIZED-REDIRECT-WRITE-PREFLIGHT"
APPLY_CONFIRM = "OWNER-AUTHORIZED-REDIRECT-WRITE-APPLY"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ZONE_ID = re.compile(r"[0-9a-f]{32}\Z")
CORE_CODE = re.compile(r"[A-Z0-9_]{1,96}\Z")
MAX_SECRET = 8192


class Stop(Exception):
    """Stable public-safe runtime reason only."""


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
        def constant(_):
            raise ValueError("constant")
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeError, ValueError, TypeError):
        raise Stop("json_invalid") from None


def verified_install(expected_main: str) -> tuple[bytes, bytes, bytes]:
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    package = {
        "launcher_sha256": guarded_bytes(ENTRY, 0o500, 131072),
        "provisioner_sha256": guarded_bytes(PROVISIONER, 0o500, 131072),
        "inventory_sha256": guarded_bytes(INVENTORY, 0o400, 131072),
        "adapter_sha256": guarded_bytes(ADAPTER, 0o400, 131072),
        "write_sha256": guarded_bytes(WRITE, 0o400, 196608),
    }
    meta = strict_json(guarded_bytes(RELEASE, 0o400, 8192))
    fields = {
        "schema_version", "repository", "source_sha", "zone_name",
        *package.keys(),
    }
    if (
        not isinstance(meta, dict)
        or set(meta) != fields
        or meta["schema_version"] != 1
        or meta["repository"] != REPOSITORY
        or meta["source_sha"] != expected_main
        or meta["zone_name"] != ZONE_NAME
    ):
        raise Stop("release_identity_invalid")
    for key, raw in package.items():
        digest = meta.get(key)
        if (
            not isinstance(digest, str)
            or SHA64.fullmatch(digest) is None
            or hashlib.sha256(raw).hexdigest() != digest
        ):
            raise Stop("release_identity_invalid")
    return (
        package["inventory_sha256"],
        package["adapter_sha256"],
        package["write_sha256"],
    )


def credential() -> tuple[str, str]:
    safe_parents(SECRET)
    try:
        directory = SECRET_DIR.lstat()
    except OSError:
        raise Stop("credential_directory_unavailable") from None
    if (
        not stat.S_ISDIR(directory.st_mode)
        or stat.S_ISLNK(directory.st_mode)
        or directory.st_uid != 0
        or directory.st_gid != 0
        or stat.S_IMODE(directory.st_mode) != 0o700
    ):
        raise Stop("credential_directory_untrusted")
    obj = strict_json(guarded_bytes(SECRET, 0o600, MAX_SECRET))
    if not isinstance(obj, dict) or set(obj) != {"zone_name", "zone_id", "api_token"}:
        raise Stop("credential_invalid")
    zone_id, token = obj.get("zone_id"), obj.get("api_token")
    if (
        obj.get("zone_name") != ZONE_NAME
        or not isinstance(zone_id, str)
        or ZONE_ID.fullmatch(zone_id) is None
        or not isinstance(token, str)
        or not 16 <= len(token) <= 512
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
    ):
        raise Stop("credential_invalid")
    return zone_id, token


def load_write(inventory_raw: bytes, adapter_raw: bytes, write_raw: bytes):
    names = (
        "ausmalwiese_redirect_inventory",
        "ausmalwiese_redirect_get_adapter",
        "ausmalwiese_redirect_write_v1",
    )
    if any(name in sys.modules for name in names):
        raise Stop("module_namespace_occupied")
    created = []
    try:
        inventory = types.ModuleType(names[0])
        inventory.__file__ = str(INVENTORY)
        exec(compile(inventory_raw, str(INVENTORY), "exec"), inventory.__dict__)
        sys.modules[names[0]] = inventory
        created.append(names[0])

        adapter = types.ModuleType(names[1])
        adapter.__file__ = str(ADAPTER)
        exec(compile(adapter_raw, str(ADAPTER), "exec"), adapter.__dict__)
        sys.modules[names[1]] = adapter
        created.append(names[1])

        write = types.ModuleType(names[2])
        write.__file__ = str(WRITE)
        exec(compile(write_raw, str(WRITE), "exec"), write.__dict__)
        sys.modules[names[2]] = write
        created.append(names[2])
        return write
    except Stop:
        raise
    except Exception:
        raise Stop("installed_source_load_failed") from None
    finally:
        for name in reversed(created):
            sys.modules.pop(name, None)


def core_call(expected_main: str, *, expected_baseline: str | None) -> dict[str, Any]:
    inventory_raw, adapter_raw, write_raw = verified_install(expected_main)
    zone_id, token = credential()
    write = load_write(inventory_raw, adapter_raw, write_raw)
    try:
        transport = write.FixedZoneRedirectWriteTransport(zone_id, token)
        if expected_baseline is None:
            result = write.preflight(transport, zone_id)
            required = {
                "schema", "zone_name", "phase", "legacy_hostname",
                "baseline_sha256", "operation", "mutation_required",
                "safe_to_apply",
            }
            if (
                type(result) is not dict
                or set(result) != required
                or result.get("zone_name") != ZONE_NAME
                or result.get("safe_to_apply") is not False
                or SHA64.fullmatch(result.get("baseline_sha256", "")) is None
            ):
                raise Stop("sanitized_preflight_invalid")
            return result
        result = write.run_once(transport, zone_id, expected_baseline)
        required = {
            "schema", "status", "operation", "mutation_started",
            "pre_baseline_sha256", "post_baseline_sha256",
        }
        if (
            type(result) is not dict
            or set(result) != required
            or result.get("status") != "PASS"
            or type(result.get("mutation_started")) is not bool
            or SHA64.fullmatch(result.get("pre_baseline_sha256", "")) is None
            or SHA64.fullmatch(result.get("post_baseline_sha256", "")) is None
        ):
            raise Stop("sanitized_result_invalid")
        return result
    except Stop:
        raise
    except Exception as exc:
        code = str(exc)
        if exc.__class__.__name__ == "WriteBlocked" and CORE_CODE.fullmatch(code):
            raise Stop("write_" + code.lower()) from None
        raise Stop("trusted_runtime_failed") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed Ausmalwiese legacy redirect runtime")
    parser.add_argument("--expected-main", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-baseline")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            if args.confirm != PRE_CONFIRM or args.expected_baseline is not None:
                raise Stop("confirmation_or_mode_invalid")
            result = core_call(args.expected_main, expected_baseline=None)
        else:
            if (
                args.confirm != APPLY_CONFIRM
                or not isinstance(args.expected_baseline, str)
                or SHA64.fullmatch(args.expected_baseline) is None
            ):
                raise Stop("confirmation_or_baseline_invalid")
            result = core_call(
                args.expected_main,
                expected_baseline=args.expected_baseline,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except Stop as exc:
        print(json.dumps({
            "status": "STOP",
            "reason": str(exc),
            "credential_content_emitted": False,
        }, sort_keys=True, separators=(",", ":")))
        return 3
    except Exception:
        print('{"credential_content_emitted":false,"reason":"trusted_runtime_failed","status":"STOP"}')
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
