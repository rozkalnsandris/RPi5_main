#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo_root}/scripts/collect-safe-inventory.sh"
verifier="${repo_root}/scripts/verify-safe-inventory.sh"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${repo_root}/scripts/safe-inventory-lib.sh"

test_root="$(mktemp -d "${repo_root}/evidence/test-safe-inventory.XXXXXX")"
stub_bin="${test_root}/stub-bin"
mkdir -p -- "${stub_bin}"

cleanup() {
  rm -rf -- "${test_root}"
  rm -f -- "${repo_root}/evidence/test-safe-inventory-link"
}
trap cleanup EXIT

fail() {
  printf 'test-safe-inventory: FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  [[ "$1" == *"$2"* ]] || fail "$3"
}

assert_not_contains() {
  [[ "$1" != *"$2"* ]] || fail "$3"
}

printf '%s\n' '#!/usr/bin/env bash' \
  'set -Eeuo pipefail' \
  'name=${0##*/}' \
  'case "${name}" in' \
  '  cat) printf "PRETTY_NAME=TestOS\\nVERSION_ID=1\\n" ;;' \
  '  uname) printf "Linux test 6.1 aarch64\\n" ;;' \
  '  uptime) printf "up 1 hour\\n" ;;' \
  '  lscpu) printf "Architecture: aarch64\\nCPU(s): 4\\n" ;;' \
  '  free) printf "Mem: 1024 512 512\\n" ;;' \
  '  lsblk) printf "NAME TYPE SIZE\\nsda disk 8G\\n" ;;' \
  '  df) printf "Filesystem Type Size Used Avail Use%% Mounted on\\n/dev/root ext4 8G 1G 7G 13%% /\\n" ;;' \
  '  findmnt) printf "/ /dev/root ext4 rw\\n" ;;' \
  '  dpkg-query) printf "base-files\\t1.0\\n" ;;' \
  '  systemctl) if [[ "${STUB_SYSTEMCTL_MODE:-ok}" == timeout ]]; then sleep 3; fi; printf "demo.service enabled\\n" ;;' \
  '  docker) case "${1:-}" in version) printf "27.0\\n" ;; ps) printf "demo\\tdemo:latest\\tUp (healthy)\\n" ;; compose) printf "demo-project\\n" ;; network) printf "bridge\\tbridge\\n" ;; esac ;;' \
  '  ss) printf "tcp LISTEN 0 128 127.0.0.1:8080 0.0.0.0:*\\n" ;;' \
  '  journalctl) printf "2026-01-01T00:00:00Z kernel: warning summary\\n" ;;' \
  '  ip) printf "lo UNKNOWN 127.0.0.1/8\\n" ;;' \
  '  hostname) printf "test-host\\n" ;;' \
  '  *) exit 127 ;;' \
  'esac' > "${stub_bin}/stub-command"
chmod 700 -- "${stub_bin}/stub-command"
for command_name in cat uname uptime lscpu free lsblk df findmnt dpkg-query systemctl docker ss journalctl ip hostname; do
  ln -s stub-command "${stub_bin}/${command_name}"
done

collect_result() {
  local mode="${1:-ok}" log result
  log="${test_root}/collector-${RANDOM}.log"
  if [[ "${mode}" == 'timeout' ]]; then
    PATH="${stub_bin}:/usr/bin:/bin" STUB_SYSTEMCTL_MODE=timeout SAFE_INVENTORY_TEST_MODE=1 SAFE_INVENTORY_FIXED_UTC='2026-01-01T00:00:00Z' SAFE_INVENTORY_TIMEOUT_SECONDS=1 \
      "${collector}" --output "${test_root}/output" > "${log}"
  elif [[ "${mode}" == 'missing' ]]; then
    PATH="${stub_bin}:/usr/bin:/bin" SAFE_INVENTORY_TEST_MODE=1 SAFE_INVENTORY_TEST_MISSING_COMMANDS=docker SAFE_INVENTORY_FIXED_UTC='2026-01-01T00:00:00Z' \
      "${collector}" --output "${test_root}/output" > "${log}"
  else
    PATH="${stub_bin}:/usr/bin:/bin" SAFE_INVENTORY_TEST_MODE=1 SAFE_INVENTORY_FIXED_UTC='2026-01-01T00:00:00Z' \
      "${collector}" --output "${test_root}/output" > "${log}"
  fi
  result="$(awk -F ': ' '/^Inventory result:/ {print $2}' "${log}")"
  [[ -d "${result}" ]] || fail 'collector did not report a result directory'
  printf '%s\n' "${result}"
}

first_result="$(collect_result)"
"${verifier}" "${first_result}" >/dev/null
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${first_result}/summary.json"
awk -F '\t' 'NR == 1 { next } NF != 5 || $4 !~ /^[0-9]+$/ { bad=1 } END { exit (NR > 1 && !bad ? 0 : 1) }' "${first_result}/section-status.tsv" || fail 'section statuses are incomplete'

