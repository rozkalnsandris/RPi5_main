#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
checker="$repo/ops/bin/rpi5-tmp-headroom"
service="$repo/ops/systemd/rpi5-tmp-headroom.service"
timer="$repo/ops/systemd/rpi5-tmp-headroom.timer"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
root="$tmp/root"

[[ -x "$checker" && ! -L "$checker" ]]
[[ -f "$service" && ! -L "$service" ]]
[[ -f "$timer" && ! -L "$timer" ]]

# shellcheck source=../ops/bin/rpi5-tmp-headroom
source "$checker"

rpi5_tmp_headroom_classify \
    2123235328 1916403712 10 1777 tmpfs 'rw,nosuid,nodev'
[[ "$RPI5_TMP_HEADROOM_REASON" == 'PASS' ]]

expect_reason() {
    local expected="$1"
    shift
    local rc=0
    rpi5_tmp_headroom_classify "$@" || rc=$?
    [[ "$rc" -ne 0 ]]
    [[ "$RPI5_TMP_HEADROOM_REASON" == "$expected" ]]
}

expect_reason TMP_METRICS_INVALID bad 1916403712 10 1777 tmpfs 'rw,nosuid,nodev'
expect_reason TMP_NOT_TMPFS 2123235328 1916403712 10 1777 ext4 'rw,nosuid,nodev'
expect_reason TMP_SIZE_BELOW_1G 268435456 134217728 50 1777 tmpfs 'rw,nosuid,nodev'
expect_reason TMP_MODE_NOT_1777 2123235328 1916403712 10 0755 tmpfs 'rw,nosuid,nodev'
expect_reason TMP_NOT_RW 2123235328 1916403712 10 1777 tmpfs 'ro,nosuid,nodev'
expect_reason TMP_NOSUID_MISSING 2123235328 1916403712 10 1777 tmpfs 'rw,nodev'
expect_reason TMP_NODEV_MISSING 2123235328 1916403712 10 1777 tmpfs 'rw,nosuid'
expect_reason TMP_NOEXEC_SET 2123235328 1916403712 10 1777 tmpfs 'rw,nosuid,nodev,noexec'
expect_reason TMP_NOATIME_SET 2123235328 1916403712 10 1777 tmpfs 'rw,nosuid,nodev,noatime'
expect_reason TMP_RELATIME_SET 2123235328 1916403712 10 1777 tmpfs 'rw,nosuid,nodev,relatime'
expect_reason TMP_HEADROOM_BELOW_256M 2123235328 268435455 84 1777 tmpfs 'rw,nosuid,nodev'
expect_reason TMP_USAGE_AT_OR_ABOVE_85_PERCENT 2123235328 318485299 85 1777 tmpfs 'rw,nosuid,nodev'

# Source safety: this monitor must remain read-only and scoped to /tmp metadata.
! grep -Eq '(^|[;&|])[[:space:]]*(sudo|mount|umount|rm|systemctl|docker)([[:space:]]|$)' "$checker"
grep -Fq 'MIN_TMP_AVAILABLE_BYTES=$((256 * 1024 * 1024))' "$checker"
grep -Fq 'MAX_TMP_USED_PERCENT=85' "$checker"
grep -Fq 'findmnt -n -o FSTYPE --target /tmp' "$checker"
grep -Fq "df -B1 --output=size,avail,pcent /tmp" "$checker"

# Unit semantics: frequent lightweight check, existing notifier, and no PrivateTmp
# because a private namespace would hide the host /tmp that this service monitors.
grep -Fxq 'OnFailure=rpi5-maintenance-notify@%N.service' "$service"
grep -Fxq 'ExecStart=/usr/local/sbin/rpi5-tmp-headroom' "$service"
grep -Fxq 'PrivateTmp=no' "$service"
grep -Fxq 'ProtectSystem=strict' "$service"
grep -Fxq 'CapabilityBoundingSet=' "$service"
grep -Fxq 'OnBootSec=5min' "$timer"
grep -Fxq 'OnUnitActiveSec=15min' "$timer"
grep -Fxq 'AccuracySec=1min' "$timer"
grep -Fxq 'RandomizedDelaySec=0' "$timer"

mkdir -p "$root/etc/systemd/system" "$root/usr/local/sbin"
cp -- "$service" "$timer" "$root/etc/systemd/system/"
printf '#!/bin/sh\nexit 0\n' >"$root/usr/local/sbin/rpi5-tmp-headroom"
chmod 0755 "$root/usr/local/sbin/rpi5-tmp-headroom"
cat >"$root/etc/systemd/system/rpi5-maintenance-notify@.service" <<'UNIT'
[Unit]
Description=CI notification stub for %i
[Service]
Type=oneshot
ExecStart=/bin/true
UNIT
cat >"$root/etc/systemd/system/timers.target" <<'UNIT'
[Unit]
Description=CI timers target stub
UNIT

systemd-analyze verify \
    --root="$root" \
    --man=no \
    --recursive-errors=no \
    "$root/etc/systemd/system/rpi5-tmp-headroom.service" \
    "$root/etc/systemd/system/rpi5-tmp-headroom.timer"

printf '%s\n' 'RPi5 /tmp headroom monitor tests: PASS'
