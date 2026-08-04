#!/usr/bin/env bash
# V01: bounded, sanitized, read-only infrastructure inventory.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"

collector_version='v01.0.0'
section_timeout_seconds="${SAFE_INVENTORY_TIMEOUT_SECONDS:-15}"
max_section_bytes="${SAFE_INVENTORY_MAX_SECTION_BYTES:-524288}"

die() {
  printf 'collect-safe-inventory: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'Usage: %s --output DIR\n' "${0##*/}" >&2
}

effective_uid() {
  if [[ "${SAFE_INVENTORY_TEST_MODE:-}" == '1' && -n "${SAFE_INVENTORY_TEST_UID:-}" ]]; then
    printf '%s\n' "${SAFE_INVENTORY_TEST_UID}"
  else
    id -u
  fi
}

utc_now() {
  if [[ "${SAFE_INVENTORY_TEST_MODE:-}" == '1' && -n "${SAFE_INVENTORY_FIXED_UTC:-}" ]]; then
    printf '%s\n' "${SAFE_INVENTORY_FIXED_UTC}"
  else
    date -u '+%Y-%m-%dT%H:%M:%SZ'
  fi
}

assert_no_symlink_components() {
  local absolute_path="$1" component cursor='/'
  local -a parts=()
  IFS='/' read -r -a parts <<< "${absolute_path}"
  for component in "${parts[@]}"; do
    case "${component}" in
      ''|'.') ;;
      '..') cursor="$(dirname -- "${cursor}")" ;;
      *)
        if [[ "${cursor}" == '/' ]]; then
          cursor="/${component}"
        else
          cursor="${cursor}/${component}"
        fi
        [[ -L "${cursor}" ]] && die 'refusing a path containing a symlink'
        ;;
    esac
  done
  return 0
}

