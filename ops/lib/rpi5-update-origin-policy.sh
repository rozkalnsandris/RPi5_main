#!/usr/bin/env bash
# Application-origin health policy owned by the weekly RPi5 updater.
# These two public application origins are intentionally exposed only on
# host loopback for consumption by the host-owned Cloudflare connector.

readonly RPI5_CV_LOCAL_HEALTH_URL="http://127.0.0.1:8088/"
readonly RPI5_HERMES_TECH_LOCAL_HEALTH_URL="http://127.0.0.1:8089/"

rpi5_application_local_health_targets() {
    printf '%s\t%s\n' "CV" "$RPI5_CV_LOCAL_HEALTH_URL"
    printf '%s\t%s\n' "Hermes Tech" "$RPI5_HERMES_TECH_LOCAL_HEALTH_URL"
}
