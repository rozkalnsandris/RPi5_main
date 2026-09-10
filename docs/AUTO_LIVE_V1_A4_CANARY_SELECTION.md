# Auto-Live v1 A4 — first-canary candidate selection

**Status:** A4 OWNER REQUIRED / NO CANARY SELECTED / LIVE DISABLED  
**Roadmap:** `RPi5_main#421`  
**Machine contract:** `ops/deploy/auto-live-a4-canary-selection.json`

## Purpose

A4 evaluates the first real Auto-Live canary candidate from the merged A0-A3 contracts without activating production behavior. It is a source-level continuity and fail-closed candidate-selection gate only.

A0 policy, A1 shared policy, A2 repository manifests and the A3 read-only controller are source-complete. A2 manifests remain `INACTIVE_SOURCE_ONLY`, the A3 controller remains mutation-disabled, and the global executor registry remains `execution_enabled=false`.

## Source-level candidate

Dashboard remains the only current A2 manifest with an automatic-eligible class, `AUTO_DEPLOY_SAFE`, limited to `apps/web/`. Its reviewed static operation is `dashboard-rpi5.production-release.v1`. Weather has no automatic-eligible class.

The original reviewed/frozen Dashboard source candidate remains `343366427441811a22739b05b04d069c10905805`. It is historical selection evidence only and is not reusable LIVE authority.

## Current GitHub source evidence — 2026-09-10

Fresh source reconciliation observed:

- `RPi5_main/main = 782b531728e35e4f9ccda492b6f95886fffe60f0`;
- `dashboard_RPi5/main = a15a276c88d20d4a69895fc2fc0d95007ded8cbb`;
- previous A4-observed Dashboard main = `20e47ff7ba808f183db56e347d4fde3e1d6a129f`;
- reviewed/frozen Dashboard source candidate = `343366427441811a22739b05b04d069c10905805`;
- current Dashboard exact-SHA `FAST-LANE Merge Gate` = `success`.

The frozen-candidate-to-current range now includes `apps/server/`, `apps/web/`, `packages/contracts/`, documentation, tests and `AGENTS.md`. Under the existing manifest, `apps/server/` and `packages/contracts/` are `MANUAL_ROLLOUT_REQUIRED`, which outranks `AUTO_DEPLOY_SAFE`.

Therefore the current source range is deterministically:

`MANUAL_ROLLOUT_REQUIRED`

## Why a fresh LIVE baseline is not needed to reject this current target

A genuine first canary requires a production baseline different from the target and a full production-baseline-to-target range that is `AUTO_DEPLOY_SAFE`.

For current Dashboard main `a15a276c88d20d4a69895fc2fc0d95007ded8cbb`:

- if production is any reachable ancestor before current main, the range necessarily contains the latest Dashboard commit, which changes `apps/server/` and therefore classifies `MANUAL_ROLLOUT_REQUIRED`;
- if production already equals current main, there is no genuine source delta and the canary would be a no-op.

So current Dashboard main cannot be the first automatic Auto-Live canary under the present manifest. No trusted-host read was needed for this source-only rejection.

## Historical trusted production evidence — 2026-09-09

The previous minimum-sufficient trusted-host read-only preflight observed Dashboard production release `066b9a24008dd57439f9e66eae198416c4dfc590`.

At that checkpoint the complete baseline-to-frozen range already classified `MANUAL_ROLLOUT_REQUIRED` because it contained `package-lock.json`. That production evidence remains historical point-in-time provenance; it is not asserted as the current production baseline on 2026-09-10.

## A4 decision

A4 remains fail-closed to `OWNER_REQUIRED`.

No A4 Auto-Live canary is selected. Current Dashboard main `a15a276c88d20d4a69895fc2fc0d95007ded8cbb` is not an automatic live target.

A future A4 canary requires either:

1. a later genuinely `AUTO_DEPLOY_SAFE` full production-baseline-to-target range, established with fresh trusted production baseline and exact-target CI/provenance; or
2. a separately reviewed project-specific source-policy change that explicitly narrows the exact currently manual class.

LIVE authorization alone cannot override the source classification.

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

No RPi5 host state, service, Docker state, production release, database, credential, permission, network or Cloudflare state was read or changed by this source refresh.
