# Auto-Live v1 A4 — first-canary candidate selection

**Status:** A4 OWNER REQUIRED / NO CANARY SELECTED / LIVE DISABLED  
**Roadmap:** `RPi5_main#421`  
**Machine contract:** `ops/deploy/auto-live-a4-canary-selection.json`

## Purpose

A4 evaluates the first real Auto-Live canary candidate from the merged A0-A3 contracts without activating production behavior. It is a source-level continuity and fail-closed candidate-selection gate only.

A0 policy, A1 shared policy, A2 repository manifests and the A3 read-only controller are source-complete. A2 manifests remain `INACTIVE_SOURCE_ONLY`, the A3 controller remains mutation-disabled, and the global executor registry remains `execution_enabled=false`.

## Source-level candidate

Before trusted production-baseline evidence was available, the deterministic source-level A4 candidate was `rozkalnsandris/dashboard_RPi5` / `dashboard-rpi5-production-release` using static operation `dashboard-rpi5.production-release.v1`.

That source-level selection remains useful evidence, but it is not an Auto-Live target selection:

- Dashboard is the only current A2 manifest with an automatic-eligible class, `AUTO_DEPLOY_SAFE`;
- that class is limited to `apps/web/`;
- the Dashboard static operation is the reviewed ordinary operation for the same target alias;
- Weather has no automatic-eligible class and remains outside the first ordinary Auto-Live canary.

## Current GitHub evidence

At this reconciliation checkpoint:

- `RPi5_main/main = 9b92b08aa5a9c7f2691ff092ca7099c9dd918900`;
- `dashboard_RPi5/main = 20e47ff7ba808f183db56e347d4fde3e1d6a129f`;
- the reviewed/frozen Dashboard source candidate is `343366427441811a22739b05b04d069c10905805`;
- current Dashboard `main` is a direct child of that reviewed SHA;
- the complete frozen-to-current delta is only `AGENTS.md`, which the Dashboard manifest classifies as `NO_DEPLOY`.

These are point-in-time source facts. Current Dashboard `main` is not automatically promoted into a live target, and the reviewed/frozen SHA is not reusable LIVE authorization.

## Trusted production-baseline reconciliation

The minimum-sufficient trusted-host read-only preflight observed current Dashboard production release:

`066b9a24008dd57439f9e66eae198416c4dfc590`

No production mutation, candidate activation, host wiring or privilege widening was performed by that read-only evidence collection.

The complete production-baseline-to-frozen-candidate range contains:

- `apps/web/public/sw.js`
- `apps/web/src/pwa-register.ts`
- `apps/web/vite.config.ts`
- `docs/ISSUE243_PWA_CACHE_LIFECYCLE.md`
- `package-lock.json`
- `tests/e2e/pwa.spec.ts`

Under the existing Dashboard manifest, `apps/web/` is `AUTO_DEPLOY_SAFE`, documentation/tests are `NO_DEPLOY`, and `package-lock.json` is `MANUAL_ROLLOUT_REQUIRED`. The manifest precedence places `MANUAL_ROLLOUT_REQUIRED` above `AUTO_DEPLOY_SAFE`, so the complete production-baseline-to-frozen-candidate range is deterministically:

`MANUAL_ROLLOUT_REQUIRED`

The complete production-baseline-to-current-main range adds only `AGENTS.md`, which is `NO_DEPLOY`. It therefore remains `MANUAL_ROLLOUT_REQUIRED`.

## A4 decision

A4 fails closed to `OWNER_REQUIRED`.

No A4 Auto-Live canary is selected. Neither `343366427441811a22739b05b04d069c10905805` nor `20e47ff7ba808f183db56e347d4fde3e1d6a129f` is an automatic live target.

This reconciliation does **not** relax the classifier. In particular, it does not reclassify `package-lock.json` as `AUTO_DEPLOY_SAFE`. A future A4 canary requires either:

1. a genuinely `AUTO_DEPLOY_SAFE` full production-baseline-to-target range established from a fresh trusted production baseline, with fresh exact-target CI and provenance; or
2. a separately reviewed project-specific source-policy change that explicitly narrows the exact currently manual class.

A later owner LIVE authorization is still necessary for any real canary, but LIVE authorization alone cannot override the source classification.

## Mutation boundary

All activation and mutation surfaces remain disabled:

- `execution_enabled=false`;
- manifest activation disabled;
- automatic mutation disabled;
- mutation dispatch disabled;
- adapter apply invocation disabled;
- systemd/timer mutation disabled;
- credential/permission mutation disabled;
- production deployment disabled;
- `production_mutation_started=false`.

No RPi5 host state, service, Docker state, production release, database, credential, permission, network or Cloudflare state is changed by this source reconciliation.

Merge of this source gate would not be LIVE authority. The immediate outcome is a reviewed fail-closed A4 record with no canary selected.
