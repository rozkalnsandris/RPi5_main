#!/usr/bin/env bash
# V02A: bounded, read-only least-privilege access-model diagnostic.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"
# shellcheck source=scripts/access-diagnostic-lib.sh
source "${script_dir}/access-diagnostic-lib.sh"

probe_timeout_seconds="${ACCESS_DIAGNOSTIC_TIMEOUT_SECONDS:-10}"
max_probe_bytes="${ACCESS_DIAGNOSTIC_MAX_PROBE_BYTES:-65536}"
max_total_bytes="${ACCESS_DIAGNOSTIC_MAX_TOTAL_BYTES:-524288}"

die() {
  printf 'diagnose-access-model: %s\n' "$*" >&2
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
access_valid_context "${context_label}" || die 'invalid context label'
[[ "$(access_effective_uid)" != '0' ]] || die 'refusing to run as root'
command -v timeout >/dev/null 2>&1 || die 'timeout is required'
[[ "${probe_timeout_seconds}" =~ ^[1-9][0-9]*$ && "${max_probe_bytes}" =~ ^[1-9][0-9]*$ && "${max_total_bytes}" =~ ^[1-9][0-9]*$ ]] || die 'invalid diagnostic limits'

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

collection_time="$(access_now_utc)"
timestamp_slug="${collection_time//:/-}"
result_dir="$(mktemp -d "${output_base}/v02a-${timestamp_slug}-XXXXXX")"
sections_dir="${result_dir}/sections"
mkdir -p -- "${sections_dir}"
chmod 700 -- "${result_dir}" "${sections_dir}"
status_file="${result_dir}/probe-status.tsv"
printf 'probe\tcommand_present\texit_code\tclassification\tbytes\tstarted_at_utc\tended_at_utc\tcontext\n' > "${status_file}"
total_bytes=0

record_probe() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "${status_file}"
}

run_probe() {
  local probe="$1" kind="$2" primary_command="$3"
  shift 3
  local output_file="${sections_dir}/${probe}.txt" present=true exit_code classification bytes started ended allowed_bytes
  started="$(access_now_utc)"
  if ! access_command_available "${primary_command}"; then
    present=false
    exit_code=127
    printf 'command unavailable: %s\n' "${primary_command}" > "${output_file}"
  elif (( total_bytes >= max_total_bytes )); then
    exit_code=125
    printf '%s\n' 'total diagnostic output limit reached' > "${output_file}"
  else
    allowed_bytes=$((max_total_bytes - total_bytes))
    (( allowed_bytes > max_probe_bytes )) && allowed_bytes=${max_probe_bytes}
    set +e
    timeout "${probe_timeout_seconds}s" "$@" 2>&1 |
      safe_inventory_sanitize_stream |
      safe_inventory_cap_stream "${allowed_bytes}" > "${output_file}"
    exit_code=${PIPESTATUS[0]}
    set -e
  fi
  chmod 600 -- "${output_file}"
  bytes="$(wc -c < "${output_file}")"
  total_bytes=$((total_bytes + bytes))
  classification="$(access_classify "${kind}" "${exit_code}" "${output_file}")"
  ended="$(access_now_utc)"
  record_probe "${probe}" "${present}" "${exit_code}" "${classification}" "${bytes}" "${started}" "${ended}" "${context_label}"
}

