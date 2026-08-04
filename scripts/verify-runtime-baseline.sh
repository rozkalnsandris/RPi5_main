#!/usr/bin/env bash
# Verify a V02B runtime baseline evidence bundle without printing its contents.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"
# shellcheck source=scripts/access-diagnostic-lib.sh
source "${script_dir}/access-diagnostic-lib.sh"
# shellcheck source=scripts/runtime-baseline-lib.sh
source "${script_dir}/runtime-baseline-lib.sh"

max_file_bytes="${RUNTIME_BASELINE_VERIFY_MAX_FILE_BYTES:-65536}"
max_total_bytes="${RUNTIME_BASELINE_VERIFY_MAX_TOTAL_BYTES:-1048576}"
max_files="${RUNTIME_BASELINE_VERIFY_MAX_FILES:-32}"

fail() {
  printf 'Runtime baseline verification: FAIL: %s\n' "$*" >&2
  exit 1
}

if [[ $# -ne 1 ]]; then fail 'expected exactly one result directory'; fi
[[ "${max_file_bytes}" =~ ^[1-9][0-9]*$ && "${max_total_bytes}" =~ ^[1-9][0-9]*$ && "${max_files}" =~ ^[1-9][0-9]*$ ]] || fail 'invalid verifier limits'
[[ -d "$1" && ! -L "$1" ]] || fail 'result target is not a regular directory'
if [[ "$1" == /* ]]; then requested_absolute="$1"; else requested_absolute="$(pwd -P)/$1"; fi
access_path_has_symlink_component "${requested_absolute}" && fail 'symlink path component rejected'
result_dir="$(realpath -e -- "$1")"
case "${result_dir}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) fail 'result path is outside repository evidence/export area' ;;
esac

expected_tree=$'SHA256SUMS\nfile-inventory.txt\nsection-status.tsv\nsections/docker_compose_projects.txt\nsections/docker_compose_version.txt\nsections/docker_containers.txt\nsections/docker_engine_version.txt\nsections/docker_networks.txt\nsections/listening_sockets.txt\nsections/network_interfaces.txt\nsections/systemd_enabled_units.txt\nsections/systemd_failed_units.txt\nsections/systemd_system_state.txt\nsections/systemd_timer_units.txt\nsections/systemd_timers.txt\nsummary.json'
actual_tree="$(cd -- "${result_dir}" && LC_ALL=C find . -type f -printf '%P\n' | LC_ALL=C sort)"
[[ "${actual_tree}" == "${expected_tree}" ]] || fail 'unexpected evidence file tree'
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
  if safe_inventory_file_has_obvious_secret "${file}"; then fail 'secret-like content rejected'; fi
done < <(find "${result_dir}" -type f -print0)
(( total_bytes <= max_total_bytes )) || fail 'total-size limit exceeded'

manifest_entries="$(wc -l < "${result_dir}/SHA256SUMS")"
(( manifest_entries == file_count - 1 )) || fail 'checksum manifest does not cover every file'
if ! (cd -- "${result_dir}" && sha256sum -c --status SHA256SUMS); then fail 'checksum verification failed'; fi
expected_inventory=$'section-status.tsv\nsections/docker_compose_projects.txt\nsections/docker_compose_version.txt\nsections/docker_containers.txt\nsections/docker_engine_version.txt\nsections/docker_networks.txt\nsections/listening_sockets.txt\nsections/network_interfaces.txt\nsections/systemd_enabled_units.txt\nsections/systemd_failed_units.txt\nsections/systemd_system_state.txt\nsections/systemd_timer_units.txt\nsections/systemd_timers.txt\nsummary.json'
[[ "$(<"${result_dir}/file-inventory.txt")" == "${expected_inventory}" ]] || fail 'file inventory is invalid'

if ! python3 - "${result_dir}" 2>/dev/null <<'PY'
import csv
import ipaddress
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
sections = (
    "docker_engine_version", "docker_compose_version", "docker_containers", "docker_networks", "docker_compose_projects",
    "systemd_system_state", "systemd_enabled_units", "systemd_failed_units", "systemd_timer_units", "systemd_timers",
    "listening_sockets", "network_interfaces",
)
classes = {
    "success", "success_degraded", "command_missing", "permission_denied", "daemon_unreachable",
    "system_bus_unreachable", "unsupported_syntax", "timeout", "restricted_or_not_permitted",
    "service_absent", "not_applicable", "other_error",
}
unit = re.compile(r"^[A-Za-z0-9@_.:-]{1,128}\.(?:service|timer)$")
timer = re.compile(r"^[A-Za-z0-9@_.:-]{1,128}\.timer$")
atom = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}$")
iface = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$")
state = re.compile(r"^[a-z][a-z_-]{0,31}$")
version = re.compile(r"^[vV]?[0-9][A-Za-z0-9.+:_-]{0,63}$")
timestamp = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
hex_id = re.compile(r"^[0-9a-fA-F]{12,64}$")
mac = re.compile(r"(?:^|[^0-9A-Fa-f])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?:$|[^0-9A-Fa-f])")

def fail(message):
    raise SystemExit(1)

def contains_ip(value):
    for candidate in re.findall(r"[0-9A-Fa-f:.%]+", value):
        try:
            ipaddress.ip_address(candidate.split("%", 1)[0])
            return True
        except ValueError:
            pass
    return False

def safe_atom(value, pattern=atom):
    return bool(pattern.fullmatch(value)) and not contains_ip(value) and not mac.search(value)

def read_lines(name):
    text = (root / "sections" / f"{name}.txt").read_text(encoding="utf-8")
    forbidden = ("__runtime_error=", "ConfigFiles", "Environment=", "EnvironmentFiles=", "ExecStart=", "FragmentPath=", "DropIn", "Authorization:", "Bearer ", "Basic ")
    if any(item.lower() in text.lower() for item in forbidden):
        fail("forbidden raw field")
    if mac.search(text) or contains_ip(text):
        fail("raw network identifier")
    return [] if not text else text.splitlines()

def unique_sorted(rows):
    if rows != sorted(set(rows)):
        fail("section is not sorted and deduplicated")

summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
if set(summary) != {"collector_version", "git_commit", "context", "collected_at_utc", "sections_attempted", "sections_with_nonzero_exit", "overall_result"}:
    fail("invalid summary schema")
if summary["collector_version"] != "v02b.0.0" or not re.fullmatch(r"[0-9a-f]{40}", summary["git_commit"]):
    fail("invalid summary metadata")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", summary["context"]) or not timestamp.fullmatch(summary["collected_at_utc"]):
    fail("invalid summary context")
if summary["sections_attempted"] != len(sections) or not isinstance(summary["sections_with_nonzero_exit"], int) or summary["overall_result"] != "success":
    fail("invalid summary result")

with (root / "section-status.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
    if handle.seekable():
        handle.seek(0)
        header = handle.readline().rstrip("\n").split("\t")
if header != ["section", "command_present", "exit_code", "classification", "bytes", "started_at_utc", "ended_at_utc", "context"]:
    fail("invalid status header")
if [row.get("section") for row in rows] != list(sections):
    fail("invalid status sections")
nonzero = 0
for row in rows:
    if set(row) != {"section", "command_present", "exit_code", "classification", "bytes", "started_at_utc", "ended_at_utc", "context"}:
        fail("invalid status row")
    if row["command_present"] not in {"true", "false"} or not row["exit_code"].isdigit() or not row["bytes"].isdigit():
        fail("invalid status numeric field")
    if row["classification"] not in classes or row["context"] != summary["context"]:
        fail("invalid status classification")
    if not timestamp.fullmatch(row["started_at_utc"]) or not timestamp.fullmatch(row["ended_at_utc"]):
        fail("invalid status timestamp")
    if int(row["bytes"]) != (root / "sections" / f"{row['section']}.txt").stat().st_size:
        fail("status byte mismatch")
    nonzero += row["exit_code"] != "0"
if nonzero != summary["sections_with_nonzero_exit"]:
    fail("summary nonzero mismatch")

for name in ("docker_engine_version", "docker_compose_version"):
    lines = read_lines(name)
    if lines and (len(lines) != 1 or len(lines[0].split("\t")) != 2 or lines[0].split("\t")[0] != "version" or not version.fullmatch(lines[0].split("\t")[1])):
        fail("invalid version projection")

rows = [tuple(line.split("\t")) for line in read_lines("docker_containers")]
if any(len(row) != 4 or not safe_atom(row[0]) or not safe_atom(row[1]) or hex_id.fullmatch(row[0]) or hex_id.fullmatch(row[1]) or not state.fullmatch(row[2]) or row[3] not in {"healthy", "unhealthy", "starting", "none", "unknown"} for row in rows):
    fail("invalid container projection")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("docker_networks")]
if any(len(row) != 3 or any(not safe_atom(value) or hex_id.fullmatch(value) for value in row) for row in rows): fail("invalid network projection")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("docker_compose_projects")]
if any(len(row) != 2 or not safe_atom(row[0]) or hex_id.fullmatch(row[0]) or row[1] not in {"running", "stopped", "exited", "paused", "restarting", "unknown"} for row in rows): fail("invalid compose projection")
unique_sorted(rows)
lines = read_lines("systemd_system_state")
if lines and (len(lines) != 1 or lines[0] not in {f"state\t{x}" for x in ("running", "degraded", "maintenance", "starting", "stopping", "initializing", "offline", "unknown")}): fail("invalid system state")
rows = [tuple(line.split("\t")) for line in read_lines("systemd_enabled_units")]
if any(len(row) != 2 or not unit.fullmatch(row[0]) or not state.fullmatch(row[1]) for row in rows): fail("invalid enabled units")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("systemd_failed_units")]
if any(len(row) != 4 or not unit.fullmatch(row[0]) or any(not state.fullmatch(value) for value in row[1:]) for row in rows): fail("invalid failed units")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("systemd_timer_units")]
if any(len(row) != 2 or not timer.fullmatch(row[0]) or not state.fullmatch(row[1]) for row in rows): fail("invalid timer unit list")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("systemd_timers")]
if any(len(row) != 7 or not timer.fullmatch(row[0]) or any(not state.fullmatch(value) for value in row[1:4]) or (row[4] != "n/a" and not unit.fullmatch(row[4])) or any(len(value) > 96 or contains_ip(value) or mac.search(value) for value in row[5:]) for row in rows): fail("invalid timer properties")
unique_sorted(rows)
rows = [tuple(line.split("\t")) for line in read_lines("listening_sockets")]
if any(len(row) != 3 or row[0] not in {"tcp", "tcp6", "udp", "udp6"} or row[1] not in {"wildcard", "loopback", "private_or_local", "specific_other", "unknown"} or not row[2].isdigit() or not 1 <= int(row[2]) <= 65535 for row in rows): fail("invalid socket projection")
if rows != sorted(set(rows), key=lambda row: (row[0], row[1], int(row[2]))): fail("socket section is not sorted and deduplicated")
rows = [tuple(line.split("\t")) for line in read_lines("network_interfaces")]
for row in rows:
    if len(row) != 7 or not iface.fullmatch(row[0]) or not state.fullmatch(row[1]) or not state.fullmatch(row[2]) or row[3] not in {"true", "false"} or not row[4].isdigit() or not row[5].isdigit():
        fail("invalid interface projection")
    parts = row[6].split(",")
    if parts != [f"{key}={next((part.split('=', 1)[1] for part in parts if part.startswith(key + '=')), '')}" for key in ("host", "link", "global", "other")] or any(not re.fullmatch(r"(?:host|link|global|other)=\d+", part) for part in parts):
        fail("invalid interface scopes")
unique_sorted(rows)
PY
then
  fail 'invalid sanitized evidence schema'
fi

source_commit="$(python3 - "${result_dir}/summary.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['git_commit'])
PY
)" || fail 'summary source commit is unreadable'
git -C "${repo_root}" cat-file -e "${source_commit}^{commit}" 2>/dev/null || fail 'source commit is unavailable locally'

printf 'Runtime baseline verification: PASS (%s files, %s bytes)\n' "${file_count}" "${total_bytes}"
