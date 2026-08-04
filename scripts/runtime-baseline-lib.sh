#!/usr/bin/env bash
# Shared, source-only helpers for the V02B runtime baseline collector.

runtime_baseline_version='v02b.0.0'
runtime_allowed_classifications='success success_degraded command_missing permission_denied daemon_unreachable system_bus_unreachable unsupported_syntax timeout restricted_or_not_permitted service_absent not_applicable other_error'
runtime_expected_sections='docker_engine_version docker_compose_version docker_containers docker_networks docker_compose_projects systemd_system_state systemd_enabled_units systemd_failed_units systemd_timer_units systemd_timers listening_sockets network_interfaces'

runtime_now_utc() {
  if [[ "${RUNTIME_BASELINE_TEST_MODE:-}" == '1' && -n "${RUNTIME_BASELINE_FIXED_UTC:-}" ]]; then
    printf '%s\n' "${RUNTIME_BASELINE_FIXED_UTC}"
  else
    date -u '+%Y-%m-%dT%H:%M:%SZ'
  fi
}

runtime_effective_uid() {
  if [[ "${RUNTIME_BASELINE_TEST_MODE:-}" == '1' && -n "${RUNTIME_BASELINE_TEST_UID:-}" ]]; then
    printf '%s\n' "${RUNTIME_BASELINE_TEST_UID}"
  else
    id -u
  fi
}

runtime_valid_context() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$ ]]
}

runtime_command_available() {
  local command_name="$1"
  if [[ "${RUNTIME_BASELINE_TEST_MODE:-}" == '1' && ",${RUNTIME_BASELINE_TEST_MISSING_COMMANDS:-}," == *",${command_name},"* ]]; then
    return 1
  fi
  command -v "${command_name}" >/dev/null 2>&1
}

runtime_is_allowed_classification() {
  [[ " ${runtime_allowed_classifications} " == *" $1 "* ]]
}

runtime_classify() {
  local kind="$1" exit_code="$2" output_file="$3" marker text
  if [[ "${exit_code}" == '0' ]]; then printf '%s\n' success; return; fi
  if [[ "${exit_code}" == '124' ]]; then printf '%s\n' timeout; return; fi
  if [[ "${exit_code}" == '127' ]]; then printf '%s\n' command_missing; return; fi
  if [[ "${exit_code}" == '3' ]]; then printf '%s\n' service_absent; return; fi
  marker="$(awk -F= '/^__runtime_error=/{print $2; exit}' "${output_file}")"
  case "${marker}" in
    permission_denied|daemon_unreachable|system_bus_unreachable|unsupported_syntax|restricted_or_not_permitted|service_absent) printf '%s\n' "${marker}"; return ;;
  esac
  text="$(LC_ALL=C tr '[:upper:]' '[:lower:]' < "${output_file}")"
  if [[ "${text}" =~ (unknown[[:space:]]+(flag|option|shorthand)|unsupported|invalid[[:space:]]+(format|template|option)|could[[:space:]]not[[:space:]]be[[:space:]]parsed) ]]; then
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
