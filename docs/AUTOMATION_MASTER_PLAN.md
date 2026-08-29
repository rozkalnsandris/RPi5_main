# Automation Master Plan

Status: ACTIVE
Owner: Andris Rožkalns
Control repository: `rozkalnsandris/RPi5_main`
Canonical file: `docs/AUTOMATION_MASTER_PLAN.md`
Shared workflow repository: `rozkalnsandris/ops-workflows`
Umbrella tracker: `RPi5_main` issue #103

## Mandatory operating rule

Before starting any automation, deployment, audit, CI, runner, GitHub App, or production-control change covered by this program:

1. Read this file from current `RPi5_main/main`.
2. Identify the first incomplete phase or explicitly named next step.
3. Work only on that step and its required prerequisites.
4. Do not expand scope into unrelated cleanup, UI polish, refactors, or opportunistic improvements.
5. Preserve exact-SHA, rollback, health-check, fail-closed, least-privilege, canary, and evidence controls unless this plan explicitly replaces them.
6. Update this file whenever a phase materially changes, completes, blocks, or is superseded.
7. Re-read this file before beginning the next phase.
8. Before every host-activation gate, audit every cross-repository producer/consumer interface used by that host path; repository-local green CI alone is not sufficient evidence that the cross-repository contract is compatible.

If a proposed automation task conflicts with this file, reconcile this plan first.

## Explicit exclusion

`rozkalnsandris/hermes-email-skill` is OUT OF SCOPE. Do not inspect, modify, migrate, automate, install the automation App on, or change its visibility as part of this program.

## Architecture boundary

### `rozkalnsandris/RPi5_main` — control plane and host truth

Keep here:

- this master plan and umbrella tracker;
- `docs/AUTOMATION_GITHUB_APP.md`;
- RPi5-local GitHub App verification tooling;
- RPi5 deploy/readiness controllers and host integration;
- systemd service/timer definitions and host-side safety contracts;
- exact-SHA production approval/apply logic;
- rollback, backup, locking and health-check logic.

Do not use `RPi5_main` as the shared reusable GitHub workflow library.

### `rozkalnsandris/ops-workflows` — shared GitHub automation library

Keep here:

- reusable `workflow_call` workflows;
- reusable public-repository CI/security policy;
- action full-SHA pinning checks;
- public-runner safety checks;
- common deterministic GitHub-side audit policy;
- documentation for consuming shared workflows.

Rules:

- GitHub-hosted runners only;
- no production credentials;
- no self-hosted RPi5 runners;
- no RPi5 host mutation;
- callers reference reusable workflows only by exact 40-character `ops-workflows` commit SHA.

Current baseline SHA:

`e2fa7ecb1b1cdfab0711d8e3e147b5ae03a9a3f2`

## Goal

Standardize public repositories on this model:

`PR -> GitHub-hosted CI/security -> squash merge -> exact-SHA main CI -> trusted RPi5 local controller -> deploy-impact classification -> auto deploy or explicit approval -> root-owned helper -> health verification/evidence`

Persistent RPi5 self-hosted GitHub Actions runners are not the target for public-repository production or audit execution.

Long-lived PATs are not the target authentication model. Trusted RPi5 controllers should use a least-privilege GitHub App and short-lived installation tokens.

## Canonical deploy-impact classes

### `NO_DEPLOY`

Documentation, tests, issue templates, and other changes with no runtime effect.

### `AUTO_DEPLOY_SAFE`

Ordinary reviewed application/site/UI/API code that passed exact-SHA CI and does not cross a sensitive boundary.

### `MANUAL_ROLLOUT_REQUIRED`

Runtime dependencies, Docker/runtime image behavior, schedulers, parsers/collectors, deployment/control-plane changes, or equivalent higher-risk changes.

### `DB_HOST_APPLY_REQUIRED`

Database migrations/writes, host infrastructure, systemd/backup/Cloudflare ownership changes, or equivalent high-impact operations.

Unknown runtime-relevant paths fail toward review, never silently toward `NO_DEPLOY`.

## Repository target state

### `ops-workflows`

Shared public automation library. GitHub-hosted only, least privilege, full-SHA pinned Actions, no production mutation.

### `hermes-tech`

Reference production execution architecture. Keep GitHub-hosted CI and local RPi5 pull/poll deploy classification, exact-SHA CI, locking, canary activation, rollback, health checks, and separate sensitive approvals. Phase 6 remains a later, separately gated migration for replacing persistent user authentication with GitHub App installation authentication while independently isolating generated-content write authority behind a narrow publisher capability.

### `rozkalns-cv`

The public-repository self-hosted deployment runner has been retired. Preserve the proven local RPi5 pull/poll controller, exact-SHA CI/deploy-impact classification, transactional deploy helper, helper identity verification, rollback, public MIME/CSP/cache checks, and separate manual/DB/host authorization classes. Historical Phase 3 SHAs are completion evidence only and must never be inferred to be current source or production state.

### `hermes-deals`

Replace production and audit self-hosted runner transport with trusted local RPi5 controllers while preserving root-owned dispatchers, immutable evidence, rollback, DB protections, and separate authorization for parser/scheduler/control-plane/runtime/DB/review/publication-sensitive operations. The repository has evolved substantially since this target was first written; current migration work must begin from the live Hermes Deals governance and runner inventory, not from the historical generic checklist below.

