# V08 memory-pressure diagnostic contract

V08 implements the read-only diagnosis phase of issue #5. It collects a bounded, sanitized evidence bundle for deciding whether the RPi5 has active memory pressure or merely retained swap.

## Collected metadata

The collector records only:

- allowlisted `/proc/meminfo` values;
- memory PSI start/end samples;
- allowlisted `/proc/vmstat` counters and their short-window deltas;
- swap type, size, used amount and priority without backing-file paths;
- zram size/compression counters where available;
- aggregated process names and RSS, without PID arguments or environments;
- current per-container usage, limit, percentage and PID count from `docker stats`;
- at most 100 recent kernel lines matching OOM or memory-cgroup terms, with IP, MAC and long hexadecimal identifiers redacted.

The collector refuses root, uses fixed command argument lists and timeouts, caps every section, writes with restrictive permissions, and creates checksums plus a deterministic JSON/Markdown report under ignored `evidence/` or `exports/` paths.

## Explicit exclusions

V08 does not read process command lines, container environments, `docker inspect`, raw DNS queries, AdGuard credentials or configuration, database contents, backups, Docker volumes or application data. It does not restart services, clear swap, tune zram, add memory limits, deploy or remediate.

## Observation level

The report level is a deterministic review hint, not a diagnosis:

- `attention`: swap moved during the sample, full-memory PSI increased, or an OOM-kill counter increased;
- `informational`: swap is retained or MemAvailable is below 20%, without observed active-pressure signals;
- `none`: neither condition was observed.

A short sample can miss intermittent pressure. Root-cause conclusions require repeated verified bundles under comparable idle and busy periods.
