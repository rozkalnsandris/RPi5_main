#!/usr/bin/env bash
# Verify a V01 inventory bundle without printing possible secret values.
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
# shellcheck source=scripts/safe-inventory-lib.sh
source "${script_dir}/safe-inventory-lib.sh"

max_file_bytes="${SAFE_INVENTORY_MAX_FILE_BYTES:-524288}"
max_total_bytes="${SAFE_INVENTORY_MAX_TOTAL_BYTES:-4194304}"
max_files="${SAFE_INVENTORY_MAX_FILES:-80}"

fail() {
  printf 'Inventory verification: FAIL: %s\n' "$*" >&2
  exit 1
}

path_has_symlink_component() {
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

if [[ $# -ne 1 ]]; then
  fail 'expected exactly one inventory directory'
fi
[[ "${max_file_bytes}" =~ ^[1-9][0-9]*$ && "${max_total_bytes}" =~ ^[1-9][0-9]*$ && "${max_files}" =~ ^[1-9][0-9]*$ ]] || fail 'invalid verifier limits'
[[ -d "$1" && ! -L "$1" ]] || fail 'inventory target is not a regular directory'
if [[ "$1" == /* ]]; then requested_absolute="$1"; else requested_absolute="$(pwd -P)/$1"; fi
if path_has_symlink_component "${requested_absolute}"; then fail 'symlink path component rejected'; fi
inventory_dir="$(realpath -e -- "$1")"
case "${inventory_dir}/" in
  "${repo_root}/evidence/"*|"${repo_root}/exports/"*) ;;
  *) fail 'inventory path is outside the repository evidence/export area' ;;
esac

for required in summary.json section-status.tsv file-inventory.txt SHA256SUMS sections; do
  [[ -e "${inventory_dir}/${required}" ]] || fail 'required inventory structure is missing'
done
[[ -d "${inventory_dir}/sections" && ! -L "${inventory_dir}/sections" ]] || fail 'sections directory is invalid'

if find "${inventory_dir}" -type l -print -quit | grep -q .; then fail 'symlink artifact rejected'; fi
if find "${inventory_dir}" \( -type b -o -type c -o -type p -o -type s \) -print -quit | grep -q .; then fail 'special-file artifact rejected'; fi
if find "${inventory_dir}" -type f -links +1 -print -quit | grep -q .; then fail 'hard-linked file rejected'; fi
if find "${inventory_dir}" -perm -0002 -print -quit | grep -q .; then fail 'world-writable artifact rejected'; fi
if find "${inventory_dir}" -not -uid "$(id -u)" -print -quit | grep -q .; then fail 'unexpected artifact owner'; fi

file_count="$(find "${inventory_dir}" -type f | wc -l)"
(( file_count <= max_files )) || fail 'file-count limit exceeded'
total_bytes=0
while IFS= read -r -d '' file; do
  size="$(wc -c < "${file}")"
  (( size <= max_file_bytes )) || fail 'per-file size limit exceeded'
  total_bytes=$((total_bytes + size))
  [[ "$(basename -- "${file}")" != .env* ]] || fail 'forbidden file name rejected'
  case "$(basename -- "${file}")" in
    *.pem|*.key|*.p12|*.pfx|id_rsa*|id_ed25519*|authorized_keys|cert.json) fail 'forbidden file name rejected' ;;
  esac
  if safe_inventory_file_has_obvious_secret "${file}"; then
    fail 'secret-like content rejected'
  fi
done < <(find "${inventory_dir}" -type f -print0)
(( total_bytes <= max_total_bytes )) || fail 'total size limit exceeded'

declare -A expected_sections=()
status_rows=0
while IFS=$'\t' read -r section category available status bytes extra; do
  if [[ "${section}" == 'section' ]]; then
    [[ "${category}" == 'category' && "${available}" == 'command_available' && "${status}" == 'exit_status' && "${bytes}" == 'bytes' && -z "${extra}" ]] || fail 'invalid section-status header'
    continue
  fi
  [[ -n "${section}" && -n "${category}" && -n "${available}" && -n "${status}" && -n "${bytes}" && -z "${extra}" ]] || fail 'invalid section-status row'
  [[ "${section}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail 'invalid section name'
  [[ "${available}" == 'true' || "${available}" == 'false' ]] || fail 'invalid command availability'
  [[ "${status}" =~ ^[0-9]+$ && "${bytes}" =~ ^[0-9]+$ ]] || fail 'missing section exit status'
  [[ -f "${inventory_dir}/sections/${section}.txt" ]] || fail 'section output missing'
  [[ "$(wc -c < "${inventory_dir}/sections/${section}.txt")" == "${bytes}" ]] || fail 'section byte count mismatch'
  expected_sections["${section}.txt"]=1
  status_rows=$((status_rows + 1))
done < "${inventory_dir}/section-status.tsv"
(( status_rows > 0 )) || fail 'no attempted sections recorded'
while IFS= read -r -d '' section_file; do
  name="$(basename -- "${section_file}")"
  [[ -n "${expected_sections[${name}]:-}" ]] || fail 'unexpected section output'
done < <(find "${inventory_dir}/sections" -maxdepth 1 -type f -print0)

grep -q '"collector_version"' "${inventory_dir}/summary.json" || fail 'summary metadata missing'
grep -q '"overall_result": "success"' "${inventory_dir}/summary.json" || fail 'summary result missing'
grep -q '^sections/' "${inventory_dir}/file-inventory.txt" || fail 'file inventory missing section entries'

manifest_entries="$(wc -l < "${inventory_dir}/SHA256SUMS")"
(( manifest_entries > 0 )) || fail 'checksum manifest is empty'
if ! (cd -- "${inventory_dir}" && sha256sum -c --status SHA256SUMS); then
  fail 'checksum verification failed'
fi
actual_manifest_files="$(find "${inventory_dir}" -type f ! -name 'SHA256SUMS' | wc -l)"
(( manifest_entries == actual_manifest_files )) || fail 'checksum manifest does not cover every file'

printf 'Inventory verification: PASS (%s files, %s bytes)\n' "${file_count}" "${total_bytes}"
