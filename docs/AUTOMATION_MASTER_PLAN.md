# Automation Master Plan

Status: ACTIVE
Owner: Andris Rožkalns
Control repository: `rozkalnsandris/RPi5_main`
Canonical file: `docs/AUTOMATION_MASTER_PLAN.md`

## Mandatory operating rule

Before starting any new automation, deployment, audit, CI, runner, GitHub App, or production-control change covered by this program:

1. Read this file from current `main`.
2. Identify the first incomplete phase or explicitly named next step.
3. Work only on that step and its required prerequisites.
4. Do not expand scope into unrelated cleanup, UI polish, refactors, or opportunistic improvements.
5. Preserve existing exact-SHA, rollback, health-check, fail-closed, least-privilege, and evidence controls unless this plan explicitly replaces them.
6. Update this file when a phase materially changes, is completed, blocked, or superseded.
7. Re-check this file again before beginning the next phase.

If a proposed task conflicts with this file, stop that automation task and reconcile the plan first.

## Explicit exclusion

`rozkalnsandris/hermes-email-skill` is OUT OF SCOPE. Do not inspect, modify, migrate, automate, or change its visibility as part of this program.

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

### `hermes-tech`

Reference implementation and current architectural baseline.

Target:
- Keep GitHub-hosted CI.
- Keep local RPi5 pull/poll deploy classification.
- Keep canary-before-recurring-timer activation.
- Keep exact-SHA CI, health checks, rollback, publisher locking, and separate DB/runtime/control-plane approvals.
- Later migrate RPi5 GitHub authentication from persistent user CLI credentials to the dedicated least-privilege GitHub App without weakening existing gates.

### `rozkalns-cv`

Current state: automatic post-main-CI deployment uses a persistent RPi5 self-hosted GitHub Actions runner.

Target:
- Preserve the existing transactional deploy helper, helper identity verification, rollback, public MIME/CSP/cache validation, and health checks.
- Replace the public-repo self-hosted Actions execution path with a local RPi5 pull/poll controller modeled on Hermes Tech.
- Auto-deploy only `AUTO_DEPLOY_SAFE` changes after exact-SHA CI.
- Require approval for sensitive classes.
- Retire the repository self-hosted release runner only after an exact-SHA canary passes and production/public verification succeeds.

### `hermes-deals`

Current state: production deploy is owner-only manual exact-SHA workflow dispatch on a persistent RPi5 self-hosted runner; multiple read-only audits also use dedicated self-hosted runners.

Target:
- Preserve the existing root-owned deploy/audit dispatchers, immutable/exact-SHA evidence contracts, rollback, DB protections, and post-deploy verification.
- Replace production self-hosted Actions execution with a local RPi5 pull/poll controller.
- Restore automation only for `AUTO_DEPLOY_SAFE` application changes.
- Keep parser/scheduler/control-plane/runtime changes manual.
- Keep DB/review/publication writes separately authorized.
- Migrate dedicated RPi5 audit execution away from public-repo self-hosted Actions runners to trusted local controllers while preserving owner authorization, exact SHA, sanitized evidence, and no-write boundaries.
- Pin third-party Actions to full commit SHAs.

### `RPi5_main`

Infrastructure source of truth and automation-program control repository.

Target:
- Host this master plan.
- Host the reusable public-repository automation/security baseline unless a later reviewed decision moves it to a dedicated repository.
- Keep GitHub-hosted validation only.
- Keep infrastructure production apply manual.
- Automation may prepare a deterministic plan/readiness result, but must not auto-apply host changes.

### `rozkalnsandris`

Profile repository.

Target:
- No production deploy automation.
- Only minimal public-repository validation/security baseline where useful.

## Central reusable automation baseline

Canonical host: `rozkalnsandris/RPi5_main`.

Reason: it already owns RPi5 infrastructure/control-plane policy, is public, and avoids creating another control repository solely for orchestration.

Reusable workflows must:
- use `workflow_call`;
- run on GitHub-hosted runners only;
- default to least-privilege permissions;
- pin external Actions to full commit SHAs;
- never execute untrusted PR code on a persistent RPi5 runner;
- reject newly introduced unsafe self-hosted runner use unless an explicitly reviewed transition exception exists;
- detect unpinned third-party actions;
- preserve project-specific CI in each repository instead of replacing it with generic shallow checks.

Callers must pin reusable workflows to an exact commit SHA once the baseline is stable.

