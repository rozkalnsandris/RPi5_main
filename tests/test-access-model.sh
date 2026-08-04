#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
diagnostic="${repo_root}/scripts/diagnose-access-model.sh"
verifier="${repo_root}/scripts/verify-access-diagnostic.sh"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${repo_root}/scripts/safe-inventory-lib.sh"

test_root="$(mktemp -d "${repo_root}/evidence/test-access-model.XXXXXX")"
stub_bin="${test_root}/stub-bin"
mkdir -p -- "${stub_bin}"

cleanup() {
  rm -rf -- "${test_root}"
  rm -f -- "${repo_root}/evidence/test-access-model-link"
}
trap cleanup EXIT

fail() {
  printf 'test-access-model: FAIL: %s\n' "$*" >&2
  exit 1
}

assert_status() {
  local result="$1" probe="$2" wanted="$3"
  awk -F '\t' -v probe_name="${probe}" -v wanted_class="${wanted}" '$1 == probe_name && $4 == wanted_class { found=1 } END { exit(found ? 0 : 1) }' "${result}/probe-status.tsv" || fail "unexpected classification for ${probe}"
}

printf '%s\n' '#!/usr/bin/env bash' \
  'set -Eeuo pipefail' \
  'name=${0##*/}' \
  'case "${name}" in' \
  '  id) case "${1:-}" in -u) printf "1000\\n" ;; -un) printf "andris\\n" ;; -gn) printf "andris\\n" ;; -Gn) printf "andris docker\\n" ;; *) printf "uid=1000(andris) gid=1000(andris) groups=1000(andris),999(docker)\\n" ;; esac ;;' \
  '  readlink) printf "%s:[4026531993]\\n" "${1##*/}" ;;' \
  '  stat) printf "type=socket mode=660 owner=root group=docker\\n" ;;' \
  '  namei) printf "f: /run/example\\ndrwxr-xr-x root root /\\n" ;;' \
  '  docker)' \
  '    mode=${STUB_DOCKER_MODE:-ok}' \
  '    if [[ "${mode}" == timeout ]]; then sleep 3; exit 124; fi' \
  '    if [[ "${mode}" == permission && "${1:-}" != --version && "${2:-}" != version ]]; then printf "permission denied while trying to connect to the docker API\\n" >&2; exit 1; fi' \
  '    if [[ "${mode}" == daemon && "${1:-}" != --version && "${2:-}" != version ]]; then printf "Cannot connect to the Docker daemon\\n" >&2; exit 1; fi' \
  '    case "${1:-}" in' \
  '      --version) printf "Docker version 27.0\\n" ;;' \
  '      context) printf "default\\n" ;;' \
  '      version) printf "27.0\\n" ;;' \
  '      ps) printf "demo\\tdemo:latest\\tUp\\n" ;;' \
  '      network) printf "bridge\\tbridge\\n" ;;' \
  '      compose) case "${2:-}" in version) printf "Docker Compose version v2\\n" ;; ls) if [[ "${mode}" == unsupported ]]; then printf "unknown flag: --format\\n" >&2; exit 1; fi; if [[ "${mode}" == configfiles ]]; then printf "demo\\trunning\\tConfigFiles=/not/stored\\n"; else printf "demo\\trunning\\n"; fi ;; esac ;;' \
  '    esac ;;' \
  '  systemctl) if [[ "${STUB_SYSTEMD_MODE:-ok}" == bus && "${1:-}" == --system ]]; then printf "Failed to connect to bus: Operation not permitted\\n" >&2; exit 1; fi; if [[ "${1:-}" == --version ]]; then printf "systemd 252\\n"; else printf "running\\n"; fi ;;' \
  '  ss) if [[ "${STUB_NETWORK_MODE:-ok}" == restricted ]]; then printf "Operation not permitted\\n" >&2; exit 1; fi; printf "tcp LISTEN 0 128 127.0.0.1:8080 0.0.0.0:*\\n" ;;' \
  '  ip) if [[ "${STUB_NETWORK_MODE:-ok}" == restricted ]]; then printf "Operation not permitted\\n" >&2; exit 1; fi; printf "lo UNKNOWN 127.0.0.1/8\\n" ;;' \
  '  *) exit 127 ;;' \
  'esac' > "${stub_bin}/stub-command"
chmod 700 -- "${stub_bin}/stub-command"
for command_name in id readlink stat namei docker systemctl ss ip; do ln -s stub-command "${stub_bin}/${command_name}"; done

