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
- [x] Add and CI-prove the narrow issue #140 `AUTO_DEPLOY_SAFE` execution boundary in the local CV controller: only exact `READY` + successful exact-SHA CI + `CONTROL_PLANE_CHANGED=false` may cross the root-owned pull-helper boundary; manual/DB/no-deploy/wait/failure states remain non-mutating. This remains source-only until the cross-repository evidence-directory contract blocker below is fixed and regression-proven.
- [x] Fix and CI-prove the CV #144 pull rollback/pre-mutation source behavior, including explicit prerequisite-failure propagation in Bash conditional context; install the exact wrapper and pass the non-destructive prerequisite/legacy-baseline regression checks with production, legacy helper/rule and CV pull timer unchanged.
- [x] Install and host-prove the RPi5_main #141 generic-maintenance Compose boundary without running the weekly updater; prove `cvbot` is buildable/local-only, excluded from generic recreation, and preserve CV production state, legacy helper and timer states.
- [x] Fix the CVBot build-input identity so every current Dockerfile `COPY` input is covered; CV PR #150 merged as `f5431265232f356fa27f6204f0cba56e1e730928` with full PR-head CI run `31373969253` PASS.
- [x] Recover CV through the existing project-owned explicit manual canary/pull deploy to exact current `rozkalns-cv/main=f5431265232f356fa27f6204f0cba56e1e730928`; exact-main CI `31374125068` PASS, `MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=false`, transaction committed, rollback not performed, transactional public contracts PASS, readiness reconciled `CURRENT`, legacy helper unchanged, and CV pull timer remained disabled/inactive. CV #144 and #149 completed after this healthy recovery evidence.
- [x] Fix and regression-prove the cross-repository #140 evidence-directory contract before installing or executing the reviewed controller path. RPi5_main PR #157 merged as `d1437461126e4118f20cd503135aa9b190bb4b09`, changing only the less-privileged controller producer to the existing bounded `rozkalns-cv-main-deploy-*` namespace while leaving the CV root wrapper allow-pattern unchanged; the first PR CI attempt correctly failed on a shell parse regression and the corrected PR head passed full CI. Follow-up PR #158 merged as `ff53db3d143ecd162c72cc51888aed73158d8528`, pinning the reviewed CV pull-wrapper blob and proving the allow-pattern from exact `EXPECTED_CV_SHA:path` Git object before and after host installation proof.
- [x] Install and host-prove the reviewed #140 controller/readiness artifacts with the recurring timer still disabled/inactive. The first reviewed attempt failed closed before installation because the activation operator misread the existing #141 `no-image-change-no-recreate` contract; PR #160 corrected only that operator predicate. The exact retry on `RPi5_main/main=72ef9d986914c125c5d27bcc2866f989f47fb8d9` passed exact-main CI `31468652385`, exact CV reconciliation/CI, controller↔wrapper contract, #141 maintenance recheck with `CVBOT_GENERIC_RECREATE_AUTHORIZED=false`, artifact installation, `POST_INSTALL_PREFLIGHT=NO_OP_ALREADY_CURRENT`, healthy local/public runtime, unchanged production/legacy/sudo boundaries, inactive controller service, and recurring timer still disabled/inactive with `PRODUCTION_MUTATION_ATTEMPTED=false`.
- [x] Complete/reconcile CV issue #151 and fail closed for runtime prerequisite/config/readiness boundaries. CV PR #152 merged as `4a0069a97022841da07a687a197ea8cfacc56cd6`: the broad `bot/` `AUTO_DEPLOY_SAFE` prefix was removed, audited executable/runtime `bot/*.py` paths are explicit `MANUAL_ROLLOUT_REQUIRED`, `bot/data/` remains `DB_HOST_APPLY_REQUIRED`, unknown new `bot/` paths fail closed to manual review, and only the explicit content-only `bot/system_prompt.txt` exception remains auto-deployable.
- [x] Reconcile the CV #152 control-plane baseline through RPi5_main issue #163 before any `AUTO_DEPLOY_SAFE` execution canary. The separately authorized classifier host alignment installed/proved exact classifier blob `7fb09d469eaeb574b2bba39474cc7a6bb55504da` while production remained on `f5431265232f356fa27f6204f0cba56e1e730928`; the separately authorized manual production canary then advanced production exactly to current CV baseline `4a0069a97022841da07a687a197ea8cfacc56cd6`. Both gates preserved the recurring timer disabled/inactive and legacy runner/helper boundaries; issue #163 closed completed.
- [ ] After #163 classifier and production baseline reconciliation is green, wait for a genuinely newer exact-current-main CV delta that independently classifies `AUTO_DEPLOY_SAFE`, then run one separately authorized one-shot controller execution canary. Do not fabricate a same-SHA mutation target or weaken classification for `NO_DEPLOY`, manual, DB/host, wait or failure states. Require fresh exact-current-main/CI/pull-artifact revalidation, transactional public-contract evidence, post-deploy `CURRENT`, and the legacy runner unchanged.
- [ ] Enable the recurring local controller only after the rollback regression gate, healthy recovery prerequisite, cross-repository evidence contract gate, #151 classifier runtime-contract audit, #163 classifier/production baseline reconciliation, and one-shot `AUTO_DEPLOY_SAFE` execution canary are green.
- [ ] Disable/remove the public-repo self-hosted release runner only after the replacement execution path, rollback regression gate, healthy recovery prerequisite and public verification are green.

