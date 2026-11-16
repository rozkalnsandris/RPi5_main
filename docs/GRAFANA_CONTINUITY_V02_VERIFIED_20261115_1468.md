# Grafana V02 — verified within-invocation cgroup observations (#1468)

**Status: verified bounded LIVE diagnostic, no configuration or service change. #1468 OPEN.** This is a sanitized documentation record, not an authorization to collect again. Raw evidence stays ignored on RPi5.

## Provenance and measurement boundary

- Host: RPi5; unprivileged one-shot collector `scripts/collect-grafana-continuity.py` and independent offline verifier `scripts/verify-grafana-continuity.py`, installed source SHA `140f51fa55d0a66ad6da6d551bc6dc36b5a54718` (merged PR #1494), collector version `v01.0.0`, schema `rpi5.grafana-cgroup-continuity.v1`.
- Two *separately* owner-authorized invocations on 2026-11-15. Each preflight checked source, nonroot identity, clean tracked checkout, exact unused output and Grafana cgroup access. Each capture sealed an ignored local bundle, reported offline verifier PASS, and independently repeated offline verification PASS after completion.
- Local-only bundles: `evidence/grafana-1468-continuity-v02-20261115-a/` and `evidence/grafana-1468-continuity-v02-window-b/`; neither raw report, manifest nor identifying runtime metadata is committed.
- Collector verified a pinned directory FD, exact Docker/process identity and process start time **within-invocation**. The verifier checks the report's schema, arithmetic and integrity, **not** historical kernel or Docker identity independently. No identity continuity is claimed across the two invocations or back to the 37-second V01 descriptive snapshots.

## Window A — two samples, 15-second spacing

- UTC: `2026-11-15T22:00:32Z` to `2026-11-15T22:00:47Z`; monotonic elapsed **15,034 ms**.
- `memory.max` = 300.00 MiB at both samples.

| Numeric field (MiB) | Sample 1 | Sample 2 |
| --- | ---: | ---: |
| `memory.current` | 245.98 | 260.02 |
| `memory.swap.current` | 143.95 | 140.84 |
| `memory.peak` (historical) | 300.03 | 300.03 |

- Local `memory.events.local` within-run deltas: `max=0`, `oom=0`, `oom_kill=0`. Hierarchical `memory.events` deltas identical.
- Independently verified `report.json` SHA-256: `22d00a74b9bab15fcc18a48825bd498996fee4aa627d612a92691cf7cb40d37a`.

## Window B — four samples, 60-second spacing

- UTC: `2026-11-15T22:08:09Z` to `2026-11-15T22:11:09Z`; monotonic elapsed **180,037 ms**.
- `memory.max` = 300.00 MiB at all four samples.

| Numeric field (MiB) | Sample 1 | Sample 2 | Sample 3 | Sample 4 |
| --- | ---: | ---: | ---: | ---: |
| `memory.current` | 299.55 | 299.80 | 298.89 | 296.80 |
| `memory.swap.current` | 133.80 | 128.34 | 128.53 | 127.02 |
| `memory.peak` (historical) | 300.03 | 300.03 | 300.03 | 300.03 |

- Local `memory.events.local` within-invocation deltas: **`max=109`, `oom=0`, `oom_kill=0`**. Hierarchical `memory.events` deltas identical.
- Independently verified `report.json` SHA-256: `3a614893f63a56bd57d4a5b6d4416c1ebd91ab27939db0c4963a013f3cccc27c`.

## Interpretation and decision gate

1. Window B shows **repeated attempts to exceed the 300 MiB cgroup hard memory boundary**, according to Linux `memory.events max`, with **no recorded cgroup OOM or OOM kill** in that invocation. The count is events, not seconds blocked, processes killed, errors, latency, or direct evidence of user impact. Window A's zero does not negate window B.
2. `memory.current` is the charged cgroup memory, **not** the cache-adjusted Docker CLI working set or Grafana process-exclusive RSS/PSS. The 300.03 MiB `memory.peak` is a historical cgroup high-water value, **not** a peak measured over either diagnostic window. The `memory.swap.current` decrease is occupancy change, **not** host swap-in/swap-out activity or a rate.
3. These windows lack independent workload/activity labels, aligned host paging or PSI evidence (PSI was previously unavailable), and Grafana request latency, dashboard/query performance, availability, plugin activity and **same-window** independently measured service-health indicators. An independently authorized successful API/database health GET was performed later (see [health-correlation evidence and remaining gates](GRAFANA_HEALTH_CORRELATION_1468.md)); it was **not** synchronized with either V02 window. They cannot establish which Grafana work caused the events, a memory leak, sustained host-wide pressure or a service-health regression.
4. **Recommendation:** retain the current 300 MiB cap until a separately authorized, bounded comparison records synchronized activity and permitted service-health data. Do not reduce or raise the limit merely because `max=109`; first determine whether near-limit reclaim has observable service impact. #1469 optimization remains evidence-gated. **#1468 stays OPEN.**

Kernel references: [cgroup v2 `memory.events` / `memory.peak`](https://docs.kernel.org/admin-guide/cgroup-v2.html); [Docker Linux CLI memory accounting](https://docs.docker.com/reference/cli/docker/container/stats/). No Docker/systemd/swap/configuration change, deployment, new collection or issue closure is authorized by this source report.
