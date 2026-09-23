# Automation Master Plan

Status: ACTIVE  
Owner: Andris Rožkalns  
Control repository: `rozkalnsandris/RPi5_main`  
Canonical file: `docs/AUTOMATION_MASTER_PLAN.md`  
Shared workflow repository: `rozkalnsandris/ops-workflows`  
Umbrella tracker: `RPi5_main#103`  
AUTO-RUN FULL controller: `RPi5_main#295`  
Owner-authorized pull-deploy roadmap: `RPi5_main#236`

## 1. Mandatory operating rule

Before starting any automation, deployment, audit, CI, runner, GitHub App, or production-control change covered by this program:

1. Read this file from current `RPi5_main/main`.
2. Read current `AGENTS.md` and `.github/start-mode-routing.json`.
3. Freshly resolve current `main`, exact-main CI, controller #295, tracker #103, latest relevant #191 handoff/comment, and the exact selected work item.
4. Treat historical SHAs, CI runs, authorizations and runtime evidence as evidence only; never infer that they remain current.
5. Select exactly one current lane/gate and work only on that lane plus required prerequisites.
6. Reconcile this file before executing a task that conflicts with the current plan.
7. Before every host-activation gate, audit every cross-repository producer/consumer interface used by that path; repository-local green CI alone is insufficient.
8. Preserve exact-SHA/digest identity, least privilege, persistence, health verification, fail-closed semantics and evidence boundaries unless a reviewed later contract explicitly replaces them.

Bare `START`, `START RPi5_main`, `SYNC RPi5_main` and `turpini` remain FAST-LANE v2.2. They never inherit prior AUTO-RUN FULL or LIVE authority.

## 2. Durable safety boundary

### GitHub/source work

GitHub is canonical for source, policy, tests, CI, reviews, issues, PRs and continuity.

FAST-LANE may perform safe repository reads and source/docs/tests work through Ready. Merge remains explicit owner authority under the project-level operating contract, even when repository-local automation can otherwise carry an issue through source convergence.

### Runtime/LIVE work

Live RPi5 state is canonical only when freshly observed through an authorized minimum-sufficient read-only or mutation path.

Separate explicit owner LIVE authority is required before host/runtime mutation unless a previously reviewed and explicitly activated standing contract grants a narrow automatic mutation class for an already-adopted target.

Sensitive classes remain separately exact-gated:

- sudo/root or host-control changes;
- systemd/service/timer mutation outside an already-activated fixed ordinary deploy contract;
- Docker host/control-plane changes outside an already-activated fixed ordinary deploy contract;
- database/schema/data migration, restore, cleanup or destructive action;
- credentials, secrets or permission changes;
- Cloudflare, DNS or network mutation;
- private-provider activation;
- filesystem ownership/permission changes;
- package installation/removal/upgrade;
- any new mutation class not already frozen by the exact current contract.

Authorization is consumed at the first authorized mutation. After mutation begins, unexpected state, error, timeout, source/head/runtime drift, lock conflict, health regression or authorization ambiguity means public-safe evidence plus STOP. No undeclared retry, rollback, cleanup, restart, alternate image/tag or alternate mutation path.

Never read or expose protected secrets/configuration merely to satisfy continuity.

## 3. Architecture boundary

### `rozkalnsandris/ops-workflows`

Canonical shared GitHub-side automation and delivery-policy repository.

It owns:

- reusable `workflow_call` workflows;
- shared public-repository CI/security policy;
- SIMPLE-DEPLOY GitHub-side workflow/policy/schema/tests;
- immutable external action/workflow pinning rules;
- GitHub-hosted image build/publish/promotion logic;
- shared exact source SHA / GHCR digest identity rules;
- shared production concurrency and receipt contracts.

It must not own RPi5 credentials, root helpers, arbitrary SSH/shell, private host configuration or production host mutation implementation.

Production consumers pin accepted shared workflows to immutable full `ops-workflows` commit SHAs, not mutable `@main`.

### `rozkalnsandris/RPi5_main`

Canonical trusted host/control-plane source repository.

It owns:

- this plan and host-side trust boundaries;
- reviewed static target/operation registries;
- generic SIMPLE-DEPLOY host executor;
- systemd source and host integration contracts;
- exact digest resolution/freeze and deterministic Compose lifecycle;
- local target serialization, fail-closed state, health/readiness checks and receipts;
- sensitive-operation gates and runtime evidence contracts.

It must not become a generic arbitrary remote execution plane.

### Consumer repositories

Consumer repositories own application code and only the smallest application-specific deployment surface:

- tiny immutable-SHA-pinned shared-workflow caller;
- application deployment manifest;
- Dockerfile/Compose contract;
- fixed service/target identity;
- health/readiness contract;
- persistent-volume/data invariants;
- explicit sensitive-operation exclusions.