### `RPi5_main`

Remain infrastructure/control-plane truth. Keep infrastructure production apply manual. Automation may prepare deterministic readiness/plan states but must not auto-apply host files/services merely because CI passed.

### `rozkalnsandris`

Profile repository. No production deploy automation. Consume minimal shared policy from `ops-workflows` by exact SHA.

## GitHub App target

App name: `Rozkalns Automation`.

Purpose:

- RPi5 read-only access to repository/main/Actions state for exact-SHA verification;
- no GitHub-side production mutation required for initial operation.

Initial repository permissions:

- Actions: Read-only
- Contents: Read-only

All other repository/account/organization permissions remain No access unless a later phase proves a specific endpoint requires more.

Initial installation scope:

- `rozkalnsandris/RPi5_main`
- `rozkalnsandris/hermes-tech`
- `rozkalnsandris/rozkalns-cv`
- `rozkalnsandris/hermes-deals`

Do not install initially on:

- `rozkalnsandris/ops-workflows` — reusable Actions do not require RPi5 controller access;
- `rozkalnsandris/rozkalnsandris` — no RPi5 production controller need;
- `rozkalnsandris/hermes-email-skill` — explicitly out of scope.

Webhook remains disabled for the initial authentication-only design.

Use short-lived installation access tokens; keep the App private key only on RPi5 outside repositories/chat/evidence.

Current non-secret identity:

- App ID: `4537106`
- Installation ID: `152422751`

Detailed contract: `docs/AUTOMATION_GITHUB_APP.md`.

## Migration phases

### Phase 0 — Control plane and plan persistence — COMPLETE

- [x] `RPi5_main` chosen as canonical control repository.
- [x] Master plan and anti-drift rule persisted.
- [x] Umbrella tracker issue #103 created.

### Phase 1 — Reusable baseline proof — COMPLETE

- [x] Reusable public policy baseline proven.
- [x] Full-SHA action pinning/public-runner checks proven.
- [x] Low-risk profile caller canary proven.

Historical bootstrap evidence: `RPi5_main` baseline commit `aa9d920d7f5fbc10a8e2b52bb346659f92c13172`.

### Phase 1B — Split shared workflows into `ops-workflows` — COMPLETE

- [x] Public `rozkalnsandris/ops-workflows` created with default branch `main`.
- [x] Reusable baseline and self-canary moved there.
- [x] `ops-workflows` GitHub-hosted self-canary PASS.
- [x] Profile repo switched to exact `ops-workflows` SHA and PASS.
- [x] `RPi5_main` switched to exact `ops-workflows` SHA and full Validate/Gitleaks/policy PASS.
- [x] Duplicate reusable baseline removed from `RPi5_main` after both canaries.
- [x] Master plan, tracker, GitHub App contract/verifier and host-control logic retained in `RPi5_main`.

Canonical reusable baseline SHA: `e2fa7ecb1b1cdfab0711d8e3e147b5ae03a9a3f2`.

### Phase 2 — GitHub App preparation — COMPLETE

- [x] Exact required repository permission/API contract defined.
- [x] RPi5 read-only App verifier implemented and CI-proven (`936722453592788e6e824e0baf4dd0e158978cdc`).
- [x] `Rozkalns Automation` created with only Actions read + Contents read.
- [x] Installed on exactly the four initial controller repositories.
- [x] Private PEM stored root-only on RPi5 at `/root/.config/rozkalns-automation/github-app.pem` with mode `0600`.
- [x] Short-lived installation-token flow verified from RPi5.
- [x] Exact-SHA/Actions reads verified for all four repositories without PAT/user-token fallback.

Phase 2 canary evidence (2026-08-09):

- verifier blob: `30a2031a954c29b4f10c35d1d8279381df5b1814`;
- `GITHUB_APP_READONLY_CANARY=PASS`;
- token lifetime observed: `3599` seconds;
- effective permissions: `actions:read,contents:read`;
- repository scope matched exactly the four approved repositories;
- `RPi5_main`: main `b642c88319901a12347e9daf4b152bcc31889c96`, CI run `31316536528`;
- `hermes-tech`: main `84e818e017543bbd9cab881269785bfbd8185bbd`, CI run `31316585322`;
- `rozkalns-cv`: main `c0fec6ec45bbabb253e75127386bbc07b5338c0d`, CI run `31280034416`;
- `hermes-deals`: main `398903a94a73b1c57c615012f2c720a54304689a`, CI run `31316810092`;
- no PEM, JWT or installation token was emitted in evidence.

Exit gate: PASS. RPi5 performs required exact-SHA reads with the App and sanitized evidence; no persistent PAT is required for this read-only controller path.

### Phase 3 — CV pull-deploy migration — COMPLETE

The Phase 3 migration is complete. The detailed chronological evidence remains preserved in `RPi5_main` issue #103, CV issue #90, RPi5_main issue #140, and `docs/AUTOMATION_CHAT_CONTINUITY_2026-08-20.md`. This master plan retains only the exit evidence required to prevent stale sequencing from being executed again.

