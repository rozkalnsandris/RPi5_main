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
expected_sha256=(
  5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735
  65e4d465fc13c05c4a19842a4c6a5f4c3410bd5ac0ede1bffe79c54d359b2a8c
  d9ef8658cb78ea85a3c7bb8e3853b03eab4c896399e58c35ef5b960df2a51697
  08e0b02be895592ffd1fd56ed6c5849cdc0e7b117c161e9382165ebcf05765e2
)
expected_modes=(100755 100644 100644 100644)

for index in "${!paths[@]}"; do
  path=${paths[$index]}
  [[ -f "$path" && ! -L "$path" ]] || {
    echo "V10: missing or unsafe tracked file: $path" >&2
    exit 1
  }
  actual_blob=$(git hash-object -- "$path")
  [[ "$actual_blob" == "${expected_blobs[$index]}" ]] || {
    echo "V10: source blob drift for $path: ${actual_blob}" >&2
    exit 1
  }
  actual_sha256=$(sha256sum -- "$path" | awk '{print $1}')
  [[ "$actual_sha256" == "${expected_sha256[$index]}" ]] || {
    echo "V10: SHA256 drift for $path: ${actual_sha256}" >&2
    exit 1
  }
  actual_mode=$(git ls-files -s -- "$path" | awk 'NR==1 {print $1}')
  [[ "$actual_mode" == "${expected_modes[$index]}" ]] || {
    echo "V10: mode drift for $path: ${actual_mode}" >&2
    exit 1
  }
  printf 'V10_SHA256 %s %s\n' "$actual_sha256" "$path"
done

python3 - <<'PY'
import json
from pathlib import Path

manifest_path = Path("ops/backup/source-provenance.json")
data = json.loads(manifest_path.read_text(encoding="utf-8"))
assert data["schema"] == "rpi5-backup-source-provenance-v1"
assert data["source_repository"] == "rozkalnsandris/hermes-tech"
assert data["source_commit"] == "194083f0d850c888d23f751aeb51e69a561a047a"
assert data["original_introduction_commit"] == "36b8223710fd2dbe90b6d69898ffc17c34285da1"
expected = [
    ("ops/bin/rpi5-backup", "/usr/local/sbin/rpi5-backup", "100755", "059ac81b6af5aebb56ebd92a03407a5c28847954", "5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735"),
    ("ops/backup/rpi5-backup.conf.example", "/etc/rpi5-backup.conf", "100644", "7981cdd33c1be2b548fde61d0d47a6fd5ece58b8", "65e4d465fc13c05c4a19842a4c6a5f4c3410bd5ac0ede1bffe79c54d359b2a8c"),
    ("ops/cron.d/rpi5-backup", "/etc/cron.d/rpi5-backup", "100644", "8dde57f1a8bcc8561a9fb27df318a7d9d8367f70", "d9ef8658cb78ea85a3c7bb8e3853b03eab4c896399e58c35ef5b960df2a51697"),
    ("ops/logrotate.d/rpi5-backup", "/etc/logrotate.d/rpi5-backup", "100644", "7d1490e4c6f525f80e14490e7946da95ea0bbd1f", "08e0b02be895592ffd1fd56ed6c5849cdc0e7b117c161e9382165ebcf05765e2"),
]
actual = [
    (item["path"], item["installed_target"], item["repository_mode"], item["source_git_blob_sha1"], item["sha256"])
    for item in data["files"]
]
assert actual == expected
assert len({item[0] for item in actual}) == len(actual)
assert len({item[1] for item in actual}) == len(actual)
print("V10 provenance manifest: PASS")
PY

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

printf '%s\n' 'V10 backup ownership import tests: PASS'
