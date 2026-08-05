#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo"

paths=(
  ops/bin/rpi5-backup
  ops/backup/rpi5-backup.conf.example
  ops/cron.d/rpi5-backup
  ops/logrotate.d/rpi5-backup
)
expected_blobs=(
  059ac81b6af5aebb56ebd92a03407a5c28847954
  7981cdd33c1be2b548fde61d0d47a6fd5ece58b8
  8dde57f1a8bcc8561a9fb27df318a7d9d8367f70
  7d1490e4c6f525f80e14490e7946da95ea0bbd1f
)
expected_modes=(100755 100644 100644 100644)

for index in "${!paths[@]}"; do
  path=${paths[$index]}
  [[ -f "$path" && ! -L "$path" ]] || {
    echo "V09: missing or unsafe tracked file: $path" >&2
    exit 1
  }
  actual_blob=$(git hash-object -- "$path")
  [[ "$actual_blob" == "${expected_blobs[$index]}" ]] || {
    echo "V09: source blob drift for $path: ${actual_blob}" >&2
    exit 1
  }
  actual_mode=$(git ls-files -s -- "$path" | awk 'NR==1 {print $1}')
  [[ "$actual_mode" == "${expected_modes[$index]}" ]] || {
    echo "V09: mode drift for $path: ${actual_mode}" >&2
    exit 1
  }
  actual_sha256=$(sha256sum -- "$path" | awk '{print $1}')
  printf 'V09_SHA256 %s %s\n' "$actual_sha256" "$path"
done

bash -n ops/bin/rpi5-backup

grep -Fqx '# RPi5 šifrētais backup katru nakti 02:00.' ops/cron.d/rpi5-backup
grep -Fqx '0 2 * * * root /usr/local/sbin/rpi5-backup' ops/cron.d/rpi5-backup
[[ $(grep -Ec '^[0-9*]' ops/cron.d/rpi5-backup) -eq 1 ]]

grep -Fqx '    daily' ops/logrotate.d/rpi5-backup
grep -Fqx '    rotate 14' ops/logrotate.d/rpi5-backup
grep -Fqx '    compress' ops/logrotate.d/rpi5-backup
grep -Fqx '    delaycompress' ops/logrotate.d/rpi5-backup
grep -Fqx '    create 0600 root root' ops/logrotate.d/rpi5-backup

grep -Fqx 'LOCAL_KEEP_DAYS=7' ops/backup/rpi5-backup.conf.example
grep -Fqx 'REMOTE_KEEP_DAYS=30' ops/backup/rpi5-backup.conf.example
grep -Fqx 'AGE_KEY="/etc/rpi5-backup/age.key"' ops/backup/rpi5-backup.conf.example
grep -Fqx 'AGE_RECIPIENT_FILE="/etc/rpi5-backup/age-recipient.txt"' ops/backup/rpi5-backup.conf.example

backup=ops/bin/rpi5-backup
grep -Fq 'backup_version=12' "$backup"
grep -Fq "age -r \"\$RECIPIENT\" -o \"\$TMP_ARCHIVE\"" "$backup"
grep -Fq "age -d -i \"\$AGE_KEY\" \"\$TMP_ARCHIVE\" | tar -tzf -" "$backup"
grep -Fq 'rclone copyto "$BACKUP_FILE" "$REMOTE_FILE"' "$backup"
grep -Fq 'rclone delete "$REMOTE_DIR"' "$backup"
grep -Fq -- '-mtime +"$LOCAL_KEEP_DAYS"' "$backup"
grep -Fq -- '--min-age "${REMOTE_KEEP_DAYS}d"' "$backup"
grep -Fq 'source.backup(target, pages=256, sleep=0.05)' "$backup"
grep -Fq 'PRAGMA quick_check' "$backup"

printf '%s\n' 'V09 backup ownership import tests: PASS'
