"""Source-only fixed Cloudflare Worker settings GET executor.

Never execute from a repository checkout. Runtime requires a separately
reviewed root-owned installation, a dedicated Workers Scripts Read token,
and explicit owner permission. No OAuth cache or ambient credential fallback.
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

WORKER = "coloring-pages-stats-v1"
HOST = "api.cloudflare.com"
ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get")
RELEASE = ROOT / "release.json"
SANITIZER = ROOT / "sanitizer.py"
SECRET = Path("/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json")
PATH = "/client/v4/accounts/{account_id}/workers/scripts/" + WORKER + "/script-settings"
MAX_REPLY = 32768
ACCOUNT_RE = re.compile(r"[a-f0-9]{32}\Z")
SHA_RE = re.compile(r"[a-f0-9]{40}\Z")
DIGEST_RE = re.compile(r"[a-f0-9]{64}\Z")


class Stop(Exception):
    """Stable, credential-free failure code."""


def guard_parent(path: Path) -> None:
    parent = path.parent
    while True:
        try:
            s = parent.lstat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_gid != 0 or (s.st_mode & 0o022):
                raise Stop("parent_untrusted")
        except OSError:
            raise Stop("parent_untrusted") from None
        if parent == parent.parent:
            break
        parent = parent.parent


def guarded_bytes(path: Path, mode: int, limit: int) -> bytes:
    guard_parent(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("protected_file_unavailable") from None
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0
                or stat.S_IMODE(st.st_mode) != mode or st.st_nlink != 1
                or st.st_size < 1 or st.st_size > limit):
            raise Stop("protected_file_invalid")
        data = os.read(fd, limit + 1)
        if len(data) != st.st_size:
            raise Stop("protected_file_invalid")
        return data
    finally:
        os.close(fd)


def strict_json(data: bytes) -> object:
    try:
        def reject_constant(_: str):
            raise ValueError("invalid_constant")
        return json.loads(data.decode("utf-8"), parse_constant=reject_constant)
    except (ValueError, UnicodeError):
        raise Stop("json_invalid") from None


def verified_install(expected_main: str) -> tuple[bytes, str]:
    if not isinstance(expected_main, str) or not SHA_RE.fullmatch(expected_main):
        raise Stop("expected_main_invalid")
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("trusted_install_required")
    installed = guarded_bytes(ENTRY, 0o500, 131072)
    sanitizer = guarded_bytes(SANITIZER, 0o400, 65536)
    meta = strict_json(guarded_bytes(RELEASE, 0o400, 8192))
    fields = {"schema_version", "repository", "source_sha", "worker", "executor_sha256", "sanitizer_sha256", "account_sha256"}
    if not isinstance(meta, dict) or set(meta) != fields:
        raise Stop("release_identity_invalid")
    if (meta["schema_version"] != 1 or meta["repository"] != "rozkalnsandris/RPi5_main"
            or meta["source_sha"] != expected_main or meta["worker"] != WORKER):
        raise Stop("release_identity_invalid")
    if any(not isinstance(meta[k], str) or not DIGEST_RE.fullmatch(meta[k])
           for k in ("executor_sha256", "sanitizer_sha256", "account_sha256")):
        raise Stop("release_identity_invalid")
    if (hashlib.sha256(installed).hexdigest() != meta["executor_sha256"]
            or hashlib.sha256(sanitizer).hexdigest() != meta["sanitizer_sha256"]):
        raise Stop("release_identity_invalid")
    return sanitizer, meta["account_sha256"]


def checked_credential(expected_account_digest: str) -> tuple[str, str]:
    obj = strict_json(guarded_bytes(SECRET, 0o600, 8192))
    if not isinstance(obj, dict) or set(obj) != {"worker", "account_id", "api_token"}:
        raise Stop("credential_invalid")
    account, token = obj["account_id"], obj["api_token"]
    if (obj["worker"] != WORKER or not isinstance(account, str)
            or not ACCOUNT_RE.fullmatch(account)
            or hashlib.sha256(account.encode("ascii")).hexdigest() != expected_account_digest
            or not isinstance(token, str) or not 20 <= len(token) <= 4096
            or any(x.isspace() or ord(x) < 33 or ord(x) > 126 for x in token)):
        raise Stop("credential_invalid")
    return account, token


def single_get(account: str, token: str) -> object:
    """Exactly one HTTPS GET, no redirects, replay or raw upstream output."""
    if not isinstance(account, str) or not ACCOUNT_RE.fullmatch(account):
        raise Stop("target_invalid")
    conn = None
    try:
        conn = http.client.HTTPSConnection(HOST, timeout=10, context=ssl.create_default_context())
        conn.request("GET", PATH.format(account_id=account), headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        reply = conn.getresponse()
        if reply.status != 200:
            raise Stop("upstream_get_failed")
        typ = reply.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if typ != "application/json":
            raise Stop("response_type_invalid")
        encoding = reply.getheader("Content-Encoding", "identity").strip().lower()
        if encoding != "identity":
            raise Stop("response_encoding_invalid")
        length = reply.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > MAX_REPLY):
            raise Stop("response_size_invalid")
        raw = reply.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise Stop("response_size_invalid")
        return strict_json(raw)
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


def run_once(expected_main: str) -> dict:
    sanitizer_bytes, account_digest = verified_install(expected_main)
    account, token = checked_credential(account_digest)
    # The sanitizer is itself a pinned root-owned, hash-verified source file.
    scope = {"__name__": "ausmalwiese_trusted_sanitizer", "__file__": str(SANITIZER)}
    try:
        exec(compile(sanitizer_bytes, str(SANITIZER), "exec"), scope)
        clean = scope["sanitize_settings"](single_get(account, token))
        if type(clean) is not dict or clean.get("verified_get") is not True:
            raise Stop("sanitized_result_invalid")
        return clean
    except Stop:
        raise
    except Exception:
        raise Stop("sanitization_failed") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed Ausmalwiese Worker settings GET")
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != "OWNER-AUTHORIZED-ONE-SETTINGS-GET":
        print("STOP: confirmation_missing", file=sys.stderr)
        return 2
    try:
        result = run_once(args.expected_main)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("STOP: trusted_runtime_failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
