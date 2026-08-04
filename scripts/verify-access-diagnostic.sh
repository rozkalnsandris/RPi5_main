#!/usr/bin/env bash
# Verify a V02A access-model diagnostic without exposing stored values.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"
# shellcheck source=scripts/access-diagnostic-lib.sh
source "${script_dir}/access-diagnostic-lib.sh"

max_file_bytes="${ACCESS_DIAGNOSTIC_VERIFY_MAX_FILE_BYTES:-65536}"
max_total_bytes="${ACCESS_DIAGNOSTIC_VERIFY_MAX_TOTAL_BYTES:-1048576}"
max_files="${ACCESS_DIAGNOSTIC_VERIFY_MAX_FILES:-64}"
allowed_probes='execution_identity command_availability environment_presence namespaces docker_client_version docker_compose_version docker_context_show docker_socket_metadata docker_socket_path_permissions docker_socket_access docker_server_version docker_ps_projection docker_network_projection docker_compose_projects systemctl_version systemd_private_metadata systemd_private_path_permissions dbus_system_socket_metadata dbus_system_socket_path_permissions system_running enabled_unit_names failed_unit_names system_timers user_system_running network_binary_metadata ss_listening ip_brief_address'

fail() {
  printf 'Access diagnostic verification: FAIL: %s\n' "$*" >&2
  exit 1
}

is_allowed_probe() {
  [[ " ${allowed_probes} " == *" $1 "* ]]
}