Completed exit chain:

- [x] GitHub App-authenticated exact-SHA CI/preflight and deterministic deploy-impact classification were proven.
- [x] CV pull transport was decoupled from the legacy self-hosted runner while preserving the transactional root-owned deploy boundary.
- [x] Rollback/pre-mutation ordering, public-contract verification and fail-closed prerequisite propagation were regression-proven.
- [x] The cross-repository producer/consumer evidence-path mismatch was found before activation and fixed at the less-privileged producer while preserving the stricter CV root-wrapper allow-pattern.
- [x] A genuine `AUTO_DEPLOY_SAFE` one-shot controller canary passed for exact target `edea046966b8e69c14fb652b799297b9ae1df1bf` with transactional/public verification green.
- [x] The recurring `rozkalns-cv-pull-deploy.timer` was separately authorized and proven enabled/active.
- [x] A timer-driven controller execution/readiness cycle passed through the replacement path.
- [x] The legacy CV public-repository self-hosted release runner was separately authorized for retirement and fully deregistered.
- [x] Final Phase 3 runner evidence recorded `CV_REPOSITORY_SELF_HOSTED_RUNNER_COUNT=0`.
- [x] RPi5_main #140 and CV #90 are closed/completed.

Phase 3 invariants that remain binding after completion:

- never create a dummy/same-SHA commit merely to exercise automation;
- only exact `AUTO_DEPLOY_SAFE` may cross the automatic CV mutation boundary; `NO_DEPLOY`, manual, DB/host, wait and failure classes remain non-mutating;
- the root wrapper remains stricter than its less-privileged producer;
- cross-repository producer/consumer compatibility must be audited before every host activation gate;
- the old public self-hosted CV release runner must not be resurrected;
- historical Phase 3 source/production SHAs are evidence only. For any future CV action, fresh-read current `rozkalns-cv/main`, canonical CV #347 body + latest comments, current CI and reviewed read-only production evidence. Never infer production SHA from current `main`.

Phase 3 exit decision:

`PHASE3_ACTUAL_STATUS=COMPLETE`
`CV_REPOSITORY_SELF_HOSTED_RUNNER_COUNT=0`
`CV_LEGACY_RUNNER_RETIREMENT=PASS`

### Phase 4 — Hermes Deals public-repository execution migration — CURRENT: #236 / P9 GENUINE READ-ONLY CANARY WAITING GATE

Phase 4 remains incomplete. The owner's later 2026-08-29 continuation correction supersedes the temporary Phase 6 priority override from #269 for current program routing: resume the cross-cutting `RPi5_main#236` pull-executor lane. Accepted post-save isolated-auth trust evidence, the merged repository-ID source binding, the merged P9 runtime composition and the merged dormant-canary operation consumption gate now complete the source prerequisites for a genuine P9 read-only authorization canary. Current continuation is therefore waiting for a real READY deploy-queue item plus a separate explicit owner decision; this state does not authorize dummy READY/LIVE-AUTH creation, credential use, protected-host inspection or any host/runtime/production mutation.

Historical source evidence from the 2026-08-29 P9 isolated-auth and continuity chain; these pins are evidence only and must never be inferred to be current branch state:

- `hermes-deals/main=140a50a17b398862a220e9302da1e6fa0680f2a2` was the reviewed Hermes anchor for this P9 chain; the canary source merge `2fbde52cc5b6661343dca3fd967d8112cb2bffbe` remains historical ancestry;
- `RPi5_main#263` merged the isolated-auth source gate at `6efb1efa3e8e4792de487ec16c95f6e0dc21f622`;
- `RPi5_main#265` merged post-merge continuity at `252f1034eb1a79c2620f8ef3844a34f092c7e41f` with historical exact-main Validate #639, FAST-LANE #94 and GITHUB-ONLY #83 green;
- `RPi5_main#266` merged continuity refresh at `454d82216ad8ba9f50aeff38f212c0967fbe273c` with historical exact-main Validate #641, FAST-LANE #96 and GITHUB-ONLY #85 green;
- `ops-workflows/main=c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8` was the reviewed queue/policy anchor for this P9 chain;
- `RPi5_main#271` merged the accepted isolated-auth repository source binding at `86b9c44ecb8c999fc559b30af0b024a47295e6d7`; exact-main Validate #654, FAST-LANE #109 and GITHUB-ONLY #98 were green at that checkpoint;
- `RPi5_main#273` merged the source-only queue/LIVE-AUTH runtime composition at `c0e43799c51c32e653515ba7695c364d61fb0a35`; exact-main Validate #658, FAST-LANE #113 and GITHUB-ONLY #102 were green at that checkpoint;
- `RPi5_main#275` merged the dormant-canary operation-consumption source gate at `887ae2a5cbe8e0c94a8de6fd5e11110fda443b75`; exact-main Validate #664, FAST-LANE #119 and GITHUB-ONLY #108 were green at that checkpoint.

Immediately before any consequential source, trust-boundary or live step, fresh-read current `RPi5_main/main`, all relevant cross-repository branch heads, exact-main CI, active PR/issues/reviews/comments and any required live evidence. No continuity merge SHA in this document is a durable `current main` assertion.

