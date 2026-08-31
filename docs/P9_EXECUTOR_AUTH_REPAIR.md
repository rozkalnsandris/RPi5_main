# P9 executor authentication repair

## Status

Source-only repair for the P9 genuine read-only authorization canary. This
document does not authorize host installation, credential use, LIVE-AUTH
creation, baseline collection, StateStore access, genuine P9 execution, or
deployment.

## Problem

The P9 source-App path was repaired in PR #304 so JWT construction no longer
depends on an unauthenticated `GET /` GitHub clock probe and a successful
installation token is cached for the one-shot process.

The P9 Deploy Executor read path still used the older generic
`GitHubAppInstallationTokenProvider`. Every `GitHubRestClient` read asks its
token provider for a token, and the generic provider performed all of the
following on every call:

1. unauthenticated `GET /` solely to obtain a `Date` header;
2. generic installation lookup;
3. a fresh installation-token mint.

The genuine P9 composition has separate clients for `deploy-authorizations`
and `ops-workflows` and performs multiple reads before `DRY_RUN_READY`.
Consequently, the old composition could repeatedly mint executor tokens and
could fail on the same unauthenticated clock dependency already removed from
the source-App path.

## Reviewed repair

`ops/lib/deploy_executor/p9_runtime.py` now owns a P9-specific
`P9ExecutorInstallationTokenProvider`. The P8 generic provider remains
unchanged.

For each exact P9 capability repository, the provider:

- accepts only `rozkalnsandris/deploy-authorizations` or
  `rozkalnsandris/ops-workflows`;
- creates the App JWT from local timezone-aware UTC with the existing reviewed
  60-second `iat` backdate and 300-second `exp` window;
- makes the first auth network request to the exact repository-specific
  installation endpoint using the App JWT;
- validates the exact Deploy Executor installation, App, owner, selected
  repository posture, and read-only Issues permission;
- uses the authenticated repository-installation response `Date` for
  installation-token lifetime validation;
- mints a token narrowed to exactly one repository ID and `Issues: read`;
- caches that one token for the lifetime of the one-shot provider.

Authorization and queue clients still use separate provider instances. There is
no generic two-repository token.

The existing `GitHubRestClient` transport policy is unchanged. Its bounded
pre-mutation GET transport retry remains limited to `NetworkFailure` and HTTP
502/503/504, with at most three attempts. Token minting itself has no retry
loop in this P9 provider.

## Regression coverage

`tests/test-deploy-executor-p9-executor-auth-repair.py` proves:

- no unauthenticated root `GET /` is used;
- exact repository-specific installation endpoints are used for both
  capability repositories;
- the exact API version header is retained;
- each provider mints at most once and then returns the cached token;
- token request scope is the exact repository ID with `Issues: read`;
- missing authenticated server time fails before mint;
- installation/App/owner/type/permission drift fails before mint;
- token repository-scope drift is rejected;
- unknown repositories are rejected before network;
- authorization and queue clients receive distinct capability-specific
  providers.

## Future host convergence

Source merge alone does not authorize host mutation.

A later separately owner-authorized STRICT LIVE convergence may use
`scripts/install-deploy-executor-p9-executor-auth-upgrade.py`. The operator is
bounded to exactly:

`/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_runtime.py`

It requires the installed prestate to match reviewed old blob
`977621d420337f5f627fcfc90da5e41e9cd8e739`, `root:root`, mode `0644`, and
requires an exact reviewed source SHA. It performs no network request,
credential read, GitHub token mint, D1 request, baseline collection, P9
execution, StateStore access, systemd change, registry change, rollback, or
retry.

After any future merged source and separately authorized host convergence,
genuine P9 requires a fresh owner authorization and a newly resolved trusted
baseline. Any earlier HELD authorization must not be reused across changed
reviewed source/runtime provenance.
