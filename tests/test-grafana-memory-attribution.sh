#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
collector="${repo}/scripts/collect-grafana-memory-attribution.py"
verifier="${repo}/scripts/verify-grafana-memory-attribution.py"
root="$(mktemp -d "${repo}/evidence/test-grafana-memory.XXXXXX")"
trap 'rm -rf -- "${root}" "${repo}/evidence/test-grafana-memory-link"' EXIT

proc="${root}/proc"
cgroup="${root}/cgroup"
stub="${root}/stub"
cid="$(printf '0123456789abcdef%.0s' {1..4})"
mkdir -p "${proc}/123/fd" "${cgroup}/system.slice/docker-${cid}.scope" "${stub}"
for item in 1 2 3 4 5; do : > "${proc}/123/fd/${item}"; done

cat > "${proc}/123/comm" <<'EOF'
grafana
EOF

cat > "${proc}/123/status" <<'EOF'
Name:	grafana
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

cat > "${proc}/123/cgroup" <<EOF
0::/system.slice/docker-${cid}.scope
EOF

printf '%s\n' $((460000 * 1024)) > "${cgroup}/system.slice/docker-${cid}.scope/memory.current"
printf '%s\n' $((470000 * 1024)) > "${cgroup}/system.slice/docker-${cid}.scope/memory.peak"
printf '%s\n' $((12000 * 1024)) > "${cgroup}/system.slice/docker-${cid}.scope/memory.swap.current"
printf '%s\n' $((500 * 1024 * 1024)) > "${cgroup}/system.slice/docker-${cid}.scope/memory.max"

cat > "${cgroup}/system.slice/docker-${cid}.scope/memory.stat" <<EOF
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

cat > "${cgroup}/system.slice/docker-${cid}.scope/memory.events" <<'EOF'
low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0
EOF
cat > "${cgroup}/system.slice/docker-${cid}.scope/memory.events.local" <<'EOF'
low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0
EOF

cat > "${stub}/docker" <<'EOF'
#!/usr/bin/env bash
case "${1-}" in
  ps) printf '%s\tgrafana\n' "${GRAFANA_ATTR_TEST_CONTAINER_ID:?}" ;;
  stats) printf 'grafana\t438.4MiB / 500MiB\t87.68%%\t15\n' ;;
  *) exit 1 ;;
esac
EOF
chmod +x "${stub}/docker"