Completed Phase 4 source/live gates:

- [x] Current Hermes Deals governance/open-work inventory was re-read before implementation.
- [x] `hermes-deals#787` froze the public RPi5 execution inventory and capability grouping, with separate audit and release trust domains.
- [x] The replacement architecture is capability-specific rather than a generic powerful remote agent.
- [x] `origin-path-rpi5-audit` was selected as the lowest-risk read-only migration canary.
- [x] `RPi5_main#247` added and merged a dormant STRICT source contract for `hermes-deals.origin-path-audit.v1` with exact Hermes Deals repository/helper source identity bindings and adversarial tests.
- [x] The production executor registry remains globally disabled: `execution_enabled=false`. After `RPi5_main#275` it contains only the reviewed dormant STRICT `hermes-deals.origin-path-audit.v1` operation; this does not make P8 consume, dispatch or apply registry entries.
- [x] The Hermes Deals canary adapter remains validation-only; `apply()` fails closed.
- [x] The P0 authorization-surface trust-root audit completed fail-closed before P7; unknown/unapproved Issues writers are not accepted authority.
- [x] P7 created `Rozkalns Deploy Executor` as a private GitHub App installed only on `ops-workflows`, with Issues read-only plus Metadata read, webhook disabled and no GitHub write permission.
- [x] `RPi5_main#249` merged the exact-source-bound P8 dry-run installer/poller/timer/credential contract at `6a43ef875c785321a1b6bf09d8e558c5151c8546`.
- [x] Separately owner-authorized P8 host installation/activation completed on RPi5: exact source installed, sandbox verification passed, read-only authenticated polling succeeded as the dedicated unprivileged identity, timer is enabled/active, production dispatcher/result writer remain disabled and `PRODUCTION_MUTATION_STARTED=false`.
- [x] Temporary P8 staging credential was removed under a separate exact cleanup authorization without changing the installed root-owned credential.
- [x] `RPi5_main#250` merged the mutation-disabled P9 decision core and exact-main CI passed at `d425f98db85fc2ffdffb2d66f6b34727e5e75b07`.
- [x] `RPi5_main#254` merged the fail-closed P9 governance/Hermes baseline evidence schemas and parsers at `26f1f8810eaafbdf34e020f77253b57f7fe56da6`; exact-main CI passed and work item #251 is completed.
- [x] `RPi5_main#256` merged the fixed-path root-owned provenance loader/placement contract at `68632ac3c5216f569d235fe1af04d4c4df1e1d6c`; exact-main CI passed and work item #255 is completed.
- [x] `RPi5_main#258` merged the narrowly typed governance/Hermes evidence producer and fixed-file atomic publisher contract at `5f0f1ed62e4d52422139364898f735578be2cbdb`; exact-main CI passed and work item #257 is completed. The approved governance writer-set digest remains deliberately unset.
- [x] `RPi5_main#260` merged the complete-source fail-closed governance collector boundary at `cc2d9cd6bd9f76c9d6f96a6389acf765cf3555e8`; exact-main CI passed and work item #259 is completed. The current read-only executor capability still cannot independently prove the complete installed-App/integration administration surface of `ops-workflows`.
- [x] Owner architecture decision selected the P0 fallback `P9 TRUST DECISION: ISOLATED-AUTH-SURFACE` rather than broadening autonomous executor permissions.
- [x] `RPi5_main#263` merged the dormant isolated LIVE-AUTH authorization-surface contract at `6efb1efa3e8e4792de487ec16c95f6e0dc21f622`; exact-main Validate #637, FAST-LANE #92 and GITHUB-ONLY #81 are green. Work item #264 is completed. The merged source still keeps `authorization_repository_id=null`, `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false` and `production_mutation_enabled=false`.
- [x] `RPi5_main#265` merged the post-merge canonical continuity reconciliation at `252f1034eb1a79c2620f8ef3844a34f092c7e41f`; exact-main Validate #639, FAST-LANE #94 and GITHUB-ONLY #83 were green. This continuity merge does not alter the isolated-auth trust boundary or authorize any live/setup mutation.
- [x] `RPi5_main#266` merged the continuity refresh at `454d82216ad8ba9f50aeff38f212c0967fbe273c`; exact-main Validate #641, FAST-LANE #96 and GITHUB-ONLY #85 were green. This is historical completion evidence, not a durable current-main pin.
- [x] The first separately owner-authorized isolated-auth trust-boundary transaction created private `rozkalnsandris/deploy-authorizations` at observed GitHub ID `1350486101`, enabled Issues, disabled Actions, proved zero direct collaborators and zero installed GitHub Apps, then stopped fail-closed before App selection. Sanitized evidence is `RPi5_main#191` comment `5461784620`.
- [x] Connector-scope reconciliation rejects the earlier Issues-only assumption for `chatgpt-codex-connector` App ID `1144995`: its selected-repository permission set includes broader write authority for Actions, Contents/code, Issues, Pull requests and Workflows. The corrected source contract selects owner-only LIVE-AUTH writing and explicitly excludes that App from the authorization repository.
- [x] `RPi5_main#268` merged that corrected owner-only connector-scope contract at `de68073fa2269a128b130d67e4f868d914c61a47`; exact-main Validate #646, FAST-LANE #101 and GITHUB-ONLY #90 completed successfully.
- [x] Under a later exact owner authorization, the owner revalidated the intended private/Issues-on/Actions-off/zero-collaborator/no-writer posture in GitHub UI and performed one `Rozkalns Deploy Executor` selected-repository Save after the UI showed `Only select repositories`, `ops-workflows` plus `deploy-authorizations`, and only Issues read + Metadata read. The authorization was consumed at Save.
- [x] The initial connector-only post-save read could prove connector exclusion but could not enumerate Deploy Executor installation `157217641`; the transaction stopped without retry or mutation.
- [x] Later owner-authenticated sanitized post-save evidence was accepted in `RPi5_main#191` comment `5462591875`: repository ID `1350486101`, private visibility, Issues enabled, Actions disabled, zero direct collaborators, no writer integration including `chatgpt-codex-connector`, and exactly the read-only `Rozkalns Deploy Executor` App ID `4748870` with Issues read + Metadata read were proven.
- [x] `RPi5_main#271` merged the source-only accepted-evidence binding at `86b9c44ecb8c999fc559b30af0b024a47295e6d7`, preserving queue `rozkalnsandris/ops-workflows` / `1328835922`, binding authorization repository `rozkalnsandris/deploy-authorizations` / `1350486101`, excluding App `1144995`, accepting only reader App `4748870`, and keeping `activation_enabled=false`, `runtime_binding_ready=false`, `host_wiring_enabled=false` and `production_mutation_enabled=false`.
- [x] `RPi5_main#273` merged the source-only P9 runtime composition at `c0e43799c51c32e653515ba7695c364d61fb0a35`: queue and LIVE-AUTH repository roles are explicit, separate single-repository Issues-read clients are composed, app-authored LIVE-AUTH is rejected fail-closed, and a one-shot P9 source entrypoint exists while P8/runtime/host/production activation remains unchanged and disabled.
- [x] `RPi5_main#275` merged the source-only P9 canary-operation-consumption gate at `887ae2a5cbe8e0c94a8de6fd5e11110fda443b75`: the production registry contains only the reviewed dormant STRICT Hermes operation while `execution_enabled=false`; P8 remains operation-blind/read-only, adapter `apply()` remains fail-closed, and exact-main Validate #664, FAST-LANE #119 and GITHUB-ONLY #108 are green.

