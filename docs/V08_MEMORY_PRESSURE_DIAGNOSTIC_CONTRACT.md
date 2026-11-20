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

## Precise, backward-compatible counter-read envelopes (v08.2.0; #1468)

V08 **v08.2.0** retains the existing schema and section inventory, adding
`clock_source` and `counter_intervals` to its metadata. Each PSI and
`/proc/vmstat` start/end read has **before/after** UTC timestamps at
microsecond precision and monotonic elapsed microseconds within that
invocation. The independent V08 verifier requires exact keys, valid
calendar/time ordering, bounded elapsed time and UTC/monotonic agreement.
The monotonic origin is not persisted. Fixed-clock test fixtures are marked
`synthetic_test`; they cannot be treated as production measurements.

The offline Grafana-host analyzer distinguishes legacy coarse collection
start times from a **conservative vmstat counter window** bounded by
*after the first read* and *before the last read*. A real-clock, verified
v08.2.0 bundle may be classified `bounded_counter_window_overlap`
relative to Grafana V02 sample timestamps. This does **not** establish
the precise event time, Grafana performance or causation:
`verified_same_window=false` and `proven_causation=false` remain
invariant. v08.0.0 and v08.1.0 bundles retain original coarse semantics;
the analyzer never fabricates missing historical timestamps. Unknown
memory PSI is always null, not a measured zero.

This is a source-only prerequisite for #1468. New RPi5 collection still
requires a distinct, exact-SHA owner LIVE authorization and an unused,
ignored, bounded output target. No services, Docker, memory limits,
swap/zram or production settings are changed by this source update.
