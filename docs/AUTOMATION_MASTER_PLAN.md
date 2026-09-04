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

### Phase 4 — Hermes Deals public-repository execution migration — CURRENT: #191 / P9 EXIT GATE MET / P10 SEPARATELY GATED

Phase 4 remains incomplete. Canonical current continuation is `RPi5_main#191`. Gate B source-App capability proof, Gate C least-privilege D1 credential correction, Gate D source/host convergence and READY eligibility are **PASS / COMPLETE**. The clean genuine P9 read-only authorization canary is now also **PASS**, while `ops-workflows#27` remains an eligibility/read-only canary record rather than P10 execution authority. Current mutable state must still be fresh-read before every consequential continuation.

Historical P9 failures remain non-reusable evidence. The first incident chain used malformed shell syntax and then a prohibited retry inside an already consumed STRICT envelope. The later clean-repeat #6 invocation was correctly formed but failed closed in `_preflight()` because its trusted baseline was stale, before `LazyP9StateStore` construction. A timing-recovery attempt then produced baseline evidence `1e2adbccd7d92533b2021f1fb7648f87a496001b6cb3703ae258941e44662bec`, but owner-authored `deploy-authorizations#7` was created at `2026-08-31T21:33:00Z`, twenty seconds after that baseline expired at `21:32:40Z`; exactly one P9 #7 invocation correctly stopped with the same stale-baseline error and was not retried. #5/#6/#7 and their baselines are consumed or expired historical evidence only.

The accepted clean P9 used the repaired freshness flow after all non-live preparation. One baseline returned PASS for exact Control `f04601dfd47e5691c875c0935b36ff101680f4dd`, `observed_at=2026-08-31T21:43:20Z`, `expires_at=2026-08-31T21:48:20Z`, `remaining_freshness_seconds=299`, and evidence SHA-256 `3c9e713bd802758f4cd6194d9ba9f08741410312b0dc881471ad809316af43ff`. Owner-authored `deploy-authorizations#8` was created three seconds later at `21:43:23Z`, with owner numeric ID `277435981`, `type=User`, `author_association=OWNER`, `performed_via_github_app=null`, queue #27, exact Control source and request ID `4ee18cb5-5551-49e2-b368-e159e5054ade`. Exactly one correctly formed `/usr/local/sbin/rozkalns-deploy-p9 --issue-number 8` then returned protocol-compliant `DRY_RUN_READY`; preflight and result both resolved `baseline_evidence_id=sha256:e505bd13adddbb7862f06d7a0f3930fde98a45e3f38e9d4931137ab5f080b6db`, source/current-main both matched exact Control `f04601df...`, source CI run was `33380350418`, and `mutation_dispatch_enabled=false`, `result_writer_enabled=false`, `production_mutation_started=false`. No workflow owner trigger/dispatch/rerun, P10 or production deploy occurred.

`RPi5_main#308` merged the source-only 300-second-preserving freshness handoff repair. `RPi5_main#312` later reconciled overlapping host-convergence operators and merged at current canonical checkpoint `5c89aff9d6e02b2a8d39d11ff917ad19c9bab202`; trusted-host convergence recorded in canonical #191 proves the checkout reached that exact source and only `/usr/local/sbin/rozkalns-deploy-p9-control-baseline` was replaced with repaired blob `8dc38e4d224373925483a45b782f04e0aa27a8bd`, preserving `root:root 0755` and byte-for-byte/source SHA-256 equality. These repairs explain why the accepted #8 handoff completed inside the freshness window; they do not authorize P10.

Current classification is binding:

`P9_EXIT_GATE=MET`
`CLEAN_P9_REPEAT_REQUIRED=false`
`P10_BLOCKED_BY_P9=false`
`P10_EXECUTED=false`
`P10_SEPARATE_LIVE_GATE_REQUIRED=true`

Historical source evidence from the 2026-08-29 P9 isolated-auth and continuity chain; these pins are evidence only and must never be inferred to be current branch state:

- `hermes-deals/main=140a50a17b398862a220e9302da1e6fa0680f2a2` was the reviewed Hermes anchor for this P9 chain; the canary source merge `2fbde52cc5b6661343dca3fd967d8112cb2bffbe` remains historical ancestry;
- `RPi5_main#263` merged the isolated-auth source gate at `6efb1efa3e8e4792de487ec16c95f6e0dc21f622`;
- `RPi5_main#265` merged post-merge continuity at `252f1034eb1a79c2620f8ef3844a34f092c7e41f` with historical exact-main Validate #639, FAST-LANE #94 and GITHUB-ONLY #83 green;
- `RPi5_main#266` merged continuity refresh at `454d82216ad8ba9f50aeff38f212c0967fbe273c` with historical exact-main Validate #641, FAST-LANE #96 and GITHUB-ONLY #85 green;
- `ops-workflows/main=c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8` was the reviewed queue/policy anchor for this P9 chain;
- `RPi5_main#271` merged the accepted isolated-auth repository source binding at `86b9c44ecb8c999fc559b30af0b024a47295e6d7`; exact-main Validate #654, FAST-LANE #109 and GITHUB-ONLY #98 were green at that checkpoint;
- `RPi5_main#273` merged the source-only queue/LIVE-AUTH runtime composition at `c0e43799c51c32e653515ba7695c364d61fb0a35`; exact-main Validate #658, FAST-LANE #113 and GITHUB-ONLY #102 were green at that checkpoint;
- `RPi5_main#275` merged the dormant-canary operation-consumption gate at `887ae2a5cbe8e0c94a8de6fd5e11110fda443b75`; exact-main Validate #664, FAST-LANE #119 and GITHUB-ONLY #108 were green at that checkpoint.

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
- [x] **GATE B SOURCE-APP CAPABILITY PROOF:** accepted PASS/COMPLETE in canonical #191 after the repository-specific installation repair, diagnostics and repository-selection remediation sequence.
- [x] **GATE C D1 PROVIDER-SIDE LEAST-PRIVILEGE CORRECTION:** accepted PASS in #191 comment `5471157006` for token `d1c673feaf430ab7c9a0898ef82ecf46`, exact account `70e29dbca0e8363358659102d2b74178`, active status and exactly `D1 Read` with no unrelated/write permission.
- [x] **GATE C HOST CREDENTIAL REPLACEMENT:** accepted PASS in #191 comment `5471196497`; the trusted RPi5 checkout was bound to exact source `7506e0ebc560b6d8c2266dd5de622d65659a719a`, the #289 operator verified the same active token ID and replaced only the fixed credential without reading old credential bytes, D1 access, rollback or retry.
- [x] **GATE C RE-PROOF:** final metadata-safe provider policy re-proof plus the host replacement receipt were accepted in #191 comment `5471209774`; **Gate C overall is GREEN / COMPLETE**.
- [x] **GATE D TRUSTED BASELINE / READY ELIGIBILITY:** accepted source/host convergence, post-runtime fresh baseline PASS and #27 READY eligibility reconciliation are recorded in #191 comments `5481283344`, `5482221858`, `5482425077` and `5482473002`. This proves queue eligibility only; comments/READY never extend baseline freshness.
- [x] **P9 EXIT-GATE INCIDENT CLASSIFICATION — HISTORICAL:** #307 recorded the earlier `P9_EXIT_GATE=NOT_MET` decision for the malformed/retry and #6 stale-baseline incidents. It remains historical incident evidence and does not override the later clean #8 PASS.
- [x] **P9 FRESHNESS-HANDOFF SOURCE REPAIR:** #308 preserved the 300-second baseline lifetime and 600-second LIVE-AUTH TTL while adding trusted-server-time diagnostics and the 180-second handoff floor.
- [x] **P9 FRESHNESS HOST CONVERGENCE:** #312 reconciled the duplicate operators; trusted-host receipt #191 comment `5484799171` proves exact source `5c89aff9d6e02b2a8d39d11ff917ad19c9bab202` and repaired baseline CLI blob `8dc38e4d224373925483a45b782f04e0aa27a8bd` installed as the single canonical target.
- [x] **P9 CLEAN GENUINE READ-ONLY CANARY:** fresh baseline PASS plus owner-authored `deploy-authorizations#8` and exactly one P9 #8 invocation ended `DRY_RUN_READY` with matching baseline evidence IDs and all mutation/result-writer/production-mutation flags false.
- [x] **P9 EXIT GATE:** protocol-compliant clean P9 is proven; `P9_EXIT_GATE=MET` and `CLEAN_P9_REPEAT_REQUIRED=false`.
- [ ] **P10 HARDENED CONTROLLER BOOTSTRAP INSTALLER/STAGER SOURCE / MERGE WAIT:** `ops-workflows#28` remains the selected lowest-risk genuine ordinary candidate, binding `dashboard_RPi5@5f7739348f56398d0ba301c9320e1de0062838fc` to `dashboard-rpi5-production-release`. `RPi5_main#319` is merged and provides the execution-disabled one-shot hardened-controller bootstrap capability. Post-merge read-only audits then proved the installed bootstrap entrypoint/modules and fixed staging root are still absent while the exact preserved candidate/manifest remain available; therefore #28 remains `WAITING_HARDENED_CONTROLLER_BOOTSTRAP_INSTALLER_STAGER_SOURCE`. Current source work is PR #320: a narrow installer/stager bound to exact reviewed RPi5 control source, Dashboard candidate SHA and candidate SHA-256 `c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0`, consuming only the preserved preflight evidence through a descriptor-safe fixed interface, installing only the fixed root-owned bootstrap trust anchor and materializing only the fixed bootstrap staging tree. It grants no generic shell/path/argv authority and may not materialize a production release, change `current`, run P10 PLAN/APPLY, mutate package/service/systemd/Docker/network/credentials, retry, clean up or roll back. Source merge does not authorize LIVE/root use. After #320 merge, exact-main CI/provenance must be refreshed before a separate exact LIVE/root installer/stager authorization. After that bounded transaction, read-only proof must establish the exact installed helper/modules/staging and fresh production baseline before a different separate LIVE/root bootstrap authorization may be considered. Bootstrap success itself is a STOP; only fresh post-bootstrap reconciliation may lead to a new ordinary P10 PLAN authorization. #28 remains WAITING through all of these source/bootstrap gates.
- [ ] Only after the replacement path is proven may any current Hermes Deals self-hosted canary runner/path be retired, and runner retirement itself remains separately owner-authorized.