Phase 3 evidence through 2026-08-11:

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
- first explicit production-canary invocation at 23:28 local failed before transaction commit on the new CVBot pseudonymization-secret prerequisite and exposed a rollback regression: `DEPLOY_RESULT=FAIL_ROLLBACK_FAIL`, `FINAL_STATE_SHA=0149bed2b84803f6fd8c191920191730c7a887cb`, `TRANSACTION_COMMITTED=false`, `ROLLBACK_PERFORMED=true`;
- protected production `bot/.env` was subsequently corrected without exposing either secret; file metadata changed at 23:32:38 local and later sanitized validation returned `CLIENT_KEY_SECRET_STATUS=PASS`;
- replacement production canary PASS at `2026-08-09T21:34:03Z` on the second explicit manual invocation: approved/target SHA `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, previous production `0149bed2b84803f6fd8c191920191730c7a887cb`, exact-main CI `31336104950`, `DEPLOY_IMPACT=MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=true`, `DEPLOY_RESULT=PASS`, `PRODUCTION_CHANGED=true`, `MUTATION_STARTED=true`, `TRANSACTION_COMMITTED=true`, `ROLLBACK_PERFORMED=false`, `SHARED_INGRESS_CONTROLLED=false`, `DATABASE_MIGRATIONS_EXECUTED=false`;
- production-canary postconditions PASS: final production state `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, `TRANSACTIONAL_PUBLIC_CONTRACTS=PASS`, `READINESS_RECONCILIATION=CURRENT`, legacy helper unchanged, recurring timer remained `disabled/inactive`, evidence ID `rozkalns-cv-main-deploy-canary-6f13986c27d2.HIm0dR8B`, and `LEGACY_RUNNER_RETIREMENT_AUTHORIZED=false`;
- provenance audit: both production-canary sudo invocations were explicit `andris` calls from `TTY=pts/0`; no `rozkalns-cv-pull-deploy.service/.timer` activity occurred, so the successful canary was not recurring automation;
- CV #144 source hardening: PR #147 merged as `cf9d439ff832f15fd12a8f1f876100640440addf`; follow-up conditional-context fix PR #148 merged as `8afead7cae3f36882abca1b519af5bdc138978ce`; exact wrapper blob `ddaa8c7f8c0776e77be18b2cd5ea8a9489900e70`; exact-main CV CI `31368863144` PASS;
- CV #144 installed synthetic regression evidence: `INSTALLED_PREMUTATION_ORDER=PASS`, `INSTALLED_EXPLICIT_FAILURE_PROPAGATION=PASS`, `CONDITIONAL_CONTEXT_FAILURE_PROPAGATION=PASS`, invalid-target prerequisite rejection PASS, legacy-baseline compatibility PASS, valid-target strict validation PASS, invalid-current secret rejection PASS, production unchanged at `6f13986c27d2c32c2fbcdbdbb1912bf163b8af88`, legacy helper/rule unchanged, recurring CV pull timer still `disabled/inactive`;
- RPi5_main #141 source fix PR #148 merged as `f44aab15b8291dc27ea2a2b98cc52098e683bee9`; helper-only activation operator PR #150 merged as `58c22cf3501b782ef678d0614062c4e7a78016ef`; exact operator blob `5fb3159f2b6799249f8fdefb9b28d48f5328961f`, Compose-policy blob `e7ee5074767c309e699503345422de42d6aba913`;
- #141 helper-only host gate PASS on `58c22cf3501b782ef678d0614062c4e7a78016ef` with exact-main CI run `31372705385`: `CVBOT_CLASSIFICATION=buildable-local`, `CVBOT_GENERIC_RECREATE_AUTHORIZED=false`, `COMPOSE_POLICY_MODE=no-image-change-no-recreate`; weekly updater not executed, production unchanged, legacy CV helper unchanged, CV pull timer remained disabled/inactive;
- CV recovery preparation then found incomplete CVBot image build-input identity in issue #149; source fix PR #150 merged as current CV main `f5431265232f356fa27f6204f0cba56e1e730928`, PR-head CI `31373969253` PASS including real image identity build/OCI label verification and Trivy; every current Dockerfile `COPY` input is now covered by the deterministic identity regression;
- final project-owned recovery canary PASS at `2026-08-10T20:23:15Z`: target/current CV main `f5431265232f356fa27f6204f0cba56e1e730928`, production before `8afead7cae3f36882abca1b519af5bdc138978ce`, exact-main CI `31374125068`, `DEPLOY_IMPACT=MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=false`, `DEPLOY_RESULT=PASS`, `FINAL_STATE_SHA=f5431265232f356fa27f6204f0cba56e1e730928`, `MUTATION_STARTED=true`, `TRANSACTION_COMMITTED=true`, `ROLLBACK_PERFORMED=false`, `TRANSACTIONAL_PUBLIC_CONTRACTS=PASS`, `READINESS_RECONCILIATION=CURRENT`, legacy helper unchanged, recurring CV pull timer remained disabled/inactive, evidence ID `rozkalns-cv-main-deploy-canary-f5431265232f.WtUg6Aao`, and `LEGACY_RUNNER_RETIREMENT_AUTHORIZED=false`; CV #144 and #149 are completed;
- #140 host-activation operator source merged on RPi5_main as `321ff3bc593d1d2dc074c59a4f76340bb807811a`, adding `ops/bin/rozkalns-cv-controller-activate` plus focused tests. This source merge does not authorize or prove host activation and must not be run while the evidence-directory contract blocker below remains open;
- 2026-08-10 end-to-end audit found a P1 cross-repository contract mismatch not covered by the repository-local green CI suites: RPi5 controller blob `b3599d308f10f432af09faaf7a5af28c07a2cdd5` creates `$EVIDENCE_ROOT/rozkalns-cv-auto-deploy-${TARGET_SHA:0:12}.XXXXXXXX`, while CV pull-wrapper blob `ddaa8c7f8c0776e77be18b2cd5ea8a9489900e70` accepts evidence only under `$PULL_EVIDENCE_ROOT/rozkalns-cv-main-deploy-*`. A real `READY`/`AUTO_DEPLOY_SAFE` execution would therefore fail closed in the root wrapper before production mutation. The safe fix is to preserve the wrapper path-bound restriction, correct the controller producer contract, and add a cross-repository regression so this interface cannot drift silently again;
- #140 evidence-contract repair: RPi5_main PR #157 merged as `d1437461126e4118f20cd503135aa9b190bb4b09`; its first CI run failed closed on a real Bash quote/syntax regression, the corrected head passed full Validate/Gitleaks/shared-policy CI, and the merged controller now creates `rozkalns-cv-main-deploy-auto-*` evidence while the CV root wrapper's bounded `rozkalns-cv-main-deploy-*` allow-pattern remains unchanged;
- exact-object follow-up: RPi5_main PR #158 merged as `ff53db3d143ecd162c72cc51888aed73158d8528`, full PR-head CI run `31435636372` PASS; the #140 host-activation operator now pins CV pull-wrapper blob `ddaa8c7f8c0776e77be18b2cd5ea8a9489900e70`, resolves it from exact `f5431265232f356fa27f6204f0cba56e1e730928:path`, reads the allow-pattern from that exact Git object instead of detached-worktree filesystem state, and rechecks the contract after installation proof;
- #140 maintenance recheck correction: the first host-install attempt passed exact RPi5/CV CI and cross-repo identity gates but failed closed before installation because the operator rejected `cvbot` even under the reviewed #141 `no-image-change-no-recreate` mode. PR #160 merged as `72ef9d986914c125c5d27bcc2866f989f47fb8d9` with full PR-head CI `31468513235` PASS, preserving the #141 helper and making the activation proof mode-aware;
- #140 reviewed host-install retry PASS on exact `RPi5_main/main=72ef9d986914c125c5d27bcc2866f989f47fb8d9`: exact-main CI `31468652385`, CV exact-main CI `31374125068`, production/main reconciliation PASS at `f5431265232f356fa27f6204f0cba56e1e730928`, controller↔wrapper evidence contract PASS, `CVBOT_GENERIC_RECREATE_AUTHORIZED=false`, maintenance mode `no-image-change-no-recreate`, runtime health PASS, controller/readiness artifact install PASS, post-install preflight `NO_OP_ALREADY_CURRENT`, production unchanged, cvbot healthy, local/public site PASS, legacy helper/rules and pull sudo rule unchanged, CV pull timer disabled/inactive, controller service inactive, and `PRODUCTION_MUTATION_ATTEMPTED=false`;
- CV #151 classifier runtime-contract audit completed in PR #152, merged as current CV main `4a0069a97022841da07a687a197ea8cfacc56cd6`; broad `bot/` auto classification is removed, audited runtime paths are explicit manual rollout, unknown `bot/` paths fail closed, and `bot/system_prompt.txt` is the narrow content-only auto exception;
- RPi5_main issue #163 source gate merged in PR #164 as `73879f4821791d938349e9f79f44ce1a0bd55ab0`; it pins old classifier blob `e9020c00328122a1a028c9734002f0ea1c956f2f`, target classifier blob `7fb09d469eaeb574b2bba39474cc7a6bb55504da`, exact CV target `4a0069a97022841da07a687a197ea8cfacc56cd6`, rollback-on-proof-failure, timer/service/legacy/pull-transport invariants and post-install `MANUAL_ROLLOUT_REQUIRED`/`CONTROL_PLANE_CHANGED=true`/mutation=false. PR-head Validate run `31482148993` PASS;
- #163 classifier host-alignment PASS on exact `RPi5_main/main=49c50fa17b7e186a7d16a1aa352de2c6a5c7ea9d` with exact-main CI `31484347810` and exact `rozkalns-cv/main=4a0069a97022841da07a687a197ea8cfacc56cd6` with CI `31470749336`: classifier blob `7fb09d469eaeb574b2bba39474cc7a6bb55504da` installed/proven, post-alignment preflight `MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=true`, production unchanged during this gate, timer disabled/inactive, service inactive, cvbot healthy, local/public site PASS, legacy helper and pull transport unchanged;
- #163 separately authorized manual production-alignment canary PASS at `2026-08-11T20:37:35Z`: production advanced exactly `f5431265232f356fa27f6204f0cba56e1e730928` → `4a0069a97022841da07a687a197ea8cfacc56cd6`, exact CV CI `31470749336`, `DEPLOY_IMPACT=MANUAL_ROLLOUT_REQUIRED`, `CONTROL_PLANE_CHANGED=true`, `DEPLOY_RESULT=PASS`, `TRANSACTION_COMMITTED=true`, `ROLLBACK_PERFORMED=false`, `SHARED_INGRESS_CONTROLLED=false`, `DATABASE_MIGRATIONS_EXECUTED=false`, `TRANSACTIONAL_PUBLIC_CONTRACTS=PASS`, `READINESS_RECONCILIATION=CURRENT`, legacy helper unchanged, recurring timer remained disabled/inactive, evidence ID `rozkalns-cv-main-deploy-canary-4a0069a97022.NBmr997m`; issue #163 closed completed;
- self-audit process rule persisted in tracker #103: before every host activation gate, audit all cross-repository producer/consumer interfaces used by the host path; repository-local green CI alone is insufficient evidence of interface compatibility;
- pre-activation audit blocker #140 originally identified that readiness-only controller blob `bc0b338f0ec776f1ea607758c7d95de676fa69fe` mapped `READY` to `AUTO_DEPLOY_READY` but never invoked `/usr/local/sbin/rozkalns-cv-pull-deploy-main`; timer blob `75ad7b3c0565b2c8a3e6a73600ce38265520199b` therefore remained disabled/inactive while the execution boundary was added and reviewed.

