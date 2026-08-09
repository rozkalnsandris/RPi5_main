#!/usr/bin/env bash
# Reboot decision helpers for the weekly updater.

# Return success only when the supplied package list represents packages that
# were actually applied by a real updater run and includes a kernel/firmware
# package whose activation can require reboot. `--check` package lists come from
# APT simulation and must never be described as already updated.
rpi5_applied_packages_require_reboot() {
    local mode="${1:?missing updater mode}"
    local package_list="${2-}"

    [[ "$mode" == "run" ]] || return 1

    grep -Eq '(^| )(linux-image|raspberrypi-kernel|raspberrypi-bootloader|raspi-firmware|rpi-eeprom)([^ ]*)($| )' \
        <<<"$package_list"
}
