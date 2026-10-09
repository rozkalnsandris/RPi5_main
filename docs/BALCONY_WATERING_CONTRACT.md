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

The primary controller checks exactly **12 active** Home Assistant entities before any pump-ON request:

- flower **1**;
- flowers **3-13** (including flower **5**).

ESP32 firmware retired flowers **2, 14 and 15**. Those retired entities are no longer required; only the 12 active sensors form the fail-closed gate.

This **supersedes** the historical 14-sensor source gate in #174 (flowers 1-4 and 6-15, which excluded flower 5). The firmware source change was shipped to the ESP32 independently; updating this RPi5 source does not prove that the private production controller has been replaced.

The controller fails closed before pump ON when any required entity is missing, `unavailable`, or `unknown`. It also skips when Home Assistant cannot be reached or the returned states cannot be parsed.

`last_updated` age is intentionally **not** a watering freshness criterion. The ESP32 can republish unchanged categorical MQTT state while Home Assistant retains an older `last_updated`; an age-only gate therefore produced false offline decisions.

## Watering-cycle contract

After the sensor gate passes, the primary controller uses Home Assistant service calls only as requests. HTTP 200 by itself is **not** treated as pump-state acknowledgement.

For each transition the controller reads the exact switch entity and requires the expected `on` or `off` state within a bounded five-sample confirmation window with one-second spacing.

The cycle contract is:

1. before an ON request, set the local hazard flag `PUMP_IS_ON=1`, meaning the pump **may** be energized or the ON result may be ambiguous;
2. issue exactly one ON service request for that cycle — ON is duplicate-sensitive because a repeated command can extend an already-running ESP32 session;
3. require the switch entity to report `on`; if it does not, fail closed and let the EXIT/INT/TERM cleanup request OFF;
4. water for 60 seconds by default only after `on` is confirmed;
5. request OFF with up to three attempts because repeated OFF is fail-safe/idempotent at the relay boundary;
6. require the switch entity to report `off` before clearing `PUMP_IS_ON`;
7. if OFF cannot be confirmed, fail the run and keep the cleanup obligation active;
8. pause for 300 seconds by default;
9. repeat the same confirmed ON/OFF sequence once more.

The `PUMP_IS_ON` name is retained for compatibility, but its safety meaning is conservative: `1` means **may be ON**, not “physical current was independently measured.” It is cleared only after Home Assistant reports `off`.

Home Assistant switch-state confirmation is software-path evidence from the ESP32/MQTT state topic. It is stronger than service-call HTTP status but is **not** independent pump-current, water-flow, or relay-contact sensing. The firmware's independent 180-second pump fail-safe remains a separate device-side safety layer and is not replaced by this host controller.

## 14:00 temperature gate

The heat-gate source reads the Home Assistant weather entity and uses a default threshold of `27.0` C:

- below the threshold: exit successfully without delegating to watering;
- at or above the threshold: `exec` the same primary two-cycle controller;
- Home Assistant or temperature parse failure: fail closed without delegation.

The primary controller always re-runs its own 12-sensor gate after temperature delegation.

## Current schedule evidence

A historical read-only reconciliation found three enabled production schedules with successful latest status at that time:

- 07:00 — primary two-cycle watering;
- 14:00 — temperature gate;
- 23:00 — primary two-cycle watering.

Those schedules were owned by the private Hermes runtime at reconciliation time. **Current activation, the live controller's exact bytes and the schedule must be revalidated before any separately authorized LIVE deployment.** Raw Hermes job state is not tracked here, and this source PR does not alter or re-create those schedules.

## Autumn/winter mode — one daily moisture and frost decision

`ops/bin/balcony-watering-autumn` is the reviewed source for the cold-season controller. Heather (`Calluna vulgaris`) outside a summer heat pattern does not need a fixed twice-daily schedule; it needs one daily decision that answers "is any pot actually dry, and is it safe to wet the soil today". This source is deliberately stricter than the two-cycle controller: it keeps the same fail-closed transport and switch-confirmation safety model and adds a quorum, a frost gate and a once-per-day bound.

### Target schedule (source-side intent only)

- 07:00, 14:00 and 23:00 two-cycle watering: to be disabled in the cold season;
- 11:00 — one daily moisture and frost-risk check.

