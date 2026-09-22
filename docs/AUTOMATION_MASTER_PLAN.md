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

FAST-LANE may perform safe repository reads and source/docs/tests work through Ready. Merge remains explicit owner authority unless an exact current AUTO-RUN FULL issue activation grants issue-scoped merge authority under the repository-local contract.

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

The A0/A2 source contracts remain useful for exact source/target identity, full production-baseline-to-target classification, target serialization, least privilege and first-activation owner-gate semantics. Historical Auto-Live source state with `execution_enabled=false` must not be interpreted as current runtime activation.

The retained A4 source-contract compatibility state is historical/non-authorizing and exists so current validators can distinguish durable policy state from volatile candidate SHAs:

`AUTO_LIVE_TRACK_Y_CURRENT=A4_DISCOVERY_READY_NO_CANARY_SELECTED`  
`A4_DISCOVERY_CONTRACT=ops/deploy/auto-live-a4-candidate-discovery.json`  
`A4_VOLATILE_CANDIDATE_SHA_PERSISTED=false`

These A4 markers do not select the current deployment lane, do not activate Auto-Live, and do not override current fresh Weather continuity.

SIMPLE-DEPLOY v1 is now the concrete shared application-release profile for compatible Docker/Compose services. Where old Auto-Live manifests or controllers conflict with the accepted SIMPLE-DEPLOY consumer/runtime contract, reconcile them as compatibility/history rather than creating another deployment engine.

## 5. Current cross-project priority — SIMPLE-DEPLOY v1 Weather public acceptance

The one-time Weather SIMPLE-DEPLOY cutover, first standing release proof, public corpus bootstrap/integrity and recurring public ingest are now accepted historical/runtime evidence. The current public Weather focus is truthful current-observation freshness/provenance plus consumer UI acceptance. Fresh GitHub state and the latest relevant #191 continuity receipt remain authoritative over point-in-time values in this plan.

### Accepted source/runtime chain

- shared SIMPLE-DEPLOY: `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- initial Weather cutover consumer: `rozkalns_weather@606981d10eee59d13b802f6a682abf1daa2aa8a5`;
- historical #672 source-only deterministic installer/principal prerequisite merged via PR #673, including the reviewed principal provisioning path;
- #674 sequencing work merged and enabled the reviewed Phase A/B/C path;
- Phase A install-only, post-install Phase-B repair, Phase B schema-init and Phase C activation all completed under their separate consumed owner authorizations;
- Phase B preserved `rozkalns-weather-public_weather_data` and changed `/ready` from `503` to `200`;
- Phase C completed the first bounded reconciliation and activated the reviewed generic SIMPLE-DEPLOY scheduler for the fixed Weather target;
- the first genuine post-cutover standing release `rozkalns_weather@789a79820807829cc9b057d9ffafc56e0e41afe9` reached the fixed target through pinned `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c` and recorded `/health=200` plus `/ready=200`;
- Weather public-data companion source #682 / PR #683 merged at `RPi5_main@a78d53404f1e614386550f77c6635881b73cc88e`;
- source reconciliation #684 / PR #685 merged at `RPi5_main@edc5003fba34523e4b400fc18e2a5446c3928a93`, separating historical bootstrap source pinning from post-bootstrap recurring-enable semantics and providing deterministic installed-artifact reconciliation;
- later separately owner-authorized runtime work reconciled the installed companion, completed the production public corpus/integrity path and enabled recurring public ingest;
- fresh read-only acceptance receipt #191 comment `5779640396` on 2026-09-22 observed `rozkalns-weather-public-ingest.timer` enabled/active/waiting, a successful oneshot exit `0`, `/health=200`, `/ready=200`, corpus integrity `ok=true`, populated corpus, and populated `station_05480`-scoped hourly/daily forecasts.

These receipts do not create reusable authority for database/data recovery, destructive cleanup, credentials, network/Cloudflare changes, private-provider activation or unrelated host control. Consumed one-shot authorizations remain non-reusable.

### Current exact Weather gate

`RPi5_main#669` is historical one-time cutover metadata. Its Phase A/B/C Definition of Done is satisfied; stale issue text must not be interpreted as reopening or reauthorizing those gates.

