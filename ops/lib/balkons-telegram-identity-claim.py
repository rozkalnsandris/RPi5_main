#!/usr/bin/env python3
"""Pure, offline builder of *untrusted* HA/RPi5 identity claims.

This is NOT a credential collector: values are provided by a separately
reviewed, authorized private adapter. No protected path, environment, network,
process or HA API is accessed here. HMAC equality is only a consistency claim;
it never attests provenance or authorizes an HA/Telegram cutover.
"""
from __future__ import annotations

import hashlib
import hmac

SCHEMA = "rozkalns.balkons-telegram-identity-compare.v1"
_DOMAIN = b"balkons-identity-v1\x00"
_MAX_SECRET_BYTES = 512


class ClaimInputError(ValueError):
    """Fixed, non-sensitive input rejection category."""


def _bytes(value: object, *, length: int | None = None) -> bytes:
    if type(value) is not bytes:
        raise ClaimInputError("CLAIM_VALUE_TYPE_INVALID")
    if length is not None:
        if len(value) != length:
            raise ClaimInputError("CLAIM_VALUE_LENGTH_INVALID")
    elif not (1 <= len(value) <= _MAX_SECRET_BYTES):
        raise ClaimInputError("CLAIM_VALUE_LENGTH_INVALID")
    return value


def _secret(value: object) -> bytes:
    raw = _bytes(value)
    try:
        decoded = raw.decode("utf-8", "strict")
    except UnicodeError:
        raise ClaimInputError("CLAIM_SECRET_ENCODING_INVALID") from None
    if "\x00" in decoded:
        raise ClaimInputError("CLAIM_SECRET_ENCODING_INVALID")
    return raw


def _proof(*, session_key: bytes, challenge: bytes, field: bytes,
           value: bytes) -> str:
    # Domain separation prevents bot/chat proofs from being interchanged.
    message = _DOMAIN + field + b"\x00" + challenge + b"\x00" + value
    return hmac.new(session_key, message, hashlib.sha256).hexdigest()


def _shared(*, token: object, chat: object, session_key: object,
            challenge: object) -> dict[str, str]:
    key = _bytes(session_key, length=32)
    nonce = _bytes(challenge, length=16)
    bot = _secret(token)
    recipient = _secret(chat)
    return {
        "challenge": nonce.hex(),
        "bot_hmac": _proof(session_key=key, challenge=nonce, field=b"bot",
                           value=bot),
        "chat_hmac": _proof(session_key=key, challenge=nonce, field=b"chat",
                            value=recipient),
    }


def ha_claim(*, token: bytes, chat: bytes, session_key: bytes,
             challenge: bytes, entity_id: str,
             entry_mode: str, registry_link_checked: bool) -> dict[str, object]:
    """Produce HA-claimed evidence; registry_link_checked is NOT attested."""
    if (type(entity_id) is not str or entity_id != "notify.andris"
            or type(entry_mode) is not str or entry_mode != "Broadcast"
            or registry_link_checked is not True):
        raise ClaimInputError("HA_LINK_CLAIM_INVALID")
    values = _shared(token=token, chat=chat, session_key=session_key,
                     challenge=challenge)
    return {
        "origin": "HA_PRIVATE_COLLECTOR_CLAIM",
        "entity_id": "notify.andris",
        "entry_mode": "Broadcast",
        "registry_link_checked": True,
        **values,
    }


def rpi5_claim(*, token: bytes, chat: bytes, session_key: bytes,
               challenge: bytes, service: str) -> dict[str, object]:
    """Produce RPi5-claimed evidence; no running service is inspected."""
    if type(service) is not str or service != "balkons-bot.service":
        raise ClaimInputError("RPI5_SERVICE_CLAIM_INVALID")
    values = _shared(token=token, chat=chat, session_key=session_key,
                     challenge=challenge)
    return {
        "origin": "RPI5_PRIVATE_COLLECTOR_CLAIM",
        "service": "balkons-bot.service",
        **values,
    }
