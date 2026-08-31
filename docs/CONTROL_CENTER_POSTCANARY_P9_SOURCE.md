# Control Center post-canary reconciliation — P9 source contract

Status: **SOURCE RECONCILIATION / DORMANT OPERATION / GLOBALLY DISABLED / P9 DRY-RUN ONLY**

Tracking:

- shared executor roadmap: `RPi5_main#236`
- isolated-auth trust boundary: `RPi5_main#191`
- source registry/auth gates: `RPi5_main#271`, `#273`, `#275`, `#276`, `#277`, `#278`
- Control Center source corrections: `rozkalnsandris/rozkalns-control-center#489`, `#491`
- historical first-operation contract: `docs/HERMES_DEALS_ORIGIN_PULL_CANARY_SOURCE.md`

## Owner routing decision

On 2026-08-30 the owner redirected the first P9 genuine read-only canary target from Hermes Deals to the Rozkalns Control post-canary read-only reconciliation path.

The selected dormant operation is:

`rozkalns-control-center.merge-postcanary-reconcile.v1`

This is a source-routing decision only. It does not authorize a genuine P9 run, creation/promotion of a READY queue item or LIVE-AUTH, posting the Control owner trigger comment, workflow dispatch/rerun, D1 access, Worker deployment, Cloudflare mutation, host/runtime mutation, permission change or any other live side effect.

## Reviewed Control source identity

Reviewed source evidence for this source contract:

- repository: `rozkalnsandris/rozkalns-control-center`
- stable repository ID: `1329279953`
- reviewed main after squash merge of `#491`: `f9b900a884bffda993197fc7fa9223c886e11a90`
- reviewed workflow path: `.github/workflows/phase3-merge-postcanary-readonly-reconcile.yml`
- reviewed workflow blob: `84b060b364fb5e9d824cf0d43e4f81c8ec6ea449`
- exact reviewed-main CI: `CI` #676 / run `33302808439` — successful
- target evidence repository: `rozkalnsandris/ops-workflows`, stable repository ID `1328835922`

Control Center #491 changed only the target-PR failure diagnostics: the former aggregate merge-evidence failure was split into predicate-specific fail-closed STOP codes. The reviewed diff preserves the same target PR number/state/merged-at/draft/head/base/repository/merge-SHA predicates, and does not widen workflow permissions, trigger authority, D1 access or mutation behavior.

The reviewed SHA and workflow blob are source-review evidence, not permanent execution authority. Any genuine P9 attempt must freshly resolve the current Control repository identity, the exact authorized SHA, merged/reachable status and exact-SHA CI. Any drift in the selected workflow identity or safety contract is a STOP condition and requires a new source review.

## Why this operation is suitable for P9

The Control workflow is a bounded post-canary reconciliation path. Its reviewed source:

- is owner-comment triggered from Control issue `#278`;
- gives the workflow token only `contents: read` and `actions: read`;
- performs GitHub evidence reads for current Control main/CI and the consumed target Merge canary;
- constrains Cloudflare D1 requests to SQL beginning with `SELECT `;
- rejects D1 responses that report database changes, rows written or changes;
- asserts at termination that Merge post-send, D1 mutation, Worker mutation, Cloudflare config mutation, GitHub decision mutation and GitHub App permission mutation are all `NO`.

The actual workflow still uses an owner comment as a trigger and makes an authenticated external D1 read request. Therefore **P9 must not invoke it**. P9 proves only that the queue/LIVE-AUTH/source/CI/baseline/static-operation control plane would select this exact reviewed read-only operation while all execution surfaces remain disabled.

## Static operation contract

The production registry selects exactly this dormant Control operation while retaining the global `execution_enabled=false` gate.

Static selectors:

- authorization class: `STRICT`
- ordinary LIVE-ALL eligibility: `false`
- target alias: `control-center-merge-postcanary-reconcile`
- execution location class: `github-actions-readonly`
- repository entrypoint: `.github/workflows/phase3-merge-postcanary-readonly-reconcile.yml`
- deploy class: `STRICT_LIVE_AUTH_REQUIRED`
- baseline resolver ID: `control-center.merge-postcanary-audit-row.v1`
- rollback policy: `NONE`
- future invocation budget: one `control-center.read-only-reconciliation-run`