The standing ordinary reconciliation contract is active only for the already-adopted fixed target `rozkalns-weather-public-rpi5` and eligible `AUTO_DEPLOY_SAFE` releases within the reviewed static target contract.

Current sequence from this checkpoint:

```text
one-time Weather SIMPLE-DEPLOY Phase A/B/C cutover — COMPLETE
-> first genuine Weather AUTO_DEPLOY_SAFE standing release proof — COMPLETE
-> Weather public-data companion source/reconciliation — COMPLETE
-> one-time public corpus bootstrap + integrity — COMPLETE
-> recurring public-ingest timer — ACTIVE / READ-ONLY VERIFIED
-> resolve/understand DWD current-observation freshness + provenance
-> verify truthful consumer UI with real provider/current/corpus evidence
-> complete public Weather acceptance when its own DoD passes
-> migrate/test additional compatible consumers when explicitly selected
```

Fresh read-only evidence on 2026-09-22 found `/api/current` correctly bound to canonical DWD CDC `station_05480`, but its newest stored observation was `2026-09-21T23:00:00Z`; provider health reported `dwd_observations = ok / unknown / SOURCE_TIME_MISSING`. This is a remaining acceptance concern, not permission to rerun bootstrap or scheduler activation. The consumer UI source already contains explicit stale semantics and must continue to avoid presenting old observations as current-now.

WeatherNext/private BigQuery remains a separate optional research lane. It is not required for public-runtime health and is not authorized by public Weather receipts.

### Historical Weather v10 path

`RPi5_main#663` is CLOSED/not_planned and superseded for steady-state ordinary Weather deployment.

The Weather-specific successor broker / registration / operator / queue / JIT / Composite path remains historical evidence only. Do not execute it merely because old source, issues or handoff text still exists.

No new v11/v12 successor to that ordinary-release control plane should be created while Weather fits SIMPLE-DEPLOY.

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
- one target is serialized at a time;
- persistent volumes/data are preserved;
- ordinary app deploy does not initialize, migrate, backfill, restore, delete or clean databases/corpora;
- ordinary app deploy does not mutate Cloudflare/network/secrets/private providers;
- failure after mutation is fail-closed and does not authorize fallback to an old deployment framework.

## 7. Weather acceptance sequence after #669

The one-time cutover, standing release proof and public DATA lane have advanced to recurring operation. The current acceptance sequence is:

1. **COMPLETE** — fixed SIMPLE-DEPLOY Weather target activated and standing ordinary release path proven;
2. **COMPLETE** — `/health=200` and `/ready=200` accepted after reconciliation and again in later read-only evidence;
3. **COMPLETE** — #682/PR #683 public-data companion source plus #684/PR #685 source reconciliation;
4. **COMPLETE** — separately authorized installed-capability reconciliation and one-time production public corpus bootstrap/integrity path;
5. **ACTIVE / READ-ONLY VERIFIED** — recurring public-ingest timer; 2026-09-22 evidence recorded an enabled/active timer and successful oneshot;
6. **PASS at audit point** — corpus integrity `ok=true` and station-scoped hourly/daily forecast endpoints populated;
7. **REMAINING ACCEPTANCE** — investigate/resolve canonical DWD `station_05480` current-observation freshness/provenance; latest sampled observation was stale and provider health reported `SOURCE_TIME_MISSING`;
8. **REMAINING ACCEPTANCE** — verify the consumer UI truthfully renders real current/provider/corpus evidence, including stale-state behavior, before public Weather acceptance is closed.

Deployment health/readiness and forecast corpus availability are necessary but not sufficient evidence for final consumer UI acceptance. Never fabricate freshness or silently substitute legacy station `10416` for canonical measured benchmark `05480`.

WeatherNext/private-home activation is not required for the first usable public Weather UI and remains separate.

## 8. Fleet rollout after Weather

Weather has proved SIMPLE-DEPLOY end to end. Fleet reuse is eligible to proceed when explicitly selected, but it does not supersede remaining Weather current-observation/UI acceptance work. When fleet rollout is selected:

1. migrate at least one additional compatible Docker/Compose consumer;
2. then migrate other compatible services one at a time;
3. preserve per-service application/data invariants;
4. use the same shared `ops-workflows` implementation and the same generic RPi5 deployer;
5. avoid per-project deployment frameworks;
6. declare SIMPLE-DEPLOY stable/default only after at least Weather plus one non-Weather consumer prove reuse.