Phase 4 next gates (current, not waived):

- [x] **CONNECTOR-SCOPE SOURCE GATE:** owner-only LIVE-AUTH writing and explicit connector exclusion are merged in #268 and exact-main CI is green.
- [x] **POST-SAVE TRUST EVIDENCE:** accepted sanitized evidence is recorded in #191 comment `5462591875` and proves the isolated repository's required owner-only writer plus single read-only executor surface.
- [x] **ISOLATED-AUTH SOURCE BINDING:** #271 binds authorization repository ID `1350486101` separately from queue repository ID `1328835922` while all activation/runtime/host/production flags remain false.
- [x] **P9 RUNTIME COMPOSITION SOURCE GATE:** #273 splits queue versus LIVE-AUTH roles, composes separately repository-scoped read-only queue/auth clients and adds the one-shot P9 source entrypoint while keeping installed P8/runtime/host/production state unchanged.
- [x] **OPS-WORKFLOWS GOVERNANCE DIGEST NON-GATE:** `APPROVED_GOVERNANCE_WRITER_SET_SHA256` remains intentionally unset. Isolation does not convert the partial `ops-workflows` writer inventory into trusted LIVE-AUTH authority; the accepted isolated authorization repository is the trust root instead.
- [x] **P9 CANARY OPERATION CONSUMPTION SOURCE GATE:** #275 merged the exact reviewed dormant `hermes-deals.origin-path-audit.v1` operation into the production operation registry while keeping global `execution_enabled=false`; P8 still does not normalize, select, dispatch, preflight or apply registry operations and remains mutation/result-writer disabled.
- [ ] **P9 GENUINE READ-ONLY CANARY — CURRENT / WAITING:** run only against a real READY deploy-queue item plus a separate explicit owner decision. A fresh 2026-08-29 queue search found zero open issues titled `[DEPLOY-QUEUE][READY]`, so there is currently no eligible genuine P9 candidate. Do not create or promote a dummy/placeholder READY item or LIVE-AUTH merely to exercise the executor.
- [ ] P9 must end with local `DRY_RUN_READY` and `PRODUCTION_MUTATION_STARTED=false`; P10 remains a separate live mutation gate.
- [ ] Only after the replacement path is proven may any current Hermes Deals self-hosted canary runner/path be retired, and runner retirement itself remains separately owner-authorized.

Do not use this phase to select `chatgpt-codex-connector` for the authorization repository, retry or clean up consumed P9 transactions, change the accepted isolated-auth binding outside a separately reviewed source gate, consume retailer-specific execution authorizations, change parser/corpus state, write DB/Review/publication state, deploy production, mutate Cloudflare, modify repository settings or widen credentials/permissions without the exact separate gate for that action.

