# Balcony watering — controlled autumn/winter rollout plan

Issue: #986. Source contract: [BALCONY_WATERING_CONTRACT.md](BALCONY_WATERING_CONTRACT.md). Reviewed autumn source: `ops/bin/balcony-watering-autumn` (#930, PR #931). **Status: SOURCE PLAN ONLY — NOT LIVE-READY.**

## Decision: keep the system simple

Use the **existing ESP32 → MQTT → Home Assistant → Hermes** control chain and one cold-season controller. Do not add a new broker, daemon, scheduler, parallel watering controller, device firmware or WeatherNext dependency to solve the seasonal change.

The selected *candidate* is `ops/bin/balcony-watering-autumn`: 11 active flowers (1, 3–10, 12 and 13), a minimum dry-sensor quorum, frost forecast guard, at most one 45 s candidate cycle per day and switch-state-confirmed ON/OFF. These are **source properties, not observed live-device behavior**. The device-side 180 s hard limit remains independent.

Historical read-only evidence showed three enabled private Hermes jobs: 07:00 and 23:00 invoked `laistisana_2x.sh`; 14:00 invoked `laistisana_2x_karstums.sh`. The historical primary script used the superseded 14-sensor gate. This evidence is **not current authority to modify those jobs**. Their identity, state, schedule and script bindings must be freshly re-proven.

## Gate 0 — release choice (owner decision before LIVE)

**Do not deploy a moving Git branch.** On the day of a proposed cutover:

