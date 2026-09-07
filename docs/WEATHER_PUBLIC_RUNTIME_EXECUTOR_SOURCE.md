# Weather public runtime executor source contract

Issue #408 imports the merged `rozkalnsandris/rozkalns_weather` public-only RPi5 handoff into the `RPi5_main` deploy executor as a **static, execution-disabled contract**. This document describes source state only. It is not LIVE authorization and it does not prove any weather runtime exists on the RPi5.

## Reviewed upstream handoff

Design/provenance source: `rozkalnsandris/rozkalns_weather@6296556e783967c0897abc4e27368295a1158c7e`.

The reviewed artifact identities are:

- `deploy/runtime-descriptor.json` blob `dde970523486123e2809388bff9ed8b643cb6940`;
- `deploy/docker-compose.public.yml` blob `41b40d614907acd7f257c2fd4eea368de47fb1ea`;
- `deploy/public-ingest-schedule.json` blob `d67dd0bb606f6d25922972729a4ff1ad33a68224`;
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` blob `8004da2243aa3bb3e1fb9917bc8819134f117cf8`.

The design SHA pins the handoff reviewed by Issue #408. It is **not** the only source SHA the future operation may accept. A future deployment candidate must supply its own exact lowercase 40-character weather SHA, and future execution must independently prove that SHA is merged/reachable from current weather `main` with successful exact-SHA CI.

## Static operation

`ops/deploy/executor-operations.json` registers exactly one weather operation:

- operation / adapter: `rozkalns-weather.public-runtime-release.v1`;
- source repository: `rozkalnsandris/rozkalns_weather` (stable repository ID `1359499204`);
- target alias: `rozkalns-weather-public-rpi5`;
- execution location: `trusted-home-host`;
- fixed repository entrypoint: `deploy/runtime-descriptor.json`;
- deploy class: `STRICT_LIVE_AUTH_REQUIRED`;
- authorization class: `STRICT`;
- ordinary LIVE-ALL eligibility: `false`;
- baseline resolver: `rozkalns-weather.public-runtime-baseline.v1`;
- rollback policy: `NONE`.

The global registry remains `execution_enabled=false`. `WeatherPublicRuntimeAdapter.apply()` rejects execution while this source state is in force. There is no host command, shell, argv, environment or privileged dispatch bridge in the adapter.

## Public package and future mutation envelope

The source contract binds the fixed Compose services `schema-init`, `weather`, `public-ingest`, and `readiness`, the persistent logical named volume `weather_data`, the in-container URL `sqlite:///data/weather.db`, and readiness endpoint `/ready`.

Only these future application-release mutation categories are represented in the static registry, each with a maximum count of one:

1. `filesystem.release-materialization`;
2. `docker.named-volume-ensure`;
3. `docker.compose-build`;
4. `docker.compose-application-apply`;
5. `systemd.public-ingest-schedule-install-or-update`.

Their presence in the registry is contract metadata, not permission to execute them. No LIVE mutation class is authorized by Issue #408.

## Baseline resolver contract

`weather_public_runtime_baseline.py` defines a deterministic pure resolver for sanitized evidence. It performs no filesystem, Docker, systemd, network, credential or database access. Evidence is exact-keyed and may contain only deployment state, current source SHA, logical volume state and public-ingest schedule state for the fixed target.

A host with no weather application is represented safely as `not_deployed` with no current source SHA. Presence of a retained named volume or schedule is represented independently and does not imply application deployment. Extra fields, including private runtime configuration, are rejected.

## First-bootstrap composition — Issue #410

Issue #410 adds `weather_public_runtime_bootstrap.py`, a source-only composition layer for the first public-only rollout. It does **not** add a process launcher, privileged helper, host wiring or executable Docker/systemd/database path. Its only caller-controlled request field is one authorization issue number; all source SHA, target, capability, bounds and baseline state must be independently re-derived by a capability-specific canonical revalidator and sanitized baseline resolver.

The bootstrap plan is deterministic and ordered:

1. `application_release` — existing `rozkalns-weather.public-runtime-release.v1` application release capability;
2. `persistent_volume_ensure` — retain/ensure logical `weather_data`;
3. `explicit_schema_init` — one idempotent schema initialization capability;
4. `readiness_schema_privacy` — read-only `/ready` schema/privacy verification;
5. `public_smoke_read_only` — optional read-only public provider smoke;
6. `bounded_dwd_truth_backfill` — DWD observation truth pinned to WMO station `10416`;
7. `bounded_deterministic_forecast_backfill` — exact Single Runs for `icon_d2`, `ecmwf_ifs`, and `ecmwf_aifs` at reviewed 00/06/12/18 UTC cycles;
8. `corpus_integrity_check` — read-only reconciliation of expected exact runs;
9. `recurring_public_ingest_schedule` — reviewed `PT30M` recurring public ingest schedule.

The source contract limits the first historical window to at most 180 inclusive days. The later canonical LIVE authorization must carry explicit start/end dates and one reviewed recovery decision before corpus writes become eligible. Accepted recovery decisions are deliberately non-destructive: either a separately verified backup is available, or the owner explicitly accepts proceeding without a pre-write backup. Neither choice authorizes backup creation, restore, database rollback or corpus deletion.

Mutation classes remain distinct even when a later owner chooses one bounded composite LIVE:

- application release;
- named-volume ensure;
- SQLite schema init;
- bounded DWD truth corpus write;
- bounded deterministic forecast corpus write;
- recurring public-ingest schedule install/update.

Readiness, public smoke and integrity are read-only stages. Application rollback never implies SQLite rollback/delete/restore, and the `weather_data` logical corpus volume must be retained across application replacement.

### Bootstrap sanitized baseline

The Issue #410 resolver protocol may represent only:

- deployed/not-deployed state and exact application source SHA when deployed;
- logical `weather_data` state;
- schema state and reviewed schema version when ready;
- public-ingest schedule state;
- coarse bootstrap stage state;
- an explicit `privacy_safe=true` assertion.

Unknown fields are rejected, including `HOME_LAT`, `HOME_LON`, credentials, raw configuration, exact host database paths, process/container environments and private runtime logs.

### Future LIVE gate

Merging Issue #410 still does not make weather deployable. A future LIVE gate must freshly bind the exact merged weather SHA, exact target alias, successful exact-SHA CI, reviewed artifact identities, sanitized current baseline, bounded historical dates/model scope, recovery decision and exact mutation budgets. Source state keeps `privileged_dispatch_enabled=false`, `host_wiring_enabled=false` and `production_mutation_started=false`.

## Explicitly separate gates

This static operation and bootstrap source composition do not include or authorize:

- RPi5 deploy/redeploy/restart or executor global enablement;
- production SQLite schema initialization;
- historical forecast/truth corpus writes;
- corpus backup, restore, deletion or destructive rollback;
- `.env`, credentials, Google Cloud, BigQuery or WeatherNext private access;
- `HOME_LAT`, `HOME_LON` or exact home coordinates;
- Cloudflare, network or firewall mutation;
- package installation, generic `sudo`/root authority or arbitrary shell/path/argv/environment authority;
- repository settings, rulesets, permissions or secrets changes.

Application rollback, if a later reviewed LIVE capability is introduced, must never imply SQLite rollback, deletion or restore. The `weather_data` corpus volume is retained across application replacement by contract.

DWD remains the authoritative severe-weather warning source. WeatherNext remains research output and is optional/access-pending in this public-only runtime class.