Do not use this phase to select `chatgpt-codex-connector` for the authorization repository, retry or clean up consumed P9/P10 transactions, change the accepted isolated-auth binding outside a separately reviewed source gate, consume retailer-specific execution authorizations, change parser/corpus state, write DB/Review/publication state, deploy production, mutate Cloudflare, modify repository settings or widen credentials/permissions without the exact separate gate for that action.

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

### Cross-cutting Track X — owner-authorized pull deploy executor v1 — P9 EXIT GATE MET / P10 INSTALLER/STAGER SOURCE

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
P10 Dashboard preflight: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P10_PREFLIGHT.md`.
P10 hardened controller bootstrap: `docs/OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P10_BOOTSTRAP.md`.
P10 installer/stager source operator: `scripts/install-deploy-executor-p10-bootstrap-installer-stager.py`.
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

Current supersession: canonical `RPi5_main#191` proves the clean genuine P9 PASS and the P10 candidate-preparation/classification chain. `RPi5_main#319` is now merged at source checkpoint `56fdbba15510a5f9878d1dd51b51a45755ca5fb2` and provides the execution-disabled one-shot hardened-controller bootstrap capability. The post-merge read-only audit recorded in #191 then proved the installed bootstrap entrypoint/modules and fixed staging root are absent, while the exact preserved Dashboard candidate `5f7739348f56398d0ba301c9320e1de0062838fc` and candidate SHA-256 `c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0` remain available. Therefore `ops-workflows#28` remains WAITING with reason `WAITING_HARDENED_CONTROLLER_BOOTSTRAP_INSTALLER_STAGER_SOURCE`. The current boundary is **P10 INSTALLER/STAGER SOURCE (#320) -> MERGE GATE -> EXACT-MAIN CI/PROVENANCE REVALIDATION -> SEPARATE LIVE/ROOT INSTALLER/STAGER STOP -> READ-ONLY TRUST-ANCHOR/STAGING/PRODUCTION-BASELINE PROOF -> SEPARATE LIVE/ROOT BOOTSTRAP STOP -> FRESH POST-BOOTSTRAP RECONCILIATION -> NEW ORDINARY P10 PLAN GATE**. The installer/stager gate may install only the exact reviewed root-owned bootstrap trust anchor and fixed bootstrap staging tree; it may not materialize a production release, change `current`, execute P10 PLAN/APPLY, retry, clean up or roll back. #28 does not become READY merely because #320 or #319 is merged.

The future transport remains data-only:

`owner-authored isolated LIVE-AUTH -> exact ops-workflows queue/SHA/target/operation/baseline revalidation -> static source-controlled operation registry -> fixed project adapter preflight -> DRY_RUN_READY`.

P9 does not cross the mutation-capable adapter boundary. P10 is the first possible live executor canary and remains separately gated.

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

**#191 / #236 / P10 CANDIDATE #28 — INSTALLER/STAGER SOURCE (#320) -> MERGE GATE -> EXACT-MAIN CI/PROVENANCE -> SEPARATE LIVE/ROOT INSTALLER/STAGER STOP:** P9 is complete, #319 is merged, and the exact Dashboard candidate remains `5f7739348f56398d0ba301c9320e1de0062838fc` with preserved candidate SHA-256 `c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0`. Post-#319 read-only evidence proves the bootstrap trust-anchor files and fixed staging tree are not yet installed. #28 therefore remains WAITING for the dedicated installer/stager source capability.

Finish PR #320 only through focused source review, exact-head CI and Ready. Then STOP for explicit `MERGE RPi5_main #320`. After an owner-authorized merge, freshly require exact-main CI and source/provenance revalidation. Source merge does not authorize the installer/stager live transaction, bootstrap execution, production release materialization or `current` transition.

The next live step, only after that post-merge evidence passes, is a **separate exact LIVE/root installer/stager authorization** bound to the merged RPi5 control SHA, exact Dashboard candidate/digest, exact preserved evidence identity, exact helper/module Git blobs, fixed staging/install destinations and the no-retry/no-cleanup/no-rollback mutation envelope. It may install only the fixed bootstrap trust anchor and fixed staging tree; it must report zero production-release materializations, zero `current` swaps, zero P10 PLAN/APPLY and no package/service/systemd/Docker/network/credential mutation. After that transaction, STOP and perform only read-only proof of installed identities/staging plus a fresh production baseline.

