#!/usr/bin/env python3
"""SOURCE ONLY: future root-installed report Worker secrets provisioner.

Never run this repository copy as root. A future separately authorized LIVE
installation must pin and install these exact reviewed bytes as a root-owned
fixed executable. This program never contacts Cloudflare, Turnstile or Brevo.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import termios

ENTRY = Path("/usr/local/sbin/rpi5-ausmalwiese-report-secrets-provision")
DIRECTORY = Path("/etc/rpi5-secrets/cloudflare")
TARGET = DIRECTORY / "ausmalwiese-report-wrangler-secrets.json"
WORKER = "coloring-pages-report-v1"
CONFIRM = "OWNER-AUTHORIZED-REPORT-SECRETS-PROVISION"
SECRET_NAMES = (
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET",
    "BREVO_API_KEY",
    "REPORT_TO",
)
EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\."
    r"[A-Za-z]{2,63}\Z"
)
MAX_PAYLOAD_BYTES = 16384


class Stop(Exception):
    """Static safe error code only; never append owner input or exception text."""


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
    parent = path.parent
    while True:
        try:
            info = parent.lstat()
        except OSError:
            raise Stop("parent_untrusted") from None
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise Stop("parent_untrusted")
        if parent == parent.parent:
            return
        parent = parent.parent


def trusted_entry() -> None:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    safe_parents(ENTRY)
    safe_metadata(ENTRY, 0o500)


def absent(dir_fd: int) -> None:
    try:
        os.stat(TARGET.name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        raise Stop("target_state_unknown") from None
    raise Stop("secrets_file_already_exists")


def guarded_directory() -> tuple[int, tuple[int, int]]:
    safe_parents(TARGET)
    safe_metadata(DIRECTORY, 0o700, directory=True)
    try:
        fd = os.open(
            DIRECTORY,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
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


def read_private(fd: int, prompt: bytes, max_length: int) -> str:
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
        termios.tcsetattr(fd, termios.TCSANOW, original)
        for index in range(len(data)):
            data[index] = 0


def visible_secret(value: str, *, minimum: int, maximum: int, reason: str) -> str:
    if (not isinstance(value, str) or not minimum <= len(value) <= maximum
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in value)):
        raise Stop(reason)
    return value


def validate_values(values: dict[str, str]) -> dict[str, str]:
    if not isinstance(values, dict) or tuple(values) != SECRET_NAMES:
        raise Stop("secret_fields_invalid")
    visible_secret(values["TURNSTILE_SITE_KEY"], minimum=8, maximum=512,
                   reason="turnstile_site_key_invalid")
    visible_secret(values["TURNSTILE_SECRET"], minimum=8, maximum=4096,
                   reason="turnstile_secret_invalid")
    visible_secret(values["BREVO_API_KEY"], minimum=20, maximum=4096,
                   reason="brevo_api_key_invalid")
    report_to = values["REPORT_TO"]
    if (not isinstance(report_to, str) or len(report_to) > 320
            or EMAIL_RE.fullmatch(report_to) is None):
        raise Stop("report_to_invalid")
    return values


def owner_tty_values() -> dict[str, str]:
    try:
        tty = os.open("/dev/tty", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("controlling_tty_required") from None
    try:
        if not os.isatty(tty) or os.tcgetpgrp(tty) != os.getpgrp():
            raise Stop("controlling_tty_required")
        values = {
            "TURNSTILE_SITE_KEY": read_private(tty, b"TURNSTILE_SITE_KEY (hidden): ", 512),
            "TURNSTILE_SECRET": read_private(tty, b"TURNSTILE_SECRET (hidden): ", 4096),
            "BREVO_API_KEY": read_private(tty, b"BREVO_API_KEY (hidden): ", 4096),
            "REPORT_TO": read_private(tty, b"REPORT_TO (hidden): ", 320),
        }
        return validate_values(values)
    finally:
        os.close(tty)


def secrets_bytes(values: dict[str, str]) -> bytes:
    validate_values(values)
    payload = (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    if not 1 <= len(payload) <= MAX_PAYLOAD_BYTES:
        raise Stop("secrets_payload_size_invalid")
    return payload


def exclusive_create(dir_fd: int, payload: bytes) -> None:
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
        try:
            if os.write(fd, payload) != len(payload):
                raise Stop("post_dispatch_unknown_state")
            os.fsync(fd)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or info.st_size != len(payload)):
                raise Stop("post_dispatch_unknown_state")
        finally:
            os.close(fd)
    except Exception:
        raise Stop("post_dispatch_unknown_state") from None


def run() -> None:
    trusted_entry()
    directory_fd, identity = guarded_directory()
    try:
        values = owner_tty_values()
        payload = secrets_bytes(values)
        safe_parents(TARGET)
        current = safe_metadata(DIRECTORY, 0o700, directory=True)
        if (current.st_dev, current.st_ino) != identity:
            raise Stop("parent_drift")
        absent(directory_fd)
        exclusive_create(directory_fd, payload)
    finally:
        os.close(directory_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fixed owner-TTY Ausmalwiese report secrets provisioning"
    )
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print("STOP: confirmation_missing", file=sys.stderr)
        return 3
    try:
        run()
        print(json.dumps({
            "status": "PASS",
            "worker": WORKER,
            "secrets_file_created": True,
            "secret_content_emitted": False,
        }, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 3
    except Exception:
        print("STOP: post_dispatch_state_unknown_or_preflight_failed", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
