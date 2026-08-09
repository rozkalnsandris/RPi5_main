#!/usr/bin/env python3
"""Bounded Telegram notifier for RPi5 maintenance.

Input is exactly three UTF-8 fields separated by NUL bytes on stdin:
TOKEN\0CHAT_ID\0TEXT

Secrets are intentionally not accepted in argv or process environment.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

CHUNK_LIMIT = 3800


def split_message(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    if limit <= 0:
        raise ValueError("limit must be positive")

    chunks: list[str] = []
    current = ""
    for line in text.splitlines() or [""]:
        candidate = line if not current else current + "\n" + line
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line

    if current or not chunks:
        chunks.append(current)
    return chunks


def parse_stdin(payload: bytes) -> tuple[str, str, str]:
    parts = payload.split(b"\0", 2)
    if len(parts) != 3:
        raise ValueError("expected TOKEN, CHAT_ID and TEXT fields")
    token, chat_id, text = (part.decode("utf-8") for part in parts)
    if not token or not chat_id:
        raise ValueError("missing Telegram credential field")
    return token, chat_id, text


def deliver(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in split_message(text):
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
    try:
        token, chat_id, text = parse_stdin(sys.stdin.buffer.read())
        deliver(token, chat_id, text)
    except Exception as exc:  # noqa: BLE001 - boundary intentionally sanitizes all failures
        # Never stringify the exception: urllib exceptions may retain request
        # metadata. The caller needs only a bounded failure class, not the URL.
        print(f"Telegram delivery failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
