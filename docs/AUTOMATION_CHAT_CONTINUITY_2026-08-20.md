# Automation chat continuity audit — 2026-08-20

Status: HANDOFF / GOVERNANCE AUDIT

Cutoff: 2026-08-20 18:32 CEST

Purpose: preserve this long ChatGPT automation conversation in GitHub so a new chat can continue 1:1 without relying on conversation history or stale model memory.

## Read order in a new chat

Before any automation/deploy/host/runner/CI work:

1. Fresh-read current `RPi5_main/main`.
2. Read `docs/AUTOMATION_MASTER_PLAN.md`, but apply the drift warning below before trusting its Phase 3 status.
3. Read RPi5_main issue #196 — master-plan reconciliation blocker created by this audit.
4. Read RPi5_main issue #103 latest comments for later automation-program evidence.
5. For CV-specific work, read `rozkalnsandris/rozkalns-cv` issue #347 body **and latest comments**, then fresh-read current CV `main`, open PRs/issues and CI.
6. Before any host activation, audit every cross-repository producer/consumer interface used by that path. Repository-local green CI alone is not enough.
7. Never infer live production state from a repository `main` SHA. Resolve production through the reviewed read-only host/preflight evidence when needed.

## End-of-chat audit verdict

The architecture developed in this chat was directionally correct and the important safety boundaries worked, but the conversation snapshot itself is no longer a valid current-state source.

The main governance finding on 2026-08-20 is:

`docs/AUTOMATION_MASTER_PLAN.md` still describes CV Phase 3 as CURRENT and still contains the historical instruction to wait for a genuine AUTO target after `7012e830...`.

That instruction has been superseded by later GitHub evidence. Phase 3 subsequently completed. Issue #196 now blocks new automation-program phase work until the master plan is reconciled.

Do **not** execute the stale Phase 3 `Current next action` from the master-plan file.

## Fresh repository state at this handoff

### RPi5_main

Fresh current `main` observed by this audit:

`a5e388e617300b03e918e9789fef2cabb2a4dc35`

Recent RPi5_main work after the automation migration includes unrelated homelab/maintenance work. Do not interpret those later commits as Phase 3 automation changes merely because they are newer.

Current master-plan blob observed by the audit:

`d8d5239a457ed3650c5c25ee5173ba4c28546185`

Governance drift tracker:

RPi5_main #196 — `[P1/Governance] Reconcile AUTOMATION_MASTER_PLAN after completed CV Phase 3`.

### rozkalns-cv

Fresh current `main` observed by this audit:

`71191e9b0820d747a1b7dde67073d4892cb20679`

Current commit title:

`Harden public nginx container runtime boundary (#367)`

This is newer than the old Phase 3 baselines and newer than the body cutoff of canonical CV continuity issue #347.

CV #347 is still the correct current continuity anchor for CV work, but its body must be combined with its **latest comments and fresh GitHub reads**.

Latest production value explicitly verified in #347 continuity before this audit was:

`c8fc01f8365c90187a5f2489e07dd91137e4a354`

Do not claim that value is still live without a fresh production/preflight read. Current `main=71191e9b...` includes later source changes, including a runtime-relevant Compose hardening merge, so source and production must be treated as separate state.

## What this chat built and proved historically

The conversation started from an automation-program migration whose target architecture was:

`PR -> GitHub-hosted CI/security -> squash merge -> successful exact-SHA main CI -> trusted RPi5 local controller -> deterministic deploy classification -> automatic safe rollout or explicit approval -> root-owned transactional helper -> health/evidence`

Key completed foundations:

- `RPi5_main` became control-plane/host-truth repository.
- `ops-workflows` became the shared GitHub-hosted CI/security policy repository.
- Public-repository PR CI remained GitHub-hosted; persistent public-repo self-hosted production runners were treated as migration targets for removal.
- `Rozkalns Automation` GitHub App was established as a least-privilege read identity with Actions read + Contents read and short-lived installation tokens.
- CV preflight verifies exact current `main`, successful exact-SHA main CI, production ancestry, deployment classification and exact installed transport identities.
- CV deploy classes were made fail-closed: `NO_DEPLOY`, `AUTO_DEPLOY_SAFE`, `MANUAL_ROLLOUT_REQUIRED`, `DB_HOST_APPLY_REQUIRED`.
- Unknown runtime-relevant paths fail toward review, not toward automatic deployment.
- CV pull deployment was separated from the old Actions runner transport.
- Root-owned pull wrapper preserves exact-current-main, caller/evidence-path, helper/library identity, rollback and public verification boundaries.
- Public MIME/cache/nosniff/CSP checks remain inside the rollback-capable transaction before state commit.
- RPi5 readiness/controller source and systemd integration were added under a staged activation model.
- Generic weekly maintenance was separated from application-owned/local-build deployment behavior.

