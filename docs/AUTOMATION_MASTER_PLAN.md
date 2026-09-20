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

These A4 markers do not select the current deployment lane, do not activate Auto-Live, and do not override #669.

SIMPLE-DEPLOY v1 is now the concrete shared application-release profile for compatible Docker/Compose services. Where old Auto-Live manifests or controllers conflict with the accepted SIMPLE-DEPLOY consumer/runtime contract, reconcile them as compatibility/history rather than creating another deployment engine.

## 5. Current cross-project priority — SIMPLE-DEPLOY v1 Weather canary

The current priority remains the accepted shared SIMPLE-DEPLOY rollout, not the historical Weather v10 broker/operator/JIT path and not an unconditional return to older Phase 3/4 checkpoints. Fresh GitHub state and the latest #191 continuity comment remain authoritative over this point-in-time plan text.

### Accepted source/runtime chain

- shared SIMPLE-DEPLOY: `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- initial Weather cutover consumer: `rozkalns_weather@606981d10eee59d13b802f6a682abf1daa2aa8a5`;
- historical #672 source-only deterministic installer/principal prerequisite merged via PR #673, including the reviewed principal provisioning path;
- #674 install/schema-init/activation sequencing merged via PR #675 at `RPi5_main@b57ed42d5eb01f15b62c1f53459ffe0539a57d9c`;
- Phase A install-only completed from that exact baseline and stopped without daemon-reload, service/timer activation, Docker reconciliation or database/data mutation;
- the Phase-B Docker-state/runtime-identity correction merged via PR #676 as `RPi5_main@7c6c7a8a80ca62d783c7f378b5865fae348a3fe9`, with exact-main CI green;
- the separately authorized post-install Phase-B repair completed without Docker, systemd activation, reconciliation or database/data mutation;
- Phase B schema-init completed against the preserved `rozkalns-weather-public_weather_data` volume: `/ready` changed `503 -> 200`, the production pointer remained unchanged, and the frozen image was `sha256:d495d10b2d5e002a3c19b6532746624955269e0d483996c42ad6dea87e7afc38`;
- Phase C activation completed: the first bounded reconciliation returned `SUCCESS` for that same immutable digest, `/health=200`, `/ready=200`, and the reviewed `rozkalns-simple-deployer.timer` was enabled/started;
- post-activation read-only verification observed the timer active/enabled, a successful timer trigger, service result `success`/exit `0`, and `/health=200` plus `/ready=200`;
- the first genuine post-cutover standing release is also proven: `rozkalns_weather@789a79820807829cc9b057d9ffafc56e0e41afe9` was published through pinned `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c` to immutable digest `sha256:72031b1918d6bec064a26c303450d8b9e1ed2c66021ca3cb9acc3af55ec52c20`; the standing reconciler recorded `SUCCESS`, later scheduled cycles returned `NO_OP_CURRENT`, and `/health=200` plus `/ready=200` remained true.

These receipts complete both the one-time Weather SIMPLE-DEPLOY cutover and the first genuine standing-release proof. They do not create reusable authority for database/data work, unrelated host control, credentials, network/Cloudflare changes or any other sensitive mutation class.

### Current exact Weather gate

`RPi5_main#669` is the historical/canonical one-time cutover gate whose Phase A/B/C Definition of Done is now satisfied by the accepted receipts above. Its issue body and #674 metadata remain stale until separately reconciled; they must not be interpreted as reopening or reauthorizing consumed one-shot gates.

The standing ordinary reconciliation contract is active only for the already-adopted fixed target `rozkalns-weather-public-rpi5` and only for eligible `AUTO_DEPLOY_SAFE` releases within the reviewed static target contract. The first genuine newly merged Weather release has now reached this fixed target end to end through shared SIMPLE-DEPLOY with exact source/image/shared-workflow identity and truthful health/readiness evidence. Deployment success alone does not prove public corpus/provider/UI usability.

Current sequence from this checkpoint:

```text
one-time Weather SIMPLE-DEPLOY Phase A/B/C cutover — COMPLETE
-> first genuine newly merged Weather AUTO_DEPLOY_SAFE release proof — COMPLETE
-> source continuity records both accepted milestones
-> fresh Weather acceptance bootstrap selects the next unmet acceptance gap
-> separately gate corpus/backfill/recurring-ingest work only if still required
-> usable Weather UI/provider/corpus acceptance
-> migrate/test additional compatible consumers when explicitly selected
```

No consumed Phase-A/B/C authorization is reusable. No alternate Docker config path, helper retry, cleanup, rollback or historical broker/JIT path is authorized by this continuity update.

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

The one-time cutover and first genuine standing-release proof have passed. The current acceptance sequence is:

1. **COMPLETE** — genuine merged Weather source `789a79820807829cc9b057d9ffafc56e0e41afe9` reached the fixed SIMPLE-DEPLOY target through the standing ordinary reconciliation path;
2. **COMPLETE** — exact shared workflow `e05ed760791a127c7c9628696806ef39c9fe329c` and immutable image digest `sha256:72031b1918d6bec064a26c303450d8b9e1ed2c66021ca3cb9acc3af55ec52c20` were recorded;
3. **COMPLETE** — `/health=200` was observed after reconciliation;
4. **COMPLETE** — `/ready=200` was observed after reconciliation; future regressions must still fail closed rather than be fabricated as PASS;
5. treat the first SQLite schema initialization as complete; fresh Weather bootstrap must determine whether any public corpus bootstrap/backfill remains required, and any such work stays a separate data gate;
6. separately enable recurring public ingest only through its own exact host/scheduler gate if still required;
7. require real public DWD/ICON-D2/ECMWF state and corpus integrity before declaring Weather usable;
8. close the Weather UI master only after real UI/provider/readiness evidence passes.

