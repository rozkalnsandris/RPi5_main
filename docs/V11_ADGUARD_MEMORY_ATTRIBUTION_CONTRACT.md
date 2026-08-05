# V11 AdGuard memory attribution contract

V11 attributes the Linux memory classes behind the exact `AdGuardHome` process and `adguard` container. It is a bounded, non-root, read-only extension of issue #5 and issue #27.

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

## AdGuard-specific hypotheses

Official AdGuard Home configuration documentation identifies several settings that may affect heap or retained data:

- `dns.cache_size` controls DNS cache size in bytes;
- `querylog.size_memory` controls the number of query-log entries retained in memory before flushing;
- `statistics.interval` controls statistics retention;
- filter rules, runtime clients, safe-browsing/search/parental caches, and client-specific upstream caches may also retain memory.

AdGuard Home supports Go `pprof`, but enabling it requires configuration and a restart. V11 does not enable profiling, read raw configuration, or claim an internal owner without application-level evidence.

## Output and verification

The collector writes a new atomic bundle only below ignored `evidence/` or `exports/` paths. The bundle contains canonical JSON, deterministic Markdown, a strict file inventory, checksums, and bounded section files. The verifier rejects path escapes, symlinks, hard links, unexpected ownership, unsafe file types, oversized artifacts, secret-like content, checksum mismatches, malformed metrics, report tampering, and Markdown drift.

## Safety boundary

V11 does not use `sudo`, `docker inspect`, process command lines, container environments, raw AdGuard configuration, DNS-query capture, client exports, service or container restarts, swap clearing, zram tuning, Docker mutation, deployment, or remediation.

A future heap profile or configuration change requires separate explicit approval, an exact commit binding, DNS health checks, rollback instructions, and evidence that the safer Linux-level attribution is insufficient.