second_result="$(collect_result)"
cmp "${first_result}/summary.json" "${second_result}/summary.json" || fail 'summary is not deterministic in test mode'

missing_result="$(collect_result missing)"
awk -F '\t' '$1 == "docker_version" && $3 == "false" && $4 == "127" { found=1 } END { exit(found ? 0 : 1) }' "${missing_result}/section-status.tsv" || fail 'missing optional command was not recorded'

timeout_result="$(collect_result timeout)"
awk -F '\t' '$1 == "enabled_units" && $4 == "124" { found=1 } END { exit(found ? 0 : 1) }' "${timeout_result}/section-status.tsv" || fail 'timeout was not recorded'

if SAFE_INVENTORY_TEST_MODE=1 SAFE_INVENTORY_TEST_UID=0 "${collector}" --output "${test_root}/root-refusal" >/dev/null 2>&1; then
  fail 'collector accepted test root identity'
fi
if "${collector}" --output "${repo_root}/.." >/dev/null 2>&1; then
  fail 'collector accepted output-path escape'
fi
ln -s "${test_root}" "${repo_root}/evidence/test-safe-inventory-link"
if "${collector}" --output "${repo_root}/evidence/test-safe-inventory-link" >/dev/null 2>&1; then
  fail 'collector accepted symlinked output path'
fi
rm -f -- "${repo_root}/evidence/test-safe-inventory-link"

symlink_result="$(collect_result)"
ln -s /tmp "${symlink_result}/sections/linked-artifact"
if "${verifier}" "${symlink_result}" >/dev/null 2>&1; then fail 'verifier accepted symlink'; fi

fifo_result="$(collect_result)"
mkfifo "${fifo_result}/sections/pipe-artifact"
if "${verifier}" "${fifo_result}" >/dev/null 2>&1; then fail 'verifier accepted FIFO'; fi

checksum_result="$(collect_result)"
printf 'x' >> "${checksum_result}/summary.json"
if "${verifier}" "${checksum_result}" >/dev/null 2>&1; then fail 'verifier accepted invalid checksum'; fi

oversized_result="$(collect_result)"
truncate -s 524289 "${oversized_result}/sections/large-artifact.txt"
if "${verifier}" "${oversized_result}" >/dev/null 2>&1; then fail 'verifier accepted oversized output'; fi

many_result="$(collect_result)"
for number in $(seq 1 90); do : > "${many_result}/sections/extra-${number}.txt"; done
if "${verifier}" "${many_result}" >/dev/null 2>&1; then fail 'verifier accepted too many files'; fi

fixture_value='value-must-not-appear'
key_name="$(printf '%s%s' pass word)"
assignment_output="$(printf '%s=%s\n' "${key_name}" "${fixture_value}" | safe_inventory_sanitize_stream)"
assert_not_contains "${assignment_output}" "${fixture_value}" 'assignment value was not redacted'
assert_contains "${assignment_output}" "${key_name}=[REDACTED]" 'assignment key was not preserved'

begin_marker="$(printf '%s %s' '-----BEGIN' 'PRIVATE KEY-----')"
end_marker="$(printf '%s %s' '-----END' 'PRIVATE KEY-----')"
key_output="$(printf '%s\n%s\n%s\n' "${begin_marker}" "${fixture_value}" "${end_marker}" | safe_inventory_sanitize_stream)"
assert_not_contains "${key_output}" "${fixture_value}" 'private-key block value was not redacted'

auth_kind='Bearer'
bearer_output="$(printf '%s %s\n' "${auth_kind}" "${fixture_value}" | safe_inventory_sanitize_stream)"
assert_not_contains "${bearer_output}" "${fixture_value}" 'bearer value was not redacted'
basic_kind='Basic'
basic_output="$(printf '%s %s\n' "${basic_kind}" "${fixture_value}" | safe_inventory_sanitize_stream)"
assert_not_contains "${basic_output}" "${fixture_value}" 'basic value was not redacted'
url_output="$(printf 'https://%s:%s@example.invalid/path\n' user "${fixture_value}" | safe_inventory_sanitize_stream)"
assert_not_contains "${url_output}" "${fixture_value}" 'URL userinfo was not redacted'

redacted_file="${test_root}/redacted.txt"
printf '%s\n' "${bearer_output}" > "${redacted_file}"
if safe_inventory_file_has_obvious_secret "${redacted_file}"; then fail 'verifier scanner rejected redacted authorization'; fi

leak_result="$(collect_result)"
printf '%s=%s\n' "${key_name}" "${fixture_value}" > "${leak_result}/sections/content-check.txt"
verifier_log="${test_root}/verifier.log"
if "${verifier}" "${leak_result}" >"${verifier_log}" 2>&1; then fail 'verifier accepted secret-like content'; fi
if grep -Fq -- "${fixture_value}" "${verifier_log}"; then fail 'verifier printed a secret value'; fi

printf '%s\n' 'Safe inventory tests: PASS'
