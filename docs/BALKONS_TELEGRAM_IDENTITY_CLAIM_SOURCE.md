# Balkons Telegram identity claim builder — source only

This is a **pure in-memory proof builder**, not a live HA/RPi5 credential
collector. It prepares the `ha` and `rpi5` claim objects consumed by the
already merged `ops/bin/balkons-telegram-identity-compare` contract. The
existing comparator still exits 2 even for matching claims, and always has
`cutover_ready=false`.

## Intended boundary

- `ops/lib/balkons-telegram-identity-claim.py` exports `ha_claim(...)` and
  `rpi5_claim(...)`. It has **no CLI** and cannot inspect files, `.storage`,
  systemd credentials, application configuration, process environment, network,
  Telegram API or Home Assistant.
- A future **separately reviewed and owner-authorized private collector** must
  supply the effective bot token and recipient chat values from independently
  proven, correctly mapped runtime sources **in memory**, along with one fresh
  32-byte private session key and one shared fresh 16-byte challenge.
- HA must bind `notify.andris` to the **exact** Telegram config entry and
  check its `Broadcast` mode before setting `registry_link_checked=True`.
  A caller's boolean is a *claim*, not proof of registry provenance. The two
  observed devices called `Andris` must never be matched by display name.
- RPi5 must independently prove the effective `balkons-bot.service` entrypoint
  and the bot/chat values actually used by its running process. Previous
  `configured_public_source_not_reviewed` remains an independent blocker.
- Bot and chat values are **exact UTF-8 byte strings** already prepared by the
  trusted adapter, without any normalization in this library. The RPi5 source
  currently calls `.strip()` on credential text; a future private adapter
  must compare effective values, not blindly hash ciphertext/file bytes.
- Session key distribution and freshness are **not implemented**. The caller
  must protect key/challenge from reuse, prove the two producers are trusted,
  and never expose the key, raw values or real HMAC proof bundle in logs,
  GitHub, chat, environment variables, process argv or a public artifact.
  Python immutable bytes cannot be guaranteed to be zeroized.

Both functions return only the fixed fields specified by
`rozkalns.balkons-telegram-identity-compare.v1`, including HMAC-SHA256 of
`balkons-identity-v1` + NUL + (`bot` or `chat`) + NUL + raw 16-byte
challenge + NUL + the original effective UTF-8 value. The 32-byte session
key is not serialized. Invalid lengths, types, NUL, UTF-8 or target/mode
claims produce only fixed category errors. No raw token, chat ID, user ID,
key or caller-supplied value is printed by the library.

## Limits, gates and offline verification

No source-only tool can authenticate a self-asserted collector origin,
`registry_link_checked`, session freshness, or protected-data provenance.
The comparator reports only **consistent, unverified claims**. User-ID
allowlist, unique Telegram Polling receiver, old MQTT forwarder exclusion,
`/stop` independent access, and exact live device state remain separate gates.
Neither this library nor its merge authorizes RPi5 or HA changes.

Synthetic offline tests exercise matching and mismatching identities, known
HMAC vectors, domain separation, strict schema and no-sensitive-output checks:

```text
python3 tests/test-balkons-telegram-identity-claim.py
```

**No real value is used or collected.** An authenticated collector and private
key-exchange/identity-binding workflow are a separate STRICT owner decision,
not implied by this source work. Do not improvise extraction from HA `.storage`
or RPi5 encrypted credentials to satisfy the comparator.
