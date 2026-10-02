# WeatherNext private GCS host runtime

Status: **SOURCE READY / READ-ONLY RPI5 PREFLIGHT NEXT**  
Issue: `RPi5_main#835`  
Weather gate: `rozkalns_weather#122`

## Purpose

This source completes the GCS-specific host wiring boundary without installing
or executing it. It is deliberately separate from the historical WeatherNext
BigQuery host capability.

The GCS host capability has its own trusted checkout, operator, activation
marker, binding root and authorization identity. Project, dataset, Analytics Hub
and BigQuery state are not part of this composition.

## Fixed source identity

The source contract is bound to:

- Weather source `1fc7ea70efde88cb826c2e4a0baf26925078375c`;
- GCS runtime closure
  `4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148`;
- Linux aarch64 / CPython 3.13 / `cp313`;
- reviewed host compatibility floor `manylinux_2_28_aarch64`;
- Weather entrypoint
  `rozkalns_weather.weathernext_gcs_transport.read_private_first_access_gcs`.

The future host observer exposes only sanitized readiness:

- capability/application/runtime presence and exact source identities;
- runtime closure/ABI/platform;
- whether host glibc meets the reviewed 2.28 floor;
- GCS auth binding state `absent|ready|mismatch`;
- read-only first-access authorization/execution booleans.

It never emits credential paths or contents, Google identity, coordinates, raw
WeatherNext values, project IDs, datasets or billing-project values.

## Authorization shape

Future owner authorization must be a single exact
`read_only_private_gcs` operation for target `rpi5` and must bind:

- exact Weather source SHA;
- exact `rpi5-main-sha:<sha>`;
- exact GCS contract ID;
- exact `weathernext-init-utc:YYYY-MM-DDTHH:00:00Z`;
- rollback policy `NONE`.

The init time is not a CLI or caller parameter. The operator accepts only an
authorization issue number.

Durable authorization is revalidated against both current reviewed source SHAs
immediately before consumption. The installed execution-ready observer rejects
missing application/runtime/auth prerequisites before that consumption, so a
read-only GCS authorization cannot be consumed to perform staging,
materialization or credential-binding mutations.

## Protected credential boundary

The GCS path has a separate fixed binding root:
`/var/lib/rpi5-deploy/weather-private-gcs-bindings`.

The sanitized auth marker contains only schema, fixed slot ID, fixed provider
class and `ready=true`. The protected private binding contains only one
credential basename. No project or dataset is required.

Only after durable owner authorization consumption may the future first-access
runner resolve that basename under the fixed credential root, construct explicit
Google credentials, construct
`obstore.auth.google.GoogleCredentialProvider(credentials=...)`, and pass the
provider to the fixed Weather GCS entrypoint. Ambient ADC remains forbidden.

## Current execution state

This issue is source-only:

- no trusted checkout is created on RPi5;
- no operator is installed;
- no activation marker is written;
- no runtime is materialized;
- no credential or protected binding is read;
- no Google/GCS request is made;
- all execution/install switches remain disabled;
- source merge does not authorize LIVE.

## Next step after merge

The next step is a minimum-sufficient **read-only** RPi5 preflight. It may
classify only the sanitized fields above and host glibc compatibility. It must
not read credential or private binding contents.

That preflight will determine which, if any, separate owner LIVE gates are
actually required for application staging, GCS runtime materialization, GCS auth
binding or host capability installation. A real GCS request remains a later
separate authorization.
