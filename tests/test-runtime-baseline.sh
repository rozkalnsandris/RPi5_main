#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo_root}/scripts/collect-runtime-baseline.sh"
verifier="${repo_root}/scripts/verify-runtime-baseline.sh"
renderer="${repo_root}/scripts/render-runtime-baseline.py"
test_root="$(mktemp -d "${repo_root}/evidence/test-runtime-baseline.XXXXXX")"
stub_bin="${test_root}/stub-bin"
mkdir -p -- "${stub_bin}"

cleanup() {
  rm -rf -- "${test_root}"
  rm -f -- "${repo_root}/evidence/test-runtime-baseline-link"
}
trap cleanup EXIT

fail() {
  printf 'test-runtime-baseline: FAIL: %s\n' "$*" >&2
  exit 1
}

assert_status() {
  local result="$1" section="$2" wanted="$3"
  awk -F '\t' -v section_name="${section}" -v wanted_class="${wanted}" '$1 == section_name && $4 == wanted_class { found=1 } END { exit(found ? 0 : 1) }' "${result}/section-status.tsv" || fail "unexpected classification for ${section}"
}

rechecksum() {
  local result="$1"
  (
    cd -- "${result}"
    LC_ALL=C find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort |
      while IFS= read -r file; do sha256sum -- "${file}"; done
  ) > "${result}/SHA256SUMS"
}

