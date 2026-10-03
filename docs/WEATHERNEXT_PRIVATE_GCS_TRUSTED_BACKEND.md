# WeatherNext private GCS trusted execution boundary

Status: **SOURCE READY / READ-ONLY RPI5 PREFLIGHT NEXT**  
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

Issue #828 now provides the reviewed **GCS-specific runtime materializer
source** and deterministic offline wheelhouse closure. The closure is separate
from the historical BigQuery runtime, contains 25 exact wheels rooted in `google-auth 2.59.1`, `obstore 0.11.1`,
`requests 2.34.2`, `xarray 2026.9.0` and `zarr 3.4.0`, and is bound by
closure SHA-256
`4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148`.
Issue #833 regenerates this closure against Weather
`70e9ce0a95d2fad0857cd7aae64185c14eb3e8d3` after the explicit Google
credential-provider runtime dependencies were added.

This does **not** install or wire the materializer on the host. Accordingly:

- no host capability is installed;
- no external entrypoint is enabled;
- no credential is read;
- no Google request can run through this source;
- no runtime dependency is installed or materialized on RPi5;
- source merge does not authorize LIVE.

Issue #835 now adds the fixed GCS-only host/runtime wiring source, separate
operator/activation/binding roots, durable authorization boundary and sanitized
readiness observer. All install/execution switches remain disabled.

After #835 source merge, the next step is a minimum-sufficient **read-only RPi5
preflight** that may classify only capability/application/runtime identity,
closure/ABI/platform, glibc compatibility and GCS auth marker state. It must not
read protected credential or private binding contents.

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


## GCS prerequisite rollout

Issue #843 wires the source-only privileged prerequisite operations required after the sanitized host preflight: GCS host install, exact application-stage reuse, GCS runtime artifact transport/materialization and protected GCS auth binding. All remain behind separate STRICT LIVE-AUTH + READY Queue contracts. The first-access bridge continues to skip these stages when exact and does not automatically invoke them.

After #843 merge, the next owner gate is one bounded COMPOSITE STRICT LIVE prerequisite rollout. A real `read_only_private_gcs` request remains a later, separate authorization.
