# WeatherNext private BigQuery source boundary

This document defines the **source-only** RPi5 trust boundary for the first private WeatherNext 3 BigQuery access path. It does not authorize Google Cloud, host, credential, Analytics Hub, Docker/systemd or SQLite mutation.

## Separation from the public Weather runtime

`rozkalns-weather.public-runtime-release.v1` remains public-only. Its existing exclusion of `Google Cloud, BigQuery or WeatherNext private access` is intentional and remains authoritative. The private source contract is `rozkalns-weather.weathernext-private-bigquery-first-access.v1`; the two authorities are not interchangeable.

The private contract is execution-disabled source metadata. A later runtime executor must consume only a freshly reviewed exact `RPi5_main` SHA and a freshly JIT-verified exact `rozkalns_weather` SHA. Issue-creation SHAs are evidence, not durable runtime authority.

## Upstream Weather contract

The private RPi5 source boundary consumes the invariants defined by the Weather repository's:

- `deploy/weathernext-first-access.json`
- `docs/WEATHERNEXT_FIRST_ACCESS.md`

The first-access model contract remains WeatherNext 3 `3.0.0` with exact tables `weathernext_3_0_0_0p05deg` and `weathernext_3_0_0_0p1deg`.

## Fixed first-access scope

The initial canary is the canonical measured benchmark `station_05480` (DWD CDC Werl 05480), exactly 6 forecast hours, with private home scope disabled. Legacy `station_10416` remains non-first-access compatibility/MOSMIX context and is rejected as a private first-access canary. Both `0p05_station` and `0p1_surface` are required. A BigQuery dry-run is mandatory before a real query. Every query must have an explicit bytes cap no greater than 1 GiB, and a future LIVE gate should tighten that cap from fresh dry-run evidence when possible.

No SQLite write is part of this first-access contract.

## Ordered first-access stages

The source contract preserves this order:

1. `linked_dataset_probe`
2. `schema_fingerprint`
3. `dry_run_cost_guard`
4. `bounded_canary_query`
5. `provenance_validate`

The first production WeatherNext snapshot is a later, separate `production_sqlite_forecast_snapshot_write` owner gate.

## Runtime prerequisites and later owner gates

The private path keeps these mutation classes separate:

1. `weathernext_private_runtime_materialization` — if the isolated reviewed Python closure is absent;
2. `google_auth_binding` — bind ADC or equivalent service identity without putting credential material in Git;
3. `google_project_binding` — bind the private Google project identity outside GitHub;
4. `analytics_hub_link_create` — only when the approved WeatherNext listing has not yet been added to the project;
5. `read_only_private_bigquery` — linked-dataset/schema/dry-run/canary/provenance verification;
6. `production_sqlite_forecast_snapshot_write` — separate later data mutation.

`Analytics Hub` subscription/link creation is a Google control-plane mutation. It is never inferred from read-only BigQuery authorization. IAM/permission changes are also a separate owner decision.

## Isolated runtime closure

The source contract records the Weather requirement `google-cloud-bigquery>=3.36,<4` but does not install it. A future implementation must use a fixed reviewed isolated runtime closure rather than generic `apt`, arbitrary `pip`, shell, path, argv or environment authority. The agent must not read protected credential files or process/container environments.

## Sanitized readiness evidence

Only boolean/presence classifications are eligible for source-side readiness decisions. The source classifier keeps these states distinct:

- `private_runtime_required`
- `credential_binding_required`
- `google_project_binding_required`
- `analytics_hub_link_required`
- `permission_denied`
- `read_only_access_probe_required`
- `ready_for_read_only_first_access`

Project IDs, linked dataset IDs, credential material, account email, `.env` contents, private filesystem paths, raw logs and `HOME_LAT`/`HOME_LON` never belong in GitHub evidence.

## Failure semantics

Immediately before any future mutation, revalidate exact `RPi5_main` SHA/CI, exact Weather SHA/CI, target host, expected runtime baseline and the exact mutation classes being authorized. Authorization is consumed by the first authorized mutation.

After mutation begins, any timeout, source/runtime drift, permission ambiguity, linkage/schema/cost mismatch or health regression means minimum sanitized read-only evidence and STOP. There is no automatic retry, credential replacement, alternate dataset/link, cleanup, rollback, restore, delete or restart.

DWD remains the official severe-weather warning authority in Germany. WeatherNext remains research forecast output.