### Phase 5 — Hermes Deals migration completion / residual audit paths — PENDING AFTER PHASE 4

- [ ] Reconcile Phase 4 canary evidence against every remaining audit/diagnostic/release path.
- [ ] Migrate remaining capabilities incrementally, one trust domain at a time, preserving exact SHA, owner authorization, sanitized evidence and no-write boundaries where applicable.
- [ ] Remove each residual self-hosted runner only after its replacement is proven and separate owner authorization is granted.
- [ ] Record final runner/control-plane inventory and regression evidence in Hermes Deals governance and `RPi5_main#103`.

### Phase 6 — Hermes Tech authentication migration — DEFERRED: TEMPORARY PRIORITY OVERRIDE SUPERSEDED 2026-08-29

Phase 6 remains planned but is no longer the current program lane. The owner's later 2026-08-29 continuation correction returned current work to the `RPi5_main#236` RPi5 pull-executor/P9 trust-boundary lane. This sequencing correction does not authorize GitHub App permission changes, credential movement/rotation/revocation, ruleset/repository-setting changes, host/service/systemd changes, publication, deployment, scheduler mutation or any other live mutation.

Canonical Phase 6 owners and evidence:

- `rozkalnsandris/hermes-tech#95` / `#116` own the residual publisher/authentication risk and roadmap;
- `rozkalnsandris/RPi5_main#93` / `#110` own the host-side isolated publisher implementation;
- Hermes Tech `docs/publisher-credential-boundary.md` defines the replacement boundary and staged production migration;
- Phase 2 already proved `Rozkalns Automation` read-only Actions/Contents installation authentication. That existing App remains read-only unless a later reviewed Phase 6 design proves an exact additional endpoint/permission is required.

Phase 6 execution order:

1. **SOURCE INVENTORY / DESIGN GATE:** fresh-read current `hermes-tech/main`, `RPi5_main/main`, #95/#116/#110, current CI/reviews/comments and the exact source paths that still depend on persistent user auth, raw publisher SSH/deploy-key access or related GitHub credentials. Record only sanitized identities/capabilities; never read or emit secret bytes/tokens.
2. **SOURCE IMPLEMENTATION GATE:** implement the narrow #110 publisher boundary and authentication changes with synthetic/no-network tests first. Preserve exact repository/branch/base/parent/subject/path/refspec/fast-forward/post-push validation and existing classifier/readiness/timer/locking contracts. Do not expose arbitrary Git/SSH/sudo/shell execution.
3. **READ-ONLY AUTH MIGRATION:** replace any remaining persistent user `gh auth` dependency with repository-scoped short-lived GitHub App installation authentication where the operation is read-only. Do not broaden `Rozkalns Automation` beyond its proven Actions-read/Contents-read contract for this step.
4. **WRITE-CREDENTIAL DECISION:** keep publication write authority as a separate capability from read-only controller authentication. Before choosing a deploy-key copy, dedicated publisher App, or another token-minting boundary, document the exact required GitHub write endpoint, minimal permission, host secret owner, sudo/service boundary, rollback and abuse boundary. No permission/key/ruleset mutation occurs in source implementation.
5. **PRE-LIVE READY GATE:** source-reviewed implementation must be CI-green with adversarial synthetic coverage, exact rollback/recovery procedure and cross-repository producer/consumer audit. Merge remains explicit and does not authorize live activation.
6. **COMPOSITE LIVE GATE:** only after a separate exact owner authorization may host installation/credential placement and one controlled publication canary occur. Old shared-UID write access remains available for recovery until the new path is proven.
7. **RETIREMENT GATE:** only after the new path and recovery proof pass may the obsolete shared-UID credential/user-auth path be removed, rotated or revoked under another exact authorization if not already included in a bounded approved transaction.

Phase 6 exit requires:

- [ ] persistent user `gh auth` is not required for normal Hermes Tech controller reads;
- [ ] generated-content write credential/token-minting secret is isolated from the shared `andris` UID;
- [ ] Hermes runtime can invoke only the narrow generated-content publication capability and cannot read/export raw write authority;
- [ ] classifier, canary, timer, locking, deploy helper, readiness alerts, publication serialization and exact-SHA/fast-forward gates remain intact;
- [ ] one separately approved real publication canary and recovery proof pass;
- [ ] obsolete shared-UID credential/auth path is removed/rotated only after replacement proof;
- [ ] final residual risk and rotation/recovery procedure are recorded in #95/#116/#110 and this master plan before Phase 6 is marked complete.

### Phase 7 — RPi5_main auto-plan/readiness

- [ ] Keep host apply manual.
- [ ] Automate safe read-only plan/readiness generation where useful.
- [ ] Never auto-apply host files/services merely because CI passed.

### Phase 8 — Final retirement and audit

- [ ] No in-scope public repository depends on persistent RPi5 self-hosted Actions runners.
- [ ] External Actions are full-SHA pinned where required.
- [ ] Shared workflow callers use exact `ops-workflows` SHAs.
- [ ] GitHub App remains least privilege.
- [ ] No long-lived PAT required for normal operation.
- [ ] Full rollback/health/readiness audit PASS.
- [ ] Final architecture documented and issue #103 closed.

