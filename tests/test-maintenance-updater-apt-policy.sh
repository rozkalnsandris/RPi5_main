#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
policy="$repo/ops/lib/rpi5-update-apt-policy.sh"
source_file="$repo/ops/bin/rpi5-update"

[[ -f "$policy" && ! -L "$policy" ]]
[[ -f "$source_file" && ! -L "$source_file" ]]

# shellcheck source=/dev/null
source "$policy"

[[ "$RPI5_APT_METADATA_SKIPPED_RC" -eq 10 ]]

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/lists"

cat >"$tmp/bin/apt-get" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >>"$RPI5_TEST_APT_CALLS"
EOF
chmod 0755 "$tmp/bin/apt-get"

export RPI5_TEST_APT_CALLS="$tmp/apt-calls.log"
export PATH="$tmp/bin:$PATH"

set +e
rpi5_prepare_apt_metadata check -o Acquire::Retries=3
check_rc=$?
set -e
[[ "$check_rc" -eq "$RPI5_APT_METADATA_SKIPPED_RC" ]]
[[ ! -e "$RPI5_TEST_APT_CALLS" ]]

set +e
rpi5_prepare_apt_metadata cleanup -o Acquire::Retries=3
cleanup_rc=$?
set -e
[[ "$cleanup_rc" -eq 2 ]]
[[ ! -e "$RPI5_TEST_APT_CALLS" ]]

rpi5_prepare_apt_metadata run -o Acquire::Retries=3
[[ -f "$RPI5_TEST_APT_CALLS" ]]
[[ "$(wc -l <"$RPI5_TEST_APT_CALLS")" -eq 1 ]]
grep -Fxq -- '-o Acquire::Retries=3 --error-on=any update' "$RPI5_TEST_APT_CALLS"

python3 - "$tmp/lists/example_Packages" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.write_text("fixture\n", encoding="utf-8")
os.utime(path, (900, 900))
PY

age="$(rpi5_cached_apt_list_age_seconds "$tmp/lists" 1000)"
[[ "$age" == "100" ]]

rm -f "$tmp/lists/example_Packages"
set +e
rpi5_cached_apt_list_age_seconds "$tmp/lists" 1000 >/dev/null
empty_rc=$?
set -e
[[ "$empty_rc" -eq 1 ]]

# The updater must delegate metadata preparation to the reviewed policy helper.
grep -Fq 'rpi5-update-apt-policy.sh' "$source_file"
grep -Fq 'rpi5_prepare_apt_metadata "$MODE" "${APT_COMMON[@]}"' "$source_file"
if grep -Fq -- '--error-on=any update' "$source_file"; then
    echo "direct apt-get metadata refresh escaped the reviewed APT policy helper" >&2
    exit 1
fi

printf 'Maintenance updater APT policy: PASS\n'
