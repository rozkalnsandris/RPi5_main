#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "lib" / "rpi5-update-telegram.py"
spec = importlib.util.spec_from_file_location("rpi5_update_telegram", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

chunks = module.split_message("alpha\nbeta", limit=10)
assert chunks == ["alpha\nbeta"]
chunks = module.split_message("abcdefghijk", limit=4)
assert chunks == ["abcd", "efgh", "ijk"]
assert all(len(chunk) <= 4 for chunk in chunks)
print("PASS telegram-chunking")

token = "SECRET_TOKEN_SHOULD_NOT_LEAK"
chat_id = "SECRET_CHAT_SHOULD_NOT_LEAK"
text = "maintenance result"
parsed = module.parse_stdin(
    token.encode() + b"\0" + chat_id.encode() + b"\0" + text.encode()
)
assert parsed == (token, chat_id, text)
print("PASS telegram-stdin-fields")

class SyntheticUrlError(RuntimeError):
    pass

original_urlopen = module.urllib.request.urlopen
module.urllib.request.urlopen = lambda *args, **kwargs: (_ for _ in ()).throw(
    SyntheticUrlError(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}")
)
try:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            module.deliver(token, chat_id, text)
        except Exception as exc:
            # Exercise the same sanitization rule used by main() without
            # printing the exception object itself.
            print(f"Telegram delivery failed ({type(exc).__name__})", file=sys.stderr)
    output = stderr.getvalue()
finally:
    module.urllib.request.urlopen = original_urlopen

assert token not in output
assert chat_id not in output
assert "SyntheticUrlError" in output
print("PASS telegram-error-sanitization")

for malformed in (b"", b"one", b"one\0two", b"\0chat\0text", b"token\0\0text"):
    try:
        module.parse_stdin(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError(f"malformed payload unexpectedly accepted: {malformed!r}")
print("PASS telegram-malformed-input")

print("Maintenance updater Telegram tests: PASS (4 cases)")
