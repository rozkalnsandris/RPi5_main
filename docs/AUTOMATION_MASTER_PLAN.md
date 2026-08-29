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

### Phase 4 — Hermes Deals public-repository execution migration — CURRENT: P9 PRODUCERS MERGED / P9 GOVERNANCE COLLECTOR SOURCE

Hermes Deals Phase 4 remains the canonical production/live migration lane. Historical checklists are evidence only; current execution must re-resolve live repository state before every consequential step.

Current source anchors after the 2026-08-28 P9 producer merge reconciliation:

- `hermes-deals/main=140a50a17b398862a220e9302da1e6fa0680f2a2`; the reviewed canary source merge `2fbde52cc5b6661343dca3fd967d8112cb2bffbe` remains an ancestor beneath a later docs-progress commit;
- `RPi5_main/main=5f0f1ed62e4d52422139364898f735578be2cbdb` (`RPi5_main#258` squash merge);
- `ops-workflows/main=c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8`;
- exact-main RPi5 checks for `5f0f1ed62e4d52422139364898f735578be2cbdb` are green: Validate #621 (including Gitleaks/public automation baseline), FAST-LANE policy drift #76 and GITHUB-ONLY policy drift #65.

Completed Phase 4 source/live gates:

- [x] Current Hermes Deals governance/open-work inventory was re-read before implementation.
- [x] `hermes-deals#787` froze the public RPi5 execution inventory and capability grouping, with separate audit and release trust domains.
- [x] The replacement architecture is capability-specific rather than a generic powerful remote agent.
- [x] `origin-path-rpi5-audit` was selected as the lowest-risk read-only migration canary.
- [x] `RPi5_main#247` added and merged a dormant STRICT source contract for `hermes-deals.origin-path-audit.v1` with exact Hermes Deals repository/helper source identity bindings and adversarial tests.
- [x] The production executor registry remains disabled: `execution_enabled=false`, `operations=[]`.
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

Phase 4 next gates:

- [ ] `RPi5_main#259` is the current source-only gate for the complete governance writer-surface collector boundary, exact `ops-workflows` source/tree pinning and fail-closed completeness/provenance contracts.
- [ ] Governance evidence must remain fail-closed until every required human/team/App/workflow/token mutation surface is established by a reviewed complete collector and a separate reviewed source change pins the approved writer-set digest. Do not invent a new admin credential or treat a partial audit as trusted.
- [ ] The installed App/integration administration surface is still an unresolved runtime capability boundary. If the already reviewed read-only credentials cannot establish it completely, STOP for a separate owner architecture/credential/permission decision before any live collection or source pin.
- [ ] P9 live wiring must preserve two independent read-only App trust domains: Deploy Executor reads only `ops-workflows` Issues; Rozkalns Automation reads only approved source Contents/Actions. Do not widen either merely for convenience.
- [ ] Source + separately authorized host wiring is still required for the Automation App read-only credential/client and a one-shot P9 entrypoint.
- [ ] The production registry and current P8 poller remain empty/disabled until a later reviewed source gate makes the exact canary operation consumable without weakening P8 safety.
- [ ] A genuine P9 canary may run only when a real READY deploy-queue item and explicit owner decision exist. Do not create a dummy/placeholder LIVE-AUTH merely to test the executor.
- [ ] P9 must end with local `DRY_RUN_READY` and `PRODUCTION_MUTATION_STARTED=false`; P10 remains a separate live mutation gate.
- [ ] Only after the replacement path is proven may any current Hermes Deals self-hosted canary runner/path be retired, and runner retirement itself remains separately owner-authorized.

Do not use this phase to consume retailer-specific execution authorizations, change parser/corpus state, write DB/Review/publication state, deploy production, mutate Cloudflare, modify repository settings or widen credentials/permissions without the exact separate gate for that action.

### Phase 5 — Hermes Deals migration completion / residual audit paths

- [ ] Reconcile Phase 4 canary evidence against every remaining audit/diagnostic/release path.
- [ ] Migrate remaining capabilities incrementally, one trust domain at a time, preserving exact SHA, owner authorization, sanitized evidence and no-write boundaries where applicable.
- [ ] Remove each residual self-hosted runner only after its replacement is proven and separate owner authorization is granted.
- [ ] Record final runner/control-plane inventory and regression evidence in Hermes Deals governance and `RPi5_main#103`.

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

### Cross-cutting Track X — owner-authorized pull deploy executor v1 — P8 COMPLETE / P9 GOVERNANCE COLLECTOR SOURCE

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
Hermes Deals dormant canary contract: `docs/HERMES_DEALS_ORIGIN_PULL_CANARY_SOURCE.md`.

