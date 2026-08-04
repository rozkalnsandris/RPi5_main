#!/usr/bin/env bash
# Shared, source-only helpers for the V02A access-model diagnostic.

access_diagnostic_version='v02a.0.0'
access_allowed_classifications='success command_missing permission_denied daemon_unreachable system_bus_unreachable unsupported_syntax timeout restricted_or_not_permitted service_absent not_applicable other_error'
access_allowed_decisions='no_access_change_needed likely_execution_context_difference docker_user_access_missing docker_daemon_unreachable systemd_bus_access_issue command_compatibility_issue mixed inconclusive'

access_now_utc() {
  if [[ "${ACCESS_DIAGNOSTIC_TEST_MODE:-}" == '1' && -n "${ACCESS_DIAGNOSTIC_FIXED_UTC:-}" ]]; then
    printf '%s\n' "${ACCESS_DIAGNOSTIC_FIXED_UTC}"
  else
    date -u '+%Y-%m-%dT%H:%M:%SZ'
  fi
}

access_effective_uid() {
  if [[ "${ACCESS_DIAGNOSTIC_TEST_MODE:-}" == '1' && -n "${ACCESS_DIAGNOSTIC_TEST_UID:-}" ]]; then
    printf '%s\n' "${ACCESS_DIAGNOSTIC_TEST_UID}"
  else
    id -u
  fi
}

access_valid_context() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$ ]]
}

access_path_has_symlink_component() {
  local absolute_path="$1" component cursor='/'
  local -a parts=()
  IFS='/' read -r -a parts <<< "${absolute_path}"
  for component in "${parts[@]}"; do
    case "${component}" in
      ''|'.') ;;
      '..') cursor="$(dirname -- "${cursor}")" ;;
      *)
        if [[ "${cursor}" == '/' ]]; then cursor="/${component}"; else cursor="${cursor}/${component}"; fi
        [[ -L "${cursor}" ]] && return 0
        ;;
    esac
  done
  return 1
}

access_command_available() {
  local command_name="$1"
  if [[ "${ACCESS_DIAGNOSTIC_TEST_MODE:-}" == '1' && ",${ACCESS_DIAGNOSTIC_TEST_MISSING_COMMANDS:-}," == *",${command_name},"* ]]; then
    return 1
  fi
  command -v "${command_name}" >/dev/null 2>&1
}

access_is_allowed_classification() {
  [[ " ${access_allowed_classifications} " == *" $1 "* ]]
}

access_is_allowed_decision() {
  [[ " ${access_allowed_decisions} " == *" $1 "* ]]
}

access_classify() {
  local kind="$1" exit_code="$2" output_file="$3" text
  if [[ "${exit_code}" == '0' ]]; then printf '%s\n' success; return; fi
  if [[ "${exit_code}" == '124' ]]; then printf '%s\n' timeout; return; fi
  if [[ "${exit_code}" == '127' ]]; then printf '%s\n' command_missing; return; fi
  if [[ "${exit_code}" == '3' ]]; then printf '%s\n' service_absent; return; fi
  text="$(LC_ALL=C tr '[:upper:]' '[:lower:]' < "${output_file}")"
  if [[ "${text}" =~ (unknown[[:space:]]+(flag|option|shorthand)|unsupported|invalid[[:space:]]+(format|template|option)|template[[:space:]].*(error|invalid)|could[[:space:]]not[[:space:]]be[[:space:]]parsed|parsing[[:space:]]failed) ]]; then
    printf '%s\n' unsupported_syntax
  elif [[ "${kind}" == docker && "${text}" =~ (permission[[:space:]]denied|access[[:space:]]denied) ]]; then
    printf '%s\n' permission_denied
  elif [[ "${kind}" == docker && "${text}" =~ (cannot[[:space:]]connect|daemon[[:space:]].*(unavailable|unreachable|not[[:space:]]running)|connection[[:space:]]refused|no[[:space:]]such[[:space:]]file) ]]; then
    printf '%s\n' daemon_unreachable
  elif [[ "${kind}" == systemd && "${text}" =~ (failed[[:space:]]to[[:space:]]connect[[:space:]]to[[:space:]]bus|system[[:space:]]has[[:space:]]not[[:space:]]been[[:space:]]booted|host[[:space:]]is[[:space:]]down) ]]; then
    printf '%s\n' system_bus_unreachable
  elif [[ "${text}" =~ (operation[[:space:]]not[[:space:]]permitted|not[[:space:]]permitted|namespace) ]]; then
    printf '%s\n' restricted_or_not_permitted
  elif [[ "${text}" =~ permission[[:space:]]denied ]]; then
    printf '%s\n' permission_denied
  else
    printf '%s\n' other_error
  fi
}

access_compose_projection() {
  LC_ALL=C awk -F '\t' '
    {
      lower=tolower($0)
      if (NF >= 2) {
        print $1 "\t" $2
      } else if (lower ~ /configfiles/ || lower ~ /^\{.*\}$/) {
        next
      } else {
        print $0
      }
    }
  '
}

access_compose_json_projection() {
  python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    value = json.loads(raw)
except json.JSONDecodeError:
    for line in raw.splitlines():
        if "configfiles" not in line.lower():
            print(line)
    raise SystemExit(0)
items = value if isinstance(value, list) else [value]
for item in items:
    if isinstance(item, dict):
        name = item.get("Name", "")
        status = item.get("Status", "")
        if isinstance(name, str) and isinstance(status, str):
            print(name + "\t" + status)
'
}
