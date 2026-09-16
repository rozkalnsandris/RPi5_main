# WeatherNext private execution bridge source

This source-only bridge lets a future exact owner LIVE authorization select one fixed WeatherNext 3 private first-access sequence without giving the conversational agent generic shell, root, path, argv, environment, credential, Google-project, or arbitrary-query authority.

The bridge is intentionally **execution-disabled**. Source merge does not install a host capability, bind credentials, create an Analytics Hub link, query BigQuery, write SQLite, restart services, or authorize LIVE.

## Fixed authority surface

The only caller-controlled authority is a positive owner-authorization issue number. A trusted canonical revalidator must independently derive the exact reviewed `RPi5_main` SHA, exact reviewed `rozkalns_weather` SHA, target alias `rpi5`, bounded first-access scope, and sanitized prerequisite-presence state.

The caller cannot choose an executable, command, path, argv, environment, project, dataset, account identity, credential source, target, source SHA, SQL/query text, or mutation sequence.

## Ordered capability sequence

A future separately reviewed LIVE wrapper may drive only this order:

1. `weathernext_private_application_staging` when exact Weather application source is absent;
2. `weathernext_private_runtime_materialization` when the reviewed offline Python closure is absent;
3. `google_auth_binding` when the fixed runtime identity is not bound;
4. `google_project_binding` when the fixed private project context is not bound;
5. `analytics_hub_link_create` only when the approved linked dataset is absent;
6. `read_only_private_bigquery` for bounded first-access verification.

`production_sqlite_forecast_snapshot_write` is deliberately excluded and remains a separate later owner gate.

## First-access invariants

The bridge reuses the existing private BigQuery contract: WeatherNext 3 `3.0.0`, `station_10416`, exactly six forecast hours, both required product surfaces, mandatory dry-run before canary, a hard per-query ceiling of 1 GiB, home scope disabled, and SQLite write disabled. A later LIVE gate must tighten the real cap to the smallest defensible value from fresh dry-run evidence.

## Binding adapters and failure semantics

The source defines narrow trusted adapter interfaces for application staging, runtime materialization, Google auth binding, project binding, Analytics Hub link creation, and read-only first access. CI uses fakes only. No real Google or host implementation is invoked by this source PR.

A canonical authorization consumer must consume the future owner authorization immediately before the first required action. Any adapter failure stops the sequence. The bridge performs no automatic retry, cleanup, rollback, credential substitution, alternate project/dataset selection, restart, or SQLite recovery.

Only sanitized stage/status evidence is eligible for continuity. Raw provider values, private logs, account identities, project/dataset identifiers, credential material/paths, and home coordinates are forbidden from GitHub evidence.

## Current readiness

The source can be reviewed while runtime switches remain false: host capability installation, external entrypoint, global executor execution, Google control-plane execution, credential binding execution, read-only BigQuery execution, and SQLite write execution are all disabled. Source merge does not authorize LIVE.

A later exact owner gate must separately establish and verify the trusted host backend before `rozkalns_weather#122` can execute real private read-only first access.

DWD remains the authoritative severe-weather warning source in Germany; WeatherNext remains research forecast output.