Phase 1 evidence:
- reusable baseline merged in `RPi5_main` at `aa9d920d7f5fbc10a8e2b52bb346659f92c13172`;
- the baseline found and forced correction of two pre-existing unpinned `actions/checkout@v4` references in `RPi5_main`;
- low-risk caller `rozkalnsandris/rozkalnsandris` adopted the baseline pinned to that exact commit and passed its first workflow run.

## GitHub App target

Desired app name: `Rozkalns Automation` (or an equivalent unambiguous name if unavailable).

Purpose:
- RPi5 read-only access to repository/main/Actions state for exact-SHA verification.
- Optional narrowly scoped status/deployment reporting back to GitHub.

Initial permissions are defined by `docs/AUTOMATION_GITHUB_APP.md` and must remain minimal.

Add write permissions only for a proven function such as deployment/check reporting or sanitized audit comments. Do not grant Secrets, Workflows write, or broad Administration access merely for convenience.

Use short-lived installation tokens rather than a long-lived PAT.

## Migration sequence and gates

### Phase 0 — Control plane and plan persistence

- [x] Choose `RPi5_main` as canonical automation control repository.
- [x] Define this master plan and strict anti-drift operating rule.
- [x] Merge this plan to `main` after CI.
- [x] Create/maintain one umbrella GitHub issue that tracks phase status and points here.

Exit gate: master plan exists on `main`, CI passes, umbrella tracker exists.

### Phase 1 — Reusable public-repo baseline

- [x] Add a reusable `workflow_call` baseline in `RPi5_main`.
- [x] Check action SHA pinning and public-runner safety without replacing project-specific tests.
- [x] Validate the baseline in `RPi5_main` itself.
- [x] Adopt it in one low-risk caller first.
- [x] Pin caller reference to exact `RPi5_main` commit SHA.

Exit gate: reusable baseline is CI-proven and exact-SHA consumed by at least one repository.

### Phase 2 — GitHub App preparation

- [x] Define exact required repository permissions from real controller calls.
- [ ] Create/install `Rozkalns Automation` only on in-scope repositories.
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

Exit gate: CV deploys safely without a persistent public-repo self-hosted Actions runner.

### Phase 4 — Hermes Deals production migration

- [ ] Pin unpinned external Actions in core CI first.
- [ ] Add deterministic Deals deploy-impact classifier.
- [ ] Build local RPi5 exact-SHA controller around the existing root-owned deploy helper.
- [ ] Preserve manual-only DB/review/publication/runtime-sensitive gates.
- [ ] Run exact-SHA canary and public/API/UI verification.
- [ ] Enable recurring local controller for safe classes.
- [ ] Retire the production self-hosted Actions release path after canary success.

Exit gate: safe Deals application merges can deploy automatically without exposing RPi5 as a public-repo Actions runner.

### Phase 5 — Hermes Deals audit runner migration

- [ ] Inventory active dedicated audit runner workflows and their root-owned dispatchers.
- [ ] Group only genuinely equivalent audit transport patterns; do not refactor domain audit logic merely for neatness.
- [ ] Move trusted audit dispatch to local controllers while preserving exact-SHA, owner authorization, sanitized evidence, no-write boundaries, and deterministic evidence identity.
- [ ] Remove each self-hosted audit runner only after its replacement path proves a canary.

Exit gate: no persistent RPi5 GitHub Actions runner is required by Deals public-repo audits.

### Phase 6 — Hermes Tech authentication migration

- [ ] Replace persistent user `gh auth` dependency with GitHub App installation authentication.
- [ ] Preserve current classifier, canary, timer, locking, deploy helper, readiness alerts, and exact-SHA gates.
- [ ] Canary before changing recurring production behavior.

Exit gate: Hermes Tech uses the common GitHub App identity without regression.

### Phase 7 — RPi5_main auto-plan/readiness

- [ ] Keep host apply manual.
- [ ] Automate safe read-only plan/readiness generation after reviewed main changes where technically useful.
- [ ] Never auto-apply host files/services merely because CI passed.

Exit gate: operator receives deterministic READY/BLOCKED/NO_OP state while production host mutation remains explicit.

### Phase 8 — Final retirement and audit

- [ ] Confirm in-scope public repositories no longer depend on persistent RPi5 self-hosted Actions runners.
- [ ] Confirm external Actions are full-SHA pinned where policy requires.
- [ ] Confirm reusable workflow references are exact-SHA pinned.
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

**Phase 2 only:** create and install `Rozkalns Automation` with the exact read-only permission/repository scope defined in `docs/AUTOMATION_GITHUB_APP.md`; then verify one-hour installation-token authentication and exact-SHA/Actions reads on RPi5. Do not start CV/Deals runner migration before the Phase 2 exit gate is proven.