Only if that proof passes may a **different separate LIVE/root bootstrap authorization** be considered. Bootstrap success itself is another STOP. Only fresh post-bootstrap verification may make a new ordinary P10 PLAN authorization eligible. #28 remains WAITING until those gates are satisfied; no P10 APPLY, production deployment, cleanup, runner retirement or unrelated live mutation is authorized by PR #320, its eventual merge, or either source-only gate. Phase 6 Hermes Tech work remains deferred while this #191/#236 executor lane is current.

## Current supersession — P10 post-#321 source state (2026-09-01)

This section is the canonical current-state override for all earlier wording in this file that still describes `RPi5_main#319` or `#320` as an unmerged/current source gate. Those passages are retained only as historical sequencing context and MUST NOT be used as the next-action authority.

Source state at this checkpoint:

- `RPi5_main#320` merged the narrow P10 bootstrap installer/stager source capability;
- `RPi5_main#321` merged the post-merge source/machine-contract reconciliation;
- the post-#321 source checkpoint is `6bfcb577e937f171ae0c69fdddb6b6142b619997`;
- exact-main Validate #772, FAST-LANE #228 and GITHUB-ONLY #216 completed successfully for that checkpoint;
- installer/stager source remains execution-disabled and source merge is not LIVE/root authorization;
- `ops-workflows#28` remains `WAITING`; its current blocker is the separate installer/stager LIVE gate, not missing installer/stager source.

The current queue reason is `WAITING_HARDENED_CONTROLLER_BOOTSTRAP_INSTALLER_STAGER_LIVE_GATE`.

Current gate sequence:

1. before any host mutation, freshly revalidate current `RPi5_main/main`, exact-main CI/provenance, #191/#236/#28 and the trusted-host read-only baseline required by the installer/stager contract;
2. only after those reads pass may the owner issue a **separate exact LIVE/root installer/stager authorization** bound to the exact merged control source, Dashboard candidate/digest, preserved evidence identity, helper/module Git blobs, fixed destinations and fixed mutation budget;
3. that installer/stager transaction may install only the fixed bootstrap trust anchor and materialize only the fixed staging tree; production-release materialization, `current` swap, P10 PLAN/APPLY, package/service/systemd/Docker/network/credential mutation, retry, cleanup and rollback remain excluded;
4. installer/stager completion MUST STOP; fresh read-only proof must establish installed helper/module identities, fixed staging identity and the current production baseline;
5. only after that proof passes may a **different separate exact LIVE/root hardened-controller bootstrap authorization** be considered;
6. bootstrap completion MUST STOP again for fresh post-bootstrap verification and a new ordinary P10 PLAN reconciliation;
7. `ops-workflows#28` remains WAITING through these gates and may become READY only after a valid fresh reviewed P10 PLAN baseline exists. READY never authorizes P10 APPLY.

No merge in the #320/#321 source chain authorizes host/runtime mutation, deployment, bootstrap execution or P10 application APPLY.

## Current supersession — P10 ordinary deployment canary COMPLETE (2026-09-03)

This section supersedes every earlier mutable-state statement in this file that says `P10_EXECUTED=false`, describes `ops-workflows#28` as WAITING/READY for this canary, or treats the Dashboard P10 application APPLY as a future gate. Those passages remain historical sequencing evidence only. GitHub remains canonical for source/queue state, and host/runtime identity must always be freshly revalidated before any later consequential action.

Accepted completion evidence is recorded in canonical `RPi5_main#191`, roadmap `RPi5_main#236`, and the completed queue `ops-workflows#28`:

- source-security work item `RPi5_main#349` is closed/completed and PR #350 merged the root execution-provenance boundary;
- the reviewed RPi5 control source checkpoint for the completed gate chain was `a4ad23274b5e5574b5ad6e1d3fb409f521ae6073`; this SHA is completion evidence, not a durable assertion of future `main`;
- Dashboard PR #258 merged exact candidate source `066b9a24008dd57439f9e66eae198416c4dfc590`, tree `62756ba22fc8d47e44988c086c08dcf37779cfb3`, direct parent `5f7739348f56398d0ba301c9320e1de0062838fc`;
- frozen candidate SHA-256 was `d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9`, with 72 files and 6,773,246 bytes;
- source checkout convergence, candidate-ingress reproof, execution-ingress preparation, root-owned execution-bundle materialization/proof, root-owned handoff materialization/proof, and candidate staging/proof all passed under separately bounded one-shot gates;
- trusted-controller PLAN-only then passed with observed current `5f7739348f56398d0ba301c9320e1de0062838fc`, target `066b9a24008dd57439f9e66eae198416c4dfc590` absent, and exact planned operations `copy_manifest_allowlisted_release`, `write_verified_manifest_marker`, `atomic_current_symlink_swap`; its postcheck proved no production mutation;
- after separate exact owner authorization, P10 application APPLY returned `status=APPLIED`, previous release `5f7739348f56398d0ba301c9320e1de0062838fc`, current release `066b9a24008dd57439f9e66eae198416c4dfc590`, exact candidate SHA-256 `d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9`, and `releasesDeleted=0`;
- read-only post-APPLY proof showed target `verified-existing`, observed current `066b9a24008dd57439f9e66eae198416c4dfc590`, `operations=[]`, and successful apply-lock cleanup;
- no retry, rollback, destructive cleanup, alternate path, credential/permission mutation, package/service/systemd/Docker/network/Cloudflare/DB mutation, or undeclared release deletion occurred;
- `ops-workflows#28` is closed/completed with the sanitized completion receipt;
- every one-time LIVE authorization consumed during this chain is non-reusable.