1. Obtain fresh canonical `RPi5_main/main`, `AGENTS.md`, the autumn contract, open PRs/reviews and exact-head CI.
2. Resolve the source policy of [PR #977](https://github.com/rozkalnsandris/RPi5_main/pull/977), which is open at plan creation: whether missing active moisture sensors **block** the run (the current merged source) or are **presumed wet** and excluded from confirmed dry counts (the proposed change), and whether results go to the RPi5 notifications bot or the balcony bot via Home Assistant MQTT. **Choose one reviewed, merged implementation; do not mix the two.** An explicit owner decision to use the current merged source is also acceptable if the open PR remains unmerged.
3. Freeze one full **merged Git SHA** and the SHA-256 of the exact `ops/bin/balcony-watering-autumn` bytes. Verify all repository-required CI and review gates for that release. Never use an unmerged PR HEAD for LIVE.
4. Freeze the candidate configuration contract: 11 active sensors, default dry quorum 2, wet guard 9, frost threshold 2.0 °C with forecast required, one daily decision, at most one 45 s candidate cycle, and the 180 s firmware boundary. Treat changes to any of these as a **new owner decision**, not a silent rollout detail.
5. Confirm the selected season and notification destination with the owner. If winter watering is not wanted, **STOP** rather than automatically activating a different schedule.

Discovery baseline on 2026-10-12: `main` `86c2a1917f39717632de73fcc575596ff2865f84`. This is **not** a frozen future rollout SHA.

## Gate 1 — sanitized read-only production preflight (separate scoped authority)

Collect only **derived allowlisted evidence** from the private Hermes scheduler and actual script target. Do not print/store raw job JSON, job prompts, commands, paths, logs, environment, HA credentials, MQTT payloads or Telegram IDs in Git, issues or chat.

Required report fields:

- target host identity; verified source checkout/immutable artifact identity; current host checkout state, tracked cleanliness and ancestor relation to chosen release;
- exactly which **three original watering jobs** are enabled, their clock times, timezone interpretation and direct Hermes script-name bindings; preservation count/fingerprint for every unrelated job;
- actual **referenced and resolved** live file identity for `laistisana_2x.sh` and `laistisana_2x_karstums.sh`: owner/type/mode/size, one-link and symlink check, SHA-256 and sensor-gate/switch-confirmation classification;
- if the selected autumn controller already exists, its exact target identity, mode/owner/hash and whether another schedule invokes it; refuse an ambiguous or conflicting install target;
- protected-runtime capability metadata only: availability of `HASS_URL`, `HASS_TOKEN`, weather entity, necessary notification transport and writable state/lock/log directories, **without exposing values or credential paths**;
- read-only HA/ESP32 status evidence as separately authorized: relevant 11 entity availability, weather/frost forecast usability, MQTT/HA health and software-reported pump state. Software `off` is **not independent physical current/flow evidence**;
- time-window safety: no watering run currently executing, no concurrent scheduler/owner manual start and adequate margin before the next existing scheduled trigger; confirm the 11:00 job will mean the intended local clock time.

Any missing, inconsistent or unreadable binding => **BLOCKED before mutation**. Historic SHA, past dry-run or GitHub merge is insufficient.

## Gate 2 — exact one-shot LIVE envelope (new explicit owner authorization)

A later owner authorization must name **host, merged SHA, immutable source hash, exact private target classes, expected baseline fingerprints, scheduled-job identities, permitted writes, recovery boundary, and hard exclusions**. Source merge/this plan grants none of those permissions.

The reviewed one-shot intent (not implemented by this document) is:

1. **Prepare and verify private recovery artifacts before replacing anything**: protected backups of the existing script(s), target metadata and original **three** job definitions, plus a restoration method preserving ownership, modes, schedule identity and credential binding. Backup creation is itself a host mutation and must be in the LIVE envelope. No backup contents leave the host.
2. Confirm the release's exact bytes and hash via a reviewed read-only GitHub artifact/checkout path; a host checkout update (`fetch` / `ff-only`) is a **separate explicitly listed** mutation if needed. No reset, rebase, clean, force operation or broad sync.
3. Stage only the fixed reviewed `balcony-watering-autumn` artifact with locked owner/mode and current private credential binding. Do **not** overwrite `laistisana_2x.sh`, the heat gate or unrelated scripts. Do not replace historical Hermes state wholesale.
4. Run **one owner-authorized staged dry-run** (`BALCONY_AUTUMN_DRY_RUN=1`) through the same protected runtime wiring: check sensor, dry-quorum, forecast/frost and switch-state decision **without a pump command, Telegram send or last-watered marker**. This dry-run is **not purely read-only**: the source may create a state directory, lock, temporary snapshot and log entry and may call Home Assistant's read-only forecast service. These host-side effects must be within the explicit LIVE authority. If the software-reported pump is already ON, the dry-run aborts without sending OFF.
5. Only after stage and dry-run acceptance, change the **four exact schedule intents as one bounded cutover**: disable the 07:00, 14:00 and 23:00 legacy watering jobs; create/enable precisely **one** 11:00 autumn decision with the fixed staged script, explicit intended timezone and Hermes `deliver=local`. Keep *all* unrelated jobs, their payloads and identifiers unchanged. No overlapping old and new schedules; do not start the new job manually to test it.
6. Compare the post-cutover sanitizer projection with the frozen baseline: old three disabled, exactly one 11:00 autumn job enabled, no duplicate, correct script hash, forecast and credential bindings preserved, all other jobs untouched, no accidental pump command.

**Do not** install a broad deployer, change HA/MQTT/broker, mutate ESP32, run OTA/flash, change bot tokens, restart services or start/stop the pump. Do not automate a real watering acceptance test. A physical trial needs a **separate exact owner authorization**.

## Gate 3 — acceptance and observation

Release/cutover acceptance is limited to source identity, **sanitized schedule and file metadata**, authorized dry-run evidence, safe state checks and operator review. Report these distinctions explicitly:

- **SOURCE_READY** = merged reviewed source and offline CI, but not live;
- **DRY_RUN_PASS** = gates evaluated with physical actuation suppressed, but not proof of live pump performance;
- **SCHEDULE_READY** = the four intended job states verified, without assuming the next execution succeeds;
- **OBSERVED** = later, separately authorized read-only evidence of the actual 11:00 outcome and the chosen notification channel.

Check the first scheduled **decision** after cutover for normal no-watering, frost/error skip or permitted watering outcome and the one-cycle-per-calendar-day marker. Its logs may contain private telemetry: expose only a sanitized outcome class, timestamp class and success/failure flags. No automatic repeated manual run to “verify” it. The candidate 45-second duration is not calibrated; defer duration changes until independently assessed under separate authorization.

## Fail-closed / recovery contract

Before the first mutation, any failed gate means **BLOCKED — no apply**. After the first authorized mutation, an unexpected response, permission error, timeout, head drift, ambiguous job state, source/hash mismatch, missing switch confirmation or unverified backup means **STOP**; collect only minimal read-only evidence. **No automatic retry, rollback, cleanup, resume, replacement write, cron re-enable or opposite pump command**. Recovery/restoration must be separately and explicitly owner-authorized against fresh state, even if the backup was prepared. A failed transition may leave watering disabled; do not conceal this or silently re-enable old fixed watering.

Three identical failed operation attempts require STOP and failure-layer analysis; this is **not** authority to attempt them three times.

## Source-only evidence and remaining gates

- Offline regression is already part of `make validate`: `tests/test-balcony-watering.sh` and `tests/test-balcony-watering-autumn.sh` use mocked network/pump paths. CI establishes source correctness, **not host adoption**.
- This plan intentionally adds **no executable installer, scheduler editor, private binding, secrets, live config, new service, or actuator command**.
- **Current result: READY for source review; BLOCKED for LIVE** until Gate 0 owner release choice, fresh Gate 1 read-only evidence and a reviewed fixed-target executor/recovery envelope exist.
- Only after a separate **MERGE** decision for this plan may a future bounded **COMPOSITE LIVE** request be prepared. Neither merge nor source checks authorize runtime action.