run_compose_projects_probe() {
  local probe='docker_compose_projects' output_file="${sections_dir}/docker_compose_projects.txt" present=true exit_code classification bytes started ended allowed_bytes
  started="$(access_now_utc)"
  if ! access_command_available docker; then
    present=false
    exit_code=127
    printf '%s\n' 'command unavailable: docker' > "${output_file}"
  elif (( total_bytes >= max_total_bytes )); then
    exit_code=125
    printf '%s\n' 'total diagnostic output limit reached' > "${output_file}"
  else
    allowed_bytes=$((max_total_bytes - total_bytes))
    (( allowed_bytes > max_probe_bytes )) && allowed_bytes=${max_probe_bytes}
    set +e
    timeout "${probe_timeout_seconds}s" docker compose ls --format '{{.Name}}\t{{.Status}}' 2>&1 |
      access_compose_projection |
      safe_inventory_sanitize_stream |
      safe_inventory_cap_stream "${allowed_bytes}" > "${output_file}"
    exit_code=${PIPESTATUS[0]}
    format_classification="$(access_classify docker "${exit_code}" "${output_file}")"
    if [[ "${format_classification}" == unsupported_syntax ]] && access_command_available python3; then
      set +e
      timeout "${probe_timeout_seconds}s" docker compose ls --format json 2>&1 |
        access_compose_json_projection |
        safe_inventory_sanitize_stream |
        safe_inventory_cap_stream "${allowed_bytes}" > "${output_file}"
      exit_code=${PIPESTATUS[0]}
      set -e
    fi
    set -e
  fi
  chmod 600 -- "${output_file}"
  bytes="$(wc -c < "${output_file}")"
  total_bytes=$((total_bytes + bytes))
  classification="$(access_classify docker "${exit_code}" "${output_file}")"
  ended="$(access_now_utc)"
  record_probe "${probe}" "${present}" "${exit_code}" "${classification}" "${bytes}" "${started}" "${ended}" "${context_label}"
}

run_probe execution_identity context id bash -c 'printf "uid=%s\nuser=%s\nprimary_group=%s\ngroups=%s\n" "$(id -u)" "$(id -un)" "$(id -gn)" "$(id -Gn)"'
run_probe command_availability context bash bash -c '
  for command_name in docker systemctl ss ip stat namei readlink timeout python3; do
    if command -v "$command_name" >/dev/null 2>&1; then
      printf "%s\tpresent=true\tpath=%s\n" "$command_name" "$(command -v "$command_name")"
    else
      printf "%s\tpresent=false\n" "$command_name"
    fi
  done'
run_probe environment_presence context bash bash -c '
  for variable_name in DOCKER_HOST DOCKER_CONTEXT CONTAINER_HOST DBUS_SYSTEM_BUS_ADDRESS XDG_RUNTIME_DIR SYSTEMD_OFFLINE GH_TOKEN GITHUB_TOKEN GH_CONFIG_DIR; do
    if [[ -v "$variable_name" ]]; then printf "%s\tpresent=true\n" "$variable_name"; else printf "%s\tpresent=false\n" "$variable_name"; fi
  done'
run_probe namespaces context readlink bash -c 'for namespace_path in /proc/self/ns/user /proc/self/ns/mnt /proc/self/ns/pid /proc/self/ns/net; do printf "%s=" "${namespace_path##*/}"; readlink "$namespace_path"; done'

run_probe docker_client_version docker docker docker --version
run_probe docker_compose_version docker docker docker compose version
run_probe docker_context_show docker docker docker context show
run_probe docker_socket_metadata docker stat bash -c 'if [[ -e /run/docker.sock || -S /run/docker.sock ]]; then stat -c "type=%F mode=%a owner=%U group=%G" /run/docker.sock; else printf "socket_absent\n"; exit 3; fi'
run_probe docker_socket_path_permissions docker namei bash -c 'if [[ -e /run/docker.sock || -S /run/docker.sock ]]; then namei -l /run/docker.sock; else printf "socket_absent\n"; exit 3; fi'
run_probe docker_socket_access docker stat bash -c '
  if [[ ! -S /run/docker.sock ]]; then printf "socket_present=false\n"; exit 3; fi
  socket_group="$(stat -c %G /run/docker.sock)"
  group_member=false
  for group_name in $(id -Gn); do [[ "$group_name" == "$socket_group" ]] && group_member=true; done
  [[ -r /run/docker.sock ]] && readable=true || readable=false
  [[ -w /run/docker.sock ]] && writable=true || writable=false
  printf "socket_present=true\treadable=%s\twritable=%s\tsocket_group_member=%s\n" "$readable" "$writable" "$group_member"'