Binding classification after this canary:

`P9_EXIT_GATE=MET`
`P10_EXIT_GATE=MET`
`P10_EXECUTED=true`
`P10_CANARY_QUEUE_28=COMPLETED`
`P10_CANARY_REUSABLE_LIVE_AUTH=false`

P10 completion proves this reviewed ordinary Dashboard release path can cross its bounded production mutation boundary under explicit owner authorization. It does not grant generic executor authority, does not make high-risk/control-plane P11 operations ordinary, does not authorize another deployment, and does not authorize retirement of any runner/path.

### Current Phase 4 next action after P10

Phase 4 remains the current program phase until its residual Hermes Deals execution paths are reconciled. Do **not** jump directly to P11 merely because the P10 ordinary canary passed.

After this source-only plan reconciliation is merged and exact-main CI is freshly green:

1. re-read current `RPi5_main/main`, this master plan, canonical #191, roadmap #236, and the closed `ops-workflows#28` completion record;
2. fresh-read current Hermes Deals governance and only the exact residual self-hosted canary/runner/audit/release paths that Phase 4 still needs to retire or migrate; do not infer current runner/runtime state from this document or old receipts;
3. perform a **read-only/source-only residual-path retirement-readiness audit** and identify one exact next Phase 4 work item;
4. if source changes are required, use the normal focused branch -> PR -> CI/review -> Ready flow;
5. if a runner/path retirement or any other host/runtime mutation becomes eligible, STOP for a new exact owner LIVE authorization. `turpini`, P10 success, this document, and the closed queue do not authorize retirement or any other live mutation.

P11 high-risk/control-plane operation work remains pending behind completion of the current Phase 4 residual-path decision. Any future P11 adapter/root operation requires its own reviewed source contract and separate STRICT owner authorization; it cannot inherit the ordinary P10 canary envelope.

## Current supersession — Hermes origin privileged dispatcher source gate (2026-09-04)

This section supersedes the prior generic Phase 4 residual-path next-action wording above. Historical P9/P10 sequencing remains evidence only; it is not current execution authority.

Fresh source state at `RPi5_main#361` activation:

- `RPi5_main/main = 68a6246171af014dac79711ebc510ddbc6c3d31a`;
- `hermes-deals/main = 2f47f64ab15e767f4e53ad182326e64e313d5094`;
- `RPi5_main#352` / PR #353 completed dormant Hermes production-registry registration while global `execution_enabled=false` remained authoritative;
- `RPi5_main#354` / PR #355 completed the identity-only request carrying only `schema` + `authorization_issue_number`;
- `RPi5_main#356` / PR #357 completed the double-canonical-revalidation privileged consumer, still without an execution surface;
- `hermes-deals#834` / PR #840 completed the runner-independent capability-specific pull helper;
- `RPi5_main#359` / PR #360 completed exact pull-helper provenance/interface and sanitized host-evidence binding;
- `RPi5_main#361` / Draft PR #362 is the current source-only gate for the capability-specific privileged dispatcher plan.

The #361 source gate must derive `registered_source_sha` only from the fully revalidated canonical Hermes source evidence and derive helper `as_of` only from the UTC calendar date of the already validated GitHub server-side owner authorization `created_at`. Neither value is caller authority. The caller still supplies only `authorization_issue_number`.

The reviewed helper remains fixed to capability `origin-path-audit`, source blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`, installed identity `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`, and exactly two argument names `registered_source_sha`, `as_of`. The dispatcher source may emit an immutable capability plan only; it must not expose a generic shell/subprocess/sudo/path/argv/environment execution primitive and must not launch the helper in this gate.

Binding classification for the current gate:

`PHASE4_CURRENT_WORK_ITEM=RPi5_main#361`
`P9_EXIT_GATE=MET`
`P10_EXIT_GATE=MET`
`GLOBAL_EXECUTION_ENABLED=false`
`PRIVILEGED_DISPATCH_SOURCE_GATE=IN_PROGRESS`
`PRIVILEGED_DISPATCH_ENABLED=false`
`HOST_WIRING_ENABLED=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

Current gate sequence:

1. finish #361 / PR #362 through focused source review, exact-head CI and Ready, then STOP for a separate explicit owner `MERGE RPi5_main #362` decision;
2. after any separately authorized merge, freshly require exact-main CI and provenance/interface revalidation; merge still proves source readiness only;
3. define and review a separate source/host installation-wiring security gate for the exact broker/helper/service/permission boundary and cross-repository producer/consumer contract;
4. only after that gate may a separate explicit LIVE authorization install or activate the exact reviewed capability-specific host components;
5. a later separate STRICT authorization is required for exactly one genuine read-only Hermes origin audit canary with sanitized postconditions;
6. runner/path retirement is eligible only after the replacement path is proven end-to-end and remains a separate owner-authorized LIVE mutation.

