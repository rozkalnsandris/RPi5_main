# RPi5 memory + Grafana composite baseline, 2026-11-16 (#1468)

**VERIFIED BOUNDED SNAPSHOT; NOT SUSTAINED-PRESSURE PROOF; NO_LIVE_AUTHORITY.**
Sanitized account of one owner-authorized RPi5 composite run. Raw evidence is
kept only in the host repository's ignored `evidence/` directory, not GitHub.
**#1468 stays OPEN** because idle/busy replication and PSI are not yet proven.

## Provenance and scope

- `rpi5`, repository `rozkalnsandris/RPi5_main`; both GitHub `main` and
  host's clean checkout were verified at
  `96154199cfb0282292a964121d1d139383789f37`.
- The exact `#1468 COMPOSITE-MEMORY-BASELINE` authorization covered
  one `git fetch origin main`, one `git merge --ff-only FETCH_HEAD`,
  four V08 five-second host windows with `--skip-kernel-events`,
  one Grafana V02 four-sample run at 15-second intervals, verified
  ignored evidence writes and offline correlation. No retries or rollback.
- **4/4 V08 and 1/1 Grafana V02** sealed bundles passed their independent
  verifiers; the offline comparison passed.
- Grafana V02 window: **2026-11-16T22:32:41Z** to
  **2026-11-16T22:33:26Z**, 45 seconds. Four host intervals nominally
  overlap that span. The V08 run-start timestamp is not the precise
  instant of a `vmstat` or PSI read. Correlation classification:
  `nominal_overlap_not_alignment`, with
  `verified_same_window=false` and `proven_causation=false`.
- Source and evidence were checked with the installed commit. No
  kernel journal access, `sudo`, Docker configuration/inspection,
  service restart, software deployment, swap reset or secret access.
  These source-level statements do not constitute new LIVE authority.

## Numeric findings

| Metric | Result |
| --- | --- |
| V08 classification | `attention` for all four five-second windows |
| `MemAvailable` | **1361.70 → 1312.94 MiB**, first to last |
| `MemAvailable` fraction | **33.62% → 32.42%**, first to last |
| Swap occupancy | **1859.75 → 1851.75 MiB**, first to last |
| Swap-in | **883 pages**, sum of the four sampled intervals |
| Swap-out | **195 pages**, sum of sampled intervals |
| Major page faults | **976**, sum of sampled intervals |
| Host `oom_kill` delta | **0** across sampled intervals |
| Host memory PSI | **UNKNOWN: 0/4 measured**, not zero PSI |
| zram device count | **1** reported; no configuration changed |
| Grafana `memory.max` | **300 MiB** |
| Grafana `memory.events.local max` | **6** within the V02 interval |
| Grafana `oom` / `oom_kill` delta | **0 / 0** within V02 interval |
| Grafana HTTP request latency/errors | **NOT MEASURED** |

The 883 page-ins and 195 page-outs are not continuously measured totals
for the full Grafana interval; they sum only four short V08 samples.
The swap occupancy delta is a point-in-time difference, not a page-rate
measurement. Bidirectional swap activity was observed, so the occupied
swap is **not exclusively inactive retained swap** in these samples.
Neither that observation nor the occupancy demonstrates sustained
thrashing, memory exhaustion, or a future OOM. PSI absence is unknown.

### Top containers (last V08 sample; current working set, not peak)

| Container | Current memory | Reported limit |
| --- | ---: | ---: |
| `homeassistant` | 373.3 MiB | 768 MiB |
| `grafana` | 261.7 MiB | 300 MiB |
| `adguard` | 159.3 MiB | 500 MiB |
| `uptime-kuma` | 153.4 MiB | 200 MiB |
| `prometheus` | 83.42 MiB | 100 MiB |

The V08 snapshot listed 21 container rows. Its process-name RSS
aggregation is not PSS, may double-count shared pages, and must not be
summed with Docker working-set values. No representative per-container
peak was measured; historical `memory.peak` is not an interval peak.

## Finding, confidence and owner gate

**High confidence** in the sealed bundle integrity and observed
short-window numeric data; **low confidence** in generalizing this
to sustained pressure or attributing it to Grafana. Grafana's six
`memory.events.local max` events indicate memory-limit boundary
attempts, **not** OOM. Earlier Grafana `max=109` evidence belongs to
another interval and must not be added to the six. The earlier passing
Grafana `/api/health` was not synchronized with this run; no request
performance degradation was demonstrated. The Prometheus scrape-name
checks cannot exclude differently labeled targets.

**Decision:** retain Grafana's **300 MiB** limit and all existing host
settings. Do not change container memory budgets or restart anything
from this snapshot. To finish #1468, gather separately authorized
idle and representative busy windows at different times, resolve PSI
availability if possible without widening trust boundaries, and record
PSS/true peak data as unavailable unless independently measured.
Do not generate synthetic production load or claim sustained pressure.

**NO_LIVE_AUTHORITY.** This document does not authorize re-collection,
host mutation, deployment, privileged access, changing settings,
cleanup, or closing #1468. Each future evidence write needs separate
exact owner authority and a fail-closed STOP with no retry/rollback.

See [composite source contract](GRAFANA_HOST_MEMORY_COMPOSITE_1468.md),
[V08 contract](V08_MEMORY_PRESSURE_DIAGNOSTIC_CONTRACT.md),
and [Grafana V02 identity contract](GRAFANA_CONTINUOUS_CGROUP_IDENTITY_CONTRACT_1468.md).

## Read-only PSI availability follow-up (2026-11-17; #1468)

A narrowly scoped unprivileged **metadata-only** follow-up checked the
four already verified V08 `section-status.tsv` files under the existing
ignored host evidence directory. All four recorded the exact same result
for both `psi_start` and `psi_end`: `command_available=false`,
`exit_status=127`, and `bytes=0` (eight unavailable section reads).
An independent `lstat` check found **both** `/proc/pressure` and
`/proc/pressure/memory` **absent** on `rpi5` at this later observation.

The historical status proves PSI was unavailable **to V08 during the
2026-11-16 captures**. The later path check confirms that the interface
was still absent on 2026-11-17. Neither result proves *why* the kernel
does not expose it, and neither is evidence of zero PSI or of a
successful PSI measurement. No `/proc/pressure` content, kernel logs,
kernel command line or configuration were read. No service or system
settings were modified. Do **not** enable PSI, adjust boot/kernel options
or request privileged inspection under the existing authorization.

### Next evidence scope, not an authorization

The remaining comparison needs **distinct natural idle and
representative busy periods**, not four consecutive samples from one
45-second Grafana window. Reuse the existing V08 collector with
`--skip-kernel-events` and the independently verified V09 memory series
analyzer (`scripts/analyze-memory-pressure-series.py`), rather than
building another collector or repeating Grafana GETs by default.
Schedule the two periods only under separately specified owner LIVE
authority; V08 and V09 output creation writes ignored evidence and is
**not** covered by `START`. Keep PSI explicitly **unknown** if the
interface remains absent, and do not infer a PSI rate from swap counts.

V09's `sustained_pressure` label is a **deterministic heuristic**: two
swap-out-positive snapshots close together do **not** by themselves
prove sustained pressure over separate hours or workloads. Require
cross-period evidence and describe uncertainty before recommending any
resource budget change. Measured process PSS and comparable
per-container peaks are still missing; do not claim that V08 RSS or
Grafana historical `memory.peak` fills those gaps. Preserve original
raw evidence on host; GitHub gets sanitized facts only.

**NO_LIVE_AUTHORITY; #1468 remains OPEN.**