New compatible projects should bootstrap from the shared caller + manifest model rather than inventing deployment infrastructure.

## 9. AUTO-RUN FULL Queue vNext — deliberately later

`ops-workflows#96` is the planned post-fleet queue evolution.

Do not implement or activate it in parallel with SIMPLE-DEPLOY rollout.

Only after SIMPLE-DEPLOY is stable/default across intended compatible consumers may Queue vNext provide one explicit ordered activation such as:

```text
AUTO-RUN FULL QUEUE repo #1 #2 #3 #4

#1 -> source -> CI -> merge -> SIMPLE-DEPLOY -> receipt -> #2
#2 -> source -> CI -> merge -> SIMPLE-DEPLOY -> receipt -> #3
...
```

Normal successful items should then advance without another owner approval between them. Real scope/risk/CI/runtime failures still STOP and require owner input. Sensitive DB/secret/network/host-control operations remain separate.

Current Queue v1/A1 or historical Simple LIVE text must not be interpreted as already granting this future vNext authority.

## 10. Other active architecture programs

### Owner-authorized pull deploy executor — #236

#236 remains a valid trust-boundary/architecture roadmap and historical source for deterministic owner-authorized operations. It does not override the current Weather public acceptance lane.

Use its owner identity, replay, exact source/target, fail-closed and static-operation principles where they remain applicable, but do not revive project-specific old Weather broker/JIT execution as steady state.

### AUTO-RUN FULL controller — #295

#295 is durable controller state for explicit issue-scoped AUTO-RUN FULL. Bare START/continuation never infers FULL from controller state.

### Hermes residual migration

Hermes migration history and residual work remain valid backlog/program state. It may proceed only when it is the explicitly selected current lane. It does not automatically outrank the accepted Weather public acceptance lane merely because historical Phase 4 was once marked incomplete.