Neither P10 completion, #361 source readiness, source merge, `START`, `turpini`, nor ordinary AUTO-RUN continuation authorizes helper execution, host wiring, systemd/sudoers/user/group/permission mutation, READY/LIVE-AUTH creation, runner retirement, deployment, DB/application-data writes, credential/App permission changes, Cloudflare/network/container/runtime mutation, retry, cleanup or rollback.

## Current supersession — Hermes privileged broker installation/wiring security gate (2026-09-04)

This section supersedes the #361 current-gate wording immediately above. The #361 section remains historical source evidence only; **this final section is the current Phase 4 next-action authority**.

Fresh source state at `RPi5_main#363` creation:

- `RPi5_main/main = 8c157f0f6caf6258ebab7765a9b9ec2934070964`;
- #361 is closed/completed and PR #362 merged to that exact main SHA;
- exact-main Validate #814, FAST-LANE #270 and GITHUB-ONLY #258 are SUCCESS;
- `hermes-deals/main = 2f47f64ab15e767f4e53ad182326e64e313d5094`;
- Hermes Deals CI #1775 and GITHUB-ONLY #101 are SUCCESS;
- reviewed runner-independent helper blob remains `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- current source work item is `RPi5_main#363` / Draft PR #364.

#363 proves the **source contract** for a capability-specific broker installation/wiring boundary while deliberately keeping the actual mutation path absent. The new broker transport accepts exactly one bounded identity-only UNIX-socket frame carrying only `authorization_issue_number`; it calls the already-reviewed dispatcher preparation path itself and cannot accept caller-selected source SHA, `as_of`, capability, executable/path, argv, environment, UID/GID, unit, command, output path or a prebuilt dispatch plan.

The source-only host transport is fixed to:

- socket unit `rozkalns-hermes-deals-origin-broker.socket`;
- socket path `/run/rozkalns-hermes-deals-origin-broker/request.sock`;
- socket `root:rozkalns-deploy-executor` mode `0660`, `Accept=yes`, `MaxConnections=1`;
- per-connection root service `rozkalns-hermes-deals-origin-broker@.service`;
- fixed broker path `/usr/local/libexec/rozkalns-hermes-deals-origin-broker`;
- existing poller `rozkalns-deploy-executor.service` unchanged with `NoNewPrivileges=true` and no generic sudo/root/Docker-socket authority;
- generic `ops/bin/rozkalns-deploy-dispatch` still `DISABLED`.

`ops/deploy/hermes-deals-origin-broker-installation.json` freezes the intended broker/module/unit/helper/registration/probe/evidence/credential paths and owner/group/mode posture. It deliberately records `eligible_source_sha=null`, `POST_MERGE_EXACT_MAIN_BIND_REQUIRED` and `live_install_eligible=false`; it is evidence, not an installer or LIVE authorization.

The source-read boundary remains deliberately fail-closed. Phase 2 historically proved the read-only `Rozkalns Automation` App contract included `hermes-deals`, but that historical evidence is **not current host credential/runtime proof**. The currently concrete privileged `p9_source_auth.py` provider is source-allowlisted only for `rozkalns-control-center`; #363 neither broadens that provider nor mutates any App installation, permission or credential. The broker entrypoint therefore returns `SOURCE_AUTHORITY_UNPROVEN`, and no helper process-launch implementation is present.

Binding classification for the current gate:

`PHASE4_CURRENT_WORK_ITEM=RPi5_main#363`
`P9_EXIT_GATE=MET`
`P10_EXIT_GATE=MET`
`GLOBAL_EXECUTION_ENABLED=false`
`BROKER_BOUNDARY_IMPLEMENTED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`
`HELPER_PROCESS_LAUNCH_IMPLEMENTED=false`
`PRIVILEGED_DISPATCH_ENABLED=false`
`HOST_WIRING_ENABLED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

Current gate sequence:

1. finish #363 / PR #364 through focused source review, exact-head CI and Ready, then STOP for a separate explicit owner `MERGE RPi5_main #364` decision;
2. after any separately authorized merge, freshly require exact-main CI and bind the exact merged RPi5 source identity; merge still proves source readiness only;
3. open a **new source prerequisite gate** that composes exact authenticated Hermes GitHub source/Actions read authority from the reviewed read-only App contract without implicit permission widening, and implements/reviews the exact bounded fixed-helper launch surface while every live flag remains false;
4. merge that prerequisite only under a separate owner MERGE decision and again require fresh exact-main/cross-repository compatibility evidence;
5. only then may a separate explicit LIVE authorization install/activate the exact reviewed broker/helper/socket/service/credential boundary on the host;
6. a later separate STRICT authorization is required for exactly one genuine read-only Hermes origin audit canary;
7. runner/path retirement is eligible only after the replacement path is proven end-to-end and remains a separate owner-authorized LIVE mutation.

