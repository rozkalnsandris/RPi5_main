#!/usr/bin/env python3
"""SOURCE ONLY: fixed owner-TTY provisioner for redirect write credential.

Never run the repository copy as root. Future use requires separately
authorized installation and credential provisioning. No Cloudflare call occurs.
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
import termios

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-redirect-write-provision")
RUNTIME = Path("/usr/local/sbin/rpi5-ausmalwiese-redirect-write")
ROOT = Path("/usr/local/libexec/rpi5-ausmalwiese-redirect-write")
INVENTORY = ROOT / "inventory.py"
ADAPTER = ROOT / "adapter.py"
WRITE = ROOT / "write.py"
RELEASE = ROOT / "release.json"
DIRECTORY = Path("/etc/rpi5-secrets/cloudflare")
TARGET = DIRECTORY / "ausmalwiese-redirect-write.json"
REPOSITORY = "rozkalnsandris/RPi5_main"
ZONE_NAME = "rozkalns.net"
CONFIRM = "OWNER-AUTHORIZED-REDIRECT-WRITE-CREDENTIAL-PROVISION"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
ZONE_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_CREDENTIAL_BYTES = 8192


class Stop(Exception):
    """Static non-secret failure reason."""


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


def strict_json(raw: bytes):
    try:
        def pairs(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError("duplicate")
                out[key] = value
            return out
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, ValueError, TypeError):
        raise Stop("release_invalid") from None


def trusted_entry() -> None:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    guarded_bytes(ENTRY, 0o500, 131072)


def validated_release(expected_main: str) -> None:
    if not isinstance(expected_main, str) or SHA40.fullmatch(expected_main) is None:
        raise Stop("expected_main_invalid")
    package = {
        "launcher_sha256": guarded_bytes(RUNTIME, 0o500, 131072),
        "provisioner_sha256": guarded_bytes(ENTRY, 0o500, 131072),
        "inventory_sha256": guarded_bytes(INVENTORY, 0o400, 131072),
        "adapter_sha256": guarded_bytes(ADAPTER, 0o400, 131072),
        "write_sha256": guarded_bytes(WRITE, 0o400, 196608),
    }
    meta = strict_json(guarded_bytes(RELEASE, 0o400, 8192))
    if (
        not isinstance(meta, dict)
        or set(meta) != {
            "schema_version", "repository", "source_sha", "zone_name",
            *package.keys(),
        }
        or meta["schema_version"] != 1
        or meta["repository"] != REPOSITORY
        or meta["source_sha"] != expected_main
        or meta["zone_name"] != ZONE_NAME
    ):
        raise Stop("release_invalid")
    for key, raw in package.items():
        digest = meta.get(key)
        if (
            not isinstance(digest, str)
            or SHA64.fullmatch(digest) is None
            or hashlib.sha256(raw).hexdigest() != digest
        ):
            raise Stop("release_invalid")


def guarded_directory() -> tuple[int, tuple[int, int]]:
    safe_parents(TARGET)
    try:
        info = DIRECTORY.lstat()
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
    try:
        fd = os.open(
            DIRECTORY,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except OSError:
        raise Stop("credential_directory_untrusted") from None
    current = os.fstat(fd)
    return fd, (current.st_dev, current.st_ino)


def absent(dir_fd: int) -> None:
    try:
        os.stat(TARGET.name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        raise Stop("credential_state_unknown") from None
    raise Stop("credential_already_exists")


def read_private(fd: int, prompt: bytes, maximum: int) -> str:
    try:
        original = termios.tcgetattr(fd)
    except Exception:
        raise Stop("controlling_tty_required") from None
    changed = list(original)
    changed[3] &= ~(termios.ECHO | termios.ECHONL | termios.ECHOE | termios.ECHOK)
    data = bytearray()
    try:
        termios.tcsetattr(fd, termios.TCSANOW, changed)
        os.write(fd, prompt)
        while len(data) <= maximum:
            ch = os.read(fd, 1)
            if ch in (b"\n", b"\r"):
                break
            if len(ch) != 1:
                raise Stop("private_input_invalid")
            data.extend(ch)
        else:
            raise Stop("private_input_invalid")
        os.write(fd, b"\n")
        try:
            return data.decode("ascii")
        except UnicodeError:
            raise Stop("private_input_invalid") from None
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        finally:
            for index in range(len(data)):
                data[index] = 0


def owner_tty_values() -> tuple[str, str]:
    try:
        tty = os.open("/dev/tty", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("controlling_tty_required") from None
    try:
        if not os.isatty(tty) or os.tcgetpgrp(tty) != os.getpgrp():
            raise Stop("controlling_tty_required")
        zone_id = read_private(tty, b"Cloudflare zone ID (hidden): ", 32)
        token = read_private(tty, b"Dynamic URL Redirects Write token (hidden): ", 512)
        return zone_id, token
    finally:
        os.close(tty)


def credential_bytes(zone_id: str, token: str) -> bytes:
    if not isinstance(zone_id, str) or ZONE_ID.fullmatch(zone_id) is None:
        raise Stop("zone_id_invalid")
    if (
        not isinstance(token, str)
        or not 16 <= len(token) <= 512
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
    ):
        raise Stop("token_invalid")
    raw = (
        json.dumps(
            {"zone_name": ZONE_NAME, "zone_id": zone_id, "api_token": token},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")
    if not 1 <= len(raw) <= MAX_CREDENTIAL_BYTES:
        raise Stop("credential_size_invalid")
    return raw


def exclusive_create(dir_fd: int, payload: bytes) -> None:
    fd = -1
    try:
        old_umask = os.umask(0o077)
        try:
            fd = os.open(
                TARGET.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=dir_fd,
            )
        finally:
            os.umask(old_umask)
        if os.write(fd, payload) != len(payload):
            raise Stop("post_dispatch_unknown_state")
        os.fsync(fd)
        os.fsync(dir_fd)
    except Stop:
        raise
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None
    finally:
        if fd >= 0:
            os.close(fd)


def run(expected_main: str) -> None:
    trusted_entry()
    validated_release(expected_main)
    directory_fd, identity = guarded_directory()
    try:
        zone_id, token = owner_tty_values()
        payload = credential_bytes(zone_id, token)
        current = DIRECTORY.lstat()
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != identity
            or stat.S_IMODE(current.st_mode) != 0o700
        ):
            raise Stop("credential_directory_drift")
        absent(directory_fd)
        exclusive_create(directory_fd, payload)
    finally:
        os.close(directory_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed owner-TTY redirect write credential provisioning")
    parser.add_argument("--expected-release-main", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print('{"credential_content_emitted":false,"reason":"confirmation_missing","status":"STOP"}')
        return 3
    try:
        run(args.expected_release_main)
        print('{"credential_content_emitted":false,"credential_file_created":true,"status":"PASS"}')
        return 0
    except Stop as exc:
        print(json.dumps({
            "status": "STOP",
            "reason": str(exc),
            "credential_content_emitted": False,
        }, sort_keys=True, separators=(",", ":")))
        return 4 if str(exc) == "post_dispatch_unknown_state" else 3
    except Exception:
        print('{"credential_content_emitted":false,"reason":"trusted_provisioner_failed","status":"STOP"}')
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
