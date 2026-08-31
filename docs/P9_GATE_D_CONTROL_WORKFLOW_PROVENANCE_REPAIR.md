# P9 Gate D Control workflow provenance repair

Status: **SOURCE-ONLY REPAIR / NO LIVE AUTHORIZATION**

Tracking:

- canonical P9 handoff: `RPi5_main#191`
- deploy queue candidate: `ops-workflows#27` (`[DEPLOY-QUEUE][WAITING]`)
- Control handoff: `rozkalns-control-center#278`
- Control source repair: `rozkalns-control-center#496`

## Why this repair exists

A separately authorized Gate D trusted baseline was stopped before any protected
credential or baseline operation because fresh reconciliation found that the
authorized Control source `f9b900a884bffda993197fc7fa9223c886e11a90`
was no longer current.

Fresh reviewed Control source is:

- repository: `rozkalnsandris/rozkalns-control-center`
- stable repository ID: `1329279953`
- current reviewed main: `f04601dfd47e5691c875c0935b36ff101680f4dd`
- exact-main CI: `CI` #682 / run `33380350418` — successful
- workflow path: `.github/workflows/phase3-merge-postcanary-readonly-reconcile.yml`
- reviewed workflow blob: `48a55c05eae0daee72d87abf66e04ea5b872dd58`

The prior RPi contract pinned workflow blob `84b060b364fb5e9d824cf0d43e4f81c8ec6ea449`.

Control #496 changed only the reviewed post-canary merge-evidence path: when
GitHub REST API `2026-03-10` does not provide a usable pull-request
`merge_commit_sha`, the workflow may prove the same pinned merge identity using
one exact `merged` timeline event whose `commit_id` and timestamp match the
reviewed tuple. A present but different merge SHA still stops; the target issue,
PR, head, base, immutable merge commit, ancestry, D1 SELECT-only zero-write
contract and no-mutation assertions remain fail-closed.

Therefore this is a cross-repository provenance repair, not permission to ignore
source drift.

## Source contract after this repair

The selected operation remains exactly:

`rozkalns-control-center.merge-postcanary-reconcile.v1`

Unchanged invariants:

- source repository ID `1329279953`;
- target alias `control-center-merge-postcanary-reconcile`;
- target repository ID `1328835922`;
- owner-comment trigger `owner-issue-comment-278-v1`;
- D1 capability `d1-access:select-only-zero-write-v1`;
- `p9-trigger-dispatch:prohibited`;
- authorization class `STRICT`;
- global and prepared `execution_enabled=false`;
- rollback policy `NONE`;
- one future `control-center.read-only-reconciliation-run` maximum;
- no GitHub decision write, D1 write/migration/apply, Worker deploy,
  Cloudflare mutation, credential/permission mutation or host/runtime mutation
  through the adapter.

The production registry, reviewed fixture and adapter now bind only workflow
blob `48a55c05eae0daee72d87abf66e04ea5b872dd58`. Focused tests deliberately substitute the stale blob
`84b060b364fb5e9d824cf0d43e4f81c8ec6ea449` and an arbitrary SHA and require the adapter to reject both as
`source/interface dependency mismatch`.

The synthetic READY queue fixture is updated only to exercise the reviewed
source contract in tests. It is not the real deploy queue and grants no
authorization.

## Real queue remains WAITING

`ops-workflows#27` is intentionally different from the synthetic test fixture.
During this source repair its machine-parsed `## Queue contract` remains
byte-for-byte on the old Control SHA/blob. Only its `## Evidence` records the
pre-mutation drift.

Do not update the real Queue contract to the new Control SHA/blob until:

1. this source repair is merged with exact-main CI green; and
2. the required trusted-host workflow-provenance adapter convergence is
   separately authorized and proven.

`WAITING` is not LIVE-AUTH and is not execution authority.

## Trusted-host source audit

The installed Gate D baseline CLI imports
`p9_control_postcanary_collector`, and the collector imports
`WORKFLOW_SOURCE_BLOB` from `control_center_postcanary_adapter`.
The earlier API-2026 host upgrade replaced only the baseline CLI. It did not
replace the installed adapter.

Consequently, a fresh baseline bound to the new Control workflow provenance
requires a later installed-adapter convergence gate.

This repository therefore contains the source-only reviewed operator:

`scripts/install-deploy-executor-p9-gate-d-control-workflow-provenance-upgrade.py`

Its exact target set contains one file only:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/control_center_postcanary_adapter.py`

The operator's expected old blob is
`2a92f7fc0994b37f9625cb1c1178be98215e83e5`, mode `0644`, owner/group
`root:root`. That value is an **expected prestate for future live preflight, not
a claim about current host bytes**.

Before any future write the operator must prove:

- exact reviewed RPi5 source SHA;
- the operator itself matches that exact source;
- root execution;
- root-owned, non-group/world-writable parent chain;
- regular non-symlink target;
- exact owner/mode;
- exact old blob;
- unchanged inode/path immediately before the first truncate.

Without `--apply`, it is preflight-only and reports mutation `NO`.
Source merge does not authorize `--apply`.

A separately scoped later LIVE authorization is required for the one-target
replacement. The operator has no network, credential, D1, baseline collection,
P9, StateStore, systemd, config-registry, rollback, cleanup or retry path.

## Why the config registry is not a Gate D target

The Gate D baseline collection path does not load
`/etc/rozkalns-deploy-executor-p9/executor-operations.json`; it consumes the
installed collector/adapter provenance directly. Expanding this repair operator
to the installed config registry would add an unnecessary live mutation
category.

The installed registry must be freshly reconciled before any later genuine P9
attempt that uses the full runtime/queue operation path. That later work is not
authorized by this source repair or by a future Gate D baseline authorization.

## Required sequence after merge

After this source PR is merged, the next gates remain separate:

1. separately authorized trusted-host one-target adapter provenance convergence;
2. source/GitHub continuity reconciliation, including only then updating the
   real `ops-workflows#27` Queue contract if the host gate passed;
3. a new separately owner-authorized Gate D trusted baseline;
4. only after a baseline PASS may genuine P9 eligibility be reconsidered.

A host adapter PASS does not authorize baseline collection. A baseline PASS does
not authorize genuine P9. Genuine P9 still requires its own fresh authority and
all current queue/LIVE-AUTH/trust predicates.
