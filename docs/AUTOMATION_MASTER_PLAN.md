# Automation Master Plan

Status: ACTIVE  
Owner: Andris Rožkalns  
Control repository: `rozkalnsandris/RPi5_main`  
Canonical file: `docs/AUTOMATION_MASTER_PLAN.md`  
Shared workflow repository: `rozkalnsandris/ops-workflows`  
Umbrella tracker: `RPi5_main#103`  
AUTO-RUN FULL controller: `RPi5_main#295`  
Owner-authorized pull-deploy roadmap: `RPi5_main#236`

## Current fleet reconciliation — 2026-09-26

This dated reconciliation is authoritative for **current lane selection** and supersedes older `NEXT` / `FOLLOWING` sequencing labels later in this document where they conflict with the facts below. Historical architecture and safety boundaries remain unchanged.

- Control Center Cloudflare-native deploy-standardization source work is **COMPLETE** at `rozkalnsandris/rozkalns-control-center@8a43dc4902ddad43a49d55e043964f1ae61b8c71`. No production Worker/Static Assets, D1, Queue, Cloudflare, credential or RPi5 mutation is implied.
- Hermes Tech public static/Hugo SIMPLE-DEPLOY consumer source and GitHub-side publication proof are **COMPLETE** at `rozkalnsandris/hermes-tech@3d8e2400e26e7bf4e992539e1239120f9bc1af44`; SIMPLE-DEPLOY run `36149826529` completed successfully against immutable shared workflow `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`.
- Hermes Tech RPi5 target/allowlist source registration is **COMPLETE** in `RPi5_main` via merged PR #737 at exact `main` `57098e4244752abc306f984b9ed155c9baac9c6c`; exact-main push `Validate` run `36230598079` completed successfully. The registry now contains `hermes-tech-public-rpi5` alongside Weather and the parked Hermes Deals target.
- Hermes Tech target registration is **source-only**. It does not prove host/runtime installation and does not authorize the one-time target activation/cutover, retirement/replacement of the existing V14 runtime, Docker/Compose execution, GHCR publication, protected configuration access or any other LIVE mutation.
- `rozkalns-cv` SIMPLE-DEPLOY consumer source and GitHub-side publication proof are **COMPLETE** at `rozkalnsandris/rozkalns-cv@139fb7046c77e1e58ec4a0876db3dddb96c85cb5`; SIMPLE-DEPLOY run `36150943895` completed successfully against the same immutable shared workflow, but CV is not yet registered as an RPi5 target.
- **NEXT SOURCE GATE:** review and prepare the `rozkalns-cv` RPi5 target/allowlist source contract one consumer at a time, preserving the accepted SIMPLE-DEPLOY safety boundary. Carry source/tests through Draft PR, exact-head CI/review and Ready only; merge remains separately owner-authorized.
- Any Hermes Tech or future CV one-time activation/cutover remains a separate exact LIVE gate after the relevant target/allowlist source change is merged and freshly revalidated. No target installation, Compose execution, systemd, Docker, host, secret, Cloudflare or database mutation is authorized by this reconciliation itself.
- `dashboard_RPi5` remains outside the ordinary whole-service SIMPLE-DEPLOY profile; Hermes Deals operational activation remains fleet-last; `ops-workflows#96` Queue vNext remains blocked until the intended compatible-consumer rollout and stability criteria are actually satisfied.

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

## 5. Current cross-project priority — deploy standardization + SIMPLE-DEPLOY fleet source adaptation

Weather public acceptance is now **COMPLETE**. `rozkalns_weather#176` closed after fresh post-#177 runtime/API evidence and real consumer UI acceptance proved canonical DWD `station_05480` current-now behavior, populated forecast surfaces and truthful presentation. The older Weather freshness/UI wording in historical issues and receipts must not be treated as a current blocker.

The owner-selected order now prioritizes `rozkalns-control-center` deploy-standardization source work before the remaining compatible SIMPLE-DEPLOY consumers, while preserving each repository's native production architecture and keeping Hermes Deals operational activation fleet-last:

- shared SIMPLE-DEPLOY remains pinned to accepted `ops-workflows@e05ed760791a127c7c9628696806ef39c9fe329c`;
- Weather remains the activated standing canary target;
- `rozkalnsandris/rozkalns-control-center` is the **next deploy-standardization candidate**, but it remains a Cloudflare Worker/Static Assets/D1/Queues application and is **not** an RPi5 Docker/Compose SIMPLE-DEPLOY target;
- Control Center source work must preserve the Cloudflare architecture and standardize only a deterministic source/deploy contract: exact source SHA, build/test evidence, bounded Worker/Static Assets publication semantics, fail-closed verification and explicit deploy-impact classification;
- D1 schema/data migration or remote apply, Queue mutation, Cloudflare Access/DNS/Tunnel/network changes, credentials/secrets, GitHub App permission expansion and any production Worker deployment remain separately exact-gated and are not implied by deploy-standardization source work;
- `rozkalnsandris/hermes-tech` follows Control Center as the next ordinary SIMPLE-DEPLOY source-adaptation candidate;
- Hermes Tech remains a candidate only for its public static/Hugo origin under the ordinary image/Compose profile; digest generation, SQLite state, scheduled publication, generated-content Git synchronization, publisher credentials and schema/data operations remain outside ordinary SIMPLE-DEPLOY;
- the Hermes Tech source adaptation must first establish a tiny immutable-SHA-pinned caller, consumer manifest, Dockerfile/Compose origin contract and fixed health/readiness semantics in the consumer repository before any RPi5 target registration or runtime activation is considered;
- `dashboard_RPi5` is not an ordinary SIMPLE-DEPLOY v1 whole-service candidate because its production design includes root-owned immutable release-controller, systemd, Unix-socket and Docker-broker trust boundaries;
- Hermes Deals already has substantial source preparation, but its **operational activation/cutover is deliberately fleet-last** and must not preempt the remaining source work;
- no target registry, allowlist, host/runtime, Cloudflare, D1, Queue, protected configuration or secrets/permissions change is implied by this sequencing decision.

The existing Hermes Deals source chain remains accepted historical/source preparation rather than discarded work:

- Hermes consumer caller/contract was accepted at `rozkalnsandris/hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c`;
- Hermes compatibility prerequisite #690 / PR #691 is COMPLETE;
- Hermes static source target binding #692 / PR #693 is COMPLETE;
- Hermes existing-install adoption source #698 / PR #699 is COMPLETE;
- Hermes post-Phase-B identity correction #708 / PR #709 is COMPLETE;
- Hermes host-prerequisite materialization v1 source #711 / PR #712 is COMPLETE, with its Phase-B parent/preflight semantics superseded by v2;
- Hermes Phase-B state-parent/preflight correction #713 / PR #714 is COMPLETE.

Any Hermes Deals metadata-only preflight or later Composite LIVE cutover must be freshly revalidated when the fleet reaches that final operational stage. Earlier source completion, tracker wording or target registration does not create standing authority to execute it now.

No source registration, tracker update, plan update or read-only preflight grants LIVE authority.

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

### Current deployment-standardization / SIMPLE-DEPLOY sequence

```text
shared SIMPLE-DEPLOY policy/workflow — COMPLETE
-> Weather static target + one-time activation — COMPLETE
-> Weather standing release proof — COMPLETE
-> Weather public data/runtime/UI acceptance — COMPLETE
-> Control Center Cloudflare deploy-standardization source contract — NEXT SOURCE GATE
-> Control Center exact-head CI/review/Ready; merge remains separately owner-authorized
-> any later Control Center production Worker/Static Assets publication, D1/Queue change, credential or Cloudflare mutation — SEPARATE EXACT LIVE GATE
-> Hermes Tech source compatibility/adaptation — FOLLOWING SIMPLE-DEPLOY SOURCE GATE
-> Hermes Tech exact-head CI/review/Ready; merge remains separately owner-authorized
-> after Hermes Tech source acceptance: separate RPi5 target/allowlist source review and separate one-time LIVE activation only if the final contract still fits SIMPLE-DEPLOY v1
-> migrate/test other compatible consumers one at a time
-> Hermes Deals operational activation/cutover — FLEET-LAST
-> prove final intended compatible-consumer set and declare SIMPLE-DEPLOY stable/default only after reuse criteria are actually satisfied
-> ONLY THEN revisit ops-workflows#96 Queue vNext
```

