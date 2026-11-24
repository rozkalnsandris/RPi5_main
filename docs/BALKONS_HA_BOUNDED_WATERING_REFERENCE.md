# HA bounded watering — inhibited native reference (#1556)

**SOURCE ONLY. Do not install, import, enable, execute, or use as an OTA/cutover instruction.** This reference deliberately cannot send even a ticket request. The existing HA preview, Telegram STOP and legacy watering schedule are unchanged. The ESP32 candidate is merged source, not installed firmware evidence.

## Source binding and scope

- HA design: #1554 / PR #1555, main at discovery `f7ed1c407fe5c901be3197c0e0f03ec0d210b3ce`.
- ESP32 candidate: balcony-irrigation-esp32#69 / PR #70, `2664df2d5516452951b8934e9deb2ec78cba4f13`, `docs/HA_BOUNDED_WATERING_PROTOCOL.md`.
- Reference package: `ops/homeassistant/balkons-watering-bounded-reference.yaml`. It is not included from any deployed configuration. Preserve the existing marker and read-only dry-run.

The native reference uses one single-mode admission script, a non-restored default-OFF owner arm latch, a default-ON incomplete-attempt latch, a reply mailbox and a disabled 11:00 local schedule. The second latch prevents an interrupted attempt from silently becoming eligible on a later day while the owner arm remains ON. No code automatically turns the arm ON. Recovery and any future arm transition require a separate reviewed procedure. The source contains literal false entry gates in both scripts and the scheduler, and additional false freshness/release conditions in the start sequence. Turning a helper or automation ON cannot release it.

## Admission and reply handling

The preview is only a negative filter, never a live permit. Before dispatch, the reference requires OFF software state, armed/not pending, valid local date and marker, then latches pending. A pre-subscribed MQTT reply sensor avoids opening a one-off subscription after a fast reply. The non-retained QoS1 ticket request has a fixed 16-hex correlation ID. Only an exact matching offer shape (24-hex ticket) is sampled; capture once, never refresh or retry, reject any mailbox replacement before dispatch. Verify the day reservation with exact readback and unchanged sensor/weather snapshot, arm and pending state; require a short elapsed request window. A stable categorical snapshot is **not** proof of fresh telemetry. The hard false freshness and dispatch gates must remain until that evidence and the remaining safety gates are addressed in a separate source review.

A single non-retained QoS1 start uses the frozen ticket. Software ON must match it within five seconds; OFF must correlate to the same ticket and the switch must report OFF by the conservative HA deadline (45 seconds from dispatch, with the device deadline measured from earlier ticket issuance). Missing, overwritten, late, or ambiguous replies fail closed; never repeat ON. On a clean correlated result, clear only pending; on uncertainty, keep pending latched, disarm, and use the proposed bounded OFF-only recovery (maximum three sends, five-second confirmation waits). The independent STOP reference cancels admission/disarms before sending OFF; it does not wait for the start script to finish naturally. The existing live Telegram STOP remains unchanged, not yet routed through this reference.

## Explicit unresolved release gates

1. The firmware candidate does not yet supply independently verified current-session sensor/pump freshness. Retained MQTT states and HA expiry timers cannot establish it. Define and test the minimum fresh-sample evidence, including disconnected sensors, stale/replayed samples, exact session binding and current device identity.
2. A single MQTT state mailbox is not a guaranteed first-event queue. A second offer may overwrite the first before HA samples it, and a quick OFF may overwrite ON. The reference rejects changes after capture and fails closed on missed correlation, but does **not** prove strict first-offer semantics. Prove the required event capture and cancellation ordering in actual HA Core and broker/device integration before release; if necessary change the minimal protocol rather than add a general message-processing service. Random request IDs are correlation only, not durable uniqueness or authentication. A delayed ticket after STOP is not safe unless the original HA admission is irrevocably canceled. Verify STOP from every entry point, cancellation before offer, between checks and dispatch, during ON, disconnect and reconnect. Do not claim that separate HA service actions form an atomic transaction. A failed helper action, script cancellation or restart can bypass later script steps; the pending/arm defaults are proposed protection, not proven durability.
3. The 45-second device deadline currently uses cooperative firmware timing; a physical short cutoff under stalls, firmware identity, physical NO wiring, sensor calibration, and independent power isolation remain unverified. Verify day reservation and latch recovery for crash/reload/clock rollback, all direct MQTT/HA start publishers, sole scheduler, and the actual installed HA configuration. The only acceptable release is a separately reviewed source outcome with real evidence, then separate owner authorization. Do not simply remove the literal false conditions or toggle the helpers. No overlapping legacy and HA schedules; no forced watering to test a missing gate.

## Offline evidence

`tests/test-balkons-ha-bounded-reference.py` parses the actual reference YAML and renders its key Jinja predicates with synthetic state; it checks hard gates, exact non-retained protocol action count/order, reservation ordering, correlation, cancellation, deadline boundaries and bounded OFF recovery. It is registered in the balcony CI group. It does not execute any HA service, instantiate HA Core, publish MQTT, simulate all asynchronous interleavings, or measure physical timing.

HA official references:
- https://www.home-assistant.io/docs/script/
- https://www.home-assistant.io/integrations/input_boolean/
- https://www.home-assistant.io/integrations/sensor.mqtt/
- https://www.home-assistant.io/actions/mqtt.publish/
- https://www.home-assistant.io/actions/script.turn_off/
- https://www.home-assistant.io/integrations/input_datetime/

Next source dependency: resolve device/session freshness and strict offer/cancellation evidence. Leave this package inert until reviewed release.
