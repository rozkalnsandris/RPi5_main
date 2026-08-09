#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-origin-policy.sh
source "$repo/ops/lib/rpi5-update-origin-policy.sh"

[[ "$RPI5_CV_LOCAL_HEALTH_URL" == "http://127.0.0.1:8088/" ]]
[[ "$RPI5_HERMES_TECH_LOCAL_HEALTH_URL" == "http://127.0.0.1:8089/" ]]

case "$RPI5_CV_LOCAL_HEALTH_URL $RPI5_HERMES_TECH_LOCAL_HEALTH_URL" in
    *'${HOST_IPV4}'*|*'192.168.'*)
        echo "loopback application health policy regressed to LAN addressing" >&2
        exit 1
        ;;
esac

mapfile -t targets < <(rpi5_application_local_health_targets)
[[ "${#targets[@]}" -eq 2 ]]
[[ "${targets[0]}" == $'CV\thttp://127.0.0.1:8088/' ]]
[[ "${targets[1]}" == $'Hermes Tech\thttp://127.0.0.1:8089/' ]]

printf '%s\n' 'Maintenance updater loopback-origin policy tests: PASS'
