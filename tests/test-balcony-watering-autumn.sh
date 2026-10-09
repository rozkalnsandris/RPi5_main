#!/usr/bin/env bash
# Offline regression gate for ops/bin/balcony-watering-autumn.
#
# No network, no pump, no live Home Assistant: every curl URL is answered by a
# local mock and every sleep is a no-op. The Telegram endpoint is intercepted
# locally so message policy (real watering / error / frost block only) can be
# asserted without any outbound request.
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
autumn="$repo/ops/bin/balcony-watering-autumn"

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/state"
actions="$tmp/actions.log"
tg="$tmp/telegram.log"
logfile="$tmp/autumn.log"
switch_state="$tmp/switch-state"

cat >"$tmp/bin/curl" <<'MOCK_CURL'
#!/usr/bin/env bash
set -Eeuo pipefail
url=""
method="GET"
for arg in "$@"; do
    case "$arg" in
        http://*|https://*) url="$arg" ;;
        POST) method="POST" ;;
    esac
done

case "$url" in
    */api/services/switch/turn_on)
        code="${MOCK_ON_CODE:-200}"
        printf 'on\n' >>"${MOCK_ACTIONS:?}"
        if [[ "$code" == "200" && "${MOCK_ON_APPLY:-1}" == "1" ]]; then
            printf 'on\n' >"${MOCK_SWITCH_STATE_FILE:?}"
        fi
        printf '%s' "$code"
        ;;
    */api/services/switch/turn_off)
        code="${MOCK_OFF_CODE:-200}"
        printf 'off\n' >>"${MOCK_ACTIONS:?}"
        if [[ "$code" == "200" && "${MOCK_OFF_APPLY:-1}" == "1" ]]; then
            printf 'off\n' >"${MOCK_SWITCH_STATE_FILE:?}"
        fi
        printf '%s' "$code"
        ;;
    */api/services/weather/get_forecasts*)
        case "${MOCK_FORECAST_SERVICE_MODE:-ok}" in
            ok) printf '{"service_response":{"weather.forecast_home":{"forecast":[{"datetime":"%s","templow":%s}]}}}' \
                    "$(date -u -d '+6 hours' '+%Y-%m-%dT%H:%M:%S+00:00')" "${MOCK_FORECAST_MIN:-4.0}" ;;
            empty) printf '{"service_response":{}}' ;;
            malformed) printf '{bad-json' ;;
            *) echo "unknown MOCK_FORECAST_SERVICE_MODE" >&2; exit 96 ;;
        esac
        ;;
    */api/states/switch.balkona_laistisana_suknis)
        case "${MOCK_SWITCH_STATE_MODE:-valid}" in
            empty) exit 0 ;;
            malformed) printf '{bad-json' ;;
            valid) printf '{"state":"%s"}' "$(cat "${MOCK_SWITCH_STATE_FILE:?}")" ;;
            *) echo "unknown MOCK_SWITCH_STATE_MODE" >&2; exit 96 ;;
        esac
        ;;
    */api/states)
        case "${MOCK_SENSOR_MODE:-valid}" in
            empty) exit 0 ;;
            malformed) printf '{bad-json' ;;
            valid|retired|active_missing|active_unavailable|active_unknown|active_odd_state|one_dry|all_wet|retired_only)
                python3 - "${MOCK_SENSOR_MODE:-valid}" <<'PY'
import json
import os
import sys
from datetime import datetime, timedelta, timezone

mode = sys.argv[1]
active = [1] + list(range(3, 14))
retired = [2, 14, 15]
soon = (datetime.now(timezone.utc) + timedelta(hours=6)).replace(microsecond=0).isoformat()
target = 5
dry = [1, 3, 7]

states = []
for i in active:
    if mode == "active_missing" and i == target:
        continue
    state = "mitrs"
    if mode == "one_dry":
        state = "sauss" if i == 1 else "mitrs"
    elif mode == "all_wet":
        state = "mitrs"
    elif i in dry:
        state = "sauss"
    if mode in ("active_unavailable", "active_unknown", "active_odd_state") and i == target:
        state = {
            "active_unavailable": "unavailable",
            "active_unknown": "unknown",
            "active_odd_state": "kalibracija",
        }[mode]
    states.append({"entity_id": "sensor.balkona_laistisana_puke_%d" % i, "state": state})

if mode in ("retired", "retired_only"):
    for i in retired:
        states.append({"entity_id": "sensor.balkona_laistisana_puke_%d" % i, "state": "unavailable"})