## Important incidents and lessons from this chat

### GitHub App token broker 422

The first host token canary failed closed because installation-token `repositories` payload used full `owner/repo` names instead of repository short names. The fix changed request serialization while preserving the allowlist and response-scope validation.

Lesson: validate GitHub API payload semantics against current API behavior and keep the response-scope check, not only the request intent.

### Legacy helper activation hazard

A safety audit found that simply installing a newer helper while the old self-hosted workflow was still alive could unlock queued legacy jobs because that workflow gated on installed helper identity.

Lesson: source installation itself can be a production-control mutation. During migrations, inspect old and new callers together before changing a shared executable.

### First explicit production canary / rollback defect

The first production canary encountered a new CVBot client-secret prerequisite before transaction commit. Rollback then reused the newer prerequisite semantics against the restored older baseline and also failed.

The fix:

- validates target-only prerequisites before mutation;
- makes rollback prerequisite validation depend on the restored baseline contract;
- keeps secrets out of evidence.

A follow-up host regression found a Bash conditional-context bug: relying on `errexit` inside a function called under `if ! function ...` allowed a failing strict validator to be followed by a successful `printf`. The fix used explicit failure propagation (`|| return 1`) and added a regression test executing the actual function under conditional context.

Lesson: Bash `set -e` is not a security boundary. Critical functions must explicitly propagate failure in conditional/subshell contexts.

### Stale CVBot image recreated by generic maintenance

A weekly maintenance catch-up used Compose behavior that skipped buildable image pulls but still performed a project-wide `compose up`, recreating the locally built `cvbot` from a stale image. Docker health then returned repeated 404 for `/health/ready`.

The #141 policy fixed the ownership boundary:

- buildable/local services such as `cvbot` are not generic recreation targets;
- changed registry-backed services may be updated selectively;
- `no-image-change-no-recreate` may include running services only under explicit `--no-recreate`, `--no-build`, `--no-deps` protections;
- configuration drift fails closed to project-owned deployment.

Lesson: `compose up` can apply configuration/recreate behavior even when image pulling/building is excluded. Generic maintenance must distinguish registry services from application-owned buildable services.

### Incomplete CVBot build-input identity

The original deterministic image-input identity did not cover every Dockerfile `COPY` source. That was fixed so the image identity contract includes every current Docker COPY input and is regression-tested against Dockerfile changes.

Lesson: an image label is only authoritative if its digest covers the full actual build input set.

### Cross-repository evidence-directory mismatch

RPi5 controller and CV root wrapper were independently green but disagreed on the evidence-directory namespace:

- producer originally created `rozkalns-cv-auto-deploy-*`;
- root wrapper accepted only bounded `rozkalns-cv-main-deploy-*`.

The safe correction changed the less-privileged producer and preserved the root wrapper's strict allow-pattern. Follow-up proof pinned the exact CV wrapper Git object/blob.

Permanent process rule created by this incident:

**Before every host activation gate, audit every cross-repository producer/consumer interface used by the host path. Repository-local green CI alone is insufficient evidence of compatibility.**

### #140 maintenance-policy proof false rejection

The first reviewed #140 host-install proof failed closed because its operator treated any `cvbot` occurrence in Compose args as an unsafe maintenance target. That contradicted the already reviewed #141 `no-image-change-no-recreate` contract, where `cvbot` is allowed in the command only together with `--no-recreate`.

The operator predicate was fixed without weakening/changing #141 policy.

Lesson: safety proofs must validate the semantics of the protected mode, not merely grep for an object name.

## Phase 3 actual completion — supersedes stale master-plan status

Later GitHub evidence after the chat-era wait state proves the CV migration completed:

- genuine `AUTO_DEPLOY_SAFE` one-shot controller deployment PASS to exact target `edea046966b8e69c14fb652b799297b9ae1df1bf`;
- transaction/public/readiness evidence PASS;
- recurring `rozkalns-cv-pull-deploy.timer` was separately owner-authorized and proven enabled/active;
- fresh timer-driven controller service execution succeeded;
- replacement execution path remained exact-SHA/readiness gated;
- legacy CV self-hosted runner retirement was separately owner-authorized;
- retired runner was `rpi5-rozkalns-cv-release`;
- legacy runner-only service/sudo reachability was removed;
- repository self-hosted runner count was verified as `0`;
- RPi5_main #140 and CV #90 are closed/completed.

