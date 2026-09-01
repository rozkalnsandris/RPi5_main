# P10 Dashboard normal candidate stager — source-only contract

Status: **source only / execution disabled / no LIVE authority**.

Issue: `RPi5_main#341`.

This contract adds the narrowly scoped source implementation needed for the first genuine Dashboard P10 production candidate. It does not stage anything on the Raspberry Pi, install a root helper, enable the deploy executor, run the Dashboard controller, perform PLAN/APPLY, or mutate production.

## Exact candidate identity

The only Dashboard source SHA accepted by this source capability is:

```text
066b9a24008dd57439f9e66eae198416c4dfc590
```

Its reviewed direct parent is:

```text
5f7739348f56398d0ba301c9320e1de0062838fc
```

The candidate manifest remains the Dashboard-owned `dashboard-rpi5.production-candidate.v1` format. A future preverification step must build the exact reviewed Dashboard checkout and generate/verify the manifest with the existing Dashboard production-candidate tooling. The resulting `candidateSha256` is not guessed or synthesized by `RPi5_main`; a separate exact LIVE envelope must bind the observed lowercase 64-hex digest before root staging can start.

## Fixed preverified handoff

The future unprivileged handoff is source-derived only:

```text
/var/lib/rozkalns-deploy-executor/dashboard-candidate-input/066b9a24008dd57439f9e66eae198416c4dfc590/
  source/
  candidate-manifest.json
```

The handoff owner/group is fixed to `rozkalns-deploy-executor`. Before privileged staging, the tree must be immutable-by-contract:

- directories: `0555`;
- files and manifest: `0444`;
- no symlinks;
- no special files;
- exact tree equality with the manifest;
- exact file byte sizes and SHA-256 digests;
- exact manifest self-digest and source SHA;
- exact `candidateSha256` equality with the separate LIVE binding.

The root stager traverses the handoff only through `openat`-style file descriptors with `O_NOFOLLOW`. It does not execute anything from the candidate tree.

## Fixed root-owned output

The only staging destination is:

```text
/var/lib/rozkalns-dashboard-release-candidates/066b9a24008dd57439f9e66eae198416c4dfc590/
  source/
  candidate-manifest.json
```

Output directories are root:root `0755`; output files/manifest are root:root `0644`. Candidate files are copied from descriptor-safe input descriptors and re-hashed while copying. The final candidate root is published by one source-derived sibling rename only after all files and the manifest have been materialized successfully.

The normal Dashboard production controller therefore later sees exactly the paths already frozen by `dashboard-rpi5.production-release.v1`:

```text
candidate root:
  /var/lib/rozkalns-dashboard-release-candidates/<source>/source

candidate manifest:
  /var/lib/rozkalns-dashboard-release-candidates/<source>/candidate-manifest.json
```

## Privilege boundary

The stager has no CLI argument for source SHA, input path, destination path, manifest path, command, script, arbitrary argv, environment or shell text. Its only dynamic authorization value is the exact future candidate SHA-256 digest, plus explicit `--apply` and a capability-specific acknowledgement.

It does not import or invoke Node, the candidate controller, package managers, shells, `sudo`, `git`, systemd, Docker, network clients or credential APIs. Candidate JavaScript is data only during staging and is never executed as root.

The source file is not installed by this issue and is not registered as an executable deploy operation. `ops/deploy/executor-operations.json` remains globally:

```json
{"execution_enabled": false}
```

A later LIVE gate must separately review and authorize any installation/invocation crossing.

## Staging-only mutation budget

Maximum mutations for one later authorized staging attempt:

- staging namespace root creation: 1;
- source-specific partial candidate root creation: 1;
- candidate file materializations: at most 512 and exactly the manifest count;
- manifest materialization: 1;
- final source-specific rename: 1.

There is no deletion budget. If a later staging mutation starts and then fails, the implementation does not automatically retry, clean the partial tree, roll back, choose an alternate path, or continue to production. Evidence is preserved for a new owner decision.

## Production exclusions

The source implementation never targets:

- `/opt/dashboard_RPi5` for writes;
- `/opt/dashboard_RPi5/current`;
- `/opt/dashboard_RPi5/releases/<source>`;
- the Dashboard apply lock;
- P10 PLAN or APPLY;
- services, packages, Docker, network, Cloudflare, credentials, permissions, DB/data or any other runtime surface.

The manifest's `releasePath=/opt/dashboard_RPi5/releases/<source>` remains validated metadata because the existing Dashboard controller expects that canonical manifest shape; it is not a staging write target.

## Gate sequence after source merge

Merge of this source capability grants no host authority. The next allowed sequence remains:

1. exact-main CI and source verification;
2. fresh read-only trusted-host provenance/prestate verification;
3. separate exact LIVE/root authorization for one candidate staging attempt bound to source `066b9a...` and one exact candidate SHA-256;
4. STOP after staging and collect read-only evidence;
5. later separate trusted-controller PLAN-only gate;
6. only after an accepted non-noop PLAN may queue reconciliation proceed;
7. mutation-capable P10 APPLY still requires its own later LIVE-AUTH.
