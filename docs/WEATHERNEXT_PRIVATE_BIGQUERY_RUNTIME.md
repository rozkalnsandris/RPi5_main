# WeatherNext private BigQuery runtime materialization

Issue #542 implements the **source-only executable capability** for the first private WeatherNext runtime closure. It remains separate from the public Weather runtime and does not authorize host execution by being merged.

## Runtime identity

The operation identity is `rozkalns-weather.weathernext-private-runtime-materialization.v1`. The only mutation class represented by this source is `weathernext_private_runtime_materialization`.

The reviewed target is:

- Linux `aarch64`;
- CPython `3.13`, ABI `cp313`;
- `manylinux2014_aarch64`;
- exact root dependency `google-cloud-bigquery==3.42.1`, satisfying the Weather source requirement `google-cloud-bigquery>=3.36,<4`.

The tracked lock records the complete transitive runtime wheel set. Every package is exact-version pinned and bound to one exact wheel filename plus SHA-256. The canonical closure digest is computed over the normalized package records.

This source does **not** assert that the production RPi5 currently provides CPython 3.13. A later LIVE preflight must prove the exact host architecture/Python baseline and STOP on mismatch. Source compatibility is not runtime evidence.

## Deterministic CI artifact

The dedicated GitHub workflow builds an offline wheelhouse artifact for the exact PR/main source SHA. It performs `pip download` only in the ephemeral GitHub-hosted build workspace, with:

- exact package versions from the tracked lock;
- `--no-deps`;
- binary wheels only;
- fixed `manylinux2014_aarch64`;
- fixed CPython 3.13 / `cp313` + `abi3`;
- no package installation.

Every downloaded filename and SHA-256 must match the tracked lock exactly. CI then creates an uncompressed deterministic tar with sorted wheel filenames, zero timestamps, fixed ownership metadata and a public-safe `runtime-closure.json`. A separate receipt binds:

- exact source SHA;
- closure SHA-256;
- artifact SHA-256 and byte size;
- artifact format;
- OS/architecture/Python ABI/platform.

Generated tar/receipt evidence is an Actions artifact only. It is not committed to Git.

## Future materialization semantics

The source materializer is intentionally narrow:

1. authority must be the private WeatherNext contract, never `rozkalns-weather.public-runtime-release.v1`;
2. exact source SHA, closure digest, artifact digest, size and platform receipt must validate;
3. the artifact must already exist in the fixed root-controlled artifact cache;
4. the tar must contain exactly `runtime-closure.json` plus the locked wheel filenames;
5. every wheel digest is re-verified before extraction;
6. wheel paths, symlinks, hardlinks, traversal and non-`purelib`/`platlib` `.data` destinations are rejected;
7. wheels are unpacked directly into an isolated `site-packages` tree without invoking a package manager or network;
8. activation uses Linux `renameat2(RENAME_NOREPLACE)` so an existing runtime is never silently replaced.

A prior partial staging directory, existing runtime, digest mismatch, unexpected archive member or any extraction error causes STOP semantics. The source performs no automatic retry, cleanup or rollback.

The materializer may create only its fixed runtime directory tree. It does not configure or read credentials, bind a Google project/dataset, create an Analytics Hub subscription/link, execute BigQuery, touch SQLite, control Docker/systemd or mutate Cloudflare/network state.

## Public-safe evidence states

Only public-safe identity/status evidence is needed for later orchestration:

- `runtime_materialization_required`;
- `runtime_identity_mismatch`;
- `runtime_materialization_source_ready`.

The installed marker contains only source/artifact/closure/platform identity and explicit false downstream-authority flags. It contains no project ID, dataset ID, account identity, credential path/material, `.env` content or private coordinates.

## Later gates

After this source is merged, the ordered owner-gated path remains:

1. exact `weathernext_private_runtime_materialization` LIVE authorization using a fresh artifact receipt and fresh RPi5 baseline;
2. `google_auth_binding` and `google_project_binding` if absent;
3. `analytics_hub_link_create` if the approved listing is still not linked;
4. `read_only_private_bigquery` for linked-dataset probe, schema fingerprint, dry-run, bounded canary and provenance validation;
5. separate `production_sqlite_forecast_snapshot_write`.

No later authority is implied by this source or by its merge. DWD remains the official severe-weather warning authority in Germany; WeatherNext remains research forecast output.

## Reviewed host transport — issue #704

Issue #704 wires the existing deterministic artifact and materializer into the WeatherNext privileged boundary without granting the boundary GitHub Actions download or credential authority.

The host transport has three deliberately separate states:

1. **external acquisition / fixed handoff** — a separately authorized process must place exactly `runtime-artifact-receipt.json` and `weathernext-private-runtime.tar` in `/var/lib/rpi5-deploy/weather-private-runtime/incoming`; #704 does not implement an Actions downloader, use the P9 Issues-only GitHub App for artifact access, or consume a user token;
2. **validated root cache import** — the privileged transport accepts only that fixed incoming root, root-owned regular files, exact receipt identity, exact source SHA, closure/platform/Python identity, byte size, artifact SHA-256 and complete reviewed archive contents, then publishes one fixed cache directory with no-replace semantics;
3. **runtime materialization** — after the cache is exact, the existing offline materializer unpacks the reviewed wheel closure and no-replace publishes the fixed cp313 runtime.

The privileged CLI still accepts only an authorization issue number. The requested operation is derived from the canonical owner-authored non-App LIVE-AUTH and READY Queue; callers cannot select a URL, repository, source SHA, artifact digest, path, filename, interpreter, command, argv or environment.

The runtime transport has no Actions artifact download, credential acquisition, network install, package-manager, Google, Analytics Hub, BigQuery, SQLite, Docker, systemd or network-control authority. Source merge grants no LIVE authority.

A future LIVE execution therefore still requires two independently bounded things to be true before consume: the exact reviewed artifact must already be present in the fixed incoming handoff, and a fresh owner LIVE-AUTH/READY Queue must bind the current `RPi5_main` source and runtime operation. Any missing, partial, conflicting or mismatched state fails closed with no automatic retry, cleanup or rollback.
