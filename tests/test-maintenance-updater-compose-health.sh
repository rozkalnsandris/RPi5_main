#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-compose-health.sh
source "$repo/ops/lib/rpi5-update-compose-health.sh"

expected=$'db\napi\nweb'
actual=$'db\napi\nweb'
rpi5_find_missing_compose_services "$expected" "$actual"
[[ -z "$RPI5_MISSING_COMPOSE_SERVICES" ]]
printf '%s\n' 'PASS complete-project'

actual=$'db\nweb'
if rpi5_find_missing_compose_services "$expected" "$actual"; then
    echo 'missing service was not detected' >&2
    exit 1
fi
[[ "$RPI5_MISSING_COMPOSE_SERVICES" == 'api' ]]
printf '%s\n' 'PASS one-missing-service'

actual=''
if rpi5_find_missing_compose_services "$expected" "$actual"; then
    echo 'empty runtime was not detected' >&2
    exit 1
fi
[[ "$RPI5_MISSING_COMPOSE_SERVICES" == $'db\napi\nweb' ]]
printf '%s\n' 'PASS all-services-missing'

actual=$'web\ndb\napi\napi'
rpi5_find_missing_compose_services "$expected" "$actual"
printf '%s\n' 'PASS runtime-order-and-duplicates-ignored'

printf '%s\n' 'Maintenance updater Compose completeness tests: PASS (4 cases)'