The replacement production canary intentionally retained `MANUAL_ROLLOUT_REQUIRED` because the pre-deploy production-to-target range contained `runner/`/control-plane changes. The canary completed through the explicit manual boundary and production advanced under that approved target. No reclassification to `AUTO_DEPLOY_SAFE` was used.

The #140 execution boundary does not weaken that rule. It may invoke the dedicated root-owned pull wrapper only after the App-authenticated preflight returns exact `READY` for `AUTO_DEPLOY_SAFE`, reports `CONTROL_PLANE_CHANGED=false`, exposes valid exact-SHA CI and pull-artifact identities, and passes a second identical preflight immediately before mutation. The CV wrapper itself still fresh-fetches and rejects any target that is no longer exact current `origin/main`. All manual, DB/host, no-deploy, wait and preflight-failure states remain non-mutating.

The #144 rollback/pre-mutation and health-recovery gate, #151 classifier runtime-contract audit, and #163 classifier/production baseline reconciliation are complete. CV production and the installed classifier are reconciled to exact `4a0069a97022841da07a687a197ea8cfacc56cd6`, readiness is `CURRENT`, transactional public checks passed, and the recurring CV pull timer remains disabled/inactive. The first incomplete Phase 3 gate is now to wait for a genuinely newer exact-current-main CV delta that independently classifies `AUTO_DEPLOY_SAFE` with `CONTROL_PLANE_CHANGED=false`; only then may the separately authorized #140 one-shot controller execution canary be prepared.

