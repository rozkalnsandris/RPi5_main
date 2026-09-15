# WeatherNext private trusted host backend

Status: **SOURCE-ONLY / HOST CAPABILITY INSTALL REQUIRED**  
Issue: `RPi5_main#549`  
Operation: `rozkalns-weather.weathernext-private-trusted-backend.v1`

## Purpose

This layer closes the source gap between the merged WeatherNext private execution bridge and the later real private first-access gate in `rozkalns_weather#122`. It does not grant LIVE authority. It defines one capability-specific canonical revalidator and one trusted backend whose caller-controlled input is only a positive owner-authorization issue number.

The implementation reuses, rather than bypasses:

- `weather_private_bigquery_execution_bridge.py` for fixed stage order and one-shot authorization consumption;
- `weather_private_bigquery_runtime_materialization.py` for the exact offline CPython 3.13 / `cp313` runtime;
- the fixed Weather first-access entrypoint `rozkalns_weather.weathernext_access.read_first_access_canary`;
- the existing WeatherNext 3 first-access scope: `station_10416`, exactly 6 forecast hours, both required product surfaces, mandatory dry-run, hard ceiling `<= 1 GiB/query`, home disabled, SQLite disabled.

DWD remains the authoritative severe-weather warning source in Germany. WeatherNext remains `primary_research` forecast output.

## Canonical revalidation boundary

A future installed host capability must provide `CanonicalPrivateFactsProvider`. The conversational caller cannot supply those facts. Given only the owner authorization issue identity, the trusted provider independently derives public-safe state from canonical GitHub/runtime sources and returns the closed `CanonicalPrivateFacts` schema.

The revalidator fails closed unless:

- the owner authorization issue identity matches and is active;
- `RPi5_main` and `rozkalns_weather` identities are exact Git SHAs;
- required exact-source CI is successful for both repositories;
- target alias is exactly `rpi5`;
- a present private runtime is the reviewed `cp313` runtime;
- an absent private runtime cannot be represented by system Python such as `cp311`;
- auth, project and Analytics Hub link states are only `absent` or `ready`; `mismatch` always stops.

No account email, Google project ID, dataset ID, Analytics Hub private identifier, credential material/path, query text, home coordinate or raw provider value is part of the canonical facts or sanitized readiness schema.

## Fixed capability adapters

The backend has separate capability-specific interfaces:

1. **Weather application staging** — exact reviewed Weather source only, fixed stage identity and fixed future root `/var/lib/rpi5-deploy/weather-private-application`. Caller-selected paths and source SHAs are absent.
2. **Private runtime materialization** — calls only the reviewed `materialize_reviewed_runtime()` implementation with the private contract identity and exact artifact receipt. No `pip`, `apt`, package manager or live dependency download is added.
3. **Google auth binding** — fixed slot `weathernext-private-google-auth-v1`, fixed mechanism class `root-owned-runtime-credential-reference`; credential material and credential paths remain runtime-only.
4. **Google project binding** — fixed slot `weathernext-private-google-project-v1`; no project identifier is accepted from the caller or emitted to GitHub.
5. **Analytics Hub link binding** — fixed slot `weathernext-private-approved-linked-dataset-v1`; there is no arbitrary listing/dataset selection, deletion, relink or alternate-link authority.
6. **Read-only first access** — fixed Weather entrypoint and validated first-access scope only; no caller SQL, table, location, forecast window or mutation sequence.

Each capability remains independently fail-closed. The existing bridge verifies receipt stage identity, mutation classification and prohibition of automatic retry, cleanup and rollback.

## Trusted host entrypoint

`TrustedPrivateHostEntrypoint.dispatch()` accepts exactly one caller field: `authorization_issue_number`. It delegates to the merged bridge after canonical revalidation. There is no module-level daemon, shell dispatcher, root shell, command/path/argv/environment input or public-Weather authority reuse.

Source readiness deliberately reports:

- backend source implemented;
- host capability not installed;
- external entrypoint disabled;
- global executor execution disabled;
- credential binding execution disabled;
- Google control-plane execution disabled;
- read-only BigQuery execution disabled;
- SQLite write execution disabled.

Therefore merge of #549 still performs **no host installation and no private Google access**.

## Later owner-gated sequence

After #549 is merged and exact-main CI is green, the next work is not another undefined source architecture layer. It is a concrete one-time host capability installation/activation gate that installs the already reviewed backend/revalidator wiring and proves sanitized capability identity on `rpi5`.

Only after that capability is installed may separately frozen LIVE gates establish, in order and only when absent:

1. exact Weather application staging;
2. reviewed private runtime materialization;
3. fixed Google auth binding;
4. fixed Google project binding;
5. approved Analytics Hub linked dataset;
6. `rozkalns_weather#122` read-only first access.

`production_sqlite_forecast_snapshot_write` remains a separate later data-mutation authorization.

## Failure semantics

Future LIVE authorization is consumed immediately before its first authorized mutation. After mutation starts, source/head/CI/baseline drift, runtime mismatch, credential ambiguity, permission failure, linked-dataset mismatch, schema/cost mismatch, provider/API error or health regression permits only minimum sanitized read-only evidence followed by STOP.

There is no automatic retry, cleanup, rollback, credential replacement, alternate account/project/dataset/link, package installation, restart or SQLite recovery unless a later exact owner authorization explicitly freezes that recovery.

## CI boundary

The #549 workflow uses fixtures/fakes only. It imports and tests the existing bridge/runtime contracts, validates this closed JSON source contract and Python syntax, and never performs RPi5, credential, Google API, BigQuery, Analytics Hub or SQLite operations.