Therefore:

`PHASE3_ACTUAL_STATUS=COMPLETE`

The old hourly `CV AUTO_DEPLOY_SAFE Watch` automation created during the waiting period is now disabled/historical and must not be resumed without a new explicit purpose.

## CV work after Phase 3

CV continued evolving substantially after the migration completed. Historical Phase 3 SHAs must not be treated as current product state.

Important continuity progression includes:

- classifier runtime-contract audit completed; broad `bot/` AUTO allowance was removed and runtime-sensitive bot paths became manual/fail-closed;
- later CV source/production reconciliations continued through the same pull-controller/transactional architecture;
- legacy self-hosted runner bootstrap source was later reduced to inert fail-closed tombstones;
- current operational docs were updated to describe the pull-controller and host-owned shared Cloudflare ingress architecture;
- Python dependency handling was made Dependabot-ready with `bot/requirements.in` + generated hash-locked `bot/requirements.txt`;
- CV #347 became the canonical CV-specific new-chat handoff and must be fresh-read for current work.

At the 2026-08-19 #347 cutoff the last verified production was `c8fc01f8365c90187a5f2489e07dd91137e4a354`; current source has advanced since then to `71191e9b...`. Resolve current production rather than guessing.

## Permanent safety / workflow rules to preserve

- GitHub is the source of truth for project source, issues, PRs and evidence.
- Fresh-read current state before every action; do not act from an old chat SHA.
- Work from branch -> focused commits -> Draft PR -> exact-head CI/security/review -> Ready -> explicit merge authorization -> squash merge -> exact-main CI -> deployment classification.
- Do not commit directly to `main`.
- `turpini` means continue safe/source/read-only work within the current reviewed scope; it is not a blanket production/host/root/settings authorization.
- Merge requires explicit owner instruction when the current repository workflow requires it.
- Production deploy, root/host/systemd/timer mutation, DB write/migration, Cloudflare/DNS/Access, GitHub settings, branch deletion and similar boundaries require separate explicit authorization.
- Never paste or request PEM/JWT/installation tokens/API keys/runtime secrets. Only sanitized evidence is acceptable.
- Keep GitHub App least privilege; do not broaden permissions without a proven endpoint need.
- Preserve exact-SHA CI gates, deterministic classification, rollback, health checks and evidence.
- Do not fabricate a dummy/same-SHA deployment candidate just to exercise automation.
- After a GitHub connector/write transport error, read actual GitHub state before replaying the mutation.
- Do not use `update_ref` to imitate branch deletion.
- Preserve shared Cloudflare Tunnel ownership outside the CV application lifecycle.
- Generic host maintenance must not implicitly become an application deployment mechanism.
- Cross-repository interfaces require joint compatibility proof before host activation.
- The old public-repo CV self-hosted release runner is retired; do not resurrect it.

## Current governance blocker and exact next program action

Issue #196 is the first governance prerequisite created by this handoff audit.

Before starting another automation-program phase:

1. Fresh-read current `RPi5_main/main`, #103 latest comments and relevant repository trackers.
2. Reconcile `docs/AUTOMATION_MASTER_PLAN.md` so CV Phase 3 is marked COMPLETE and the stale `7012e830...` wait instruction is removed.
3. Record the completed Phase 3 exit evidence: genuine AUTO one-shot, recurring timer proof, legacy runner retirement and runner count 0.
4. Resolve the **actual** current automation-program next phase from fresh evidence. #103 recorded Phase 4 Hermes Deals after Phase 3 completion, but Hermes Deals has evolved independently since then; do not execute an old Phase 4 checklist without fresh-reading its current roadmap/issues/PRs.
5. Perform the reconciliation as a docs-only branch -> PR -> CI -> exact-base -> squash merge.
6. Re-read the newly merged plan before any implementation/host/production action.

This continuity document itself authorizes no deployment, host mutation, timer/settings change, DB/Cloudflare change, branch deletion or new project implementation.

## New-chat bootstrap contract

A new chat should begin by saying it is continuing from this GitHub continuity document and issue #196, then fresh-read GitHub before making any claim about current source, production, CI, open work or next phase.

The new chat must not continue from the old `7012e830...` Phase 3 wait state. That state is historical and superseded.
