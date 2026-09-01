# Owner-authorized pull deploy executor v1 — P10 hardened controller bootstrap

Status: SOURCE-ONLY RECONCILIATION
Roadmap: `RPi5_main#236`
Queue: `ops-workflows#28`
Dashboard candidate: `5f7739348f56398d0ba301c9320e1de0062838fc`
Machine contract: `ops/deploy/p10-dashboard-bootstrap.json`

## Why this gate exists

The repaired P10 trusted-host preflight successfully built the exact Dashboard ARM64 candidate, explicitly built and staged `node-pty`, verified the production candidate manifest and passed isolated production runtime smoke. It then stopped before `sudo` and before any privileged PLAN because the controller reached through `/opt/dashboard_RPi5/current` had Git blob:

`c501bea57c0d5c35e7961ae1f1e5593a02268661`

That blob is known GitHub source from Dashboard commit `400296591ec14c062e4c3c9fdbc95c38109ba0fd`, which added the historical root-only read-only PLAN path. It is not evidence of arbitrary host tampering.

However, it predates the descriptor-safe/current-release trust boundary introduced later by Dashboard issue `#236` / hardening commit `da49cfa0940fd7897f53674c72b4f9b54e4f239b`. Dashboard's canonical `docs/PHASE11D_RELEASE_ACTIVATION.md` explicitly requires a separate first hardened-controller bootstrap when the current verified release predates that boundary.

## Security decision

`c501bea57c0d5c35e7961ae1f1e5593a02268661` is classified as **known historical, bootstrap required**.

It must not be treated as a third normal P10 PLAN allowlist identity. In particular:

- do not execute operator-writable candidate JavaScript as root;
- do not patch the current immutable release in place;
- do not copy/replace only the installed controller as a preflight workaround;
- do not retry the consumed preflight authorization;
- do not use an alternate controller path merely to make PLAN pass.

The normal hardened controller identities remain:

- `7fcc58cbea2f1247d6e4d93bc3805923697fbfab` — reviewed hardened legacy controller;
- `c0566adb76e044632a4556dbefeb0f46839b4996` — current symlink-safe hardened controller.

## What the successful preflight already proves

The latest trusted-host attempt established, for exact Dashboard `5f7739348f56398d0ba301c9320e1de0062838fc`:

- Node 24 / Linux ARM64 build prerequisites were sufficient;
- `npm ci --ignore-scripts` completed;
- explicit `node-pty` source rebuild completed;
- native runtime staging returned `NATIVE_RUNTIME_PACKAGED=YES`;
- candidate manifest generation completed;
- manifest verification returned `MANIFEST_VERIFIED=YES`;
- isolated production runtime smoke returned `RUNTIME_SMOKE=PASS`;
- controller classification stopped before privileged invocation;
- privileged PLAN attempts = 0;
- production mutation started = NO;
- P10 APPLY executed = NO;
- retry allowed = NO.

This evidence narrows the remaining P10 blocker to the first hardened-controller bootstrap trust anchor; it does not authorize any host mutation.

## Required bootstrap implementation

The next source deliverable is a dedicated, one-time, capability-specific bootstrap adapter owned by the RPi5 control plane. It must not be a generic privileged shell or a new arbitrary remote execution interface.

The implementation must bind at least:

1. exact Dashboard candidate SHA;
2. exact known historical current-controller blob `c501bea57c0d5c35e7961ae1f1e5593a02268661`;
3. exact reviewed bootstrap adapter/helper identity;
4. exact root-owned trust-anchor path and metadata;
5. exact allowed mutation categories/counts;
6. explicit exclusions;
7. fail-closed evidence semantics after the first mutation;
8. a one-shot/non-replayable authorization envelope.

Candidate bytes must be consumed through descriptor-safe semantics or an equivalent immutable snapshot mechanism. A pathname-only `lstat/hash -> later root open/copy` flow is not sufficient.

The bootstrap source must remain execution-disabled until separately installed/activated under a fresh explicit LIVE/root authorization.

## Preferred trust-anchor shape

Prefer a small root-owned immutable bootstrap capability whose only purpose is crossing this one historical-to-hardened controller boundary. It should establish reviewed hardened controller authority without granting generic sudo, arbitrary argv, arbitrary source paths, package authority, service authority, Docker authority, networking authority or credential access.

The exact implementation may use a fixed root-owned helper or immutable bundle, but its provenance and file identities must be fully reviewable in source and independently revalidated immediately before first privileged execution.

After the hardened current-controller boundary is established, ordinary P10 and later deployments must return to the normal current-release controller path. The bootstrap capability must not become a permanent alternate deployment channel.

## Source/live separation

This reconciliation is source-only. It does not authorize:

- host filesystem mutation;
- installation of a bootstrap helper/bundle;
- `sudo` or root execution;
- controller replacement;
- current symlink mutation;
- production PLAN retry;
- production APPLY/deploy;
- service/systemd/Docker/Cloudflare mutation;
- permissions/identity/credential changes;
- cleanup of preserved evidence.

A later source implementation PR must become merged and exact-main green first. Only then may the owner consider a separate exact LIVE bootstrap authorization.

## Queue state

`ops-workflows#28` remains WAITING. Its reason should become `WAITING_HARDENED_CONTROLLER_BOOTSTRAP_IMPLEMENTATION` until the dedicated bootstrap adapter is source-ready, merged and revalidated.

The queue must not transition to READY merely because the historical controller identity is now understood.