The check runs once and decides for itself whether anything is watered. The once-per-day bound is enforced by the controller through a `last-watered` date file, not by the schedule, so a duplicated or repeated invocation cannot produce a second cycle.

Creating, disabling or editing Hermes schedules, installing the controller at a live path and starting a real run are LIVE operations. This source changes no schedule by itself.

### Gates, in order

1. **State fetch** — one `GET /api/states` snapshot. An empty answer is a skip with an error notification.
2. **Active sensor set** — exactly 12 entities: flowers 1 and 3–13. Retired flowers 2, 14 and 15 are never required, never counted and never treated as dry. An active sensor that is missing, `unavailable`, `unknown` or carries an unexpected categorical value is uncertainty: the run skips and no pump request is made.
3. **Quorum** — watering is considered only when at least `BALCONY_MIN_DRY_SENSORS` (default `2`) of the 12 active sensors report `sauss`. A single dry sensor never waters the whole tray.
4. **Wet-enough guard** — when at least `BALCONY_MAX_MOIST_SENSORS` (default `10`) of the 12 report `mitrs`, the run skips quietly.
5. **Frost gate** — the low temperature for the next 24 h is read from the weather entity `forecast` attribute. When that attribute is absent, the read-only `weather.get_forecasts` service is used. The lower of that low and the current temperature is compared with `BALCONY_FROST_THRESHOLD_C` (default `2.0`); at or below the threshold the run is blocked and reported as a frost block. When no usable temperature can be obtained, the run skips with an error. `BALCONY_FROST_REQUIRE_FORECAST=0` downgrades a missing forecast to the current temperature with a logged warning; the default `1` keeps it fail-closed.

`BALCONY_AUTUMN_DRY_RUN=1` executes every gate, logs the decision and suppresses the pump request, all Telegram messages and the day marker. It exists so a preflight can prove what the controller would do before anything is live.

### Cycle and safety

One cycle only: a single confirmed ON request, `BALCONY_AUTUMN_DURATION_SECONDS` (default `45`) of watering, then a confirmed OFF with the same retry and confirmation rules as the two-cycle controller. A duration above the device's 180 s hard limit is rejected outright. The day marker is written as soon as ON is confirmed, so a later failure can never allow a second cycle that day. The `PUMP_IS_ON` hazard flag and the EXIT/INT/TERM cleanup obligation are unchanged.

If the switch already reports `on` before this controller asks for anything, another actor owns the relay: the controller requests a confirmed OFF, aborts and reports an error instead of watering on top of it.

The ESP32 keeps its independent 180 s pump fail-safe. This controller neither weakens it nor treats it as the only protection.

### Cycle-length calibration

`45 s` is a candidate, not a calibrated value. The controller always logs a `calibration:` line comparing the dry/moist split before the cycle with the split after `BALCONY_AUTUMN_SOAK_SECONDS` (default `300`); `BALCONY_AUTUMN_CALIBRATION=1` also sends it to Telegram. Procedure: run one cycle, read the readback, and adjust `BALCONY_AUTUMN_DURATION_SECONDS` inside the reviewed 30–60 s window until the dry pots reach `mitrs` without the tray staying saturated. A duration outside 30–60 s is logged as a warning.

### Message policy

Telegram receives exactly three kinds of message: a real watering cycle (duration and the dry count before it), an error (unreachable Home Assistant, unusable state JSON, unusable active sensor, unusable temperature, unconfirmed ON or OFF), and a frost block. A normal skip — too few dry sensors, tray already wet, already watered today, lock busy — is logged only.

### Manual commands and frost (evaluation)

Manual paths stay outside this gate: the bot's `/laist` and `/laist_N` publish `balkons/cmd` directly, and `balkons/sukna/komanda ON` reaches the device as well. The bot holds an MQTT and Telegram credential, not a Home Assistant credential, so it cannot evaluate the frost gate itself.

Evaluated options:

- **Host-side flag (recommended next step).** The 11:00 controller already computes a frost decision; writing a dated frost flag into its state directory would let the bot refuse `/laist*` while the flag is fresh, without new credentials. This is a separate, bounded change that must also define flag staleness and the owner-override wording.
- **Device-side block.** A firmware subscription to a frost/block topic would refuse starts even for a direct MQTT publisher, but it adds a coupled topic, a new firmware revision and an OTA to the critical path.