P0 through P8 are complete at their respective source/live gates. The P9 decision core is merged by `RPi5_main#250`; the P9 evidence schemas/parsers are merged by `RPi5_main#254` at `26f1f8810eaafbdf34e020f77253b57f7fe56da6`; the fixed-path provenance boundary is merged by `RPi5_main#256` at `68632ac3c5216f569d235fe1af04d4c4df1e1d6c`; the typed producer/publisher boundary is merged by `RPi5_main#258` at `5f0f1ed62e4d52422139364898f735578be2cbdb`; `RPi5_main#259` is the current governance writer-surface collector source gate. P8 remains installed and accepted on RPi5 at exact reviewed source `6a43ef875c785321a1b6bf09d8e558c5151c8546`; the recurring poller is unprivileged/read-only, production dispatch remains disabled, and the temporary staging credential was removed separately after acceptance.

Critical P0 authorization invariant remains binding:

**An autonomous RPi5 credential must not have write authority over the GitHub surface from which owner authorization is accepted.**

The roadmap body's historical Issues read/write Deploy Executor App text remains superseded by P0 review/checkpoints. The authorization reader is `ops-workflows` only with Issues read-only plus minimum metadata. Result reporting, if later implemented, must use a separately reviewed non-authority channel and must not gain the ability to mutate accepted LIVE-AUTH authority.

P9 preserves two independent read-only identities:

- `Rozkalns Deploy Executor` reads only the authorization surface in `ops-workflows`;
- `Rozkalns Automation` remains the existing source/CI reader with Actions read + Contents read on only the reviewed source repository allowlist.

`RPi5_main#250` provides stable source repository identity, merged/reachable exact-SHA + CI proof, JIT writer-set-governance freshness, genuine READY queue/source/baseline/adapter-preflight composition and final unchanged-authority verification. `RPi5_main#254` provides strict schemas/parsers for the JIT governance and sanitized Hermes baseline evidence. `RPi5_main#256` provides the fixed-path root-owned consumer provenance/placement boundary. `RPi5_main#258` provides the separately reviewed typed producer/publisher source boundary while deliberately keeping governance evidence fail-closed. `RPi5_main#259` now freezes the source/tree and completeness/provenance boundary for the complete writer-surface collector without claiming that the unresolved installed-App/integration administration surface is already collectable. None of these gates changes the production registry, P8 poller, systemd units, credentials or GitHub permissions, and none exposes a mutation/apply/result-writer path.

P9 live readiness still requires the complete reviewed runtime governance collection capability, a real complete writer-set audit plus separate approved digest source pin, the separate Automation App read-only runtime credential/client boundary, a one-shot P9 entrypoint, an exact operation-specific registry/runtime composition, a genuine READY queue and explicit owner decision. Any host credential/service/systemd/protected-evidence or GitHub permission/repository-setting change remains separately owner-gated.

The future transport remains data-only:

`owner-authored LIVE-AUTH -> exact queue/SHA/target/operation/baseline revalidation -> static source-controlled operation registry -> fixed project adapter preflight -> DRY_RUN_READY`.

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

**SOURCE ONLY:** complete `RPi5_main#259` review/CI for the fail-closed P9 governance writer-surface collector boundary. The collector must stay pinned to exact reviewed `ops-workflows` source/tree identity and must reject any incomplete collaborator/team/App/workflow/token surface. `APPROVED_GOVERNANCE_WRITER_SET_SHA256` remains unset; this gate performs no protected host/admin collection, places no credential, changes no permissions/repository settings/systemd/registry/poller state, creates no LIVE-AUTH/READY queue and authorizes no P9 canary.

After #259 is explicitly merged and exact-main CI is green, re-resolve whether the complete installed-App/integration administration surface can be collected with an already reviewed read-only capability. If not, STOP for the separate owner architecture/credential/permission decision before any runtime audit or digest source pin. The separate Automation App client/one-shot P9 runtime composition also remains source work after that trust prerequisite is resolved. Any step that reads protected host state, changes permissions/repository settings, or places credentials/files/services remains a later Composite STRICT owner gate.

Do **not** create a dummy LIVE-AUTH, pin an approved governance digest from synthetic/partial evidence, place/change credentials, modify systemd, widen GitHub App permissions, activate any mutation-capable adapter, deregister Hermes Deals runners, deploy production, write DB/Review/publication state, consume retailer-specific execution authorization, or mutate Cloudflare/repository settings merely because #259 is Ready or merged.
