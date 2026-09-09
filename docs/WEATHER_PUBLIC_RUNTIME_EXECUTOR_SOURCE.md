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

## First-bootstrap composition — Issue #410

Issue #410 adds `weather_public_runtime_bootstrap.py`, a source-only composition layer for the first public-only rollout. It does **not** add a process launcher, privileged helper, host wiring or executable Docker/systemd/database path. Its only caller-controlled request field is one authorization issue number; all source SHA, target, capability, bounds and baseline state must be independently re-derived by a capability-specific canonical revalidator and sanitized baseline resolver.

The bootstrap plan is deterministic and ordered:

1. `application_release` — existing `rozkalns-weather.public-runtime-release.v1` application release capability;
2. `persistent_volume_ensure` — retain/ensure logical `weather_data`;
3. `explicit_schema_init` — one idempotent schema initialization capability;
4. `readiness_schema_privacy` — read-only `/ready` schema/privacy verification;
5. `public_smoke_read_only` — optional read-only public provider smoke;
6. `bounded_dwd_truth_backfill` — DWD observation truth pinned to WMO station `10416`;
7. `bounded_deterministic_forecast_backfill` — exact Single Runs for `icon_d2`, `ecmwf_ifs`, and `ecmwf_aifs` at reviewed 00/06/12/18 UTC cycles;
8. `corpus_integrity_check` — read-only reconciliation of expected exact runs;
9. `recurring_public_ingest_schedule` — reviewed `PT30M` recurring public ingest schedule.

The source contract limits the first historical window to at most 180 inclusive days. The later canonical LIVE authorization must carry explicit start/end dates and one reviewed recovery decision before corpus writes become eligible. Accepted recovery decisions are deliberately non-destructive: either a separately verified backup is available, or the owner explicitly accepts proceeding without a pre-write backup. Neither choice authorizes backup creation, restore, database rollback or corpus deletion.

Mutation classes remain distinct even when a later owner chooses one bounded composite LIVE:

- application release;
- named-volume ensure;
- SQLite schema init;
- bounded DWD truth corpus write;
- bounded deterministic forecast corpus write;
- recurring public-ingest schedule install/update.

Readiness, public smoke and integrity are read-only stages. Application rollback never implies SQLite rollback/delete/restore, and the `weather_data` logical corpus volume must be retained across application replacement.

### Bootstrap sanitized baseline

The Issue #410 resolver protocol may represent only:

- deployed/not-deployed state and exact application source SHA when deployed;
- logical `weather_data` state;
- schema state and reviewed schema version when ready;
- public-ingest schedule state;
- coarse bootstrap stage state;
- an explicit `privacy_safe=true` assertion.

Unknown fields are rejected, including `HOME_LAT`, `HOME_LON`, credentials, raw configuration, exact host database paths, process/container environments and private runtime logs.

## Pre-activation authorization composition — Issue #432

Issue #432 adds `weather_public_runtime_preactivation.py`, a source-only bridge between the existing #236 owner-authorized LIVE-AUTH/READY-queue protocol and the Issue #410 weather bootstrap planner. It deliberately reuses `accept_issue`, `validate_queue_binding` and `verify_authorization_unchanged`; weather does not define a second owner identity, TTL, payload-hash or queue-binding protocol.

The caller supplies only one LIVE-AUTH issue number. Repository-controlled resolvers must independently provide the canonical authorization issue, READY queue, replay/consumption state, weather source/CI evidence and sanitized bootstrap baseline. The composition revalidates the authorization and queue before and after bootstrap planning, then binds a public-safe immutable envelope containing authorization/request identity and hashes, queue hash, exact weather SHA/target, sanitized baseline token, bounded dates/models/run hours/recovery decision and the fixed ordered stage/capability mapping.

This bridge is **pre-activation only**. Source state remains:

- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `production_mutation_enabled=false`;
- `production_mutation_started=false`;
- `process_launch_surface=false`;
- `separate_mutation_gates_required=true`.

Unknown/reordered/duplicate stage identities, authorization edits/expiry, queue drift/not-READY state, replay uncertainty, source/CI/baseline/recovery/date/model drift and private-input expansion fail closed. The module contains no subprocess/shell/network/root transport and does not install or invoke any helper.

### Future LIVE gate

Merging Issues #410 and #432 still does not make weather deployable. A future LIVE gate must freshly bind the exact merged weather SHA, exact target alias, successful exact-SHA CI, reviewed artifact identities, sanitized current baseline, bounded historical dates/model scope, recovery decision and exact mutation budgets. Source state keeps privileged dispatch, host wiring, production mutation enablement and production mutation start disabled.

## Trusted host-wiring source bridge — Issue #435

Issue #435 adds `weather_public_runtime_host_wiring.py` plus the machine contract `ops/deploy/weather-public-runtime-host-wiring.json`. The host-wiring interface is implemented in source but remains disabled on the host. This source bridge consumes the already validated `WeatherPreactivationEnvelope`; it does not create a second LIVE-AUTH, READY-queue, replay or owner-identity protocol.