printf '%s\n' '#!/usr/bin/env bash' \
  'set -Eeuo pipefail' \
  'name=${0##*/}' \
  'case "${name}" in' \
  '  docker)' \
  '    mode=${STUB_DOCKER_MODE:-ok}' \
  '    if [[ "${mode}" == timeout ]]; then sleep 3; exit 124; fi' \
  '    if [[ "${mode}" == permission && "${1:-}" != --version ]]; then printf "permission denied while trying to connect to the Docker daemon\n" >&2; exit 1; fi' \
  '    if [[ "${mode}" == daemon && "${1:-}" != --version ]]; then printf "Cannot connect to the Docker daemon\n" >&2; exit 1; fi' \
  '    case "${1:-}" in' \
  '      version) if [[ "${mode}" == permission ]]; then printf "permission denied while trying to connect to the Docker daemon\n" >&2; exit 1; fi; if [[ "${mode}" == daemon ]]; then printf "Cannot connect to the Docker daemon\n" >&2; exit 1; fi; printf "27.0.1\n" ;;' \
  '      compose) case "${2:-}" in' \
  '        version) printf "Docker Compose version v2.29.1\n" ;;' \
  '        ls) if [[ "${STUB_COMPOSE_MODE:-json}" == fallback && "${4:-}" == json ]]; then printf "unknown flag: --format\n" >&2; exit 1; fi; if [[ "${4:-}" == json ]]; then printf "[{\"Name\":\"demo\",\"Status\":\"running(2)\",\"ConfigFiles\":\"/must-not-store\"}]\n"; else printf "demo\trunning\tConfigFiles=/must-not-store\n"; fi ;;' \
  '      esac ;;' \
  '      ps) printf "web\tghcr.io/example/web:1.2.3\trunning\tUp 2 hours (healthy)\nworker\tbusybox:latest\texited\tExited (0)\nstarter\tbusybox:latest\trestarting\tUp 1 second (health: starting)\nbadhealth\tbusybox:latest\trunning\tUp 1 minute (unhealthy)\nnohealth\tbusybox:latest\trunning\tUp 1 minute\nleaky\tbusybox:latest\trunning\tUp command=/must-not-store label=must-not-store mount=/must-not-store\n0123456789abcdef\tbusybox:latest\trunning\tUp\nimageid\t0123456789abcdef\trunning\tUp\n" ;;' \
  '      network) printf "bridge\tbridge\tlocal\nbridge\tbridge\tlocal\n" ;;' \
  '      --version) printf "Docker version 27.0.1\n" ;;' \
  '    esac ;;' \
  '  systemctl)' \
  '    mode=${STUB_SYSTEMD_MODE:-running}' \
  '    if [[ "${1:-}" == --version ]]; then printf "systemd 255\n"; exit 0; fi' \
  '    if [[ "${1:-}" == --system && "${2:-}" == is-system-running ]]; then if [[ "${mode}" == bus ]]; then printf "Failed to connect to bus: Operation not permitted\n" >&2; exit 1; fi; if [[ "${mode}" == degraded ]]; then printf "degraded\n"; exit 1; fi; if [[ "${mode}" == unknown ]]; then printf "mystery\n" >&2; exit 1; fi; printf "running\n"; exit 0; fi' \
  '    if [[ "${1:-}" == --system && "${2:-}" == list-unit-files ]]; then if [[ " $* " == *" --state=enabled "* ]]; then printf "demo.service enabled\nhousekeeping.timer enabled\n"; else printf "housekeeping.timer enabled\ninvalid.timer; enabled\n"; fi; exit 0; fi' \
  '    if [[ "${1:-}" == --system && "${2:-}" == list-units ]]; then printf "failed.service loaded failed failed ignored description\n"; exit 0; fi' \
  '    if [[ "${1:-}" == --system && "${2:-}" == show ]]; then unit=${3:-}; if [[ "${unit}" == housekeeping.timer ]]; then printf "Id=housekeeping.timer\nLoadState=loaded\nActiveState=active\nSubState=waiting\nUnit=demo.service\nNextElapseUSecRealtime=Wed 2026-01-01 00:00:00 UTC\nLastTriggerUSec=Tue 2025-12-31 00:00:00 UTC\nEnvironment=must-not-store\n"; else printf "Unit not found\n" >&2; exit 3; fi; exit 0; fi' \
  '    exit 1 ;;' \
  '  ss) if [[ "${STUB_NETWORK_MODE:-ok}" == timeout ]]; then sleep 3; exit 124; fi; if [[ "${STUB_NETWORK_MODE:-ok}" == restricted ]]; then printf "Operation not permitted\n" >&2; exit 1; fi; printf "tcp LISTEN 0 128 127.0.0.1:8080 0.0.0.0:*\ntcp6 LISTEN 0 128 [::]:443 [::]:*\nudp UNCONN 0 0 10.0.0.1:53 0.0.0.0:*\ntcp LISTEN 0 128 127.0.0.1:8080 0.0.0.0:*\n" ;;' \
  '  ip) if [[ "${STUB_NETWORK_MODE:-ok}" == restricted ]]; then printf "Operation not permitted\n" >&2; exit 1; fi; if [[ "${1:-}" == -j ]]; then if [[ "${STUB_NETWORK_MODE:-ok}" == fallback ]]; then printf "unknown option -j\n" >&2; exit 1; fi; printf "[{\"ifname\":\"lo\",\"operstate\":\"UNKNOWN\",\"link_type\":\"loopback\",\"address\":\"00:11:22:33:44:55\",\"flags\":[\"LOOPBACK\"],\"addr_info\":[{\"family\":\"inet\",\"local\":\"127.0.0.1\",\"scope\":\"host\"},{\"family\":\"inet6\",\"local\":\"::1\",\"scope\":\"host\"}]},{\"ifname\":\"eth0\",\"operstate\":\"UP\",\"link_type\":\"ether\",\"address\":\"00:11:22:33:44:56\",\"addr_info\":[{\"family\":\"inet\",\"local\":\"192.168.1.20\",\"scope\":\"global\"},{\"family\":\"inet6\",\"local\":\"fe80::1\",\"scope\":\"link\"}]}]\n"; else printf "lo UNKNOWN 127.0.0.1/8 ::1/128\neth0 UP 192.168.1.20/24 fe80::1/64\n"; fi ;;' \
  '  *) exit 127 ;;' \
  'esac' > "${stub_bin}/stub-command"
chmod 700 -- "${stub_bin}/stub-command"
for command_name in docker systemctl ss ip; do ln -s stub-command "${stub_bin}/${command_name}"; done

collect_result() {
  local label="$1"
  shift
  local log="${test_root}/collector-${label}-${RANDOM}.log" result
  env PATH="${stub_bin}:/usr/bin:/bin" RUNTIME_BASELINE_TEST_MODE=1 RUNTIME_BASELINE_FIXED_UTC='2026-01-01T00:00:00Z' "$@" \
    "${collector}" --output "${test_root}/output" --context test-host > "${log}"
  result="$(awk -F ': ' '/^Runtime baseline result:/ {print $2}' "${log}")"
  [[ -d "${result}" ]] || fail 'collector did not report a result directory'
  printf '%s\n' "${result}"
}

