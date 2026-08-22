#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
operator="$repo/scripts/activate-tmp-headroom-monitor.sh"

[[ -f "$operator" && -x "$operator" && ! -L "$operator" ]]
bash -n "$operator"

grep -Fxq "readonly REPOSITORY='rozkalnsandris/RPi5_main'" "$operator"
grep -Fxq "readonly WORKFLOW='validate.yml'" "$operator"
grep -Fxq "readonly CHECKER_BLOB='e342b3eabdcabb87d1201c7568458fd2bb76cfe6'" "$operator"
grep -Fxq "readonly SERVICE_BLOB='deec01cca3f0599b58fd421bb3b5d7b4bfa1aec7'" "$operator"
grep -Fxq "readonly TIMER_BLOB='6898909484485f3db7fd6967c687b192319b6e28'" "$operator"

grep -Fq 'row.get("event") == "push"' "$operator"
grep -Fq 'row.get("head_branch") == "main"' "$operator"
grep -Fq 'row.get("head_sha") == sha' "$operator"
grep -Fq '"public-automation-baseline / public automation policy"' "$operator"
grep -Fq 'local checkout is not exact current GitHub main' "$operator"
grep -Fq 'executed operator bytes do not match current main' "$operator"

grep -Fq "readonly EXPECTED_TMP_MOUNT_FRAGMENT='/run/systemd/generator/tmp.mount'" "$operator"
grep -Fq "unexpected systemd major version" "$operator"
grep -Fq 'activation baseline is not absent' "$operator"
grep -Fq 'PRE_ACTIVATION_TMP_POLICY=PASS' "$operator"
grep -Fq 'PRE_ACTIVATION_BASELINE=ABSENT_INACTIVE' "$operator"

grep -Fq 'install -o root -g root -m 0755 "$repo/$CHECKER_REL" "$CHECKER_DEST"' "$operator"
grep -Fq 'install -o root -g root -m 0644 "$repo/$SERVICE_REL" "$SERVICE_DEST"' "$operator"
grep -Fq 'install -o root -g root -m 0644 "$repo/$TIMER_REL" "$TIMER_DEST"' "$operator"
grep -Fq 'systemd-analyze verify "$SERVICE_DEST" "$TIMER_DEST"' "$operator"
grep -Fq 'systemctl start "$SERVICE_UNIT"' "$operator"
grep -Fq 'systemctl enable --now "$TIMER_UNIT"' "$operator"

grep -Fq 'systemctl disable --now "$TIMER_UNIT"' "$operator"
grep -Fq 'systemctl stop "$SERVICE_UNIT"' "$operator"
grep -Fq 'rm -f -- "$TIMER_DEST" "$SERVICE_DEST" "$CHECKER_DEST"' "$operator"
grep -Fq 'systemctl reset-failed "$SERVICE_UNIT" "$TIMER_UNIT"' "$operator"
grep -Fq 'TMP_MONITOR_ACTIVATION_ROLLBACK=PASS' "$operator"

pre_line="$(grep -nF 'PRE_ACTIVATION_BASELINE=ABSENT_INACTIVE' "$operator" | cut -d: -f1)"
mutation_line="$(grep -nF 'mutation_started=true' "$operator" | tail -n1 | cut -d: -f1)"
first_install_line="$(grep -nF 'install -o root -g root -m 0755' "$operator" | cut -d: -f1)"
[[ "$pre_line" -lt "$mutation_line" && "$mutation_line" -lt "$first_install_line" ]]

! grep -Eq '(^|[[:space:]])(mount|umount|docker|apt|apt-get|reboot|shutdown|poweroff)([[:space:]]|$)' "$operator"
! grep -Fq '/etc/fstab' "$operator"
! grep -Eq 'git[[:space:]]+(fetch|merge|reset|rebase|clean)([[:space:]]|$)' "$operator"
! grep -Eq 'rm[[:space:]]+-[^[:space:]]*r' "$operator"
! grep -Eq 'systemctl[[:space:]]+(restart|reload)([[:space:]]|$)' "$operator"

printf '%s\n' 'RPi5 /tmp headroom activation source contract: PASS'
