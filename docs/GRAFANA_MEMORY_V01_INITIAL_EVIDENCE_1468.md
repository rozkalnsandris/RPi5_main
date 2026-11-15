# Grafana V01 — initial sanitized RPi5 evidence (#1468)

**Status:** Two verified initial samples; **#1468 remains OPEN**. No same-cgroup event-delta proof, host swap attribution, RAM optimization or LIVE permission is implied.

## Provenance

- Owner-authorized bounded `GRAFANA-V01-INITIAL-DIAGNOSTIC` on `rpi5`, 2026-11-15. Authorized scope: one `git fetch`, one fast-forward-only host checkout update, non-root Grafana-only numeric reads, two immutable snapshots, independent verification and one descriptive series. No other host/runtime change was authorized.
- Exact installed source SHA at collection: `65eba8930ebfda18ec7e4fe7656e0f92f31f92e7`. The host checkout update was verified clean after the collection.
- Snapshot UTC: `2026-11-15T12:29:36Z` and `2026-11-15T12:30:13Z` (**37 seconds apart**). These are not distinct naturally representative idle/busy workload periods.
- Both per-snapshot verifications: **PASS**; independent series verification: **PASS**. Series outputs `comparison=descriptive_only`, `same_cgroup_identity=unproven`, `cgroup_oom_event_deltas=null`.
- Raw reports retained only in ignored RPi5 `evidence/grafana-1468-v01-20261115-a`, `evidence/grafana-1468-v01-20261115-b`, and `evidence/grafana-1468-v01-20261115-series`; **not committed**. No PID, container ID, cgroup path, protected configuration or secrets are present in this document.

## Verified numeric findings

| Field | A | B |
| --- | ---: | ---: |
| Docker CLI displayed memory working set | 259.00 MiB | 261.40 MiB |
| Docker displayed limit | 300.00 MiB | 300.00 MiB |
| cgroup `memory.current` | 297.67 MiB | 294.36 MiB |
| cgroup `memory.max` | 300.00 MiB | 300.00 MiB |
| cgroup `memory.peak` (historical) | 300.03 MiB | 300.03 MiB |
| cgroup `memory.swap.current` | 131.53 MiB | 135.33 MiB |
| cgroup `memory.stat` anonymous | 189.47 MiB | 183.03 MiB |
| cgroup `memory.stat` file | 98.61 MiB | 101.64 MiB |
| cgroup `memory.stat` kernel | 8.95 MiB | 8.95 MiB |
| Historical hierarchical `memory.events max` | 30664 | 30670 |
| Historical local `memory.events.local max` | 30664 | 30670 |
| Hierarchical and local `oom` / `oom_kill` | 0 / 0 | 0 / 0 |

For both samples the collector classified `observation_level=informational`, `basis=cgroup_current`, and `dominant_component=anonymous`. These are Linux accounting categories; they do not prove a Grafana leak or an application-specific cause. Docker's cache-adjusted display is not equivalent to the cgroup charge. `memory.peak` is a historical high-water mark, not a 37-second sample peak.

## Uncertainty and classification

- **Cgroup identity continuity remains unproven.** The individual snapshot collector verified the process/container binding during each acquisition, but the sanitized reports intentionally omit the identifier needed to confirm that it is the same cgroup across snapshots. The differing cumulative `max` counters must **not** be interpreted as new attributable cgroup events; `cgroup_oom_event_deltas=null`.
- **Near-limit charge is a diagnostic signal, not an OOM or health failure.** The two available historical OOM and OOM-kill counters are zero. The `max` counter can increment without OOM kills.
- **Swap occupancy is not a swap-in/out rate.** The difference in `memory.swap.current` is not proof of active host paging or proof that Grafana caused the host-wide swap activity. Host PSI was unavailable in earlier baseline evidence; its state remains **unknown**, not zero.
- **Representative workload, process PSS, service-health correlation, simultaneous host paging rates and continuous same-cgroup identity proof are missing.** Two snapshots over 37 seconds do not establish sustained or transient host pressure.

## Read-only report extraction incident

After both snapshot verifiers and the independent descriptive-series verifier had already passed, an auxiliary read-only Python report snippet failed with `KeyError: 'memory_stat'`. The correct schema key is `cgroup.memory_stat_bytes`. A later, separately authorized **read-only** inspection of the same stored reports succeeded and produced the anonymous/file/kernel and event values above. No new collection, retry, rollback, cleanup or host setting change occurred in that follow-up.

## Next decision gate

**#1468 stays OPEN.** Before attributing new Grafana OOM/max events or adjusting #1469 RAM budgets, review a separate source-only continuous-identity measurement/verifier design and collect multiple naturally separated representative windows (plus host paging-rate and service-health correlation) **only after new explicit LIVE authorization**. No container limit, service, deployment, OS migration or RAM optimization is justified or authorized by these two snapshots.
