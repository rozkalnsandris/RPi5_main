# Native HA autumn watering decision — dry-run only (#1550)

The source-only script `ops/homeassistant/balkons-watering-dry-run.yaml` is a scripts.yaml mapping (not a complete configuration file). It is **not installed, scheduled, or capable of starting the pump**. Its only action is a read of the daily weather forecast; it computes variables and returns a response. It never changes a helper, sends a notification, calls a watering script or publishes MQTT. No Hermes, HA, or firmware change is implied by merge.

## Policy and deliberate differences

The proposed policy follows the ten-sensor autumn controller in `docs/BALCONY_WATERING_CONTRACT.md`: channels 1, 3–10 and 12; at least two measured dry; at most two absent/unknown/unavailable (counted as assumed moist, never measured); eight measured-plus-assumed moist blocks; 45 seconds is a hypothetical duration, not a command. Unknown values including `videjs` block because the actual canonical shell implementation currently rejects that value despite documenting it as a category. Resolve that discrepancy separately before live parity; do not silently relax it.

The historical installed Hermes controller was observed with twelve sensors and strict availability. This candidate is **not** equivalent to that installation; switching to ten sensors or tolerating two missing sensors might resume watering. Approval of the ten-sensor policy and current evidence are mandatory before activation.

Frost: require available Celsius weather, finite current temperature and a unique finite daily minimum (`templow`) for every local date intersecting the next 24 elapsed hours. Taking the minimum across complete calendar days is deliberately conservative and may overblock. Missing forecasts, missing lows, ambiguous timestamps or non-Celsius units block. Never substitute a daily high for a low.

Require Europe/Berlin, pump software state OFF and a valid date-only `input_datetime.balkons_last_watering_attempt` strictly before today. This helper is only a proposed binding; **do not create or initialize it in this outcome**. Absence, invalid or future date, and an attempt today block. A helper with a plausible date is not proof of earlier physical behavior. No date is written in the preview.

## Offline validation

With Jinja2 3.1.6, MarkupSafe 3.0.3 and PyYAML 6.0.3 installed in an isolated test environment, run `python3 tests/test-balkons-ha-watering-dry-run.py`. The balcony CI job installs these test-only pins in a temporary virtual environment. Tests render the actual YAML template against synthetic HA function stubs and verify the exact action allowlist, policy boundaries and adverse inputs. This is not an HA Core execution or proof of entity bindings.

The response always identifies `dry_run: true`, `live_authorized: false`; even `would_water` is hypothetical. Any exception or missing response is a blocked preview, not a permit. Treat the first blocking reason as diagnostic only.

## Next gate (not authorized here)

Before any HA staging, verify actual entity IDs and supported daily forecast response shape, temperature unit/timezone, moisture availability/freshness semantics and exact intended script name. Do not infer physical OFF from switch state. For an eventual active controller, separately establish last-watering/attempt provenance across Hermes and HA, restart-safe pre-ON reservation and readback, one scheduler and shared manual/automatic admission, non-repeating ON, bounded acknowledgement and OFF handling, independent STOP, and the ESP32 180-second device-side limit. No automatic enable, manual /laist* changes, Hermes disable or pump test from this source. Keep existing scheduling unchanged.

Official HA references:
- https://www.home-assistant.io/docs/scripts/
- https://www.home-assistant.io/docs/automation/action/
- https://www.home-assistant.io/integrations/weather/
- https://www.home-assistant.io/docs/templating/dates-and-times/
- https://www.home-assistant.io/integrations/input_datetime/

## Conservative one-time day-marker bootstrap (#1552)

This is a source-only operator runbook, not permission to execute it. A previous confirmed-ON date and a date reserved before attempting ON have different meanings. The historical record is insufficient to establish the most recent attempt with certainty. Rather than invent a historical date, reserve the current Europe/Berlin calendar day as unavailable for a new attempt. This is deliberately conservative and is **not** evidence that watering occurred. It only blocks this HA preview for that day; it does not inhibit Hermes or any other controller.

### Separately authorized operator procedure

1. Before changing anything, verify the HA timezone is Europe/Berlin and record the current local date as D (ISO YYYY-MM-DD). Confirm the exact helper ID is absent from both the entity registry and states, including disabled entities; check for name/ID collisions and ensure there are no unexpected consumers or writers and no active HA watering controller. Verify the pump software state is OFF, without changing it. If any check is uncertain, stop.
2. In Settings > Devices & services > Helpers, create one Date and/or time helper named `Balkons last watering attempt`, selecting Date only. Verify the resulting entity ID is exactly `input_datetime.balkons_last_watering_attempt`. Do not configure a fixed initial value: restoring state is necessary for future reservation semantics, whereas a fixed initial date can overwrite the restored value at startup. Creation is permitted only by separate explicit live approval.
3. Before setting the date, confirm the local date is still D, the new helper has `has_date: true` and `has_time: false`, and its identity is unchanged. Use Developer tools > Actions once with the exact entity target and literal verified date D (replace the placeholder below; never use a historical or future date):

   ```yaml
   action: input_datetime.set_datetime
   target:
     entity_id: input_datetime.balkons_last_watering_attempt
   data:
     date: "YYYY-MM-DD"
   ```

4. Read back the helper through Developer tools > States without using Set state. Require the same ID, exact ISO state D, `has_date: true`, `has_time: false` and unchanged local date D. Record D and the verified result as a conservative bootstrap reservation, not a confirmed watering event. No schedule, automation, MQTT command, pump action, restart, or Hermes change is part of this procedure. On any failure, collision, unexpected consumer, or date rollover, stop; no retry, deletion, overwrite, or rollback without a separately approved recovery plan.

### Acceptance and limits

On the same date D, a separately authorized manual dry-run invocation with the pump software OFF and correct timezone should return `decision: block_already_attempted`, `dry_run: true`, `live_authorized: false`. Timezone and pump-state checks precede the day-marker check; forecast, sensor and frost decisions follow it. A missing response or an earlier block is not a successful bootstrap preview test. The preview must remain unchanged. Do not invoke an actual watering action to validate it.

On later days, a past date removes only this particular preview block; it is not authorization to water. Before any cutover, independently establish an exclusive scheduler, common manual/automatic admission, a restart-safe pre-ON reservation and readback protocol, and the remaining safety prerequisites in the preceding section. Do not clear or backdate the reservation to force a preview or live run. A successful bootstrap neither authorizes activation nor proves a physical pump state.

Official HA action reference: https://www.home-assistant.io/actions/input_datetime.set_datetime/
