# P9 Gate D public-target pre-auth forensic repair

Status: **SOURCE ONLY / FAIL-CLOSED REPAIR / NO LIVE AUTHORIZATION**

This document records the source repair following the separately owner-authorized
Gate D baseline attempt that stopped with:

`TARGET_PR_MERGE_SHA_MISMATCH`

The consumed baseline authorization is not reusable. This source repair does not
authorize a host upgrade, credential access, D1 request, baseline retry, genuine
P9 execution, StateStore access, queue/LIVE-AUTH mutation, deployment, rollback,
cleanup, or retry.

## Incident facts

The repaired runtime from RPi5_main PR #292 detected the target PR mismatch
before fixed D1 credential read/client construction. Therefore that failed
attempt reached no D1 credential read and no D1 SELECT request, did not publish a
new baseline, did not execute genuine P9, and did not touch StateStore.

Post-STOP read-only GitHub evidence reported target PR #24
`merge_commit_sha=db3b0ff76ee471d3b430e440a14d5cabbb1d99bc`, matching the pinned
expected merge SHA. The immutable merge commit/parent and compare ancestry also
matched the pinned tuple. The exact alternate PR merge SHA returned to the
failed live observation was not retained by the old sanitized diagnostic, so the
response-time mismatch cause remains unresolved. The pinned predicate must not be
weakened to make the baseline pass.

Canonical incident receipt: RPi5_main #191 comment `5471622361`.

## Repaired trust boundary

The baseline path now separates public target validation from protected source
and D1 capabilities:

1. An unauthenticated reader performs exactly the pinned public target repository,
   issue, PR, immutable merge-commit, and compare GETs.
2. Those responses are normalized with GitHub server time and optional ETag
   metadata.
3. The existing shared target predicate function validates the same issue, PR,
   merge-parent, and main-descends predicates used by the producer. No target
   predicate is removed or relaxed.
4. Any target mismatch stops before `build_source_client()`, before source-App
   private-key read/token mint, before D1 credential read, and before any D1
   request.
5. Only after the complete public target preflight passes may the source-App
   capability be constructed/primed.
6. The collector revalidates the in-process target snapshot before source
   evidence and again necessarily before D1 construction.
7. D1 remains capability-specific and unchanged: the same fixed credential,
   fixed account/database, exactly two source-fixed SELECT statements, and
   zero-write metadata requirements.

There is no automatic retry path.

## Public-safe mismatch diagnostics

Target semantic failures remain bounded to fixed failure codes. Diagnostics add
only public evidence:

- the fixed failure code and endpoint class;
- the source-pinned expected SHA when the predicate is SHA-bearing;
- the observed value only when it is a valid public 40-character SHA, otherwise
  the fixed marker `INVALID` or `NONE`;
- GitHub response server time;
- the public response ETag when present, otherwise `NONE`.

No authorization header, App JWT, installation token, D1 token, private-key
content, response body, D1 row content, or other credential-derived value is
included.

## Tests

The focused tests cover every reviewed target semantic failure code, including
malformed issue/PR/merge/compare objects. For every case they prove the public
target preflight stops before source-client construction/token mint and before
D1 credential/client access. The valid case still constructs the D1 capability
once and executes exactly the two fixed SELECT calls with zero-write metadata.

The CLI ordering test binds the production order to:

`public target snapshot -> source client -> one source-App token -> collector -> D1`

The tests also preserve the complete existing PR predicate set including
`TARGET_PR_MERGE_SHA_MISMATCH` and prove the public preflight reads each pinned
target endpoint exactly once.

## Future trusted-host upgrade — separately gated

Source includes a narrow future operator:

`scripts/install-deploy-executor-p9-gate-d-public-target-preauth-upgrade.py`

It is source-only in this repair and must not be executed without a later
separate STRICT LIVE owner authorization. It is bound to the currently proven
installed prestate from the #292 host upgrade and may replace only:

- `/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_control_postcanary_collector.py`
  from old Git blob `744ecc5d262982d82689ff5cd8e798c454077f3e`;
- `/usr/local/sbin/rozkalns-deploy-p9-control-baseline`
  from old Git blob `3cfd1fad722944c0a69767850a748791d49f4c71`.

The operator has preflight-only behavior without `--apply`, revalidates exact
source and installed old bytes/metadata before the first mutation, has no
network/credential/D1/baseline/P9/StateStore/systemd/config path, and has no
rollback or retry path.

Source merge is not host-upgrade authorization. A later host-upgrade PASS is not
a baseline authorization. A later fresh Gate D baseline PASS is not genuine P9
authorization.
