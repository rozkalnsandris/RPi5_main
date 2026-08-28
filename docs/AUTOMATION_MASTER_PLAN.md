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

Reference production execution architecture. Keep GitHub-hosted CI and local RPi5 pull/poll deploy classification, exact-SHA CI, locking, canary activation, rollback, health checks, and separate sensitive approvals. Later replace persistent user `gh auth` with the GitHub App.

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

### Phase 4 — Hermes Deals public-repository execution migration — CURRENT: READ-ONLY RECONCILIATION FIRST

The historical Phase 4/5 checklist is not a runnable current-state script. Hermes Deals has continued evolving and now has extensive owner-gated release, retailer-audit, diagnostic, registration and retained-evidence paths. Current canonical public-runner migration is tracked by Hermes Deals #384, with project/runtime governance in #35, #39 and #386 plus the currently relevant retailer/continuity trackers.

Fresh audit anchor on 2026-08-20 only — re-resolve before every consequential step:

- `hermes-deals/main=e96dad4cc4099d43e81daf865e535dbbacef1346`;
- Hermes Deals #384 is open and requires inventory before migration;
- current retailer work has independent trust/authorization boundaries; for example Kaufland continuity #741 records a separately authorized-but-not-yet-executed K2 retained-evidence NO_OP replay. That authorization is not part of this automation migration and must not be consumed or widened by Phase 4 work.

First Phase 4 gate — source/read-only only:

- [ ] Fresh-read current `hermes-deals/main`, #35, #39, #386, #384, current open PRs/issues and the continuity issue(s) relevant to any path being inventoried.
- [ ] Inventory every current self-hosted workflow, runner label, installed dispatcher/helper/runtime dependency and owner-trigger path; do not rely on the historical runner count in #384.
- [ ] Group each path by capability: production release, read-only retailer audit, diagnostic, retained-evidence operation, bootstrap/finalizer or other explicit class.
- [ ] Audit every cross-repository producer/consumer contract used by those host paths before proposing activation or replacement.
- [ ] Record which paths are already pull/local-controller based, which still require a persistent repository runner, and which are obsolete/superseded; do not infer from workflow filenames alone.
- [ ] Select the lowest-risk read-only migration canary only after the inventory is reviewed and current-main exact-SHA/CI/owner-auth requirements are explicit.

Only after that read-only gate is complete may Phase 4 prepare a bounded source change. Any later root helper installation, sudoers/systemd/timer mutation, runner deregistration, production deploy, DB/Review/publication write, source/corpus apply, Cloudflare change or repository-settings mutation remains a separate explicit authorization boundary.

Phase 4 target sequence after inventory:

- [ ] Define the smallest replacement architecture per capability rather than one generic powerful agent.
- [ ] Keep ordinary PR validation GitHub-hosted and prevent public/fork-controlled input from executing arbitrary RPi5 code.
- [ ] Preserve exact merged/reachable SHA + successful CI + owner numeric-identity authorization where the existing contract requires them.
- [ ] Keep root privilege behind narrow hash-pinned dispatchers/helpers and sanitized evidence.
- [ ] Migrate one lowest-risk read-only canary first and prove end-to-end fail-closed behavior.
- [ ] Migrate remaining production/audit capabilities incrementally only after each predecessor is proven.
- [ ] Deregister persistent Hermes Deals repository runners only after all required capabilities have proven replacements; final target is runner count `0` or an explicitly justified residual runner accepted by the owner.

### Phase 5 — Hermes Deals migration completion / residual audit paths

- [ ] Reconcile Phase 4 inventory results against every remaining audit/diagnostic/release path.
- [ ] Preserve exact SHA, owner authorization, sanitized evidence and no-write boundaries for read-only audits.
- [ ] Remove each residual self-hosted runner only after replacement canary success and separate owner authorization.
- [ ] Record final runner/control-plane inventory and regression evidence in Hermes Deals governance and RPi5_main #103.

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

### Cross-cutting Track X — owner-authorized pull deploy executor v1 — P6 SOURCE ONLY (P0/P1/P2/P3/P4/P5 COMPLETE)