first_result="$(collect_result complete)"
"${verifier}" "${first_result}" >/dev/null
python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "${first_result}/summary.json"
awk -F '\t' 'NR == 1 { next } NF != 8 || $3 !~ /^[0-9]+$/ || $4 == "" { bad=1 } END { exit (NR == 13 && !bad ? 0 : 1) }' "${first_result}/section-status.tsv" || fail 'section status is incomplete'
if grep -RIEq 'ConfigFiles|Environment=|127\.0\.0\.1|192\.168\.1\.20|00:11:22:33:44:55|command=|label=|mount=|0123456789abcdef' "${first_result}"; then fail 'raw data leaked into evidence'; fi

render_json="${test_root}/render/current.json"
render_markdown="${test_root}/render/CURRENT_RUNTIME_BASELINE.md"
python3 "${renderer}" --input "${first_result}" --json-out "${render_json}" --markdown-out "${render_markdown}"
python3 - "${render_json}" "${first_result}/SHA256SUMS" <<'PY'
import hashlib, json, pathlib, sys
payload=json.load(open(sys.argv[1], encoding='utf-8'))
assert payload['metadata']['evidence_manifest_sha256'] == hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest()
assert {x['health'] for x in payload['docker']['containers']} == {'healthy','unhealthy','none','starting','unknown'}
assert payload['docker']['compose_projects'] == [{'name':'demo','status':'running'}]
assert payload['docker']['networks'] == [{'name':'bridge','driver':'bridge','scope':'local'}]
assert payload['systemd']['system_state'] == 'running'
assert payload['sockets'] == sorted(payload['sockets'], key=lambda x:(x['protocol'],x['address_scope'],x['port']))
assert all('127.' not in value for value in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines())
PY

second_result="$(collect_result deterministic)"
second_json="${test_root}/render/second.json"
second_markdown="${test_root}/render/second.md"
python3 "${renderer}" --input "${second_result}" --json-out "${second_json}" --markdown-out "${second_markdown}"
cmp "${render_json}" "${second_json}" || fail 'rendered JSON is not deterministic'
cmp "${render_markdown}" "${second_markdown}" || fail 'rendered Markdown is not deterministic'

permission_result="$(collect_result permission STUB_DOCKER_MODE=permission)"
assert_status "${permission_result}" docker_engine_version permission_denied
daemon_result="$(collect_result daemon STUB_DOCKER_MODE=daemon)"
assert_status "${daemon_result}" docker_engine_version daemon_unreachable
degraded_result="$(collect_result degraded STUB_SYSTEMD_MODE=degraded)"
assert_status "${degraded_result}" systemd_system_state success_degraded
unknown_result="$(collect_result unknown STUB_SYSTEMD_MODE=unknown)"
assert_status "${unknown_result}" systemd_system_state other_error
fallback_result="$(collect_result compose-fallback STUB_COMPOSE_MODE=fallback)"
"${verifier}" "${fallback_result}" >/dev/null
grep -q '^demo[[:space:]]\+running$' "${fallback_result}/sections/docker_compose_projects.txt" || fail 'compose fallback projection failed'
if grep -q 'invalid.timer;' "${first_result}/sections/systemd_timer_units.txt"; then fail 'arbitrary timer unit was retained'; fi
interface_fallback_result="$(collect_result interface-fallback STUB_NETWORK_MODE=fallback)"
"${verifier}" "${interface_fallback_result}" >/dev/null
grep -q '^eth0[[:space:]]' "${interface_fallback_result}/sections/network_interfaces.txt" || fail 'interface fallback projection failed'
restricted_result="$(collect_result restricted STUB_NETWORK_MODE=restricted)"
assert_status "${restricted_result}" listening_sockets restricted_or_not_permitted
missing_result="$(collect_result missing RUNTIME_BASELINE_TEST_MISSING_COMMANDS=docker,systemctl,ss,ip)"
assert_status "${missing_result}" docker_engine_version command_missing
assert_status "${missing_result}" systemd_system_state command_missing
assert_status "${missing_result}" listening_sockets command_missing
assert_status "${missing_result}" network_interfaces command_missing
timeout_result="$(collect_result timeout RUNTIME_BASELINE_TIMEOUT_SECONDS=1 STUB_DOCKER_MODE=timeout)"
assert_status "${timeout_result}" docker_engine_version timeout