Consumers must not copy the generic SIMPLE-DEPLOY algorithm.

## 4. Canonical deploy-impact classes

### `NO_DEPLOY`

No runtime effect.

### `AUTO_DEPLOY_SAFE`

Ordinary reviewed application/site/UI/API changes that passed exact-SHA CI and remain inside an already-reviewed, already-activated fixed deploy target.

After a target has completed its one-time SIMPLE-DEPLOY activation, this class may progress automatically through the fixed deploy path without a fresh per-release LIVE decision, but only within the exact adopted target contract.

### `MANUAL_ROLLOUT_REQUIRED`

Runtime dependency changes, schedulers, parsers/collectors, deployment/control-plane changes or equivalent higher-risk application mutations.

### `DB_HOST_APPLY_REQUIRED`

Database/schema/data mutation, host infrastructure, systemd/control-plane changes, secrets/permissions, Cloudflare/network and equivalent high-impact operations.

Unknown runtime-relevant paths fail toward review, never silently toward `NO_DEPLOY` or automatic deployment.

### Cross-cutting Track Y — Post-merge Auto-Live v1

Auto-Live v1 is retained as an architectural foundation for post-merge exact-target reconciliation and fail-closed automatic eligibility. It is not a competing current deployment framework.

Canonical A0 contract: `docs/AUTO_LIVE_V1.md` + `ops/deploy/auto-live-v1.json`. Roadmap/DoD: issue #421.

The retained A4 source-contract compatibility state is historical/non-authorizing:

`AUTO_LIVE_TRACK_Y_CURRENT=A4_DISCOVERY_READY_NO_CANARY_SELECTED`  
`A4_DISCOVERY_CONTRACT=ops/deploy/auto-live-a4-candidate-discovery.json`  
`A4_VOLATILE_CANDIDATE_SHA_PERSISTED=false`

These markers do not select the current deployment lane or activate Auto-Live.

SIMPLE-DEPLOY v1 is the concrete shared application-release profile for compatible Docker/Compose services. Where old Auto-Live manifests or controllers conflict with the accepted SIMPLE-DEPLOY consumer/runtime contract, reconcile them as compatibility/history rather than creating another deployment engine.

## 5. Current cross-project priority — SIMPLE-DEPLOY v1 first non-Weather reuse

Weather public acceptance is now **COMPLETE**. `rozkalns_weather#176` closed after fresh post-#177 runtime/API evidence and real consumer UI acceptance proved canonical DWD `station_05480` current-now behavior, populated forecast surfaces and truthful presentation. The older Weather freshness/UI wording in historical issues and receipts must not be treated as a current blocker.

The current cross-project priority is the first non-Weather reuse proof through Hermes Deals:

- shared SIMPLE-DEPLOY remains pinned to accepted `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- Weather remains the activated standing canary target;
- Hermes consumer caller/contract was accepted at `rozkalnsandris/hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c`;
- Hermes compatibility prerequisite #690 / PR #691 is COMPLETE;
- Hermes static source target binding #692 / PR #693 is COMPLETE;
- issue #698 / PR #699 is the current source-only existing-install adoption outcome needed before any Hermes host cutover;
- after #698 source merge and exact-main verification, Hermes still requires a separate exact host materialization/cutover/E2E gate before it is an activated target.

No source registration, tracker update or master-plan update grants LIVE authority.

### Accepted Weather source/runtime chain

The following are completed historical/accepted evidence rather than gates to rerun:

- one-time Weather SIMPLE-DEPLOY Phase A/B/C cutover;
- historical #672 source-only deterministic installer/principal prerequisite completed with reviewed principal provisioning;
- first genuine standing `AUTO_DEPLOY_SAFE` Weather release proof;
- public-data companion source/reconciliation;
- production public corpus bootstrap/integrity;
- recurring public-ingest activation and read-only verification;
- DWD current-observation provenance correction;
- dedicated exact-station current-now source adoption;
- final public API/runtime/UI acceptance under `rozkalns_weather#176`.

Consumed one-shot Weather authorizations remain non-reusable. Weather acceptance does not authorize database/data recovery, destructive cleanup, credentials, network/Cloudflare changes, private-provider activation or unrelated host control.

### Current SIMPLE-DEPLOY sequence