Sequencing note: the non-deploying host preparation happened before PR #133 reconciled the canonical plan, but PR #133 merged before the first production canary was approved and executed. Later recovery prerequisites remain subject to the same anti-drift rule and explicit authorization boundary.

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

**Phase 3 only:** issue #163 is complete. CV production and the installed classifier are reconciled to exact baseline `4a0069a97022841da07a687a197ea8cfacc56cd6`, readiness is `CURRENT`, and the recurring CV pull timer remains disabled/inactive.

The first incomplete gate is to wait for a **genuinely newer** exact-current-main `rozkalns-cv` delta after `4a0069a9...`. Do not create a dummy commit, manufacture a same-SHA target, or weaken classification merely to exercise automation.

When a genuine newer CV delta exists, re-read exact current RPi5_main and CV main, require fresh exact-current-main push CI, and require the App-authenticated preflight to classify the complete production→target range `AUTO_DEPLOY_SAFE` with `CONTROL_PLANE_CHANGED=false`. Revalidate exact installed preflight/classifier/pull-library/pull-wrapper identities and the proven controller↔wrapper evidence contract.

Only after those gates are green may exactly one #140 one-shot controller execution canary be separately reviewed and authorized while the recurring timer remains disabled/inactive. Require identical `READY` / `AUTO_DEPLOY_SAFE` preflight immediately before mutation, transactional public MIME/cache/nosniff/CSP evidence, final production at the exact target SHA, post-deploy readiness `CURRENT`, rollback/public checks green, and unchanged legacy helper/runner. Any `NO_DEPLOY`, `MANUAL_ROLLOUT_REQUIRED`, `DB_HOST_APPLY_REQUIRED`, wait or failure state remains non-mutating.

Recurring CV timer activation remains forbidden until that genuine one-shot AUTO canary is green. Legacy self-hosted runner retirement remains the final Phase 3 gate and requires its own review/authorization after recurring replacement execution evidence is green.