collect_result() {
  local label="$1"
  shift
  local log="${test_root}/collector-${label}-${RANDOM}.log" result
  env PATH="${stub_bin}:/usr/bin:/bin" ACCESS_DIAGNOSTIC_TEST_MODE=1 ACCESS_DIAGNOSTIC_FIXED_UTC='2026-01-01T00:00:00Z' "$@" \
    "${diagnostic}" --output "${test_root}/output" --context test-context > "${log}"
  result="$(awk -F ': ' '/^Access diagnostic result:/ {print $2}' "${log}")"
  [[ -d "${result}" ]] || fail 'diagnostic did not report a result directory'
  printf '%s\n' "${result}"
}

first_result="$(collect_result normal)"
"${verifier}" "${first_result}" >/dev/null
python3 -c 'import json,sys; json.load(open(sys.argv[1],encoding="utf-8")); json.load(open(sys.argv[2],encoding="utf-8"))' "${first_result}/summary.json" "${first_result}/decision.json"
awk -F '\t' 'NR == 1 { next } NF != 8 || $3 !~ /^[0-9]+$/ || $4 == "" { bad=1 } END { exit (NR > 1 && !bad ? 0 : 1) }' "${first_result}/probe-status.tsv" || fail 'probe status is incomplete'

second_result="$(collect_result repeat)"
cmp "${first_result}/summary.json" "${second_result}/summary.json" || fail 'summary is not deterministic in fixed test mode'

missing_result="$(collect_result missing ACCESS_DIAGNOSTIC_TEST_MISSING_COMMANDS=docker,systemctl,ss,ip)"
assert_status "${missing_result}" docker_client_version command_missing
assert_status "${missing_result}" systemctl_version command_missing
assert_status "${missing_result}" ss_listening command_missing
assert_status "${missing_result}" ip_brief_address command_missing

permission_result="$(collect_result permission STUB_DOCKER_MODE=permission)"
assert_status "${permission_result}" docker_server_version permission_denied
daemon_result="$(collect_result daemon STUB_DOCKER_MODE=daemon)"
assert_status "${daemon_result}" docker_server_version daemon_unreachable
bus_result="$(collect_result bus STUB_SYSTEMD_MODE=bus)"
assert_status "${bus_result}" system_running system_bus_unreachable
unsupported_result="$(collect_result unsupported STUB_DOCKER_MODE=unsupported)"
assert_status "${unsupported_result}" docker_compose_projects unsupported_syntax
timeout_result="$(collect_result timeout ACCESS_DIAGNOSTIC_TIMEOUT_SECONDS=1 STUB_DOCKER_MODE=timeout)"
assert_status "${timeout_result}" docker_client_version timeout
restricted_result="$(collect_result restricted STUB_NETWORK_MODE=restricted)"
assert_status "${restricted_result}" ss_listening restricted_or_not_permitted

if ACCESS_DIAGNOSTIC_TEST_MODE=1 ACCESS_DIAGNOSTIC_TEST_UID=0 "${diagnostic}" --output "${test_root}/root-refusal" --context test-context >/dev/null 2>&1; then fail 'diagnostic accepted test root identity'; fi
if "${diagnostic}" --output "${test_root}/invalid" --context 'invalid context!' >/dev/null 2>&1; then fail 'diagnostic accepted invalid context'; fi
if "${diagnostic}" --output "${repo_root}/.." --context test-context >/dev/null 2>&1; then fail 'diagnostic accepted output escape'; fi
ln -s "${test_root}" "${repo_root}/evidence/test-access-model-link"
if "${diagnostic}" --output "${repo_root}/evidence/test-access-model-link" --context test-context >/dev/null 2>&1; then fail 'diagnostic accepted symlinked output'; fi
rm -f -- "${repo_root}/evidence/test-access-model-link"

symlink_result="$(collect_result symlink)"
ln -s /tmp "${symlink_result}/sections/linked-artifact"
if "${verifier}" "${symlink_result}" >/dev/null 2>&1; then fail 'verifier accepted internal symlink'; fi

fifo_result="$(collect_result fifo)"
mkfifo "${fifo_result}/sections/pipe-artifact"
if "${verifier}" "${fifo_result}" >/dev/null 2>&1; then fail 'verifier accepted FIFO'; fi

checksum_result="$(collect_result checksum)"
printf 'x' >> "${checksum_result}/summary.json"
if "${verifier}" "${checksum_result}" >/dev/null 2>&1; then fail 'verifier accepted checksum corruption'; fi

