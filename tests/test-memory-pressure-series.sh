#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo}/scripts/collect-memory-pressure-diagnostic.py"
analyzer="${repo}/scripts/analyze-memory-pressure-series.py"
verifier="${repo}/scripts/verify-memory-pressure-series.py"
root="$(mktemp -d "${repo}/evidence/test-memory-series.XXXXXX")"
trap 'rm -rf -- "${root}" "${repo}/evidence/test-memory-series-link"' EXIT
proc="${root}/proc"
stub="${root}/stub"
mkdir -p "${proc}/pressure" "${stub}" "${root}/bundles"

fail(){ printf 'test-memory-pressure-series: FAIL: %s\n' "$1" >&2; exit 1; }

cat > "${stub}/ps" <<'EOF'
#!/usr/bin/env bash
printf 'python3 120000\nAdGuardHome 50000\n'
EOF
cat > "${stub}/docker" <<'EOF'
#!/usr/bin/env bash
printf 'adguard\t%s / 500MiB\t%s\t15\n' "${STUB_ADGUARD_USAGE:-436.1MiB}" "${STUB_ADGUARD_PERCENT:-87.22%}"
printf 'grafana\t180MiB / 300MiB\t60.00%%\t30\n'
EOF
cat > "${stub}/zramctl" <<'EOF'
#!/usr/bin/env bash
printf '/dev/zram0 3221225472 2411724800 612345678 700000000 4\n'
EOF
cat > "${stub}/journalctl" <<'EOF'
#!/usr/bin/env bash
:
EOF
chmod +x "${stub}"/*

write_proc(){
  local available="$1" swap_free="$2" pswpin_delta="$3" pswpout_delta="$4" major_delta="$5" psi_delta="$6"
  cat > "${proc}/meminfo" <<EOF
MemTotal:        4146960 kB
MemFree:          200000 kB
MemAvailable:     ${available} kB
Buffers:           20000 kB
Cached:           500000 kB
SReclaimable:      50000 kB
Shmem:             10000 kB
SwapTotal:       4170608 kB
SwapFree:        ${swap_free} kB
Dirty:               100 kB
Writeback:             0 kB
AnonPages:       2200000 kB
Mapped:            90000 kB
Slab:             120000 kB
KernelStack:       12000 kB
PageTables:        22000 kB
EOF
  cat > "${proc}/pressure/memory.start" <<'EOF'
some avg10=0.00 avg60=0.00 avg300=0.00 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=200
EOF
  cat > "${proc}/pressure/memory.end" <<EOF
some avg10=0.00 avg60=0.00 avg300=0.00 total=$((1000 + psi_delta))
full avg10=0.00 avg60=0.00 avg300=0.00 total=200
EOF
  cat > "${proc}/vmstat.start" <<'EOF'
pswpin 100
pswpout 200
pgmajfault 300
oom_kill 0
allocstall_normal 4
compact_stall 5
kswapd_low_wmark_hit_quickly 6
kswapd_high_wmark_hit_quickly 7
EOF
  cat > "${proc}/vmstat.end" <<EOF
pswpin $((100 + pswpin_delta))
pswpout $((200 + pswpout_delta))
pgmajfault $((300 + major_delta))
oom_kill 0
allocstall_normal 4
compact_stall 5
kswapd_low_wmark_hit_quickly 6
kswapd_high_wmark_hit_quickly 7
EOF
  cat > "${proc}/swaps" <<'EOF'
Filename                                Type            Size            Used            Priority
/dev/zram0                              partition       3145724         2300000         100
EOF
}

collect(){
  local label="$1" utc="$2" usage="$3" percent="$4"
  local log="${root}/${label}.log"
  PATH="${stub}:/usr/bin:/bin" \
  STUB_ADGUARD_USAGE="${usage}" \
  STUB_ADGUARD_PERCENT="${percent}" \
  MEMORY_DIAG_TEST_MODE=1 \
  MEMORY_DIAG_TEST_UID=1000 \
  MEMORY_DIAG_TEST_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  MEMORY_DIAG_FIXED_UTC="${utc}" \
  MEMORY_DIAG_SAMPLE_SECONDS=0 \
  MEMORY_DIAG_PROC_ROOT="${proc}" \
  python3 "${collector}" --output "${root}/bundles" >"${log}"
  awk -F ': ' '/^Memory diagnostic result:/ {print $2}' "${log}"
}

write_proc 1674832 1735136 3 0 3 0
one="$(collect one 2026-08-05T12:10:54Z 436.1MiB 87.22%)"
write_proc 1641856 1755616 2 0 67 0
two="$(collect two 2026-08-05T12:26:16Z 438.4MiB 87.68%)"

python3 "${analyzer}" --output "${root}/series-one" "${one}" "${two}" >/dev/null
python3 "${verifier}" "${root}/series-one" >/dev/null
python3 - "${root}/series-one/report.json" "${root}/series-one/report.md" <<'PY'
import json,pathlib,sys
report=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert report["classification"]=="intermittent_activity"
assert report["series_level"]=="informational"
assert report["aggregate"]["pswpin_pages_total"]==5
assert report["aggregate"]["pswpout_pages_total"]==0
adguard=next(row for row in report["containers"] if row["name"]=="adguard")
assert adguard["change_kib"]==2356
assert adguard["max_kib"]==448922
markdown=pathlib.Path(sys.argv[2]).read_text()
assert "| `adguard` | 2 | 436.10 | 438.40 | 2.30 | 438.40 | 87.68% |" in markdown
PY

python3 "${analyzer}" --output "${root}/series-two" "${one}" "${two}" >/dev/null
cmp "${root}/series-one/report.json" "${root}/series-two/report.json"
cmp "${root}/series-one/report.md" "${root}/series-two/report.md"

if python3 "${analyzer}" --output "${root}/reversed" "${two}" "${one}" >/dev/null 2>&1; then
  fail 'analyzer accepted reversed timestamps'
fi
if python3 "${analyzer}" --output "${root}/duplicate" "${one}" "${one}" >/dev/null 2>&1; then
  fail 'analyzer accepted duplicate bundle'
fi
if python3 "${analyzer}" --output /tmp/memory-series-test "${one}" "${two}" >/dev/null 2>&1; then
  fail 'analyzer accepted output escape'
fi
ln -s "${root}" "${repo}/evidence/test-memory-series-link"
if python3 "${analyzer}" --output "${repo}/evidence/test-memory-series-link/out" "${one}" "${two}" >/dev/null 2>&1; then
  fail 'analyzer accepted symlink output'
fi
rm -f "${repo}/evidence/test-memory-series-link"

bad="${root}/bad-source"
cp -a "${one}" "${bad}"
printf '\n' >> "${bad}/report.json"
if python3 "${analyzer}" --output "${root}/bad-result" "${bad}" "${two}" >/dev/null 2>&1; then
  fail 'analyzer accepted tampered source'
fi

tampered="${root}/tampered-series"
cp -a "${root}/series-one" "${tampered}"
printf '\n' >> "${tampered}/report.json"
if python3 "${verifier}" "${tampered}" >/dev/null 2>&1; then
  fail 'verifier accepted tampered report'
fi

write_proc 500000 1700000 0 3 50 100
three="$(collect three 2026-08-05T13:00:00Z 440MiB 88.00%)"
write_proc 480000 1690000 0 2 60 120
four="$(collect four 2026-08-05T13:05:00Z 441MiB 88.20%)"
python3 "${analyzer}" --output "${root}/pressure" "${three}" "${four}" >/dev/null
python3 "${verifier}" "${root}/pressure" >/dev/null
python3 - "${root}/pressure/report.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1], encoding="utf-8"))
assert report["classification"]=="sustained_pressure"
assert report["series_level"]=="attention"
assert report["evidence"]["sustained_pressure"] is True
assert report["evidence"]["swapout_activity_samples"]==2
PY

printf '%s\n' 'Memory pressure series tests: PASS'
