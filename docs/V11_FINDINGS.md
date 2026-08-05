# V11 AdGuard memory attribution findings

## Starting evidence

The verified V09 idle series showed that the host was not under sustained memory pressure:

- MemAvailable remained 39.59–40.39%;
- swap usage decreased by 20 MiB;
- four sampled windows contained 8 swap-in pages, 0 swap-out pages, 0 PSI time, and 0 OOM kills;
- AdGuard moved from 436.10 MiB to 438.40 MiB, a correct increase of 2.30 MiB.

This does not demonstrate a leak, but AdGuard remains the largest steady container and uses about 87.7% of its 500 MiB limit.

## Official-source review

AdGuard Home exposes multiple configurable memory contributors: DNS cache size, query-log in-memory entry count, statistics retention, filtering structures, runtime clients, and protection caches. The project also supports Go `pprof` for heap attribution. Public reports of high memory usage exist, but they cover different versions and configurations and do not establish the cause on this host.

Therefore the next evidence must first determine whether the container is dominated by anonymous application memory, file-backed cache, shared memory, kernel/socket memory, or swap. Only anonymous dominance plus verified growth would justify considering a separately approved heap profile or settings audit.

## Tooling result

V11 adds a bounded collector and strict verifier for that Linux-level attribution. Synthetic tests cover:

- PSS-based anonymous dominance;
- cgroup fallback when `smaps_rollup` is unavailable without elevated privileges;
- exact Docker unit and limit-headroom arithmetic;
- deterministic output;
- rejection of root execution, missing process identity, path escape, symlink output, hard links, and tampered reports;
- prevention of cgroup-path leakage.

No live V11 bundle is committed. A minimum of four verified live samples is required before the root-cause conclusion is updated.

## Safety

No AdGuard configuration, DNS queries, client data, process arguments, container environments, Docker inspect data, service state, swap, zram, or production settings are changed by this phase.
