#!/usr/bin/env python3
"""SOURCE ONLY: fixed Weather v7 Telegram credentials, installed-root TTY entry.

Source merge or copying this file never authorizes credential mutation.
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

ENTRY = Path("/usr/local/sbin/rpi5-weather-v7-telegram-credentials")
DIRECTORY = Path("/etc/credstore")
TARGETS = (
    ("telegram-token", "weather-v7-failure-telegram-token"),
    ("telegram-chat-id", "weather-v7-failure-telegram-chat-id"),
)
CONFIRM = "OWNER-AUTHORIZED-WEATHER-V7-TELEGRAM-CREDENTIALS"
BOT_TOKEN = re.compile(r"[0-9]{6,}:[A-Za-z0-9_-]{20,}\Z")
CHAT_ID = re.compile(r"-?[0-9]{1,20}\Z")
MAX_BYTES = 256


class Stop(Exception):
    """Public-safe static failure category; never include owner input."""


def safe_parents(path: Path) -> None:
    path = path.parent
    while True:
        try:
            info = path.lstat()
        except OSError:
            raise Stop("unsafe_parent") from None
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
            raise Stop("unsafe_parent")
        if path == path.parent:
            return
        path = path.parent


def trusted_entry() -> None:
    if os.geteuid() != 0 or str(Path(__file__).absolute()) != str(ENTRY):
        raise Stop("installed_root_entry_required")
    safe_parents(ENTRY)
    try:
        info = ENTRY.lstat()
    except OSError:
        raise Stop("installed_entry_untrusted") from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
            or info.st_gid != 0 or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o500):
        raise Stop("installed_entry_untrusted")


def directory() -> tuple[int, tuple[int, int]]:
    safe_parents(DIRECTORY)
    try:
        info = DIRECTORY.lstat()
    except OSError:
        raise Stop("credstore_directory_missing") from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
            or info.st_gid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
        raise Stop("credstore_directory_untrusted")
    try:
        fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY
                     | os.O_NOFOLLOW | os.O_CLOEXEC)
        actual = os.fstat(fd)
        if (not stat.S_ISDIR(actual.st_mode) or actual.st_uid != 0
                or actual.st_gid != 0 or actual.st_dev != info.st_dev
                or actual.st_ino != info.st_ino):
            raise Stop("credstore_directory_changed")
    except Exception:
        if "fd" in locals():
            os.close(fd)
        raise Stop("credstore_directory_untrusted") from None
    return fd, (actual.st_dev, actual.st_ino)


def targets_absent(fd: int) -> None:
    for _, filename in TARGETS:
        try:
            os.stat(filename, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError:
            raise Stop("credential_target_state_unknown") from None
        raise Stop("credential_target_exists")


def read_hidden(fd: int, prompt: bytes, limit: int) -> str:
    data = bytearray()
    try:
        original = termios.tcgetattr(fd)
    except Exception:
        raise Stop("controlling_tty_required") from None
    changed = original.copy()
    changed[3] &= ~(termios.ECHO | termios.ECHONL | termios.ECHOE | termios.ECHOK)
    try:
        termios.tcsetattr(fd, termios.TCSANOW, changed)
        os.write(fd, prompt)
        while len(data) <= limit:
            ch = os.read(fd, 1)
            if ch in (b"\n", b"\r"):
                break
            if not ch:
                raise Stop("private_input_invalid")
            data.extend(ch)
        else:
            raise Stop("private_input_invalid")
        os.write(fd, b"\n")
        try:
            return data.decode("ascii")
        except UnicodeDecodeError:
            raise Stop("private_input_invalid") from None
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        for index in range(len(data)):
            data[index] = 0


def values_from_owner_tty() -> tuple[str, str]:
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise Stop("controlling_tty_required") from None
    try:
        if not os.isatty(fd) or os.tcgetpgrp(fd) != os.getpgrp():
            raise Stop("controlling_tty_required")
        token = read_hidden(fd, b"Weather v7 BOT TOKEN (hidden): ", MAX_BYTES)
        chat = read_hidden(fd, b"Weather v7 CHAT ID (hidden): ", 20)
        validate_values(token, chat)
        return token, chat
    finally:
        os.close(fd)


def validate_values(token: str, chat: str) -> None:
    if (not isinstance(token, str) or len(token) >= MAX_BYTES
            or BOT_TOKEN.fullmatch(token) is None):
        raise Stop("bot_token_format_invalid")
    if not isinstance(chat, str) or CHAT_ID.fullmatch(chat) is None:
        raise Stop("chat_id_format_invalid")
    try:
        number = int(chat, 10)
    except ValueError:
        raise Stop("chat_id_format_invalid") from None
    if number == 0 or not -(2 ** 63) <= number < 2 ** 63:
        raise Stop("chat_id_format_invalid")


def exclusive_credential(fd: int, name: str, data: str) -> None:
    blob = data.encode("ascii") + b"\n"
    if not 1 <= len(blob) <= MAX_BYTES:
        raise Stop("credential_size_invalid")
    old_umask = os.umask(0o077)
    try:
        try:
            child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
        finally:
            os.umask(old_umask)
        try:
            if os.write(child, blob) != len(blob):
                raise Stop("post_mutation_unknown")
            os.fsync(child)
            info = os.fstat(child)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or info.st_size != len(blob)):
                raise Stop("post_mutation_unknown")
        finally:
            os.close(child)
    except Exception:
        raise Stop("post_mutation_unknown") from None


def run(*, check_only: bool) -> dict[str, object]:
    trusted_entry()
    fd, identity = directory()
    try:
        targets_absent(fd)
        if check_only:
            return {
                "result": "PREFLIGHT_PASS", "credentials_absent": 2,
                "credential_contents_read": False, "mutation_started": False,
            }
        token, chat = values_from_owner_tty()
        # Recheck both targets and trusted parent immediately before first write.
        safe_parents(DIRECTORY)
        latest = DIRECTORY.lstat()
        if (latest.st_dev, latest.st_ino) != identity:
            raise Stop("credstore_directory_changed")
        targets_absent(fd)
        # First create consumes the separately authorized credential LIVE gate.
        # Partial completion is terminal: never clean up/retry automatically.
        exclusive_credential(fd, TARGETS[0][1], token)
        exclusive_credential(fd, TARGETS[1][1], chat)
        return {
            "result": "PASS", "created_file_count": 2,
            "credential_contents_logged": False, "mutation_started": True,
            "automatic_retry": False, "automatic_cleanup": False,
        }
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weather v7 fixed private credentials")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--confirm")
    args = parser.parse_args(argv)
    if not args.check and args.confirm != CONFIRM:
        print("STOP: owner_confirmation_required", file=sys.stderr)
        return 3
    try:
        result = run(check_only=args.check)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Stop as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 3
    except Exception:
        # Do not stringify errors: they may contain the Telegram bot token.
        print("STOP: unexpected_error_or_mutation_state_unknown", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
