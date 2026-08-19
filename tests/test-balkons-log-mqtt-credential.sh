#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
wrapper="$repo/ops/bin/balkons-log-subscribe"
unit="$repo/ops/systemd/balkons-log.service"
contract="$repo/docs/BALKONS_LOG_MQTT_AUTH_CONTRACT.md"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() {
    echo "balkons-log credential regression: FAIL: $*" >&2
    exit 1
}

write_test_credential() {
    mkdir -p "$tmp/creds"
    printf '%s\n' '-u <test-user>' '-P TEST_ONLY_SENTINEL_173' >"$tmp/creds/mqtt-client-config"
    chmod 600 "$tmp/creds/mqtt-client-config"
}

bash -n "$wrapper"
write_test_credential

cat >"$tmp/docker" <<'MOCK'
#!/usr/bin/env bash
set -Eeuo pipefail

# Lifecycle cleanup delivers a shell helper to docker exec over stdin. Model
# the real Docker contract: the cleanup branch is accepted only with -i.
if [[ "${1:-}" == "exec" && "${2:-}" == "-i" && "${3:-}" == "mosquitto" && "${4:-}" == "sh" ]]; then
    printf '%s\n' "$@" >"${CAPTURE_CLEANUP_ARGS:?}"
    cat >/dev/null
    printf 'cleanup\n' >>"${CAPTURE_CLEANUP:?}"
    exit 0
fi

printf '%s\n' "$@" >"${CAPTURE_ARGS:?}"
cat >"${CAPTURE_STDIN:?}"
MOCK
chmod +x "$tmp/docker"

CAPTURE_ARGS="$tmp/argv" \
CAPTURE_STDIN="$tmp/stdin" \
CAPTURE_CLEANUP="$tmp/cleanup" \
CAPTURE_CLEANUP_ARGS="$tmp/cleanup-argv" \
CREDENTIALS_DIRECTORY="$tmp/creds" \
BALKONS_LOG_DOCKER_BIN="$tmp/docker" \
BALKONS_LOG_MQTT_CONTAINER="mosquitto" \
BALKONS_LOG_MQTT_HOST="broker.invalid" \
BALKONS_LOG_MQTT_TOPIC="balkons/log" \
BALKONS_LOG_MQTT_FORMAT="%I %t %p" \
"$wrapper"

cmp -s "$tmp/creds/mqtt-client-config" "$tmp/stdin" || fail "credential config was not forwarded only through stdin"

grep -Fxq -- 'exec' "$tmp/argv" || fail "docker exec verb missing"
grep -Fxq -- '-i' "$tmp/argv" || fail "docker stdin attachment missing"
grep -Fxq -- 'mosquitto' "$tmp/argv" || fail "container target missing"
grep -Fxq -- 'mosquitto_sub' "$tmp/argv" || fail "subscriber command missing"
grep -Fxq -- '-o' "$tmp/argv" || fail "Mosquitto config option missing"
grep -Fxq -- '/dev/stdin' "$tmp/argv" || fail "Mosquitto config is not sourced from stdin"
grep -Fxq -- 'broker.invalid' "$tmp/argv" || fail "non-secret host option missing"
grep -Fxq -- 'balkons/log' "$tmp/argv" || fail "topic option missing"
grep -Fxq -- '%I %t %p' "$tmp/argv" || fail "format option missing"
grep -Fxq -- 'balkons-log-service' "$tmp/argv" || fail "managed non-secret client id missing"
[[ "$(grep -c '^cleanup$' "$tmp/cleanup")" -eq 1 ]] || fail "pre-start lifecycle cleanup was not invoked exactly once"
grep -Fxq -- 'exec' "$tmp/cleanup-argv" || fail "cleanup docker exec verb missing"
grep -Fxq -- '-i' "$tmp/cleanup-argv" || fail "cleanup helper stdin is not attached"
grep -Fxq -- 'mosquitto' "$tmp/cleanup-argv" || fail "cleanup container target missing"
grep -Fxq -- 'sh' "$tmp/cleanup-argv" || fail "cleanup shell missing"
grep -Fxq -- '-s' "$tmp/cleanup-argv" || fail "cleanup shell stdin mode missing"

if grep -Fq -- 'TEST_ONLY_SENTINEL_173' "$tmp/argv"; then
    fail "credential value leaked into docker argv"
fi
if grep -Fxq -- '-P' "$tmp/argv" || grep -Fxq -- '--pw' "$tmp/argv"; then
    fail "password flag leaked into docker argv"
fi
if grep -Fxq -- '-u' "$tmp/argv" || grep -Fxq -- '--username' "$tmp/argv"; then
    fail "username flag leaked into docker argv"
fi

CAPTURE_ARGS="$tmp/stop-argv" \
CAPTURE_STDIN="$tmp/stop-stdin" \
CAPTURE_CLEANUP="$tmp/cleanup" \
CAPTURE_CLEANUP_ARGS="$tmp/stop-cleanup-argv" \
BALKONS_LOG_DOCKER_BIN="$tmp/docker" \
BALKONS_LOG_MQTT_CONTAINER="mosquitto" \
BALKONS_LOG_MQTT_HOST="broker.invalid" \
BALKONS_LOG_MQTT_TOPIC="balkons/log" \
BALKONS_LOG_MQTT_FORMAT="%I %t %p" \
"$wrapper" --stop

