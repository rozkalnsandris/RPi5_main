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

## PSI availability (v08.1.0; #1468)

PSI is considered measured only if **both** start/end reads succeed. New bundles record `psi_available=false` and null deltas when absent, with explicit unavailable Markdown. The verifier still accepts historical v08.0.0 bundles unchanged; old placeholder zeros are **not measured** PSI, so consumers must consult section-status metadata.

## Explicit kernel-journal opt-out (#1468)

The V08 CLI now accepts `--skip-kernel-events`. When selected it **never
invokes `journalctl`**, writes an empty `kernel_memory_events.txt`,
marks the section unavailable (`command_available=false`, exit status 127),
and reports that kernel events are **unknown**, not absent. The existing
V08 verifier accepts and validates this bounded omitted-data case.

Without the flag, legacy V08 behavior is unchanged. A future composite
RPi5 diagnostic should include this flag unless separate protected
kernel-journal inspection is explicitly owner-authorized. No source merge
authorizes a new RPi5 host collection or LIVE activity.
