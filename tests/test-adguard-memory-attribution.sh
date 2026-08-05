#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo}/scripts/collect-adguard-memory-attribution.py"
verifier="${repo}/scripts/verify-adguard-memory-attribution.py"
root="$(mktemp -d "${repo}/evidence/test-adguard-memory.XXXXXX")"
trap 'rm -rf -- "${root}" "${repo}/evidence/test-adguard-memory-link"' EXIT

proc="${root}/proc"
cgroup="${root}/cgroup"
stub="${root}/stub"
mkdir -p "${proc}/123/fd" "${cgroup}/test.slice/adguard.scope" "${stub}"
for item in 1 2 3 4 5; do : > "${proc}/123/fd/${item}"; done

cat > "${proc}/123/comm" <<'EOF'
AdGuardHome
EOF

cat > "${proc}/123/status" <<'EOF'
Name:	AdGuardHome
VmSize:	700000 kB
VmRSS:	450000 kB
RssAnon:	420000 kB
RssFile:	25000 kB
RssShmem:	5000 kB
VmData:	600000 kB
VmStk:	132 kB
VmExe:	12000 kB
VmLib:	3000 kB
VmPTE:	900 kB
VmSwap:	16000 kB
Threads:	15
EOF

cat > "${proc}/123/smaps_rollup" <<'EOF'
00400000-7fffffffffff ---p 00000000 00:00 0                          [rollup]
Rss:              450000 kB
Pss:              430000 kB
Pss_Anon:         400000 kB
Pss_File:          25000 kB
Pss_Shmem:          5000 kB
Shared_Clean:      10000 kB
Shared_Dirty:          0 kB
Private_Clean:     15000 kB
Private_Dirty:    425000 kB
Anonymous:        420000 kB
AnonHugePages:         0 kB
Swap:              16000 kB
SwapPss:            8000 kB
Locked:                0 kB
EOF

cat > "${proc}/123/cgroup" <<'EOF'
0::/test.slice/adguard.scope
EOF

printf '%s\n' $((460000 * 1024)) > "${cgroup}/test.slice/adguard.scope/memory.current"
printf '%s\n' $((470000 * 1024)) > "${cgroup}/test.slice/adguard.scope/memory.peak"
printf '%s\n' $((12000 * 1024)) > "${cgroup}/test.slice/adguard.scope/memory.swap.current"
printf '%s\n' $((500 * 1024 * 1024)) > "${cgroup}/test.slice/adguard.scope/memory.max"

cat > "${cgroup}/test.slice/adguard.scope/memory.stat" <<EOF
anon $((420000 * 1024))
file $((20000 * 1024))
kernel $((20000 * 1024))
kernel_stack $((1000 * 1024))
pagetables $((2000 * 1024))
percpu 0
sock $((2000 * 1024))
shmem $((1000 * 1024))
file_mapped $((5000 * 1024))
file_dirty 0
file_writeback 0
swapcached $((100 * 1024))
slab_reclaimable $((6000 * 1024))
slab_unreclaimable $((4000 * 1024))
workingset_refault_anon 12
workingset_refault_file 34
workingset_activate_anon 5
workingset_activate_file 6
pgfault 10000
pgmajfault 70
pgrefill 100
pgscan 120
pgsteal 110
thp_fault_alloc 0
EOF

cat > "${cgroup}/test.slice/adguard.scope/memory.events" <<'EOF'
low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0
EOF

cat > "${stub}/docker" <<'EOF'
#!/usr/bin/env bash
printf 'adguard\t438.4MiB / 500MiB\t87.68%%\t15\n'
EOF
chmod +x "${stub}/docker"

collect(){
  local output="$1"
  PATH="${stub}:/usr/bin:/bin" \
  ADGUARD_ATTR_TEST_UID=1000 \
  ADGUARD_ATTR_TEST_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  ADGUARD_ATTR_FIXED_UTC=2026-08-05T13:00:00Z \
  ADGUARD_ATTR_PROC_ROOT="${proc}" \
  ADGUARD_ATTR_CGROUP_ROOT="${cgroup}" \
  python3 "${collector}" --output "${output}" >/dev/null
}

