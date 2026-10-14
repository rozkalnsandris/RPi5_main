#!/usr/bin/env python3
"""Fixed installed Redirect Rules inventory launcher; source-only, not installed.

No CLI, credential acquisition, permissions, ambient token or Cloudflare writes.
A separately reviewed privileged caller MAY later inject a zone ID/read-only
token in memory under a new explicit owner REVIEW authorization.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-redirect-get")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-redirect-get")
INVENTORY = ROOT / "inventory.py"
ADAPTER = ROOT / "adapter.py"
RELEASE = ROOT / "release.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ZONE_RE = re.compile(r"[0-9a-f]{32}\Z")
REPO = "rozkalnsandris/RPi5_main"


class Stop(Exception):
    """Stable non-sensitive failure code only."""


def guarded_bytes(path: Path, mode: int, maximum: int) -> bytes:
    parent = path.parent
    while True:
        try:
            s = parent.lstat()
            if (not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_gid != 0
                    or stat.S_IMODE(s.st_mode) & 0o022):
                raise Stop("unsafe_parent")
        except OSError:
            raise Stop("unsafe_parent") from None
        if parent == parent.parent:
            break
        parent = parent.parent
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("installed_file_missing") from None
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_gid != 0
                or s.st_nlink != 1 or stat.S_IMODE(s.st_mode) != mode
                or not 0 < s.st_size <= maximum):
            raise Stop("installed_file_untrusted")
        content = os.read(fd, maximum + 1)
        if len(content) != s.st_size:
            raise Stop("installed_file_untrusted")
        return content
    finally:
        os.close(fd)


def installed_sources(expected_main: str) -> tuple[bytes, bytes]:
    if not isinstance(expected_main, str) or not SHA40.fullmatch(expected_main):
        raise Stop("invalid_source_sha")
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("trusted_install_required")
    launcher = guarded_bytes(ENTRY, 0o500, 131072)
    inventory = guarded_bytes(INVENTORY, 0o400, 131072)
    adapter = guarded_bytes(ADAPTER, 0o400, 131072)
    metadata = guarded_bytes(RELEASE, 0o400, 8192)
    try:
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("duplicate")
                obj[key] = value
            return obj
        record = json.loads(metadata.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, ValueError, TypeError):
        raise Stop("release_invalid") from None
    fields = {"schema_version", "repository", "source_sha", "zone_name",
              "launcher_sha256", "inventory_sha256", "adapter_sha256"}
    if (not isinstance(record, dict) or set(record) != fields
            or record["schema_version"] != 1 or record["repository"] != REPO
            or record["source_sha"] != expected_main or record["zone_name"] != "rozkalns.net"):
        raise Stop("release_invalid")
    content = (("launcher_sha256", launcher), ("inventory_sha256", inventory),
               ("adapter_sha256", adapter))
    for key, raw in content:
        actual = record.get(key)
        if not isinstance(actual, str) or not SHA64.fullmatch(actual):
            raise Stop("release_invalid")
        if hashlib.sha256(raw).hexdigest() != actual:
            raise Stop("installed_digest_mismatch")
    return inventory, adapter


def run_once(expected_main: str, zone_id: str, in_memory_read_token: str) -> dict:
    """Single bounded three-GET inventory after installed-file verification.

    No credential source is implemented. This is NOT a runtime authorization;
    an independently reviewed authorized caller must supply the values.
    """
    inventory_raw, adapter_raw = installed_sources(expected_main)
    if not isinstance(zone_id, str) or not ZONE_RE.fullmatch(zone_id):
        raise Stop("invalid_zone_id")
    if not isinstance(in_memory_read_token, str) or not 16 <= len(in_memory_read_token) <= 512:
        raise Stop("invalid_credential_input")
    name = "ausmalwiese_redirect_inventory"
    if name in sys.modules:
        raise Stop("module_namespace_occupied")
    # Both modules are verified root-owned sources. No repository import path.
    try:
        namespace = {"__name__": name, "__file__": str(INVENTORY)}
        exec(compile(inventory_raw, str(INVENTORY), "exec"), namespace)
        import types
        module = types.ModuleType(name)
        module.__dict__.update(namespace)
        sys.modules[name] = module
        try:
            adapter_scope = {"__name__": "trusted_redirect_adapter", "__file__": str(ADAPTER)}
            exec(compile(adapter_raw, str(ADAPTER), "exec"), adapter_scope)
            result = adapter_scope["sanitized_redirect_inventory"](zone_id, in_memory_read_token)
        finally:
            del sys.modules[name]
    except Stop:
        raise
    except Exception:
        raise Stop("trusted_inventory_failed") from None
    if (type(result) is not dict
            or result.get("schema") != "rozkalns.rpi5-main.redirect-inventory-sanitized.v1"
            or result.get("zone_name") != "rozkalns.net"
            or result.get("account_level_checked") is not False
            or result.get("safe_to_apply") is not False):
        raise Stop("sanitized_result_invalid")
    return result


# No __main__, no argv/env/stdin token, no file credential, no API write.
