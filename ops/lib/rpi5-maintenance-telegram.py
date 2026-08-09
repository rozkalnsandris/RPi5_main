#!/usr/bin/env python3
"""Send a bounded Telegram message using systemd credentials.

Expected credential names under $CREDENTIALS_DIRECTORY:
- telegram-token
- telegram-chat-id

The credential values are never accepted through argv or dedicated secret
environment variables. The message is read from stdin.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK_LIMIT = 3800


def read_credential(directory: Path, name: str) -> str:
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing credential: {name}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"empty credential: {name}")
    return value


def chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    if not text:
        return []
    result: list[str] = []
    current = ""
    for line in text.splitlines() or [""]:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            result.append(current)
            current = ""
        while len(line) > limit:
            result.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        result.append(current)
    return result


def send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in chunks(text):
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
            if not body.get("ok"):
                raise RuntimeError("Telegram API returned ok=false")


def main() -> int:
    credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if not credentials_directory:
        print("Telegram notifier: CREDENTIALS_DIRECTORY is not set", file=sys.stderr)
        return 2

    directory = Path(credentials_directory)
    message = sys.stdin.read().strip()
    if not message:
        return 0

    try:
        token = read_credential(directory, "telegram-token")
        chat_id = read_credential(directory, "telegram-chat-id")
        send(token, chat_id, message)
    except urllib.error.HTTPError as exc:
        print(f"Telegram notifier: HTTP error {exc.code}", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Telegram notifier: network error", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Telegram notifier: {type(exc).__name__}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