one="${root}/bundle-one"
two="${root}/bundle-two"
collect "${one}"
collect "${two}"
python3 "${verifier}" "${one}" >/dev/null
python3 "${verifier}" "${two}" >/dev/null
cmp "${one}/report.json" "${two}/report.json"
cmp "${one}/report.md" "${two}/report.md"

python3 - "${one}/report.json" "${one}/report.md" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "rpi5.adguard-memory-attribution.v1"
assert report["observation_level"] == "informational"
assert report["process"]["count"] == 1
assert report["process"]["threads"] == 15
assert report["process"]["fd_count"] == 5
attr = report["attribution"]
assert attr["basis"] == "process_pss"
assert attr["basis_total_kib"] == 430000
assert attr["anonymous_kib"] == 400000
assert attr["file_kib"] == 25000
assert attr["shared_kib"] == 5000
assert attr["dominant_component"] == "anonymous"
assert attr["process_swap_kib"] == 8000
assert attr["cgroup_swap_kib"] == 12000
assert attr["kernel_kib"] == 20000
assert attr["sock_kib"] == 2000
assert attr["container_headroom_kib"] == 63078
assert report["container"]["usage_kib"] == 448922
assert report["container"]["limit_kib"] == 512000
assert report["container"]["percent_basis_points"] == 8768
markdown = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
assert "Dominant component: `anonymous`." in markdown
assert "headroom 61.60 MiB" in markdown
PY

if grep -R -F 'test.slice/adguard.scope' "${one}" >/dev/null; then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: cgroup path leaked' >&2
  exit 1
fi

rm -f "${proc}/123/smaps_rollup"
fallback="${root}/bundle-fallback"
collect "${fallback}"
python3 "${verifier}" "${fallback}" >/dev/null
python3 - "${fallback}/report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["attribution"]["basis"] == "cgroup_current"
assert report["attribution"]["anonymous_kib"] == 420000
assert report["attribution"]["dominant_component"] == "anonymous"
assert "process_smaps_unavailable" in report["attribution"]["reason_codes"]
assert any("smaps_rollup" in item for item in report["limitations"])
PY

if ADGUARD_ATTR_TEST_UID=0 \
   ADGUARD_ATTR_PROC_ROOT="${proc}" \
   ADGUARD_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output "${root}/root-rejected" >/dev/null 2>&1
then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: root execution accepted' >&2
  exit 1
fi

mv "${proc}/123/comm" "${proc}/123/comm.off"
if ADGUARD_ATTR_TEST_UID=1000 \
   ADGUARD_ATTR_PROC_ROOT="${proc}" \
   ADGUARD_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output "${root}/missing-process" >/dev/null 2>&1
then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: missing process accepted' >&2
  exit 1
fi
mv "${proc}/123/comm.off" "${proc}/123/comm"

if ADGUARD_ATTR_TEST_UID=1000 \
   ADGUARD_ATTR_PROC_ROOT="${proc}" \
   ADGUARD_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output /tmp/adguard-memory-test >/dev/null 2>&1
then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: output escape accepted' >&2
  exit 1
fi

ln -s "${root}" "${repo}/evidence/test-adguard-memory-link"
if ADGUARD_ATTR_TEST_UID=1000 \
   ADGUARD_ATTR_PROC_ROOT="${proc}" \
   ADGUARD_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" \
   --output "${repo}/evidence/test-adguard-memory-link/output" >/dev/null 2>&1
then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: symlink output accepted' >&2
  exit 1
fi
rm -f "${repo}/evidence/test-adguard-memory-link"

tampered="${root}/tampered"
cp -a "${one}" "${tampered}"
printf '\n' >> "${tampered}/report.json"
if python3 "${verifier}" "${tampered}" >/dev/null 2>&1; then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: tampered report accepted' >&2
  exit 1
fi

hardlinked="${root}/hardlinked"
cp -a "${one}" "${hardlinked}"
rm -f "${hardlinked}/report.md"
ln "${one}/report.md" "${hardlinked}/report.md"
if python3 "${verifier}" "${hardlinked}" >/dev/null 2>&1; then
  printf '%s\n' 'test-adguard-memory-attribution: FAIL: hard link accepted' >&2
  exit 1
fi

printf '%s\n' 'AdGuard memory attribution tests: PASS'