run_probe docker_server_version docker docker docker version --format '{{.Server.Version}}'
run_probe docker_ps_projection docker docker docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
run_probe docker_network_projection docker docker docker network ls --format '{{.Name}}\t{{.Driver}}'
run_compose_projects_probe

run_probe systemctl_version systemd systemctl systemctl --version
run_probe systemd_private_metadata systemd stat bash -c 'if [[ -e /run/systemd/private || -S /run/systemd/private ]]; then stat -c "type=%F mode=%a owner=%U group=%G" /run/systemd/private; else printf "socket_absent\n"; exit 3; fi'
run_probe systemd_private_path_permissions systemd namei bash -c 'if [[ -e /run/systemd/private || -S /run/systemd/private ]]; then namei -l /run/systemd/private; else printf "socket_absent\n"; exit 3; fi'
run_probe dbus_system_socket_metadata systemd stat bash -c 'if [[ -e /run/dbus/system_bus_socket || -S /run/dbus/system_bus_socket ]]; then stat -c "type=%F mode=%a owner=%U group=%G" /run/dbus/system_bus_socket; else printf "socket_absent\n"; exit 3; fi'
run_probe dbus_system_socket_path_permissions systemd namei bash -c 'if [[ -e /run/dbus/system_bus_socket || -S /run/dbus/system_bus_socket ]]; then namei -l /run/dbus/system_bus_socket; else printf "socket_absent\n"; exit 3; fi'
run_probe system_running systemd systemctl systemctl --system is-system-running
run_probe enabled_unit_names systemd systemctl systemctl --system list-unit-files --state=enabled --type=service --type=timer --no-legend --no-pager
run_probe failed_unit_names systemd systemctl systemctl --system list-units --failed --no-legend --no-pager
run_probe system_timers systemd systemctl systemctl --system list-timers --all --no-legend --no-pager
run_probe user_system_running systemd systemctl systemctl --user is-system-running

run_probe network_binary_metadata network stat bash -c '
  for command_name in ss ip; do
    if command -v "$command_name" >/dev/null 2>&1; then
      command_path="$(command -v "$command_name")"
      printf "%s\tpath=%s\t" "$command_name" "$command_path"
      stat -c "mode=%a owner=%U group=%G" "$command_path"
    else
      printf "%s\tpresent=false\n" "$command_name"
    fi
  done'
run_probe ss_listening network ss ss -H -lntu
run_probe ip_brief_address network ip ip -brief address

commit_sha='unavailable'
if git -C "${repo_root}" rev-parse --verify HEAD >/dev/null 2>&1; then commit_sha="$(git -C "${repo_root}" rev-parse HEAD)"; fi
probe_count=0
nonzero_count=0
while IFS=$'\t' read -r probe present exit_code classification bytes started ended context; do
  [[ "${probe}" == probe ]] && continue
  probe_count=$((probe_count + 1))
  [[ "${exit_code}" == '0' ]] || nonzero_count=$((nonzero_count + 1))
done < "${status_file}"

class_for() {
  awk -F '\t' -v wanted="$1" '$1 == wanted {print $4}' "${status_file}"
}
socket_member=false
if [[ -f "${sections_dir}/docker_socket_access.txt" ]] && grep -q 'socket_group_member=true' "${sections_dir}/docker_socket_access.txt"; then socket_member=true; fi
docker_problem=false
systemd_problem=false
network_problem=false
compose_unsupported=false
docker_user_missing=false
for probe_name in docker_server_version docker_ps_projection docker_network_projection docker_compose_projects; do
  probe_class="$(class_for "${probe_name}")"
  [[ "${probe_class}" == success || "${probe_class}" == command_missing || "${probe_class}" == service_absent ]] || docker_problem=true
  [[ "${probe_class}" == unsupported_syntax ]] && compose_unsupported=true
  [[ "${probe_class}" == permission_denied && "${socket_member}" == false ]] && docker_user_missing=true
