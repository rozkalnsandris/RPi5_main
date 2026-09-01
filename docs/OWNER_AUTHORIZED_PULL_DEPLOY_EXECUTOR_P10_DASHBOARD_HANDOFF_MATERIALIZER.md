# P10 Dashboard preverified handoff materializer — source-only contract

Status: **source only / execution disabled / no LIVE authority**.

Issue: `RPi5_main#345`.

This capability closes one narrow trust-boundary gap: it defines how the exact already-preverified Dashboard candidate may later cross from a fixed unprivileged ingress namespace into the fixed service-owned handoff consumed by `scripts/dashboard-rpi5-production-candidate-stager.py`. This source change does not populate the live ingress, install or invoke the materializer, invoke the normal candidate stager, stage a production candidate, run PLAN/APPLY, or mutate the Raspberry Pi.

## Frozen candidate and provenance

The materializer is compiled to exactly one reviewed candidate identity:

- repository: `rozkalnsandris/dashboard_RPi5`;
- source SHA: `066b9a24008dd57439f9e66eae198416c4dfc590`;
- source tree: `62756ba22fc8d47e44988c086c08dcf37779cfb3`;
- direct parent: `5f7739348f56398d0ba301c9320e1de0062838fc`;
- manifest producer: `tools/production-candidate-manifest.mjs` blob `bea0f30602d119ae53b81e70ce2d4c283d369ce8`;
- candidate SHA-256: `d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9`;
- manifest files: exactly `72`;
- manifest total bytes: exactly `6,773,246`.

The previously observed timestamp/PID preparation root remains evidence only. It is deliberately absent from the privileged materializer source and is never accepted as a root-selected input path.

## Deterministic unprivileged ingress

Before any future root gate, the exact preverified bytes must exist under the only reviewed ingress namespace:

```text
/home/andris/.cache/rozkalns-dashboard-preverified-ingress/066b9a24008dd57439f9e66eae198416c4dfc590/
  source/
  candidate-manifest.json
```

That ingress is owned by `andris:andris`; directories are `0555`, files and manifest are `0444`. Preparing those exact bytes is an **unprivileged** pre-LIVE activity. The privileged materializer has no CLI field for an alternate source, path, manifest, candidate digest, command, script, argv or environment. It cannot select the historical timestamp/PID preparation root or a Git checkout.

Read-only modes are an additional invariant, not the trust mechanism by themselves: the owner can still alter user-owned files. Therefore root revalidates the full manifest/tree and re-hashes every file from descriptor-safe `O_NOFOLLOW` file descriptors while copying.

## Exact validation

Before mutation, the materializer requires:

- Linux descriptor-safe traversal with `/proc/self/fd`, `O_DIRECTORY`, `O_NOFOLLOW` and `O_NONBLOCK`;
- exact `dashboard-rpi5.production-candidate.v1` manifest shape;
- exact source SHA, release path, Node major and SHA-256 algorithm;
- exact `fileCount=72`, `totalBytes=6773246` and candidate digest `d12a49de...47b9`;
- deterministically sorted normalized relative paths with no `..`, empty components, backslashes or reserved components;
- exact tree equality with manifest paths;
- no symlinks or special files;
- exact ingress owner/group/modes;
- exact file byte sizes and SHA-256 values.

The manifest is read into memory before mutation. Candidate file bytes are opened again through descriptor-safe paths and re-hashed as those same descriptors are copied. If the user-owned ingress changes after preverification, the output is not accepted or published unless the copied bytes still exactly match the frozen manifest.

## Fixed service-owned output

The only root mutation target is:

```text
/var/lib/rozkalns-deploy-executor/dashboard-candidate-input/066b9a24008dd57439f9e66eae198416c4dfc590/
  source/
  candidate-manifest.json
```

The existing handoff base is a precondition and must be `root:root` mode `0755`, so the service account cannot create or replace candidate entries in that namespace. The final candidate handoff is `rozkalns-deploy-executor:rozkalns-deploy-executor`; all directories are `0555`; all files and the manifest are `0444`.

Materialization first uses exactly one source-specific sibling partial. The partial and its build files remain root-owned during byte copy/rehash; service ownership is applied only after the exact build has been verified:

```text
/var/lib/rozkalns-deploy-executor/dashboard-candidate-input/.066b9a24008dd57439f9e66eae198416c4dfc590.handoff-materializer-partial
```

Both final target and partial must be absent before the first write. Publication uses Linux `renameat2(..., RENAME_NOREPLACE)` so a concurrent target cannot be overwritten. There is no deletion budget.

## One-attempt mutation budget

A later separately authorized materialization attempt is bounded to:

- one partial handoff root creation;
- one source root creation;
- exactly 72 candidate file materializations;
- one manifest materialization;
- one no-replace atomic final rename.

Directory metadata operations are part of creating/finalizing those fixed output objects; they do not grant extra path authority. On any failure after the partial is created, the implementation preserves that partial as evidence. It performs no automatic retry, cleanup, rollback, deletion or alternate-path continuation.

## Root execution exclusions

The materializer does not import or invoke subprocesses, shells, Node, package managers, Git, network clients or credential APIs. Candidate JavaScript is data only. It never writes `/var/lib/rozkalns-dashboard-release-candidates`, `/opt/dashboard_RPi5`, `current`, release directories or the apply lock, and it does not install/enable/invoke the normal candidate stager.

`ops/deploy/executor-operations.json` remains globally `execution_enabled=false`. Merge of this source grants **no** host/root/LIVE authority.

## Required post-merge gates

The full sequence is intentionally split so one privileged capability cannot silently authorize the next:

1. **unprivileged preverification PASS** for the exact frozen candidate, with deterministic ingress prepared without root path selection;
2. **separate handoff-materialization LIVE/root gate** for exactly one materializer attempt;
3. STOP and collect **read-only handoff proof**: fixed target, owner/group/modes, exact manifest/digest/tree, no partial on success;
4. **separate candidate-stager LIVE/root gate** for exactly one normal staging attempt bound to the same candidate digest;
5. STOP and collect **read-only candidate-staging proof**;
6. **trusted-controller PLAN-only gate**;
7. **READY reconciliation** only after the accepted non-noop PLAN;
8. a later mutation-capable **APPLY LIVE-AUTH** remains a separate owner gate.

No merge, prior LIVE authorization, successful handoff materialization, successful candidate staging, PLAN result or READY state implicitly authorizes a later gate.