if [[ $# -ne 1 ]]; then fail 'expected exactly one result directory'; fi
[[ "${max_file_bytes}" =~ ^[1-9][0-9]*$ && "${max_total_bytes}" =~ ^[1-9][0-9]*$ && "${max_files}" =~ ^[1-9][0-9]*$ ]] || fail 'invalid verifier limits'
[[ -d "$1" && ! -L "$1" ]] || fail 'result target is not a regular directory'
if [[ "$1" == /* ]]; then requested_absolute="$1"; else requested_absolute="$(pwd -P)/$1"; fi
if access_path_has_symlink_component "${requested_absolute}"; then fail 'symlink path component rejected'; fi
result_dir="$(realpath -e -- "$1")"
case "${result_dir}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) fail 'result path is outside repository evidence/export area' ;;
esac
for required in summary.json probe-status.tsv decision.json file-inventory.txt SHA256SUMS sections; do
  [[ -e "${result_dir}/${required}" ]] || fail 'required result structure is missing'
done
[[ -d "${result_dir}/sections" && ! -L "${result_dir}/sections" ]] || fail 'sections directory is invalid'

if find "${result_dir}" -type l -print -quit | grep -q .; then fail 'symlink artifact rejected'; fi
if find "${result_dir}" \( -type b -o -type c -o -type p -o -type s \) -print -quit | grep -q .; then fail 'non-regular artifact rejected'; fi
if find "${result_dir}" -type f -links +1 -print -quit | grep -q .; then fail 'hard-linked file rejected'; fi
if find "${result_dir}" -perm -0002 -print -quit | grep -q .; then fail 'world-writable artifact rejected'; fi
if find "${result_dir}" -not -uid "$(id -u)" -print -quit | grep -q .; then fail 'unexpected artifact owner'; fi

file_count="$(find "${result_dir}" -type f | wc -l)"
(( file_count <= max_files )) || fail 'file-count limit exceeded'
total_bytes=0
while IFS= read -r -d '' file; do
  size="$(wc -c < "${file}")"
  (( size <= max_file_bytes )) || fail 'per-file size limit exceeded'
  total_bytes=$((total_bytes + size))
  case "$(basename -- "${file}")" in
    .env*|*.pem|*.key|*.p12|*.pfx|id_rsa*|id_ed25519*|authorized_keys|cert.json) fail 'forbidden file name rejected' ;;
  esac
  if safe_inventory_file_has_obvious_secret "${file}"; then fail 'secret-like content rejected'; fi
  if grep -Eqi 'configfiles|(^|[[:space:]])(DOCKER_HOST|DOCKER_CONTEXT|CONTAINER_HOST|DBUS_SYSTEM_BUS_ADDRESS|XDG_RUNTIME_DIR|SYSTEMD_OFFLINE|GH_TOKEN|GITHUB_TOKEN|GH_CONFIG_DIR)[[:space:]]*=' "${file}"; then
    fail 'forbidden raw field rejected'
  fi
done < <(find "${result_dir}" -type f -print0)
(( total_bytes <= max_total_bytes )) || fail 'total-size limit exceeded'

declare -A expected_sections=()
status_context=''
status_rows=0
while IFS=$'\t' read -r probe present exit_code classification bytes started ended context extra; do
  if [[ "${probe}" == probe ]]; then
    [[ "${present}" == command_present && "${exit_code}" == exit_code && "${classification}" == classification && "${bytes}" == bytes && "${started}" == started_at_utc && "${ended}" == ended_at_utc && "${context}" == context && -z "${extra}" ]] || fail 'invalid probe-status header'
    continue
  fi
  is_allowed_probe "${probe}" || fail 'unknown probe rejected'
  [[ "${present}" == true || "${present}" == false ]] || fail 'invalid command presence'
  [[ "${exit_code}" =~ ^[0-9]+$ && "${bytes}" =~ ^[0-9]+$ ]] || fail 'missing numeric probe metadata'
  access_is_allowed_classification "${classification}" || fail 'unknown classification rejected'
  access_valid_context "${context}" || fail 'invalid context label'
  [[ -z "${status_context}" || "${status_context}" == "${context}" ]] || fail 'mixed context labels rejected'
  status_context="${context}"
  [[ -f "${result_dir}/sections/${probe}.txt" ]] || fail 'probe output missing'
  [[ "$(wc -c < "${result_dir}/sections/${probe}.txt")" == "${bytes}" ]] || fail 'probe byte count mismatch'
  expected_sections["${probe}.txt"]=1
  status_rows=$((status_rows + 1))
done < "${result_dir}/probe-status.tsv"
(( status_rows == 27 )) || fail 'unexpected attempted-probe count'
while IFS= read -r -d '' section_file; do
  section_name="$(basename -- "${section_file}")"
  [[ -n "${expected_sections[${section_name}]:-}" ]] || fail 'unexpected probe output'
done < <(find "${result_dir}/sections" -maxdepth 1 -type f -print0)

if ! awk -F '\t' '
  BEGIN { split("DOCKER_HOST DOCKER_CONTEXT CONTAINER_HOST DBUS_SYSTEM_BUS_ADDRESS XDG_RUNTIME_DIR SYSTEMD_OFFLINE GH_TOKEN GITHUB_TOKEN GH_CONFIG_DIR", names, " "); for (i in names) allowed[names[i]]=1 }
  NF != 2 || !($1 in allowed) || ($2 != "present=true" && $2 != "present=false") { bad=1 }
  { seen[$1]=1 }
  END { for (name in allowed) if (!seen[name]) bad=1; exit(bad ? 1 : 0) }
' "${result_dir}/sections/environment_presence.txt"; then
  fail 'environment presence schema rejected'
fi
if ! awk -F '=' '
  BEGIN { allowed["uid"]=1; allowed["user"]=1; allowed["primary_group"]=1; allowed["groups"]=1 }
  NF != 2 || !($1 in allowed) || $2 == "" { bad=1 }
  { seen[$1]=1 }
  END { for (name in allowed) if (!seen[name]) bad=1; exit(bad ? 1 : 0) }
' "${result_dir}/sections/execution_identity.txt"; then
  fail 'execution identity schema rejected'
fi

command -v python3 >/dev/null 2>&1 || fail 'python3 is required to validate JSON'
if ! python3 -c 'import json,sys; s=json.load(open(sys.argv[1],encoding="utf-8")); d=json.load(open(sys.argv[2],encoding="utf-8")); assert s["diagnostic_version"] == "v02a.0.0"; assert s["context"] == d["context"]; assert s["overall_result"] == "success"; assert isinstance(s["probes_attempted"],int); assert isinstance(s["probes_with_nonzero_exit"],int); assert d["decision"] in {"no_access_change_needed","likely_execution_context_difference","docker_user_access_missing","docker_daemon_unreachable","systemd_bus_access_issue","command_compatibility_issue","mixed","inconclusive"}; assert isinstance(d["evidence_codes"],list); assert d["comparison_performed"] is False' "${result_dir}/summary.json" "${result_dir}/decision.json"; then
  fail 'invalid summary or decision JSON'
fi
[[ "${status_context}" == "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["context"])' "${result_dir}/summary.json")" ]] || fail 'summary context mismatch'
grep -q '^sections/' "${result_dir}/file-inventory.txt" || fail 'file inventory missing sections'

manifest_entries="$(wc -l < "${result_dir}/SHA256SUMS")"
(( manifest_entries > 0 )) || fail 'checksum manifest is empty'
if ! (cd -- "${result_dir}" && sha256sum -c --status SHA256SUMS); then fail 'checksum verification failed'; fi
actual_manifest_files="$(find "${result_dir}" -type f ! -name SHA256SUMS | wc -l)"
(( manifest_entries == actual_manifest_files )) || fail 'checksum manifest does not cover every file'

printf 'Access diagnostic verification: PASS (%s files, %s bytes, context=%s)\n' "${file_count}" "${total_bytes}" "${status_context}"
