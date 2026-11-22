#!/usr/bin/env python3
"""Offline in-memory check of *untrusted* HA Telegram sender-binding claims.

Not a private runtime collector or attestation: independently authorized
adapters must establish event/registry provenance, sender ownership, allowlist,
and freshness. No files, network, environment, CLI or HA actions are accessed.
"""
from __future__ import annotations

import hmac
import re

EVENT = "event.balkona_laistisana_update_event"
SCHEMA = "rozkalns.balkons-ha-polling-sender-binding.v1"
_EVENT_KEYS = frozenset(("entity_id", "event_type", "bot_config_entry_id",
                         "chat_id", "user_id", "args"))
_APPROVED_KEYS = frozenset(("bot_config_entry_id", "chat_id", "user_id"))
_REGISTRY_KEYS = frozenset(("entity_id", "bot_config_entry_id", "entry_mode",
                           "registry_event_link_checked"))
_ENTRY = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)
_CHAT = re.compile(r"-?[1-9][0-9]{0,19}\Z", re.ASCII)
_USER = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)


class BindingRejected(ValueError):
    """Only fixed, ID-free reason codes are exposed to callers."""


def _shape(value: object, keys: frozenset[str], reason: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise BindingRejected(reason)
    return value


def _entry(value: object) -> bytes:
    if type(value) is not str or _ENTRY.fullmatch(value) is None:
        raise BindingRejected("BOT_ENTRY_INVALID")
    return value.encode("ascii")


def _identifier(value: object, *, chat: bool) -> bytes:
    if type(value) is int:
        value = str(value)
    if type(value) is not str:
        raise BindingRejected("SENDER_ID_INVALID")
    pattern = _CHAT if chat else _USER
    if pattern.fullmatch(value) is None:
        raise BindingRejected("SENDER_ID_INVALID")
    return value.encode("ascii")


def evaluate_binding(*, event: object, approved: object,
                     registry: object) -> dict[str, object]:
    """Check scalar equality only; never claim the inputs' origin is trusted.

    'event' is an allowlisted projection of one HA telegram_command event,
    'approved' is a *separately* approved private sender+bot binding, and
    'registry' is an independently established Polling event-entity mapping.
    They MUST NOT all be synthesized from the same event or display name.
    """
    observed = _shape(event, _EVENT_KEYS, "EVENT_SHAPE_INVALID")
    sender = _shape(approved, _APPROVED_KEYS, "APPROVAL_SHAPE_INVALID")
    mapped = _shape(registry, _REGISTRY_KEYS, "REGISTRY_SHAPE_INVALID")

    if (observed["entity_id"] != EVENT or type(observed["entity_id"]) is not str
            or observed["event_type"] != "telegram_command"
            or type(observed["event_type"]) is not str
            or not (type(observed["args"]) is str and observed["args"] == ""
                    or type(observed["args"]) is list and observed["args"] == [])):
        raise BindingRejected("EVENT_UNEXPECTED")
    if (mapped["entity_id"] != EVENT or type(mapped["entity_id"]) is not str
            or mapped["entry_mode"] != "Polling"
            or type(mapped["entry_mode"]) is not str
            or mapped["registry_event_link_checked"] is not True):
        raise BindingRejected("REGISTRY_LINK_CLAIM_INVALID")

    entry = _entry(observed["bot_config_entry_id"])
    if not (hmac.compare_digest(entry, _entry(sender["bot_config_entry_id"]))
            and hmac.compare_digest(entry, _entry(mapped["bot_config_entry_id"]))):
        raise BindingRejected("BOT_ENTRY_MISMATCH")
    if not hmac.compare_digest(_identifier(observed["chat_id"], chat=True),
                               _identifier(sender["chat_id"], chat=True)):
        raise BindingRejected("CHAT_ID_MISMATCH")
    if not hmac.compare_digest(_identifier(observed["user_id"], chat=False),
                               _identifier(sender["user_id"], chat=False)):
        raise BindingRejected("USER_ID_MISMATCH")

    return {
        "schema": SCHEMA,
        "result": "CONSISTENT_INPUTS_ORIGIN_UNVERIFIED",
        "sender_claims_match": True,
        "independent_provenance_verified": False,
        "sender_authorization_verified": False,
        "event_freshness_verified": False,
        "cutover_ready": False,
        "mutation": False,
    }
