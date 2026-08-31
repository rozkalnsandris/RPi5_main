# P9 Gate D GitHub REST API 2026-03-10 compatibility repair

Status: source-only forensic repair. Source merge never authorizes host installation, baseline collection, genuine P9, D1 mutation, credential mutation, workflow dispatch, or deployment.

## Incident

A separately owner-authorized Gate D trusted baseline on installed `RPi5_main` source `6f14e91531c4a9215f64397219b41d16883e12c7` stopped fail-closed during the public target pre-auth stage:

- failure: `TARGET_PR_MERGE_SHA_MISMATCH`;
- expected public merge SHA: `db3b0ff76ee471d3b430e440a14d5cabbb1d99bc`;
- observed PR `merge_commit_sha`: `NONE`;
- GitHub server time: `2026-08-31T00:12:29Z`;
- public ETag: `"feb3ee9b82de30d3784d807ae790d1cafcb9377805f2b026a469f1af2e116586"`.

The stop occurred before protected source-App construction/private-key access, before installation-token mint, before the fixed D1 credential read/client construction, before both D1 SELECTs, and before baseline publication. Genuine P9 and StateStore were not reached. The consumed baseline authorization is not reusable.

## Root cause

`ops/lib/deploy_executor/transport.py` pins `X-GitHub-Api-Version: 2026-03-10`.

GitHub documents `2026-03-10` as the first calendar REST API version containing breaking changes. Its breaking-change list removes the `merge_commit_sha` property from pull-request payloads across endpoints that return pull-request objects, including `GET /repos/{owner}/{repo}/pulls/{pull_number}` and `GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls`.

GitHub separately documents `GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls` as the endpoint that lists the merged pull request that introduced a commit to the repository. Public resources may use this endpoint without authentication.

The previous test fixture incorrectly modeled the old pull-request response contract by including `merge_commit_sha`, so source tests passed while the real `2026-03-10` public response omitted the field.

## Reviewed repair

The baseline CLI keeps the API version pinned to `2026-03-10` and does not downgrade to the legacy API contract.

Before any protected source-App/private-key/token work and before D1, the public preflight now reads exactly these pinned public target resources:

1. target repository identity;
2. pinned issue #25;
3. pinned PR #24;
4. immutable expected merge commit `db3b0ff76ee471d3b430e440a14d5cabbb1d99bc`;
5. `commits/db3b0ff76ee471d3b430e440a14d5cabbb1d99bc/pulls` association;
6. compare from the expected merge commit to `main`.

The association response must contain exactly one row matching the pinned PR #24 identity, including its expected head SHA, target repository, closed/merged/non-draft posture, and `main` base. Missing, malformed, or wrong association fails closed with `TARGET_MERGE_PR_ASSOCIATION_MISMATCH` before protected auth or D1.

Only after that commit-specific association proof succeeds, the CLI derives the legacy `merge_commit_sha` compatibility field in a copied in-process PR object so the frozen downstream predicate set remains unchanged. The value is not trusted from the GitHub PR payload and the raw response object is not mutated.

All other repository, issue, PR number/state/merged-at/draft/head/head-repository/base, immutable merge commit/parent, and compare/main predicates remain in force. No automatic retry is added.

Association mismatch diagnostics are bounded to public-safe failure code/endpoint, expected PR number, observed positive PR numbers (or `NONE`/`INVALID`/`MANY`), GitHub server time, and ETag. No response body, secret, private-key material, installation token, D1 token, or D1 row data is logged.

## Regression coverage

The focused public-target-preauth test now:

- asserts `transport.API_VERSION == "2026-03-10"`;
- models the PR and commit-associated-PR payloads without `merge_commit_sha`;
- proves all remaining target issue/PR/merge/compare mismatches still stop before source-App construction and before D1;
- proves missing and wrong commit-to-PR associations stop before source-App construction and before D1;
- verifies public-safe association diagnostics;
- verifies the six public GETs occur once and before `build_source_client()` / installation-token mint;
- proves the raw PR payload is not mutated and the legacy compatibility field is derived only after association proof;
- preserves the existing source-only host-upgrade regression and adds a source-only one-target future upgrade operator bound to the currently installed baseline CLI blob `af13d0d227bfe48b20430d76cfac8c9f5ac971bc`.

## Future host boundary

The source-only operator `scripts/install-deploy-executor-p9-gate-d-api-2026-compat-upgrade.py` exists only to make a later host change reviewable and provenance-bound. It targets only `/usr/local/sbin/rozkalns-deploy-p9-control-baseline`, performs no network request, credential read, D1 request, baseline collection, P9 execution, StateStore access, systemd/config mutation, rollback, or retry, and requires separate STRICT LIVE owner authorization before `--apply`.

A source merge does not authorize that operator. A later host upgrade PASS still does not authorize a fresh Gate D baseline. A later baseline PASS still does not authorize genuine P9.
