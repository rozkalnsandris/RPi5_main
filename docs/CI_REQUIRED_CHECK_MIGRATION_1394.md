# CI required-check migration — issue #1394

## Scope

This document prepares the source side of issue #1394. It does not change repository settings, rulesets, branch protection, merge policy or LIVE/runtime state.

Evidence snapshot used for this plan: `main` at `921a447d3ee90334c2e90dd95b392b38141fe30e` on 2026-11-07.

## Why the current `source` requirement is ambiguous

GitHub identifies a workflow status check by the job/check name. Required status checks do not include the workflow name, matrix or event type in that identity. GitHub also recommends unique job names across workflows when those checks are required.

Current workflow inventory contains eight distinct jobs named exactly `source`:

1. `.github/workflows/simple-deploy-coloring-pages-alignment-source.yml`
2. `.github/workflows/simple-deploy-hermes-adoption-source.yml`
3. `.github/workflows/simple-deploy-hermes-prerequisite-materialization-source.yml`
4. `.github/workflows/simple-deploy-hermes-prerequisite-phase-b-parent-source.yml`
5. `.github/workflows/simple-deploy-hermes-prerequisite-recovery-v3-source.yml`
6. `.github/workflows/weather-data-companion-source.yml`
7. `.github/workflows/weathernext-installer-boundary-trusted-dispatch-mode-reconcile-source.yml`
8. `.github/workflows/weathernext-private-installer-boundary-refresh-source.yml`

Some of these workflows use path filtering. GitHub documents that a workflow skipped by path or branch filtering can leave a required workflow check pending, so these specialized workflows must not become individually required checks.

References:

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets

## Source-side migration decision

No `source` job will be individually required after the settings migration. Therefore these eight jobs do not need a rename as part of #1394.

The stable required CI aggregate is `validate`. Source-specific regression programs that previously existed only inside the eight `source` jobs are now registered in `ci/validate-groups.json`. Their Python syntax coverage is centralized in `tests/test-python-syntax.py`, including the two WeatherNext executable Python entrypoints outside the normal `scripts/*.py` and `ops/lib/deploy_executor/*.py` globs.

`tests/test-validation-manifest.py` fails closed if:

- the set of workflows emitting a job named `source` changes without an explicit governance update;
- a Python test directly executed by one of those `source` jobs is missing from the required validation manifest;
- the two non-standard WeatherNext Python entrypoints fall out of centralized syntax coverage;
- `workflow-security` is no longer a dependency of the final `validate` aggregator.

The final `validate` job already depends on the reusable `workflow-security` job. That reusable workflow runs actionlint and zizmor, so workflow-security failure is transitively blocking through required `validate`; direct actionlint/zizmor required contexts are not needed.

## Owner-gated settings phase

After this source change is merged and exact-main `validate` is green, the settings migration is intentionally small:

1. Freshly verify the active `main-governance-v1` ruleset and classic branch metadata.
2. Remove only the ambiguous classic required status context `source`.
3. Preserve the required `validate` context and every other existing branch-protection/ruleset behavior.
4. Leave `main-governance-v1` required checks unchanged unless fresh evidence shows drift.
5. Verify on a real subsequent PR that `validate` blocks failures and no required `source` context remains.

Rulesets and classic branch protection layer together, so the settings mutation must preserve unrelated protection. The current GitHub App cannot read the full admin branch-protection endpoint; do not perform a blind replacement from incomplete metadata.

## Boundary

Source merge does not authorize the repository-settings mutation. The settings phase requires separate explicit owner authorization and an admin-capable execution surface.
