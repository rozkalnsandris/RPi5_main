#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-maintenance-health.sh
source "$repo/ops/lib/rpi5-maintenance-health.sh"

bash -n "$repo/ops/lib/rpi5-maintenance-health.sh"

rpi5_container_state_is_healthy running none
rpi5_container_state_is_healthy running healthy
! rpi5_container_state_is_healthy running starting
! rpi5_container_state_is_healthy exited none
printf '%s\n' 'PASS container-state-policy'

rows=$'api\trunning\thealthy\nweb\trunning\tnone'
rpi5_validate_container_rows "$rows"
printf '%s\n' 'PASS all-containers-healthy'

rows=$'api\trunning\thealthy\nweb\texited\tnone'
rc=0
rpi5_validate_container_rows "$rows" || rc=$?
[[ "$rc" -eq 1 ]]
[[ "$RPI5_BAD_CONTAINERS" == *$'web\texited\tnone'* ]]
printf '%s\n' 'PASS unhealthy-container-reported'

rc=0
rpi5_validate_container_rows "" || rc=$?
[[ "$rc" -eq 2 ]]
printf '%s\n' 'PASS zero-containers-fail'

required=$'api\nweb'
rows=$'api\trunning\thealthy\nweb\trunning\tnone\nretired\texited\tnone'
rpi5_validate_required_container_inventory "$required" "$rows"
printf '%s\n' 'PASS extra-retired-container-ignored'

required=$'api\nmissing-service'
rc=0
rpi5_validate_required_container_inventory "$required" "$rows" || rc=$?
[[ "$rc" -eq 1 ]]
[[ "$RPI5_BAD_CONTAINERS" == *$'missing-service\tmissing\tmissing'* ]]
printf '%s\n' 'PASS required-missing-container-fails'

for code in 200 204 302 401 403; do
    rpi5_http_code_is_reachable "$code"
done
for code in 000 404 500; do
    ! rpi5_http_code_is_reachable "$code"
done
printf '%s\n' 'PASS HTTP-reachability-policy'

printf '%s\n' 'Maintenance health helper tests: PASS'
