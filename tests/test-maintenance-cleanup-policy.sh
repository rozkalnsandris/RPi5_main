#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck source=../ops/lib/rpi5-update-cleanup-policy.sh
source "$repo/ops/lib/rpi5-update-cleanup-policy.sh"

bash -n "$repo/ops/lib/rpi5-update-cleanup-policy.sh"

[[ "$(rpi5_cleanup_owned_path_kind /tmp/rpi5-update-20260809.ABC123)" == "tmp_directory" ]]
[[ "$(rpi5_cleanup_owned_path_kind /var/log/rpi5-update.log.1)" == "log_rotation" ]]
[[ "$(rpi5_cleanup_owned_path_kind /var/log/rpi5-update.log.20260809)" == "log_rotation" ]]
printf '%s\n' 'PASS owned-cleanup-paths'

for path in \
    /tmp/rpi5-update-foo/bar \
    /tmp/rpi5-repair.sh \
    /tmp/deploy_rpi5_fix.sh \
    /var/log/rpi5-monitor.log.1 \
    /var/log/rpi5-backup.log.1 \
    /usr/local/sbin/rpi5-update \
    /usr/local/lib/rpi5-maintenance/rpi5-update-cleanup-policy.sh \
    /etc/systemd/system/rpi5-update.service \
    /home/example/rpi5-old.log \
    /home/example/rpi5-backup-20260809; do
    if rpi5_cleanup_owned_path_kind "$path" >/dev/null 2>&1; then
        echo "unexpected cleanup ownership: $path" >&2
        exit 1
    fi
done
printf '%s\n' 'PASS unowned-control-and-recovery-paths-rejected'

printf '%s\n' 'Maintenance cleanup ownership policy tests: PASS'
