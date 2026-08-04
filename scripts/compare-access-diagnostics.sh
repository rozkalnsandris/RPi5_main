#!/usr/bin/env bash
# Create a bounded, sanitized V02A comparison artifact from two verified results.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"
# shellcheck source=scripts/access-diagnostic-lib.sh
source "${script_dir}/access-diagnostic-lib.sh"

die() {
  printf 'compare-access-diagnostics: %s\n' "$*" >&2
  exit 1
}

if [[ $# -ne 6 || "$1" != '--output' || "$3" != '--left' || "$5" != '--right' ]]; then
  printf 'Usage: %s --output DIR --left RESULT_DIR --right RESULT_DIR\n' "${0##*/}" >&2
  exit 2
fi
output_arg="$2"
left_dir="$4"
right_dir="$6"
"${script_dir}/verify-access-diagnostic.sh" "${left_dir}" >/dev/null
"${script_dir}/verify-access-diagnostic.sh" "${right_dir}" >/dev/null

if [[ "${output_arg}" == /* ]]; then requested_absolute="${output_arg}"; else requested_absolute="$(pwd -P)/${output_arg}"; fi
access_path_has_symlink_component "${requested_absolute}" && die 'refusing output path with a symlink component'
output_base="$(realpath -m -- "${requested_absolute}")"
case "${output_base}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) die 'output directory must resolve below repository evidence/ or exports/' ;;
esac
umask 077
mkdir -p -- "${output_base}"
access_path_has_symlink_component "${output_base}" && die 'refusing output path with a symlink component'
timestamp="$(access_now_utc)"
result_dir="$(mktemp -d "${output_base}/v02a-comparison-${timestamp//:/-}-XXXXXX")"
chmod 700 -- "${result_dir}"

comparison_file="${result_dir}/comparison.json"
python3 -c '
import csv, json, pathlib, sys

left, right, output = map(pathlib.Path, sys.argv[1:])
command_names = ("docker", "systemctl", "ss", "ip", "stat", "namei", "readlink", "timeout", "python3")
probe_names = ("docker_server_version", "docker_ps_projection", "docker_network_projection", "docker_compose_projects", "system_running", "enabled_unit_names", "failed_unit_names", "system_timers", "ss_listening", "ip_brief_address")

def statuses(directory):
    with (directory / "probe-status.tsv").open(encoding="utf-8") as handle:
        return {row["probe"]: row for row in csv.DictReader(handle, delimiter="\t")}

def lines(directory, name):
    return (directory / "sections" / (name + ".txt")).read_text(encoding="utf-8").splitlines()

def values(directory, name, allowed):
    found = {}
    for line in lines(directory, name):
        for item in line.split("\t"):
            for field in item.split():
                if "=" in field:
                    key, value = field.split("=", 1)
                    if key in allowed:
                        found[key] = value
    return found

def command_presence(directory):
    found = {}
    for line in lines(directory, "command_availability"):
        fields = line.split("\t")
        if fields and fields[0] in command_names:
            found[fields[0]] = "present=true" in fields
    return found

def one(directory):
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    decision = json.loads((directory / "decision.json").read_text(encoding="utf-8"))
    status = statuses(directory)
    return {
        "context": summary["context"],
        "namespaces": values(directory, "namespaces", {"user", "mnt", "pid", "net"}),
        "commands_present": command_presence(directory),
        "docker_socket": values(directory, "docker_socket_metadata", {"type", "mode", "owner", "group"}) | values(directory, "docker_socket_access", {"socket_present", "readable", "writable", "socket_group_member"}),
        "systemd_private_socket": values(directory, "systemd_private_metadata", {"type", "mode", "owner", "group"}),
        "dbus_system_socket": values(directory, "dbus_system_socket_metadata", {"type", "mode", "owner", "group"}),
        "probes": {name: {"exit_code": int(status[name]["exit_code"]), "classification": status[name]["classification"]} for name in probe_names},
        "decision": decision["decision"],
        "evidence_codes": decision["evidence_codes"],
    }

payload = {"comparison_version": "v02a.0.0", "left": one(left), "right": one(right)}
payload["namespace_ids_differ"] = payload["left"]["namespaces"] != payload["right"]["namespaces"]
output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
' "${left_dir}" "${right_dir}" "${comparison_file}"
chmod 600 -- "${comparison_file}"
(
  cd -- "${result_dir}"
  printf '%s\n' comparison.json > file-inventory.txt
  sha256sum comparison.json file-inventory.txt > SHA256SUMS
)
chmod 600 -- "${result_dir}/file-inventory.txt" "${result_dir}/SHA256SUMS"
printf 'Access comparison result: %s\n' "${result_dir}"