```text
shared SIMPLE-DEPLOY policy/workflow — COMPLETE
-> Weather static target + one-time activation — COMPLETE
-> Weather standing release proof — COMPLETE
-> Weather public data/runtime/UI acceptance — COMPLETE
-> Hermes consumer SIMPLE-DEPLOY contract — COMPLETE
-> Hermes RPi5 compatibility prerequisite #690/#691 — COMPLETE
-> Hermes static source target binding #692/#693 — COMPLETE
-> Hermes existing-install adoption source #698/#699 — CURRENT SOURCE OUTCOME
-> exact-main verification after #698 merge
-> separate exact Hermes host materialization/cutover + first reconciliation/E2E proof
-> migrate/test another compatible consumer as required for reuse confidence
-> declare SIMPLE-DEPLOY stable/default only after reuse criteria are actually satisfied
-> ONLY THEN revisit ops-workflows#96 Queue vNext
```

WeatherNext/private BigQuery remains a separate optional research lane and is not required for public-runtime health or Hermes adoption.

## 6. SIMPLE-DEPLOY steady-state contract

After successful one-time target activation, ordinary eligible release flow is:

```text
AUTO-RUN FULL consumer issue
-> source/tests/PR/review/CI
-> guarded merge
-> immutable-SHA-pinned shared SIMPLE-DEPLOY
-> GitHub-hosted image build
-> GHCR exact source SHA + immutable digest
-> stable production pointer as discovery only
-> generic RPi5 outbound pull deployer
-> freeze resolved digest
-> docker compose pull
-> docker compose up -d --wait --wait-timeout <bounded>
-> fixed health/readiness
-> deployed digest/source receipt
-> LIVE
```

Rules:

- build once; RPi5 does not rebuild application source during ordinary deployment;
- mutable production tag/channel is discovery only;
- immutable resolved digest is deployment identity;
- targets are independently serialized;
- persistent volumes/data are preserved;
- ordinary app deploy does not initialize, migrate, backfill, restore, delete or clean databases/corpora;
- ordinary app deploy does not mutate Cloudflare/network/secrets/private providers;
- failure after mutation is fail-closed and does not authorize fallback to an old deployment framework.

## 7. Weather acceptance — completed historical gate

The Weather acceptance chain is complete:

1. **COMPLETE** — fixed SIMPLE-DEPLOY Weather target activated and standing ordinary release path proven;
2. **COMPLETE** — `/health=200` and `/ready=200` accepted after reconciliation;
3. **COMPLETE** — public-data companion source and source reconciliation;
4. **COMPLETE** — installed-capability reconciliation and production public corpus bootstrap/integrity;
5. **COMPLETE / STANDING** — recurring public-ingest timer activation and subsequent successful operation;
6. **COMPLETE** — corpus integrity and station-scoped hourly/daily forecast surfaces;
7. **COMPLETE** — canonical DWD `station_05480` current-observation source-time/provenance semantics, including dedicated current-now feed work;
8. **COMPLETE** — real consumer UI acceptance in `rozkalns_weather#176`, including truthful freshness and official-warning separation.

Historical observations of stale data or `SOURCE_TIME_MISSING` are evidence of the problem that was resolved; they are not current runtime assertions.

WeatherNext/private-home activation remains separate and optional.

## 8. Fleet rollout after Weather

Fleet reuse is now the selected current SIMPLE-DEPLOY lane.

### Hermes Deals — first non-Weather consumer

Hermes uses the same shared GitHub-side workflow and the same generic RPi5 reconciler rather than a new project-specific deployment engine.

Accepted source facts:

- consumer contract: `hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c`;
- source compatibility prerequisite #690 / PR #691: COMPLETE;
- static target binding #692 / PR #693: COMPLETE;
- current existing-install adoption source: #698 / PR #699;
- RPi5-owned API-only adapter: `ops/deploy/simple-deploy-compose/hermes-deals-api.yml`;
- target alias: `hermes-deals`;
- liveness: `http://127.0.0.1:9128/api/health`;
- readiness: `not-applicable`;
- persistent database-volume identity: `hermes_deals_pgdata`;
- private runtime config and host namespace remain separately LIVE-gated.

Issue #692 completed the reviewed source target registration. Issue #698 now defines the bounded fail-closed path for adopting that already-registered target into an existing Weather-only SIMPLE-DEPLOY host installation. Neither source outcome installs the target, creates host paths, provisions private configuration or runs Docker.

After #698 source merge and exact-main verification, a separate exact LIVE/cutover decision must prove minimum host materialization, target installation and first reconciliation/E2E before Hermes counts as activated reuse.

### Reuse/stability rule

1. prove Hermes source adoption and separately prove its live E2E cutover;
2. migrate/test additional compatible consumers one at a time as needed to prove reuse beyond a one-off second target;
3. preserve each service's data and application invariants;
4. keep the generic executor shared and target configuration static;
5. do not revive old project-specific control planes for ordinary releases;
6. declare SIMPLE-DEPLOY stable/default only when Weather plus non-Weather reuse evidence satisfies the current program criteria.

New compatible projects should bootstrap from the shared caller + manifest model rather than inventing deployment infrastructure.

