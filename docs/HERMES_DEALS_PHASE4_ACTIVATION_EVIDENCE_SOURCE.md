# Hermes Deals Phase 4 activation/evidence source bundle (#472)

This bundle advances the Phase 4 source contracts after `RPi5_main#470`. It is intentionally source-only. It does not prove or mutate current RPi5 host/runtime state.

## Frozen source anchors

- `RPi5_main` activation/main SHA: `6a1d17614e0dc270de75af0f5a11daa7bb3f6ffb`
- predecessor terminal receipt: `5638466496`
- AUTO-RUN activation receipt: `5638880694`
- `hermes-deals` source SHA: `8015d6175b2b3c260fdb26546021bb17dcc5f4fb`
- Hermes required CI workflow blob: `89059e310ab3270001daef43fd8f22a38b258c99`
- required Hermes gate: `FAST-LANE Merge Gate`

The capability-specific source identities are frozen in `ops/contracts/hermes-deals-phase4-activation-evidence-v1.json` and validated by the focused regression suite.

## Jobs 1–10

1. Ingest the exact #470 terminal receipt/main evidence into a deterministic successor gate.
2. Freeze current Hermes Deals provenance for origin-path audit, approved audit/runner-smoke, source-sync and production release.
3. Define the runner-independent `hermes-deals.runner-smoke-audit.v1` helper/registration contract using the dedicated `hermes-deals-audit-canary` non-login, non-root, no-Docker identity.
4. Define a deterministic install plan and read-only verifier without an apply entrypoint or host writes.
5. Define future canary authorization/replay/receipt validation without creating READY, LIVE-AUTH, replay consumption or synthetic PASS evidence.
6. Define the concrete `hermes-deals.source-sync.v1` static operation bound to `HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT` and fast-forward-only semantics.
7. Define read-only source-sync preflight, deterministic `HEAD_EQUALS_EXACT_TARGET_AND_CLEAN_MAIN_CHECKOUT` postcondition and fail-closed future receipt semantics.
8. Register `hermes-deals.production-release.v1` in the Auto-Live source manifest/static-operation schema while keeping the manifest `INACTIVE_SOURCE_ONLY`, automatic mutation disabled, the operation not ordinarily eligible and the global executor disabled.
9. Define current-runtime receipt ingestion and mechanical runner-retirement eligibility. Missing, stale, conflicting, source-generated or otherwise non-authentic evidence remains `NOT_ELIGIBLE`.
10. Produce one deterministic next LIVE gate plus the ordered later gates without executing any of them.

## Auto-Live A5 safety

`ops/deploy/auto-live-manifests/hermes-deals.json` is deliberately conservative:

- `INACTIVE_SOURCE_ONLY`;
- `automatic_mutation_enabled=false`;
- global `ops/deploy/executor-operations.json` remains `execution_enabled=false`;
- the Hermes production operation has `ordinary_live_all_eligible=false`;
- the current `AUTO_DEPLOY_SAFE` path allowlist is empty;
- documentation/tests are `NO_DEPLOY`;
- application/dependency changes are owner-required;
- workflow/runner/migration/deploy infrastructure changes are `DB_HOST_APPLY_REQUIRED`;
- unmatched or ambiguous paths are `BLOCKED`.

Source registration is not LIVE activation and is not production deployment authority.

## Runtime evidence and runner retirement

The source evaluator accepts only receipts matching `rozkalns.hermes-deals.phase4-runtime-evidence.v1` with the frozen source SHA, known capability and slot, authentic + sanitized + current runtime observation, non-source-generated status and bounded freshness. Each capability must have all of these current slots:

- `host_wiring_proven`
- `installed_identity_verified`
- `genuine_canary_or_e2e_proven`
- `fallback_dependency_removed`
- `fresh_final_runner_inventory`

Even complete evidence only reaches `ELIGIBLE_FOR_SEPARATE_OWNER_RETIREMENT_GATE`; it never authorizes runner deregistration or repository-settings mutation by itself.

## First future LIVE gate

The first future LIVE candidate is exactly:

- gate: `hermes-deals.runner-smoke-audit.install.v1`
- target alias: `hermes-deals-runner-smoke-audit-install`
- capability operation: `hermes-deals.runner-smoke-audit.v1`
- mutation class: capability-specific host install/wiring
- rollback policy: `NONE`
- automatic retry/cleanup/rollback after mutation start: forbidden

Before that gate, exact merged RPi5_main source/CI, exact merged Hermes source/CI, helper/registration identities, the dedicated account model and fixed destination state must be revalidated. A separate owner LIVE authorization must bind the exact gate envelope.

The later order is: runner-smoke genuine canary → source-sync host wiring/canary → production-release A5 activation/canary only where the complete range is `AUTO_DEPLOY_SAFE` → fallback removal → fresh final runner inventory → explicit runner retirement/settings gate.

Phase 4 remains `NOT_CLOSED_LIVE_EVIDENCE_REQUIRED`. Merging this source bundle does not authorize LIVE execution.
