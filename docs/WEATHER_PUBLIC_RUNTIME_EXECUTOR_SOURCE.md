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

## Explicitly separate gates

This static operation does not include or authorize:

- RPi5 deploy/redeploy/restart or executor global enablement;
- SQLite schema initialization;
- historical forecast/truth corpus backfill;
- corpus backup, restore, deletion or destructive rollback;
- `.env`, credentials, Google Cloud, BigQuery or WeatherNext private access;
- `HOME_LAT`, `HOME_LON` or exact home coordinates;
- Cloudflare, network or firewall mutation;
- package installation, generic `sudo`/root authority or arbitrary shell/path/argv/environment authority;
- repository settings, rulesets, permissions or secrets changes.

Application rollback, if a later reviewed LIVE capability is ever introduced, must never imply SQLite rollback, deletion or restore. The `weather_data` corpus volume is retained across application replacement by contract.

DWD remains the authoritative severe-weather warning source. WeatherNext remains research output and is optional/access-pending in this public-only runtime class.
