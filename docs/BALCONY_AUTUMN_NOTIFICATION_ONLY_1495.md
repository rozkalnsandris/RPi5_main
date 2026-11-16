# Legacy 11:00 watering notifications → Balkona Laistīšana (#1495)

**SOURCE ONLY: neither merged nor installed. No pump/Telegram/MQTT operation.**

The installed 11:00 controller is byte-identical to historical GitHub
`ops/bin/balcony-watering-autumn@5850fd707464a9f2c9dfcd472903d867276d4f86`,
SHA-256 `86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b`
(20,789 bytes). Its direct Telegram API notifications use the wrong bot identity.

The interim candidate `ops/bin/balcony-watering-autumn-notify-only` has
SHA-256 `7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1`. Its **only change** is the comment and
`send_tg()` block, verified by exact historical SHA restoration in an offline test.
The current main `ops/bin/balcony-watering-autumn` is unchanged.

**Only notification routing changes.** The old controller's 12 active sensors
(including flowers 11 and 13), all-sensors-usable blocking, frost gate, pump
ON/OFF confirmation, 180s ESP32 bound, day marker, durations and decision texts
remain exactly as installed. In particular, reported missing sensors 5/11/13
still prevent automatic watering. There is **no** `MAX_DEGRADED=2`, new
10-sensor policy or `manual-safety-v1.json` write in this interim candidate.

The notifier uses existing wrapper-provided `HASS_URL` and `HASS_TOKEN`
to call `POST /api/services/mqtt/publish` with exact
`balkons/telegram_out`, `qos=0`, `retain=false`.
The existing `balkons-bot.service` subscribes and sends to **Balkona Laistīšana**.
No Telegram token/chat ID, second bot poller, HA automation or MQTT actuator
topic is added. Dry-run suppresses sending. HTTP 200 only proves MQTT handoff,
not human Telegram receipt.

## Separate owner LIVE gate — not authorized by this PR

1. Freshly verify unique enabled/local 11:00 job, disabled legacy schedules,
   exact deployed old SHA, wrapper SHA
   `3e5698a54d33fafaef59a0bc5c847136672c6658de3a22001058bffe51a4133f`,
   clean source/provenance, file safety, and bot MQTT subscription. The #1474
   preflight is pinned to the *different* 10-sensor candidate: its PASS is
   **insufficient** for this interim 12-sensor candidate.
2. Obtain a reviewed, exact-target protected backup, recovery boundary and
   one-file replacement operator. Any protected runtime/HA capability
   inspection requires a separate precise read authorization. Do not expose
   tokens, private config, scripts or chat IDs.
3. Obtain explicit COMPOSITE STRICT LIVE authority for a one-time atomic
   replacement of only the deployed controller, preserving 0700 andris ownership,
   exact wrapper/cron/bot/service state, then re-read its SHA. No retry,
   rollback or cleanup after error/ambiguity without new authorization.
4. Only if separately authorized, run a protected no-actuation dry-run.
   Observe the next normal 11:00 schedule (never trigger watering as a test),
   check sanitized MQTT/TG API handoff and independent receipt in the correct
   Telegram conversation. Avoid duplicate consumers.

This outcome deliberately does **not** restore automatic watering. The separate
10-sensor/assumed-moist policy decision remains out of scope.
