# RPi5 11:00 Telegram notification-only: one-shot LIVE preparation (#1498)

SOURCE PREPARATION ONLY. No host runtime change or permission to execute --apply.

## Pinned evidence and route

- Reviewed source baseline: RPi5_main main a9aa708504c52775eaed8706bd118dd2a314f7ed, after merged PR #1496. A future LIVE action MUST use the actual later merged SHA.
- Installed legacy controller expected SHA-256: 86972a10bd457abb6350e2f924d7c3bcc54139af322f335707f51e1e440ac60b.
- Existing Hermes wrapper expected SHA-256: 3e5698a54d33fafaef59a0bc5c847136672c6658de3a22001058bffe51a4133f.
- Frozen historical Hermes job definition fingerprint: bc085927b0a145b947742551c1550e4a875b55fc2c9925148e11c3d5e3123562. Must be freshly rechecked.
- Replacement source ops/bin/balcony-watering-autumn-notify-only SHA-256: 7c993c5e0fdffdcb405b57aebad2be65a133be17caf13f16492fde6f12bc45b1.
- This is the merged #1496 LEGACY-COMPATIBLE source, NOT ops/bin/balcony-watering-autumn (10-sensor version). It preserves 12 sensors, missing-sensor hard blocking, frost, one cycle per day, and pump behavior. Flowers 5, 11, 13 may still block watering.
- Telegram handoff uses existing Home Assistant POST /api/services/mqtt/publish with topic balkons/telegram_out, qos=0, retain=false. Existing balkons-bot.service consumes the topic, intended solely for Balkona Laistīšana. HA HTTP 200 is NOT confirmation of Telegram receipt.
- Official Home Assistant: https://www.home-assistant.io/integrations/mqtt/ (REST API example), https://www.home-assistant.io/actions/mqtt.publish/ (QoS/retain semantics).

## Source-only tooling (not executed on RPi5)

1. ops/bin/balcony-watering-autumn-notify-only-preflight: sanitized read-only existing 11:00 job, 07/14/23 disabled schedule, fixed fingerprint, wrapper and deployed source exact hashes, 0700 target and matching 12-sensor candidate. No secrets, raw Hermes records or private path output. Old #1474 preflight is NOT equivalent (pins the separate 10-sensor variant).
2. ops/bin/balcony-watering-autumn-notify-only-operator: fixed-target --check (reads protected Hermes store, requires exact READONLY host authorization) or --apply (requires separate explicit owner COMPOSITE STRICT LIVE authority). Neither flag nor source merge grants authority. It also verifies a clean exact-main checkout and fixed Git blob provenance. It never runs the controller or sends MQTT/Telegram/pump commands.
3. tests/test-balcony-watering-autumn-notify-only-preflight.py and tests/test-balcony-watering-autumn-notify-only-operator.py: synthetic offline-only; never touch host runtime, HA, Telegram, MQTT or devices.

## Exact runtime gates BEFORE any LIVE mutation

Obtain separate STRICT READONLY authorization for metadata-only host verification: 11:00 unique enabled/local job, exact current script SHA and wrapper/job fingerprint, 07/14/23 disabled; checkout exactly equal to freshly approved merged Git SHA; actual HA MQTT capability; the bot has acknowledged subscription and only the desired Telegram recipient is bound without exposing tokens/chat IDs; no parallel HA notify automation; no running controller; no unexpected lockfile override; expected existing lockfile is available; time margin away from next 11:00. Confirm target owner/group/mode and no existing stage/recovery. Read no .env, credentials, raw configs, journal payloads, chat IDs or process environment. Check source checkout; if it needs updating, even trusted git fetch/ff-only is a separate host mutation that must be explicitly authorized.

BLOCK if any protected runtime gate is unproven. No test MQTT publish, Telegram message or watering action.

## Future owner-gated COMPOSITE STRICT LIVE scope (NOT yet authorized)

One exact approved merged release SHA, host rpi5, andris account, candidate SHA, old SHA, wrapper/job identity, and fixed deployed controller filename under ~/.hermes/scripts. Only one-script replacement is within scope; no wrapper/Hermes cron edits, no bot/HA/service restart or token mutation, no device/actuator commands.

- precheck 10:00-12:00 Europe/Berlin quiet window, exact enabled job/old SHA, no existing recovery/stage, no active controller; nonblocking acquisition of EXISTING controller lock;
- first mutation creates one 0600 same-directory exclusive recovery file; exact readback; creates one 0700 same-directory exclusive stage; exact readback; atomic os.replace of ONE controller target, preserves andris uid/gid and 0700, exact post-install hash and directory fsync;
- creation of the recovery file consumes LIVE authority. Any subsequent error, unexpected state or timeout: STOP, keep recovery/stage evidence, NO retry, cleanup, rollback or opposite pump command without separate approval;
- the routine next 11:00 decision is the acceptance event: check sanitized HA handoff/bot API outcome and verify receipt in Balkona Laistīšana, not RPi5 Paziņojumi. No manually started controller as an acceptance test.

This is strictly a notification-route fix. The outdated 12-sensor hard gate remains and watering may continue to be skipped.