if RUNTIME_BASELINE_TEST_MODE=1 RUNTIME_BASELINE_TEST_UID=0 "${collector}" --output "${test_root}/root-refusal" --context test-host >/dev/null 2>&1; then fail 'collector accepted root identity'; fi
if "${collector}" --output "${repo_root}/.." --context test-host >/dev/null 2>&1; then fail 'collector accepted output escape'; fi
if "${collector}" --output "${test_root}/invalid" --context 'invalid context!' >/dev/null 2>&1; then fail 'collector accepted invalid context'; fi
ln -s "${test_root}" "${repo_root}/evidence/test-runtime-baseline-link"
if "${collector}" --output "${repo_root}/evidence/test-runtime-baseline-link" --context test-host >/dev/null 2>&1; then fail 'collector accepted symlink output path'; fi
rm -f -- "${repo_root}/evidence/test-runtime-baseline-link"

symlink_result="$(collect_result symlink)"
ln -s /tmp "${symlink_result}/sections/linked-artifact"
if "${verifier}" "${symlink_result}" >/dev/null 2>&1; then fail 'verifier accepted internal symlink'; fi
fifo_result="$(collect_result fifo)"
mkfifo "${fifo_result}/sections/pipe-artifact"
if "${verifier}" "${fifo_result}" >/dev/null 2>&1; then fail 'verifier accepted FIFO'; fi
checksum_result="$(collect_result checksum)"
printf x >> "${checksum_result}/summary.json"
if "${verifier}" "${checksum_result}" >/dev/null 2>&1; then fail 'verifier accepted checksum corruption'; fi
oversized_result="$(collect_result oversized)"
truncate -s 65537 "${oversized_result}/sections/docker_containers.txt"
if "${verifier}" "${oversized_result}" >/dev/null 2>&1; then fail 'verifier accepted oversized evidence'; fi
many_result="$(collect_result many)"
for number in $(seq 1 40); do : > "${many_result}/sections/extra-${number}.txt"; done
if "${verifier}" "${many_result}" >/dev/null 2>&1; then fail 'verifier accepted excessive file count'; fi
unknown_result="$(collect_result unknown-section)"
sed -i '2s/^docker_engine_version/unknown_section/' "${unknown_result}/section-status.tsv"
rechecksum "${unknown_result}"
if "${verifier}" "${unknown_result}" >/dev/null 2>&1; then fail 'verifier accepted unknown section'; fi
unknown_class_result="$(collect_result unknown-class)"
sed -i '2s/\tsuccess\t/\tunknown_class\t/' "${unknown_class_result}/section-status.tsv"
rechecksum "${unknown_class_result}"
if "${verifier}" "${unknown_class_result}" >/dev/null 2>&1; then fail 'verifier accepted unknown classification'; fi
raw_ip_result="$(collect_result raw-ip)"
printf 'tcp\tloopback\t8080\n192.0.2.1\n' > "${raw_ip_result}/sections/listening_sockets.txt"
rechecksum "${raw_ip_result}"
if "${verifier}" "${raw_ip_result}" >/dev/null 2>&1; then fail 'verifier accepted raw IP'; fi
raw_mac_result="$(collect_result raw-mac)"
printf 'lo\tunknown\tloopback\ttrue\t1\t1\thost=2,link=0,global=0,other=0\n00:11:22:33:44:55\n' > "${raw_mac_result}/sections/network_interfaces.txt"
rechecksum "${raw_mac_result}"
if "${verifier}" "${raw_mac_result}" >/dev/null 2>&1; then fail 'verifier accepted MAC'; fi
secret_result="$(collect_result secret)"
secret_value='must-not-appear-in-output'
printf 'token=%s\n' "${secret_value}" >> "${secret_result}/sections/docker_containers.txt"
rechecksum "${secret_result}"
secret_log="${test_root}/secret-verifier.log"
if "${verifier}" "${secret_result}" >"${secret_log}" 2>&1; then fail 'verifier accepted secret'; fi
if grep -Fq -- "${secret_value}" "${secret_log}"; then fail 'verifier printed secret value'; fi
if python3 "${renderer}" --input "${secret_result}" --json-out "${test_root}/render/invalid.json" --markdown-out "${test_root}/render/invalid.md" >/dev/null 2>&1; then fail 'renderer accepted unverified evidence'; fi
if python3 "${renderer}" --input "${first_result}" --json-out /tmp/v02b-invalid.json --markdown-out /tmp/v02b-invalid.md >/dev/null 2>&1; then fail 'renderer wrote outside repository'; fi

printf '%s\n' 'Runtime baseline tests: PASS'
