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
