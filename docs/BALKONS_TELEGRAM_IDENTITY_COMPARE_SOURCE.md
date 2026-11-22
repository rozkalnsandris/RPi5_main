# Balkona Telegram identity comparison — source only

**Scope:** Offline comparison of separately produced *opaque* HA and RPi5
Telegram bot/chat identity claims. No production attestation is available yet.
The current HA UI exposes two `Andris` recipients among four Broadcast
services. Their display names alone cannot establish the `notify.andris`
config-entry mapping or the RPi5 bot/chat identity. Historical RPi5 route
attribution returned `configured_public_source_not_reviewed`; this is an
independent provenance blocker, not evidence of a bot mismatch.

## Contract

`ops/bin/balkons-telegram-identity-compare` accepts one bounded JSON object
from stdin with exactly `schema`, `ha` and `rpi5`. The schema is
`rozkalns.balkons-telegram-identity-compare.v1`.

- `ha`: `origin=HA_PRIVATE_COLLECTOR_CLAIM`, `entity_id=notify.andris`,
  `entry_mode=Broadcast`, `registry_link_checked=true`, plus `challenge`,
  `bot_hmac`, `chat_hmac`.
- `rpi5`: `origin=RPI5_PRIVATE_COLLECTOR_CLAIM`,
  `service=balkons-bot.service`, plus the same three opaque fields.
- `challenge`: lowercase hex encoding of 16 fresh random bytes; both sides
  must use the *same* challenge for the same comparison.
- Each HMAC: lowercase 64-character SHA-256 hex digest, computed by two
  **separately trusted, owner-authorized private collectors** using the same
  fresh 256-bit session key. The exact domain-separated message for a value
  is UTF-8 bytes `balkons-identity-v1` + NUL + `bot` or `chat` + NUL +
  the 16 challenge bytes + NUL + the original value's UTF-8 bytes.
  Token/chat values must not be silently normalized. The private key and
  original values must never be sent to the comparer, a chat, logs or GitHub.
  Reusing a key/challenge, publishing it, or deriving a proof from an
  unreviewed source invalidates the evidence.

No collector, key distribution, credential access, HA `.storage` inspection,
Telegram API call, SSH, MQTT action, or service operation is included in this
source change. The repo's existing forbidden-data policy remains binding.
Do **not** create ad-hoc collectors or fetch token/chat IDs to satisfy this
contract. Future collection needs separately reviewed provenance and owner
permission; the existence of the comparator is not that authorization.

## Interpretation

- `EVIDENCE_CONSISTENT_ORIGIN_UNVERIFIED` means the supplied HMAC claims
  match, **not** that their origins or the HA registry link are authenticated.
- `BLOCKED` uses fixed reason codes; malformed or mismatched evidence never
  prints source fields. No result prints token, chat ID, user ID, HMAC or key.
- `cutover_ready` is always `false`. User-ID allowlisting, the exact
  `notify.andris` → HA config entry, RPi5 installed-source provenance, active
  MQTT forwarder exclusion and independent `/stop` remain separate gates.
- This source work does not turn on the inert HA automation, stop the existing
  RPi5 bot, register a second Telegram Polling client, or send test messages.

Offline tests, using deliberately synthetic proofs:

```text
python3 tests/test-balkons-telegram-identity-compare.py
```
