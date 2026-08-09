#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
unit_dir="$repo/ops/systemd"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
root="$tmp/root"

units=(
    rpi5-update.service
    rpi5-update.timer
    rpi5-monitor.service
    rpi5-monitor.timer
    rpi5-post-reboot.service
    rpi5-maintenance-notify@.service
)
for unit in "${units[@]}"; do
    [[ -f "$unit_dir/$unit" && ! -L "$unit_dir/$unit" ]]
done

# Schedule semantics are checked by systemd itself.
systemd-analyze calendar 'Sun *-*-* 02:20:00' >/dev/null
systemd-analyze calendar '*-*-* 09:00:00' >/dev/null

grep -Fxq 'OnCalendar=Sun *-*-* 02:20:00' "$unit_dir/rpi5-update.timer"
grep -Fxq 'Persistent=true' "$unit_dir/rpi5-update.timer"
grep -Fxq 'AccuracySec=1s' "$unit_dir/rpi5-update.timer"
grep -Fxq 'RandomizedDelaySec=0' "$unit_dir/rpi5-update.timer"

grep -Fxq 'OnCalendar=*-*-* 09:00:00' "$unit_dir/rpi5-monitor.timer"
grep -Fxq 'Persistent=false' "$unit_dir/rpi5-monitor.timer"
grep -Fxq 'AccuracySec=1s' "$unit_dir/rpi5-monitor.timer"
grep -Fxq 'RandomizedDelaySec=0' "$unit_dir/rpi5-monitor.timer"

grep -Fxq 'Type=oneshot' "$unit_dir/rpi5-update.service"
grep -Fxq 'TimeoutStartSec=2h' "$unit_dir/rpi5-update.service"
grep -Fxq 'OnFailure=rpi5-maintenance-notify@%N.service' "$unit_dir/rpi5-update.service"

grep -Fxq 'Type=oneshot' "$unit_dir/rpi5-monitor.service"
grep -Fxq 'TimeoutStartSec=5min' "$unit_dir/rpi5-monitor.service"
grep -Fxq 'OnFailure=rpi5-maintenance-notify@%N.service' "$unit_dir/rpi5-monitor.service"

grep -Fxq 'Type=oneshot' "$unit_dir/rpi5-post-reboot.service"
grep -Fxq 'TimeoutStartSec=7min' "$unit_dir/rpi5-post-reboot.service"
grep -Fxq 'OnSuccess=rpi5-maintenance-notify@%N.service' "$unit_dir/rpi5-post-reboot.service"
grep -Fxq 'OnFailure=rpi5-maintenance-notify@%N.service' "$unit_dir/rpi5-post-reboot.service"

grep -Fxq 'DynamicUser=yes' "$unit_dir/rpi5-maintenance-notify@.service"
grep -Fxq 'LoadCredential=telegram-token:/etc/credstore/rpi5-maintenance-telegram-token' "$unit_dir/rpi5-maintenance-notify@.service"
grep -Fxq 'LoadCredential=telegram-chat-id:/etc/credstore/rpi5-maintenance-telegram-chat-id' "$unit_dir/rpi5-maintenance-notify@.service"
grep -Fxq 'ProtectSystem=strict' "$unit_dir/rpi5-maintenance-notify@.service"
grep -Fxq 'CapabilityBoundingSet=' "$unit_dir/rpi5-maintenance-notify@.service"

# Verify directives with systemd-analyze in an isolated root containing dummy
# executable/dependency targets, so CI never needs to modify the runner host.
mkdir -p "$root/etc/systemd/system" "$root/usr/local/sbin" "$root/etc/credstore"
cp -- "$unit_dir"/* "$root/etc/systemd/system/"
for executable in rpi5-update rpi5-monitor rpi5-post-reboot rpi5-maintenance-notify; do
    printf '#!/bin/sh\nexit 0\n' >"$root/usr/local/sbin/$executable"
    chmod 0755 "$root/usr/local/sbin/$executable"
done
printf 'synthetic\n' >"$root/etc/credstore/rpi5-maintenance-telegram-token"
printf 'synthetic\n' >"$root/etc/credstore/rpi5-maintenance-telegram-chat-id"

for target in network-online.target timers.target multi-user.target; do
    printf '[Unit]\nDescription=CI stub %s\n' "$target" >"$root/etc/systemd/system/$target"
done
for service in docker.service cloudflared.service ssh.service; do
    cat >"$root/etc/systemd/system/$service" <<EOF
[Unit]
Description=CI stub $service
[Service]
Type=oneshot
ExecStart=/bin/true
EOF
done

systemd-analyze verify \
    --root="$root" \
    --man=no \
    --recursive-errors=no \
    "$root/etc/systemd/system/rpi5-update.service" \
    "$root/etc/systemd/system/rpi5-update.timer" \
    "$root/etc/systemd/system/rpi5-monitor.service" \
    "$root/etc/systemd/system/rpi5-monitor.timer" \
    "$root/etc/systemd/system/rpi5-post-reboot.service" \
    "$root/etc/systemd/system/rpi5-maintenance-notify@.service"

printf '%s\n' 'Maintenance systemd unit/calendar tests: PASS'
