# HA Telegram Polling sender binding — private adapter core (SOURCE ONLY)

## Current observed staging (owner reported, not runtime attestation)

On 2026-11-22 the user reported `automation.balkons_telegram_polling_commands_staged`
(HA UI ID `1795378925536`) saved OFF with disabled trigger and main action.
Observed correct event entity: `event.balkona_laistisana_update_event`.
Chat/user IDs remain placeholders. The GitHub reference YAML still includes
an event placeholder and must NOT be mistaken for the installed HA YAML.

## Prepared interface, never an authenticated private collector

`ops/lib/balkons-ha-polling-sender-binding.py` exposes `evaluate_binding`.
It compares **three independently supplied in-memory projections**:

1. `event`: exact telegram_command entity, `bot_config_entry_id` projected
   from `bot.config_entry_id`, canonical chat/user IDs, and empty `args`.
2. `approved`: independently owner-approved bot entry, chat ID and user ID.
3. `registry`: independently established entity-to-Polling-bot mapping.

IDs are not printed, logged, serialized or used as error text. Chat IDs
may be negative; user IDs must be positive. Wrong event/type/args/entry
or mismatched chat/user fail closed with fixed reason codes.
The script has no file, network, environment, CLI, HA or runtime access.
Only synthetic fixtures run in CI. The registry boolean is a *claim*.

Even when all inputs match, results explicitly keep
`independent_provenance_verified=false`, `sender_authorization_verified=false`,
`event_freshness_verified=false`, `cutover_ready=false` and `mutation=false`.
Do not treat consistency as authorization, trusted origin, or permission to enable.
The previous HA/RPi5 HMAC claim builder/comparator also cannot attest provenance.

## Next independent STRICT gate — not authorized

- Separately review and authorize trusted private-source adapters for actual
  HA event + event-entity registry provenance, bot/config entry, allowlisted
  chat and owner user, and fresh single-use observation. Do not infer identity
  from the two same-name `Andris` recipients or from one event alone.
- Independently verify `notify.andris` recipient/config entry, no competing
  Telegram `getUpdates` client, and `/stop` independent safety access.
- Confirm *effective installed* automation and credentials privately;
  staged source currently checks chat/user but **not** `bot.config_entry_id`
  in its HA template guard. Any additional guard, value insertion, Save,
  enablement or live validation needs separate explicit owner authorization.
- `/laist*` must stay denied and MQTT/ESP32/pump state must not be inferred
  from source. On any unverified provenance outcome remain BLOCKED.

No HA `.storage`, bot token/credentials, RPi5 config/env/runtime reads,
Telegram send, MQTT publish, HA changes, service changes, pump command,
source merge, or real user IDs are included or authorized.

Offline test: `python3 tests/test-balkons-ha-polling-sender-binding.py`.

Official docs: https://www.home-assistant.io/integrations/telegram_bot/
(telegram_command includes `bot.config_entry_id`, `chat_id`, `user_id`, `args`).
