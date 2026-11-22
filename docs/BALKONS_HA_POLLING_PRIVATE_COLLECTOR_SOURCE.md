# HA Polling private sender collector — SOURCE ONLY

This source prepares **one HA-local, read-only collector** for a future
separately authorized invocation. The Python module is
`ops/lib/balkons-ha-polling-private-collector.py`.
Unlike the previous claim-only comparator, it reads actual Home Assistant
in-memory entity registry, config-entry metadata, event entity state and
Telegram allowed-chat subentries. This source is **not installed in HA**.

## Calling contract

Inside a separately authorized **trusted HA-local** Python context call:

`collect_sender_binding(hass=<real HomeAssistant>,
approved_chat_id=<owner-approved private chat>,
approved_user_id=<owner-approved private sender>)`

The caller must supply IDs in memory, separately and independently approved
by the owner. They **must not** be copied from the Telegram event, inferred
from the chat allowlist, or chosen by either display name `Andris`.
Do not pass private values in CLI, environment, GitHub, chat, file or log.
A source-only repository merge does not authorize protected-runtime access.

The collector requires:
1. An actual entity-registry link for `event.balkona_laistisana_update_event`
   to the HA `telegram_bot` integration.
2. The linked bot's config entry is `loaded`, in `polling` mode; its
   ID agrees with the current event's `bot.config_entry_id`.
3. A recent (at most 120 seconds, with at most 5 seconds of future skew)
   `telegram_command` event with no args and a nonwatering command.
4. A matching `chat_id` and `user_id` against the privately approved values,
   plus exactly one matching `allowed_chat_ids` config subentry.

Results contain only fixed reason/status codes, no raw identifiers or
tracebacks. The result always sets `cutover_ready=false` and
`mutation=false` even on a match. It does **not** prove owner ID provenance,
`notify.andris` Broadcast recipient mapping, uniqueness of Telegram
`getUpdates` receivers, the independent `/stop` safety path, MQTT delivery,
or actual ESP32/pump status.

## Mandatory next gate (not authorized by this source)

1. Review compatibility against the **installed HA version**, trusted
   HA-native executor and exact private approved-value provenance.
2. Obtain separate explicit STRICT owner authority for the bounded
   HA runtime/registry read and approved private inputs. No direct
   `.storage` reading, secret extraction or raw config export.
3. Independently confirm `notify.andris`, no competing Telegram poller,
   emergency STOP access and the saved automation's OFF/disabled state.
4. Any change to private HA automation filters, Save, enablement or
   LIVE communication needs its own explicit owner authorization.
   `/laist*` remains prohibited until safety parity is independently proven.

No HA, RPi5, MQTT, Telegram, ESP32, pump or credential mutation is
included. There is no deployed integration or automatic runner.

Offline synthetic test: `python3 tests/test-balkons-ha-polling-private-collector.py`.
Seven tests cover wrong/missing identity, stale events, bot mismatch,
wrong mode, duplicate/absent allowlist and ID-free output.

Sources:
https://www.home-assistant.io/integrations/telegram_bot/
https://contributors.home-assistant.io/core/integrations/subentries/
