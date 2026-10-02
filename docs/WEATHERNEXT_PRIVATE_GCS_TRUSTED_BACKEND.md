# WeatherNext private GCS trusted execution boundary

Status: **SOURCE READY / GCS RUNTIME MATERIALIZATION SOURCE REQUIRED**  
Issue: `RPi5_main#825`  
Weather gate: `rozkalns_weather#122`  
Host capability identity: `rpi5.weathernext-private-gcs-backend.v1`

## Purpose

This source slice creates a distinct trusted RPi5 boundary for the bounded
WeatherNext 3 GCS statistics path merged in Weather PR #324. It deliberately
does **not** modify or replace the existing BigQuery private bridge.

The new private class is `read_only_private_gcs`. BigQuery authority cannot
dispatch it, and GCS authority cannot dispatch the BigQuery bridge.

## Fixed source boundary

The source wrapper fixes:

- target: `rpi5`;
- model contract: WeatherNext 3 `3.0.0`;
- location: `station_05480`;
- one exact UTC init supplied only by the owner-authorization surface;
- six forecast hours;
- bucket: `weathernext3_statistics_spatial`;
- required permissions: `storage.objects.list` and `storage.objects.get`;
- output ceiling: 288 required statistic scalars;
- Weather entrypoint:
  `rozkalns_weather.weathernext_gcs_transport.read_private_first_access_gcs`.

The conversational caller may supply only an authorization issue number. It
cannot select command, path, argv, environment, repository SHA, bucket, prefix,
coordinates, credential material, private identity, target or mutation sequence.

## Stage sequence

The only allowed sequence is:

1. exact Weather application staging, only if absent;
2. a reviewed **GCS-specific** private runtime materialization, only if absent;
3. the fixed Google auth binding, only if absent;
4. `read_only_private_gcs`.

There is intentionally no Google project binding, Analytics Hub linked-dataset
stage, BigQuery stage, billing-project header, Requester Pays full-ensemble
fallback, private-home scope or SQLite/corpus write.

## Current execution state

The bridge, envelope validation, canonical fact validation and fixed trusted
adapter composition are implemented and fixture-testable.

The **real GCS runtime materializer is not implemented in this issue**.
Accordingly:

- no host capability is installed;
- no external entrypoint is enabled;
- no credential is read;
- no Google request can run through this source;
- no runtime dependency is installed or materialized;
- source merge does not authorize LIVE.

The next source prerequisite is an offline/reviewed GCS runtime closure for
`obstore + xarray + zarr`, with no live-network installation. Only after that
source prerequisite is merged may a future minimum-sufficient read-only runtime
preflight determine whether staging/runtime/auth markers are present.

## Failure semantics

The future execution path must freshly bind exact reviewed `RPi5_main` and
`rozkalns_weather` SHAs plus required CI immediately before authorization
consumption. Source/baseline/authorization drift fails closed.

After private access begins there is no automatic retry, alternate init/source,
full-ensemble fallback, cleanup or rollback. Any ambiguity permits only
minimum sanitized read-only evidence followed by STOP.

## Privacy and authority

GitHub evidence must not contain credentials, tokens, credential paths, account
identity, coordinates, raw WeatherNext values or provider payloads.

WeatherNext remains research output. DWD remains the authoritative severe-weather
warning source in Germany.