weather = {"entity_id": "weather.forecast_home", "state": "cloudy", "attributes": {"temperature": float(os.environ.get("MOCK_TEMP", "11.5")), "forecast": [{"datetime": soon, "templow": float(os.environ.get("MOCK_FORECAST_ATTR_MIN", "6.0"))}]}}
if mode != "no_weather":
    states.append(weather)

print(json.dumps(states))
PY
                ;;
            no_weather|weather_badjson)
                python3 - "${MOCK_SENSOR_MODE:-valid}" <<'PY'
import json
import sys

mode = sys.argv[1]
active = [1] + list(range(3, 14))
dry = [1, 3, 7]
states = [{"entity_id": "sensor.balkona_laistisana_puke_%d" % i,
           "state": "sauss" if i in dry else "mitrs"} for i in active]
if mode == "weather_badjson":
    states.append({"entity_id": "weather.forecast_home", "state": "cloudy",
                   "attributes": {"temperature": "not-a-number"}})
print(json.dumps(states))
PY
                ;;
            *) echo "unknown MOCK_SENSOR_MODE" >&2; exit 97 ;;
        esac
        ;;
    https://api.telegram.org/*)
        for arg in "$@"; do
            case "$arg" in
                text=*) printf '%s\n' "${arg#text=}" >>"${MOCK_TG_FILE:?}" ;;
            esac
        done
        printf '{"ok":true}'
        ;;
    *)
        echo "unexpected curl URL in offline test: ${url:-<none>}" >&2
        exit 99
        ;;
esac
MOCK_CURL
chmod +x "$tmp/bin/curl"

cat >"$tmp/bin/sleep" <<'MOCK_SLEEP'
#!/usr/bin/env bash
exit 0
MOCK_SLEEP
chmod +x "$tmp/bin/sleep"

export PATH="$tmp/bin:$PATH"
export HASS_URL="http://home-assistant.invalid"
export HASS_TOKEN="offline-test-token"
export TELEGRAM_TOKEN="offline-test-token"
export CHAT_ID="12345"
export MOCK_ACTIONS="$actions"
export MOCK_TG_FILE="$tg"
export MOCK_SWITCH_STATE_FILE="$switch_state"
export BALCONY_AUTUMN_DURATION_SECONDS=45
export BALCONY_AUTUMN_SOAK_SECONDS=0
export BALCONY_AUTUMN_STATE_DIR="$tmp/state"
export BALCONY_AUTUMN_LOCKFILE="$tmp/autumn.lock"
export BALCONY_AUTUMN_LOGFILE="$logfile"

fail() {
    echo "balcony autumn watering regression: FAIL: $*" >&2
    exit 1
}

assert_actions() {
    local expected="$1"
    local actual=""
    [[ -f "$actions" ]] && actual="$(paste -sd, "$actions")"
    [[ "$actual" == "$expected" ]] || fail "expected actions '$expected', got '$actual'"
}

assert_tg_contains() {
    local needle="$1"
    [[ -f "$tg" ]] || fail "expected a Telegram message containing '$needle', none was sent"
    grep -qF -- "$needle" "$tg" || fail "expected Telegram message containing '$needle', got: $(paste -sd'|' "$tg")"
}

assert_tg_count() {
    local expected="$1"
    local actual=0
    [[ -f "$tg" ]] && actual="$(wc -l <"$tg")"
    [[ "$actual" == "$expected" ]] || fail "expected ${expected} Telegram message(s), got ${actual}: $(paste -sd'|' "$tg" 2>/dev/null)"
}

reset_run() {
    : >"$actions"
    : >"$tg"
    : >"$logfile"
    rm -f "$tmp/state/last-watered"
    printf 'off\n' >"$switch_state"
}

run_autumn() {
    set +e
    bash "$autumn" >"$tmp/stdout" 2>"$tmp/stderr"
    rc=$?
    set -e
}

bash -n "$autumn"
[[ -x "$autumn" ]] || fail "autumn controller source must be executable"
! grep -q 'FRESH_LIMIT' "$autumn" || fail "timestamp freshness limit must not return"
if grep -Ev '^[[:space:]]*#' "$autumn" | grep -q 'last_updated'; then
    fail "runtime code must not depend on last_updated"