The old Phase 4 detailed chronology remains available in Git history and #191. Historical evidence is intentionally not duplicated as current mutable state in this concise plan.

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
1. Phase A install-only — COMPLETE; authority consumed
2. Phase-B correction/repair + schema-init against preserved weather_data — COMPLETE; /ready=200; authorities consumed
3. Phase-C activation + first bounded reconciliation — COMPLETE; standing ordinary target activated; authority consumed
4. first genuine newly merged Weather AUTO_DEPLOY_SAFE release — COMPLETE
5. Weather public-data companion source #682/#683 — COMPLETE
6. Weather data companion source reconciliation #684/#685 — COMPLETE
7. separately authorized installed-capability reconciliation + one-time public corpus bootstrap/integrity — COMPLETE
8. recurring public-ingest timer enable/start — COMPLETE; recurring operation READ-ONLY VERIFIED on 2026-09-22
9. DWD station_05480 measured-current freshness/provenance — CURRENT PUBLIC ACCEPTANCE WORK
10. truthful consumer UI/provider/corpus acceptance — CURRENT PUBLIC ACCEPTANCE WORK
11. migrate/test additional compatible consumers when explicitly selected
```

If fresh GitHub or host evidence invalidates an accepted receipt, reclassify before action. Never rerun a consumed one-shot gate, improvise a Docker/config path, or treat a source merge as authority for a separately sensitive mutation class.

## 13. Current authorization state

Current durable authority state has no inferred merge authority, no active AUTO-RUN FULL authority and no fresh one-shot LIVE authority. Bare FAST continuation may perform source/docs/tests work only within the current command through Ready; merge remains explicit owner authority.

The completed cutover, data bootstrap and recurring-ingest activation authorizations were consumed by their completed attempts and are non-reusable. Their historical success does not grant authority to rerun them.

The successful Weather cutover activated only the reviewed standing ordinary `AUTO_DEPLOY_SAFE` reconciliation contract for the already-adopted static Weather target. That standing contract does **not** authorize:

- merge of any PR without the exact authority required by the active repository lane;
- database/schema/data migration, destructive recovery, corpus rewrite/backfill replay or scheduler reconfiguration;
- target/registry/Compose/service identity widening outside reviewed source;
- unrelated Docker/systemd/host-control, package or filesystem-permission mutation;
- secrets/credentials/private-provider changes;
- Cloudflare/DNS/network mutation;
- retry, cleanup, rollback or alternate recovery after a fail-closed ordinary deployment error unless a separately reviewed recovery contract authorizes it.

Fresh read-only runtime evidence may verify state, but it never creates mutation authority. Any new data repair, timer/systemd change, private-provider activation or other sensitive mutation requires the exact current owner gate.

## 14. Continuity references

For fresh state, read in this order when relevant:

1. current `AGENTS.md` and routing policy;
2. current `docs/AUTOMATION_MASTER_PLAN.md`;
3. #295 controller;
4. #103 umbrella tracker;
5. latest relevant #191 handoff/comment, including Weather public-data acceptance receipt `5779640396`;
6. exact selected work item from fresh bootstrap; #669 is historical cutover metadata, #682/#684 are completed source/data-lane history, and #688 is the current continuity reconciliation issue until merged;
7. exact current `main` and required CI/review/ruleset state;
8. minimum-sufficient live evidence only when the exact current gate requires it.

GitHub source state never proves live deployment/runtime state.

## 15. Historical compatibility appendix — Hermes Phase 4 validators

This appendix preserves exact historical section identifiers and source-state markers that repository regression tests use to prove ordering and non-expansion of the old Hermes Phase 4 trust boundary. It is **historical compatibility evidence only**. None of these sections selects the current lane, proves current host state, grants LIVE authority, or overrides the current Weather public acceptance lane.

## Current supersession — Hermes source auth + bounded helper launch gate (2026-09-04)

Historical source checkpoint: the Source App composition and bounded fixed helper-launch design existed, while concrete production revalidation/host evidence and live wiring remained separate later gates.

## Current supersession — Hermes canonical source-integration gate (2026-09-04)

Historical source checkpoint: the concrete canonical Hermes revalidator, sanitized host-evidence resolver and inert broker composition were source-integrated without converting repository source into runtime proof.

## Current supersession — Hermes broker-entrypoint wiring source gate (2026-09-06)

Historical source checkpoint: the broker entrypoint was source-wired to the fixed runtime composition, with caller authority still limited to `authorization_issue_number` and durable replay consume required before helper launch.

## Current supersession — Hermes broker runtime upgrade/provenance source gate (2026-09-06)

Historical validator markers from the final superseding source gate in that sequence:

`PHASE4_CURRENT_WORK_ITEM=EXACT_BROKER_RUNTIME_UPGRADE_PROVENANCE_AND_MINIMAL_REPLAY_WRITE_PERMISSION`
`BROKER_ENTRYPOINT_WIRED=true`
`CURRENT_SERVICE_REPLAY_WRITE_AUTHORITY_PROVEN=false`
`RUNTIME_UPGRADE_PREFLIGHT_PROVEN=false`
`RUNTIME_UPGRADE_APPLIED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

These markers deliberately retain their historical values. They must not be interpreted as current mutable state, a current Phase 4 priority, or authorization to revive the old Hermes control path.

## Current supersession — Hermes PARTIAL_READY runtime-adapter trust-boundary source gate (2026-09-06)

Historical validator markers for the runtime-adapter source checkpoint:

`PHASE4_CURRENT_WORK_ITEM=HERMES_ORIGIN_RUNTIME_ADAPTER_TRUST_BOUNDARY_SOURCE`
`BROKER_ENTRYPOINT_WIRED=false`
`PRIVILEGED_DISPATCH_ENABLED=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`PRODUCTION_MUTATION_STARTED=false`

These values are retained solely for source-contract regression compatibility. They are not current-state assertions and do not alter current Weather public-acceptance sequencing.

### SIMPLE-DEPLOY Weather canary sequencing correction (#674)

Historical sequencing correction: the original canary activation was split to preserve strict readiness and Weather data authority: `install-only -> separate exact schema-init gate -> /ready=200 -> SIMPLE-DEPLOY activation/first reconciliation -> later corpus + ingest`. That correction remains important historical safety evidence, but every named one-time stage through recurring-ingest activation has since completed under separately accepted gates. It must not be interpreted as a current instruction to rerun those mutations.