Neither #363 source readiness, PR #364, any later source merge, historical Phase 2 App proof, `START`, `SYNC`, `turpini`, nor AUTO-RUN continuation authorizes helper execution, credential/App permission change, host file placement, chmod/chown, systemd socket/service install/enable/start, sudoers/user/group mutation, READY/LIVE-AUTH creation, runner retirement, deployment, DB/application-data writes, Cloudflare/network/container/runtime mutation, retry, cleanup or rollback.


## Current supersession — Hermes source auth + bounded helper launch gate (2026-09-04)

This section supersedes the #363 current-gate wording above. The #361/#363 sections remain historical source evidence only; **this final section is the current Phase 4 next-action authority**.

Fresh source state at `RPi5_main#365` creation:

- `RPi5_main/main = 9c60248547043ee5ae7b1d0e2897fd9b8aac381a`;
- #363 is closed/completed and PR #364 merged to that exact main SHA;
- exact-main Validate #820, FAST-LANE #276 and GITHUB-ONLY #264 are SUCCESS;
- current `hermes-deals/main = 511c1566111983f809bc958bc4b68510771d3efb`;
- the current Hermes head is a verified docs-only bot commit whose parent is `2f47f64ab15e767f4e53ad182326e64e313d5094`;
- the reviewed runner-independent helper blob remains exact `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673` on current Hermes main;
- current source work item is `RPi5_main#365` / Draft PR #366.

#365 reuses the existing read-only Source App provider rather than creating a broader authentication mechanism. It source-binds `rozkalnsandris/hermes-deals` / repository ID `1317143994` to App ID `4537106`, installation ID `152422751`, selected-repository posture, a one-repository installation token and exactly `Actions:read + Contents:read`. No GitHub App installation, selected repository, permission, private key or credential is changed by this source gate.

#365 also adds a separately source-reviewed one-shot helper launch abstraction. It first calls the existing `prepare_hermes_deals_origin_privileged_dispatch()` path, preserving the identity-only request and mandatory double canonical revalidation, and then fixes the process boundary to:

- executable `/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch`;
- helper blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673`;
- exactly two canonical arguments `registered_source_sha`, `as_of`;
- `shell=False`;
- a fixed minimal environment;
- 50-second timeout;
- 4096-byte stdout and stderr limits;
- one invocation budget;
- accepted exit codes only `0`, `1`, `2`;
- exact validated helper stdout with explicit false production DB/deployment/restart flags.

CI uses a fake runner seam. No real helper/audit process is executed by this source gate.

Demand-driven inspection during #365 found an additional prerequisite: `CanonicalHermesOriginRevalidator` and `SanitizedHermesOriginHostEvidenceResolver` are still Protocol/test seams, not concrete production Hermes compositions. Consequently the broker entrypoint remains inert and #365 does not wire the fixed launcher into a live-capable path.

Binding classification for the current gate:

`PHASE4_CURRENT_WORK_ITEM=RPi5_main#365`
`P9_EXIT_GATE=MET`
`P10_EXIT_GATE=MET`
`GLOBAL_EXECUTION_ENABLED=false`
`SOURCE_AUTH_COMPOSITION_IMPLEMENTED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`
`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=false`
`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`
`HELPER_PROCESS_LAUNCH_WIRED=false`
`PRIVILEGED_DISPATCH_ENABLED=false`
`HOST_WIRING_ENABLED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

Current gate sequence:
1. finish #365 / PR #366 through focused source review, exact-head CI and Ready, then STOP for a separate explicit owner `MERGE RPi5_main #366` decision;
2. after any separately authorized merge, freshly require exact-main CI and cross-repository helper provenance;
3. open a **separate source integration gate** that implements/reviews the concrete canonical Hermes revalidator and sanitized host-evidence resolver, then binds those components to the broker entrypoint without expanding caller authority;
4. merge that integration gate only under a separate owner MERGE decision and again require fresh exact-main/cross-repository evidence plus a read-only runtime preflight for the expected App installation/credential/helper/unit identities;
5. only if every source and runtime prerequisite passes may a separate explicit LIVE authorization install/activate the exact reviewed host components;
6. a later separate STRICT authorization is required for exactly one genuine read-only Hermes origin audit canary;
7. runner/path retirement is eligible only after the replacement path is proven end-to-end and remains a separate owner-authorized LIVE mutation.

Neither #365 source readiness, PR #366, either source merge, historical Phase 2 App proof, `START`, `SYNC`, `turpini`, nor AUTO-RUN continuation authorizes App/credential mutation, broker/helper execution, host file placement, chmod/chown, systemd installation/enable/start, user/group/sudoers changes, READY/LIVE-AUTH creation, runner retirement, deployment, DB/application-data writes, Cloudflare/network/container/runtime mutation, retry, cleanup or rollback.