oversized_result="$(collect_result oversized)"
truncate -s 65537 "${oversized_result}/sections/large-artifact.txt"
if "${verifier}" "${oversized_result}" >/dev/null 2>&1; then fail 'verifier accepted oversized file'; fi

many_result="$(collect_result many)"
for number in $(seq 1 70); do : > "${many_result}/sections/extra-${number}.txt"; done
if "${verifier}" "${many_result}" >/dev/null 2>&1; then fail 'verifier accepted excessive file count'; fi

unknown_probe_result="$(collect_result unknown-probe)"
sed -i '2s/^execution_identity/unknown_probe/' "${unknown_probe_result}/probe-status.tsv"
if "${verifier}" "${unknown_probe_result}" >/dev/null 2>&1; then fail 'verifier accepted unknown probe'; fi

unknown_class_result="$(collect_result unknown-class)"
sed -i '2s/\tsuccess\t/\tunknown_class\t/' "${unknown_class_result}/probe-status.tsv"
if "${verifier}" "${unknown_class_result}" >/dev/null 2>&1; then fail 'verifier accepted unknown classification'; fi

fixture_value='value-must-not-appear'
key_name="$(printf '%s%s' pass word)"
assignment_output="$(printf '%s=%s\n' "${key_name}" "${fixture_value}" | safe_inventory_sanitize_stream)"
[[ "${assignment_output}" != *"${fixture_value}"* ]] || fail 'assignment value was not redacted'
begin_marker="$(printf '%s %s' '-----BEGIN' 'PRIVATE KEY-----')"
end_marker="$(printf '%s %s' '-----END' 'PRIVATE KEY-----')"
key_output="$(printf '%s\n%s\n%s\n' "${begin_marker}" "${fixture_value}" "${end_marker}" | safe_inventory_sanitize_stream)"
[[ "${key_output}" != *"${fixture_value}"* ]] || fail 'private key block value was not redacted'
bearer_output="$(printf '%s %s\n' Bearer "${fixture_value}" | safe_inventory_sanitize_stream)"
[[ "${bearer_output}" != *"${fixture_value}"* ]] || fail 'bearer value was not redacted'
basic_output="$(printf '%s %s\n' Basic "${fixture_value}" | safe_inventory_sanitize_stream)"
[[ "${basic_output}" != *"${fixture_value}"* ]] || fail 'basic value was not redacted'
url_output="$(printf 'https://%s:%s@example.invalid/path\n' user "${fixture_value}" | safe_inventory_sanitize_stream)"
[[ "${url_output}" != *"${fixture_value}"* ]] || fail 'URL userinfo was not redacted'

environment_name="$(printf '%s_%s' GH TOKEN)"
environment_result="$(collect_result environment "${environment_name}=${fixture_value}")"
grep -q 'GH_TOKEN[[:space:]]\+present=true' "${environment_result}/sections/environment_presence.txt" || fail 'environment presence was not recorded'
if grep -Fq -- "${fixture_value}" "${environment_result}/sections/environment_presence.txt"; then fail 'environment value was collected'; fi

environment_schema_result="$(collect_result environment-schema)"
printf 'GH_TOKEN\tvalue-not-allowed\n' > "${environment_schema_result}/sections/environment_presence.txt"
if "${verifier}" "${environment_schema_result}" >/dev/null 2>&1; then fail 'verifier accepted environment value schema violation'; fi

compose_result="$(collect_result compose STUB_DOCKER_MODE=configfiles)"
if grep -Rqi 'ConfigFiles' "${compose_result}/sections"; then fail 'raw Compose ConfigFiles field was stored'; fi
grep -q '^demo[[:space:]]\+running$' "${compose_result}/sections/docker_compose_projects.txt" || fail 'Compose projection did not retain name and status'
if grep -q 'unrelated-user' "${first_result}/sections/execution_identity.txt"; then fail 'unrelated account data was collected'; fi

leak_result="$(collect_result leak)"
printf '%s=%s\n' "${key_name}" "${fixture_value}" >> "${leak_result}/sections/execution_identity.txt"
verifier_log="${test_root}/verifier.log"
if "${verifier}" "${leak_result}" >"${verifier_log}" 2>&1; then fail 'verifier accepted secret-like content'; fi
if grep -Fq -- "${fixture_value}" "${verifier_log}"; then fail 'verifier printed secret value'; fi

printf '%s\n' 'Access model tests: PASS'