if [[ $# -ne 2 || "$1" != '--output' || -z "${2:-}" ]]; then
  usage
  exit 2
fi

if [[ "$(effective_uid)" == '0' ]]; then
  die 'refusing to run as root'
fi
command -v timeout >/dev/null 2>&1 || die 'timeout is required for bounded collection'
[[ "${section_timeout_seconds}" =~ ^[1-9][0-9]*$ ]] || die 'invalid timeout value'
[[ "${max_section_bytes}" =~ ^[1-9][0-9]*$ ]] || die 'invalid section byte limit'

output_arg="$2"
if [[ "${output_arg}" == /* ]]; then
  requested_absolute="${output_arg}"
else
  requested_absolute="$(pwd -P)/${output_arg}"
fi
assert_no_symlink_components "${requested_absolute}"
output_base="$(realpath -m -- "${requested_absolute}")"
case "${output_base}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) die 'output directory must resolve below this repository evidence/ or exports/ tree' ;;
esac
if [[ -e "${output_base}" && ! -d "${output_base}" ]]; then
  die 'output path is not a directory'
fi
umask 077
mkdir -p -- "${output_base}"
assert_no_symlink_components "${output_base}"

timestamp="$(utc_now)"
timestamp_slug="${timestamp//:/-}"
result_dir="$(mktemp -d "${output_base}/v01-${timestamp_slug}-XXXXXX")"
sections_dir="${result_dir}/sections"
mkdir -p -- "${sections_dir}"
chmod 700 -- "${result_dir}" "${sections_dir}"
status_file="${result_dir}/section-status.tsv"
printf 'section\tcategory\tcommand_available\texit_status\tbytes\n' > "${status_file}"

record_section() {
  local section="$1" category="$2" available="$3" status="$4" bytes="$5"
  printf '%s\t%s\t%s\t%s\t%s\n' "${section}" "${category}" "${available}" "${status}" "${bytes}" >> "${status_file}"
}

command_available() {
  local command_name="$1"
  if [[ "${SAFE_INVENTORY_TEST_MODE:-}" == '1' && ",${SAFE_INVENTORY_TEST_MISSING_COMMANDS:-}," == *",${command_name},"* ]]; then
    return 1
  fi
  command -v "${command_name}" >/dev/null 2>&1
}

run_section() {
  local section="$1" category="$2" availability_command="$3"
  shift 3
  local output_file="${sections_dir}/${section}.txt" rc bytes
  if ! command_available "${availability_command}"; then
    printf 'command unavailable: %s\n' "${availability_command}" > "${output_file}"
    chmod 600 -- "${output_file}"
    record_section "${section}" "${category}" 'false' '127' "$(wc -c < "${output_file}")"
    return 0
  fi
  set +e
  timeout "${section_timeout_seconds}s" "$@" 2>&1 |
    safe_inventory_sanitize_stream |
    safe_inventory_cap_stream "${max_section_bytes}" > "${output_file}"
  rc=${PIPESTATUS[0]}
  set -e
  chmod 600 -- "${output_file}"
  bytes="$(wc -c < "${output_file}")"
  record_section "${section}" "${category}" 'true' "${rc}" "${bytes}"
}

run_section os_release os-metadata cat cat /etc/os-release
run_section kernel_arch_uptime os-metadata uname bash -c 'uname -srmo; uptime -p 2>/dev/null || true'
run_section cpu_memory hardware-summary bash bash -c 'lscpu 2>/dev/null || true; free -h 2>/dev/null || true'
run_section storage storage-summary bash bash -c 'lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS 2>/dev/null || true; df -hPT 2>/dev/null || true; findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null || true'
run_section packages packages dpkg-query dpkg-query -W '-f=${binary:Package}\t${Version}\n'
run_section enabled_units systemd systemctl systemctl list-unit-files --state=enabled --no-legend --no-pager
run_section failed_units systemd systemctl systemctl list-units --failed --no-legend --no-pager
run_section timers systemd systemctl systemctl list-timers --all --no-legend --no-pager
run_section docker_version docker docker docker version --format '{{.Server.Version}}'
run_section docker_containers docker docker docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
run_section compose_projects docker docker docker compose ls --format '{{.Name}}'
run_section docker_networks docker docker docker network ls --format '{{.Name}}\t{{.Driver}}'
run_section listening_sockets network ss ss -H -lntu
run_section kernel_warnings journal journalctl journalctl -k -b -p warning..alert --no-pager -n 200 -o short-iso
run_section failed_service_summary service-health systemctl systemctl list-units --failed --no-legend --no-pager
run_section backup_units service-health systemctl bash -c 'set -o pipefail; systemctl list-unit-files --type=service --type=timer --no-legend --no-pager 2>/dev/null | awk '\''tolower($1) ~ /(backup|borg|restic|rclone)/ { print $1 "\t" $2 }'\'''
run_section service_health service-health systemctl bash -c 'systemctl is-system-running; first=$?; systemctl list-units --failed --no-legend --no-pager; second=$?; [[ $first -eq 0 && $second -eq 0 ]]'
run_section repository_status repositories git bash -c '
  for repo in /home/andris/hermes-deals /home/andris/hermes-tech /home/andris/RPi5_main; do
    name=${repo##*/}
    if git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]; then state=dirty; else state=clean; fi
      printf "%s\t%s\n" "$name" "$state"
    else
      printf "%s\tmissing\n" "$name"
    fi
  done'
run_section network_interfaces network ip ip -brief address

commit_sha='unavailable'
if git -C "${repo_root}" rev-parse --verify HEAD >/dev/null 2>&1; then
  commit_sha="$(git -C "${repo_root}" rev-parse HEAD)"
fi
hostname_value="$(hostname 2>/dev/null || printf 'unavailable')"
architecture_value="$(uname -m 2>/dev/null || printf 'unavailable')"
collection_time="$(utc_now)"
section_count=0
nonzero_count=0
while IFS=$'\t' read -r section category available status bytes; do
  [[ "${section}" == 'section' ]] && continue
  section_count=$((section_count + 1))
  [[ "${status}" == '0' ]] || nonzero_count=$((nonzero_count + 1))
done < "${status_file}"

summary_file="${result_dir}/summary.json"
{
  printf '{\n'
  printf '  "collector_version": %s,\n' "$(safe_inventory_json_string "${collector_version}")"
  printf '  "git_commit": %s,\n' "$(safe_inventory_json_string "${commit_sha}")"
  printf '  "hostname": %s,\n' "$(safe_inventory_json_string "${hostname_value}")"
  printf '  "architecture": %s,\n' "$(safe_inventory_json_string "${architecture_value}")"
  printf '  "collected_at_utc": %s,\n' "$(safe_inventory_json_string "${collection_time}")"
  printf '  "sections_attempted": %s,\n' "${section_count}"
  printf '  "sections_with_nonzero_exit": %s,\n' "${nonzero_count}"
  printf '  "overall_result": "success",\n'
  printf '  "sections": [\n'
  row=0
  while IFS=$'\t' read -r section category available status bytes; do
    [[ "${section}" == 'section' ]] && continue
    row=$((row + 1))
    [[ "${available}" == 'true' ]] && json_available=true || json_available=false
    printf '    {"name":%s,"category":%s,"command_available":%s,"exit_status":%s,"bytes":%s}' \
      "$(safe_inventory_json_string "${section}")" \
      "$(safe_inventory_json_string "${category}")" \
      "${json_available}" "${status}" "${bytes}"
    [[ "${row}" -lt "${section_count}" ]] && printf ','
    printf '\n'
  done < "${status_file}"
  printf '  ]\n'
  printf '}\n'
} > "${summary_file}"
chmod 600 -- "${summary_file}" "${status_file}"

inventory_file="${result_dir}/file-inventory.txt"
(
  cd -- "${result_dir}"
  LC_ALL=C find . -type f ! -name 'SHA256SUMS' ! -name 'file-inventory.txt' -printf '%P\n' | LC_ALL=C sort
) > "${inventory_file}"
chmod 600 -- "${inventory_file}"
(
  cd -- "${result_dir}"
  LC_ALL=C find . -type f ! -name 'SHA256SUMS' -printf '%P\n' | LC_ALL=C sort |
    while IFS= read -r file; do sha256sum -- "${file}"; done
) > "${result_dir}/SHA256SUMS"
chmod 600 -- "${result_dir}/SHA256SUMS"

printf 'Inventory result: %s\n' "${result_dir}"
printf 'Overall result: success (%s sections; %s non-zero section exits recorded)\n' "${section_count}" "${nonzero_count}"