## 9. AUTO-RUN FULL Queue vNext — deliberately later

`ops-workflows#96` is the planned post-fleet queue evolution.

Do not implement or activate it in parallel with SIMPLE-DEPLOY rollout.

It remains **BLOCKED** until shared implementation, generic deployer, Weather E2E, non-Weather reuse, intended compatible-consumer migration/testing and stable ordinary-flow criteria are actually satisfied.

Only after SIMPLE-DEPLOY is stable/default may Queue vNext provide one explicit ordered activation such as:

```text
AUTO-RUN FULL QUEUE repo #1 #2 #3 #4

#1 -> source -> CI -> merge -> SIMPLE-DEPLOY -> receipt -> #2
#2 -> source -> CI -> merge -> SIMPLE-DEPLOY -> receipt -> #3
...
```

Sensitive DB/secret/network/host-control operations remain separate even if Queue vNext is later activated.

## 10. Other active architecture programs

### Owner-authorized pull deploy executor — #236

#236 remains a valid trust-boundary/architecture roadmap and historical source for deterministic owner-authorized operations. It does not override the selected SIMPLE-DEPLOY fleet-adoption lane.

Use its owner identity, replay, exact source/target, fail-closed and static-operation principles where applicable, but do not revive project-specific old Weather or Hermes broker/JIT execution as the ordinary release path.

### AUTO-RUN FULL controller — #295

#295 is the aggregate durable controller view for explicit issue-scoped AUTO-RUN FULL. Issue-local activation receipts remain authoritative per lane. Bare START/continuation never infers FULL from controller state.

### Hermes residual migration

Older Hermes Phase-4/control-plane issues such as #472 remain separate historical/backlog architecture. They must not be repurposed as an alternative ordinary deployment framework now that Hermes fits the SIMPLE-DEPLOY application-release profile.

## 11. Historical phase ledger

Completed or historical program phases are retained as references, not current-state assertions:

- Phase 0 — control plan/tracker: COMPLETE;
- Phase 1 — reusable baseline proof: COMPLETE;
- Phase 1B — split shared workflows into `ops-workflows`: COMPLETE;
- Phase 2 — read-only GitHub App preparation/canary: COMPLETE;
- Phase 3 — CV pull-deploy migration and legacy public self-hosted runner retirement: COMPLETE;
- historical P8/P9/P10 owner-authorized executor canaries: evidence in #191/#236 and Git history;
- historical Weather broker/operator upgrades: evidence only; #663 is superseded for steady state.

Do not use historical SHAs in this ledger as current source/runtime identity.

## 12. Current canonical sequencing

```text
1. Weather Phase A install-only — COMPLETE; authority consumed
2. Weather Phase-B correction/repair + schema-init — COMPLETE; authorities consumed
3. Weather Phase-C activation + first bounded reconciliation — COMPLETE; authority consumed
4. first genuine Weather AUTO_DEPLOY_SAFE release — COMPLETE
5. Weather public-data companion source/reconciliation — COMPLETE
6. production public corpus bootstrap/integrity — COMPLETE
7. recurring public ingest — COMPLETE / STANDING
8. DWD station_05480 provenance/current-now + real UI acceptance — COMPLETE (#176)
9. Hermes SIMPLE-DEPLOY consumer contract — COMPLETE
10. Hermes RPi5 compatibility prerequisite #690/#691 — COMPLETE
11. Hermes static source target binding #692/#693 — COMPLETE
12. Hermes existing-install adoption source #698/#699 — CURRENT SOURCE OUTCOME
13. exact-main verification after #698 merge — NEXT SOURCE GATE
14. separate exact Hermes host materialization/cutover + first reconciliation/E2E — LATER LIVE GATE
15. further compatible-consumer reuse/stability proof
16. only after stable/default criteria: ops-workflows#96 Queue vNext
```

If fresh GitHub or host evidence invalidates an accepted receipt, reclassify before action. Never rerun a consumed one-shot gate, improvise a Docker/config path, or treat a source merge as authority for a separately sensitive mutation class.

## 13. Current authorization state

No plan, tracker or source merge grants inferred LIVE authority.

The current Hermes existing-install adoption outcome #698 is source/docs/tests only. Its eventual source merge will not install the target on the running RPi5, materialize `/etc` or `/var/lib` state, provision private runtime configuration, run Docker/systemd, or authorize database/network/secret changes.

The completed Weather cutover/data/UI authorizations were consumed by their completed attempts and are non-reusable. The successful Weather cutover activated only the reviewed standing ordinary `AUTO_DEPLOY_SAFE` reconciliation contract for the already-adopted static Weather target.

Any new target cutover, data repair, timer/systemd change, private-provider activation or other sensitive mutation requires the exact current owner gate.
