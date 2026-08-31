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
blob `48a55c05eae0daee72d87abf66e04ea5b872dd58`. Focused tests deliberately
substitute the stale blob `84b060b364fb5e9d824cf0d43e4f81c8ec6ea449` and an arbitrary SHA and require
the adapter to reject both as `source/interface dependency mismatch`.

The synthetic READY queue fixture is updated only to exercise the reviewed
source contract in tests. It is not the real deploy queue and grants no
authorization.

## Real queue remains WAITING

`ops-workflows#27` is intentionally different from the synthetic test fixture.
Its machine-parsed `## Queue contract` remains on the older reviewed Control
SHA/workflow blob while the required host provenance gates are incomplete.
Evidence comments may record completed prerequisites without changing READY
eligibility.

Do not update the real Queue contract or title to READY until all of the
following are true:

1. the Control workflow-provenance source repair is merged with exact-main CI
   green;
2. the trusted-host installed adapter provenance convergence is separately
   authorized and proven;
3. a trusted Gate D baseline has passed with public-target pre-auth, exact
   source-App read scope and D1 SELECT-only zero-write evidence; and
4. the installed P9 operation registry has been separately converged to the
   reviewed current registry bytes described below.

`WAITING` is not LIVE-AUTH and is not execution authority. A baseline PASS is
not sufficient to make genuine P9 READY while the full runtime registry remains
on an incompatible dependency contract.

## Trusted-host adapter audit

The installed Gate D baseline CLI imports `p9_control_postcanary_collector`, and
the collector imports `WORKFLOW_SOURCE_BLOB` from
`control_center_postcanary_adapter`. The earlier API-2026 host upgrade replaced
only the baseline CLI. It did not replace the installed adapter.

Consequently, a baseline bound to the new Control workflow provenance required
the later installed-adapter convergence gate.

The reviewed source-only adapter operator is:

`scripts/install-deploy-executor-p9-gate-d-control-workflow-provenance-upgrade.py`

Its exact target set contains one file only:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/control_center_postcanary_adapter.py`

Its expected old blob is `2a92f7fc0994b37f9625cb1c1178be98215e83e5`,
mode `0644`, owner/group `root:root`. That value is an expected prestate for live
preflight, not a general claim about host bytes.

## Why the config registry was not a Gate D baseline target

The Gate D baseline collection path does not load
`/etc/rozkalns-deploy-executor-p9/executor-operations.json`; it consumes the
installed collector/adapter provenance directly. Expanding the baseline repair
operator to the installed config registry would therefore have added an
unnecessary live mutation category to Gate D.

Genuine P9 is different. `p9_host_runtime.py` loads the installed registry and
passes its normalized operation dependencies into the selected adapter. The
current adapter requires workflow blob
`48a55c05eae0daee72d87abf66e04ea5b872dd58`. An installed registry that still
pins `84b060b364fb5e9d824cf0d43e4f81c8ec6ea449` is therefore intentionally
incompatible and must fail closed before genuine P9 can become eligible.

## Genuine-P9 registry provenance convergence

The reviewed initial P9 runtime installer installed exactly:

`/etc/rozkalns-deploy-executor-p9/executor-operations.json`

with owner/group `root:root`, mode `0644`, from source blob
`5e9e4c7e96b6f24453077d896812a402bb303a92`. Subsequent accepted host repair
receipts explicitly excluded config-registry mutation. This historical chain is
the reviewed expected prestate for a future live preflight; it is not a fresh
read of protected host contents.

The current reviewed source registry is `ops/deploy/executor-operations.json`.
It binds the repaired Control workflow provenance. This repository therefore
contains the source-only reviewed one-target operator:

`scripts/install-deploy-executor-p9-gate-d-registry-provenance-upgrade.py`

The operator may replace only the installed registry above. Before any write it
must prove:

- exact reviewed RPi5 source SHA;
- the operator itself matches that exact source;
- root execution;
- root-owned, non-group/world-writable parent chain;
- regular non-symlink target;
- exact `root:root 0644` metadata;
- exact old blob `5e9e4c7e96b6f24453077d896812a402bb303a92`;
- unchanged inode/path immediately before the first truncate.

The replacement bytes are read from
`<exact-reviewed-sha>:ops/deploy/executor-operations.json`; they are never copied
from an unpinned worktree file. Without `--apply`, the operator is preflight-only
and reports `P9_GATE_D_REGISTRY_PROVENANCE_MUTATION=NO`.

A successful separately authorized apply reports exactly one registry target
replacement and `CONFIG_REGISTRY_MUTATION=YES`. It has no network, credential,
D1, baseline collection, P9 execution, StateStore, systemd, adapter, baseline
CLI, collector, rollback, cleanup or retry path. Source merge alone never
authorizes `--apply`.

## Required sequence from the current WAITING state

The remaining gates are deliberately separate:

1. merge this source-only registry-provenance operator after exact-head CI and
   review are green;
2. separately authorize a trusted checkout clean/ancestor-gated fast-forward to
   that exact merged RPi5 SHA plus exactly one installed-registry replacement;
3. record public-safe host provenance evidence and only then reconcile
   `ops-workflows#27` machine Queue contract to the current reviewed Control
   SHA/workflow dependency contract;
4. only after fresh queue/registry/baseline/trust reconciliation may genuine P9
   be considered READY; genuine P9 still requires its own fresh authority and
   any required isolated LIVE-AUTH.

The already completed adapter convergence and Gate D baseline do not authorize
this registry mutation. A registry PASS does not authorize genuine P9, and a
READY queue never substitutes for LIVE authorization.
