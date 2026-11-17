# V09 memory-pressure series contract

V09 analyzes two to sixty-four previously collected and verified V08 memory-pressure bundles. It is offline-only and performs no host collection or mutation.

## Inputs

Every source directory must remain below the repository `evidence/` or `exports/` tree and pass `verify-memory-pressure-diagnostic.py`. Sources must be unique and supplied in strictly increasing `collected_at_utc` order.

The analyzer binds each source by bundle name, collection UTC and the SHA-256 of its canonical V08 `report.json`. Source bundles are never modified.

## Unit normalization

Docker memory strings are parsed with explicit binary and decimal units and normalized to whole KiB using decimal half-up rounding. JSON stores KiB and percentage basis points only. Markdown converts KiB to MiB exactly once.

For the observed regression case, `436.1 MiB` becomes `446566 KiB`, `438.4 MiB` becomes `448922 KiB`, and the whole-KiB change is `2356 KiB`, rendered as `2.30 MiB`.

## Classification

The deterministic series classifications are:

- `stable_idle`: no sampled swap, major-fault, PSI or OOM activity;
- `intermittent_activity`: activity exists, but sustained-pressure rules are not met;
- `sustained_pressure`: any OOM, any full-memory PSI, swap-out in at least two samples, PSI activity in at least two samples, or available memory below 15% in at least two samples.

A single V08 `attention` window does not automatically make the series `sustained_pressure`.

## Outputs

`analyze-memory-pressure-series.py` writes canonical `report.json`, deterministic `report.md` and `SHA256SUMS` atomically to a new directory below ignored `evidence/` or `exports/` paths. `verify-memory-pressure-series.py` checks structure, ownership, file types, checksums, canonical JSON, arithmetic, chronology, classification and exact Markdown rendering.

The report summarizes source windows and associations only. It does not prove causality, diagnose a leak, deploy, remediate, clear swap, tune zram, restart services or change Docker.

## PSI availability (v09.1.0; #1468)

V09 checks PSI source status even for verified legacy V08 bundles. It emits `psi_available=false` and null deltas when absent; aggregate PSI is null when any source lacks data. Confirmed repeated swap-out still establishes `sustained_pressure`; no recorded activity plus incomplete PSI results in `indeterminate`, not `stable_idle`. The verifier supports historical v09.0.0 output for provenance; reanalyze old sources for corrected PSI interpretation.\n\n## Interpretation of distinct idle and busy windows (#1468)

A V09 classification is a within-input observation heuristic, **not
proof of sustained pressure across independently observed idle and
busy periods**. In particular, swap-out in two adjacent five-second
V08 samples can satisfy the rule for `sustained_pressure`, even if
these were collected during a single brief interval. Do not translate
that label into a cross-day trend, Grafana causation or OOM prognosis.

For RPi5 #1468, compare **distinct idle and busy windows** under
separately authorized LIVE captures. The 2026-11-16 four-window
composite all belongs to one short Grafana interval; no independent
busy-versus-idle classification has been established. Both PSI
sections were unavailable in all four verified V08 inputs.
Follow-up read-only metadata on 2026-11-17 confirmed the
`/proc/pressure` directory was absent. PSI therefore remains
`unknown`, not measured zero; no kernel setting change is implied.

See [the verified #1468 baseline](RPI5_MEMORY_BASELINE_20261116_1468.md).
