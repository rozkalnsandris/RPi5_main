# Auto-Live v1 A4 — first-canary candidate selection

**Status:** A4 OWNER REQUIRED / NO CANARY SELECTED / LIVE DISABLED  
**Roadmap:** `RPi5_main#421`  
**Machine contract:** `ops/deploy/auto-live-a4-canary-selection.json`

## Purpose

A4 evaluates the first real Auto-Live canary candidate from the merged A0-A3 contracts without activating production behavior. It is a source-level continuity and fail-closed candidate-selection gate only.

A0 policy, A1 shared policy, A2 repository manifests and the A3 read-only controller are source-complete. A2 manifests remain `INACTIVE_SOURCE_ONLY`, the A3 controller remains mutation-disabled, and the global executor registry remains `execution_enabled=false`.

## Source-level candidate

Dashboard remains the only current A2 manifest with an automatic-eligible class, `AUTO_DEPLOY_SAFE`, limited to `apps/web/`. Its reviewed static operation is `dashboard-rpi5.production-release.v1`. Weather has no automatic-eligible class.

The original reviewed/frozen Dashboard source candidate `343366427441811a22739b05b04d069c10905805` is historical selection evidence only and is not reusable LIVE authority.

## State-based continuity rule

The canonical A4 state is **not** bound to an exact Dashboard `main` SHA. Dashboard `main` is volatile and must be read fresh at each candidate evaluation. A new Dashboard merge does not, by itself, require an `RPi5_main` continuity PR.

Continuity changes only when the A4 state or policy changes: for example, a genuinely eligible full production-baseline-to-target range is identified, a canary is selected, activation authority changes, or the reviewed classifier/operation contract changes.

## Point-in-time GitHub source evidence — 2026-09-10

The latest evaluated snapshot for this source correction observed:

- `RPi5_main` evidence base = `c4accd5ea08343f8e4fce30534a6e7734a461e5f`;
- evaluated `dashboard_RPi5` SHA = `b5838741d094ad7f70987bf5a5060be11371a6ae`;
- previous evaluated Dashboard SHA = `a15a276c88d20d4a69895fc2fc0d95007ded8cbb`;
- reviewed/frozen Dashboard source candidate = `343366427441811a22739b05b04d069c10905805`;
- evaluated Dashboard exact-SHA `FAST-LANE Merge Gate` = `success`.

The frozen-candidate-to-evaluated range includes `ops/production/container-metrics-source-contract.json` and `tools/issue265-container-metrics-source-readiness.test.mjs`. Under the unchanged manifest, `ops/` and `tools/` are `DB_HOST_APPLY_REQUIRED`, the highest-precedence class. The same range also contains `package.json`, `apps/server/` and `packages/contracts/`, which are `MANUAL_ROLLOUT_REQUIRED`.

Therefore this evaluated source range is deterministically `DB_HOST_APPLY_REQUIRED` and cannot be an automatic Auto-Live canary. The exact SHA and CI result are point-in-time evidence only.

## Historical trusted production evidence — 2026-09-09

The previous minimum-sufficient trusted-host read-only preflight observed Dashboard production release `066b9a24008dd57439f9e66eae198416c4dfc590`.

At that checkpoint the complete baseline-to-frozen range already classified `MANUAL_ROLLOUT_REQUIRED` because it contained `package-lock.json`. That production evidence remains historical point-in-time provenance and is not asserted as current runtime truth.

## A4 decision

A4 remains fail-closed to `OWNER_REQUIRED` with **no canary selected**. The canonical gate is now `A4_OWNER_REQUIRED_PENDING_FRESH_ELIGIBLE_CANDIDATE`, not an exact source SHA.

Every future candidate evaluation must freshly resolve the then-current Dashboard source head and trusted production baseline, classify the **complete** baseline-to-target range, and verify exact-target CI/provenance. Only a genuinely `AUTO_DEPLOY_SAFE` full range can advance to a separately owner-authorized LIVE canary.

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

No RPi5 host state, service, Docker state, production release, database, credential, permission, network or Cloudflare state was read or changed by this source correction.
