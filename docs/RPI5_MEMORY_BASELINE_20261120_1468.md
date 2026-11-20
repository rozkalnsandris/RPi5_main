# RPi5 memory + Grafana verified V08.2 composite, 2026-11-20 (#1468)

**VERIFIED BOUNDED OBSERVATION; NO PROOF OF SERVICE DEGRADATION OR CAUSATION; NO LIVE AUTHORITY.**
This records a previously owner-authorized one-shot diagnostic, independently re-verified
read-only during `START RPi5_main`. Original evidence remains ignored on `rpi5`;
no raw runtime evidence, private metrics, secrets or identifying host metadata are committed.

## Provenance and verification

- Repository: `rozkalnsandris/RPi5_main`; exact GitHub and RPi5 clean `main`
  `ffa06004b0e23af489a5b7d475b5d02d6ded9182`; exact-main required
  GitHub CI workflows successful.
- Explicit consumed authorization: `#1468 POST-V082-COMPOSITE`, one clean
  fast-forward from `29bb633687d4a0e6c41448abf9bf4171b2dfb1ee`,
  four non-root V08 five-second bundles with `--skip-kernel-events`, and
  one Grafana V02 four-sample continuity run with 20 seconds between
  samples. There was no synthetic load, restart, limit/configuration change,
  protected metrics query, privileged log read, retry, rollback or cleanup.
- Host evidence root (ignored/untracked):
  `evidence/issue-1468-post-v082-20261120/`. Verification results:
  **4/4 V08 PASS; 1/1 Grafana V02 PASS**. Offline comparison completed
  `bounded_counter_window_overlap`, `synthetic=false`.
- The independent Grafana verifier establishes report arithmetic and file
  integrity, **not independently observed kernel cgroup identity**.
  Intra-invocation identity is asserted by its collector, not across runs.
- Report SHA-256 (sanitized `report.json` only, order: V02, V08-01..04):
  - Grafana V02: `4bc5885429d72bc70dcbb10d246ea05b093ad5bc17dc8be39a7f3510331146d1`
  - V08-01: `99fb35b8577438bc3184e16a361b225e1a20e40e43f9a5a4fafc54151a29bf11`
  - V08-02: `1ca0c4a0fd44fc43a8bfa2126affd7a6af1e4724222f406370f1a785b0df7421`
  - V08-03: `3e9ddf64dc76122144fbdc277cfaa648f10db260554b3ced269602ef46312fcf`
  - V08-04: `19ecf6ea7a5c015e8a33f15d2c2bf2bf6e2b4aa729d45802fe3631cb685ad21d`

## Numeric evidence

The Grafana V02 observation window was **2026-11-20 19:02:18–19:03:18 UTC**,
60 seconds in one verified collector invocation. Its cgroup
`memory.max=314572800 bytes` (**300 MiB**). The observed
`memory.current` was 312721408 bytes first and 313851904 bytes last
(about **299.3 MiB** last). Within this invocation,
`memory.events.local max` increased **17**, while `oom=0`
and `oom_kill=0`. An increase in `max` denotes memory-limit boundary
attempts, not an OOM or measured request slowdown. Cgroup
`memory.swap.current` was 119750656 bytes at the final observation
(occupancy, not a page-in/page-out rate).

The independently verified V08 v08.2.0 bundles recorded real-clock
UTC+monotonic envelopes around their actual kernel counter reads.
The following values are **per five-second sampled intervals only**:

| UTC start | MemAvailable (KiB) | Host swap used (KiB) | Swap-in pages | Swap-out pages | Major faults | Host OOM kills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 19:02:20 | 1382144 | 2198064 | 84 | 0 | 84 | 0 |
| 19:02:27 | 1393120 | 2193968 | 1027 | 1408 | 1279 | 0 |
| 19:02:35 | 1399952 | 2190896 | 108 | 70 | 116 | 0 |
| 19:02:42 | 1341344 | 2190896 | 81 | 161 | 95 | 0 |
| **Sampled sums** | — | — | **1300** | **1639** | **1574** | **0** |

- MemAvailable ranged **1341344–1399952 KiB** of **4146944 KiB**
  physical host RAM reported by the collector (roughly 32–34%).
- Retained host swap occupancy declined from **2198064** to
  **2190896 KiB** between the first and final samples. This point-in-time
  decline does **not** negate observed swap activity.
- Swap-out was nonzero in **3/4** short samples. These discontinuous
  windows cover only 20 seconds of counters, not the entire 60-second
  Grafana interval; their totals must not be represented as 60-second rates.
- Memory PSI was **unavailable in 4/4** samples; it is **unknown**, not
  measured zero. Kernel journal was intentionally excluded. No current
  PSS, true per-container peak, or representative idle/busy workload
  classification was established in this one-shot.
- All four **bounded vmstat counter intervals** overlapped the Grafana
  V02 observation span. Correlation classification was
  `bounded_counter_window_overlap`, but
  **`verified_same_window=false`** and **`proven_causation=false`**
  remain invariant: overlap does not establish the instant of individual
  `max` or host paging events, and it does not identify Grafana as the
  cause of host swap.

## Interpretation and next decision gate

**Confirmed:** this RPi5 had active sampled paging and significant
historically occupied swap, while Grafana approached its 300 MiB
cgroup cap and recorded 17 boundary attempts without new OOM events.
**Not established:** a memory leak, thrashing, host-wide chronic shortage,
a causal link to Grafana, impaired dashboard/API performance, or a
representative difference between idle and busy workloads.

For context, the [2026-11-16 baseline](RPI5_MEMORY_BASELINE_20261116_1468.md)
recorded 6 Grafana max events in a different 45-second window and 195
host swap-out pages over four separate samples. Those runs used
different time windows and workload circumstances, and older coarse
V08 timestamps; the counts **must not** be added or interpreted as a
performance regression or improvement. Similarly the older
2026-11-15 Grafana 109 max events belong to a separate 180-second run.

**Decision:** keep Grafana's **300 MiB** cap and current host settings.
`#1468` remains OPEN and `#1469` stays evidence-gated.
A useful next diagnostic needs an independently supported naturally
occurring idle-versus-busy comparison and **same-window Grafana request
error/latency evidence** from a separately validated, safely accessible
aggregate source. Do **not** repeat a near-identical V08/V02 run without
a new hypothesis. If safe service-health metrics are unavailable,
record that gap rather than expanding to private `/metrics`, raw
scrape configs, dashboards or credentials.

**STOP / NO_LIVE_AUTHORITY:** this source document neither authorizes
new RPi5 evidence writes nor a host, Docker, Grafana, swap/zram,
service/timer, database or production change. The original one-shot
authorization is consumed. New LIVE collection or any resource limit
change requires separate exact owner authority. Merge of this
documentation is a separate owner gate and never implies LIVE permission.

See [composite contract](GRAFANA_HOST_MEMORY_COMPOSITE_1468.md),
[V08 contract](V08_MEMORY_PRESSURE_DIAGNOSTIC_CONTRACT.md), and
[Grafana health evidence boundary](GRAFANA_HEALTH_CORRELATION_1468.md).
