# V11 AdGuard memory attribution contract

V11 attributes the Linux memory classes behind the exact `AdGuardHome` process and `adguard` container. It is a bounded, non-root, read-only extension of issue #27. The broader host-pressure investigation in issue #5 was concluded separately from controlled workload-removal and V08/V09 idle-series evidence.

## Collected data

The collector records only allowlisted numeric metadata:

- aggregate `/proc/<pid>/status` values for exact `AdGuardHome` process names;
- aggregate `/proc/<pid>/smaps_rollup` RSS/PSS values when readable without elevation;
- process/thread counts and file-descriptor counts without resolving descriptor targets;
- cgroup-v2 `memory.current`, `memory.peak`, `memory.swap.current`, `memory.max`, `memory.events`, and allowlisted `memory.stat` values;
- one exact `docker stats` row for the container name `adguard`.

Process IDs, cgroup paths, container IDs, file names, sockets, DNS queries, client identities, process arguments, environments, and raw configuration are not emitted.

## Attribution precedence

The report uses the strongest available source in this order:

1. process proportional-set-size values from `smaps_rollup`;
2. cgroup current/anonymous/file/shmem counters;
3. process RSS anonymous/file/shmem values.

The dominant component is reported only when one class accounts for at least 50% of the selected basis. Anonymous dominance identifies application-private or Go-runtime memory, but does not prove which AdGuard subsystem owns that heap.

## Four-sample live series

Issue #27 requires at least four verified live V11 samples before the Linux-level root-cause conclusion is updated. The supported one-command workflow is:

```bash
python3 scripts/collect-adguard-memory-series.py \
  --output evidence/v11-adguard-series-$(date -u +%Y%m%dT%H%M%SZ)
```

The production interval defaults to 300 seconds, giving a fifteen-minute four-sample window. Production intervals shorter than 60 seconds or longer than 1800 seconds are rejected.

For each sample the series collector:

1. invokes the existing bounded V11 single-sample collector;
2. immediately invokes the existing strict single-sample verifier;
3. retains the sample only when verification succeeds;
4. waits the configured interval before the next sample;
5. requires all four reports to bind to the same exact 40-character Git commit;
6. requires strictly increasing UTC collection timestamps;
7. computes only deterministic Linux-memory-class and bounded container-trend facts;
8. writes canonical `series.json`, deterministic `series.md`, and checksums;
9. invokes the independent series verifier after the atomic final rename;
10. removes the final output again if series verification fails.

The series summary reports per-sample attribution basis, dominant component, anonymous/file/shared memory, process/cgroup swap, kernel memory, container memory/limit percentage and cgroup OOM counters. It also reports first/last/min/max/change for container use when Docker stats are available for all four samples.

The series deliberately does **not** call a monotonic increase a leak. Its interpretation boundary states that four samples establish Linux memory-class and bounded trend evidence only; identifying DNS cache, query-log buffering, statistics, filtering structures, runtime clients, or another Go heap owner would require separately approved application-level evidence.

## Test-fixture boundary

All environment overrides used by synthetic V11 tests are fail-closed and test-only. `ADGUARD_ATTR_TEST_UID`, fixed commit/time values, Docker-disable and no-sleep controls are accepted only when both fake proc and fake cgroup roots are explicitly supplied and resolve beneath this repository's ignored `evidence/` or `exports/` trees.

Test overrides are rejected when either root is the real `/proc` or `/sys/fs/cgroup`, when only one root is supplied, when a root escapes the ignored fixture trees, or when a test-only override is supplied without fixture mode. Therefore `ADGUARD_ATTR_TEST_UID=1000` cannot be used to bypass the production root-execution refusal against real host data.

Fixture mode also skips the five-minute wait only through the test-only `ADGUARD_ATTR_TEST_NO_SLEEP=1`; a fixed fixture timestamp is then required and the four synthetic samples receive deterministic strictly increasing timestamps.

## AdGuard-specific hypotheses

Official AdGuard Home configuration documentation identifies several settings that may affect heap or retained data:

- `dns.cache_size` controls DNS cache size in bytes;
- `querylog.size_memory` controls the number of query-log entries retained in memory before flushing;
- `statistics.interval` controls statistics retention;
- filter rules, runtime clients, safe-browsing/search/parental caches, and client-specific upstream caches may also retain memory.

AdGuard Home supports Go `pprof`, but enabling it requires configuration and a restart. V11 does not enable profiling, read raw configuration, or claim an internal owner without application-level evidence.

## Output and verification

A single-sample collector writes a new atomic bundle only below ignored `evidence/` or `exports/` paths. The bundle contains canonical JSON, deterministic Markdown, a strict file inventory, checksums, and bounded section files. The verifier rejects path escapes, symlinks, hard links, unexpected ownership, unsafe file types, oversized artifacts, secret-like content, checksum mismatches, malformed metrics, report tampering, and Markdown drift.

A series root contains exactly `samples/01` through `samples/04`, `series.json`, `series.md`, and `SHA256SUMS`. The series verifier re-runs the strict single-sample verifier for all four sample directories, recomputes the deterministic summary, checks canonical JSON/Markdown equality, and verifies checksums that bind the summary to each sample's `report.json`.

## Safety boundary

V11 does not use `sudo`, `docker inspect`, process command lines, container environments, raw AdGuard configuration, DNS-query capture, client exports, service or container restarts, swap clearing, zram tuning, Docker mutation, deployment, or remediation.

The four-sample production collector is observational only. It executes four bounded reads and `docker stats --no-stream`; it does not change the `adguard` container, DNS behavior, memory limits, host swap, zram, or any service state.

A future heap profile or configuration change requires separate explicit approval, an exact commit binding, DNS health checks, rollback instructions, and evidence that the safer Linux-level attribution is insufficient.
