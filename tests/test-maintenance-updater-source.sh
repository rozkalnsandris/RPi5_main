#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_file="$repo/ops/bin/rpi5-update"
manifest="$repo/ops/maintenance/updater-source-provenance.json"
validator="$repo/scripts/validate-maintenance-updater-source.py"

[[ -f "$source_file" && ! -L "$source_file" ]]
[[ -f "$manifest" && ! -L "$manifest" ]]
[[ -f "$validator" && ! -L "$validator" ]]

readarray -t expected < <(
    python3 - "$manifest" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
candidate = data["candidate"]
print(candidate["sha256"])
print(candidate["size_bytes"])
print(candidate["git_blob_sha1"])
PY
)

expected_sha256="${expected[0]}"
expected_size="${expected[1]}"
expected_blob="${expected[2]}"
actual_sha256="$(sha256sum "$source_file" | awk '{print $1}')"
actual_size="$(stat -c '%s' "$source_file")"
index_line="$(git -C "$repo" ls-files -s -- ops/bin/rpi5-update)"
index_mode="$(awk '{print $1}' <<<"$index_line")"
index_blob="$(awk '{print $2}' <<<"$index_line")"

[[ "$actual_sha256" == "$expected_sha256" ]] || {
    echo "V21 updater SHA256 mismatch: expected=$expected_sha256 actual=$actual_sha256" >&2
    exit 1
}
[[ "$actual_size" == "$expected_size" ]] || {
    echo "V21 updater size mismatch: expected=$expected_size actual=$actual_size" >&2
    exit 1
}
[[ "$index_mode" == "100755" ]] || {
    echo "V21 updater Git mode must be 100755, got $index_mode" >&2
    exit 1
}
[[ "$index_blob" == "$expected_blob" ]] || {
    echo "V21 updater Git blob mismatch: expected=$expected_blob actual=$index_blob" >&2
    exit 1
}

bash -n "$source_file"
python3 "$validator" "$source_file"

for temporary_path in \
    "$repo/ops/maintenance/.v21-staging" \
    "$repo/ops/maintenance/.v21-public-staging" \
    "$repo/.github/workflows/v21-assemble-updater.yml" \
    "$repo/.github/workflows/v21-sanitize-public-source.yml" \
    "$repo/.github/workflows/v21-assemble-public-source.yml"; do
    [[ ! -e "$temporary_path" ]] || {
        echo "temporary V21 source transport artifact remains: $temporary_path" >&2
        exit 1
    }
done

printf 'V21 updater source ownership: PASS sha256=%s size=%s mode=%s\n' \
    "$actual_sha256" "$actual_size" "$index_mode"