Roadmap: `RPi5_main#236`.
Threat model / protocol: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_V1.md`.
P5 audit: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P5_AUDIT.md`.
P6 attestation: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P6_ATTESTATION.md`.

This track standardizes a future owner-authorized GitHub -> outbound-polling RPi5 execution transport. It does **not** replace the ordered repository migration phases above and it does not make a READY queue item executable by itself.

Current ordering rules:

- the canonical production/live migration lane remains Phase 4 until the plan explicitly advances it;
- P0 merged through #237, P1 through #238, P2 through #241, P3 through `RPi5_main#242` plus `ops-workflows#23`, P4 through `RPi5_main#243`, and P5 through `RPi5_main#244`;
- merged P5 runtime/source candidate identity is `RPi5_main/main=cef684e8cde2da00de2f1591c58647a868e6acf3`; its exact-main Validate #589, Gitleaks/public baseline, FAST-LANE drift #44 and GITHUB-ONLY drift #33 are green;
- P5-bound cross-repository identities remain `ops-workflows/main=c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8` and `rozkalns-cv/main=d25730b20c41edff29a83927bff386751f053cd0`, with their exact-main CI green and audited policy/helper blob identities unchanged;
- the owner's fresh 2026-08-28 `turpini` continuation selects only P6 post-merge exact-main/cross-repository attestation source work;
- P6 may update governance/evidence only; it must not change executor runtime code, the production registry, adapters or the proposed systemd unit;
- `ops/deploy/executor-operations.json` remains `execution_enabled=false` with zero production operations, and the P5 CV adapter remains mutation-disabled;
- the P6 governance commit is not a replacement runtime-source authorization: the attested P5 runtime/source candidate remains exact SHA `cef684e8cde2da00de2f1591c58647a868e6acf3` until a later reviewed source change explicitly supersedes it;
- every source PR merge remains separately explicit owner authority;
- P7 GitHub App creation/permission changes, P8 host installation, P9/P10 canaries and all later live execution remain blocked and require their own explicit live authorization.

Critical authorization invariant established by P0 and enforced by P1-P6:

**An autonomous RPi5 credential must not have write authority over the GitHub surface from which owner authorization is accepted.**

Therefore the future executor-side authorization App defaults to `ops-workflows` only with Issues **read-only**, not Issues write. The existing `Rozkalns Automation` App also remains unchanged at Actions read + Contents read on its existing repository scope. Automatic GitHub result reporting must use a separately reviewed non-authority channel; it must never require giving the validator write access to LIVE-AUTH authority.

The future transport remains data-only:

`owner-authored LIVE-AUTH -> exact queue/SHA/target/operation/baseline revalidation -> static source-controlled operation registry -> fixed project adapter -> existing narrow controller/helper`.

Forbidden permanently for this track:

- SSH command transport;
- persistent self-hosted GitHub Actions production runner;
- inbound public RPi5 webhook/API;
- GitHub-provided shell command, executable path or arbitrary argv authority;
- generic `bash -c`, `sh -c`, `eval`, Docker/systemctl/sudo passthrough;
- merge-as-deploy authorization;
- automatic retry/cleanup/alternate path after mutation starts;
- automatic rollback unless the exact reviewed rollback policy is named in the queue, owner authorization and operation registry.

P6 exit gate is one reviewed/green `RPi5_main` source attestation PR proving P5 exact-main CI, unchanged cross-repository source identities/CI and the exact installation-candidate runtime source SHA, with zero runtime/registry/adapter/systemd/App/permission/credential/host/production mutation. After that PR is separately merged, re-read the resulting exact `main` and require exact-main CI green. Only then is P6 complete. P7 remains a separate explicit LIVE STOP.

## Scope-control checklist before every step

1. Which phase am I executing?
2. What exact exit gate does this change advance?
3. Is this change required for that gate?
4. Does it preserve existing production safety boundaries?
5. Am I touching a repository or subsystem outside the phase scope?
If question 3 is `no` or question 5 is `yes`, do not make the change.

## Current next action

**Bounded explicit exception: #236 P6 exact-main/cross-repository source attestation is the immediate selected task; the canonical production/live lane remains Hermes Deals Phase 4.** Phase 3 of the main migration program is complete and must not be reopened merely to continue this cross-cutting track.

For #236 P6, change only tracked RPi5_main governance/evidence needed to attest merged P5 exact-main and the unchanged `ops-workflows` / `rozkalns-cv` compatibility identities. Do not modify executor runtime code, `ops/deploy/executor-operations.json`, adapters or the proposed executor systemd unit. Record `cef684e8cde2da00de2f1591c58647a868e6acf3` as the installation-candidate runtime source identity, while making explicit that this is not host-install authority. Do not create/modify a GitHub App, grant permissions, generate/place credentials, install host files, change root/sudoers/systemd/timers, activate an executor, create LIVE-AUTH or deploy production. P6 ends only after the attestation PR is explicitly merged and exact-main CI is green.

After P6 completion, return to the first incomplete Phase 4 Hermes Deals #384 current-state inventory/reconciliation unless a later fresh owner instruction and this master plan select another safe source prerequisite. **Do not begin P7 under a generic continuation:** P7 is a GitHub App/permission trust-boundary mutation and requires a separate explicit LIVE authorization.

Do **not** start a generic Deals controller, install/refresh host artifacts, change root/sudoers/systemd/timers, deregister a runner, deploy production, write DB/Review/publication state, consume a retailer-specific execution authorization, or change GitHub/Cloudflare settings as part of the first Phase 4 gate.

After the read-only inventory is documented and reviewed, update this plan if the actual Phase 4 sequencing differs from the target sequence above. Only then open a narrowly scoped implementation issue/PR for the selected lowest-risk read-only canary.