The bridge binds every field of the pre-activation envelope into a canonical SHA-256. A later source revalidation compares the bound plan with that whole-envelope digest, so edits to authorization/queue hashes, source SHA, target, baseline token, dates, recovery decision or stage list cannot be silently accepted after binding.

The nine reviewed bootstrap stages are mapped to nine fixed logical helper identities. They are **identities only**, not executable paths or shell fragments. The mapping preserves the existing capability ID, mutation class, read-only flag and maximum operation count for each stage. Missing, reordered or altered stages, helper-budget drift, private-input expansion and execution-state expansion fail closed.

After Issue #435 source merge, all activation state is still false:

- global `ops/deploy/executor-operations.json` remains `execution_enabled=false`;
- Weather remains authorization class `STRICT` and `ordinary_live_all_eligible=false`;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `helper_installation_enabled=false`;
- `helper_invocation_enabled=false`;
- `production_mutation_enabled=false`;
- `production_mutation_started=false`;
- `process_launch_surface=false`;
- `runtime_live_authority=false`;
- automatic retry/cleanup/rollback remains disabled.

There is still no installer invocation, subprocess/shell transport, Docker/systemd call, SQLite operation, network call, root/sudo path or generic command/path/argv/environment authority in this source bridge. `HOME_LAT`, `HOME_LON`, WeatherNext/private BigQuery inputs, credentials, protected host paths, raw runtime configuration and private logs remain outside the public-only contract.

### Future activation after Issue #435

Issue #435 does not itself activate Weather. Before any first public-only runtime mutation, a **separate exact LIVE authorization** must freshly bind the trusted host and target alias, exact merged Weather SHA and exact-SHA CI, current `RPi5_main` SHA, sanitized runtime baseline, reviewed host-wiring/helper identities, whole preactivation SHA-256, bounded date/model/run-hour scope, WMO `10416`, recovery decision, exact mutation budgets and health/readiness/provider/schema/storage/corpus-integrity postconditions.

The first selected runtime mutation consumes that later LIVE authorization. Any error, ambiguity or source/host drift after mutation start requires STOP with no undeclared retry, rollback, cleanup or alternate mutation route. Application rollback still never implies SQLite restore/delete/cleanup.

## Executable/installable Weather capability source — Issue #438

Issue #438 closes the remaining **source-side execution gap** without activating the host. It adds:

- `weather_public_runtime_execution.py`, which recompiles a validated `WeatherHostWiringPlan` into an immutable `WeatherExecutablePlan` and derives every helper argv only from canonical source/authorization/baseline/date/model/run-hour/recovery evidence;
- `weather_public_runtime_helper_launch.py`, a one-shot fixed process launcher that revalidates the executable plan immediately before launch, uses `shell=False`, a fixed environment, bounded output/timeout, one invocation per stage and no retry/cleanup/rollback;
- `weather_public_runtime_stage_helper.py` plus `ops/bin/rozkalns-weather-public-runtime-stage-helper`, the installable capability-specific helper source for the nine reviewed Weather stages;
- `ops/deploy/weather-public-runtime-execution.json`, the machine-readable installation/activation boundary.

The installed helper path is fixed at `/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper`. The helper cannot run merely because source is merged: it requires the fixed root-owned `/etc/rozkalns-weather/public-runtime-helper-activation.json` contract with mode `0600`, exact target/operation, exact Weather source SHA, whole preactivation SHA-256, bounded dates, recovery decision and the complete ordered helper-ID allowlist. That activation file is a **future LIVE mutation** and is not created by Issue #438.

The source implementation resolves helper IDs to fixed Weather stage implementations for application release, logical volume ensure, explicit schema init, readiness, public smoke, bounded DWD WMO `10416` truth backfill, bounded deterministic ICON-D2/IFS/AIFS backfill, corpus integrity and the 30-minute public-ingest schedule. Generic shell text, caller-selected executable paths, arbitrary argv/environment, WeatherNext/private BigQuery inputs and home coordinates are not accepted authority.

After Issue #438 source merge the default state still remains inactive:

- global `executor-operations.json` remains `execution_enabled=false`;
- `helper_process_launch_wired=false`;
- `privileged_dispatch_enabled=false`;
- `host_wiring_enabled=false`;
- `helper_installation_enabled=false`;
- `helper_invocation_enabled=false`;
- `production_mutation_enabled=false`;
- `production_mutation_started=false`.

Therefore Issue #438 makes the narrow implementation **available in reviewed source**, but it does not install the helper, create the root-owned activation file, enable dispatch, invoke Docker/systemd, initialize/write SQLite, backfill corpus data, start a service, or otherwise mutate RPi5. The first actual installation/activation/rollout remains one separately authorized exact `STRICT` LIVE envelope and must revalidate the current merged RPi5_main SHA, exact Weather SHA/CI, current sanitized host baseline, helper source identity, whole preactivation hash, mutation budgets and postconditions immediately before mutation.

