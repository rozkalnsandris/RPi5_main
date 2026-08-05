#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo}/scripts/collect-memory-pressure-diagnostic.py"
verifier="${repo}/scripts/verify-memory-pressure-diagnostic.py"
root="$(mktemp -d "${repo}/evidence/test-memory-pressure.XXXXXX")"
trap 'rm -rf -- "${root}" "${repo}/evidence/test-memory-pressure-link"' EXIT
proc="${root}/proc"
stub="${root}/stub"
mkdir -p "${proc}/pressure" "${stub}" "${root}/out"

fail(){ printf 'test-memory-pressure-diagnostic: FAIL: %s\n' "$1" >&2; exit 1; }

cat > "${proc}/meminfo" <<'EOF'
MemTotal:        4000000 kB
MemFree:          100000 kB
MemAvailable:     600000 kB
Buffers:           20000 kB
Cached:           500000 kB
SReclaimable:      50000 kB
Shmem:             10000 kB
SwapTotal:       3000000 kB
SwapFree:         700000 kB
Dirty:               100 kB
Writeback:             0 kB
AnonPages:       2500000 kB
Mapped:            90000 kB
Slab:             120000 kB
KernelStack:       12000 kB
PageTables:        22000 kB
EOF
cat > "${proc}/pressure/memory.start" <<'EOF'
some avg10=0.01 avg60=0.02 avg300=0.03 total=1000
full avg10=0.00 avg60=0.00 avg300=0.00 total=200
EOF
cat > "${proc}/pressure/memory.end" <<'EOF'
some avg10=0.01 avg60=0.02 avg300=0.03 total=1300
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
cat > "${proc}/vmstat.end" <<'EOF'
pswpin 100
pswpout 202
pgmajfault 303
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