collect(){
  local output="$1"
  PATH="${stub}:/usr/bin:/bin" \
  GRAFANA_ATTR_TEST_MODE=1 \
  GRAFANA_ATTR_TEST_UID=1000 \
  GRAFANA_ATTR_TEST_CONTAINER_ID="${cid}" \
  GRAFANA_ATTR_TEST_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  GRAFANA_ATTR_FIXED_UTC="${GRAFANA_ATTR_TEST_UTC:-2026-08-05T13:00:00Z}" \
  GRAFANA_ATTR_PROC_ROOT="${proc}" \
  GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
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
assert report["schema"] == "rpi5.grafana-memory-attribution.v1"
assert report["observation_level"] == "informational"
assert report["process"]["count"] == 1
assert report["process"]["threads"] == 15
assert report["process"]["fd_count"] == 5
attr = report["attribution"]
assert report["cgroup"]["memory_events_local"]["oom_kill"] == 0
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
assert "Grafana queries, plugins, Go allocations or caches" in markdown
assert "Grafana Home" not in markdown
assert "DNS cache" not in markdown
PY

if grep -R -F "system.slice/docker-${cid}.scope" "${one}" >/dev/null; then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: cgroup path leaked' >&2
  exit 1
fi

wrong="${root}/wrong-identity"
if GRAFANA_ATTR_TEST_CONTAINER_ID="$(printf 'f%.0s' {1..64})" \
   PATH="${stub}:/usr/bin:/bin" GRAFANA_ATTR_TEST_MODE=1 GRAFANA_ATTR_TEST_UID=1000 \
   GRAFANA_ATTR_PROC_ROOT="${proc}" GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output "${wrong}" >/dev/null 2>&1
then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: mismatched container accepted' >&2
  exit 1
fi
test ! -e "${wrong}"

rm -f "${cgroup}/system.slice/docker-${cid}.scope/memory.events.local"
unknown="${root}/bundle-no-local-events"
collect "${unknown}"
python3 "${verifier}" "${unknown}" >/dev/null
python3 - "${unknown}/report.json" "${unknown}/report.md" <<'PY'
import json
import pathlib
import sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["cgroup"]["memory_events_local"] is None
assert "unavailable (unknown)" in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
PY

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

if GRAFANA_ATTR_TEST_MODE=1 \
  GRAFANA_ATTR_TEST_UID=0 \
   GRAFANA_ATTR_PROC_ROOT="${proc}" \
   GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output "${root}/root-rejected" >/dev/null 2>&1
then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: root execution accepted' >&2
  exit 1
fi

mv "${proc}/123/comm" "${proc}/123/comm.off"
if GRAFANA_ATTR_TEST_MODE=1 \
  GRAFANA_ATTR_TEST_UID=1000 \
   GRAFANA_ATTR_PROC_ROOT="${proc}" \
   GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output "${root}/missing-process" >/dev/null 2>&1
then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: missing process accepted' >&2
  exit 1
fi
mv "${proc}/123/comm.off" "${proc}/123/comm"

if GRAFANA_ATTR_TEST_MODE=1 \
  GRAFANA_ATTR_TEST_UID=1000 \
   GRAFANA_ATTR_PROC_ROOT="${proc}" \
   GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" --output /tmp/grafana-memory-test >/dev/null 2>&1
then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: output escape accepted' >&2
  exit 1
fi

ln -s "${root}" "${repo}/evidence/test-grafana-memory-link"
if GRAFANA_ATTR_TEST_MODE=1 \
  GRAFANA_ATTR_TEST_UID=1000 \
   GRAFANA_ATTR_PROC_ROOT="${proc}" \
   GRAFANA_ATTR_CGROUP_ROOT="${cgroup}" \
   python3 "${collector}" \
   --output "${repo}/evidence/test-grafana-memory-link/output" >/dev/null 2>&1
then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: symlink output accepted' >&2
  exit 1
fi
rm -f "${repo}/evidence/test-grafana-memory-link"

tampered="${root}/tampered"
cp -a "${one}" "${tampered}"
printf '\n' >> "${tampered}/report.json"
if python3 "${verifier}" "${tampered}" >/dev/null 2>&1; then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: tampered report accepted' >&2
  exit 1
fi

hardlinked="${root}/hardlinked"
cp -a "${one}" "${hardlinked}"
rm -f "${hardlinked}/report.md"
ln "${one}/report.md" "${hardlinked}/report.md"
if python3 "${verifier}" "${hardlinked}" >/dev/null 2>&1; then
  printf '%s\n' 'test-grafana-memory-attribution: FAIL: hard link accepted' >&2
  exit 1
fi

# Restore the canonical source bundle link-count after the deliberate hard-link rejection.
rm -f "${hardlinked}/report.md"
python3 -B "${verifier}" "${one}" >/dev/null

series_analyzer="$repo/scripts/analyze-grafana-memory-series.py"
series_verifier="$repo/scripts/verify-grafana-memory-series.py"
later="$root/bundle-later"
GRAFANA_ATTR_TEST_UTC=2026-08-05T13:05:00Z collect "$later"
python3 -B "$series_analyzer" --output "$root/series-good" "$one" "$later" >/dev/null
python3 -B "$series_verifier" "$root/series-good" >/dev/null
python3 - "$root/series-good/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r["sample_count"] == 2
assert r["comparison"] == "descriptive_only"
assert r["same_cgroup_identity"] == "unproven"
assert r["cgroup_oom_event_deltas"] is None
assert r["summary"]["missing_local_events"] == 1
PY
if python3 -B "$series_analyzer" --output "$root/out-of-order" "$later" "$one" >/dev/null 2>&1; then
  echo "grafana series: chronological bypass" >&2; exit 1
fi
if python3 -B "$series_analyzer" --output "$root/duplicate" "$one" "$one" >/dev/null 2>&1; then
  echo "grafana series: duplicate bypass" >&2; exit 1
fi
cp -a "$root/series-good" "$root/series-tampered"
printf '\n' >> "$root/series-tampered/report.json"
if python3 -B "$series_verifier" "$root/series-tampered" >/dev/null 2>&1; then
  echo "grafana series: report tamper bypass" >&2; exit 1
fi

# Source-only historical evidence regression: documentation must keep provenance and limits.
python3 -B - "${repo}/docs/GRAFANA_MEMORY_V01_INITIAL_EVIDENCE_1468.md" "${repo}/docs/GRAFANA_MEMORY_CGROUP_PREFLIGHT_1468.md" <<'PY'
from pathlib import Path
import sys
record = Path(sys.argv[1]).read_text(encoding="utf-8")
preflight = Path(sys.argv[2]).read_text(encoding="utf-8")
required = (
    "65eba8930ebfda18ec7e4fe7656e0f92f31f92e7",
    "2026-11-15T12:29:36Z", "2026-11-15T12:30:13Z",
    "30664", "30670", "131.53 MiB", "135.33 MiB",
    "cgroup.memory_stat_bytes", "same_cgroup_identity=unproven",
    "cgroup_oom_event_deltas=null", "#1468 stays OPEN",
    "37 seconds apart", "No new collection",
)
assert all(text in record for text in required), "Grafana initial evidence contract missing"
assert "GRAFANA_MEMORY_V01_INITIAL_EVIDENCE_1468.md" in preflight
assert "SOURCE-ONLY DESIGN; NOT EXECUTED ON RPi5" not in preflight
assert "It has **not been run on RPi5**" not in preflight
assert "a source merge alone is **not** LIVE permission" in preflight
assert "No new attributable OOM events were measured" not in record
PY

# Static continuity safety contract regression: source-only, no runtime access.
python3 -B - "${repo}/docs/GRAFANA_CONTINUOUS_CGROUP_IDENTITY_CONTRACT_1468.md" "${repo}/docs/GRAFANA_MEMORY_V01_INITIAL_EVIDENCE_1468.md" "${repo}/docs/GRAFANA_CONTINUITY_V02_VERIFIED_20261115_1468.md" <<'PY'
from pathlib import Path
import sys
contract = Path(sys.argv[1]).read_text(encoding="utf-8")
evidence = Path(sys.argv[2]).read_text(encoding="utf-8")
v02 = Path(sys.argv[3]).read_text(encoding="utf-8")
required = (
    "SOURCE IMPLEMENTED", "RPi5 V02 VERIFIED", "NOT LIVE AUTHORIZATION",
    "single-process, continuous-identity", "same pinned directory handle",
    "memory.events.local", "end-start", "null deltas",
    "PID reuse", "source commit SHA", "independent offline verifier",
    "cannot independently re-observe", "No PIDs, raw or hashed container IDs",
    "After an authorized evidence write begins", "#1468 stays OPEN",
)
assert all(marker in contract for marker in required), "continuous-identity contract missing invariant"
assert "GRAFANA_CONTINUOUS_CGROUP_IDENTITY_CONTRACT_1468.md" in evidence
assert "cgroup_oom_event_deltas=null" in evidence
assert "had not been run on RPi5" in evidence
assert "GRAFANA_CONTINUITY_V02_VERIFIED_20261115_1468.md" in contract
assert "GRAFANA_CONTINUITY_V02_VERIFIED_20261115_1468.md" in evidence
assert all(marker in v02 for marker in (
    "140f51fa55d0a66ad6da6d551bc6dc36b5a54718",
    "22d00a74b9bab15fcc18a48825bd498996fee4aa627d612a92691cf7cb40d37a",
    "3a614893f63a56bd57d4a5b6d4416c1ebd91ab27939db0c4963a013f3cccc27c",
    "within-invocation", "109", "oom_kill",
    "not an authorization to collect again",
    "No identity continuity is claimed", "#1468",
)), "Grafana V02 sanitized evidence markers missing"
PY

# Grafana health GET evidence and future correlation gate are source-only.
python3 -B - "${repo}/docs/GRAFANA_HEALTH_CORRELATION_1468.md" "${repo}/docs/GRAFANA_CONTINUITY_V02_VERIFIED_20261115_1468.md" "${repo}/docs/GRAFANA_MEMORY_CGROUP_PREFLIGHT_1468.md" <<'PY'
from pathlib import Path
import sys
health, v02, preflight = [Path(p).read_text(encoding="utf-8") for p in sys.argv[1:]]
required = (
    "GRAFANA-HEALTH-SURFACE-PREFLIGHT",
    "GRAFANA-CONTAINER-HEALTH-GET",
    "140f51fa55d0a66ad6da6d551bc6dc36b5a54718",
    "a9aa708504c52775eaed8706bd118dd2a314f7ed",
    "13.3.1", "database=ok",
    "NO_PERFORMANCE_PROOF", "NO_SAME_WINDOW_CORRELATION",
    "PROMETHEUS_SERIES_UNVERIFIED", "NO_LIVE_AUTHORITY",
    "zero new Grafana OOM", "109", "#1468",
)
assert all(marker in health for marker in required), "Grafana health provenance/safety contract missing"
assert "GRAFANA_HEALTH_CORRELATION_1468.md" in v02
assert "GRAFANA_HEALTH_CORRELATION_1468.md" in preflight
assert "not synchronized" in health.lower()
assert "not synchronized" in preflight.lower()
assert "new Grafana HTTP performance evidence" not in health
PY

python3 -B "${repo}/tests/test-grafana-continuity.py"
python3 -B "${repo}/tests/test-grafana-continuity-collector.py"

printf '%s\n' 'Grafana memory attribution tests: PASS'
