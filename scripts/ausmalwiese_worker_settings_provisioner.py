#!/usr/bin/env python3
"""SOURCE ONLY: future root-installed, owner-TTY credential provisioner.

Never run this repository copy as root. A future separately authorized LIVE
installation must pin and install these bytes as a root-owned fixed executable.
This program never provisions a token at Cloudflare or calls Cloudflare APIs.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import termios

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-worker-settings-provision")
DIRECTORY = Path("/etc/rpi5-secrets/cloudflare")
TARGET = DIRECTORY / "ausmalwiese-worker-settings-read.json"
EXECUTOR = Path("/usr/local/sbin/rpi5-ausmalwiese-worker-settings-get")
SANITIZER = Path("/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/sanitizer.py")
RELEASE = Path("/usr/local/libexec/rpi5-ausmalwiese-worker-settings-get/release.json")
WORKER = "coloring-pages-stats-v1"
# Exact immutable SHA of the *already installed* GET release, not the future
# source PR head. A new runtime release requires a separate reviewed update.
INSTALLED_RELEASE_SHA = "6c55e46d43889fed2a17770d0f466c79b1db736a"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
CONFIRM = "OWNER-AUTHORIZED-ONE-CREDENTIAL-PROVISION"
ACCOUNT_RE = re.compile(r"[0-9a-f]{32}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_CREDENTIAL_BYTES = 8192


class Stop(Exception):
    """Static safe error code only; do not append exceptions or user input."""


def strict_json(data: bytes) -> object:
    try:
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate")
                out[key] = value
            return out
        def constant(_):
            raise ValueError("invalid")
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (ValueError, UnicodeError):
        raise Stop("release_invalid") from None


def safe_metadata(path: Path, mode: int, *, directory: bool = False) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise Stop("protected_path_invalid") from None
    kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (not kind_ok or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != mode
            or (not directory and info.st_nlink != 1)):
        raise Stop("protected_path_invalid")
    return info


def safe_parents(path: Path) -> None:
    # All ancestors must be real root-owned directories not writable by others.
    parent = path.parent
    while True:
        try:
            s = parent.lstat()
        except OSError:
            raise Stop("parent_untrusted") from None
        if (not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_gid != 0
                or stat.S_IMODE(s.st_mode) & 0o022):
            raise Stop("parent_untrusted")
        if parent == parent.parent:
            return
        parent = parent.parent


def read_root_file(path: Path, mode: int, limit: int) -> bytes:
    safe_parents(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("protected_file_unavailable") from None
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_gid != 0
                or stat.S_IMODE(s.st_mode) != mode or s.st_nlink != 1
                or not 0 < s.st_size <= limit):
            raise Stop("protected_file_invalid")
        data = os.read(fd, limit + 1)
        if len(data) != s.st_size:
            raise Stop("protected_file_invalid")
        return data
    finally:
        os.close(fd)


def validated_release(expected_release: str) -> None:
    if expected_release != INSTALLED_RELEASE_SHA:
        raise Stop("stale_release_sha")
    main = read_root_file(EXECUTOR, 0o500, 131072)
    sanitizer = read_root_file(SANITIZER, 0o400, 65536)
    metadata = strict_json(read_root_file(RELEASE, 0o400, 8192))
    fields = {"schema_version", "repository", "source_sha", "worker",
              "executor_sha256", "sanitizer_sha256", "account_sha256"}
    if not isinstance(metadata, dict) or set(metadata) != fields:
        raise Stop("release_invalid")
    if (metadata["schema_version"] != 1
            or metadata["repository"] != "rozkalnsandris/RPi5_main"
            or metadata["source_sha"] != INSTALLED_RELEASE_SHA
            or metadata["worker"] != WORKER
            or metadata["account_sha256"] != ACCOUNT_SHA256):
        raise Stop("release_invalid")
    for key, payload in (("executor_sha256", main),
                         ("sanitizer_sha256", sanitizer)):
        digest = metadata[key]
        if (not isinstance(digest, str) or not SHA_RE.fullmatch(digest)
                or hashlib.sha256(payload).hexdigest() != digest):
            raise Stop("release_invalid")


def trusted_entry() -> None:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    safe_parents(ENTRY)
    safe_metadata(ENTRY, 0o500)


def guarded_directory() -> tuple[int, tuple[int, int]]:
    safe_parents(TARGET)
    # No parent creation, permission changes, or implicit secret-path reads.
    safe_metadata(DIRECTORY, 0o700, directory=True)
    try:
        fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY
                     | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("parent_untrusted") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700):
            raise Stop("parent_untrusted")
        absent(fd)
        return fd, (info.st_dev, info.st_ino)
    except BaseException:
        os.close(fd)
        raise


def absent(dir_fd: int) -> None:
    try:
        os.stat(TARGET.name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        raise Stop("target_state_unknown") from None
    raise Stop("credential_already_exists")


def read_private(fd: int, title: bytes, max_length: int) -> str:
    # Controlling TTY only, never stdin, argv, env, browser, or RDC output.
    try:
        original = termios.tcgetattr(fd)
    except Exception:
        raise Stop("controlling_tty_required") from None
    changed = list(original)
    changed[3] &= ~(termios.ECHO | termios.ECHONL | termios.ECHOE | termios.ECHOK)
    data = bytearray()
    try:
        termios.tcsetattr(fd, termios.TCSANOW, changed)
        os.write(fd, title)
        while len(data) <= max_length:
            ch = os.read(fd, 1)
            if ch in (b"\r", b"\n"):
                break
            if len(ch) != 1:
                raise Stop("private_input_invalid")
            data.extend(ch)
        else:
            raise Stop("private_input_invalid")
        os.write(fd, b"\n")
        return data.decode("ascii")
    except (OSError, UnicodeError):
        raise Stop("private_input_invalid") from None
    finally:
        # Restore ECHO even if owner input or decoding fails.
        termios.tcsetattr(fd, termios.TCSANOW, original)
        for i in range(len(data)):
            data[i] = 0


def owner_tty_values() -> tuple[str, str]:
    try:
        tty = os.open("/dev/tty", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("controlling_tty_required") from None
    try:
        if not os.isatty(tty) or os.tcgetpgrp(tty) != os.getpgrp():
            raise Stop("controlling_tty_required")
        account = read_private(tty, b"Cloudflare account ID (hidden): ", 32)
        if (not ACCOUNT_RE.fullmatch(account)
                or hashlib.sha256(account.encode("ascii")).hexdigest() != ACCOUNT_SHA256):
            raise Stop("account_binding_mismatch")
        token = read_private(tty, b"Workers Scripts Read token (hidden): ", 4096)
        return account, token
    finally:
        os.close(tty)


def credential_bytes(account: str, token: str) -> bytes:
    if (not isinstance(account, str) or not ACCOUNT_RE.fullmatch(account)
            or hashlib.sha256(account.encode("ascii")).hexdigest() != ACCOUNT_SHA256):
        raise Stop("account_binding_mismatch")
    if (not isinstance(token, str) or not 20 <= len(token) <= 4096
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)):
        raise Stop("token_format_invalid")
    payload = (json.dumps({"worker": WORKER, "account_id": account,
                           "api_token": token}, sort_keys=True,
                          separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(payload) > MAX_CREDENTIAL_BYTES:
        raise Stop("credential_size_invalid")
    return payload


def exclusive_create(dir_fd: int, payload: bytes) -> None:
    # Single exclusive destination creation. After os.open dispatch any
    # ambiguity is terminal; intentionally no unlink, retry or replacement.
    try:
        old_umask = os.umask(0o077)
        try:
            fd = os.open(TARGET.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=dir_fd)
        finally:
            os.umask(old_umask)
        try:
            if os.write(fd, payload) != len(payload):
                raise Stop("post_dispatch_unknown_state")
            os.fsync(fd)
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1
                    or st.st_size != len(payload)):
                raise Stop("post_dispatch_unknown_state")
        finally:
            os.close(fd)
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def run(expected_release: str) -> None:
    trusted_entry()
    validated_release(expected_release)
    directory_fd, identity = guarded_directory()
    try:
        account, token = owner_tty_values()
        payload = credential_bytes(account, token)
        # Revalidate directory inode and absence just before the one write.
        safe_parents(TARGET)
        current = safe_metadata(DIRECTORY, 0o700, directory=True)
        if (current.st_dev, current.st_ino) != identity:
            raise Stop("parent_drift")
        absent(directory_fd)
        exclusive_create(directory_fd, payload)
    finally:
        os.close(directory_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed private owner-TTY token provisioning")
    parser.add_argument("--expected-release-main", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print("STOP: confirmation_missing", file=sys.stderr)
        return 3
    try:
        run(args.expected_release_main)
        print('{"status":"PASS","credential_content_emitted":false}')
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 3
    except Exception:
        print("STOP: post_dispatch_state_unknown_or_preflight_failed", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
