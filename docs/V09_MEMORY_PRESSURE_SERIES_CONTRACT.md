# V09 memory-pressure series contract

V09 analyzes two to sixty-four previously collected and verified V08 memory-pressure bundles. It is offline-only and performs no host collection or mutation.

## Inputs

Every source directory must remain below the repository `evidence/` or `exports/` tree and pass `verify-memory-pressure-diagnostic.py`. Sources must be unique and supplied in strictly increasing `collected_at_utc` order.

The analyzer binds each source by bundle name, collection UTC and the SHA-256 of its canonical V08 `report.json`. Source bundles are never modified.

## Unit normalization

Docker memory strings are parsed with explicit binary and decimal units and normalized to whole KiB using decimal half-up rounding. JSON stores KiB and percentage basis points only. Markdown converts KiB to MiB exactly once.

For the observed regression case, `436.1 MiB` becomes `446566 KiB`, `438.4 MiB` becomes `448922 KiB`, and the change is `2355 KiB` or `2.30 MiB`.

## Classification

The deterministic series classifications are:

- `stable_idle`: no sampled swap, major-fault, PSI or OOM activity;
- `intermittent_activity`: activity exists, but sustained-pressure rules are not met;
- `sustained_pressure`: any OOM, any full-memory PSI, swap-out in at least two samples, PSI activity in at least two samples, or available memory below 15% in at least two samples.

A single V08 `attention` window does not automatically make the series `sustained_pressure`.

## Outputs

`analyze-memory-pressure-series.py` writes canonical `report.json`, deterministic `report.md` and `SHA256SUMS` atomically to a new directory below ignored `evidence/` or `exports/` paths. `verify-memory-pressure-series.py` checks structure, ownership, file types, checksums, canonical JSON, arithmetic, chronology, classification and exact Markdown rendering.

The report summarizes source windows and associations only. It does not prove causality, diagnose a leak, deploy, remediate, clear swap, tune zram, restart services or change Docker.
