# Weather public runtime executor source contract

This document is the canonical `RPi5_main` source-side contract for the private
`rozkalns_weather` public-only RPi5 runtime. It describes reviewed source only.
Nothing in this document, a READY queue, or a source merge proves a Weather
runtime exists on the host or grants LIVE authority.

## Reviewed Weather handoff

The original reviewed design/provenance source is
`rozkalnsandris/rozkalns_weather@6296556e783967c0897abc4e27368295a1158c7e`.

Pinned reviewed handoff artifacts:

- `deploy/runtime-descriptor.json` blob `dde970523486123e2809388bff9ed8b643cb6940`;
- `deploy/docker-compose.public.yml` blob `41b40d614907acd7f257c2fd4eea368de47fb1ea`;
- `deploy/public-ingest-schedule.json` blob `d67dd0bb606f6d25922972729a4ff1ad33a68224`;
- `docs/RPI5_PUBLIC_RUNTIME_HANDOFF.md` blob `8004da2243aa3bb3e1fb9917bc8819134f117cf8`.

A later deployment candidate supplies its own exact Weather SHA. That SHA must be
merged/reachable from current Weather `main` and must have successful exact-SHA
CI before it is eligible for runtime use.

## Static release operation — Issue #408

`ops/deploy/executor-operations.json` registers
`rozkalns-weather.public-runtime-release.v1` for:

- source `rozkalnsandris/rozkalns_weather` (repository ID `1359499204`);
- target `rozkalns-weather-public-rpi5`;
- execution location `trusted-home-host`;
- authorization class `STRICT`;
- `ordinary_live_all_eligible=false`;
- baseline resolver `rozkalns-weather.public-runtime-baseline.v1`;
- rollback policy `NONE`.

The global registry remains `execution_enabled=false`.

The generic release budget is deliberately limited to:

1. `filesystem.release-materialization <= 1`;
2. `docker.named-volume-ensure <= 1`;
3. `docker.compose-build <= 1`;
4. `docker.compose-application-apply <= 1`;
5. `systemd.public-ingest-schedule-install-or-update <= 1`.

Those categories are contract metadata until a valid owner authorization is
accepted. They do not authorize SQLite/backfill, trusted-checkout creation,
helper installation, or helper activation.

## Public-only bootstrap — Issue #410

The first-bootstrap composition fixes the ordered application stages:

1. `application_release`;
2. `persistent_volume_ensure`;
3. `explicit_schema_init`;
4. `readiness_schema_privacy`;
5. `public_smoke_read_only`;
6. `bounded_dwd_truth_backfill`;
7. `bounded_deterministic_forecast_backfill`;
8. `corpus_integrity_check`;
9. `recurring_public_ingest_schedule`.

The public bootstrap scope is fixed to:

- truth provider `dwd_observations`, WMO `10416`;
- deterministic models `icon_d2`, `ecmwf_ifs`, `ecmwf_aifs`;
- run hours `00/06/12/18` UTC;
- DWD truth chunks of 14 days;
- at most 180 inclusive historical days;
- recurring public ingest cadence `PT30M`;
- recovery decision exactly `verified-backup-available` or
  `owner-accepted-no-prewrite-backup`.

Neither recovery decision authorizes automatic backup creation, restore,
database rollback, corpus deletion, cleanup, or destructive recovery.
`weather_data` is retained independently from application replacement.

WeatherNext/private BigQuery inputs and `HOME_LAT`/`HOME_LON` are outside this
public-only runtime class.

## Pre-activation and host-wiring — Issues #432 and #435

`weather_public_runtime_preactivation.py` reuses the existing owner
`rozkalns.live-auth.v1` protocol, normalized READY queue binding, authorization
immutability and replay checks. It creates an immutable public-safe preactivation
envelope; it does not grant host execution.

`weather_public_runtime_host_wiring.py` binds the whole preactivation envelope
to a SHA-256 and maps the nine bootstrap stages to the fixed helper identities in
`ops/deploy/weather-public-runtime-host-wiring.json`.

The read-only stages remain readiness, optional public smoke, and corpus
integrity. SQLite schema/truth/forecast writes remain separate mutation classes.
All host-wiring and production flags remain false in source.

## Executable helper source — Issue #438

Issue #438 added the fixed executable plan, one-shot helper launcher, candidate
materializer and Weather stage helper. The installed executable identity is:

`/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper`

The helper requires a future root-owned activation file:

`/etc/rozkalns-weather/public-runtime-helper-activation.json`

with schema `rozkalns-weather.public-runtime-helper-activation.v1`, owner
`root:root`, mode `0600`, exact Weather source identity, whole preactivation
SHA-256, bounded dates/recovery and the complete fixed helper-ID allowlist.

Launch remains `shell=False`, fixed-environment, bounded-output/timeout,
one-invocation-per-stage and no automatic retry/cleanup/rollback.

## Isolated helper install layout — Issue #443

`ops/deploy/weather-public-runtime-helper-install.json` freezes exactly 13
source-to-installed artifacts. The support root is:

`/usr/local/libexec/rozkalns-weather-public-runtime`

and the isolated package root is:

`/usr/local/libexec/rozkalns-weather-public-runtime/deploy_executor`