[[ "$(grep -c '^cleanup$' "$tmp/cleanup")" -eq 2 ]] || fail "explicit lifecycle stop cleanup was not invoked"
[[ ! -e "$tmp/stop-argv" ]] || fail "stop mode launched a subscriber command"
grep -Fxq -- '-i' "$tmp/stop-cleanup-argv" || fail "stop cleanup helper stdin is not attached"

if grep -Eq '(^|[[:space:]])(-P|--pw|--password)([[:space:]]|$)' "$unit"; then
    fail "tracked unit contains a password argv option"
fi
if grep -Eq 'BALKONS_LOG_MQTT_(USER(NAME)?|PASSWORD|PW)=' "$unit"; then
    fail "tracked unit places authentication in environment"
fi

grep -Fq 'EnvironmentFile=/etc/default/balkons-log' "$unit" || fail "non-secret runtime config boundary missing"
grep -Fq 'LoadCredential=mqtt-client-config:' "$unit" || fail "systemd credential boundary missing"
grep -Fq 'ExecStart=/usr/local/sbin/balkons-log-subscribe' "$unit" || fail "unit does not use the reviewed wrapper"
grep -Fq 'ExecStop=/usr/local/sbin/balkons-log-subscribe --stop' "$unit" || fail "unit does not retire its managed container subscriber"
grep -Fxq 'TimeoutStopSec=15s' "$unit" || fail "bounded lifecycle stop timeout missing"

# The tracked journal directives are a safe source fallback, not permission to
# overwrite a pre-existing private production append sink. The public contract
# must require a runtime-only local drop-in that preserves the captured target.
grep -Fq 'Safe source fallback only.' "$unit" || fail "tracked unit does not label journal output as fallback-only"
grep -Fxq 'StandardOutput=journal' "$unit" || fail "tracked unit stdout fallback changed"
grep -Fxq 'StandardError=journal' "$unit" || fail "tracked unit stderr fallback changed"
grep -Fq 'runtime-only local systemd drop-in' "$contract" || fail "runtime output-preservation drop-in contract missing"
grep -Fq 'StandardOutput=append:<captured-private-runtime-path>' "$contract" || fail "stdout append-preservation placeholder missing"
grep -Fq 'StandardError=append:<captured-private-runtime-path>' "$contract" || fail "stderr append-preservation placeholder missing"
grep -Fq 'FD 1 and FD 2' "$contract" || fail "running output-FD verification contract missing"
grep -Fq 'must never be copied to Git' "$contract" || fail "private output-path publication boundary missing"
grep -Fq 'container-side subscriber lifecycle' "$contract" || fail "container subscriber lifecycle contract missing"
grep -Fq 'captured legacy subscriber PID' "$contract" || fail "one-time legacy subscriber retirement contract missing"

if grep -Eq 'Standard(Output|Error)=append:/[^<[:space:]]+' "$unit" "$contract"; then
    fail "public source contains a literal private append destination"
fi

rm -f "$tmp/creds/mqtt-client-config"
if CAPTURE_ARGS="$tmp/missing-argv" \
   CAPTURE_STDIN="$tmp/missing-stdin" \
   CAPTURE_CLEANUP="$tmp/missing-cleanup" \
   CAPTURE_CLEANUP_ARGS="$tmp/missing-cleanup-argv" \
   CREDENTIALS_DIRECTORY="$tmp/creds" \
   BALKONS_LOG_DOCKER_BIN="$tmp/docker" \
   BALKONS_LOG_MQTT_HOST="broker.invalid" \
   BALKONS_LOG_MQTT_TOPIC="balkons/log" \
   BALKONS_LOG_MQTT_FORMAT="%I %t %p" \
   "$wrapper" >/dev/null 2>&1; then
    fail "wrapper did not fail closed when credential was missing"
fi

write_test_credential
if CAPTURE_ARGS="$tmp/nohost-argv" \
   CAPTURE_STDIN="$tmp/nohost-stdin" \
   CAPTURE_CLEANUP="$tmp/nohost-cleanup" \
   CAPTURE_CLEANUP_ARGS="$tmp/nohost-cleanup-argv" \
   CREDENTIALS_DIRECTORY="$tmp/creds" \
   BALKONS_LOG_DOCKER_BIN="$tmp/docker" \
   BALKONS_LOG_MQTT_TOPIC="balkons/log" \
   BALKONS_LOG_MQTT_FORMAT="%I %t %p" \
   "$wrapper" >/dev/null 2>&1; then
    fail "wrapper did not fail closed when non-secret host config was missing"
fi

rm -f "$tmp/creds/mqtt-client-config"
printf '%s\n' '-u <test-user>' '-P TEST_ONLY_SENTINEL_173' >"$tmp/real-config"
ln -s "$tmp/real-config" "$tmp/creds/mqtt-client-config"
if CAPTURE_ARGS="$tmp/symlink-argv" \
   CAPTURE_STDIN="$tmp/symlink-stdin" \
   CAPTURE_CLEANUP="$tmp/symlink-cleanup" \
   CAPTURE_CLEANUP_ARGS="$tmp/symlink-cleanup-argv" \
   CREDENTIALS_DIRECTORY="$tmp/creds" \
   BALKONS_LOG_DOCKER_BIN="$tmp/docker" \
   BALKONS_LOG_MQTT_HOST="broker.invalid" \
   BALKONS_LOG_MQTT_TOPIC="balkons/log" \
   BALKONS_LOG_MQTT_FORMAT="%I %t %p" \
   "$wrapper" >/dev/null 2>&1; then
    fail "wrapper accepted a symlink credential"
fi

echo "balkons-log credential regression: PASS"
