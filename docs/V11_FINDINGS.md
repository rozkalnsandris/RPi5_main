# V11 AdGuard memory attribution findings

## Starting evidence

The verified V09 idle series showed that the host was not under sustained memory pressure:

- MemAvailable remained 39.59–40.39%;
- swap usage decreased by 20 MiB;
- four sampled windows contained 8 swap-in pages, 0 swap-out pages, 0 PSI time, and 0 OOM kills;
- AdGuard moved from 436.10 MiB to 438.40 MiB, a correct increase of 2.30 MiB.

This does not demonstrate a leak, but AdGuard remains a large steady container and uses about 87.7% of its 500 MiB limit.

The broader host-pressure issue #5 has since been concluded separately. A controlled VS Code Remote/Codex shutdown materially improved `MemAvailable` and reduced logical zram/swap use without touching AdGuard, while the verified V08/V09 idle series showed no sustained swap-out, PSI, or OOM pressure. That evidence supports the development session as the main transient contributor to the original host-pressure event. It does not answer the narrower issue #27 question of what Linux memory class accounts for AdGuard's steady footprint.

## Official-source review

AdGuard Home exposes multiple configurable memory contributors: DNS cache size, query-log in-memory entry count, statistics retention, filtering structures, runtime clients, and protection caches. The project also supports Go `pprof` for heap attribution. Public reports of high memory usage exist, but they cover different versions and configurations and do not establish the cause on this host.

Therefore issue #27 must first determine whether the container is dominated by anonymous application memory, file-backed cache, shared memory, kernel/socket memory, or swap. Only stable anonymous dominance plus a separately verified growth pattern would justify considering a separately approved heap profile or settings audit. Anonymous dominance alone identifies private/Go-runtime memory, not a specific AdGuard subsystem.

## Tooling result

The first V11 implementation added a bounded collector and strict verifier for single-sample Linux-level attribution. Synthetic tests covered:

- PSS-based anonymous dominance;
- cgroup fallback when `smaps_rollup` is unavailable without elevated privileges;
- exact Docker unit and limit-headroom arithmetic;
- deterministic output;
- rejection of root execution, missing process identity, path escape, symlink output, hard links, and tampered reports;
- prevention of cgroup-path leakage.

A review of the remaining #27 acceptance criteria found two gaps before live collection should proceed:

1. **Test-environment override hardening.** The original collector honored `ADGUARD_ATTR_TEST_UID` directly. Although intended only for synthetic tests, that made the root-refusal boundary weaker than the rest of the collector contract. Test-only UID/time/commit/Docker/no-sleep controls are now accepted only with explicit fake proc and cgroup roots beneath ignored repository `evidence/` or `exports/` fixture trees, and are rejected against real `/proc` or `/sys/fs/cgroup`.
2. **Four-sample evidence workflow.** The issue required at least four verified live samples but only exposed a single-sample command. The new series collector runs four samples, verifies each immediately, binds all four to one exact Git commit and strictly increasing UTC timestamps, computes a deterministic non-causal trend summary, writes atomically, and runs an independent series verifier over the final result.

The default live workflow is a fifteen-minute window with four samples five minutes apart. The summary reports stable/variable Linux memory class, container first/last/min/max/change, limit usage, swap values and OOM counters, while explicitly refusing to label monotonic growth as a leak.

## Remaining live evidence gate

No four-sample live V11 series is claimed by this repository change. Issue #27 remains open until a real RPi5 series is collected with the merged tooling, the independent verifier passes, and the resulting four reports are interpreted.

The supported post-merge read-only command is:

```bash
python3 scripts/collect-adguard-memory-series.py \
  --output evidence/v11-adguard-series-$(date -u +%Y%m%dT%H%M%SZ)
```

If all four samples show stable anonymous dominance, the justified conclusion is that AdGuard's footprint is primarily private/application (Go-runtime) memory at the Linux level. That still does not identify whether DNS cache, query-log buffering, statistics, filtering structures, runtime clients, or another heap owner is responsible. If the four samples vary materially or show a different dominant class, the next step must follow that observed class rather than assuming a heap leak.

## Safety

No AdGuard configuration, DNS queries, client data, process arguments, container environments, Docker inspect data, service state, swap, zram, or production settings are changed by this phase. The new series workflow remains non-root and read-only and performs only four bounded V11 collections plus verification.
