# Weather Composite consumed-JIT GitHub time hardening

This note extends the canonical Weather public runtime executor source contract for `RPi5_main#525` after the fail-closed `deploy-authorizations#24` incident.

## Incident boundary

Authorization `#24` crossed the durable replay-consume boundary and then failed closed at `trusted_checkout_fetch` with a bounded `github_time` reason. The public receipt proved `authorization_reuse_forbidden=true` while both `host_mutation_started=false` and `production_mutation_started=false`. The authorization is therefore permanently non-reusable, and no retry, cleanup or rollback is implied by this source change.

The historical receipt intentionally did not retain the raw underlying exception. Later read-only evidence showed the RPi5 clock and a fresh GitHub `Date` header were closely aligned, so this change does not treat host clock drift as established fact.

## Security invariant retained

Initial pre-consume admission remains unchanged:

- `rozkalns.live-auth.v1` TTL remains 600 seconds;
- future skew remains bounded by the protocol;
- GitHub response timestamps must be timezone-aware and canonical to whole seconds;
- the canonical pre-consume revalidation window still rejects timestamp regression;
- the canonical pre-consume revalidation window still rejects a total GitHub timestamp spread greater than 30 seconds;
- owner identity, raw-body immutability, READY queue binding, exact source/current-main identities, exact-SHA CI, reviewed ancestry, replay availability and sanitized baseline checks remain mandatory.

## Post-consume JIT rule

After durable replay consume, the one-shot authorization cannot become available again. Revalidation still performs the same authorization, queue, source, CI, ancestry, replay-consumed and baseline drift checks, and every GitHub response must still provide a valid canonical timestamp.

The post-consume window differs only in one narrow respect: cross-request `Date` ordering and total wall-clock span are no longer standalone failure reasons. A multi-surface revalidation can legitimately take more than 30 seconds or observe a slightly older `Date` value from another GitHub response path. Burning an already-consumed one-shot authorization for those transport-ordering effects does not add freshness protection because admission TTL and the strict pre-consume sequence were already enforced before the first mutation.

Post-consume evidence therefore retains the newest canonical GitHub timestamp observed during the revalidation. Missing/invalid or non-whole-second timestamps still fail closed.

## Public-safe diagnostics

Consumed-JIT failure receipts remain bounded and must not expose URLs, filesystem paths, tokens, secrets or private runtime data. GitHub-time failures are classified into public-safe subreasons:

- `github_time_unavailable_or_invalid`
- `github_time_noncanonical`
- `github_time_regressed`
- `github_time_spread_exceeded`
- `github_time_other`

The regression and spread codes remain relevant for strict admission and for forensic classification of older behavior; the v2 consumed-JIT runtime path itself tolerates ordering regression and spans over 30 seconds while still requiring valid canonical timestamps.

## Deployment consequence

Merging this source does not change the installed RPi5 operator. The v6 successor bridge is source-only and freezes a one-target transition from the currently installed v5 entrypoint to the reviewed hardening entrypoint. A separate exact owner LIVE authorization is required before creating the v6 trusted checkout or atomically replacing `/usr/local/sbin/rozkalns-weather-public-runtime-operator`.

Only after the v6 installed-closure verification and a fresh sanitized Weather baseline may a new human-authored Composite STRICT LIVE authorization be prepared. Authorization `#24` must never be reused.

## v6 execution-mode failure and v7 successor — Issue #537

The first separately authorized v6 host-convergence attempt created the fixed v6 trusted checkout at exact `RPi5_main@9136c37156e84da3918e58d5d467c8b1e5cc403a`, then failed closed before runtime replacement because the v6 upgrade entrypoint was tracked with Git mode `100644` and therefore was not directly executable. The authorization had already crossed its first allowed Git mutation and is consumed. The v6 checkout is immutable failure evidence: no retry, cleanup, rollback, mode repair or alternate invocation is authorized from it. The installed operator remained at predecessor SHA-256 `4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f`.

Issue #537 adds a source-only v7 successor with a new fixed checkout identity and an entrypoint committed as Git mode `100755`. Regression coverage verifies the Git index/tree mode in addition to the existing zero-input/no-generic-shell contract. The runtime transition remains exactly one atomic replacement of `/usr/local/sbin/rozkalns-weather-public-runtime-operator` from the same predecessor SHA-256 to reviewed target SHA-256 `f6255bf1e80d2918555b0814b0690add739041ac11512297d904fce5e8fc0cf1`. Source merge does not authorize LIVE; a fresh exact owner authorization is required after merge.