Deployment health/readiness proves the ordinary release path; it is necessary but not sufficient evidence for usable Weather provider/corpus/UI acceptance.

WeatherNext/private-home activation is not required for the first usable public Weather UI and remains separate.

## 8. Fleet rollout after Weather

Weather has now proved SIMPLE-DEPLOY end to end. Fleet reuse is eligible to proceed when explicitly selected, but it does not by itself supersede remaining Weather provider/corpus/UI acceptance work. When fleet rollout is selected:

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

#236 remains a valid trust-boundary/architecture roadmap and historical source for deterministic owner-authorized operations. It does not override the exact current Weather SIMPLE-DEPLOY lane.

Use its owner identity, replay, exact source/target, fail-closed and static-operation principles where they remain applicable, but do not revive project-specific old Weather broker/JIT execution as steady state.

### AUTO-RUN FULL controller — #295

#295 is durable controller state for explicit issue-scoped AUTO-RUN FULL. Bare START/continuation never infers FULL from controller state.

### Hermes residual migration

Hermes migration history and residual work remain valid backlog/program state. It may proceed only when it is the explicitly selected current lane. It does not automatically outrank the accepted SIMPLE-DEPLOY Weather canary cutover merely because historical Phase 4 was once marked incomplete.

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
1. Phase A install-only at b57ed42... — COMPLETE; authority consumed
2. #674 Phase-B correction + PR #676 merge at 7c6c7a8... — COMPLETE
3. separately gated post-install Phase-B repair — COMPLETE; authority consumed
4. Phase-B schema-init against preserved weather_data — PASS; /ready=200; authority consumed
5. Phase-C activation + first bounded reconciliation — PASS; timer active; authority consumed
6. source/continuity reconciliation for the completed cutover — COMPLETE via PR #679 at 3f10614...
7. first genuine newly merged Weather AUTO_DEPLOY_SAFE release — COMPLETE at 789a798... -> sha256:72031b...; /health=200; /ready=200
8. fresh Weather bootstrap determines the next unmet acceptance gap
9. separately exact-gate corpus/backfill/recurring-ingest work only if still required
10. complete Weather UI/provider/corpus acceptance
11. then migrate/test additional compatible consumers when explicitly selected
```

If fresh GitHub or host evidence invalidates an accepted receipt, reclassify before action. Never rerun a consumed one-shot gate, improvise a Docker/config path, or treat a source merge as authority for a separately sensitive mutation class.

## 13. Current authorization state

Current durable authority state has no inferred merge authority, no active AUTO-RUN FULL authority and no fresh one-shot LIVE authority. Bare FAST continuation may perform source/docs/tests work only within the current command through Ready; merge remains explicit owner authority.

The Phase-A install, post-install repair, Phase-B schema/data and Phase-C activation authorizations were consumed by their completed attempts and are non-reusable. The successful Phase-C cutover activated only the reviewed standing ordinary `AUTO_DEPLOY_SAFE` reconciliation contract for the already-adopted static Weather target.

That standing contract does **not** authorize:

- merge of any PR without the exact authority required by the active repository lane;
- database/schema/data migration, corpus bootstrap/backfill, recurring-ingest activation or destructive recovery;
- target/registry/Compose/service identity widening outside reviewed source;
- unrelated Docker/systemd/host-control, package or filesystem-permission mutation;
- secrets/credentials/private-provider changes;
- Cloudflare/DNS/network mutation;
- retry, cleanup, rollback or alternate recovery after a fail-closed ordinary deployment error unless a separately reviewed recovery contract authorizes it.

With the first genuine standing-release proof complete, the next Weather acceptance lane must be selected by a fresh bootstrap from current Weather source/master state. Do not assume a data/host mutation is required. Any sensitive prerequisite discovered by that work remains separately exact-gated.

## 14. Continuity references

For fresh state, read in this order when relevant:

1. current `AGENTS.md` and routing policy;
2. current `docs/AUTOMATION_MASTER_PLAN.md`;
3. #295 controller;
4. #103 umbrella tracker;
5. latest relevant #191 handoff/comment;
6. exact selected work item from fresh bootstrap; #669 is the historical/canonical one-time cutover gate and is not standing LIVE authority;
7. exact current `main` and required CI/review/ruleset state;
8. minimum-sufficient live evidence only when the exact current gate requires it.

GitHub source state never proves live deployment/runtime state.

## 15. Historical compatibility appendix — Hermes Phase 4 validators

This appendix preserves exact historical section identifiers and source-state markers that repository regression tests use to prove ordering and non-expansion of the old Hermes Phase 4 trust boundary. It is **historical compatibility evidence only**. None of these sections selects the current lane, proves current host state, grants LIVE authority, or overrides the current SIMPLE-DEPLOY Weather gate #669.

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

These values are retained solely for source-contract regression compatibility. They are not current-state assertions and do not alter SIMPLE-DEPLOY/#669 sequencing.
### SIMPLE-DEPLOY Weather canary sequencing correction (#674)

Current canary activation is split to preserve strict readiness and Weather data authority: `install-only -> separate exact schema-init gate -> /ready=200 -> SIMPLE-DEPLOY activation/first reconciliation -> later corpus + ingest`. The generic reconciler remains forbidden from schema/data mutation. #669 must be freshly reconciled after #674 source merge; its earlier cutover-before-schema sequence is not executable while Weather uses `DATABASE_INIT_MODE=require-existing`.
