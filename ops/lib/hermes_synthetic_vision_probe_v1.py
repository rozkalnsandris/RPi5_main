"""Offline-only Hermes synthetic vision proof-of-boundary fixture.

Not installed in Hermes or Gateway. Never imports provider SDKs, credentials, config,
host state, Telegram or network transports. A caller-supplied test callback is NOT
a verified one-HTTP-request transport: the callback could retry internally.
"""

from __future__ import annotations

import base64
import binascii
import struct
import zlib
from typing import Callable

MODEL = "nvidia/nemotron-3.5-super-vl:free"
PROVIDER = "openrouter"
FIXTURE_REF = "synthetic:hermes-option-b-red-circle-v1"
IMAGE_MODE = "text"  # Auxiliary vision text enrichment, never main-model native.
PROMPT = "Which color is the circle at the center? Reply exactly RED, BLUE, or GREEN."
SIZE = 96


class ProbeRejected(ValueError):
    """A condition violates the offline-only test contract."""


class ProbeDispatchFailed(RuntimeError):
    """Exactly one callback was attempted; its result was not accepted."""


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", binascii.crc32(tag + payload) & 0xFFFFFFFF)
    )


def synthetic_png() -> bytes:
    """Generate only the deterministic public-safe RGB 96x96 fixture in memory."""
    blue = bytes((23, 80, 184))
    red = bytes((230, 28, 42))
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)  # PNG filter: none
        for x in range(SIZE):
            raw.extend(red if (x - 48) ** 2 + (y - 48) ** 2 <= 30**2 else blue)
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + _png_chunk(b"IEND", b"")
    )


def synthetic_request() -> dict:
    """Build one fixed request; never accept an image, prompt or model override."""
    data_url = "data:image/png;base64," + base64.b64encode(synthetic_png()).decode("ascii")
    return {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 100,
        "extra_body": {
            "provider": {
                "allow_fallbacks": False,
                "max_price": {"prompt": 0, "completion": 0, "image": 0, "request": 0},
            }
        },
    }


def validate_envelope(*, media_refs: tuple, image_mode: str, provider: str, model: str) -> None:
    """Reject anything other than the one offline-owned marker and exact route."""
    if type(media_refs) is not tuple or media_refs != (FIXTURE_REF,):
        raise ProbeRejected("FIXTURE_ONLY")
    if image_mode != IMAGE_MODE or provider != PROVIDER or model != MODEL:
        raise ProbeRejected("ROUTE_MISMATCH")


class SingleUseSyntheticProbe:
    """A single-use *mock callback* seam, not a production HTTP dispatch guard.

    For LIVE proof, bind the limit at the real outbound transport, disable all
    SDK/internal/Gateway retries and independently prove installed-code identity.
    """

    __slots__ = ("_attempted",)

    def __init__(self) -> None:
        self._attempted = False

    @property
    def callback_attempts(self) -> int:
        return int(self._attempted)

    def run(
        self,
        *,
        media_refs: tuple,
        image_mode: str,
        provider: str,
        model: str,
        send: Callable[[dict], str],
    ) -> dict:
        if self._attempted:
            raise ProbeRejected("ALREADY_ATTEMPTED")
        validate_envelope(
            media_refs=media_refs,
            image_mode=image_mode,
            provider=provider,
            model=model,
        )
        if not callable(send):
            raise ProbeRejected("NO_OFFLINE_CALLBACK")

        # Consume before invocation: failure, timeout or reentry never retries.
        self._attempted = True
        try:
            reply = send(synthetic_request())
        except Exception:
            raise ProbeDispatchFailed("CALLBACK_FAILED") from None
        if type(reply) is not str or reply.strip().upper() != "RED":
            raise ProbeDispatchFailed("UNEXPECTED_RESPONSE")
        return {"status": "OFFLINE_PASS", "color": "RED", "callback_attempts": 1}
