#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
wrapper="$repo/ops/bin/rpi5-maintenance-notify"
unit="$repo/ops/systemd/rpi5-maintenance-notify@.service"
cutover="$repo/ops/bin/rpi5-maintenance-systemd-cutover"

[[ -f "$wrapper" && ! -L "$wrapper" ]]
[[ -f "$unit" && ! -L "$unit" ]]
[[ -f "$cutover" && ! -L "$cutover" ]]
bash -n "$wrapper"

grep -Fq 'MONITOR_UNIT' "$wrapper"
grep -Fq 'MONITOR_SERVICE_RESULT' "$wrapper"
grep -Fq 'MONITOR_EXIT_CODE' "$wrapper"
grep -Fq 'MONITOR_EXIT_STATUS' "$wrapper"
grep -Fq 'MONITOR_INVOCATION_ID' "$wrapper"
grep -Fq '/usr/local/lib/rpi5-maintenance/rpi5-maintenance-telegram.py' "$wrapper"
! grep -Fq '/usr/local/libexec/rpi5-maintenance' "$wrapper"

if grep -Eq 'TELEGRAM_(TOKEN|CHAT_ID)|/etc/rpi-update\.conf|/home/[A-Za-z0-9._-]+/' "$wrapper"; then
    echo 'notification wrapper crosses secret/private runtime boundary' >&2
    exit 1
fi

# Credentials belong only to the isolated notifier unit; health/update units
# must not receive LoadCredential or a credentials directory.
for other in \
    "$repo/ops/systemd/rpi5-update.service" \
    "$repo/ops/systemd/rpi5-monitor.service" \
    "$repo/ops/systemd/rpi5-post-reboot.service"; do
    ! grep -Fq 'LoadCredential=' "$other"
    ! grep -Fq 'CREDENTIALS_DIRECTORY' "$other"
done

grep -Fq 'DynamicUser=yes' "$unit"
grep -Fq 'NoNewPrivileges=yes' "$unit"
grep -Fq 'ProtectSystem=strict' "$unit"
grep -Fq 'ProtectHome=yes' "$unit"
grep -Fq 'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' "$unit"
grep -Fq 'CapabilityBoundingSet=' "$unit"
grep -Fq 'AmbientCapabilities=' "$unit"

# DynamicUser cannot execute a root:root 0750 entrypoint. Keep the public
# notifier wrapper root-owned/non-writable but executable by the transient UID.
grep -Fq 'install -o root -g root -m 0755 "$repo/ops/bin/rpi5-maintenance-notify" /usr/local/sbin/rpi5-maintenance-notify' "$cutover"
! grep -Fq 'install -o root -g root -m 0750 "$repo/ops/bin/rpi5-maintenance-notify" /usr/local/sbin/rpi5-maintenance-notify' "$cutover"

printf '%s\n' 'Maintenance systemd notification boundary tests: PASS'