Explicit exclusions:

- GitHub merge/decision mutation;
- D1 write/migration/apply;
- Worker deploy;
- Cloudflare configuration mutation;
- GitHub App/credential/permission changes;
- host/runtime mutation.

Static dependencies bind the Control repository ID, reviewed workflow blob, target repository ID, owner-comment trigger contract, D1 SELECT-only zero-write contract and `p9-trigger-dispatch:prohibited` invariant.

Queue prose is not executable authority. The queue can select this operation only by exact static registry selectors, and the global registry remains execution-disabled.

## Adapter behavior

`ControlCenterPostCanaryAdapter` is intentionally inert:

- preflight validates exact operation/source/target/rollback/budget/exclusion/dependency identity;
- preflight explicitly returns `read_only=true`, `execution_enabled=false`, `privileged_dispatch_ready=false`, `mutation_enabled=false` and `production_apply_authorized=false`;
- `apply()` always fails closed and explicitly rejects posting the owner trigger or dispatching the workflow;
- postconditions require all Control reconciliation mutation flags to remain false;
- the adapter contains no command launcher, HTTP client, comment writer, workflow dispatcher or generic execution bridge.

P9 itself continues to omit adapter `apply()`, `StateStore.consume()`, a dispatcher, result writer and production mutation surface.

## Source evidence support

The P9 source verifier recognizes Control Center by stable repository ID `1329279953` and canonical exact-main workflow `ci.yml`.

A genuine P9 attempt must freshly prove:

1. source repository ID/full name/default branch;
2. exact authorized source SHA is current main or an ancestor of current main;
3. successful completed exact-main `ci.yml` run for that SHA;
4. at least one successful job in that exact run.

This allowlist grants only source/CI evidence verification. It does not grant write permission, workflow-trigger authority or Cloudflare access.

## Historical Hermes preservation

The Hermes Deals operation and adapter are retained as historical regression evidence. The historical fixture remains disabled and continues to prove its old static safety contract, but the current production registry no longer selects it.

Restoring Hermes as the selected P9 operation would require a new explicit owner routing decision and fresh source reconciliation.

## Genuine P9 waiting gate

Source reconciliation alone is not a genuine canary.

After this source contract is merged and exact-main CI is green, a genuine P9 attempt still requires all of the following:

1. a **real** open `rozkalnsandris/ops-workflows` `[DEPLOY-QUEUE][READY]` item that legitimately selects `rozkalns-control-center.merge-postcanary-reconcile.v1`;
2. a separate exact owner decision/authorization for the P9 attempt;
3. fresh `RPi5_main/main` and exact-main CI;
4. fresh `ops-workflows/main` and exact queue item;
5. fresh Control source identity, exact authorized SHA, merged/reachable status and exact-SHA CI;
6. fresh accepted isolated-auth trust surface and independent LIVE-AUTH/queue binding;
7. fresh operation-specific baseline evidence and cross-repository interface validation.

Do **not** create or promote a dummy/placeholder READY or LIVE-AUTH merely to exercise P9.

A successful P9 attempt ends locally with:

- `result=DRY_RUN_READY`;
- `mutation_dispatch_enabled=false`;
- `result_writer_enabled=false`;
- `PRODUCTION_MUTATION_STARTED=false`.

It does not post `/phase3-merge-postcanary-reconcile:...`, trigger/rerun the workflow or make a D1 request. P10 and any later actual read-only workflow invocation remain separate owner-gated work.

## Explicitly not authorized

This source contract and its merge do not authorize or perform:

- real READY or LIVE-AUTH creation/promotion;
- P9 execution;
- owner trigger comment creation;
- workflow dispatch/rerun;
- D1 query, write, migration or apply;
- GitHub Merge/Needs changes/other decision mutation;
- Worker deploy;
- Cloudflare DNS/Access/Tunnel/configuration mutation;
- GitHub App, credential, secret or permission change;
- host, systemd, Docker, package, storage, network, backup or firewall mutation;
- executor/broker activation;
- P10 or production mutation.

Any of those requires its own current evidence and exact owner authorization where applicable.