### Cross-cutting Track X — owner-authorized pull deploy executor v1 — P8 COMPLETE / P9 SOURCE COMPOSITION COMPLETE / GENUINE READ-ONLY CANARY WAITING

Roadmap: `RPi5_main#236`.
Threat model / protocol: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_V1.md`.
P5 audit: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P5_AUDIT.md`.
P6 attestation: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P6_ATTESTATION.md`.
P8 prep: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P8_PREP.md`.
P9 prep: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_PREP.md`.
P9 evidence contracts: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_EVIDENCE_CONTRACTS.md`.
P9 evidence provenance: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_PROVENANCE.md`.
P9 evidence producers: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_PRODUCERS.md`.
P9 governance collector: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_GOVERNANCE_COLLECTOR.md`.
P9 isolated authorization surface: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P9_ISOLATED_AUTH_SURFACE.md`.
Hermes Deals dormant canary contract: `docs/HERMES_DEALS_ORIGIN_PULL_CANARY_SOURCE.md`.

P0 through P8 are complete at their respective source/live gates. The P9 decision core is merged by `RPi5_main#250`; the P9 evidence schemas/parsers are merged by `RPi5_main#254` at `26f1f8810eaafbdf34e020f77253b57f7fe56da6c`; the fixed-path provenance boundary is merged by `RPi5_main#256` at `68632ac3c5216f569d235fe1af04d4c4df1e1d6c`; the typed producer/publisher boundary is merged by `RPi5_main#258` at `5f0f1ed62e4d52422139364898f735578be2cbdb`; the governance collector is merged by `RPi5_main#260` at `cc2d9cd6bd9f76c9d6f96a6389acf765cf3555e8` and #259 is completed. The isolated authorization-surface source gate is merged by `RPi5_main#263` at `6efb1efa3e8e4792de487ec16c95f6e0dc21f622`; #264 is completed. Historical continuity merges are `RPi5_main#265` at `252f1034eb1a79c2620f8ef3844a34f092c7e41f` and `RPi5_main#266` at `454d82216ad8ba9f50aeff38f212c0967fbe273c`; their recorded exact-main checks were green at those merge checkpoints. These SHAs are evidence only and are not a durable assertion of current `main`. `RPi5_main#268` then merged the corrected owner-only connector-scope contract at `de68073fa2269a128b130d67e4f868d914c61a47` with exact-main Validate #646, FAST-LANE #101 and GITHUB-ONLY #90 green. Accepted post-save trust evidence is recorded in #191 comment `5462591875`, and `RPi5_main#271` merged the isolated authorization-repository source binding at `86b9c44ecb8c999fc559b30af0b024a47295e6d7` with exact-main Validate #654, FAST-LANE #109 and GITHUB-ONLY #98 green. `RPi5_main#273` then merged the source-only P9 runtime composition at `c0e43799c51c32e653515ba7695c364d61fb0a35` with exact-main Validate #658, FAST-LANE #113 and GITHUB-ONLY #102 green. `RPi5_main#275` then merged the source-only canary-operation-consumption gate at `887ae2a5cbe8e0c94a8de6fd5e11110fda443b75` with exact-main Validate #664, FAST-LANE #119 and GITHUB-ONLY #108 green. P8 remains installed and accepted on RPi5 at exact reviewed source `6a43ef875c785321a1b6bf09d8e558c5151c8546`; the recurring poller is unprivileged/read-only, production dispatch remains disabled, and the temporary staging credential was removed separately after acceptance.

Critical P0 authorization invariant remains binding:

**An autonomous RPi5 credential must not have write authority over the GitHub surface from which owner authorization is accepted.**

The roadmap body's historical Issues read/write Deploy Executor App text remains superseded by P0 review/checkpoints. The accepted isolated authorization surface now proves owner-only LIVE-AUTH writing with the reviewed read-only Deploy Executor as the sole installed App, while `chatgpt-codex-connector` remains excluded. #271 source-binds `rozkalnsandris/deploy-authorizations` / `1350486101` separately from queue `rozkalnsandris/ops-workflows` / `1328835922`. #273 source-composes those roles through separate repository-scoped read-only clients and a one-shot P9 path; the installed P8 runtime is still unchanged and no host/runtime composition is activated. #275 makes only the reviewed dormant Hermes canary consumable from the production registry while global execution remains disabled and P8 remains operation-blind. Result reporting, if later implemented, must use a separately reviewed non-authority channel and must not gain the ability to mutate accepted LIVE-AUTH authority.

P9 preserves independent least-privilege roles:

- `rozkalnsandris/ops-workflows` / `1328835922` remains the READY/deploy-queue eligibility surface;
- `rozkalnsandris/deploy-authorizations` / `1350486101` is the accepted and source-bound isolated LIVE-AUTH authority surface; #273 composes it only in dormant source, while host/runtime wiring remains disabled;
- only exact owner actor `type=User`, ID `277435981`, may write accepted LIVE-AUTH issues; no writer/operator integration is approved;
- `chatgpt-codex-connector` App ID `1144995` remains excluded from the authorization repository;
- `Rozkalns Deploy Executor` App ID `4748870` remains Issues-read + Metadata-read only; accepted evidence proves it is the sole installed App on the authorization repository; #273 mints separately repository-scoped queue-read and authorization-read tokens rather than a generic broad token;
- `Rozkalns Automation` remains the existing source/CI reader with Actions read + Contents read on only the reviewed source repository allowlist.

