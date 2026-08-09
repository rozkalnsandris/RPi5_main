#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
monitor="$repo/ops/bin/rpi5-monitor"
post="$repo/ops/bin/rpi5-post-reboot"
lib="$repo/ops/lib/rpi5-maintenance-health.sh"

for f in "$monitor" "$post" "$lib"; do
    [[ -f "$f" && ! -L "$f" ]]
    bash -n "$f"
done

for f in "$monitor" "$post"; do
    grep -Fq 'must run as root' "$f"
    grep -Fq '/usr/local/lib/rpi5-maintenance' "$f"
    ! grep -Fq '/usr/local/libexec/rpi5-maintenance' "$f"
    grep -Fq '/etc/rpi5-maintenance/required-containers' "$f"
    grep -Fq 'rpi5_validate_required_container_inventory' "$f"
    grep -Fq "docker ps -a --format '{{.Names}}\\t{{.State}}\\t{{.HealthStatus}}'" "$f"
    if grep -Eq '/home/[A-Za-z0-9._-]+/|192\.168\.|10\.[0-9]|172\.(1[6-9]|2[0-9]|3[01])\.' "$f"; then
        echo "private runtime literal found in $f" >&2
        exit 1
    fi
    if grep -Eq 'TELEGRAM_(TOKEN|CHAT_ID)|/etc/rpi-update\.conf|/var/log/rpi5-(monitor|post-reboot)' "$f"; then
        echo "health entrypoint crosses secret/file-log boundary: $f" >&2
        exit 1
    fi
done

grep -Fq 'http://127.0.0.1:8088/' "$monitor"
grep -Fq 'http://127.0.0.1:8089/' "$monitor"
grep -Fq 'http://127.0.0.1:8088/' "$post"
grep -Fq 'http://127.0.0.1:8089/' "$post"

! grep -Fq 'cron.service' "$monitor"
! grep -Fq 'cron.service' "$post"
! grep -Eq 'pgrep|backup\.sh|update\.sh' "$monitor"
! grep -Eq 'pgrep|backup\.sh|update\.sh' "$post"

printf '%s\n' 'Maintenance health entrypoint contract: PASS'
