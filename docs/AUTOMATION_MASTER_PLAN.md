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

Reference production execution architecture. Keep GitHub-hosted CI and local RPi5 pull/poll deploy classification, exact-SHA CI, locking, canary activation, rollback, health checks, and separate sensitive approvals. Later replace persistent user `gh auth` with the GitHub App.

### `rozkalns-cv`

Replace the public-repo self-hosted deployment runner with a local RPi5 pull/poll controller while preserving the existing transactional deploy helper, helper identity verification, rollback, and public MIME/CSP/cache checks.

### `hermes-deals`

Replace production and audit self-hosted runner transport with trusted local RPi5 controllers while preserving root-owned dispatchers, immutable evidence, rollback, DB protections, and separate authorization for parser/scheduler/control-plane/runtime/DB/review/publication-sensitive operations.

### `RPi5_main`

Remain infrastructure/control-plane truth. Keep infrastructure production apply manual. Automation may prepare deterministic readiness/plan states but must not auto-apply host changes merely because CI passed.

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

### Phase 3 — CV pull-deploy migration — CURRENT

- [x] Add a repository-scoped GitHub App read-token broker and narrow CV-only auth/sudo boundary; prove the CV-scoped token path on RPi5.
- [x] Add App-authenticated exact-SHA CI preflight and deterministic deploy-impact classification before any activation/deploy boundary.
- [x] Decouple the local pull transport from the legacy self-hosted runner path while keeping the legacy path intact during migration.
- [x] Gate `AUTO_DEPLOY_SAFE` on exact target identities for the dedicated pull deploy library and wrapper; mismatches become the sanitized `WAIT_PULL_TRANSPORT_ACTIVATION` state.
- [x] Add the RPi5-owned readiness controller, local locking/readiness state, and systemd definitions without enabling recurring execution.
- [x] Run the first one-shot readiness-controller host canary with exact-SHA CI, timer disabled/inactive, production unchanged, legacy helper unchanged, and public-site verification PASS.
- [x] Reconcile controller/readiness compatibility for both legacy `WAIT_HELPER_ACTIVATION` and current `WAIT_PULL_TRANSPORT_ACTIVATION` states in RPi5_main PR #128.
- [x] Keep public JS MIME/cache/nosniff/CSP verification inside the pull transaction before state commit so those failures remain rollback-capable (CV PR #141).
- [x] Require the dedicated pull wrapper to accept only the exact current fetched `origin/main`, not merely an ancestor SHA (CV PR #143).
- [x] Add and CI-prove the manual-only production-canary executor and disabled installer in RPi5_main PR #135; the source boundary itself does not authorize a production canary run.
- [x] Refresh/install the exact current controller/readiness/preflight/classifier artifacts and run a current-main one-shot readiness canary with the recurring timer disabled/inactive and `production_mutation_authorized=false`; install the parallel pull transport and manual canary executor without invoking production deployment.
- [x] Separately approve and run one exact-current-main production deploy-execution canary through the merged manual canary boundary; retain `MANUAL_ROLLOUT_REQUIRED` and require transactional rollback/public verification evidence.
- [ ] Enable the recurring local controller only after the replacement production canary is green.
- [ ] Disable/remove the public-repo self-hosted release runner only after the replacement production canary and public verification are green.

Phase 3 evidence through 2026-08-09:

- GitHub App broker payload fix: RPi5_main PR #124, merge `16e59bd1f5d9623c97ee5f10e76cebbf6fef7b16`;
- deploy-impact classifier/preflight ordering: CV PR #135, merge `f9db2c4a50589df0e4db27fa60f15629c8bdee8c`;
- pull transport decoupling: CV PR #138, merge `01bf1860ef5a32f345347eae121821f60a9c4606`;
- exact pull artifact identity gate: CV commit `d47b5fd1eab1103faf6ec91093965295b4414cbc`;
- readiness controller/source: RPi5_main PR #125, merge `78c0706be0a00bb87fe1ec98317e120c70309144`;
- first readiness-controller host canary: PASS with timer disabled/inactive, production unchanged and public site PASS (tracker #103 evidence);
- pull-transport wait-state compatibility: RPi5_main PR #128, merge `7589aa9b0acabd4d88a39af03b2d3571f70e9890`;
- transactional public-contract rollback boundary: CV PR #141, merge `378984487a068989d7f505b405c3409f2d4dd857`;
- exact-current-main pull wrapper hardening: CV PR #143, merge `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`;
- manual-only production-canary source boundary: RPi5_main PR #135, merge `e755ab2c3fbe99967645c62b6c83aeda3f8a0117`;
- current host-prep/readiness evidence: RPi5_main source `e755ab2c3fbe99967645c62b6c83aeda3f8a0117`, exact-main CI run `31336091705`; CV target `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, exact-main CI run `31336104950`; source/artifact identity PASS; `PULL_DEPLOY_CONTROLLER_RESULT=MANUAL_ROLLOUT_REQUIRED`; `CONTROL_PLANE_CHANGED=true`; `PRODUCTION_MUTATION_AUTHORIZED=false`;
- host-prep safety evidence: production SHA remained `0149bed2b84803f6fd8c191920191730c7a887cb` before/after; legacy helper unchanged; legacy runner sudo rule unchanged; recurring timer `disabled/inactive`; public site PASS; `PHASE3_PRODUCTION_CANARY_PREP=PASS`; `PREP_BLOCK_RC=0`;
- replacement production canary PASS at `2026-08-09T21:34:03Z`: approved/target SHA `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, previous production `0149bed2b84803f6fd8c191920191730c7a887cb`, exact-main CI `31336104950`, `DEPLOY_IMPACT=MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=true`, `DEPLOY_RESULT=PASS`, `PRODUCTION_CHANGED=true`, `MUTATION_STARTED=true`, `TRANSACTION_COMMITTED=true`, `ROLLBACK_PERFORMED=false`, `SHARED_INGRESS_CONTROLLED=false`, `DATABASE_MIGRATIONS_EXECUTED=false`;
- production-canary postconditions PASS: final production state `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, `TRANSACTIONAL_PUBLIC_CONTRACTS=PASS`, `READINESS_RECONCILIATION=CURRENT`, legacy helper unchanged, recurring timer remained `disabled/inactive`, evidence ID `rozkalns-cv-main-deploy-canary-6f13986c27d2.HIm0dR8B`, and `LEGACY_RUNNER_RETIREMENT_AUTHORIZED=false`.

The replacement production canary intentionally retained `MANUAL_ROLLOUT_REQUIRED` because the pre-deploy production-to-target range contained `runner/`/control-plane changes. The canary completed through the explicit manual boundary and production now equals the approved target. No reclassification to `AUTO_DEPLOY_SAFE` was used.

Sequencing note: the non-deploying host preparation happened before PR #133 reconciled the canonical plan, but PR #133 merged before the production canary was approved and executed. The production canary therefore ran after canonical sequencing had been restored.

### Phase 4 — Hermes Deals production migration

- [ ] Pin remaining unpinned external Actions in core CI.
- [ ] Add deterministic deploy-impact classifier.
- [ ] Build local RPi5 exact-SHA controller around existing root-owned deploy helper.
- [ ] Preserve manual DB/review/publication/runtime-sensitive gates.
- [ ] Run canary and public/API/UI verification.
- [ ] Enable recurring controller for safe classes.
- [ ] Retire production self-hosted Actions release path only after canary success.

### Phase 5 — Hermes Deals audit runner migration

- [ ] Inventory active audit runner workflows/dispatchers.
- [ ] Move trusted audit dispatch to local controllers without refactoring unrelated domain logic.
- [ ] Preserve exact SHA, owner authorization, sanitized evidence and no-write boundaries.
- [ ] Remove each self-hosted audit runner only after replacement canary success.

### Phase 6 — Hermes Tech authentication migration

- [ ] Replace persistent user `gh auth` dependency with GitHub App installation authentication.
- [ ] Preserve classifier, canary, timer, locking, deploy helper, readiness alerts and exact-SHA gates.
- [ ] Canary before recurring production behavior changes.

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

## Scope-control checklist before every step

1. Which phase am I executing?
2. What exact exit gate does this change advance?
3. Is this change required for that gate?
4. Does it preserve existing production safety boundaries?
5. Am I touching a repository or subsystem outside the phase scope?

If question 3 is `no` or question 5 is `yes`, do not make the change.

## Current next action

**Phase 3 only:** the replacement production canary is green. The first incomplete gate is now recurring local controller activation. Before enabling recurring execution, re-read current `RPi5_main/main`, verify the installed controller/readiness/systemd artifacts still match reviewed source, confirm CV production/readiness is `CURRENT`, and confirm the timer is still disabled/inactive. Recurring activation is a separate host mutation and requires explicit authorization.

When authorized, enable/start only the reviewed local `rozkalns-cv-pull-deploy.timer` path, verify the controller remains fail-closed and observes the current production without unexpected mutation, and capture timer/service/readiness evidence. Do not retire or modify the legacy self-hosted release runner in the same step.

Legacy self-hosted runner retirement remains the final Phase 3 gate and requires its own review/authorization only after recurring-controller activation evidence is green.