fi
# retired flowers 2/14/15 must never appear in the required sensor set
! grep -qE 'ACTIVE_SENSORS=\(.*[^0-9]2[^0-9].*\)' "$autumn" || fail "retired flower 2 must not be active"
! grep -qE 'ACTIVE_SENSORS=\(.*1[45].*\)' "$autumn" || fail "retired flowers 14/15 must not be active"
# the ESP32 hard limit must not be raised
grep -q 'ESP32_MAX_SECONDS=180' "$autumn" || fail "ESP32 180 s hard limit must be preserved"

export MOCK_ON_CODE=200 MOCK_OFF_CODE=200 MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1
export MOCK_SWITCH_STATE_MODE=valid MOCK_FORECAST_SERVICE_MODE=ok MOCK_FORECAST_MIN=4.0

# 1: three dry pots of twelve, mild night => one confirmed cycle, one message,
# and the day marker is written.
export MOCK_SENSOR_MODE=valid
reset_run
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 1 expected exit 0, got ${rc}"
assert_actions 'on,off'
assert_tg_count 1
assert_tg_contains 'Balcony autumn watering done: 45s'
assert_tg_contains 'dry before 3/12 (1,3,7)'
[[ -f "$tmp/state/last-watered" ]] || fail "case 1 must record the watering date"
[[ "$(cat "$tmp/state/last-watered")" == "$(TZ=Europe/Berlin date '+%Y-%m-%d')" ]] || fail "case 1 recorded an unexpected date"

# 2: retired sensors 2/14/15 unavailable never block and never count as dry.
export MOCK_SENSOR_MODE=retired
reset_run
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 2 expected exit 0, got ${rc}"
assert_actions 'on,off'
assert_tg_contains 'dry before 3/12'

# 3: an active sensor that is missing, unavailable, unknown or reports an
# unexpected categorical value is uncertainty, not dryness, and blocks the run.
for mode in active_missing active_unavailable active_unknown active_odd_state; do
    export MOCK_SENSOR_MODE="$mode"
    reset_run
    run_autumn
    [[ "$rc" -eq 0 ]] || fail "case 3 (${mode}) expected exit 0, got ${rc}"
    assert_actions ''
    assert_tg_count 1
    assert_tg_contains 'skipped'
    [[ -f "$tmp/state/last-watered" ]] && fail "case 3 (${mode}) must not record a watering"
done

# 4: Home Assistant transport and JSON failures fail closed with a message.
export MOCK_SENSOR_MODE=empty
reset_run
run_autumn
assert_actions ''
assert_tg_contains 'did not answer the state check'

export MOCK_SENSOR_MODE=malformed
reset_run
run_autumn
assert_actions ''
assert_tg_contains 'could not be parsed'

# 5: a single dry sensor must never water the whole tray.
export MOCK_SENSOR_MODE=one_dry
reset_run
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 5 expected exit 0, got ${rc}"
assert_actions ''
assert_tg_count 0
[[ -f "$tmp/state/last-watered" ]] && fail "case 5 must not record a watering"

# 6: an already wet tray is left alone and stays quiet.
export MOCK_SENSOR_MODE=all_wet
reset_run
run_autumn
assert_actions ''
assert_tg_count 0

# 7: frost risk blocks watering and reports itself.
export MOCK_SENSOR_MODE=valid
export MOCK_FORECAST_SERVICE_MODE=ok MOCK_FORECAST_MIN=1.4 MOCK_FORECAST_ATTR_MIN=1.4
reset_run
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 7 expected exit 0, got ${rc}"
assert_actions ''
assert_tg_count 1
assert_tg_contains 'frost risk'
[[ -f "$tmp/state/last-watered" ]] && fail "case 7 must not record a watering"

# 8: a low current temperature blocks even when the forecast attribute is the
# only source and the service fallback is available.
export MOCK_SENSOR_MODE=no_weather
export MOCK_FORECAST_SERVICE_MODE=ok MOCK_FORECAST_MIN=1.0
reset_run
run_autumn
assert_actions ''
assert_tg_contains 'frost risk'

# 9: unusable temperature data fails closed.
export MOCK_SENSOR_MODE=weather_badjson
export MOCK_FORECAST_SERVICE_MODE=empty
reset_run
run_autumn
assert_actions ''
assert_tg_contains 'no usable temperature forecast'

export MOCK_FORECAST_SERVICE_MODE=ok MOCK_FORECAST_MIN=4.0 MOCK_FORECAST_ATTR_MIN=6.0

