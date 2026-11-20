# Grafana HTTP health versus cgroup memory cap: verified one-shot evidence (2026-11-20, #1468)

**VERIFIED BOUNDED HEALTH OBSERVATION. NO COMPREHENSIVE PERFORMANCE PROOF, CAUSAL ATTRIBUTION OR LIVE AUTHORITY.**

This document records a *completed* owner-authorized `GRAFANA-HTTP-CORRELATION` one-shot on `rpi5`; no new host execution is authorized by this report. Sanitized raw evidence remains ignored and untracked under `evidence/issue-1468-grafana-http-20261120/`.

## Owner authority, provenance and guardrails

- Target repository: `rozkalnsandris/RPi5_main`. Before the one-shot, GitHub `main` and green required CI were verified at `fc2b33d7f35e4035171c16f5a92eff7cab720f61`. Local RPi5 `main` was **clean** at `ffa06004b0e23af489a5b7d475b5d02d6ded9182`, exactly one documentation-only commit behind GitHub `main`. No checkout update or deployment was authorized or performed.
- The separately explicit owner envelope allowed **one** Grafana V02 4-sample collection at 20-second intervals; **four** timed, unauthenticated Grafana container-local `GET http://127.0.0.1:3000/api/health` requests, each with a 5-second HTTP timeout; and ignored, bounded, allowlisted evidence writes. A non-root caller and preexisting in-container `curl` were verified first.
- The four `docker exec grafana curl` calls were individually run with a hard subprocess timeout. Timing is **transport-inclusive**, including Docker CLI/container-exec overhead, not exclusively Grafana's server-side processing time. Only four allowlisted fields were written per request: `utc`, `http_status`, `elapsed_ms`, `database_ok`. No raw HTTP body, credentials, labels, private metrics, dashboard, command line, internal URL metadata or protected configuration was persisted.
- An independent offline Grafana V02 verifier reported **PASS**. A separate read-only postflight checked exact ignored directory membership, `0600` HTTP evidence file modes, each of the four sanitized field allowlists and time containment in the V02 observation interval. It exited **0**. Local Git checkout remained clean.

## Verified window and results

- Grafana V02 window: **2026-11-20 20:32:38–20:33:38 UTC** (4 observations, 20-second interval, 60 seconds end to end).
- Effective Grafana cgroup `memory.max`: **314572800 bytes (300 MiB)**.
- Grafana `memory.current` at first/last V02 snapshots: **311558144 / 312606720 bytes**.
- Grafana `memory.events.local` delta: **`max=49`, `oom=0`, `oom_kill=0`**. `max` is a memory-cap boundary event, **not** an OOM kill, service failure or measured latency impact.
- All four HTTP requests fell within the Grafana V02 window (allowing the bounded measured execution duration), and returned **HTTP 200** with `database_ok=true`.

| GET number | HTTP status | Transport-inclusive duration | Database |
| --- | ---: | ---: | --- |
| 01 | 200 | 76 ms | OK |
| 02 | 200 | 83 ms | OK |
| 03 | 200 | 98 ms | OK |
| 04 | 200 | 71 ms | OK |

Four-GET mean = **82 ms**; observed maximum = **98 ms**. These are small-sample point observations, not an error-rate estimate, statistical p95/p99, benchmark or an application SLO assertion.

### Evidence integrity: sanitized `report.json`/HTTP JSON SHA-256

- Grafana V02 `report.json`: `94a668a12a240b78feb972742a901afac7398d7d606a99ee6a775214c78eebd3`
- HTTP 01: `002b5058c614ad3d42a1a7fe45dda1794f928b788e1d9b0b5115d64c8e608579`
- HTTP 02: `6c0a7afd8c804a142e074a7b8cf4f9e855ca91886b0fddf458d62f5f969e9542`
- HTTP 03: `e6b1e03abd64989089e922088eada276fdcc5ca82a1ef4101153f079e5e76906`
- HTTP 04: `831bb0999981b9892440cd53c726d98441d78f275859f8d86277d11c820f6a1b`

## Inference limits, decision and next evidence gate

**Established:** Grafana's unauthenticated, lightweight database-health endpoint responded successfully during the 60-second cgroup observation despite 49 `memory.events.local max` events. No new Grafana OOM events were measured. The metric does not pinpoint the time of each `max` event; no per-HTTP-request event causality can be inferred.

**Not established:** Grafana dashboard/query latency, authenticated traffic, request error-rate under representative load, background worker health, a time-matched *idle versus naturally busy* baseline, tail latency, any long-term trend or whether Grafana contributed to previously observed host swap. The test's `docker exec` overhead makes it unsuitable for direct server-latency attribution. A single health endpoint returning HTTP 200 does not prove other endpoints or production workflows are healthy.

**Decision:** keep the Grafana **300 MiB** cap and host settings unchanged. Issue **#1468 remains OPEN**, and optimization issue **#1469** remains evidence-gated. Do not repeat an identical health GET merely to increase counts. A useful further step would be to identify an *existing, appropriately approved* non-sensitive Grafana request-latency/error aggregate and capture it only under a new, exact, bounded owner LIVE authorization alongside naturally occurring idle/busy workload labels. Prior Prometheus selectors did **not** confirm Grafana performance series; do not presume them available or expand into private `/metrics`, raw scrape configs, labels, dashboards or credentials.

**STOP / AUTHORITY CONSUMED:** this report grants **no permission** for new HTTP calls, evidence writes, protected runtime inspection, `git fetch`, checkout mutation, service/Docker/timer changes, Grafana memory limit changes, swap/zram tuning, retries, rollback, cleanup, or production deploy. Merge of this source-only document is separately owner-gated and is not LIVE authorization.

See [2026-11-20 V08.2 memory baseline](RPI5_MEMORY_BASELINE_20261120_1468.md), [Grafana health evidence boundary](GRAFANA_HEALTH_CORRELATION_1468.md) and [Grafana continuity contract](GRAFANA_CONTINUOUS_CGROUP_IDENTITY_CONTRACT_1468.md).
