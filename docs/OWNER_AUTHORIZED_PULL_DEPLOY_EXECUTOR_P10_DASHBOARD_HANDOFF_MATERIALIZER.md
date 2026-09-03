# P10 Dashboard preverified handoff materializer — repaired source-only contract

Status: **source only / execution disabled / no LIVE authority**.

Issues: original `RPi5_main#345`; security repair `RPi5_main#347`.

## Frozen candidate

- source SHA `066b9a24008dd57439f9e66eae198416c4dfc590`;
- source tree `62756ba22fc8d47e44988c086c08dcf37779cfb3`;
- parent `5f7739348f56398d0ba301c9320e1de0062838fc`;
- producer blob `bea0f30602d119ae53b81e70ce2d4c283d369ce8`;
- candidate SHA-256 `d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9`;
- exactly 72 files / 6,773,246 bytes.

## Fixed ingress and repaired root-owned handoff

The fixed unprivileged ingress remains `/home/{fixed-owner}/.cache/rozkalns-dashboard-preverified-ingress/<source-sha>` with compile-time owner `andris`, `andris:andris`, directories `0555`, files `0444`. Preparing it is a separate explicitly authorized unprivileged host mutation.

The repaired privileged handoff namespace is:

```text
/var/lib/rozkalns-dashboard-candidate-input/
  066b9a24008dd57439f9e66eae198416c4dfc590/
    source/
    candidate-manifest.json
```

It is outside the executor service StateDirectory. `/var/lib` must be `root:root 0755`; the materializer may create only the fixed base as `root:root 0755`. Partial/final candidate directories and accepted source directories remain root-owned; final directories are `0555` and final files/manifest are `0444`. No accepted handoff object is transferred to the executor service.

Publication remains one source-derived `renameat2(..., RENAME_NOREPLACE)` with final and partial required absent. After publish, the hardened entrypoint closes the publication namespace, re-opens the **absolute canonical final path**, and re-verifies root ownership, modes, manifest bytes, exact tree, sizes, and SHA-256 before success.

There is no deletion budget, automatic retry, cleanup, rollback, alternate path, normal candidate-stager invocation, `/opt/dashboard_RPi5` mutation, PLAN/APPLY, candidate JavaScript execution, shell/subprocess, Git/network/credential authority, or generic caller-selected path/command/argv/environment.

`ops/deploy/executor-operations.json` remains `execution_enabled=false`. Source merge grants **no** host/root/LIVE authority.

## Required post-merge gates

1. exact merged-source validation;
2. unprivileged preverification PASS;
3. separately authorized fixed-ingress preparation;
4. **separate handoff-materialization LIVE/root gate** bound to the repaired exact main SHA;
5. STOP + **read-only handoff proof**;
6. **separate candidate-stager LIVE/root gate**;
7. STOP + read-only candidate-staging proof;
8. **trusted-controller PLAN-only gate**;
9. **READY reconciliation**;
10. later **APPLY LIVE-AUTH**.

The old `LIVE RPi5_main #345 HANDOFF-MATERIALIZATION` authorization targeted the rejected trust boundary and is invalidated before consumption. It cannot authorize repaired-source execution.
