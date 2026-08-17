# Balcony watering source contract

Issue: #174

## Purpose

This document establishes reviewed source ownership for the RPi5-side balcony watering controller that already exists in production. It is a **source contract**, not production authorization. Merging the source does not install it, alter Hermes cron, change Home Assistant, publish MQTT, restart a service, run the pump, or deploy anything to the host.

## Canonical tracked source

The reviewed public source is:

- `ops/bin/balcony-watering-2x` — primary two-cycle watering controller;
- `ops/bin/balcony-watering-heat-gate` — temperature gate that may delegate to the primary controller;
- `tests/test-balcony-watering.sh` — offline regression coverage for the safety contract.

The live production files were reconciled read-only before this source was created. Their private host paths and private origin/config bindings are deliberately not reproduced here.

## Required sensor contract

The primary controller checks exactly 14 required Home Assistant entities before any pump-ON request:

- flowers 1-4;
- flowers 6-15.

Flower 5 is intentionally disconnected and excluded from this gate until a later hardware/source change explicitly re-adds it.

The controller fails closed before pump ON when any required entity is missing, `unavailable`, or `unknown`. It also skips when Home Assistant cannot be reached or the returned states cannot be parsed.

`last_updated` age is intentionally **not** a watering freshness criterion. The ESP32 can republish unchanged categorical MQTT state while Home Assistant retains an older `last_updated`; an age-only gate therefore produced false offline decisions.

## Watering-cycle contract

After the sensor gate passes, the primary controller preserves the established behavior:

1. request pump ON with up to three Home Assistant attempts;
2. water for 60 seconds by default;
3. request pump OFF with up to three attempts;
4. pause for 300 seconds by default;
5. repeat one more 60-second watering cycle;
6. explicitly request OFF at the end of each cycle;
7. keep `PUMP_IS_ON=1` until OFF is acknowledged so the EXIT/INT/TERM trap can retry OFF after a failed normal OFF path.

The firmware's independent pump fail-safe remains a separate device-side safety layer and is not replaced by this host controller.

## 14:00 temperature gate

The heat-gate source reads the Home Assistant weather entity and uses a default threshold of `27.0` C:

- below the threshold: exit successfully without delegating to watering;
- at or above the threshold: `exec` the same primary two-cycle controller;
- Home Assistant or temperature parse failure: fail closed without delegation.

The primary controller always re-runs its own 14-sensor gate after temperature delegation.

## Current schedule evidence

The read-only reconciliation found three enabled production schedules with successful latest status:

- 07:00 — primary two-cycle watering;
- 14:00 — temperature gate;
- 23:00 — primary two-cycle watering.

Those schedules remain owned by the existing private Hermes runtime. Raw Hermes job state is not tracked in this public repository, and this source PR does not alter or re-create those schedules.

## Private runtime boundary

Tracked files must not contain private LAN coordinates, real credentials, exact private credential paths, or raw Hermes runtime state.

Required runtime inputs:

- `HASS_URL` — private Home Assistant origin supplied outside Git;
- `HASS_TOKEN` — Home Assistant bearer token supplied outside Git.

Optional runtime inputs:

- `TELEGRAM_TOKEN` and `CHAT_ID` — enable skip notifications when both are supplied;
- `BALCONY_WATERING_ENTITY` — pump entity override;
- `BALCONY_WATERING_DURATION_SECONDS` — default `60`;
- `BALCONY_WATERING_PAUSE_SECONDS` — default `300`;
- `BALCONY_WATERING_LOCKFILE` and `BALCONY_WATERING_LOGFILE` — runtime path overrides;
- `BALCONY_WATERING_TEMP_ENTITY` — weather entity override;
- `BALCONY_WATERING_TEMP_THRESHOLD_C` — default `27.0`;
- `BALCONY_WATERING_PRIMARY` — explicit primary-controller path for the heat gate.

A later production mapping may provide these inputs through a protected host-only configuration mechanism. That mapping is intentionally out of scope here.

## Offline regression gate

`tests/test-balcony-watering.sh` replaces `curl` and `sleep` with local mocks, uses a reserved `.invalid` URL, and never performs a real network request or pump action. It verifies:

1. all 14 required sensors valid => watering path is reachable;
2. flower 5 absent => still valid;
3. one required sensor missing => skip;
4. one required sensor unavailable => skip;
5. one required sensor unknown => skip;
6. empty Home Assistant response => skip;
7. malformed state JSON => skip;
8. no runtime `last_updated` dependency;
9. failed OFF retries preserve the trap-OFF safety path;
10. below 27 C => no delegation, at 27 C => delegation;
11. all `curl` traffic remains inside the local mock.

The repository-wide `make validate` gate includes this regression together with shell syntax, secret scanning, and public-repository safety checks.

## Production and deployment boundary

This source publication deliberately does **not**:

- add a watering entry to `ops/deploy/targets.json`;
- copy or install source to a live path;
- change live file owner or mode;
- edit Hermes cron or its raw job state;
- execute the primary controller or heat gate;
- issue a pump command;
- change Home Assistant or MQTT;
- restart/reload a service;
- rotate credentials.

Any future production apply requires a separate owner authorization, fresh source/live binding, backup/rollback plan, bounded diff, and post-apply verification. A source merge alone never authorizes deployment.
