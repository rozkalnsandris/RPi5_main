# Automation Master Plan

Status: ACTIVE
Owner: Andris Rožkalns
Control repository: `rozkalnsandris/RPi5_main`
Canonical file: `docs/AUTOMATION_MASTER_PLAN.md`
Shared workflow repository: `rozkalnsandris/ops-workflows`

## Mandatory operating rule

Before starting any new automation, deployment, audit, CI, runner, GitHub App, or production-control change covered by this program:

1. Read this file from current `RPi5_main/main`.
2. Identify the first incomplete phase or explicitly named next step.
3. Work only on that step and its required prerequisites.
4. Do not expand scope into unrelated cleanup, UI polish, refactors, or opportunistic improvements.
5. Preserve existing exact-SHA, rollback, health-check, fail-closed, least-privilege, and evidence controls unless this plan explicitly replaces them.
6. Update this file when a phase materially changes, is completed, blocked, or superseded.
7. Re-check this file again before beginning the next phase.

If a proposed task conflicts with this file, stop that automation task and reconcile the plan first.

## Explicit exclusion

`rozkalnsandris/hermes-email-skill` is OUT OF SCOPE. Do not inspect, modify, migrate, automate, or change its visibility as part of this program.

## Architecture boundary

The automation program is intentionally split across two repositories.

### `rozkalnsandris/RPi5_main` — control plane and host truth

Keep here:

- this `docs/AUTOMATION_MASTER_PLAN.md` master plan;
- umbrella tracker issue #103;
- `docs/AUTOMATION_GITHUB_APP.md`;
- RPi5-local GitHub App verification tooling;
- RPi5 deploy/readiness controllers and host integration;
- systemd/service/timer definitions and host-side safety contracts;
- exact-SHA production approval/apply logic;
- host rollback, backup and health-check logic.

Do not turn `RPi5_main` into the shared GitHub workflow library.

### `rozkalnsandris/ops-workflows` — shared GitHub automation library

Keep here:

- reusable `workflow_call` workflows;
- reusable public-repository CI/security policy;
- action full-SHA pinning checks;
- public-runner safety checks;
- common deterministic GitHub-side audit policy that is not host-specific;
- documentation for consuming shared workflows;
- focused tests for shared workflow policy.

All consuming repositories must reference reusable workflows by an exact 40-character `ops-workflows` commit SHA after the first canary is proven.

### Migration safety rule

Do not remove the existing reusable baseline from `RPi5_main` until:

1. `ops-workflows` exists and is public;
2. its baseline is validated in its own CI;
3. one low-risk caller consumes it by exact commit SHA and passes;
4. `RPi5_main` itself successfully consumes the external exact-SHA baseline;
5. only then is the duplicate baseline in `RPi5_main` removed.

This avoids a control-plane gap during the split.

## Goal

Standardize the public repositories on a safe automation model:

- GitHub-hosted runners perform PR/main CI, deterministic audits, builds, secret/security checks, and reusable policy validation.
- Persistent RPi5 self-hosted GitHub Actions runners are removed from public-repository production and audit execution paths.
- RPi5 performs trusted production execution by polling/reading reviewed `main`, validating the exact target SHA and exact-SHA CI result, classifying deploy impact, and invoking narrow root-owned helpers locally.
- Safe application changes may deploy automatically after exact-SHA CI.
- Runtime/control-plane/database/host-sensitive changes require explicit approval.
- Production evidence and health verification remain fail-closed.
- Long-lived PATs are not the target authentication model. A least-privilege GitHub App is the desired RPi5 GitHub identity when its setup is ready.

## Canonical deploy-impact classes

1. `NO_DEPLOY`
   - Documentation, tests, issue templates, and other non-runtime-only changes.
   - No production action.

2. `AUTO_DEPLOY_SAFE`
   - Ordinary reviewed application/site/UI/API code that passed exact-SHA CI and does not cross a sensitive boundary.
   - RPi5 may deploy automatically.

3. `MANUAL_ROLLOUT_REQUIRED`
   - Runtime dependencies, Docker/runtime image behavior, schedulers, parsers/collectors, deployment/control-plane changes, and similar higher-risk changes.
   - Automation prepares/verifies; owner approval is required before production mutation.

4. `DB_HOST_APPLY_REQUIRED`
   - Database migrations/writes, host infrastructure, systemd/backup/Cloudflare ownership changes, and equivalent high-impact operations.
   - Always separate exact-SHA approval/apply.

Unknown runtime-relevant paths must fail toward deployment review, never silently toward `NO_DEPLOY`.

## Repository target state

### `ops-workflows`

Shared public automation library.

Target:
- GitHub-hosted runners only.
- Reusable `workflow_call` policy/workflows.
- Least-privilege permissions.
- External Actions pinned to full commit SHAs.
- No production secrets.
- No self-hosted RPi5 runners.
- No RPi5 host mutation.
- Consumers pinned to exact `ops-workflows` commit SHAs.

### `hermes-tech`

Reference production execution architecture.