# 10: an unexpected ON before this run owns the relay: confirmed OFF, no water,
# error message, abort.
export MOCK_SENSOR_MODE=valid
reset_run
printf 'on\n' >"$switch_state"
run_autumn
[[ "$rc" -ne 0 ]] || fail "case 10 must fail the run"
[[ "$(paste -sd, "$actions")" == 'off' ]] || fail "case 10 expected only an OFF, got '$(paste -sd, "$actions")'"
assert_tg_contains 'already reported ON'
[[ -f "$tmp/state/last-watered" ]] && fail "case 10 must not record a watering"

# 11: ON accepted by HTTP but never confirmed by switch state must not be
# retried and must leave the trap cleanup to request OFF.
export MOCK_SENSOR_MODE=valid MOCK_ON_APPLY=0 MOCK_OFF_APPLY=1
reset_run
run_autumn
[[ "$rc" -ne 0 ]] || fail "case 11 must fail the run"
assert_actions 'on,off'
assert_tg_contains 'pump ON was not state-confirmed'
[[ -f "$tmp/state/last-watered" ]] && fail "case 11 must not record a watering"
export MOCK_ON_APPLY=1

# 12: an unconfirmed OFF keeps the hazard flag set, retries OFF through the trap
# and still records the day, because water was already delivered.
export MOCK_OFF_APPLY=0
reset_run
run_autumn
[[ "$rc" -ne 0 ]] || fail "case 12 must fail the run"
assert_actions 'on,off,off,off,off,off,off'
assert_tg_contains 'pump OFF was not state-confirmed'
[[ -f "$tmp/state/last-watered" ]] || fail "case 12 must record the day after a confirmed ON"
export MOCK_OFF_APPLY=1

# 13: at most one cycle per calendar day, whatever the schedule does.
export MOCK_SENSOR_MODE=valid
reset_run
run_autumn
assert_actions 'on,off'
printf '%s\n' "$(TZ=Europe/Berlin date '+%Y-%m-%d')" >"$tmp/state/last-watered"
: >"$actions"
: >"$tg"
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 13 expected exit 0, got ${rc}"
assert_actions ''
assert_tg_count 0

# 14: duration is bounded by the device hard limit and reported accurately.
reset_run
export BALCONY_AUTUMN_DURATION_SECONDS=60
run_autumn
assert_actions 'on,off'
assert_tg_contains 'done: 60s'
export BALCONY_AUTUMN_DURATION_SECONDS=181
reset_run
run_autumn
[[ "$rc" -eq 2 ]] || fail "case 14 must reject a cycle above the ESP32 hard limit, got ${rc}"
assert_actions ''
export BALCONY_AUTUMN_DURATION_SECONDS=45

# 15: dry-run exercises every gate without touching the pump, Telegram or state.
reset_run
export BALCONY_AUTUMN_DRY_RUN=1
run_autumn
[[ "$rc" -eq 0 ]] || fail "case 15 expected exit 0, got ${rc}"
assert_actions ''
assert_tg_count 0
[[ -f "$tmp/state/last-watered" ]] && fail "case 15 must not record a watering"
grep -q 'DRY-RUN: gates passed' "$logfile" || fail "case 15 must log the dry-run decision"
unset BALCONY_AUTUMN_DRY_RUN

# 16: calibration readback compares before/after and stays out of Telegram by
# default, while BALCONY_AUTUMN_CALIBRATION=1 adds one explicit message.
reset_run
export BALCONY_AUTUMN_SOAK_SECONDS=300
run_autumn
assert_tg_count 1
grep -q 'calibration: dry 3 -> ' "$logfile" || fail "case 16 must log the calibration readback"

reset_run
export BALCONY_AUTUMN_CALIBRATION=1
run_autumn
assert_tg_count 2
assert_tg_contains 'Calibration:'
unset BALCONY_AUTUMN_CALIBRATION
export BALCONY_AUTUMN_SOAK_SECONDS=0

# 17: overlapping runs are refused by the lock.
reset_run
exec 201>"$tmp/autumn.lock"
flock -n 201 || fail "case 17 could not take the test lock"
run_autumn
[[ "$rc" -ne 0 ]] || fail "case 17 expected a refusal, got ${rc}"
assert_actions ''
assert_tg_count 0
exec 201>&-

printf 'Balcony autumn watering regression: PASS (quorum gate, frost gate, once-per-day, fail-closed sensors, message policy)\n'
