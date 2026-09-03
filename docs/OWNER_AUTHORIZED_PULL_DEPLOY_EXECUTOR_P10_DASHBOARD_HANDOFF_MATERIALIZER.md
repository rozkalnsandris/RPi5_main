# P10 Dashboard preverified handoff materializer — repaired source-only contract

Status: **source only / execution disabled / no LIVE authority**.

Issues: original `RPi5_main#345`; trust-namespace repair `RPi5_main#347`; privileged execution-provenance repair `RPi5_main#349`.

## Frozen candidate

- source SHA `066b9a24008dd57439f9e66eae198416c4dfc590`;
- source tree `62756ba22fc8d47e44988c086c08dcf37779cfb3`;
- parent `5f7739348f56398d0ba301c9320e1de0062838fc`;
- producer blob `bea0f30602d119ae53b81e70ce2d4c283d369ce8`;
- candidate SHA-256 `d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9`;
- exactly 72 files / 6,773,246 bytes.

## Fixed candidate ingress

The fixed unprivileged candidate ingress remains:

`/home/andris/.cache/rozkalns-dashboard-preverified-ingress/066b9a24008dd57439f9e66eae198416c4dfc590`

It is `andris:andris`, directories `0555`, files `0444`, and is never privileged authority by arbitrary pathname.

## Privileged execution provenance

Root must **not execute or import** the materializer from `/home/andris/RPi5_main`, another Git checkout, `/tmp`, or another mutable user-owned path.

Before a handoff LIVE gate can exist, #349 requires the separate execution-bundle contract:

`ops/deploy/dashboard-handoff-execution-bundle-v1.json`

The only accepted privileged entrypoint is:

`/var/lib/rozkalns-dashboard-handoff-exec/v1/dashboard-rpi5-preverified-handoff-materializer.py`

Its sibling core and `execution-manifest.json` must be in the same root-owned immutable bundle. The bundle is materialized in a separate root gate from a fixed unprivileged execution ingress, with root receiving verified bytes by stdin rather than opening user-controlled source paths. A read-only proof must establish exact merged main SHA/tree, exact wrapper/core Git blobs and SHA-256 values, root ownership/modes and exact three-file tree before handoff execution is authorized.

The wrapper checks the canonical root-owned execution path and exact execution manifest **before importing the core**. It then rehashes its own root-owned file and the root-owned core against the execution manifest. This makes the Git checkout source evidence only, never root code authority.

## Repaired root-owned handoff

The accepted handoff namespace remains:

```text
/var/lib/rozkalns-dashboard-candidate-input/
  066b9a24008dd57439f9e66eae198416c4dfc590/
    source/
    candidate-manifest.json
```

It is outside executor StateDirectory. `/var/lib` must be `root:root 0755`; the handoff base is `root:root 0755`; final handoff directories are `root:root 0555`; files/manifest are `root:root 0444`.

Publication remains one source-derived `renameat2(..., RENAME_NOREPLACE)` with final and partial required absent. After publish, the wrapper closes the publication namespace, re-opens the absolute canonical final path and re-verifies root ownership, modes, manifest bytes, exact tree, sizes and SHA-256 before success.

No accepted handoff object is transferred to the unprivileged executor service.

## Required post-merge gates

1. exact merged-source validation;
2. read-only fixed candidate-ingress reproof;
3. unprivileged execution-ingress preparation;
4. read-only execution-ingress proof;
5. **separate execution-bundle materialization LIVE/root gate**;
6. STOP + read-only execution-bundle proof;
7. **fresh handoff-materialization LIVE/root gate**;
8. STOP + read-only handoff proof;
9. **separate candidate-stager LIVE/root gate**;
10. STOP + read-only candidate-staging proof;
11. **trusted-controller PLAN-only gate**;
12. **READY reconciliation**;
13. later **APPLY LIVE-AUTH**.

The execution-bundle materialization gate does not invoke the handoff materializer. The handoff materializer does not invoke the candidate stager.

## Failure and exclusion policy

There is no deletion budget, automatic retry, cleanup, rollback or alternate path after the first mutation. Preserve partial evidence after a post-mutation failure.

There is no generic caller-selected path/command/argv/environment authority, direct root Git-checkout consumption, `/tmp` execution, candidate JavaScript/Node/package-manager execution as root, root Git/network/credential authority, normal candidate-stager invocation, `/opt/dashboard_RPi5`, PLAN/APPLY/deploy, package/systemd/service/Docker/network/Cloudflare/permission/database mutation.

`ops/deploy/executor-operations.json` remains globally `execution_enabled=false`. Source merge grants **no** execution-bundle, handoff, candidate-stager or APPLY LIVE authority.

The old `LIVE RPi5_main #345 HANDOFF-MATERIALIZATION` authorization and the pre-#349 repaired handoff authorization are unusable after this repair. Fresh post-merge proof and fresh owner authorization are required.
