# WeatherNext private GCS prerequisite rollout

Status: **SOURCE ONLY / COMPOSITE STRICT LIVE GATE NEXT**  
Issue: `RPi5_main#843`

## Outcome

This source wires the missing privileged prerequisite operations required before the WeatherNext private GCS first-access canary:

1. install the separate GCS host capability when absent;
2. reuse the existing exact Weather application-stage operation when the staged source is stale;
3. publish and materialize the exact reviewed GCS runtime artifact when absent;
4. create the separate protected GCS auth binding when absent;
5. verify only sanitized postconditions.

The sequence stops before `read_only_private_gcs`.

## Runtime identity

- Weather SHA: `70e9ce0a95d2fad0857cd7aae64185c14eb3e8d3`
- GCS runtime closure SHA-256:
  `4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148`
- target: Linux aarch64 / CPython 3.13 / cp313 / `manylinux_2_28_aarch64`

## Sanitized host baseline

The completed read-only preflight found:

- aarch64, glibc 2.36 — compatible with the reviewed >=2.28 floor;
- GCS trusted checkout/operator/activation absent;
- GCS runtime absent;
- GCS auth-ready marker absent;
- Weather application stage present but stale.

No credential/private binding content or Google identity was exposed.

## Protected auth binding

The auth-binding operation has no caller path, basename, project, dataset, account or provider selector. Only after durable owner authorization consumption may it inspect the existing root-owned WeatherNext private binding, derive one validated credential basename, no-follow copy that bounded root-owned 0600 credential into the separate GCS credential root, write a GCS-private schema+basename binding and publish the sanitized ready marker.

It performs no ADC, Google API, IAM, project/dataset, Analytics Hub, billing-project or BigQuery action. Credential contents, paths and hashes are not eligible for GitHub receipts.

## Authorization and failure semantics

Each privileged operation remains behind exact LIVE-AUTH + READY Queue + exact-main CI revalidation. Source merge enables no execution. The future Composite Live must bind the merged RPi5_main SHA, exact target aliases, mutation budgets and the sanitized baseline.

Authorization is consumed immediately before the first mutation (or protected credential read for auth binding). After any mutation starts, error/drift means STOP with no retry, cleanup, rollback or alternate path unless explicitly pre-authorized.

## Later gate

Only after all prerequisite postconditions are exact may a separate owner authorization invoke the GCS one-shot operator for `read_only_private_gcs`. That later authorization remains bounded to station_05480, one explicit init, six forecast hours and the existing materialized-scalar ceiling.
