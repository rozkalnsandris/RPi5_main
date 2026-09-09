# Auto-Live v1 A4 — first-canary candidate selection

**Status:** A4 SOURCE SELECTION ONLY / LIVE DISABLED  
**Roadmap:** `RPi5_main#421`  
**Machine contract:** `ops/deploy/auto-live-a4-canary-selection.json`

## Purpose

A4 selects the first real Auto-Live canary candidate from the already merged A0-A3 contracts without activating production behavior. It is a source-level continuity and candidate-selection gate only.

A0 policy, A1 shared policy, A2 repository manifests and the A3 read-only controller are source-complete. A2 manifests remain `INACTIVE_SOURCE_ONLY`, the A3 controller remains mutation-disabled, and the global executor registry remains `execution_enabled=false`.

## Selected source-level candidate

The deterministic source-level A4 candidate is `rozkalnsandris/dashboard_RPi5` / `dashboard-rpi5-production-release` using static operation `dashboard-rpi5.production-release.v1`.

This selection follows the current machine contracts rather than an ad-hoc preference:

- Dashboard is the only current A2 manifest with an automatic-eligible class, `AUTO_DEPLOY_SAFE`;
- that class is limited to `apps/web/`;
- the Dashboard static operation is the reviewed ordinary operation for the same target alias;
- Weather has no automatic-eligible class and remains outside the first ordinary Auto-Live canary.

## Point-in-time GitHub evidence

At this reconciliation checkpoint:

- `RPi5_main/main = 9621c601f9bf94c4a29fad76afbdec250557d293`;
- `dashboard_RPi5/main = 20e47ff7ba808f183db56e347d4fde3e1d6a129f`;
- the existing reviewed/frozen Dashboard candidate is `343366427441811a22739b05b04d069c10905805`;
- current Dashboard `main` is a direct child of that reviewed SHA;
- the complete observed delta is only `AGENTS.md`, which the Dashboard manifest classifies as `NO_DEPLOY`.

These are point-in-time source facts, not production state. Current Dashboard `main` is not automatically promoted into a live target, and the reviewed/frozen SHA is not reusable LIVE authorization.

## Future A4 LIVE gate

Before any first Auto-Live activation/canary, a later separately authorized gate must freshly establish all of the following:

- current Dashboard GitHub source and exact intended target SHA;
- a trusted current production baseline from the reviewed target-specific resolver;
- complete production-baseline-to-target range classification;
- exact-target required CI success;
- exact manifest/static-operation identity and Auto-Live eligibility;
- current trusted-host adapter/helper/controller provenance and target baseline;
- one bounded owner LIVE authorization for the exact activation/canary envelope.

If the full current production range is not `AUTO_DEPLOY_SAFE`, or any source/runtime identity is missing, stale, ambiguous or inconsistent, A4 must fail closed to owner review rather than deploy.

## Mutation boundary

This source gate keeps all activation and mutation surfaces disabled:

- `execution_enabled=false`;
- manifest activation disabled;
- automatic mutation disabled;
- mutation dispatch disabled;
- adapter apply invocation disabled;
- systemd/timer mutation disabled;
- credential/permission mutation disabled;
- production deployment disabled;
- `production_mutation_started=false`.

No RPi5 host state, service, Docker state, production release, database, credential, permission, network or Cloudflare state is changed by A4 source selection.

Merge of this source gate is not LIVE authority. After merge, the next technical step is fresh exact-main and Dashboard cross-repository validation followed by minimum-sufficient trusted-host read-only preflight. Any actual first activation/canary remains a separate explicit owner LIVE decision.
