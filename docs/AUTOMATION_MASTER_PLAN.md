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
- Weather consumer/canary: `rozkalns_weather@606981d10eee59d13b802f6a682abf1daa2aa8a5`;
- historical #672 source-only deterministic installer/principal prerequisite merged via PR #673;
- #674 sequencing outcome merged via PR #675 as `RPi5_main@b57ed42d5eb01f15b62c1f53459ffe0539a57d9c`;
- Phase A install-only completed from that exact baseline, including the reviewed principal provisioning, and stopped without daemon-reload, service/timer activation, Docker command, target reconciliation or database/data mutation;
- Phase B then stopped before Docker/data mutation with `IMAGE_CONTRACT_FAILED` caused by `POINTER_RESOLUTION_FAILED`.

The Phase-B failure exposed a source/trust-contract defect: the schema-init bridge fixed `DOCKER_CONFIG` under root-owned `/etc`, while Docker Buildx uses client configuration/state/logs and the intended execution principal is the non-root `rozkalns-simple-deployer` account. The generic reconciler already uses runtime-owned `/var/lib/rozkalns-simple-deployer`; the schema-init bridge must use the same state boundary and must freeze its effective execution identity.

### Current exact Weather gate

`RPi5_main#669` remains the canonical runtime/data gate. Issue existence and source merge grant no LIVE authority. #672/#674 issue metadata may remain open after merged source outcomes; that does not reopen consumed Phase-A authority.

The current #674 follow-up source correction must remain source/docs/tests only. It may define a narrowly bounded post-install repair path because the Phase-A host has old installed helper bytes and the first-install-only installer cannot be rerun safely. That repair path is a separate future owner-gated filesystem/identity mutation and must not run Docker, systemd activation, target reconciliation or database/data mutation.

Required sequence:

```text
Phase A install-only at b57ed42... — COMPLETE; authority consumed
-> #674 source correction: fixed runtime identity + runtime-owned anonymous Docker/Buildx state + exact preflight mode
-> source review/merge + exact-main CI
-> separately exact owner-gated post-install Phase-B repair only
   (schema-init module + generated source identity + runtime-owned state dirs; no Docker/data/systemd activation)
-> fresh minimum-sufficient Phase-B preflight under the fixed runtime principal
-> only on PRECHECK_READY: separately exact owner Phase-B schema/data authorization
-> fixed immutable-digest schema-init against preserved weather_data
-> prove /ready=200 and unchanged production pointer
-> separately exact owner Phase-C daemon-reload/timer activation + first bounded reconciliation
-> later corpus/backfill/recurring-ingest gates
```

No alternate Docker config path, helper retry, cleanup, rollback or alternate schema-init path may substitute for the reviewed sequence.

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

After the one-time cutover passes:

1. prove one genuine merged Weather release reaches the fixed SIMPLE-DEPLOY target end to end;
2. verify exact deployed source/image digest and shared workflow revision;
3. record `/health` truthfully;
4. record `/ready` truthfully — a pre-existing data-readiness blocker is not an application-deploy failure and must never be fabricated as PASS;
5. separately initialize the first production SQLite schema/public corpus if still required;
6. separately enable recurring public ingest only through its own exact host/scheduler gate;
7. require real public DWD/ICON-D2/ECMWF state and corpus integrity before declaring Weather usable;
8. close the Weather UI master only after real UI/provider/readiness evidence passes.

WeatherNext/private-home activation is not required for the first usable public Weather UI and remains separate.

## 8. Fleet rollout after Weather

Only after Weather proves SIMPLE-DEPLOY end to end:

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
2. #674 Phase-B execution-identity/Docker-state source correction
3. focused source PR + exact-head CI/review + explicit owner merge
4. exact-main CI after merge
5. separately exact owner-gated post-install Phase-B repair only
6. fresh non-mutating Phase-B --preflight under rozkalns-simple-deployer
7. only on PRECHECK_READY: separately exact owner Phase-B schema/data gate
8. prove /ready=200 and unchanged production pointer
9. separately exact owner Phase-C activation + first bounded reconciliation
10. later corpus/backfill/recurring-ingest gates
11. prove one genuine merged Weather release end to end
12. then migrate/test additional compatible consumers
```

If fresh GitHub or host evidence proves a step already complete or invalid, reclassify before action. Never rerun a consumed gate, improvise a Docker/config path, or treat source merge as LIVE authority.

## 13. Current authorization state

Current authority is source/docs/tests work only through Ready. There is no merge authority and no reusable LIVE authority. Phase-A authority is consumed.

This source correction does **not** authorize:

- merge of its PR;
- the post-install `--phase-b-repair --apply` filesystem/identity mutation;
- invoking the schema-init no-argument apply path or any database/schema/data mutation;
- `systemctl daemon-reload`, service/timer enable/start or first target reconciliation;
- alternate Docker configuration, root execution, retry, cleanup or rollback;
- secrets/credentials/permissions beyond the separately reviewed exact future repair;
- Cloudflare/DNS/network or private-provider mutation.

After source merge and exact-main green, the next genuine owner gate is the narrowly frozen post-install Phase-B repair. Only after its PASS and a fresh `--preflight` PASS may a separate Phase-B schema/data authorization be considered.

## 14. Continuity references

For fresh state, read in this order when relevant:

1. current `AGENTS.md` and routing policy;
2. current `docs/AUTOMATION_MASTER_PLAN.md`;
3. #295 controller;
4. #103 umbrella tracker;
5. latest relevant #191 handoff/comment;
6. exact selected work item, currently #669 for Weather cutover after this reconciliation;
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
