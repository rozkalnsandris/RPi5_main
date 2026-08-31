# P9 Gate D final-lifecycle baseline repair

Status: **SOURCE-ONLY REPAIR / NO LIVE AUTHORIZATION**

## Why this repair exists

The Control post-canary Gate D baseline originally pinned `rozkalnsandris/ops-workflows#25` while that canary lifecycle issue was still open. The reviewed producer therefore required the exact target issue to have `state=open` before source-App authentication, D1 credential access or either SELECT request.

The canary lifecycle has since legitimately completed. Canonical Control continuity records the Phase 3 Merge canary lifecycle as COMPLETE, and `ops-workflows#25` is now closed with `state_reason=completed` and a concrete `closed_at` timestamp. Reopening that issue merely to satisfy the historical baseline predicate would manufacture lifecycle state and is prohibited.

The previously published Gate D baseline is also deliberately short-lived: `control-center.merge-postcanary-audit-row.v1` evidence is accepted by the P9 resolver for at most 300 seconds. Historical PASS evidence remains provenance, but it is not reusable as fresh runtime authorization or fresh P9 baseline evidence.

Therefore `ops-workflows#27` must remain WAITING until source and installed producer provenance are repaired and a new separately owner-authorized trusted baseline succeeds against the completed lifecycle.

## Source correction

The only semantic change is in:

`ops/lib/deploy_executor/p9_control_postcanary_producer.py`

The exact target issue lifecycle predicate accepts:

1. the previously reviewed active state `state=open`; or
2. the canonical terminal state only when all of these are simultaneously true:
   - `state=closed`;
   - `state_reason=completed`;
   - `closed_at` is a non-empty string.

A bare closed issue, `closed/not_planned`, missing `closed_at`, wrong issue number or a pull-request object still fails closed before protected source-App or D1 paths. The existing sanitized failure code `TARGET_ISSUE_NOT_OPEN` is retained for compatibility; its accepted lifecycle semantics are now covered explicitly by focused tests.

No target PR, merge-parent, main-descendancy, canary-run, audit-row, D1 SELECT-only/zero-write, source identity, workflow provenance, evidence schema or publisher predicate is widened.

## Reviewed host convergence surface

The initial P9 installer places package modules at:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/`

with `root:root 0644` metadata. The historical/current installed producer prestate expected by this source repair is the reviewed source blob:

`d9c6601b55c11942335648ba2f4795ec9713143f`

This blob is an expected prestate for a future operator, not an assertion about current live bytes. The operator independently verifies the installed file before mutation.

The dedicated operator is:

`scripts/install-deploy-executor-p9-gate-d-final-lifecycle-producer-upgrade.py`

It is bound to exactly one target:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_control_postcanary_producer.py`

Its contract is fail-closed:

- exact reviewed `RPi5_main` source SHA required;
- operator itself must match that exact SHA;
- reviewed replacement bytes come from `git show <exact-sha>:<source-path>`;
- root execution required;
- target parent chain must be root-owned and non-group/world-writable;
- installed target must be a regular non-symlink `root:root 0644` file with exact old blob `d9c6601b55c11942335648ba2f4795ec9713143f`;
- without `--apply`, preflight reports PASS with mutation NO;
- `--apply` repeats the complete preflight immediately before mutation;
- the opened inode, metadata, old blob and path inode are revalidated before first truncate;
- mutation is one in-place reviewed file replacement only;
- post-write bytes and metadata are verified;
- no retry or rollback path exists.

Explicit non-surfaces:

- network request: NO;
- credential/private-key/token read: NO;
- D1 request: NO;
- baseline collection: NO;
- genuine P9 execution: NO;
- StateStore access: NO;
- systemd mutation: NO;
- config registry mutation: NO;
- adapter mutation: NO;
- collector mutation: NO;
- baseline CLI mutation: NO.

Source merge never authorizes `--apply`.

## Required continuation sequence

1. Carry this source repair through exact-head CI/review and Ready for review.
2. STOP for explicit MERGE authorization.
3. After merge, freshly re-read exact main/CI and cross-repository state.
4. Under a separate STRICT LIVE authorization, advance the trusted checkout only by a clean/ancestor-gated fast-forward to the exact merged SHA and run exactly the reviewed one-target producer upgrade. No baseline or P9 is included in that gate.
5. Record public-safe installed-producer provenance.
6. Under another separate STRICT LIVE authorization, collect exactly one fresh trusted Gate D baseline. The public target pre-auth must prove the real completed `ops-workflows#25` lifecycle before protected source-App/D1 work. No genuine P9 is included in that baseline gate.
7. Only while that baseline is fresh and all source/host/queue/trust evidence remains current, reconcile `ops-workflows#27` machine contract to current Control source/workflow identity and evaluate READY under the shared queue policy.
8. Genuine P9 remains a later separate owner/LIVE-AUTH gate even if #27 becomes READY.

Do not reopen `ops-workflows#25`, create placeholder evidence, create a dummy LIVE-AUTH, promote #27 prematurely, run baseline during producer convergence, or infer live producer bytes from repository source.
