#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import os
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/rpi5-maintenance-telegram.py"
spec = importlib.util.spec_from_file_location("maintenance_telegram", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.chunks("a" * 3801) == ["a" * 3800, "a"]
assert module.chunks("") == []

with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    token = "synthetic-secret-token"
    chat = "123456"
    (directory / "telegram-token").write_text(token + "\n", encoding="utf-8")
    (directory / "telegram-chat-id").write_text(chat + "\n", encoding="utf-8")
    assert module.read_credential(directory, "telegram-token") == token
    assert module.read_credential(directory, "telegram-chat-id") == chat

    symlink = directory / "symlink-token"
    symlink.symlink_to(directory / "telegram-token")
    try:
        module.read_credential(directory, "symlink-token")
    except RuntimeError:
        pass
    else:
        raise AssertionError("symlink credential unexpectedly accepted")

old_env = os.environ.pop("CREDENTIALS_DIRECTORY", None)
old_stdin = module.sys.stdin
try:
    module.sys.stdin = io.StringIO("message")
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        assert module.main() == 2
    assert "CREDENTIALS_DIRECTORY" in stderr.getvalue()
finally:
    module.sys.stdin = old_stdin
    if old_env is not None:
        os.environ["CREDENTIALS_DIRECTORY"] = old_env

source = MODULE_PATH.read_text(encoding="utf-8")
assert "CREDENTIALS_DIRECTORY" in source
assert "telegram-token" in source
assert "telegram-chat-id" in source
assert "TELEGRAM_TOKEN" not in source
assert "TELEGRAM_CHAT_ID" not in source
assert "/etc/rpi-update.conf" not in source
assert "/home/" not in source

print("Maintenance Telegram credential tests: PASS")
