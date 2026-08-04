#!/usr/bin/env bash
# Collect a bounded V02B runtime baseline evidence bundle. Read-only only.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"
# shellcheck source=scripts/access-diagnostic-lib.sh
source "${script_dir}/access-diagnostic-lib.sh"
# shellcheck source=scripts/runtime-baseline-lib.sh
source "${script_dir}/runtime-baseline-lib.sh"

section_timeout_seconds="${RUNTIME_BASELINE_TIMEOUT_SECONDS:-10}"
max_section_bytes="${RUNTIME_BASELINE_MAX_SECTION_BYTES:-65536}"
max_total_bytes="${RUNTIME_BASELINE_MAX_TOTAL_BYTES:-524288}"

die() {
  printf 'collect-runtime-baseline: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'Usage: %s --output DIR --context LABEL\n' "${0##*/}" >&2
}

if [[ $# -ne 4 || "$1" != '--output' || "$3" != '--context' || -z "${2:-}" || -z "${4:-}" ]]; then
  usage
  exit 2
fi
output_arg="$2"
context_label="$4"
runtime_valid_context "${context_label}" || die 'invalid context label'
[[ "$(runtime_effective_uid)" != '0' ]] || die 'refusing to run as root'
runtime_command_available timeout || die 'timeout is required'
runtime_command_available python3 || die 'python3 is required for fixed projections'
[[ "${section_timeout_seconds}" =~ ^[1-9][0-9]*$ && "${max_section_bytes}" =~ ^[1-9][0-9]*$ && "${max_total_bytes}" =~ ^[1-9][0-9]*$ ]] || die 'invalid collector limits'

if [[ "${output_arg}" == /* ]]; then requested_absolute="${output_arg}"; else requested_absolute="$(pwd -P)/${output_arg}"; fi
access_path_has_symlink_component "${requested_absolute}" && die 'refusing output path with a symlink component'
output_base="$(realpath -m -- "${requested_absolute}")"
case "${output_base}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) die 'output directory must resolve below repository evidence/ or exports/' ;;
esac
[[ ! -e "${output_base}" || -d "${output_base}" ]] || die 'output path is not a directory'
umask 077
mkdir -p -- "${output_base}"
access_path_has_symlink_component "${output_base}" && die 'refusing output path with a symlink component'

collection_time="$(runtime_now_utc)"
result_dir="$(mktemp -d "${output_base}/v02b-${collection_time//:/-}-XXXXXX")"
sections_dir="${result_dir}/sections"
mkdir -p -- "${sections_dir}"
chmod 700 -- "${result_dir}" "${sections_dir}"
status_file="${result_dir}/section-status.tsv"
printf 'section\tcommand_present\texit_code\tclassification\tbytes\tstarted_at_utc\tended_at_utc\tcontext\n' > "${status_file}"

total_bytes=0
declare -A section_classification=()
declare -A section_exit_code=()
declare -A section_present=()
declare -A section_bytes=()

record_section() {
  local section="$1" present="$2" exit_code="$3" classification="$4" bytes="$5" started="$6" ended="$7"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${section}" "${present}" "${exit_code}" "${classification}" "${bytes}" "${started}" "${ended}" "${context_label}" >> "${status_file}"
  section_classification["${section}"]="${classification}"
  section_exit_code["${section}"]="${exit_code}"
  section_present["${section}"]="${present}"
  section_bytes["${section}"]="${bytes}"
}

strip_marker() {
  local file="$1" clean_file
  clean_file="${file}.clean"
  awk '/^__runtime_error=/{next} {print}' "${file}" > "${clean_file}"
  mv -- "${clean_file}" "${file}"
}

execute_projection() {
  local output_file="$1" kind="$2" primary_command="$3" parser_mode="$4"
  shift 4
  runtime_present=true
  runtime_exit_code=0
  runtime_classification=success
  if ! runtime_command_available "${primary_command}"; then
    runtime_present=false
    runtime_exit_code=127
    : > "${output_file}"
  elif (( total_bytes >= max_total_bytes )); then
    runtime_exit_code=125
    : > "${output_file}"
  else
    local available_bytes=$((max_total_bytes - total_bytes))
    (( available_bytes > max_section_bytes )) && available_bytes=${max_section_bytes}
    set +e
    LC_ALL=C timeout "${section_timeout_seconds}s" "$@" 2>&1 |
      LC_ALL=C python3 "${script_dir}/runtime-baseline-parser.py" "${parser_mode}" |
      safe_inventory_cap_stream "${available_bytes}" > "${output_file}"
    runtime_exit_code=${PIPESTATUS[0]}
    set -e
  fi
  runtime_classification="$(runtime_classify "${kind}" "${runtime_exit_code}" "${output_file}")"
  strip_marker "${output_file}"
  chmod 600 -- "${output_file}"
  runtime_bytes="$(wc -c < "${output_file}")"
}

run_section() {
  local section="$1" kind="$2" primary_command="$3" parser_mode="$4"
  shift 4
  local output_file="${sections_dir}/${section}.txt" started ended
  started="$(runtime_now_utc)"
  execute_projection "${output_file}" "${kind}" "${primary_command}" "${parser_mode}" "$@"
  total_bytes=$((total_bytes + runtime_bytes))
  ended="$(runtime_now_utc)"
  record_section "${section}" "${runtime_present}" "${runtime_exit_code}" "${runtime_classification}" "${runtime_bytes}" "${started}" "${ended}"
}

run_compose_projects() {
  local section='docker_compose_projects' output_file="${sections_dir}/docker_compose_projects.txt" started ended first_bytes
  started="$(runtime_now_utc)"
  execute_projection "${output_file}" docker docker compose-json docker compose ls --format json
  first_bytes="${runtime_bytes}"
  if [[ "${runtime_classification}" == unsupported_syntax ]]; then
    # Fixed compatibility projection: no user-controlled arguments or raw fields.
    execute_projection "${output_file}" docker docker compose-fallback docker compose ls --format '{{.Name}}\t{{.Status}}'
  fi
  total_bytes=$((total_bytes + runtime_bytes))
  ended="$(runtime_now_utc)"
  record_section "${section}" "${runtime_present}" "${runtime_exit_code}" "${runtime_classification}" "${runtime_bytes}" "${started}" "${ended}"
}

run_systemd_timers() {
  local section='systemd_timers' output_file="${sections_dir}/systemd_timers.txt" temporary_file started ended
  local present=true exit_code=0 classification=success bytes timer_name one_file one_exit one_class
  started="$(runtime_now_utc)"
  : > "${output_file}"
  if ! runtime_command_available systemctl; then
    present=false
    exit_code=127
    : > "${output_file}"
    classification=command_missing
  elif [[ "${section_classification[systemd_timer_units]:-other_error}" != success ]]; then
    exit_code="${section_exit_code[systemd_timer_units]:-1}"
    classification="${section_classification[systemd_timer_units]:-other_error}"
  else
    temporary_file="$(mktemp "${result_dir}/.timer-projection.XXXXXX")"
    chmod 600 -- "${temporary_file}"
    while IFS=$'\t' read -r timer_name timer_state; do
      [[ "${timer_name}" =~ ^[A-Za-z0-9@_.:-]{1,128}\.timer$ ]] || continue
      one_file="${temporary_file}.${timer_name//[^A-Za-z0-9_.-]/_}"
      set +e
      LC_ALL=C timeout "${section_timeout_seconds}s" systemctl --system show "${timer_name}" --no-pager \
        --property=Id --property=LoadState --property=ActiveState --property=SubState --property=Unit \
        --property=NextElapseUSecRealtime --property=LastTriggerUSec 2>&1 |
        LC_ALL=C python3 "${script_dir}/runtime-baseline-parser.py" timer-properties "${timer_name}" |
        safe_inventory_cap_stream "${max_section_bytes}" > "${one_file}"
      one_exit=${PIPESTATUS[0]}
      set -e
      one_class="$(runtime_classify systemd "${one_exit}" "${one_file}")"
      strip_marker "${one_file}"
      if [[ "${one_exit}" != 0 && "${exit_code}" == 0 ]]; then
        exit_code="${one_exit}"
        classification="${one_class}"
      fi
      cat -- "${one_file}" >> "${temporary_file}"
      rm -f -- "${one_file}"
    done < "${sections_dir}/systemd_timer_units.txt"
    LC_ALL=C sort -u "${temporary_file}" | safe_inventory_cap_stream "${max_section_bytes}" > "${output_file}"
    rm -f -- "${temporary_file}"
  fi
  chmod 600 -- "${output_file}"
  bytes="$(wc -c < "${output_file}")"
  total_bytes=$((total_bytes + bytes))
  ended="$(runtime_now_utc)"
  record_section "${section}" "${present}" "${exit_code}" "${classification}" "${bytes}" "${started}" "${ended}"
}

run_section docker_engine_version docker docker docker-version docker version --format '{{.Server.Version}}'
run_section docker_compose_version docker docker compose-version docker compose version
run_section docker_containers docker docker containers docker ps --all --format '{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}'
run_section docker_networks docker docker networks docker network ls --format '{{.Name}}\t{{.Driver}}\t{{.Scope}}'
run_compose_projects

run_section systemd_system_state systemd systemctl system-state systemctl --system is-system-running
if [[ "${section_classification[systemd_system_state]}" != success ]] && awk -F '\t' '$1 == "state" && $2 ~ /^(degraded|maintenance|starting|stopping|initializing|offline|unknown)$/ { found=1 } END { exit(found ? 0 : 1) }' "${sections_dir}/systemd_system_state.txt"; then
  section_classification[systemd_system_state]=success_degraded
  awk -F '\t' -v section='systemd_system_state' -v class='success_degraded' 'BEGIN { OFS="\t" } NR == 1 { print; next } $1 == section { $4=class } { print }' "${status_file}" > "${status_file}.new"
  mv -- "${status_file}.new" "${status_file}"
fi
run_section systemd_enabled_units systemd systemctl enabled-units systemctl --system list-unit-files --state=enabled --type=service --type=timer --no-legend --no-pager
run_section systemd_failed_units systemd systemctl failed-units systemctl --system list-units --failed --no-legend --no-pager
run_section systemd_timer_units systemd systemctl timer-units systemctl --system list-unit-files --type=timer --no-legend --no-pager
run_systemd_timers

run_section listening_sockets network ss sockets ss -H -lntu
run_section network_interfaces network ip interfaces-json ip -j address show
if [[ "${section_classification[network_interfaces]}" == unsupported_syntax ]]; then
  # Fixed fallback only; raw addresses are still projected in-memory then discarded.
  output_file="${sections_dir}/network_interfaces.txt"
  old_bytes="${section_bytes[network_interfaces]}"
  total_bytes=$((total_bytes - old_bytes))
  started="$(runtime_now_utc)"
  execute_projection "${output_file}" network ip interfaces-fallback ip -brief address
  total_bytes=$((total_bytes + runtime_bytes))
  ended="$(runtime_now_utc)"
  awk -F '\t' -v section='network_interfaces' -v present="${runtime_present}" -v exit_code="${runtime_exit_code}" -v class="${runtime_classification}" -v bytes="${runtime_bytes}" -v started="${started}" -v ended="${ended}" 'BEGIN { OFS="\t" } NR == 1 { print; next } $1 == section { print section,present,exit_code,class,bytes,started,ended,$8; next } { print }' "${status_file}" > "${status_file}.new"
  mv -- "${status_file}.new" "${status_file}"
  section_classification[network_interfaces]="${runtime_classification}"
  section_exit_code[network_interfaces]="${runtime_exit_code}"
  section_present[network_interfaces]="${runtime_present}"
  section_bytes[network_interfaces]="${runtime_bytes}"
fi

commit_sha='unavailable'
if git -C "${repo_root}" rev-parse --verify HEAD >/dev/null 2>&1; then
  commit_sha="$(git -C "${repo_root}" rev-parse HEAD)"
fi
section_count=0
nonzero_count=0
while IFS=$'\t' read -r section present exit_code classification bytes started ended context; do
  [[ "${section}" == section ]] && continue
  section_count=$((section_count + 1))
  [[ "${exit_code}" == 0 ]] || nonzero_count=$((nonzero_count + 1))
done < "${status_file}"
[[ "${section_count}" == 12 ]] || die 'collector section integrity failure'

summary_file="${result_dir}/summary.json"
{
  printf '{\n'
  printf '  "collector_version": %s,\n' "$(safe_inventory_json_string "${runtime_baseline_version}")"
  printf '  "git_commit": %s,\n' "$(safe_inventory_json_string "${commit_sha}")"
  printf '  "context": %s,\n' "$(safe_inventory_json_string "${context_label}")"
  printf '  "collected_at_utc": %s,\n' "$(safe_inventory_json_string "${collection_time}")"
  printf '  "sections_attempted": %s,\n' "${section_count}"
  printf '  "sections_with_nonzero_exit": %s,\n' "${nonzero_count}"
  printf '  "overall_result": "success"\n'
  printf '}\n'
} > "${summary_file}"
chmod 600 -- "${summary_file}" "${status_file}"

inventory_file="${result_dir}/file-inventory.txt"
(
  cd -- "${result_dir}"
  LC_ALL=C find . -type f ! -name SHA256SUMS ! -name file-inventory.txt -printf '%P\n' | LC_ALL=C sort
) > "${inventory_file}"
chmod 600 -- "${inventory_file}"
(
  cd -- "${result_dir}"
  LC_ALL=C find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort |
    while IFS= read -r file; do sha256sum -- "${file}"; done
) > "${result_dir}/SHA256SUMS"
chmod 600 -- "${result_dir}/SHA256SUMS"

printf 'Runtime baseline result: %s\n' "${result_dir}"
printf 'Runtime baseline outcome: success (%s sections; %s non-zero exits)\n' "${section_count}" "${nonzero_count}"