Until one of these is authorized, manual commands remain a deliberate owner override, and the device's 180 s fail-safe is the only bound on them.

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

Autumn/winter controller inputs:

- `BALCONY_AUTUMN_DURATION_SECONDS` — default `45`, rejected above the 180 s device limit;
- `BALCONY_AUTUMN_SOAK_SECONDS` — default `300`, post-cycle readback delay;
- `BALCONY_AUTUMN_CALIBRATION` — default `0`; `1` also sends the readback to Telegram;
- `BALCONY_AUTUMN_DRY_RUN` — default `0`; `1` runs every gate without pump, messages or day marker;
- `BALCONY_FROST_THRESHOLD_C` — default `2.0`;
- `BALCONY_FROST_REQUIRE_FORECAST` — default `1` (fail closed when no forecast is available);
- `BALCONY_MIN_DRY_SENSORS` — default `2`;
- `BALCONY_MAX_MOIST_SENSORS` — default `10`;
- `BALCONY_AUTUMN_STATE_DIR`, `BALCONY_AUTUMN_LOCKFILE`, `BALCONY_AUTUMN_LOGFILE` — runtime path overrides.

A later production mapping may provide these inputs through a protected host-only configuration mechanism. That mapping is intentionally out of scope here.

## Offline regression gate

`tests/test-balcony-watering.sh` replaces `curl` and `sleep` with local mocks, uses a reserved `.invalid` URL, and never performs a real network request or pump action. It verifies:

1. all 12 active sensors valid with retired 2/14/15 absent => watering path is reachable;
2. retired 2/14/15 unavailable => still valid; active flower 5 missing/unavailable/unknown => skip;
3. one required sensor missing => skip;
4. one required sensor unavailable => skip;
5. one required sensor unknown => skip;
6. empty Home Assistant response => skip;
7. malformed sensor-state JSON => skip; retired-only states => skip;
8. no runtime `last_updated` dependency;
9. failed OFF HTTP requests preserve the trap-OFF safety path;
10. HTTP 200 for ON without a switch transition does not start the timed watering window and does not trigger a duplicate ON retry;
11. HTTP 200 for OFF without an `off` state keeps the cleanup obligation active;
12. malformed switch-state feedback fails closed and never triggers a second ON;
13. below 27 C => no delegation, at 27 C => delegation, with the same 12-sensor gate;
14. all `curl` traffic remains inside the local mock.

The repository-wide `make validate` gate includes this regression together with shell syntax, secret scanning, and public-repository safety checks.

`tests/test-balcony-watering-autumn.sh` covers the cold-season controller with the same offline technique — local `curl` and `sleep` mocks, a reserved `.invalid` origin and a locally intercepted Telegram endpoint, so no request leaves the machine and no pump action is possible. It verifies:

1. three dry pots of twelve with a mild night => exactly one confirmed `on,off` cycle, one watering message and a recorded day marker;
2. retired 2/14/15 `unavailable` => still waters and never counts as dry;
3. active sensor missing, `unavailable`, `unknown` or unexpected categorical value => skip with an error message, no pump request, no day marker;
4. empty or malformed Home Assistant state payload => skip with an error message;
5. one dry sensor => quiet skip, no Telegram message at all;
6. tray already moist => quiet skip;
7. forecast low at or below the frost threshold => blocked with a frost message and no pump request;
8. low current temperature blocks even when only the weather-service forecast is available;
9. unusable temperature data => skip with an error message;
10. an unexpected `on` before the run => confirmed OFF, abort and error message, never a watering cycle;
11. HTTP 200 for ON without a switch transition => fail closed with trap OFF, never a duplicate ON;
12. unconfirmed OFF => retries plus trap OFF, and the day is still recorded because ON was confirmed;
13. a second invocation on the same day => no pump request and no message;
14. duration is honoured and a duration above the 180 s device limit is rejected;
15. dry-run => every gate runs, no pump request, no message, no day marker;
16. post-cycle calibration readback is logged, and only sent to Telegram when explicitly enabled;
17. the lock refuses an overlapping run.

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
