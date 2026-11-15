# Grafana memory/cgroup diagnostic preflight — RPi5 #1468

Status: **SOURCE-ONLY DESIGN; NOT EXECUTED ON RPi5**. Canonical issues: [#1468](https://github.com/rozkalnsandris/RPi5_main/issues/1468) (measure first), [#1469](https://github.com/rozkalnsandris/RPi5_main/issues/1469) (optimization decision). This document prepares a narrow, owner-gated, sanitized, non-root diagnostic; it does **not** authorize cgroup inspection, new evidence writes, memory limit changes or any service mutation.

## Why Grafana first

- The verified 2026-11-15 two-window V08/V09 evidence (see [#1468 evidence](https://github.com/rozkalnsandris/RPi5_main/issues/1468#issuecomment-6892984969)) recorded a **Docker CLI displayed** Grafana working-set peak of ~**280.8 MiB**, or **93.58% of its 300 MiB configured container limit**, in window A. Window B showed ~272.6 MiB / 90.85%. These are **sample maxima**, not process-exclusive memory, cgroup `memory.peak`, or demonstrated service failure.
- The official [Grafana installation/sizing guidance](https://grafana.com/docs/grafana/latest/setup-grafana/installation/) identifies **512 MB as the minimum recommended Grafana memory**; larger sizing tiers are intended for larger deployments. This is vendor guidance, **not a proof** that this particular small installation fails at 300 MiB. It argues **against further cap reduction** before measured evidence. The separate image renderer has its own memory budget.
- The 2026-11-15 series found `MemAvailable` ~36–38%, **zero OOM in the host V08 sample windows**, but intermittent substantial swap-in/out. Those host-wide page counters **cannot attribute** the activity to Grafana.
- `/proc/pressure/memory` is **unavailable** on this host. Preserve PSI as unknown; do not report measured zero.
- V11 [AdGuard attribution contract](V11_ADGUARD_MEMORY_ATTRIBUTION_CONTRACT.md) already provides a proven **pattern** for bounded cgroup-v2 and optional process-PSS evidence. Its executable collector is specifically **AdGuard-only** and must never be silently retargeted to Grafana without focused source tests, strict new allowlists and review.

## Official semantics — what to measure

| Candidate read-only source | Allowlisted interpretation | Important caveat |
| --- | --- | --- |
| `docker stats --no-stream grafana` | Displayed working set, limit, percent and PID count | On Linux the **CLI subtracts cache**; it does not equal raw cgroup `memory.current`. No Docker API, `inspect` or protected configuration needed. |
| cgroup v2 `memory.current` | Charged cgroup memory in **bytes** | Includes page cache/kernel components; not private RSS. Existence and readability are unverified until authorized preflight. |
| cgroup v2 `memory.peak` | High-water cgroup memory in **bytes** | Peak is since cgroup creation or last relevant reset, not a five-second measurement; **never write the file to reset it**. |
| cgroup v2 `memory.max` | Effective memory cap in **bytes** or `max` | Read only; do not change `memory.max`, `memory.high` or swap limits. |
| cgroup v2 `memory.swap.current` | Charged swapped memory in **bytes** | Occupancy is not a swap *rate* or disk IO; compare with host page-counter deltas separately. |
| cgroup v2 `memory.events.local` and `memory.events` | `low`, `high`, `max`, `oom`, `oom_kill`, `oom_group_kill` integer counters where available | Cumulative counters; compute deltas across the **same cgroup identity**. `max` events are not equivalent to `oom_kill`. |
| cgroup v2 `memory.stat` | Only `anon`, `file`, `shmem`, `kernel`, `sock`, `slab_reclaimable`, `slab_unreclaimable`, `pgfault`, `pgmajfault`, `pgscan`, `pgsteal` | All memory-category quantities are **bytes**; page/event counters are **counts**. Never assume `anon + file + kernel` exactly reproduces `memory.current`. |
| If separately permitted, process `/proc/<pid>/status` / `smaps_rollup` | Only `Name`, `VmRSS`, `VmSwap`, `RssAnon`, `RssFile`, `RssShmem`, `Pss`, `Pss_Anon`, `Pss_File`, `Pss_Shmem` | Processes may be short-lived; PSS may be unreadable without privilege. Never use `cmdline`, `environ`, `maps`, raw FDs or `docker inspect`. |

Canonical references: [Linux kernel cgroup v2](https://www.kernel.org/doc/html/v6.12/admin-guide/cgroup-v2.html), [Docker stats CLI](https://docs.docker.com/reference/cli/docker/container/stats/), [Docker runtime metrics](https://docs.docker.com/engine/containers/runmetrics/), [Grafana internal monitoring](https://grafana.com/docs/grafana/latest/setup-grafana/set-up-grafana-monitoring/).

## Proposed strict source-only collector contract (not yet implemented)

1. **Identity and preflight:** pin GitHub `main`, exact installed host checkout and tool hashes; prove current clean checkout, unprivileged user, cgroup **v2** capability and a distinct new ignored `evidence/` output target. Resolve the **single exact running** `grafana` container/process identity using allowlisted names/metadata. Check cgroup namespace/layout and identity stability at every sample; **fail closed on zero/multiple matches, path traversal, changing identity, unreadable required fields or controller mismatch**. Do not print PID, cgroup path, container ID or namespace details.
2. **Constrained retrieval:** process identity via `/proc/<pid>/comm` + validated `/proc/<pid>/cgroup` mapping (never read arguments, environments, raw configurations, mounts, socket targets or Docker protected runtime data); only the explicitly allowlisted cgroup/proc numeric fields above. **No generic privileged shell/execution interface.** Require an exact owner authorization for *any* cgroup/process inspection not already allowed by current repo/host policy.
3. **Timing and identity:** capture 4–8 bounded snapshots at fixed approved intervals in at least two naturally observed workload periods. Include UTC, sample duration, validated cgroup identity continuity as a non-identifying equality check and the **difference** of cumulative events. If the cgroup was recreated or `memory.peak` was reset, classify the pair as **incomparable**, do not invent a peak trend.
4. **Missing values:** represent unsupported/unreadable `memory.peak`, `memory.events.local`, PSS or PSI as **unknown/null** with explicit missing-data status. Do not turn absence into zero. On read failure or ambiguity after evidence collection starts, preserve only sanctioned read-only error evidence and **STOP**, without retries, cleanup or alternate mutation.
5. **Immutable outputs:** sanitize to key/value numeric data and fixed enum reasons; bound input/size/time; prevent symlink/hard-link/path-escape; atomic restrictive evidence bundle with canonical JSON/Markdown, inventory, SHA256 manifest, exact source SHA, and a strict independent verifier. **Raw cgroup paths, PID/IDs, URLs, secrets, logs and application data may not enter GitHub**.
6. **Evidence correlation:** compare `memory.events.local max/oom/oom_kill` deltas and `memory.current`/peak with Docker displayed working set, Grafana-only health/response-time indicators **only when existing approved metrics are available without credentials or configuration changes**, and host V08 swap activity. Do not equate nearby host churn to Grafana ownership without matching cgroup evidence.
7. **Offline regression tests:** synthetic v2 fixtures for stable IDs; `memory.peak` unavailable; `memory.max=max`; `events.local` missing; counter regression/identity drift; boundary and input caps; path traversal/symlink/hard-link; non-root; missing/multiple process matches; sanitized no-leak; checksum, report and Markdown tampering; deterministic reports. No production test mutation.
8. **Review gate:** add collector/verifier/tests only in a separate source-level PR **after scope acceptance**. Only a later **exact LIVE owner authorization** can permit host-local collection or report-file creation. A source merge does not provide LIVE permission.

## Grafana internal metrics option (no action authorized)

Grafana supports Prometheus-compatible internal performance/HTTP metrics. First check the **existing authorized monitoring surface** (e.g., pre-existing aggregate time series) if it is already exposed without protected config, credentials or service changes. Enabling scraping or new endpoints could require application configuration, restarts, service exposure or Prometheus configuration and is **outside this scope**. Do not probe private `/metrics` endpoints or enable profiling without explicit separate approval.

## Decision rules

- **No change** if there are no new cgroup `max`/`oom`/`oom_kill` deltas and no verified health/performance regression; maintain monitoring and repeat measurements during naturally distinct workloads as authorized.
- **Investigate peak/limit headroom** if verified cgroup peak approaches `memory.max` or nonzero *new* `max` events appear, even without OOM kills; check Grafana query/dashboard/alerting demands from approved aggregate metrics before proposing a limit change.
- **Urgent reliability review** if `oom`/`oom_kill` deltas or service health regressions are verified. Any limit increase, query/cache tuning, renderer change, cgroup configuration or restart requires its own scoped change and separate owner LIVE gate.
- **Never claim saved RAM from lowering a limit**: a limit is a ceiling, not a decrease in memory actually held. Reevaluate #1469 only after measured benefit and no degradation of DNS, Home Assistant, Grafana, Prometheus or Hermes.

**Current outcome:** Grafana is a high-priority **diagnostic candidate, not an identified fault**. The repeated host swap activity remains unattributed; observed available RAM and absent host OOM argue against emergency OS migration or blanket memory caps.

## Source-level Grafana V01 implementation (#1468)

This phase includes a bounded, non-root **Grafana-only snapshot** collector, strict verifier, and synthetic regression fixtures. Exact Grafana process identity and Docker CLI row are required. The cgroup-v2 snapshot contains `memory.current`, `memory.peak`, `memory.max`, `memory.swap.current`, `memory.stat`, hierarchical `memory.events`, and optional `memory.events.local`; missing local events are represented by **null**, not zero. Source files: `scripts/collect-grafana-memory-attribution.py`, `scripts/grafana_memory_core.py`, `scripts/verify-grafana-memory-attribution.py`, `tests/test-grafana-memory-attribution.sh`.

**Important limitation:** this initial source tool captures **one snapshot**; `memory.events` values are cumulative history, *not* delta proof. The specified in-sample identity checks, multi-window event-delta verifier, and health correlation still require an independently reviewed source-only follow-up before attributing RAM pressure to Grafana. It has **not been run on RPi5**; a source merge is **not** LIVE permission. No changes to actual cgroup/container limits, Grafana runtime, PSS privileges, credentials, Docker or services are authorized.

## Grafana process/cgroup identity correction

The collector now reads only allowlisted `docker ps --no-trunc --filter name=^/grafana$` ID/name metadata (not `docker inspect`). It requires exactly one running container and one process whose cgroup leaf matches that same full Docker ID (`/docker/<id>` or `/system.slice/docker-<id>.scope`). The runtime identifier is never published. A second identity check immediately before writing the final evidence target rejects drift. Unrelated or unsupported cgroups are rejected rather than misattributed. This source-only change is not a LIVE authorization.