Directories are `0755`, the entrypoint is `0755`, Python modules are `0644`,
and required UID/GID are `0/0`.

The manifest does not wildcard-copy the deploy executor and does not overwrite
`/usr/local/libexec/rozkalns-deploy-executor/deploy_executor`. It has no
ambient checkout, `PYTHONPATH`, user-site or shell-profile dependency.

The Composite revalidator introduced by #449 is a controller-side source
authority component and is intentionally not added to this 13-artifact helper
runtime closure.

## Weather trusted checkout — Issue #446

The canonical contract is
`ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json`.

The ordinary `RPi5_main` manager checkout may be stale, dirty or detached only
as a Git object/ref manager. Its working tree, index and HEAD are not mutation
authority.

A future separately authorized Composite STRICT LIVE may perform exactly:

1. `git fetch origin main`;
2. one fixed `git worktree add --detach` at
   `RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted` for the exact
   authorized current `RPi5_main` SHA.

The authorized SHA must equal fresh `origin/main` and descend from reviewed
minimum ancestor `95b6b95b132614cbc330d6d764d0557079a67534`.
Reset, rebase, clean, checkout/switch, merge/pull, worktree removal/pruning,
branch/commit/push and force operations are forbidden.

## Composite STRICT LIVE authority bridge — Issue #449

Issue #449 closes the final source-side authority-composition gap with:

- `ops/lib/deploy_executor/weather_public_runtime_composite.py`;
- `ops/deploy/weather-public-runtime-composite-live.json`;
- fixture/security regression tests;
- explicit binding from `weather-public-runtime-execution.json`.

The generic `rozkalns.live-auth.v1` block remains authority only for the exact
normalized release operation and its five release budget categories. It cannot
be interpreted as checkout/helper/activation/SQLite authority.

For the first Composite rollout, the **same human-authored authorization issue**
must also contain exactly one Weather supplemental block with schema
`rozkalns.weather-composite-live-auth.v1`. The supplemental block carries only:

- fixed host alias `rpi5`;
- exact current `RPi5_main` SHA;
- expected sanitized bootstrap-baseline token;
- bounded start/end dates;
- one reviewed recovery decision;
- fixed helper artifact count `13`;
- the exact supplemental mutation budget.

The supplemental budget remains distinct:

- `git.trusted-checkout-fetch <= 1`;
- `git.trusted-checkout-worktree-add <= 1`;
- `filesystem.weather-helper-install-transaction <= 1`;
- `filesystem.weather-helper-activation-publish <= 1`;
- `sqlite.schema-init <= 1`;
- `sqlite.corpus-truth-backfill <= 1`;
- `sqlite.corpus-forecast-backfill <= 3`.

The concrete canonical revalidator accepts only an authorization issue number.
It revalidates owner identity, TTL, raw-body immutability, replay availability,
READY queue binding, Weather source reachability and exact-SHA CI, exact current
`RPi5_main` SHA and CI, the reviewed RPi5 minimum ancestor, fixed host/target,
and the sanitized baseline token. Authorization and queue are read again before
the immutable source plan is returned.

Private authorization/queue control-plane reads continue through the reviewed
read-only executor GitHub App boundary. Weather and `RPi5_main` are public
repositories, so source/CI revalidation uses a fixed credential-free GitHub API
reader limited to exactly those two repositories. Tests use fixtures/fakes and
perform no real GitHub, Docker, systemd, SQLite or host mutation.

`ops-workflows#46`, a generic release LIVE-AUTH, source merge, and read-only
readiness evidence are all necessary inputs but are **individually insufficient**
to authorize host mutation.

Source merge keeps every activation state inactive:

- `runtime_live_authority=false`;
- trusted checkout disabled;
- helper installation/invocation disabled;
- activation publication disabled;
- privileged dispatch disabled;
- host wiring disabled;
- production mutation disabled/not started;
- no generic shell/path/argv/environment authority;
- no automatic retry/cleanup/rollback/restore/delete.

A later owner gate must create a fresh human authorization containing both the
normal release block and the exact Weather supplemental block, then JIT-bind the
then-current Weather SHA/CI, exact current `RPi5_main` SHA/CI, sanitized live
baseline, bounded dates/recovery and fixed source contracts. The first future
authorized mutation consumes that authorization. After mutation start, any
error, timeout, drift, lock conflict, health regression or authorization
ambiguity requires STOP with minimum read-only evidence and no undeclared retry,
cleanup, rollback or alternate route.

## Explicitly separate gates

None of the reviewed source contracts authorize by themselves:

- RPi5 deployment/restart or global executor enablement;
- helper installation, activation or invocation;
- Docker/systemd/SQLite/corpus mutation;
- backup/restore/delete/cleanup or destructive database recovery;
- credentials, secrets, WeatherNext/private BigQuery or exact home coordinates;
- Cloudflare/network/firewall/package/user/group/permission mutation;
- generic `sudo`/root/shell/path/argv/environment authority;
- manager-checkout repair;
- repository settings, rulesets, permissions or secrets changes.

DWD remains the authoritative severe-weather warning source in Germany.
WeatherNext remains a first-class research model and must never be presented as
an official warning source.