cat > "${stub}/ps" <<'EOF'
#!/usr/bin/env bash
printf 'python3 120000\npython3 80000\nAdGuardHome 50000\n'
EOF
cat > "${stub}/docker" <<'EOF'
#!/usr/bin/env bash
printf 'adguard\t100MiB / 1GiB\t9.77%%\t12\n'
printf 'homeassistant\t700MiB / 1GiB\t68.36%%\t44\n'
EOF
cat > "${stub}/zramctl" <<'EOF'
#!/usr/bin/env bash
printf '/dev/zram0 3221225472 2411724800 612345678 700000000 4\n'
EOF
cat > "${stub}/journalctl" <<'EOF'
#!/usr/bin/env bash
printf '2026-08-05 kernel: normal line\n'
printf '2026-08-05 kernel: memory cgroup event for abcdef1234567890 at 192.168.1.2\n'
EOF
chmod +x "${stub}"/*

collect(){
  local out="$1" missing="${2:-}"
  local log="${root}/${out}.log"
  PATH="${stub}:/usr/bin:/bin" \
  MEMORY_DIAG_TEST_MODE=1 \
  MEMORY_DIAG_TEST_UID=1000 \
  MEMORY_DIAG_TEST_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  MEMORY_DIAG_FIXED_UTC=2026-08-05T10:00:00Z \
  MEMORY_DIAG_SAMPLE_SECONDS=0 \
  MEMORY_DIAG_PROC_ROOT="${proc}" \
  MEMORY_DIAG_TEST_MISSING_COMMANDS="${missing}" \
  python3 "${collector}" --output "${root}/${out}" >"${log}"
  awk -F ': ' '/^Memory diagnostic result:/ {print $2}' "${log}"
}

one="$(collect out1)"
python3 "${verifier}" "${one}" >/dev/null
python3 - "${one}/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
o=r['observation']; d=o['sample_delta']
assert o['level']=='attention'
assert o['mem_available_kib']==600000
assert o['swap_used_kib']==2300000
assert d['pswpout_pages']==2 and d['pgmajfault']==3 and d['psi_some_total_usec']==300
assert len(r['top_processes'])==2 and r['top_processes'][0]=={'name':'python3','rss_kib':200000}
assert [x['name'] for x in r['containers']]==['adguard','homeassistant']
PY
grep -q '\[REDACTED_HEX_ID\]' "${one}/sections/kernel_memory_events.txt" || fail 'kernel ID not redacted'
grep -q '\[REDACTED_IP\]' "${one}/sections/kernel_memory_events.txt" || fail 'kernel IP not redacted'

second="$(collect out2)"
cmp "${one}/report.json" "${second}/report.json" || fail 'report JSON not deterministic'
cmp "${one}/report.md" "${second}/report.md" || fail 'report Markdown not deterministic'

missing="$(collect missing docker)"
python3 "${verifier}" "${missing}" >/dev/null
python3 - "${missing}/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['observation']['container_rows']==0
assert any('Per-container current memory was unavailable' in x for x in r['limitations'])
PY

if PATH="${stub}:/usr/bin:/bin" MEMORY_DIAG_TEST_MODE=1 MEMORY_DIAG_TEST_UID=0 MEMORY_DIAG_PROC_ROOT="${proc}" python3 "${collector}" --output "${root}/root" >/dev/null 2>&1; then
  fail 'collector accepted root identity'
fi
if PATH="${stub}:/usr/bin:/bin" MEMORY_DIAG_TEST_MODE=1 MEMORY_DIAG_TEST_UID=1000 MEMORY_DIAG_PROC_ROOT="${proc}" python3 "${collector}" --output /tmp/memory-diag-out >/dev/null 2>&1; then
  fail 'collector accepted output escape'
fi
ln -s "${root}" "${repo}/evidence/test-memory-pressure-link"
if PATH="${stub}:/usr/bin:/bin" MEMORY_DIAG_TEST_MODE=1 MEMORY_DIAG_TEST_UID=1000 MEMORY_DIAG_PROC_ROOT="${proc}" python3 "${collector}" --output "${repo}/evidence/test-memory-pressure-link" >/dev/null 2>&1; then
  fail 'collector accepted symlink output'
fi
rm -f "${repo}/evidence/test-memory-pressure-link"

regen_manifest(){
  local d="$1"
  (cd "$d" && find . -type f ! -name SHA256SUMS -printf '%P\n' | sort | while read -r f; do sha256sum "$f"; done) > "$d/SHA256SUMS"
}

tamper="${root}/tamper"; cp -a "${one}" "$tamper"; printf '\n' >> "$tamper/report.json"; regen_manifest "$tamper"
if python3 "${verifier}" "$tamper" >/dev/null 2>&1; then fail 'verifier accepted report tampering'; fi

key_name="$(printf '%s%s' pass word)"
fixture_value='not-safe'
secret="${root}/secret"; cp -a "${one}" "$secret"; printf '%s=%s\n' "$key_name" "$fixture_value" >> "$secret/sections/limitations.txt"
python3 - "$secret/section-status.tsv" "$secret/sections/limitations.txt" <<'PY'
import pathlib,sys
status=pathlib.Path(sys.argv[1]); section=pathlib.Path(sys.argv[2]); lines=status.read_text().splitlines(); out=[]
for line in lines:
    p=line.split('\t')
    if p[0]=='limitations': p[4]=str(section.stat().st_size)
    out.append('\t'.join(p))
status.write_text('\n'.join(out)+'\n')
PY
regen_manifest "$secret"
if python3 "${verifier}" "$secret" >/dev/null 2>&1; then fail 'verifier accepted secret-like content'; fi

hex="${root}/hex"; cp -a "${one}" "$hex"; printf 'oom abcdef1234567890abcdef\n' >> "$hex/sections/kernel_memory_events.txt"
python3 - "$hex/section-status.tsv" "$hex/sections/kernel_memory_events.txt" <<'PY'
import pathlib,sys
status=pathlib.Path(sys.argv[1]); section=pathlib.Path(sys.argv[2]); lines=status.read_text().splitlines(); out=[]
for line in lines:
    p=line.split('\t')
    if p[0]=='kernel_memory_events': p[4]=str(section.stat().st_size)
    out.append('\t'.join(p))
status.write_text('\n'.join(out)+'\n')
PY
regen_manifest "$hex"
if python3 "${verifier}" "$hex" >/dev/null 2>&1; then fail 'verifier accepted raw long hex ID'; fi

fifo="${root}/fifo"; cp -a "${one}" "$fifo"; rm "$fifo/sections/kernel_memory_events.txt"; mkfifo "$fifo/sections/kernel_memory_events.txt"
if python3 "${verifier}" "$fifo" >/dev/null 2>&1; then fail 'verifier accepted FIFO'; fi

if grep -Eq 'docker[[:space:]]+inspect|/proc/.*/cmdline|[[:space:]]args=' "${collector}"; then
  fail 'collector contains forbidden inspection pattern'
fi

printf '%s\n' 'Memory pressure diagnostic tests: PASS'