done
for probe_name in system_running enabled_unit_names failed_unit_names system_timers; do
  [[ "$(class_for "${probe_name}")" == system_bus_unreachable ]] && systemd_problem=true
done
for probe_name in ss_listening ip_brief_address; do
  [[ "$(class_for "${probe_name}")" == restricted_or_not_permitted ]] && network_problem=true
done
evidence_codes=()
[[ "${docker_user_missing}" == true ]] && evidence_codes+=(docker_socket_group_membership_false docker_permission_denied)
[[ "$(class_for docker_server_version)" == daemon_unreachable ]] && evidence_codes+=(docker_daemon_unreachable)
[[ "${systemd_problem}" == true ]] && evidence_codes+=(systemd_system_bus_unreachable)
[[ "${network_problem}" == true ]] && evidence_codes+=(network_probe_not_permitted)
[[ "${compose_unsupported}" == true ]] && evidence_codes+=(compose_format_unsupported)
[[ "$(class_for docker_client_version)" == command_missing ]] && evidence_codes+=(docker_command_missing)
[[ "$(class_for systemctl_version)" == command_missing ]] && evidence_codes+=(systemctl_command_missing)
[[ "$(class_for ss_listening)" == command_missing ]] && evidence_codes+=(ss_command_missing)
[[ "$(class_for ip_brief_address)" == command_missing ]] && evidence_codes+=(ip_command_missing)
if [[ "${docker_user_missing}" == true && "${systemd_problem}" == false && "${network_problem}" == false ]]; then
  decision=docker_user_access_missing
elif [[ "$(class_for docker_server_version)" == daemon_unreachable && "${systemd_problem}" == false && "${network_problem}" == false ]]; then
  decision=docker_daemon_unreachable
elif [[ "${systemd_problem}" == true && "${docker_problem}" == false && "${network_problem}" == false ]]; then
  decision=systemd_bus_access_issue
elif [[ "${compose_unsupported}" == true && "${docker_problem}" == false && "${systemd_problem}" == false && "${network_problem}" == false ]]; then
  decision=command_compatibility_issue
elif [[ "${docker_problem}" == false && "${systemd_problem}" == false && "${network_problem}" == false ]]; then
  decision=no_access_change_needed
elif [[ "${docker_problem}" == true && "${systemd_problem}" == true || "${network_problem}" == true ]]; then
  decision=mixed
else
  decision=inconclusive
fi

summary_file="${result_dir}/summary.json"
{
  printf '{\n'
  printf '  "diagnostic_version": %s,\n' "$(safe_inventory_json_string "${access_diagnostic_version}")"
  printf '  "git_commit": %s,\n' "$(safe_inventory_json_string "${commit_sha}")"
  printf '  "context": %s,\n' "$(safe_inventory_json_string "${context_label}")"
  printf '  "collected_at_utc": %s,\n' "$(safe_inventory_json_string "${collection_time}")"
  printf '  "probes_attempted": %s,\n' "${probe_count}"
  printf '  "probes_with_nonzero_exit": %s,\n' "${nonzero_count}"
  printf '  "overall_result": "success"\n'
  printf '}\n'
} > "${summary_file}"
decision_file="${result_dir}/decision.json"
{
  printf '{\n'
  printf '  "context": %s,\n' "$(safe_inventory_json_string "${context_label}")"
  printf '  "decision": %s,\n' "$(safe_inventory_json_string "${decision}")"
  printf '  "comparison_performed": false,\n'
  printf '  "evidence_codes": ['
  for index in "${!evidence_codes[@]}"; do
    (( index > 0 )) && printf ','
    safe_inventory_json_string "${evidence_codes[${index}]}"
  done
  printf ']\n}\n'
} > "${decision_file}"
chmod 600 -- "${summary_file}" "${decision_file}" "${status_file}"

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

printf 'Access diagnostic result: %s\n' "${result_dir}"
printf 'Access diagnostic outcome: %s (%s probes; %s non-zero exits)\n' "${decision}" "${probe_count}" "${nonzero_count}"