## Isolated helper install layout — Issue #443

Issue #443 closes the source-side installability gap discovered after #438: the fixed stage-helper entrypoint imported `deploy_executor.*`, but #438 did not freeze where that package would be installed on a clean host.

The exact source-only install contract is now `ops/deploy/weather-public-runtime-helper-install.json`. It preserves the #438 executable identity `/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper` and defines one dedicated sibling support root `/usr/local/libexec/rozkalns-weather-public-runtime` with package root `/usr/local/libexec/rozkalns-weather-public-runtime/deploy_executor`.

The manifest lists exactly 13 artifacts: the fixed entrypoint, a dedicated import-free `deploy_executor/__init__.py`, and the 11 reviewed transitive Python modules needed by the stage-helper path. It does not wildcard-copy the full deploy executor package and does not install unrelated state, transport, credential or project adapter modules. In particular, it does not overwrite or upgrade `/usr/local/libexec/rozkalns-deploy-executor/deploy_executor`.

The entrypoint derives the support root only from its own fixed filename and sibling directory, inserts that exact root into `sys.path`, imports `deploy_executor`, and verifies that the loaded package initializer resolves to the expected sibling file before importing Weather modules. There is no caller-provided `PYTHONPATH`, site-package dependency, ambient repository checkout, working-directory dependency or shell-profile dependency.

`tests/test-deploy-executor-weather-public-helper-install.py` assembles the manifest into a temporary host-like filesystem and runs the entrypoint with `python -I` plus a scrubbed environment. The expected terminal result is the existing fail-closed activation error with exit code 78; `ModuleNotFoundError`, `ImportError` or the dedicated install-layout error are failures. The same test composes the #438 execution invariant suite so installability cannot bypass the fixed helper/stage/budget/security contract.

Issue #443 remains **source only**. The manifest does not self-install, and all execution/installation/activation state remains false: global executor execution, privileged dispatch, host wiring, helper installation/invocation, process-launch wiring and production mutation are still disabled. Creating `/usr/local` files, writing the root-owned activation file, updating a trusted checkout, changing ownership/modes on the host, invoking the helper or starting the Weather rollout all require a later separately authorized exact `STRICT` LIVE envelope.

## Weather trusted RPi5 checkout bootstrap — Issue #446

Issue #446 freezes the source provenance boundary that must exist before the #443 install manifest can be used on a real host. The contract is `ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json` and the only trusted checkout target is `RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted`.

The ordinary `RPi5_main` manager checkout is explicitly allowed to be stale, dirty or detached only as a Git object/ref manager. The bootstrap grants no authority to modify its working-tree bytes, index or HEAD. A future separately authorized Composite STRICT LIVE transaction may perform exactly two Git mutations in order: `git fetch origin main`, then one `git worktree add --detach` for the fixed Weather target and exact authorized `RPi5_main` SHA. Reset, rebase, clean, checkout/switch, merge/pull, worktree removal/pruning, branch/commit/push and force operations are forbidden.

After fetch and before worktree creation, `origin/main` must equal the exact authorized SHA and that SHA must descend from the reviewed #443 merge baseline `95b6b95b132614cbc330d6d764d0557079a67534`. The target must be absent before the first mutation. The created checkout must be exact, detached, clean, bound to the canonical GitHub origin and contain the reviewed Weather helper install/execution/host-wiring contracts plus the fixed stage-helper entrypoint.

Both `weather-public-runtime-helper-install.json` and `weather-public-runtime-execution.json` bind this exact checkout contract and target. The ordinary manager checkout is not an accepted helper installation source. Source merge does not create the checkout and does not authorize helper installation, activation, invocation, Docker/systemd/SQLite/corpus mutation or any other LIVE step.

## Explicitly separate gates

The static operation, bootstrap source composition, pre-activation bridge, host-wiring bridge, executable helper source, isolated install manifest and trusted-checkout contract do not themselves authorize:

- RPi5 deploy/redeploy/restart or executor global enablement;
- privileged dispatch activation, live host wiring, helper installation or helper invocation;
- production SQLite schema initialization;
- historical forecast/truth corpus writes;
- corpus backup, restore, deletion or destructive rollback;
- `.env`, credentials, Google Cloud, BigQuery or WeatherNext private access;
- `HOME_LAT`, `HOME_LON` or exact home coordinates;
- Cloudflare, network or firewall mutation;
- package installation, generic `sudo`/root authority or arbitrary shell/path/argv/environment authority;
- ambient repository/PYTHONPATH authority or mutation of the existing deploy-executor package;
- repository settings, rulesets, permissions or secrets changes.

Application rollback, if a later reviewed LIVE capability is activated, must never imply SQLite rollback, deletion or restore. The `weather_data` corpus volume is retained across application replacement by contract.

DWD remains the authoritative severe-weather warning source. WeatherNext remains research output and is optional/access-pending in this public-only runtime class.