`RPi5_main#250` provides stable source repository identity, merged/reachable exact-SHA + CI proof, JIT governance freshness, genuine READY queue/source/baseline/adapter-preflight composition and final unchanged-authority verification. `RPi5_main#254` provides strict schemas/parsers for the JIT governance and sanitized Hermes baseline evidence. `RPi5_main#256` provides the fixed-path root-owned consumer provenance/placement boundary. `RPi5_main#258` provides the separately reviewed typed producer/publisher source boundary while deliberately keeping governance evidence fail-closed. `RPi5_main#260` freezes the source/tree and completeness/provenance boundary for the complete `ops-workflows` writer-surface collector and proves the remaining admin/integration inventory capability gap. `RPi5_main#263` completes the dormant isolated-surface source gate; `RPi5_main#268` supersedes the earlier connector writer assumption with owner-only writing and explicit connector exclusion; accepted #191 evidence closes the post-save trust gate; `RPi5_main#271` binds the accepted authorization repository identity in machine source without changing P8/runtime/host/production state; `RPi5_main#273` completes the explicit queue/LIVE-AUTH role split, separate read-only client composition and one-shot P9 source entrypoint; and `RPi5_main#275` completes production-registry consumption of the reviewed dormant Hermes canary without enabling execution or changing the installed P8 runtime.

P9 source readiness prerequisites are complete through #275, but the genuine canary is intentionally **WAITING**. A fresh 2026-08-29 search of `ops-workflows` found no open issue titled `[DEPLOY-QUEUE][READY]`, so no eligible genuine queue candidate exists at this checkpoint. Do not manufacture one. When a real READY item appears, a separate explicit owner decision is still required before creating/using LIVE-AUTH or exercising protected-host/credential/runtime inputs. Immediately before that canary, freshly resolve current `RPi5_main/main`, exact-main CI, the queue item, isolated authorization trust evidence, exact source/CI/baseline evidence and every required cross-repository interface. If the current host lacks any reviewed read-only source client, credential binding or protected evidence input, STOP and request the exact separate owner authorization required for that boundary rather than silently wiring or broadening it.

The future transport remains data-only:

`owner-authored isolated LIVE-AUTH -> exact ops-workflows queue/SHA/target/operation/baseline revalidation -> static source-controlled operation registry -> fixed project adapter preflight -> DRY_RUN_READY`.

P9 does not cross the mutation-capable adapter boundary. P10 remains the first possible live executor canary and is separately gated.

Forbidden permanently for this track:

- SSH command transport;
- persistent self-hosted GitHub Actions production runner as the target architecture;
- inbound public RPi5 webhook/API;
- GitHub-provided shell command, executable path or arbitrary argv authority;
- generic `bash -c`, `sh -c`, `eval`, Docker/systemctl/sudo passthrough;
- merge-as-deploy authorization;
- automatic retry/cleanup/alternate path after mutation starts;
- automatic rollback unless the exact reviewed rollback policy is named in the queue, owner authorization and operation registry.

## Scope-control checklist before every step

1. Which phase am I executing?
2. What exact exit gate does this change advance?
3. Is this change required for that gate?
4. Does it preserve existing production safety boundaries?
5. Am I touching a repository or subsystem outside the phase scope?
If question 3 is `no` or question 5 is `yes`, do not make the change.

## Current next action

**#236 / P9 GENUINE READ-ONLY CANARY — WAITING FOR REAL READY + OWNER DECISION:** there is currently no open `ops-workflows` issue titled `[DEPLOY-QUEUE][READY]`, so no genuine P9 candidate is eligible. Do not create or promote a dummy READY item and do not create a placeholder LIVE-AUTH merely to test the executor.

When a genuine READY item appears, freshly re-read current `RPi5_main/main`, exact-main CI, current `ops-workflows/main`, the exact queue issue, relevant source repository/main + exact-SHA CI/reviews, the accepted isolated authorization trust surface, the operation-specific baseline evidence and all cross-repository producer/consumer interfaces. Require the queue to select the exact reviewed dormant `hermes-deals.origin-path-audit.v1` operation if this first P9 canary remains the Hermes origin-path audit. Any drift, ambiguous evidence, unsupported target/operation, or requirement for new permission/credential/host wiring stops before canary execution.

A P9 canary requires a separate explicit owner decision and must remain read-only: no `adapter.apply()`, no dispatcher, no `StateStore.consume()`, no result writer, no production deploy, no DB/Review/publication write and no host/runtime mutation unless a separately exact owner authorization explicitly covers a required read-only host/credential binding. Success is only local `DRY_RUN_READY` with `PRODUCTION_MUTATION_STARTED=false`. P10 remains a separate live mutation gate, and merge of this docs reconciliation authorizes none of these live actions. Phase 6 Hermes Tech work remains deferred while this #236/P9 gate is current.
