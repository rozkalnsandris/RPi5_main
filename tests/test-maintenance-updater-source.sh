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
print(candidate["stage"])
print(candidate["sha256"])
print(candidate["size_bytes"])
print(candidate["git_blob_sha1"])
PY
)

expected_stage="${expected[0]}"
expected_sha256="${expected[1]}"
expected_size="${expected[2]}"
expected_blob="${expected[3]}"
actual_sha256="$(sha256sum "$source_file" | awk '{print $1}')"
actual_size="$(stat -c '%s' "$source_file")"
index_line="$(git -C "$repo" ls-files -s -- ops/bin/rpi5-update)"
index_mode="$(awk '{print $1}' <<<"$index_line")"
index_blob="$(awk '{print $2}' <<<"$index_line")"

if [[ "$actual_sha256" != "$expected_sha256" ||
      "$actual_size" != "$expected_size" ||
      "$index_blob" != "$expected_blob" ]]; then
    printf 'Updater provenance mismatch (%s): expected_sha=%s actual_sha=%s expected_size=%s actual_size=%s expected_blob=%s actual_blob=%s\n' \
        "$expected_stage" \
        "$expected_sha256" "$actual_sha256" \
        "$expected_size" "$actual_size" \
        "$expected_blob" "$index_blob" >&2
    exit 1
fi

[[ "$index_mode" == "100755" ]] || {
    echo "Updater Git mode must be 100755, got $index_mode" >&2
    exit 1
}

bash -n "$source_file"
python3 "$validator" "$source_file"

for temporary_path in \
    "$repo/ops/maintenance/.v21-staging" \
    "$repo/ops/maintenance/.v21-public-staging" \
    "$repo/.github/workflows/v21-assemble-updater.yml" \
    "$repo/.github/workflows/v21-sanitize-public-source.yml" \
    "$repo/.github/workflows/v21-assemble-public-source.yml" \
    "$repo/.github/workflows/v24-cleanup-ownership-transform.yml" \
    "$repo/.github/workflows/v24-finalize-cleanup.yml" \
    "$repo/.github/workflows/v24-finalize-tests.yml" \
    "$repo/.github/workflows/v25-shared-lock-transform.yml"; do
    [[ ! -e "$temporary_path" ]] || {
        echo "temporary V21/V24/V25 source transport artifact remains: $temporary_path" >&2
        exit 1
    }
done

printf 'Updater source ownership: PASS stage=%s sha256=%s size=%s mode=%s blob=%s\n' \
    "$expected_stage" "$actual_sha256" "$actual_size" "$index_mode" "$index_blob"