WeatherNext/private BigQuery remains a separate optional research lane and is not required for public-runtime health or fleet source adaptation.

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

The selected program now has two deployment-standardization tracks: platform-native standardization for non-RPi5 applications, followed by ordinary SIMPLE-DEPLOY reuse for compatible Docker/Compose consumers. Do not force unlike architectures into the RPi5 SIMPLE-DEPLOY profile merely to make the fleet uniform.

### Control Center — next deploy-standardization candidate

`rozkalnsandris/rozkalns-control-center` is the next repository to standardize at source level.

Its production architecture remains Cloudflare-native:

- frontend/runtime: React + TypeScript + Vite with Workers Static Assets;
- backend/API: Cloudflare Worker;
- structured state: D1;
- event ingestion: Queues + DLQ;
- human authentication and other Cloudflare infrastructure remain separate trust-boundary concerns.

The intended source-only deploy-standardization boundary is:

- bind releases to an exact reviewed Git SHA;
- require repository CI/build/test evidence before any deploy-eligible state;
- define deterministic Worker/Static Assets build and publication inputs/outputs without moving the runtime to RPi5 or Docker;
- fail closed when deploy identity, expected environment or required evidence is stale/unknown;
- classify source-only/no-deploy, ordinary publication and strict-live changes distinctly;
- keep credentials, protected configuration and Cloudflare account authority out of source and public evidence.

Explicitly outside this source-standardization gate:

- production Worker or Static Assets deployment/promotion;
- D1 schema/data migration or remote apply;
- Queue/DLQ mutation;
- Cloudflare Access, DNS, Tunnel, network or account-setting mutation;
- credential/secret creation, rotation, export or binding mutation;
- GitHub App permission/repository-selection expansion;
- any RPi5 target, allowlist, Docker, systemd or host mutation.

A future Control Center source PR may establish this deterministic Cloudflare deployment contract through that repository's own architecture and CI. Any production publication or other Cloudflare/D1/Queue mutation remains a separate exact owner gate under the Control Center repository's rules.

### Hermes Tech — following SIMPLE-DEPLOY source candidate

Hermes Tech follows Control Center and remains the next repository to evaluate for ordinary SIMPLE-DEPLOY source adaptation.

The intended v1 boundary is narrow:

- candidate runtime: the public static/Hugo web origin only;
- shared workflow pin: immutable accepted `ops-workflows` full SHA;
- public build/publish runner: GitHub-hosted;
- candidate image must contain only public site/runtime bytes and no private runtime configuration;
- future Compose identity and health/readiness must be fixed and declarative;
- the existing shared Cloudflare connector remains RPi5 infrastructure and is not owned or restarted by the consumer deployment.

Explicitly outside the ordinary Hermes Tech SIMPLE-DEPLOY profile:

- RSS collection and AI digest generation;
- SQLite schema/data lifecycle or migration;
- scheduled publication/cron/timer behavior;
- generated-content Git synchronization/push authority;
- publisher/deploy credentials or secret movement;
- backup/restore and destructive recovery;
- Cloudflare/network or unrelated host-control changes.

The source-adaptation PR in `rozkalnsandris/hermes-tech` must prove that the static origin can be packaged independently of those excluded publication/data operations. If that separation cannot be proven without widening the ordinary deploy profile, classify Hermes Tech non-compatible rather than weakening SIMPLE-DEPLOY.

No `RPi5_main` target/allowlist mutation is part of this fleet-order reconciliation. A future target registration is a separate source change after the consumer contract is reviewed; live activation remains a later separate owner gate.

### Hermes Deals — operationally last

Hermes Deals already has reviewed source preparation and an existing static target definition, but the owner-selected fleet order makes its first production SIMPLE-DEPLOY activation the final operational cutover among the intended current candidates.

Accepted source facts remain valid as historical/source preparation:

- consumer contract: `hermes-deals@13f9fb69b9576d8e97ab3a85334927f3c576ca1c`;
- source compatibility prerequisite #690 / PR #691: COMPLETE;
- static target binding #692 / PR #693: COMPLETE;
- existing-install adoption source #698 / PR #699: COMPLETE;
- post-Phase-B identity correction #708 / PR #709: COMPLETE;
- host-prerequisite materialization v1 source #711 / PR #712: COMPLETE, with Phase-B parent/preflight semantics superseded by v2;
- Phase-B state-parent/preflight correction #713 / PR #714: COMPLETE;
- RPi5-owned API-only adapter: `ops/deploy/simple-deploy-compose/hermes-deals-api.yml`;
- target alias: `hermes-deals`;
- liveness: `http://127.0.0.1:9128/api/health`;
- readiness: `not-applicable`;
- persistent database-volume identity: `hermes_deals_pgdata`;
- private runtime config and host namespace remain separately LIVE-gated.

None of those source outcomes installs the target, creates host prerequisite paths, provisions private configuration or runs Docker. Their existence also does not require the current fleet to execute the previously next metadata-only preflight immediately.

When Hermes Deals reaches the fleet-last stage, freshly re-run the minimum required source/host evidence from current state before any owner gate. Do not reuse stale preflight conclusions, old LIVE authorization, old target baseline or historical runtime assumptions.

### Reuse/stability rule

1. standardize Control Center's Cloudflare-native source/deploy contract first without introducing RPi5 Docker SIMPLE-DEPLOY semantics or performing live Cloudflare/D1/Queue mutation;
2. adapt and test Hermes Tech at source level next, failing closed if its static origin cannot be separated from publication/data authority;
3. migrate/test any other compatible consumers one at a time before the final Deals cutover;
4. preserve each service's data, publication and application invariants;
5. keep the generic SIMPLE-DEPLOY executor shared and target configuration static for compatible RPi5 consumers;
6. do not revive old project-specific control planes for ordinary releases;
7. execute Hermes Deals operational activation only at the fleet-last stage after fresh source/runtime revalidation and a separate exact owner LIVE gate;
8. declare SIMPLE-DEPLOY stable/default only when the intended compatible set, including fleet-last Deals, has the required source and runtime evidence.

