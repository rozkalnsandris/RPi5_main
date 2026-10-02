# WeatherNext private GCS runtime closure

Status: **SOURCE READY / HOST WIRING NOT IMPLEMENTED**  
Issue: `RPi5_main#828`  
Weather gate: `rozkalns_weather#122`

## Purpose

This source defines the deterministic offline Python runtime required by the
WeatherNext 3 GCS statistics transport. It is distinct from the historical
BigQuery private runtime and cannot be dispatched by BigQuery or public Weather
authority.

The reviewed Weather prerequisite is
`rozkalns_weather@1fc7ea70efde88cb826c2e4a0baf26925078375c`, whose
`weathernext-gcs` extra declares:

- `google-auth>=2.59.1,<3`;
- `obstore>=0.11.1,<0.12`;
- `requests>=2.34.2,<3`;
- `xarray>=2026.9,<2027`;
- `zarr>=3.4,<4`.

## Exact closure

The regenerated lock contains 25 exact wheels. Root versions are:

- `google-auth==2.59.1`;
- `obstore==0.11.1`;
- `requests==2.34.2`;
- `xarray==2026.9.0`;
- `zarr==3.4.0`.

Closure SHA-256:
`4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148`.

The target is Linux aarch64, CPython 3.13 / cp313, with runtime compatibility
floor `manylinux_2_28_aarch64`. The deterministic builder explicitly accepts
compatible lower PEP 600 ARM64 wheel tags down to
`manylinux_2_17_aarch64` / `manylinux2014_aarch64`; this permits the
`obstore 0.11.1` abi3 wheel while retaining the higher host compatibility
floor required by NumPy/Pandas.

The final workflow performs no dependency resolution. It downloads each exact
`name==version` with `--no-deps --only-binary=:all:`, then requires the
wheel basenames and SHA-256 values to match the committed lock exactly.

## Artifact and materializer

CI emits a normalized tar containing only:

- `runtime-closure.json`;
- the 25 exact files below `wheelhouse/`.

The public-safe receipt binds exact RPi5_main source SHA, closure digest,
artifact digest/size, target OS/architecture/Python/ABI/platform and format.

The source materializer accepts only
`rozkalns-weather.weathernext-private-gcs-first-access.v1`. It rejects public
Weather and BigQuery authority. It validates the receipt, tar membership,
per-wheel SHA-256, traversal/symlink/duplicate targets and prior partial or
conflicting runtime state before atomic no-replace activation.

Fixed source paths are:

- artifact cache:
  `/var/lib/rpi5-deploy/weather-private-gcs-runtime/artifacts`;
- runtime:
  `/var/lib/rpi5-deploy/weather-private-gcs-runtime/runtime`.

These paths are deliberately separate from the historical BigQuery runtime.

## Authority

This issue is source-only. The materializer is **not wired into a host
entrypoint**, not installed on RPi5, and not executable from the current trusted
GCS bridge.

It grants no authority for:

- live network or package-manager installation;
- credential read/binding;
- Google/GCS requests;
- Google project, IAM, quota or Analytics Hub mutation;
- BigQuery;
- SQLite/corpus writes;
- Docker/systemd/network/Cloudflare mutation.

No retry, cleanup, rollback, source-build fallback or alternate artifact is
allowed. Partial/conflicting state must fail closed.

The next prerequisite is GCS-specific host/runtime wiring and a sanitized
readiness classifier. LIVE remains a separate explicit owner gate.
