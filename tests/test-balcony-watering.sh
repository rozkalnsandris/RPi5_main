#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
primary="$repo/ops/bin/balcony-watering-2x"
heat_gate="$repo/ops/bin/balcony-watering-heat-gate"

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/bin"
actions="$tmp/actions.log"
logfile="$tmp/watering.log"
switch_state="$tmp/switch-state"

cat >"$tmp/bin/curl" <<'MOCK_CURL'
#!/usr/bin/env bash
set -Eeuo pipefail
url=""
for arg in "$@"; do
    case "$arg" in
        http://*|https://*) url="$arg" ;;
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
    */api/states/switch.balkona_laistisana_suknis)
        case "${MOCK_SWITCH_STATE_MODE:-valid}" in
            empty) exit 0 ;;
            malformed) printf '{bad-json' ;;
            valid)
                state="$(cat "${MOCK_SWITCH_STATE_FILE:?}")"
                printf '{"state":"%s"}' "$state"
                ;;
            *) echo "unknown MOCK_SWITCH_STATE_MODE" >&2; exit 96 ;;
        esac
        ;;
    */api/states/weather.forecast_home)
        case "${MOCK_WEATHER_MODE:-valid}" in
            empty) exit 0 ;;
            malformed) printf '{bad-json' ;;
            valid) printf '{"attributes":{"temperature":%s}}' "${MOCK_TEMP:-27.0}" ;;
            *) echo "unknown MOCK_WEATHER_MODE" >&2; exit 97 ;;
        esac
        ;;
    */api/states)
        case "${MOCK_SENSOR_MODE:-valid}" in
            empty) exit 0 ;;
            malformed) printf '{bad-json' ;;
            valid|missing|unavailable|unknown)
                python3 - "${MOCK_SENSOR_MODE:-valid}" <<'PY'
import json
import sys
mode = sys.argv[1]
states = []
for i in list(range(1, 5)) + list(range(6, 16)):
    if mode == "missing" and i == 10:
        continue
    state = "mitrs"
    if i == 10 and mode == "unavailable":
        state = "unavailable"
    elif i == 10 and mode == "unknown":
        state = "unknown"
    states.append({"entity_id": f"sensor.balkona_laistisana_puke_{i}", "state": state})
print(json.dumps(states))
PY
                ;;
            *) echo "unknown MOCK_SENSOR_MODE" >&2; exit 97 ;;
        esac
        ;;
    https://api.telegram.org/*)
        echo "Telegram must remain disabled in offline tests" >&2
        exit 98
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
export BALCONY_WATERING_DURATION_SECONDS=0
export BALCONY_WATERING_PAUSE_SECONDS=0
export BALCONY_WATERING_LOCKFILE="$tmp/watering.lock"
export BALCONY_WATERING_LOGFILE="$logfile"
export MOCK_ACTIONS="$actions"
export MOCK_SWITCH_STATE_FILE="$switch_state"
unset TELEGRAM_TOKEN CHAT_ID

fail() {
    echo "balcony watering regression: FAIL: $*" >&2
    exit 1
}

assert_actions() {
    local expected="$1"
    local actual=""
    [[ -f "$actions" ]] && actual="$(paste -sd, "$actions")"
    [[ "$actual" == "$expected" ]] || fail "expected actions '$expected', got '$actual'"
}

reset_run() {
    : >"$actions"
    : >"$logfile"
    printf 'off\n' >"$switch_state"
}

run_primary() {
    reset_run
    bash "$primary" >"$tmp/stdout" 2>"$tmp/stderr"
}

bash -n "$primary"
bash -n "$heat_gate"
[[ -x "$primary" ]] || fail "primary source must be executable"
[[ -x "$heat_gate" ]] || fail "heat-gate source must be executable"
! grep -q 'FRESH_LIMIT' "$primary" || fail "timestamp freshness limit must not return"

# 1-2: all 14 required sensors valid; flower 5 is absent and does not block.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=200
export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=valid
run_primary
assert_actions 'on,off,on,off'

# 3-7: every sensor uncertainty case skips before pump ON.
for mode in missing unavailable unknown empty malformed; do
    export MOCK_SENSOR_MODE="$mode" MOCK_ON_CODE=200 MOCK_OFF_CODE=200
    export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=valid
    run_primary
    assert_actions ''
done

# 8: source has no last_updated-based freshness decision.
if grep -Ev '^[[:space:]]*#' "$primary" | grep -q 'last_updated'; then
    fail "runtime code must not depend on last_updated"
fi

# 9: an OFF HTTP failure retries three times, then EXIT cleanup retries OFF
# three more times while the may-be-ON hazard flag remains set.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=500
export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=valid
reset_run
set +e
bash "$primary" >"$tmp/stdout" 2>"$tmp/stderr"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "persistent pump-OFF HTTP failure must fail the run"
assert_actions 'on,off,off,off,off,off,off'

# 10: HTTP 200 for ON is not enough. If the switch never reports ON, the
# duplicate-sensitive ON is not retried and the trap performs a confirmed OFF.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=200
export MOCK_ON_APPLY=0 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=valid
reset_run
set +e
bash "$primary" >"$tmp/stdout" 2>"$tmp/stderr"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "unconfirmed pump ON must fail the run"
assert_actions 'on,off'

# 11: HTTP 200 for OFF is not enough either. Repeated OFF is safe, so normal
# retries and the trap continue while the switch still reports ON.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=200
export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=0 MOCK_SWITCH_STATE_MODE=valid
reset_run
set +e
bash "$primary" >"$tmp/stdout" 2>"$tmp/stderr"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "unconfirmed pump OFF must fail the run"
assert_actions 'on,off,off,off,off,off,off'

# 12: malformed switch-state feedback after an accepted ON is uncertainty.
# The controller must fail and attempt only OFF cleanup, never a second ON.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=200
export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=malformed
reset_run
set +e
bash "$primary" >"$tmp/stdout" 2>"$tmp/stderr"
rc=$?
set -e
[[ "$rc" -ne 0 ]] || fail "malformed switch-state feedback must fail the run"
assert_actions 'on,off,off,off'

# 13: heat gate below threshold never delegates; at threshold it delegates to
# the primary controller, which still performs its own 14-sensor/state gates.
export MOCK_SENSOR_MODE=valid MOCK_ON_CODE=200 MOCK_OFF_CODE=200 MOCK_WEATHER_MODE=valid
export MOCK_ON_APPLY=1 MOCK_OFF_APPLY=1 MOCK_SWITCH_STATE_MODE=valid
export BALCONY_WATERING_PRIMARY="$primary"
export MOCK_TEMP=26.9
reset_run
bash "$heat_gate" >"$tmp/stdout" 2>"$tmp/stderr"
assert_actions ''

export MOCK_TEMP=27.0
reset_run
bash "$heat_gate" >"$tmp/stdout" 2>"$tmp/stderr"
assert_actions 'on,off,on,off'

# 14: all network-capable curl calls were forced through the local mock above.
printf 'Balcony watering regression: PASS (offline guard, state confirmation, cleanup, heat gate)\n'