Target:
- Keep GitHub-hosted CI.
- Keep local RPi5 pull/poll deploy classification.
- Keep canary-before-recurring-timer activation.
- Keep exact-SHA CI, health checks, rollback, publisher locking, and separate DB/runtime/control-plane approvals.
- Later migrate RPi5 GitHub authentication from persistent user CLI credentials to the dedicated least-privilege GitHub App without weakening existing gates.
- Consume shared GitHub-side policy from `ops-workflows` by exact SHA when adopted.

### `rozkalns-cv`

Current state: automatic post-main-CI deployment uses a persistent RPi5 self-hosted GitHub Actions runner.

Target:
- Preserve the existing transactional deploy helper, helper identity verification, rollback, public MIME/CSP/cache validation, and health checks.
- Replace the public-repo self-hosted Actions execution path with a local RPi5 pull/poll controller modeled on Hermes Tech.
- Auto-deploy only `AUTO_DEPLOY_SAFE` changes after exact-SHA CI.
- Require approval for sensitive classes.
- Retire the repository self-hosted release runner only after an exact-SHA canary passes and production/public verification succeeds.
- Consume shared GitHub-side policy from `ops-workflows` by exact SHA.

### `hermes-deals`

Current state: production deploy is owner-only manual exact-SHA workflow dispatch on a persistent RPi5 self-hosted runner; multiple read-only audits also use dedicated self-hosted runners.

Target:
- Preserve existing root-owned deploy/audit dispatchers, immutable/exact-SHA evidence contracts, rollback, DB protections, and post-deploy verification.
- Replace production self-hosted Actions execution with a local RPi5 pull/poll controller.
- Restore automation only for `AUTO_DEPLOY_SAFE` application changes.
- Keep parser/scheduler/control-plane/runtime changes manual.
- Keep DB/review/publication writes separately authorized.
- Migrate dedicated RPi5 audit execution away from public-repo self-hosted Actions runners to trusted local controllers while preserving owner authorization, exact SHA, sanitized evidence, and no-write boundaries.
- Pin third-party Actions to full commit SHAs.
- Consume shared GitHub-side policy from `ops-workflows` by exact SHA after the runner migration policy permits it.

### `RPi5_main`

Infrastructure source of truth and automation-program control repository.

Target:
- Host this master plan and umbrella tracker.
- Host GitHub App contract/verifier and RPi5-local automation controllers.
- Keep GitHub-hosted validation only.
- Keep infrastructure production apply manual.
- Automation may prepare a deterministic plan/readiness result, but must not auto-apply host changes.
- Consume the shared public-repository policy from `ops-workflows` by exact SHA after the split canary.
- Remove the duplicate local reusable baseline only after the external canary is proven.

### `rozkalnsandris`

Profile repository.

Target:
- No production deploy automation.
- Minimal public-repository validation/security baseline from `ops-workflows` by exact SHA.
- This remains the preferred first external canary caller.

## Shared reusable automation baseline

Canonical host: `rozkalnsandris/ops-workflows`.

Reusable workflows must:

- use `workflow_call`;
- run on GitHub-hosted runners only;
- default to least-privilege permissions;
- pin external Actions to full commit SHAs;
- never execute untrusted PR code on a persistent RPi5 runner;
- reject unsafe self-hosted runner use;
- detect unpinned third-party Actions/reusable workflows;
- reject `permissions: write-all`;
- preserve project-specific CI in each repository instead of replacing it with generic shallow checks.

Callers must pin reusable workflows to an exact `ops-workflows` commit SHA once the baseline is stable.

Historical Phase 1 evidence from before the repository split:

- reusable baseline merged in `RPi5_main` at `aa9d920d7f5fbc10a8e2b52bb346659f92c13172`;
- the baseline found and forced correction of two pre-existing unpinned `actions/checkout@v4` references in `RPi5_main`;
- low-risk caller `rozkalnsandris/rozkalnsandris` adopted the baseline pinned to that exact `RPi5_main` commit and passed its first workflow run.

That implementation remains temporarily as the migration source until `ops-workflows` canary completes.

## GitHub App target

Desired app name: `Rozkalns Automation` (or an equivalent unambiguous name if unavailable).

Purpose:
- RPi5 read-only access to repository/main/Actions state for exact-SHA verification.
- Optional narrowly scoped status/deployment reporting back to GitHub only if a later phase proves it necessary.

Initial permissions are defined by `docs/AUTOMATION_GITHUB_APP.md` and must remain minimal.

Add write permissions only for a proven function. Do not grant Secrets, Workflows write, or broad Administration access merely for convenience.

Use short-lived installation tokens rather than a long-lived PAT.

`ops-workflows` does not need to be installed into the RPi5 production GitHub App merely because it hosts reusable Actions. The App installation scope is driven only by RPi5 controller API requirements.

## Migration sequence and gates

### Phase 0 — Control plane and plan persistence — COMPLETE

- [x] Choose `RPi5_main` as canonical automation control repository.
- [x] Define this master plan and strict anti-drift operating rule.
- [x] Merge this plan to `main` after CI.
- [x] Create/maintain umbrella GitHub issue #103.

### Phase 1 — Reusable baseline proof — COMPLETE

