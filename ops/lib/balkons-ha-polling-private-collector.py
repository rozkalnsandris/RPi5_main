#!/usr/bin/env python3
"""HA-local, read-only Telegram sender collector (source only; not installed).

A separately authorized, trusted HA-local caller supplies the HA object and two
independently owner-approved IDs in memory. Never pass IDs by CLI/env/logs.
The collector reads only HA runtime objects and returns fixed, ID-free results.
Match is *not* owner provenance, operational safety, or cutover approval.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hmac
import re

EVENT_ENTITY = "event.balkona_laistisana_update_event"
_MAX_AGE_SECONDS = 120
_MAX_FUTURE_SECONDS = 5
_CHAT = re.compile(r"-?[1-9][0-9]{0,19}\Z", re.ASCII)
_USER = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_ALLOWED_COMMANDS = frozenset(("/stop", "/mitrums", "/statuss", "/raw", "/start"))


class _Blocked(Exception):
    """Fixed category only; never embed sensitive inputs."""


def _required(test: bool, category: str) -> None:
    if not test:
        raise _Blocked(category)


def _id_bytes(value: object, *, user: bool) -> bytes:
    # HA event and HA subentry may store numerical IDs as int or str.
    if type(value) is int:
        value = str(value)
    _required(type(value) is str, "ID_FORMAT_INVALID")
    _required((_USER if user else _CHAT).fullmatch(value) is not None,
              "ID_FORMAT_INVALID")
    return value.encode("ascii")


def _result(*, matched: bool, category: str) -> dict[str, object]:
    return {
        "schema": "rozkalns.balkons-ha-polling-private-collector.v1",
        "result": "INPUTS_CONSISTENT_PROVENANCE_UNVERIFIED" if matched else "BLOCKED",
        "reason": category,
        "ha_registry_binding_checked": matched,
        "allowed_chat_subentry_checked": matched,
        "owner_user_provenance_verified": False,
        "notify_andris_binding_verified": False,
        "cutover_ready": False,
        "mutation": False,
    }


def collect_sender_binding(*, hass: object, approved_chat_id: object,
                           approved_user_id: object) -> dict[str, object]:
    """One bounded read of HA registry, Polling entry and latest Telegram event.

    Call only inside a separately owner-authorized HA-local trusted context.
    Both approvals MUST originate independently of the Telegram event and
    integration config; a match never proves that origin. Does not subscribe,
    send, save, enable, publish MQTT, or access HA storage/credentials.
    """
    try:
        # The import is intentionally local: source-only offline tests stub HA.
        from homeassistant.config_entries import ConfigEntryState
        from homeassistant.helpers import entity_registry as er

        # Validate approved values before looking up sensitive runtime objects.
        approved_chat = _id_bytes(approved_chat_id, user=False)
        approved_user = _id_bytes(approved_user_id, user=True)

        entity = er.async_get(hass).async_get(EVENT_ENTITY)
        _required(entity is not None and entity.platform == "telegram_bot"
                  and type(entity.config_entry_id) is str
                  and bool(entity.config_entry_id), "EVENT_REGISTRY_UNVERIFIED")
        # Only the HA entity registry is authoritative for the bot entry.
        entry = hass.config_entries.async_get_entry(entity.config_entry_id)
        _required(entry is not None and entry.entry_id == entity.config_entry_id
                  and entry.domain == "telegram_bot"
                  and entry.state == ConfigEntryState.LOADED
                  and entry.data.get("platform") == "polling",
                  "POLLING_ENTRY_UNVERIFIED")

        state = hass.states.get(EVENT_ENTITY)
        _required(state is not None and isinstance(state.attributes, Mapping),
                  "EVENT_STATE_MISSING")
        last_changed = state.last_changed
        _required(isinstance(last_changed, datetime)
                  and last_changed.tzinfo is not None,
                  "EVENT_FRESHNESS_UNVERIFIED")
        age = (datetime.now(timezone.utc) - last_changed).total_seconds()
        _required(-_MAX_FUTURE_SECONDS <= age <= _MAX_AGE_SECONDS,
                  "EVENT_FRESHNESS_UNVERIFIED")

        attributes = state.attributes
        bot = attributes.get("bot")
        _required(attributes.get("event_type") == "telegram_command"
                  and type(attributes.get("command")) is str
                  and attributes["command"] in _ALLOWED_COMMANDS
                  and (attributes.get("args") == "" or attributes.get("args") == [])
                  and isinstance(bot, Mapping), "COMMAND_EVENT_UNEXPECTED")
        _required(type(bot.get("config_entry_id")) is str
                  and hmac.compare_digest(bot["config_entry_id"], entry.entry_id),
                  "BOT_ENTRY_MISMATCH")

        observed_chat = _id_bytes(attributes.get("chat_id"), user=False)
        observed_user = _id_bytes(attributes.get("user_id"), user=True)
        _required(hmac.compare_digest(observed_chat, approved_chat),
                  "CHAT_ID_MISMATCH")
        _required(hmac.compare_digest(observed_user, approved_user),
                  "USER_ID_MISMATCH")

        # Subentries are registered allowed chat IDs, not display names.
        subentries = entry.subentries
        _required(isinstance(subentries, Mapping), "ALLOWLIST_UNVERIFIED")
        allowed = 0
        for item in subentries.values():
            if item.subentry_type != "allowed_chat_ids":
                continue
            data = item.data
            _required(isinstance(data, Mapping), "ALLOWLIST_UNVERIFIED")
            if hmac.compare_digest(_id_bytes(data.get("chat_id"), user=False),
                                   observed_chat):
                allowed += 1
        _required(allowed == 1, "ALLOWLIST_UNVERIFIED")
        return _result(matched=True, category="MATCH_NO_OWNER_ATTESTATION")
    except _Blocked as exc:
        return _result(matched=False, category=str(exc))
    except Exception:
        # No exception text or traceback may contain raw identifiers.
        return _result(matched=False, category="HA_RUNTIME_UNAVAILABLE")