## Current supersession — Hermes canonical source-integration gate (2026-09-04)

This section supersedes the #365 next-action wording above. All earlier Phase 4 sections remain historical evidence only; **this final section is the current Phase 4 source authority**.

Fresh source evidence for this gate:

- `RPi5_main/main = 13c0c46e9966b0682b53553a92bed510cf491c86` at branch creation;
- GitHub reports #365 completed and PR #366 merged at that exact main SHA on 2026-09-04;
- `hermes-deals/main = 511c1566111983f809bc958bc4b68510771d3efb`;
- `tools/runner/origin_path_rpi5_pull_helper.py` remains blob `51bb23cc6c2083ab7c8b4e81ba82dd880e46d673` on that Hermes main;
- this source-integration patch is not merged, so no post-integration eligible `RPi5_main` SHA or runtime claim exists yet.

The source integration introduces three capability-specific components without widening caller authority:

1. `ConcreteCanonicalHermesOriginRevalidator` accepts only `authorization_issue_number` at its request boundary and reconstructs the owner-authored LIVE-AUTH, READY queue, disabled static registry, exact Hermes repository ancestry/CI and adapter provenance from the existing reviewed read-only clients. The Hermes source client must be the existing single-repository Source App provider fixed to repository ID `1317143994`, App ID `4537106`, installation ID `152422751` and exactly `Actions:read + Contents:read`. GitHub response timestamps must be canonical, monotonic and mutually consistent.
2. `ConcreteSanitizedHermesOriginHostEvidenceResolver` accepts no path, command, environment, unit, identity or capability selector. A later privileged adapter may provide one bounded raw observation with fixed source-known registration, broker, socket, service, credential-location, helper, probe, dispatcher and workflow identities. The resolver rejects duplicate/extra fields, stale/future timestamps, secret-like material, identity drift and every positive mutation/authority flag, then emits only the minimal existing consumer evidence.
3. `HermesDealsOriginBrokerComposition` binds those exact concrete types to the existing fixed one-shot launcher. The installed broker entrypoint does not construct it, and the composition has no default real runner. CI supplies a fake runner only. The fixed helper executable, two arguments, `shell=False`, minimal environment, timeout, output bounds and one-invocation limit remain unchanged.

The canonical evidence now distinguishes a validated source-side baseline **contract** from actual host state. Repository source does not claim that any registration, credential, helper, unit or App installation exists on the RPi5. Durable replay availability and the future sanitized host observation provider remain runtime adapters that must be proven during a separate read-only preflight before any entrypoint wiring or LIVE decision.

Binding classification for the current source patch:

`PHASE4_CURRENT_WORK_ITEM=HERMES_CANONICAL_SOURCE_INTEGRATION_DRAFT`
`P9_EXIT_GATE=MET`
`P10_EXIT_GATE=MET`
`GLOBAL_EXECUTION_ENABLED=false`
`SOURCE_AUTH_COMPOSITION_IMPLEMENTED=true`
`SOURCE_READ_AUTHORITY_PROVEN=false`
`CONCRETE_CANONICAL_REVALIDATOR_IMPLEMENTED=true`
`SANITIZED_HOST_EVIDENCE_RESOLVER_IMPLEMENTED=true`
`BROKER_COMPOSITION_IMPLEMENTED=true`
`BROKER_ENTRYPOINT_WIRED=false`
`HELPER_PROCESS_LAUNCH_IMPLEMENTED=true`
`HELPER_PROCESS_LAUNCH_WIRED=false`
`PRIVILEGED_DISPATCH_ENABLED=false`
`HOST_WIRING_ENABLED=false`
`LIVE_INSTALL_ELIGIBLE=false`
`GENUINE_HERMES_AUDIT_AUTHORIZED=false`
`RUNNER_RETIREMENT_ELIGIBLE=false`
`PRODUCTION_MUTATION_STARTED=false`

Current gate sequence:

1. complete focused source review, exact-head CI and Draft PR readiness for this integration patch;
2. STOP for a separate explicit owner MERGE decision;
3. after merge, freshly bind the exact merged `RPi5_main/main`, exact-main CI and current Hermes helper provenance;
4. perform a separate read-only runtime preflight for the expected App installation, credential metadata, replay store, registration, broker, helper, socket and service identities without reading credential content;
5. only if every source and runtime prerequisite passes may a separate explicit LIVE authorization install/activate the exact reviewed host components;
6. a later separate STRICT authorization is required for exactly one genuine read-only Hermes origin audit canary;
7. runner/path retirement is eligible only after the replacement path is proven end-to-end and remains a separate owner-authorized LIVE mutation.

Neither this source patch, its Draft PR, a later source merge, #365/#366, historical App proof, nor any continuation command authorizes credential/App mutation, host inspection, broker/helper execution, host file placement, systemd action, READY/LIVE-AUTH creation, deployment, application/database mutation, runner retirement, retry, cleanup or rollback.
