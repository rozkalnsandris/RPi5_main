# CI required-check migration — issue #1394

## Outcome

RPi5_main uses one stable required aggregate, `validate`, for repository regression and workflow-security gating. The former generic `source` required context was ambiguous because several unrelated workflows emitted the same job/check name.

Evidence baseline: `main@7be4b9a0d195a5eaca24e960e0e68bdca84585c4` on 2026-11-07.

## GitHub behavior

GitHub identifies a workflow required status check by the job/check name; workflow name, matrix and event are not part of that identity. GitHub also documents that a workflow skipped by path or branch filtering can leave a required check pending and block merging.

References:

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules
- https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs

## Migration completed so far

The pre-migration inventory contained eight distinct jobs named exactly `source`:

1. `.github/workflows/simple-deploy-coloring-pages-alignment-source.yml`
2. `.github/workflows/simple-deploy-hermes-adoption-source.yml`
3. `.github/workflows/simple-deploy-hermes-prerequisite-materialization-source.yml`
4. `.github/workflows/simple-deploy-hermes-prerequisite-phase-b-parent-source.yml`
5. `.github/workflows/simple-deploy-hermes-prerequisite-recovery-v3-source.yml`
6. `.github/workflows/weather-data-companion-source.yml`
7. `.github/workflows/weathernext-installer-boundary-trusted-dispatch-mode-reconcile-source.yml`
8. `.github/workflows/weathernext-private-installer-boundary-refresh-source.yml`

PR #1399 moved every Python regression program unique to those workflows into `ci/validate-groups.json` and extended centralized Python syntax coverage for the two WeatherNext executable entrypoints outside the normal syntax globs.

The owner-authorized repository-settings migration then removed only the classic required `source` context. Post-verification showed classic branch protection requiring only `validate`; `main-governance-v1` remained active and unchanged.

## Final simplification

Because the eight specialized `source` workflows now provide no unique validation coverage, they are retired. This avoids duplicate CI execution and removes the possibility that a future generic `source` job accidentally becomes ambiguous again.

`tests/test-validation-manifest.py` now fails closed if any workflow reintroduces a top-level job named exactly `source`. The final `validate` job remains the stable aggregate and depends on `workflow-security`; actionlint and zizmor therefore remain transitively blocking through `validate`.

## Verification target

This retirement change is a real post-settings PR. It must demonstrate:

- `validate` is present and successful on the exact PR head;
- no required `source` context is pending or required;
- workflow-security/actionlint/zizmor remain covered through the `validate` dependency chain;
- existing ruleset protections remain unchanged.

## Boundary

This change is source/workflow cleanup only. It does not authorize or perform further repository-settings, merge, LIVE, host/runtime, credential, permission or deployment mutations.