- [x] Build and validate the reusable policy baseline.
- [x] Prove full-SHA action pinning/public-runner checks.
- [x] Adopt it in the low-risk profile caller.
- [x] Prove exact-SHA reusable workflow consumption.

### Phase 1B — Split shared workflows into `ops-workflows` — CURRENT

- [ ] Create public repository `rozkalnsandris/ops-workflows` with default branch `main`.
- [ ] Bootstrap README, reusable baseline and focused validation from the proven `RPi5_main` implementation.
- [ ] Validate `ops-workflows` on GitHub-hosted runners only.
- [ ] Switch `rozkalnsandris/rozkalnsandris` caller to the exact `ops-workflows` commit SHA and prove PASS.
- [ ] Switch `RPi5_main` caller to the exact `ops-workflows` commit SHA and prove PASS.
- [ ] Remove the duplicate reusable baseline from `RPi5_main` only after both canaries pass.
- [ ] Keep master plan, tracker, GitHub App contract/verifier, local controller code, host integration and production safety logic in `RPi5_main`.

Exit gate: `ops-workflows` is the sole reusable workflow source; profile and `RPi5_main` consume it by exact SHA; `RPi5_main` retains only host/control-plane responsibilities.

### Phase 2 — GitHub App preparation — PAUSED UNTIL PHASE 1B EXIT

- [x] Define exact required repository permissions from real controller calls.
- [ ] Create/install `Rozkalns Automation` only on in-scope production/controller repositories.
- [ ] Verify short-lived installation-token flow on RPi5.
- [ ] Verify read-only exact-SHA/Actions lookup before granting any write permission.

Exit gate: RPi5 can perform required exact-SHA read operations using the App; no persistent PAT is required.

### Phase 3 — CV pull-deploy migration

- [ ] Port Hermes Tech-style impact classifier/controller to CV semantics.
- [ ] Reuse existing `rozkalns-cv-deploy-main` transaction and verification helper.
- [ ] Add exact-SHA CI gate and local locking/readiness state.
- [ ] Run one exact-SHA canary.
- [ ] Verify production SHA and public site contracts.
- [ ] Enable recurring local controller.
- [ ] Disable/remove CV public-repo self-hosted release runner path only after canary success.

### Phase 4 — Hermes Deals production migration

- [ ] Pin unpinned external Actions in core CI first.
- [ ] Add deterministic Deals deploy-impact classifier.
- [ ] Build local RPi5 exact-SHA controller around the existing root-owned deploy helper.
- [ ] Preserve manual-only DB/review/publication/runtime-sensitive gates.
- [ ] Run exact-SHA canary and public/API/UI verification.
- [ ] Enable recurring local controller for safe classes.
- [ ] Retire the production self-hosted Actions release path after canary success.

### Phase 5 — Hermes Deals audit runner migration

- [ ] Inventory active dedicated audit runner workflows and their root-owned dispatchers.
- [ ] Group only genuinely equivalent audit transport patterns; do not refactor domain audit logic merely for neatness.
- [ ] Move trusted audit dispatch to local controllers while preserving exact-SHA, owner authorization, sanitized evidence, no-write boundaries, and deterministic evidence identity.
- [ ] Remove each self-hosted audit runner only after its replacement path proves a canary.

### Phase 6 — Hermes Tech authentication migration

- [ ] Replace persistent user `gh auth` dependency with GitHub App installation authentication.
- [ ] Preserve current classifier, canary, timer, locking, deploy helper, readiness alerts, and exact-SHA gates.
- [ ] Canary before changing recurring production behavior.

### Phase 7 — RPi5_main auto-plan/readiness

- [ ] Keep host apply manual.
- [ ] Automate safe read-only plan/readiness generation after reviewed main changes where technically useful.
- [ ] Never auto-apply host files/services merely because CI passed.

### Phase 8 — Final retirement and audit

- [ ] Confirm in-scope public repositories no longer depend on persistent RPi5 self-hosted Actions runners.
- [ ] Confirm external Actions are full-SHA pinned where policy requires.
- [ ] Confirm reusable workflow references point only to exact `ops-workflows` SHAs.
- [ ] Confirm GitHub App permissions are least-privilege.
- [ ] Confirm no long-lived PAT is required for normal operation.
- [ ] Run full production rollback/health/readiness audit.
- [ ] Update this document with final architecture and close umbrella tracker.

## Scope-control checklist before every step

Before making a change, answer these five questions from this file:

1. Which phase am I executing?
2. What exact exit gate does this change advance?
3. Is the change required for that gate?
4. Does it preserve existing production safety boundaries?
5. Am I touching any repository or subsystem outside the phase scope?

If question 3 is `no` or question 5 is `yes`, do not make the change.

## Current next action

**Phase 1B only:** create public `rozkalnsandris/ops-workflows`, bootstrap the proven reusable baseline there, prove exact-SHA canaries in the profile repo and `RPi5_main`, then remove only the duplicate shared baseline from `RPi5_main`. Keep the master plan, tracker, GitHub App contract/verifier and all RPi5-local production-control logic in `RPi5_main`. Do not resume Phase 2 until Phase 1B exit gate is green.