New compatible RPi5 projects should bootstrap from the shared caller + manifest model rather than inventing deployment infrastructure. Non-RPi5 platforms should keep their native runtime architecture and adopt equivalent exact-SHA, fail-closed and least-authority deployment invariants rather than copying the Docker/Compose implementation.

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
9. Control Center Cloudflare deploy-standardization source contract — NEXT SOURCE GATE
10. Control Center exact-head CI/review/Ready — source-only; merge remains separately owner-authorized
11. any Control Center production Worker/Static Assets publication, D1/Queue change, credentials or Cloudflare mutation — SEPARATE LATER LIVE GATE
12. Hermes Tech source compatibility/adaptation — FOLLOWING SIMPLE-DEPLOY SOURCE GATE
13. Hermes Tech exact-head CI/review/Ready — source-only; merge remains separately owner-authorized
14. after Hermes Tech source acceptance: separate RPi5 target/allowlist source review if still compatible — LATER SOURCE GATE
15. separate one-time Hermes Tech activation/cutover — LATER LIVE GATE
16. additional compatible-consumer source/runtime reuse proof as required
17. Hermes Deals source chain #690/#691, #692/#693, #698/#699, #708/#709, #711/#712, #713/#714 — COMPLETE SOURCE PREPARATION / PARKED OPERATIONALLY
18. Hermes Deals fresh final-stage metadata/source/runtime preflight — FLEET-LAST PRE-CUTOVER GATE
19. Hermes Deals exact Composite LIVE prerequisite materialization + exact two-key projection + target adoption + bounded first reconciliation/E2E — FLEET-LAST LIVE GATE
20. final intended compatible-consumer stability/default declaration
21. only after stable/default criteria: ops-workflows#96 Queue vNext
```

If fresh GitHub or host evidence invalidates an accepted receipt, reclassify before action. Never rerun a consumed one-shot gate, improvise a Docker/config path, or treat a source merge as authority for a separately sensitive mutation class.

## 13. Current authorization state

No plan, tracker or source merge grants inferred LIVE authority.

The selected next fleet step is source-only work in `rozkalnsandris/rozkalns-control-center`: standardize its Cloudflare-native deployment contract through that repository's normal source/docs/tests -> Draft PR -> exact-head CI/review -> Ready flow while preserving Worker/Static Assets/D1/Queues architecture. This plan does not authorize a Control Center merge, production Worker or Static Assets publication, D1 schema/data apply, Queue mutation, Cloudflare Access/DNS/Tunnel/network change, credential/secret mutation, GitHub App permission expansion, RPi5 target/allowlist change or host/runtime mutation.

After that source lane, Hermes Tech remains the following ordinary SIMPLE-DEPLOY candidate for its narrow static/Hugo origin. Its source adaptation and any later RPi5 target registration or activation remain separately gated.

The Hermes Deals source chain through #713/#714 remains completed preparation, but its operational progression is parked until the fleet-last stage. Do not treat the older tracker/master-plan wording that named a Hermes metadata-only preflight as the immediate current fleet gate. When Deals becomes current again, refresh the minimum required metadata/source/runtime evidence before asking for any Composite LIVE decision.

Any future prerequisite filesystem/application-data materialization, protected-config projection, target adoption, Docker reconciliation/E2E or other sensitive mutation requires a distinct exact current owner gate. A successful read-only preflight never authorizes those mutations.

The completed Weather cutover/data/UI authorizations were consumed by their completed attempts and are non-reusable. The successful Weather cutover activated only the reviewed standing ordinary `AUTO_DEPLOY_SAFE` reconciliation contract for the already-adopted static Weather target.

Any new target cutover, data repair, timer/systemd change, private-provider activation or other sensitive mutation requires the exact current owner gate.

## 14. Continuity references

For fresh state, read in this order when relevant:

1. current `AGENTS.md` and routing policy;
2. current `docs/AUTOMATION_MASTER_PLAN.md`;
3. #295 aggregate controller;
4. #103 umbrella tracker, treating any fleet-order wording that conflicts with the newer canonical plan as stale until separately reconciled;
5. latest relevant #191 handoff/comment;
6. accepted Weather public acceptance evidence in `rozkalns_weather#176`;
7. current `rozkalnsandris/rozkalns-control-center` rules, master issue #1, relevant handoff/current issue, source and CI when executing the next deploy-standardization lane;
8. current `rozkalnsandris/hermes-tech` rules/README/source when the following SIMPLE-DEPLOY source-adaptation lane becomes current;
9. Hermes Deals compatibility #690/#691, static target binding #692/#693, existing-install adoption #698/#699, post-Phase-B identity correction #708/#709, materialization v1 #711/#712, and Phase-B parent/preflight correction #713/#714 only when the fleet reaches the final Deals stage;
10. exact current `main` and required CI/review/ruleset state;
11. minimum-sufficient live evidence only when the exact current gate requires it.

Closed #688 is historical continuity work, not a current gate. GitHub source state never proves live deployment/runtime state.

## 15. Historical compatibility appendix — Hermes Phase 4 validators

This appendix preserves exact historical section identifiers and source-state markers that repository regression tests use to prove ordering and non-expansion of the old Hermes Phase 4 trust boundary. It is **historical compatibility evidence only**. None of these sections selects the current lane, proves current host state, grants LIVE authority, or overrides the current SIMPLE-DEPLOY fleet-adoption lane.

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

These values are retained solely for source-contract regression compatibility. They are not current-state assertions and do not alter current SIMPLE-DEPLOY fleet sequencing.

### SIMPLE-DEPLOY Weather canary sequencing correction (#674)

Historical sequencing correction: the original canary activation was split to preserve strict readiness and Weather data authority: `install-only -> separate exact schema-init gate -> /ready=200 -> SIMPLE-DEPLOY activation/first reconciliation -> later corpus + ingest`. Every named one-time stage through final public acceptance has since completed under separately accepted gates. It must not be interpreted as a current instruction to rerun those mutations.
