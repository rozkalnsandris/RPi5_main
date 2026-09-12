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

## Pre-activation and host-wiring — Issue #432 and Issue #435

`weather_public_runtime_preactivation.py` reuses the existing owner
`rozkalns.live-auth.v1` protocol, normalized READY queue binding, authorization
immutability and replay checks. It creates an immutable public-safe preactivation
envelope; it does not grant host execution.

`weather_public_runtime_host_wiring.py` binds the whole preactivation envelope
to a SHA-256 and maps the nine bootstrap stages to the fixed helper identities in
`ops/deploy/weather-public-runtime-host-wiring.json`.
The host-wiring interface is implemented in source but remains disabled on the host;
any later activation still requires a separate exact LIVE authorization.

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

## Weather trusted checkout — Issue #446 (legacy evidence contract)

The original contract is
`ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json`.
After the fail-closed LIVE attempt described under Issue #455, this original
checkout is retained as evidence-only and is no longer current mutation authority.

The ordinary `RPi5_main` manager checkout may be stale, dirty or detached only
as a Git object/ref manager. Its working tree, index and HEAD are not mutation
authority.

Under the original #446 contract, a separately authorized Composite STRICT LIVE
could perform exactly:

1. `git fetch origin main`;
2. one fixed `git worktree add --detach` at
   `RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted` for the exact
   authorized current `RPi5_main` SHA.

That original target is now legacy evidence only; current mutation authority uses
the #455 successor contract described below.

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

## Privileged install successor bridge — Issue #455

After a fail-closed first LIVE attempt created the original trusted checkout but
stopped before helper installation, Issue #455 introduced the reviewed successor
contract `ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json`
and checkout `RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted`.
The legacy `RPi5_main-weather-public-runtime-trusted` checkout is evidence-only:
it is never reset, updated, removed, cleaned or reused as mutation authority.
The #454 operator binds this successor contract and the #455 canonical 13-artifact
allowlist; it does not create a second independent helper-install identity.

Issue #482 reconciles Composite execution with that intentionally persistent successor
checkout. Before durable replay consume, the operator now performs a fixed, read-only
compatibility preflight. An existing successor checkout is reusable only when it is the
exact authorized current `RPi5_main` SHA, detached, clean, bound to the fixed origin,
descends from the reviewed minimum ancestor, and contains the canonical helper manifest
and fixed source identities. That verified-existing path performs **zero** fetch/worktree
mutations. If the fixed target is absent, the existing bounded fetch + detached-worktree
creation path remains available. Wrong SHA, dirty/attached state, wrong origin, unsafe
filesystem identity or source-closure drift fails before replay consume, so authorization
reuse remains allowed and no host/production mutation is reported. The operator never
repairs, resets, cleans, updates, removes or overwrites an existing checkout.


## Installed operator compatibility upgrade — Issue #487

Issue #487 adds a source-only bridge for the narrow post-#482 compatibility gap
between the earlier reviewed Weather operator installation and the corrected
Composite source contract. The historical checkout
`RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted` remains
immutable evidence and is never reset, cleaned, switched, removed, pruned or
advanced in place.

The upgrade uses a new fixed checkout identity:

`RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-operator-upgrade-trusted`

Its source contract permits at most one reviewed-manager `git fetch origin main`
and one fixed detached `git worktree add` for the exact separately authorized
current `RPi5_main` SHA. No caller selects a path, repository URL, command, argv
or environment, and there is no manager-checkout repair or alternate checkout
route.

`ops/deploy/weather-public-runtime-operator-upgrade.json` freezes the predecessor
source at `7b54434d296bcd7030464f3fc13e4a601acaa2d9` and permits exactly one changed
artifact in the canonical 23-artifact operator closure:
`ops/lib/deploy_executor/weather_public_runtime_operator.py`. A source-diff guard
must fail closed if any other installed artifact changes between that predecessor
and the exact upgrade checkout.

Before any runtime write, the capability-specific zero-argument upgrade bridge
must verify the complete installed operator closure, exact membership,
ownership/modes and hashes. Every non-target installed artifact must already
match the exact target checkout byte-for-byte, while the target module must match
the frozen predecessor hash. The only allowed runtime publication is a
same-directory, no-follow, exclusive temporary file followed by one atomic
replacement of
`/usr/local/libexec/rozkalns-weather-public-runtime-operator/deploy_executor/weather_public_runtime_operator.py`,
with file and parent-directory fsync. There is no automatic retry, cleanup,
rollback or backup restore; a failure after temporary-file creation preserves
evidence for an explicit owner recovery decision.

Source merge does not create the new checkout, run the upgrade, invoke the
operator, or promote `ops-workflows#46` to READY. A separate exact LIVE
authorization remains required, followed by fresh installed-closure proof and a
fresh sanitized first-deployment baseline before the Weather rollout can become
eligible.

## Composite LIVE operator wiring — Issue #454

Issue #454 adds the reviewed source-side operator composition that was deliberately
absent after #449. The machine contract is
`ops/deploy/weather-public-runtime-operator.json`; its source state is
`SOURCE_READY_HOST_NOT_INSTALLED`.

The only caller-controlled value remains `authorization_issue_number`. The
operator composes the existing canonical Composite revalidator with durable replay
consumption, the exact trusted-checkout contract, the fixed 13-artifact helper
install transaction, atomic activation publication and the existing
`WeatherOneShotStageLauncher`. No caller-selected path, executable, argv,
environment, repository URL, helper identity, Docker target, systemd unit or
SQLite path is added.

Immediately before the first mutation the same human LIVE-AUTH must still pass
owner/TTL/raw-body immutability, READY queue binding, Weather exact-SHA CI,
exact-current `RPi5_main` SHA/CI/ancestor and sanitized host-baseline validation.
The first mutation is the durable SQLite replay consume. From the instant that
consume is attempted, authorization reuse is forbidden. Every later privileged
boundary revalidates the same authorization and requires that exact request to be
`CONSUMED`; it must not become `AVAILABLE` again.

The fixed gate order remains unchanged. One implementation correction keeps its
mutation classes honest: `application_release` validates/materializes the exact
release and performs Compose build only. It does **not** run `compose up`, because
the Weather service declares `weather_data` and Compose can create a declared
named volume while starting a service. `persistent_volume_ensure` therefore
creates the exact named volume first and only then performs the fixed Weather
application apply. This prevents implicit volume creation from laundering the
`docker.named-volume-ensure` budget into the earlier application gate.

The sanitized stage baseline never derives deployed provenance from the Compose
project name alone. A deployed result requires the exact immutable release Git
HEAD/clean tree and the running Weather container image ID to match the image ID
resolved from that exact release Compose file. Readiness parsing retains only the
privacy-safe schema state; credentials, coordinates, database paths and raw logs
are not returned.

The operator's future host-install closure is frozen separately in
`ops/deploy/weather-public-runtime-operator-install.json`. It contains the fixed
entrypoint, exact transitive controller modules (including the #455 canonical
privileged-install allowlist source) and the Weather-only execution-disabled registry. This operator closure is **not** part of the
13-artifact stage-helper budget. Source merge does not install it. Host installation
still requires a separate explicit owner LIVE gate before a fresh Composite
LIVE-AUTH can be executed.

Failure semantics remain fail closed. After replay-consume attempt or any later
mutation attempt, an error/timeout/drift/lock/health/authorization ambiguity means
STOP with minimum public-safe evidence. There is no automatic retry, cleanup,
rollback, restore, delete, manager-checkout repair or alternate route.

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
