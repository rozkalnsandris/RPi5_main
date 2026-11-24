# Native HA unified balcony watering — design proposal (#1554)

Status: **design only, no executable controller, no LIVE authority**. Owner review/merge accepts this proposed target policy for subsequent source design/implementation, not activation. Existing HA preview and Telegram cutover (#1550, #1552, #1523) remain unchanged. Historical Hermes controller evidence (#1474) does not prove current installed state.

## 1. One policy, one start path

Recommend the reviewed cold-season policy for both the 11:00 Europe/Berlin automatic request and a future authenticated manual /laist request. This is deliberately stricter than the historical manual safety permit, which could bypass automatic dry/wet quorum. Do not enable manual requests before cutover; keep /laist_* duration overrides denied even after the proposed initial release. No force or summer-mode override.

| Gate | Proposed admission |
| --- | --- |
| Sensor set | Exactly channels 1, 3–10, 12; 2/11/13/14/15 retired |
| Degraded | At most 2 unavailable/unknown/missing; count as assumed moist, never dry |
| Invalid | Any other categorical value, including videjs, blocks |
| Moisture | At least 2 measured dry; measured + assumed moist below 8 |
| Freshness | Verified current device session and fresh observations; stale retained states cannot qualify as measured |
| Frost | Valid Celsius current temperature and complete daily forecast covering the next 24 h; minimum strictly above 2 C |
| Pump | Verified available, fresh reported OFF; independent physical OFF access |
| Daily cap | At most one admitted start attempt per local date; reserve before ON |
| Duration | Fixed 45 s candidate, no user-supplied duration; ESP32 absolute 180 s ceiling remains independent |

The 10-channel proposal follows the reviewed RPi5 autumn source and ESP32 source, not the historically installed 12-channel controller. It is a policy change relative to the latter. Source ESP32 README and current code supersede the old 12-channel description in its MQTT documentation. The 45 s candidate is not calibrated. Do not interpret the successful preview as proof of fresh sensors, relay safety, or permission to water.

## 2. Minimal native architecture

One HA script in single mode owns the complete admission and cycle; no queue, parallel/restart mode, secondary start script, Python daemon, collector, or duplicate policy. The existing read-only dry-run remains available for diagnostics; extract/reuse the same evaluation in implementation with parity tests rather than maintain two divergent rules. Its hypothetical response must never itself authorize ON. The time automation calls the common script directly; a future authenticated Telegram /laist route and HA dashboard request must call the same entry point, not publish directly. Ignore/reject competing requests with no deferred execution. Keep current Telegram notification/STOP routing independent; notification errors cannot affect OFF.

All entry points are trusted only within the verified HA/MQTT authorization boundary. Inventory direct HA switch actions, dashboards, automations, services, MQTT publishers, legacy Hermes jobs and firmware command paths. Hide/replace dashboard ON affordances and eliminate or independently constrain bypass publishers before activation; hiding a UI control is not access control. Retain independent OFF and physical power isolation. If exclusivity cannot be established, no active controller.

## 3. Admission and restart-safe reservation

Use the existing date-only helper as an attempt marker, never a claim of watering. No backdating, clearing, fixed initial date or reuse of today's reservation. A second, default-OFF session arm latch (proposed YAML input_boolean with initial false, not restored ON) is required if implementing the pure HA design. It must be false/unavailable at HA startup and unknown state fails closed. No automatic rearm after restart, reload affecting the control path, clock discontinuity, lost acknowledgements or interruption. Verify these semantics on the installed version; a startup automation alone has an ordering race and is not proof of default-OFF.

When unarmed, the separate authorized recovery/arm procedure requires fresh confirmed software OFF, independent physical stop availability, exclusive scheduler/publisher evidence, valid local clock and current date. Conservatively reserve the **whole recovery day** and read back the exact date before arming for a subsequent day. If storage rolled back after a crash this blocks same-day replay. Reject earlier/future dates relative to the known valid session/clock; require a stable date during admission and no ambiguous midnight transition. No automatic arm or marker reset. A power loss, restore, reload, or script cancellation must not silently permit a new start; prove the latch behavior for each case or keep disabled. Manual rearm after restart is an explicit safety/availability tradeoff, not a second daily scheduler.

Under the single-script admission lock: reject unarmed, busy, invalid date, same-day reservation, stale/invalid evidence, frost, insufficient dry count, or non-OFF. Capture D from the verified local clock. Recheck current state and date immediately before reservation, write D once, read back the exact entity/date/attributes, then recheck volatile admission inputs and arm state. Require no intervening STOP/inhibit and no conflicting writer. Failure or ambiguity consumes the reservation; do not issue or retry ON. The marker is reserved even if ON ultimately fails. No other writer may clear it.

HA documents normal input_datetime restore, not crash-durable atomic write/flush at service-return time. Readback is necessary but not sufficient for durability. The recovery-day lockout and default-OFF session latch are proposed protection, not proof. If crash, reload, clock rollback or storage-restore tests cannot demonstrate a safe lockout, require a durable device-side reservation or equivalent proven mechanism before LIVE. Same-day restart recovery must not depend solely on the restored date.

## 4. Actuator protocol: unresolved activation gate

ESP32 source at b6b222d2f2df6b4b03b908a19f4681fcd7fec6e9, src/main.cpp: MAX_PUMP_SECONDS=180; processHACommand starts a 180 s session for ON; publishDiscoveryPump specifies QoS1; startPump publishes software ON before GPIO ON. The current urgent STOP/OFF path immediately sets GPIO OFF, increments pumpStopEpoch and suppresses queued starts older than that epoch. That does not prove rejection of an ON arriving *after* STOP or a replay crossing reconnect/boot. A retained ON state is not physical feedback. Legacy text commands may extend a running session. A single HA service invocation is not exactly-once MQTT delivery.

Prefer a native HA controller without a new runtime service, but do not enable it on the assumption that HA delay/timeout alone provides the 45 s bound or that a STOP epoch solves all interleavings. Before executable release, prove a bounded start protocol with one logical start, no retain, no replay/retry/restart after cancellation and no start after an accepted STOP from an earlier admission. If existing device semantics cannot meet these requirements, the minimal separate firmware/source outcome must provide a fixed bounded device-side cycle and single-use, expiring, session-bound admission with STOP invalidation (no rearm via a delayed duplicate). Define/prove the exact protocol in that outcome; this document introduces no new command/topic. Do not substitute repeated ON or legacy /laist_X for the fixed cycle.

Acceptance contract for the later controller:
- Set a conservative may-be-ON obligation before dispatch; send one logical start only after the reservation. No repeated ON on timeout, cancellation or ambiguity.
- Bound ON acknowledgement to at most five seconds; require a new session-correlated device acknowledgement, not a stale retained state or HA service success. Start the 45 s budget at dispatch at the latest; never extend it waiting for an acknowledgement. Prefer device enforcement of the short bound in addition to the existing 180 s cap.
- Independent emergency STOP must never wait behind admission, weather, Telegram or script completion. Cancel/invalidate outstanding admission before it can issue a late start; prove device handling for STOP before dispatch, in transit, during ON, and after reconnect. Physical power-off remains independent.
- On completion, interruption, unsafe state or ambiguous ACK, the later reviewed controller must have an explicitly approved bounded OFF safety path (at most three OFF attempts with bounded five-second software confirmation per attempt, no ON retry). Do not claim a generic HA finally block: waits/scripts can terminate on restart/error. Keep start admission inhibited on unresolved OFF, record the attempt, and require operator recovery. Device limit remains independent even when HA/broker unavailable. The future runtime safety protocol is distinct from agent LIVE authority: this design grants no OFF/ON action today.
- Never equate software OFF with physical OFF. Confirm actual firmware identity and NO wiring/physical cutoff before a supervised, separately authorized first physical cycle. Report watering only with matching software evidence and clearly distinguish physical verification.

## 5. Freshness and offline acceptance

Current source publishes periodic MQTT telemetry (60 s interval in ESP32 source). Device online/retained state alone and old HA last_updated values do not prove fresh samples. Establish non-retained current-session sample/heartbeat evidence and a bounded freshness contract (proposed 120 s maximum, prove cadence and reconnect behavior). If HA cannot distinguish replay from fresh observations using existing telemetry, add only the minimum source-level evidence mechanism needed; do not count an unverified dry value. No new daemon. Verify actual bindings and forecast shape before runtime staging.

Next implementation tests must exercise the actual policy and state transitions offline without network, MQTT or pump. Required cases:

| Scenario | Required result |
| --- | --- |
| Missing/invalid/future/today marker; wrong timezone; date rolls during admission | zero starts |
| Concurrent schedule/manual; duplicate caller; helper write/readback error or collision | at most one admitted attempt, no start on ambiguous write |
| 0/1 dry; >=8 moist incl. assumed; 3 degraded; videjs; stale/retained-only; forecast missing/low <=2 C | zero starts |
| Valid inputs; 3 or more measured dry, at most 7 moist incl. assumed | evaluate candidate only after all other gates; 2 dry + 8 moist must block |
| STOP before/during start, delayed duplicate after STOP, network reconnect, cancellation | no late/replayed ON; independent OFF |
| HA crash before/after reserve/dispatch; loss of restored marker; script reload; clock rollback | no restart or duplicate start; disarmed until approved recovery, recovery day reserved |
| Missing ON ACK; OFF ACK timeout; notification failure | bounded safety OFF path, no ON retry, inhibit on unresolved outcome |
| Retired channel changes; manual duration request; competing scheduler/publisher | no override, no duplicate or unreviewed start |

Test fixture counts must be consistent: for the current 10-channel binary measured/assumed policy, 2 dry plus 8 moist blocks; at least 3 measured dry is necessary for the wet guard. Preserve both independent gates rather than quietly alter thresholds. Test shared automatic/manual parity. Test source defaults disabled/inert and absence of external start paths. Simulation/staging must never use an executable real actuator against live HA.

## 6. Exclusive staged cutover (future separate approvals)

1. Review/merge this proposed policy. Resolve the device protocol and freshness gates with focused source and offline tests; then review a complete inert HA controller and scheduler reference. No executable live automation in this design.
2. Read-only preflight exact installed firmware, HA bindings, sensor/forecast evidence, helper/latch recovery semantics, all start publishers and unique legacy Hermes schedule/job identity (not raw config). Verify the existing /stop path and physical isolation. Stage only under separate owner authority with no active scheduler or manual start; never use current source alone as runtime proof.
3. In a no-watering maintenance window, separately owner-authorize disabling only the identified legacy watering scheduler and prove no running job or other start source. No overlapping schedulers. Reserve the cutover date in HA after legacy shutdown verification; arm only after all recovery/actuator gates pass. Activate the reviewed 11:00 HA scheduler separately; keep manual denied until a separately approved shared-entry cutover. If any check fails, leave start paths disabled where already disabled; STOP, no automatic rollback or legacy re-enable.
4. First supervised actual cycle needs exact separate authority, an owner present with physical cutoff and safe weather/soil conditions, and verification of the bounded cycle/OFF. Do not force an attempt or bypass a gate to test. No automatic restart, OTA, credential change or new Hermes job. Observe ordinary notification delivery without a redundant forced pump test.

Open gates: current installed firmware and physical wiring, fresh telemetry, cancellation/replay-safe bounded device protocol, persistence/recovery evidence, sole scheduler/publisher inventory and later owner LIVE approval. Dry-run acceptance (#1550) and helper bootstrap (#1552) do not close these gates.

Official HA references: https://www.home-assistant.io/docs/script/ (single mode and error handling); https://www.home-assistant.io/building-blocks/wait_template/ (restart terminates waits); https://www.home-assistant.io/integrations/input_datetime/ (restore); https://www.home-assistant.io/integrations/input_boolean/ (initial state); https://www.home-assistant.io/docs/automation/how-automations-react-to-changes/ (startup trigger limitations).
